"""Derived attributes and units of measure.

Two generality items that turn out to be one mechanism (#7 and #10).

## Derived attributes (#7)

Every attribute was a mirror of a stored column, so anything the business computes
had to be recomputed inside each rule that needed it:

    「毛利率」= (revenue - cost) / revenue
    「合同剩余额度」= credit_limit - customer_active_total
    「逾期天数」= today - due_date

Copying that expression into five rules means five places to fix when the business
changes its definition, and five chances for them to disagree. A derived attribute
names it once.

Derived attributes are ordinary attributes to every consumer -- rules, explanations,
the graph view, exports -- and differ only in where the value comes from.

## Units (#10)

A number without a unit is not a business value. `amount = 1000` is meaningless
across a schema where one table stores 元 and another 万元, and `duration = 2` says
nothing at all. The concrete failure this prevents:

    合同金额（万元）> 客户额度（元）

comparing 500万元 against 1,000,000元 as `500 > 1000000` -- false, when the truth is
that the limit is breached fivefold. That is a wrong verdict produced from correct
data.

So a comparison between two quantities in *different* units of the same dimension
is converted; between different *dimensions* it is refused rather than guessed.

## Why evaluation reuses the rule sandbox

A derived expression is evaluated by the same AST-allowlist sandbox as a rule
expression. Deliberately: a second expression evaluator would be a second thing to
audit, and the first time they diverged, one of them would be the way in.

The sandbox is passed **in** rather than imported: this module is a leaf, and the
kernel imports it. Importing back would create the cycle that technical debt item 3
records -- the kind that becomes a hard error at packaging time (ROADMAP stage E),
because a cross-package cycle cannot be papered over with a function-local import.

## Fail-closed, again

A derived attribute that cannot be computed is absent from the rule context, not
None. A rule referencing it then raises NameError, which the kernel turns into "not
passed" with the reason attached (ADR-0002). Injecting None would make
`margin > 0.1` evaluate to False -- indistinguishable from a real breach.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from .database import connect

logger = logging.getLogger(__name__)


class ExpressionSandbox(Protocol):
    """The rule sandbox, injected so this module stays a leaf.

    Returns (value, error); a non-None error means the expression could not be
    evaluated and the value must not be used.
    """

    def __call__(self, expression: str, context: dict[str, Any]) -> tuple[Any, Optional[str]]: ...


class ExpressionValidator(Protocol):
    """The rule expression static check, injected for the same reason."""

    def __call__(self, expression: str) -> dict[str, Any]: ...


_sandbox: Optional[ExpressionSandbox] = None
_validator: Optional[ExpressionValidator] = None


def bind_sandbox(evaluate: ExpressionSandbox, validate: ExpressionValidator) -> None:
    """Wire in the rule sandbox. Called once by the kernel at import time.

    Binding rather than importing keeps the dependency one-directional. It is not a
    plugin point: a deployment that swapped in a different evaluator would get
    derived attributes with different semantics from rules, which is precisely the
    divergence this arrangement exists to prevent.
    """
    global _sandbox, _validator
    _sandbox = evaluate
    _validator = validate


def _evaluate(expression: str, context: dict[str, Any]) -> tuple[Any, Optional[str]]:
    if _sandbox is None:  # pragma: no cover - the kernel binds on import
        raise DerivedAttributeError("规则沙箱尚未绑定，无法求值派生属性。")
    return _sandbox(expression, context)


def _validate_expression(expression: str) -> dict[str, Any]:
    if _validator is None:  # pragma: no cover - the kernel binds on import
        raise DerivedAttributeError("规则沙箱尚未绑定，无法校验派生表达式。")
    return _validator(expression)


class DerivedAttributeError(ValueError):
    """Raised when a derived attribute definition is invalid."""


class UnitError(ValueError):
    """Raised when a unit is unknown or a conversion is not meaningful."""


# -- Units ------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """A unit and its ratio to the canonical unit of its dimension.

    Conversion goes through the canonical unit rather than pairwise factors: N units
    need N factors this way instead of N², and there is one place to check.
    """

    code: str
    name: str
    dimension: str
    # How many canonical units one of this unit is worth. 1 万元 = 10000 元.
    to_canonical: float


# Built-in units. Deliberately small and domain-neutral: currency scale, time and
# the mass/length units that appear in equipment and logistics schemas. Anything
# domain-specific is registered by the deployment rather than shipped here, for the
# same reason ADR-0003 keeps domain vocabulary out of the platform.
#
# Currency *scale* is a unit; currency *identity* is not -- see `convert`.
BUILTIN_UNITS: tuple[Unit, ...] = (
    Unit("yuan", "元", "currency", 1.0),
    Unit("wan_yuan", "万元", "currency", 10_000.0),
    Unit("yi_yuan", "亿元", "currency", 100_000_000.0),
    Unit("fen", "分", "currency", 0.01),
    Unit("second", "秒", "duration", 1.0),
    Unit("minute", "分钟", "duration", 60.0),
    Unit("hour", "小时", "duration", 3600.0),
    Unit("day", "天", "duration", 86_400.0),
    Unit("month_30", "月(30天)", "duration", 2_592_000.0),
    Unit("gram", "克", "mass", 1.0),
    Unit("kilogram", "千克", "mass", 1000.0),
    Unit("tonne", "吨", "mass", 1_000_000.0),
    Unit("millimetre", "毫米", "length", 1.0),
    Unit("metre", "米", "length", 1000.0),
    Unit("kilometre", "千米", "length", 1_000_000.0),
    Unit("percent", "百分比", "ratio", 0.01),
    Unit("ratio", "比率", "ratio", 1.0),
    Unit("piece", "个", "count", 1.0),
)

_UNITS: dict[str, Unit] = {unit.code: unit for unit in BUILTIN_UNITS}


def register_unit(unit: Unit, *, replace: bool = False) -> Unit:
    """Add a deployment-specific unit.

    Replacement is opt-in: silently redefining 吨 would change every stored value's
    meaning without any record of it having happened.
    """
    if not unit.code or not unit.code.isidentifier():
        raise UnitError(f"单位编码必须是合法标识符: {unit.code!r}")
    if unit.to_canonical <= 0:
        raise UnitError(f"单位换算系数必须为正数: {unit.to_canonical!r}")
    if unit.code in _UNITS and not replace:
        raise UnitError(f"单位已存在: {unit.code}。要覆盖请显式传 replace=True。")
    _UNITS[unit.code] = unit
    return unit


def get_unit(code: str) -> Unit:
    unit = _UNITS.get((code or "").strip())
    if unit is None:
        raise UnitError(f"未知单位: {code!r}。已登记: {'、'.join(sorted(_UNITS))}")
    return unit


def known_units() -> tuple[Unit, ...]:
    return tuple(sorted(_UNITS.values(), key=lambda unit: (unit.dimension, unit.to_canonical)))


def convert(value: float, from_code: str, to_code: str) -> float:
    """Convert between units of the same dimension.

    Cross-dimension conversion raises rather than returning the number unchanged:
    comparing a duration against a mass is a modelling error, and quietly passing
    the raw number through would let the resulting verdict look valid.

    Currency is treated as a single dimension covering *scale only* (元/万元/亿元).
    Exchange rates are deliberately out of scope: a rate is time-varying data, and
    embedding one would make a verdict unreproducible (ADR-0005).
    """
    source, target = get_unit(from_code), get_unit(to_code)
    if source.dimension != target.dimension:
        raise UnitError(
            f"无法在不同量纲间换算: {source.name}（{source.dimension}）→ {target.name}（{target.dimension}）。"
            "这通常意味着建模有误，而不是需要换算。"
        )
    return float(value) * source.to_canonical / target.to_canonical


class Quantity(float):
    """A number that carries its unit and converts on comparison.

    Subclasses float so every existing arithmetic operation, aggregate and JSON
    serialisation keeps working on the *stored* magnitude. What changes is
    comparison: comparing 500 万元 with 1000000 元 converts first, instead of
    comparing 500 against 1000000 and concluding the limit is respected.

    Comparison against a plain number is left as a plain comparison. A bare literal
    in a rule (`amount > 0`) has no unit to convert to, and refusing it would break
    every existing rule; the interpretation is "in this attribute's own unit",
    which is what the rule author sees in the model.
    """

    unit: str

    def __new__(cls, value: Any, unit: str) -> "Quantity":
        instance = super().__new__(cls, value)
        instance.unit = unit
        return instance

    def _aligned(self, other: Any) -> Optional[float]:
        """`other` expressed in this quantity's unit, or None if not applicable."""
        if isinstance(other, Quantity) and other.unit != self.unit:
            return convert(float(other), other.unit, self.unit)
        return None

    def __eq__(self, other: object) -> bool:
        aligned = self._aligned(other)
        return float(self) == (aligned if aligned is not None else other)  # type: ignore[operator]

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: Any) -> bool:
        aligned = self._aligned(other)
        return float(self) < (aligned if aligned is not None else other)

    def __le__(self, other: Any) -> bool:
        aligned = self._aligned(other)
        return float(self) <= (aligned if aligned is not None else other)

    def __gt__(self, other: Any) -> bool:
        aligned = self._aligned(other)
        return float(self) > (aligned if aligned is not None else other)

    def __ge__(self, other: Any) -> bool:
        aligned = self._aligned(other)
        return float(self) >= (aligned if aligned is not None else other)

    def __hash__(self) -> int:
        # Hashing on the magnitude alone would make 1万元 and 1元 collide, which is
        # wrong; hashing on the canonical value keeps equal quantities equal.
        return hash((get_unit(self.unit).dimension, float(self) * get_unit(self.unit).to_canonical))

    def __repr__(self) -> str:
        return f"Quantity({float(self)!r}, {self.unit!r})"

    def in_unit(self, code: str) -> "Quantity":
        return Quantity(convert(float(self), self.unit, code), code)

    def describe(self) -> str:
        return f"{float(self):g}{get_unit(self.unit).name}"


# -- Derived attributes -----------------------------------------------------


@dataclass
class DerivedSpec:
    """One derived attribute: a named expression over the instance context.

    `unit` is optional; when set the computed value becomes a `Quantity`, so a
    comparison against another united value converts instead of comparing raw
    magnitudes.
    """

    code: str
    name: str
    expression: str
    unit: str = ""
    description: str = ""

    def validate(self) -> "DerivedSpec":
        """Check the definition through the *rule* sandbox validator.

        Reusing it is the point: a derived expression runs in the same sandbox as a
        rule, so it must pass the same static check. A separate validator would
        drift, and the looser of the two would become the way in.
        """
        if not self.code or not self.code.isidentifier():
            raise DerivedAttributeError(f"派生属性编码必须是合法标识符: {self.code!r}（规则要按此名引用它）")
        if self.code.startswith("_"):
            raise DerivedAttributeError("派生属性编码不能以下划线开头，避免与沙箱内部名冲突")
        validation = _validate_expression(self.expression)
        if not validation["valid"]:
            raise DerivedAttributeError(f"派生表达式不可执行: {validation['error']}")
        if self.unit:
            get_unit(self.unit)
        return self

    def referenced_names(self) -> list[str]:
        return list(_validate_expression(self.expression).get("referencedNames") or [])

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "expression": self.expression,
            "unit": self.unit,
            "description": self.description,
        }

    @classmethod
    def from_row(cls, row: Any) -> "DerivedSpec":
        return cls(
            code=row["code"],
            name=row["name"],
            expression=row["derived_expression"],
            unit=row["unit"] or "",
            description="",
        )


@dataclass
class DerivedResult:
    """A computed derived attribute, with enough detail to explain a verdict."""

    code: str
    name: str
    value: Any
    expression: str
    unit: str = ""
    error: str = ""

    @property
    def computed(self) -> bool:
        return self.error == ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            # A Quantity is a float subclass, so it serialises as its magnitude;
            # the unit travels alongside rather than inside the number.
            "value": float(self.value) if isinstance(self.value, float) else self.value,
            "expression": self.expression,
            "unit": self.unit,
            "error": self.error,
        }


# A derived attribute may reference another one declared before it. Depth is capped
# rather than resolved as a graph: a chain deeper than this is almost certainly a
# modelling mistake, and an uncapped resolver on a cyclic definition would not
# terminate.
MAX_DERIVATION_PASSES = 5


def compute_derived(specs: list[DerivedSpec], context: dict[str, Any]) -> dict[str, DerivedResult]:
    """Evaluate derived attributes against an instance context.

    Multi-pass so one derived attribute can build on another without the modeller
    having to declare them in dependency order -- declaration order in a UI is not
    something a business user should have to reason about. Each pass evaluates
    whatever became computable, and the loop stops as soon as a pass adds nothing.

    Failures are reported per attribute rather than aborting: one bad definition
    must not take out the other attributes of the same object.
    """
    results: dict[str, DerivedResult] = {}
    working = dict(context)
    pending = list(specs)
    for _ in range(MAX_DERIVATION_PASSES):
        if not pending:
            break
        deferred: list[DerivedSpec] = []
        progressed = False
        for spec in pending:
            value, error = _evaluate(spec.expression, working)
            if error:
                deferred.append(spec)
                continue
            if spec.unit and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = Quantity(value, spec.unit)
            results[spec.code] = DerivedResult(spec.code, spec.name, value, spec.expression, spec.unit)
            working[spec.code] = value
            progressed = True
        pending = deferred
        if not progressed:
            break

    # Whatever never became computable is reported with its reason, and stays out of
    # the context so a rule referencing it fails closed.
    for spec in pending:
        _, error = _evaluate(spec.expression, working)
        results[spec.code] = DerivedResult(
            spec.code,
            spec.name,
            None,
            spec.expression,
            spec.unit,
            error=error or "派生表达式依赖的名称不可用",
        )
    return results


def derived_context(results: dict[str, DerivedResult]) -> dict[str, Any]:
    """Values to inject into the rule sandbox. Only computed ones (see module docstring)."""
    return {code: result.value for code, result in results.items() if result.computed}


def apply_units(context: dict[str, Any], units_by_code: dict[str, str]) -> dict[str, Any]:
    """Wrap stored column values in their declared unit.

    Only plain numbers are wrapped. A None stays None -- a missing value has no
    magnitude, and wrapping it as 0 of some unit would make a threshold rule pass.
    """
    if not units_by_code:
        return context
    updated = dict(context)
    for code, unit in units_by_code.items():
        value = context.get(code)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if isinstance(value, Quantity):
            continue
        try:
            get_unit(unit)
        except UnitError as error:
            logger.warning("属性 %s 声明了未知单位 %s，已忽略: %s", code, unit, error)
            continue
        updated[code] = Quantity(value, unit)
    return updated


# -- Persistence ------------------------------------------------------------


def define_derived_attribute(
    platform_db: Path | str,
    ontology_id: int,
    object_code: str,
    spec: DerivedSpec,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Declare a derived attribute on an object.

    Stored as an ordinary `business_attribute` row with `derived_expression` set, so
    every existing consumer -- explanations, the graph view, exports, the frontend --
    sees it as an attribute without changes. Published ontologies are immutable.
    """
    spec.validate()
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise DerivedAttributeError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise DerivedAttributeError("已发布本体不可修改派生属性，请派生新版本。")
        business_object = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, object_code),
        ).fetchone()
        if business_object is None:
            raise DerivedAttributeError(f"业务对象不存在: {object_code}")
        object_id = int(business_object["id"])

        existing = conn.execute(
            "select id, derived_expression from business_attribute where object_id = ? and code = ?",
            (object_id, spec.code),
        ).fetchone()
        if existing is not None and not (existing["derived_expression"] or ""):
            # Overwriting a mapped column with a computed value would silently
            # change what every rule reading that name evaluates against.
            raise DerivedAttributeError(
                f"属性 {spec.code} 已绑定来源列，不能改为派生属性。请换一个编码，或先解除映射。"
            )
        if existing is not None:
            conn.execute(
                """
                update business_attribute
                set name = ?, derived_expression = ?, unit = ?, data_type = 'derived'
                where id = ?
                """,
                (spec.name, spec.expression, spec.unit, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                insert into business_attribute
                    (object_id, code, name, data_type, required, derived_expression, unit)
                values (?, ?, ?, 'derived', 0, ?, ?)
                """,
                (object_id, spec.code, spec.name, spec.expression, spec.unit),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "define_derived_attribute",
                "business_attribute",
                f"{object_code}.{spec.code}",
                json.dumps(spec.to_json(), ensure_ascii=False),
            ),
        )
    return {
        "objectCode": object_code,
        **spec.to_json(),
        "note": "规则表达式可直接按该编码引用此派生值。",
    }


def set_attribute_unit(
    platform_db: Path | str,
    ontology_id: int,
    object_code: str,
    attribute_code: str,
    unit: str,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Declare the unit a stored attribute is measured in.

    An empty unit clears the declaration, which restores plain numeric comparison.
    """
    if unit:
        get_unit(unit)
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise DerivedAttributeError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise DerivedAttributeError("已发布本体不可修改属性单位，请派生新版本。")
        row = conn.execute(
            """
            select ba.id from business_attribute ba
            join business_object bo on bo.id = ba.object_id
            where bo.ontology_id = ? and bo.code = ? and ba.code = ?
            """,
            (ontology_id, object_code, attribute_code),
        ).fetchone()
        if row is None:
            raise DerivedAttributeError(f"属性不存在: {object_code}.{attribute_code}")
        conn.execute("update business_attribute set unit = ? where id = ?", (unit, int(row["id"])))
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (actor, "set_attribute_unit", "business_attribute", f"{object_code}.{attribute_code}", unit),
        )
    return {"objectCode": object_code, "attributeCode": attribute_code, "unit": unit}


def load_derived_specs(conn: Any, ontology_id: int, object_code: str) -> list[DerivedSpec]:
    """Derived specs for one object, on the caller's connection.

    An invalid stored definition is skipped and logged; it will make its rule fail
    closed, which is the safe direction.
    """
    rows = conn.execute(
        """
        select ba.code, ba.name, ba.derived_expression, ba.unit
        from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        where bo.ontology_id = ? and bo.code = ? and ba.derived_expression <> ''
        order by ba.id
        """,
        (ontology_id, object_code),
    ).fetchall()
    specs = []
    for row in rows:
        try:
            specs.append(DerivedSpec.from_row(row).validate())
        except (DerivedAttributeError, UnitError) as error:
            logger.warning("派生属性 %s 不合法，已跳过: %s", row["code"], error)
    return specs


def load_attribute_units(conn: Any, ontology_id: int, object_code: str) -> dict[str, str]:
    """Declared units for the object's stored attributes, keyed by source column.

    Keyed by column name rather than attribute code because units are applied to the
    raw record read from the source, before attribute codes exist in the context.
    """
    rows = conn.execute(
        """
        select ba.code, ba.unit, sc.column_name
        from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        left join source_column sc on sc.id = ba.source_column_id
        where bo.ontology_id = ? and bo.code = ? and ba.unit <> '' and ba.derived_expression = ''
        """,
        (ontology_id, object_code),
    ).fetchall()
    units: dict[str, str] = {}
    for row in rows:
        column = row["column_name"] or row["code"]
        units[column] = row["unit"]
    return units


def list_derived_attributes(platform_db: Path | str, ontology_id: int, object_code: str = "") -> list[dict[str, Any]]:
    clauses = ["bo.ontology_id = ?", "ba.derived_expression <> ''"]
    params: list[Any] = [ontology_id]
    if object_code:
        clauses.append("bo.code = ?")
        params.append(object_code)
    with connect(platform_db) as conn:
        rows = conn.execute(
            f"""
            select bo.code as object_code, ba.code, ba.name, ba.derived_expression, ba.unit
            from business_attribute ba
            join business_object bo on bo.id = ba.object_id
            where {" and ".join(clauses)}
            order by bo.code, ba.code
            """,
            tuple(params),
        ).fetchall()
    return [
        {
            "objectCode": row["object_code"],
            "code": row["code"],
            "name": row["name"],
            "expression": row["derived_expression"],
            "unit": row["unit"] or "",
            "unitName": _unit_name(row["unit"]),
        }
        for row in rows
    ]


def _unit_name(code: Any) -> str:
    if not code:
        return ""
    try:
        return get_unit(str(code)).name
    except UnitError:
        return str(code)
