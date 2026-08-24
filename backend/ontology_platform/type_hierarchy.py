"""Type hierarchy: subtypes that inherit attributes and rules.

Generality item #6. Every business object was a peer, so the most common shape in a
real schema had no expression:

    个人客户 / 企业客户 都是客户
    定期合同 / 框架合同 都是合同
    电气设备 / 机械设备 都是设备

Without inheritance, a rule that applies to *all* customers has to be written once
per subtype. That is not merely repetitive: the copies drift, and when they drift
the platform gives two different answers to the same business question depending on
which subtype the instance happens to be.

## Expansion is deterministic, not search

This is emphatically **not** DL subsumption reasoning (ADR-0005). Nothing is
inferred about *whether* A is a subtype of B -- that is declared. What the hierarchy
does is expand, at assessment time, along declared parent links:

- the subtype's rule set is its own rules plus every ancestor's
- the subtype's attribute set is its own plus every ancestor's

Both are a walk up a declared chain. The same ontology always produces the same
expansion, which is what keeps a verdict reproducible.

## An override must be explicit

Rule codes are unique per ontology, so a subtype cannot shadow an ancestor's rule by
reusing its code. Overriding is therefore **declared**: a rule scoped to the subtype
names the ancestor rule it supersedes in its `overrides` column, and the expansion
drops the superseded one.

Declaring it, rather than inferring it from a name collision, is the safer shape.
A name collision is ambiguous -- two teams can pick the same code by accident, and
the platform would silently disable one team's control. A declaration cannot happen
by accident.

**Weakening is not blocked**, because a legitimate business exception exists (a
state-owned counterparty exempt from a credit check). What is refused is doing it
*invisibly*.

## Cycles are refused at declaration, not at assessment

A cyclic hierarchy has no well-defined expansion. Refusing the declaration means the
failure surfaces to the person who caused it, with the cycle named -- rather than at
assessment time, to a user who cannot act on it.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .database import connect

logger = logging.getLogger(__name__)

# A hierarchy deeper than this is almost certainly a modelling mistake, and the cap
# also bounds the walk if a cycle ever reaches storage despite the checks.
MAX_HIERARCHY_DEPTH = 16


class HierarchyError(ValueError):
    """Raised when a subtype declaration is invalid."""


@dataclass
class InheritedRule:
    """One rule in an object's expanded rule set, with its provenance.

    Provenance is not decoration: a verdict that cites an inherited rule has to be
    able to say which type guarantees it, or the operator cannot tell where to go to
    change it.
    """

    code: str
    origin_object_code: str
    inherited: bool
    overridden_from: str = ""

    def describe(self) -> str:
        if self.overridden_from:
            return f"{self.code}（已覆盖上级规则 {self.overridden_from}）"
        if self.inherited:
            return f"{self.code}（继承自 {self.origin_object_code}）"
        return self.code


@dataclass
class Expansion:
    """The result of expanding an object along its declared ancestry."""

    object_code: str
    ancestors: list[str] = field(default_factory=list)
    rules: list[InheritedRule] = field(default_factory=list)
    # Attribute code -> the object code that declares it.
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def rule_codes(self) -> list[str]:
        return [rule.code for rule in self.rules]

    @property
    def overrides(self) -> list[InheritedRule]:
        return [rule for rule in self.rules if rule.overridden_from]

    def as_dict(self) -> dict[str, Any]:
        return {
            "objectCode": self.object_code,
            "ancestors": list(self.ancestors),
            "rules": [
                {
                    "code": rule.code,
                    "originObjectCode": rule.origin_object_code,
                    "inherited": rule.inherited,
                    "overriddenFrom": rule.overridden_from,
                    "description": rule.describe(),
                }
                for rule in self.rules
            ],
            "attributes": dict(self.attributes),
        }


def declare_subtype(
    platform_db: Path | str,
    ontology_id: int,
    object_code: str,
    parent_object_code: str,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Declare that one object is a subtype of another.

    An empty `parent_object_code` clears the declaration, which restores the object
    to a standalone type.
    """
    if object_code == parent_object_code:
        raise HierarchyError(f"对象不能是自身的子类型: {object_code}")
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise HierarchyError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise HierarchyError("已发布本体不可修改类型层级，请派生新版本。")
        child = _require_object(conn, ontology_id, object_code)
        if parent_object_code:
            _require_object(conn, ontology_id, parent_object_code)
            _refuse_cycle(conn, ontology_id, object_code, parent_object_code)
        conn.execute(
            "update business_object set parent_object_code = ? where id = ?",
            (parent_object_code, int(child["id"])),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "declare_subtype",
                "business_object",
                object_code,
                parent_object_code or "(已解除)",
            ),
        )
    return {"objectCode": object_code, "parentObjectCode": parent_object_code}


def _require_object(conn: Any, ontology_id: int, object_code: str) -> Any:
    row = conn.execute(
        "select id, code from business_object where ontology_id = ? and code = ?",
        (ontology_id, object_code),
    ).fetchone()
    if row is None:
        raise HierarchyError(f"业务对象不存在: {object_code}")
    return row


def _refuse_cycle(conn: Any, ontology_id: int, object_code: str, parent_object_code: str) -> None:
    """Refuse a declaration that would close a loop.

    Checked here rather than at assessment time so the failure reaches the person who
    caused it, naming the cycle, instead of reaching a user who cannot act on it.
    """
    chain = [parent_object_code]
    current = parent_object_code
    for _ in range(MAX_HIERARCHY_DEPTH):
        row = conn.execute(
            "select parent_object_code from business_object where ontology_id = ? and code = ?",
            (ontology_id, current),
        ).fetchone()
        parent = (row["parent_object_code"] or "") if row is not None else ""
        if not parent:
            return
        if parent == object_code:
            raise HierarchyError("类型层级不能形成环: " + " → ".join([object_code, *chain, object_code]))
        chain.append(parent)
        current = parent
    raise HierarchyError(f"类型层级超过 {MAX_HIERARCHY_DEPTH} 层，请检查是否存在环。")


def ancestors_of(conn: Any, ontology_id: int, object_code: str) -> list[str]:
    """Declared ancestors, nearest first.

    A cycle that somehow reached storage is broken by the depth cap and logged,
    rather than looping: refusing to assess the instance at all would turn a bad
    declaration into an outage.
    """
    chain: list[str] = []
    seen = {object_code}
    current = object_code
    for _ in range(MAX_HIERARCHY_DEPTH):
        row = conn.execute(
            "select parent_object_code from business_object where ontology_id = ? and code = ?",
            (ontology_id, current),
        ).fetchone()
        parent = (row["parent_object_code"] or "") if row is not None else ""
        if not parent or parent in seen:
            if parent:
                logger.warning("类型层级存在环，已在 %s 处截断: %s", parent, " → ".join([*chain, parent]))
            return chain
        chain.append(parent)
        seen.add(parent)
        current = parent
    logger.warning("类型层级超过 %s 层，已截断: %s", MAX_HIERARCHY_DEPTH, " → ".join(chain))
    return chain


def subtypes_of(conn: Any, ontology_id: int, object_code: str) -> list[str]:
    """Direct subtypes. Used to report what a change to a supertype affects."""
    rows = conn.execute(
        "select code from business_object where ontology_id = ? and parent_object_code = ? order by code",
        (ontology_id, object_code),
    ).fetchall()
    return [row["code"] for row in rows]


def expand(conn: Any, ontology_id: int, object_code: str) -> Expansion:
    """Expand an object into its full rule and attribute set.

    A rule scoped to the object may declare that it supersedes an ancestor's rule; the
    superseded one is then dropped and the fact recorded. Declared rather than inferred
    from a name collision, because a collision is ambiguous -- two teams can pick the
    same code by accident, and the platform would then silently disable one team's
    control.
    """
    ancestors = ancestors_of(conn, ontology_id, object_code)
    expansion = Expansion(object_code=object_code, ancestors=ancestors)

    # Own rules first, then each ancestor by increasing distance.
    collected: list[InheritedRule] = []
    superseded: dict[str, str] = {}
    for index, source in enumerate([object_code, *ancestors]):
        for code, overrides in _rule_declarations(conn, ontology_id, source):
            if overrides:
                # Remember which ancestor rule this one replaces, and by whom, so the
                # replacement is reportable rather than merely effective.
                superseded.setdefault(overrides, source)
            collected.append(InheritedRule(code=code, origin_object_code=source, inherited=index > 0))
    expansion.rules = [_with_override_note(rule, superseded) for rule in collected if rule.code not in superseded]

    for source in [object_code, *ancestors]:
        for code in _attribute_codes(conn, ontology_id, source):
            # An own attribute shadows an inherited one of the same code; the
            # subtype's own column is what its instances actually carry.
            expansion.attributes.setdefault(code, source)
    return expansion


def _with_override_note(rule: InheritedRule, superseded: dict[str, str]) -> InheritedRule:
    """Record on the overriding rule which ancestor rule it replaced."""
    replaced = [code for code, by in superseded.items() if by == rule.origin_object_code]
    if replaced and not rule.inherited:
        rule.overridden_from = "、".join(sorted(replaced))
    return rule


def _rule_declarations(conn: Any, ontology_id: int, object_code: str) -> list[tuple[str, str]]:
    """(code, overrides) for rules scoped to one object.

    `overrides` is read defensively: the column postdates the rule table, and a row
    from an older deployment simply overrides nothing.
    """
    rows = conn.execute(
        "select code, overrides from business_rule where ontology_id = ? and scope_object_code = ? order by code",
        (ontology_id, object_code),
    ).fetchall()
    declarations = []
    for row in rows:
        try:
            overrides = row["overrides"] or ""
        except (KeyError, IndexError, TypeError):
            overrides = ""
        declarations.append((row["code"], overrides))
    return declarations


def _attribute_codes(conn: Any, ontology_id: int, object_code: str) -> list[str]:
    rows = conn.execute(
        """
        select ba.code from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        where bo.ontology_id = ? and bo.code = ?
        order by ba.code
        """,
        (ontology_id, object_code),
    ).fetchall()
    return [row["code"] for row in rows]


def inherited_rule_scopes(conn: Any, ontology_id: int, object_code: str) -> list[str]:
    """Object codes whose rules apply to this object, nearest first.

    The kernel loads rules by scope; this is the list of scopes it must load so an
    ancestor's rules are evaluated against a subtype's instance.
    """
    return [object_code, *ancestors_of(conn, ontology_id, object_code)]


def describe_hierarchy(platform_db: Path | str, ontology_id: int) -> list[dict[str, Any]]:
    """The declared hierarchy, for review and for the graph view."""
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select code, name, parent_object_code
            from business_object where ontology_id = ?
            order by code
            """,
            (ontology_id,),
        ).fetchall()
        items = []
        for row in rows:
            expansion = expand(conn, ontology_id, row["code"])
            items.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "parentObjectCode": row["parent_object_code"] or "",
                    "ancestors": expansion.ancestors,
                    "subtypes": subtypes_of(conn, ontology_id, row["code"]),
                    "inheritedRuleCount": sum(1 for rule in expansion.rules if rule.inherited),
                    "overrides": [rule.describe() for rule in expansion.overrides],
                }
            )
    return items


def parent_of(conn: Any, ontology_id: int, object_code: str) -> Optional[str]:
    row = conn.execute(
        "select parent_object_code from business_object where ontology_id = ? and code = ?",
        (ontology_id, object_code),
    ).fetchone()
    if row is None:
        return None
    return row["parent_object_code"] or None
