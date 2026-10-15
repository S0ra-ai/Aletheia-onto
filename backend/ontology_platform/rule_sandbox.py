"""The rule expression sandbox: one evaluator, one thing to audit.

Extracted from `semantic_kernel` to break the last top-level import cycle
(`ontology` ↔ `semantic_kernel`, technical debt item 3). Draft generation validates
the rules it writes, and the kernel explains the instances it assesses, so each
module needed something from the other. The sandbox is what draft generation actually
wanted, and it depends on neither -- so it becomes the shared leaf and both cycles
disappear.

That is the packaging argument. The stronger argument is that this *is* the security
boundary, and a security boundary buried in a 1,200-line module is a boundary nobody
reviews. Everything that decides what a rule expression may do now lives in one file:

- `ALLOWED_AST_NODES` -- the node allowlist
- `FORBIDDEN_ATTRIBUTE_PREFIXES` -- blocks `__class__`, `__globals__` and friends
- `RULE_FUNCTION_REGISTRY` -- which functions are callable
- `evaluate_expression_value` -- the single `eval` call in the codebase

## One evaluator, three callers

Business rules, workflow transition guards and derived attributes all evaluate here.
Deliberately: a second evaluator would drift, and the first time they diverged, the
looser of the two would be the way in.

## Values that broadcast

`RelatedRows` and `RelatedValues` let a rule say `payment_plan.amount > 0` against a
collection, broadcasting element-wise. `MappedValue` lets `status == 'A'` and
`status == '生效中'` both hold for one cell (ADR-0008). These live here because they
are part of what an expression can mean, not incidental data plumbing.

Stability: `validate_rule_expression`, `evaluate_rule_expression` and
`register_rule_function` are public. The rest is internal (ADR-0007).
"""

from __future__ import annotations

import ast
import logging
import re
from typing import Any, Callable, Iterable

from .derived_attributes import bind_sandbox
from .registry import Registry, load_entry_point_plugins
from .value_mapping import state_for

logger = logging.getLogger(__name__)

__all__ = [
    # The public surface. A third party writing rule functions or validating an
    # expression uses these; everything else is internal and may change (ADR-0007).
    "MappedValue",
    "RelatedRows",
    "RelatedValues",
    "RowObject",
    "allowed_rule_function_names",
    "apply_value_mappings",
    "evaluate_expression_value",
    "evaluate_rule_expression",
    "load_rule_function_plugins",
    "register_rule_function",
    "validate_rule_expression",
]


class RowObject:
    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, name: str) -> Any:
        return self._values.get(name)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class MappedValue(str):
    """A legacy code that also compares equal to its semantic state name.

    Subclasses str so every existing operation on the column value keeps working
    -- comparison, `in`, string methods, JSON serialisation. What changes is that
    ``status == 'A'`` and ``status == '生效中'`` are both true for the same cell,
    which is what lets a rule be written in business language without breaking
    rules already written against the raw code.
    """

    state: str

    def __new__(cls, raw: Any, state: str) -> "MappedValue":
        instance = super().__new__(cls, "" if raw is None else str(raw))
        instance.state = state
        return instance

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other or self.state == other
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return NotImplemented if result is NotImplemented else not result

    def __hash__(self) -> int:
        # Equality spans two strings, so hash on the raw value only; dict lookups
        # by state name are not supported and would be ambiguous anyway.
        return str.__hash__(self)


class RelatedValues(list[Any]):
    def __eq__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value == other for value in self]

    def __ne__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value != other for value in self]

    # Comparisons deliberately broadcast element-wise so a rule can say
    # `payment_plan.amount > 0` against every related row. That is incompatible
    # with list's own comparison signature, hence the overrides.
    def __lt__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "lt") for value in self]

    def __le__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "le") for value in self]

    def __gt__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "gt") for value in self]

    def __ge__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "ge") for value in self]


class RelatedRows:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = [RowObject(row) for row in rows]

    def __getattr__(self, name: str) -> RelatedValues:
        return RelatedValues([row.as_dict().get(name) for row in self._rows])

    def __len__(self) -> int:
        return len(self._rows)

    def as_list(self) -> list[dict[str, Any]]:
        return [row.as_dict() for row in self._rows]


ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
)


RULE_FUNCTION_REGISTRY: Registry[Callable[..., Any]] = Registry("规则函数")

RULE_FUNCTION_ENTRY_POINT_GROUP = "aletheia.rule_functions"


def register_rule_function(
    name: str,
    implementation: Callable[..., Any],
    *,
    replace: bool = False,
) -> Callable[..., Any]:
    """Make a function callable from rule expressions.

    >>> register_rule_function("abs", abs)                 # doctest: +SKIP
    >>> register_rule_function("days_between", days_between)  # doctest: +SKIP

    Names must be plain identifiers: the sandbox matches `ast.Name` nodes, so a
    dotted name could never be resolved and would fail confusingly at eval time.
    """
    if not name.isidentifier():
        raise ValueError(f"规则函数名必须是合法标识符: {name!r}")
    if name.startswith("_"):
        raise ValueError(f"规则函数名不能以下划线开头，避免与沙箱内部名冲突: {name!r}")
    if not callable(implementation):
        raise ValueError(f"规则函数 {name!r} 必须可调用")
    RULE_FUNCTION_REGISTRY.register(name, implementation, replace=replace)
    return implementation


def allowed_rule_function_names() -> frozenset[str]:
    return frozenset(RULE_FUNCTION_REGISTRY.names())


def load_rule_function_plugins() -> list[str]:
    return load_entry_point_plugins(
        RULE_FUNCTION_ENTRY_POINT_GROUP,
        lambda name, func: register_rule_function(name, func),
    )


FORBIDDEN_ATTRIBUTE_PREFIXES = ("__",)


def evaluate_rule_expression(expression: str, context: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluate an expression in the rule sandbox.

    The one entry point for a yes/no verdict: business rules, workflow transition
    guards and anything a plugin adds all come through here, so there is exactly one
    sandbox to audit and every caller inherits its hardening.

    Returns (passed, error). A non-None error means the expression could not be
    evaluated; callers are expected to treat that as *not passed* (ADR-0002).
    """
    value, error = evaluate_expression_value(expression, context)
    if error is not None:
        return False, error
    return bool(value), None


def evaluate_expression_value(expression: str, context: dict[str, Any]) -> tuple[Any, str | None]:
    """Evaluate an expression and return its *value* rather than its truthiness.

    Rules only need a verdict, but a derived attribute needs the number. Both go
    through this one function so there is exactly one sandbox to audit -- a second
    evaluator would drift, and the looser of the two would become the way in.

    Returns (value, error). A non-None error means the expression could not be
    evaluated; callers are expected to treat that as unusable (ADR-0002), never to
    substitute a default.
    """
    normalized = _normalize_expression(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
        _validate_ast(tree)
        value = eval(compile(tree, "<business-rule>", "eval"), {"__builtins__": {}}, _allowed_names(context))
        return value, None
    except Exception as error:
        return None, _describe_evaluation_failure(error)


_NAME_NOT_DEFINED = re.compile(r"name '([^']+)' is not defined")


def _describe_evaluation_failure(error: Exception) -> str:
    """A rule-evaluation failure, described for the person who has to fix the rule.

    The exception's own text used to be the entire message, and this message is not an edge
    case: §13 of the extension guide describes a rule referencing an unavailable association
    as an expected outcome, so `name 'signed_date' is not defined` was routinely the first
    thing a new deployment read in its first verdict. That is a true statement about a Python
    namespace and a useless one about a business rule.

    Each branch names what the modeller can act on. The identifier is kept, because it is how
    they find the rule; the framing says what its absence usually means, because "not defined"
    invites the reader to look for a typo when the usual cause is a blueprint rule applied to
    an object that never had that association.
    """
    if isinstance(error, NameError):
        name = getattr(error, "name", "") or (_NAME_NOT_DEFINED.search(str(error)) or [None, ""])[1]
        if name:
            return (
                f"表达式引用了此处不可用的名称「{name}」。"
                "常见原因是该规则来自行业蓝图而本对象没有这个关联，或该字段尚未映射到本对象；"
                "可按扩展指南第 13 节处理。"
            )
        return "表达式引用了此处不可用的名称。"
    if isinstance(error, SyntaxError):
        return f"表达式语法不合法：{error.msg}"
    if isinstance(error, ZeroDivisionError):
        return "表达式除以零，无法得出判定。"
    if isinstance(error, TypeError):
        # The second common case: a column holding text compared as a number, or a
        # comparison against a field whose value is absent. CPython's own wording names the
        # two types, and which two clashed is exactly what the modeller needs -- so the
        # types are translated rather than dropped, and the sentence around them is ours.
        clash = next((p.search(str(error)) for p in _COMPARISON_PATTERNS if p.search(str(error))), None)
        if clash:
            left, right = _type_name(clash.group(1)), _type_name(clash.group(2))
            # The explanation has to follow the types, not be attached to the branch: a
            # comparison against an empty value and a text-versus-number comparison are
            # fixed differently, and asserting the wrong cause is worse than asserting none.
            if "空值" in (left, right):
                cause = "常见原因是所引用的字段在该实例上为空值；请确认该字段是否必填，或在表达式里先处理空值。"
            elif "文本" in (left, right):
                cause = "常见原因是该字段存的是文本却按数字参与比较；请核对所引用字段的实际取值类型后改写表达式。"
            else:
                cause = "请核对所引用字段的实际取值类型后改写表达式。"
            return f"表达式中的值类型不匹配：无法在「{left}」与「{right}」之间比较。{cause}"
        return (
            "表达式中的值类型不匹配：参与运算的值，其实际类型与表达式假定的不一致。"
            "请核对所引用字段的实际取值类型后改写表达式。"
        )
    if isinstance(error, LookupError):
        # A registered rule function's own KeyError/IndexError: the text is its author's, so
        # it is quoted rather than replaced, with the fact that it came from a function.
        return f"表达式求值缺少所需数据（{type(error).__name__}）：{error}"
    if isinstance(error, (ValueError, ArithmeticError)):
        return f"表达式无法求值：{_readable_value_error(error)}"
    # Anything else is a defect in the sandbox or in a registered rule function rather than
    # a property of the rule text, so the message names the type and the detail goes to the
    # log instead of into every verdict that rule appears in.
    logger.warning("规则求值出现非预期异常：%s: %s", type(error).__name__, error)
    return f"表达式求值失败（{type(error).__name__}），请查看服务端日志。"


# `'<' not supported between instances of 'str' and 'int'` and its arithmetic sibling. The
# two types are the useful part, and the part that is not in the reader's language.
_COMPARISON_PATTERNS = (
    re.compile(r"not supported between instances of '(\w+)' and '(\w+)'"),
    re.compile(r"unsupported operand type\(s\) for [-+*/%]+: '(\w+)' and '(\w+)'"),
)

# `could not convert string to float: 'abc'` / `invalid literal for int() with base 10: 'x'`
_CONVERSION_PATTERNS = (
    re.compile(r"could not convert string to (\w+): '([^']*)'"),
    re.compile(r"invalid literal for (\w+)\(\) with base \d+: '([^']*)'"),
)

_TYPE_NAMES = {
    "str": "文本",
    "int": "整数",
    "float": "小数",
    "bool": "布尔值",
    "NoneType": "空值",
    "Decimal": "小数",
    "datetime": "日期时间",
    "date": "日期",
    "list": "列表",
    "dict": "对象",
    "tuple": "列表",
    "set": "集合",
}


def _type_name(python_type: str) -> str:
    return _TYPE_NAMES.get(python_type, python_type)


def _readable_value_error(error: Exception) -> str:
    """A ValueError's text, with the idiom that actually occurs rewritten.

    Converting a text column is what produces most of these, so the conversion messages are
    the ones a modeller meets. Everything else is passed through unchanged rather than
    guessed at — a registered rule function's own ValueError is its author's wording, and
    restating it would be overwriting someone else's message with ours.
    """
    text = str(error)
    for pattern in _CONVERSION_PATTERNS:
        match = pattern.search(text)
        if match:
            target, value = _type_name(match.group(1).lower()), match.group(2)
            return f"无法把「{value}」当作{target}参与计算；该字段存的是文本，而表达式按数值使用它。"
    return text


def _normalize_expression(expression: str) -> str:
    normalized = re.sub(r"\bnull\b", "None", expression)
    normalized = normalized.replace(" is not None", " != None").replace(" is None", " == None")
    return normalized


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(f"不允许的规则表达式节点: {type(node).__name__}")
        if isinstance(node, ast.Call):
            allowed = allowed_rule_function_names()
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed:
                raise ValueError(f"只允许 {'、'.join(sorted(allowed))} 函数")
            if node.keywords:
                raise ValueError("规则函数不支持关键字参数")
        if isinstance(node, ast.Attribute) and node.attr.startswith(FORBIDDEN_ATTRIBUTE_PREFIXES):
            raise ValueError(f"不允许访问内部属性: {node.attr}")


def validate_rule_expression(expression: str, available_names: Iterable[str] | None = None) -> dict[str, Any]:
    """Statically check a business rule expression.

    Called when a rule is written so an unparseable expression is rejected up
    front instead of silently failing during assessment.
    """
    text = (expression or "").strip()
    if not text:
        return {"valid": False, "error": "规则表达式不能为空", "referencedNames": []}
    normalized = _normalize_expression(text)
    try:
        tree = ast.parse(normalized, mode="eval")
        _validate_ast(tree)
    except SyntaxError as error:
        return {"valid": False, "error": f"规则表达式语法错误: {error.msg}", "referencedNames": []}
    except ValueError as error:
        return {"valid": False, "error": str(error), "referencedNames": []}

    referenced = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in allowed_rule_function_names() and node.id != "None"
        }
    )
    result: dict[str, Any] = {"valid": True, "error": "", "referencedNames": referenced}
    if available_names is not None:
        known = set(available_names)
        unknown = [name for name in referenced if name not in known]
        result["unknownNames"] = unknown
        if unknown:
            result["warning"] = "表达式引用了当前来源结构中不存在的字段: " + "、".join(unknown)
    return result


def _allowed_names(context: dict[str, Any]) -> dict[str, Any]:
    names = dict(context)
    # Registered functions are added after the context so a column named `sum`
    # cannot shadow the function and silently change what a rule means.
    names.update(dict(RULE_FUNCTION_REGISTRY.items()))
    names["None"] = None
    return names


def _count(value: Any) -> int:
    if isinstance(value, (RelatedValues, list, tuple)):
        return sum(1 for item in value if item)
    if isinstance(value, RelatedRows):
        return len(value)
    return 1 if value else 0


def _safe_compare(left: Any, right: object, operator: str) -> bool:
    try:
        if operator == "lt":
            return left < right
        if operator == "le":
            return left <= right
        if operator == "gt":
            return left > right
        if operator == "ge":
            return left >= right
    except TypeError:
        return False
    return False


def apply_value_mappings(
    context: dict[str, Any], table_name: str, mappings: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Wrap mapped column values so business language and legacy codes both match.

    Lives with the sandbox rather than with the kernel because what a comparison means
    is a property of the evaluator, not of how the row was loaded.
    """
    updated = dict(context)
    for column, value in context.items():
        state = state_for(mappings, table_name, column, value)
        if state is not None and not isinstance(value, MappedValue):
            updated[column] = MappedValue(value, state)
    return updated


# The default rule functions. Registered rather than hardcoded so a deployment can add
# domain predicates without forking, while every entry still runs inside the AST
# allowlist: registering grants the right to *call* a function, never the right to skip
# node validation.
register_rule_function("sum", sum)
register_rule_function("len", len)
register_rule_function("count", _count)
register_rule_function("any", any)
register_rule_function("all", all)

# Derived attributes evaluate in this same sandbox, injected rather than imported so
# the dependency stays one-directional (see `derived_attributes`).
bind_sandbox(evaluate_expression_value, validate_rule_expression)
