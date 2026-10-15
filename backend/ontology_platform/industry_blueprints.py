from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .context import PlatformDb
from .database import connect


@dataclass(frozen=True)
class RuleTemplate:
    code: str
    name: str
    rule_type: str
    scope_object_code: str
    expression: str
    severity: str
    natural_language: str


@dataclass(frozen=True)
class IndustryBlueprint:
    id: str
    name: str
    domain: str
    description: str
    object_hints: dict[str, str]
    attribute_hints: dict[str, str]
    rule_templates: tuple[RuleTemplate, ...]
    table_keywords: tuple[str, ...]
    capability_tags: tuple[str, ...]
    source: str = "builtin"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "objectHints": self.object_hints,
            "attributeHints": self.attribute_hints,
            "rules": [template.__dict__ for template in self.rule_templates],
            "tableKeywords": list(self.table_keywords),
            "capabilityTags": list(self.capability_tags),
            "source": self.source,
        }


BLUEPRINTS: dict[str, IndustryBlueprint] = {
    "contract-management": IndustryBlueprint(
        id="contract-management",
        name="合同管理蓝图",
        domain="合同管理",
        description="覆盖客户、合同、付款计划、发票等合同生命周期对象与履约风控规则。",
        object_hints={
            "customer": "客户",
            "contract": "合同",
            "payment_plan": "付款计划",
            "invoice": "发票",
        },
        attribute_hints={
            "customer_name": "客户名称",
            "credit_status": "信用状态",
            "industry": "行业",
            "contract_no": "合同编号",
            "customer_id": "客户",
            "title": "标题",
            "amount": "金额",
            "status": "状态",
            "signed_date": "签订日期",
            "effective_date": "生效日期",
            "end_date": "结束日期",
            "plan_no": "付款计划编号",
            "due_date": "到期日期",
            "planned_amount": "计划金额",
            "paid_amount": "已付金额",
            "paid_date": "付款日期",
            "invoice_no": "发票编号",
            "invoice_amount": "发票金额",
            "issued_date": "开票日期",
        },
        rule_templates=(
            RuleTemplate(
                "contract_amount_positive",
                "合同金额必须大于 0",
                "validation",
                "contract",
                "amount > 0",
                "blocking",
                "合同金额必须大于 0。",
            ),
            RuleTemplate(
                "effective_contract_signed",
                "已生效合同必须有签订日期",
                "validation",
                "contract",
                "status != 'effective' or signed_date != null",
                "blocking",
                "当合同状态为已生效时，签订日期不能为空。",
            ),
            RuleTemplate(
                "blacklist_customer_warning",
                "黑名单客户合同风险",
                "risk",
                "contract",
                "customer.credit_status != 'blacklist'",
                "warning",
                "客户为黑名单时，新签或存量合同需要风险复核。",
            ),
            RuleTemplate(
                "payment_plan_amount_match",
                "付款计划总额应等于合同金额",
                "validation",
                "contract",
                "sum(payment_plan.planned_amount) == amount",
                "warning",
                "付款计划总额应等于合同金额。",
            ),
            RuleTemplate(
                "overdue_payment_warning",
                "逾期付款风险",
                "risk",
                "payment_plan",
                "status != 'overdue'",
                "warning",
                "付款计划已逾期，需提示履约风险。",
            ),
        ),
        table_keywords=("contract", "customer", "payment", "invoice"),
        capability_tags=("contract-risk", "payment-control", "approval-preflight"),
    ),
    "equipment-maintenance": IndustryBlueprint(
        id="equipment-maintenance",
        name="设备运维蓝图",
        domain="设备运维",
        description="覆盖设备、工单、点检、备件等运维对象与安全库存、故障闭环规则。",
        object_hints={
            "equipment": "设备",
            "work_order": "工单",
            "inspection_record": "点检记录",
            "spare_part": "备件",
        },
        attribute_hints={
            "equipment_code": "设备编号",
            "equipment_name": "设备名称",
            "location": "位置",
            "criticality": "重要等级",
            "work_order_no": "工单编号",
            "equipment_id": "设备",
            "fault_description": "故障描述",
            "reported_at": "报修时间",
            "closed_at": "关闭时间",
            "inspection_date": "点检日期",
            "result": "结果",
            "part_code": "备件编号",
            "part_name": "备件名称",
            "stock_quantity": "库存数量",
            "minimum_quantity": "最低库存",
        },
        rule_templates=(
            RuleTemplate(
                "critical_equipment_open_fault",
                "重要设备存在未关闭工单风险",
                "risk",
                "equipment",
                "criticality != 'high' or count(work_order.status == 'open') == 0",
                "warning",
                "重要设备存在未关闭工单时，需要优先处理。",
            ),
            RuleTemplate(
                "closed_work_order_has_closed_at",
                "已关闭工单必须有关闭时间",
                "validation",
                "work_order",
                "status != 'closed' or closed_at != null",
                "blocking",
                "工单关闭时必须记录关闭时间。",
            ),
            RuleTemplate(
                "spare_part_stock_floor",
                "备件库存不能低于最低库存",
                "risk",
                "spare_part",
                "stock_quantity >= minimum_quantity",
                "warning",
                "备件库存低于最低库存时，需要补货。",
            ),
        ),
        table_keywords=("equipment", "work_order", "inspection", "spare_part"),
        capability_tags=("fault-risk", "work-order-preflight", "inventory-warning"),
    ),
    "generic-enterprise": IndustryBlueprint(
        id="generic-enterprise",
        name="通用企业蓝图",
        domain="通用业务",
        description="适用于未知行业的基础对象识别、字段语义化和数值校验种子规则。",
        object_hints={},
        attribute_hints={
            "id": "标识",
            "name": "名称",
            "code": "编码",
            "status": "状态",
            "created_at": "创建时间",
            "updated_at": "更新时间",
        },
        rule_templates=(),
        table_keywords=(),
        capability_tags=("metadata-scan", "semantic-mapping", "rule-seeding"),
    ),
}


def list_industry_blueprints(platform_db: PlatformDb | None = None) -> list[dict[str, Any]]:
    blueprints = dict(BLUEPRINTS)
    if platform_db is not None:
        blueprints.update(_custom_blueprints(platform_db))
    return [blueprint.to_dict() for blueprint in blueprints.values()]


def get_industry_blueprint(
    blueprint_id: str | None, domain: str | None = None, platform_db: PlatformDb | None = None
) -> IndustryBlueprint:
    blueprints = dict(BLUEPRINTS)
    if platform_db is not None:
        blueprints.update(_custom_blueprints(platform_db))
    if blueprint_id:
        try:
            return blueprints[blueprint_id]
        except KeyError as error:
            raise ValueError(f"行业蓝图不存在: {blueprint_id}") from error
    if domain:
        normalized = domain.strip().lower()
        for blueprint in blueprints.values():
            if normalized in {blueprint.domain.lower(), blueprint.name.lower(), blueprint.id.lower()}:
                return blueprint
    return blueprints["generic-enterprise"]


def infer_industry_blueprint(
    table_names: list[str], domain: str | None = None, platform_db: PlatformDb | None = None
) -> IndustryBlueprint:
    if domain:
        try:
            return get_industry_blueprint(None, domain, platform_db)
        except ValueError:
            pass
    blueprints = dict(BLUEPRINTS)
    if platform_db is not None:
        blueprints.update(_custom_blueprints(platform_db))
    table_text = " ".join(table_names).lower()
    best_blueprint = blueprints["generic-enterprise"]
    best_score = 0
    for blueprint in blueprints.values():
        score = sum(1 for keyword in blueprint.table_keywords if keyword in table_text)
        if score > best_score or (
            score == best_score and score > 0 and blueprint.source == "custom" and best_blueprint.source != "custom"
        ):
            best_score = score
            best_blueprint = blueprint
    return best_blueprint


def upsert_industry_blueprint(platform_db: PlatformDb, payload: dict[str, Any]) -> dict[str, Any]:
    blueprint = _blueprint_from_payload(payload, "custom")
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into industry_blueprint (
                id, name, domain, description, object_hints, attribute_hints,
                rule_templates, table_keywords, capability_tags, source, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'custom', current_timestamp)
            on conflict(id) do update set
                name = excluded.name,
                domain = excluded.domain,
                description = excluded.description,
                object_hints = excluded.object_hints,
                attribute_hints = excluded.attribute_hints,
                rule_templates = excluded.rule_templates,
                table_keywords = excluded.table_keywords,
                capability_tags = excluded.capability_tags,
                updated_at = current_timestamp
            """,
            (
                blueprint.id,
                blueprint.name,
                blueprint.domain,
                blueprint.description,
                json.dumps(blueprint.object_hints, ensure_ascii=False),
                json.dumps(blueprint.attribute_hints, ensure_ascii=False),
                json.dumps([item.__dict__ for item in blueprint.rule_templates], ensure_ascii=False),
                json.dumps(list(blueprint.table_keywords), ensure_ascii=False),
                json.dumps(list(blueprint.capability_tags), ensure_ascii=False),
            ),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "system",
                "upsert_industry_blueprint",
                "industry_blueprint",
                blueprint.id,
                json.dumps({"domain": blueprint.domain}, ensure_ascii=False),
            ),
        )
    return blueprint.to_dict()


def _custom_blueprints(platform_db: PlatformDb) -> dict[str, IndustryBlueprint]:
    with connect(platform_db) as conn:
        rows = conn.execute("select * from industry_blueprint order by id").fetchall()
        return {
            row["id"]: IndustryBlueprint(
                id=row["id"],
                name=row["name"],
                domain=row["domain"],
                description=row["description"],
                object_hints=json.loads(row["object_hints"] or "{}"),
                attribute_hints=json.loads(row["attribute_hints"] or "{}"),
                rule_templates=tuple(
                    _rule_template(index, item) for index, item in enumerate(json.loads(row["rule_templates"] or "[]"))
                ),
                table_keywords=tuple(json.loads(row["table_keywords"] or "[]")),
                capability_tags=tuple(json.loads(row["capability_tags"] or "[]")),
                source=row["source"],
            )
            for row in rows
        }


# Field names a blueprint may use to identify or label a hint entry. A blueprint arriving
# from a model, or from a hand-written file, is free to write these fields as a list of
# descriptors instead of a mapping -- and that is the *richer* form, because a descriptor
# can carry the source table, primary key and relationships that `{code: label}` cannot.
_HINT_KEY_FIELDS = ("code", "objectCode", "object_code", "sourceTable", "source_table", "table", "column", "key", "id")
_HINT_LABEL_FIELDS = ("name", "label", "displayName", "display_name", "title", "description")


def _hint_key(value: Any) -> str:
    """The code from a hint entry."""
    if isinstance(value, dict):
        for field in _HINT_KEY_FIELDS:
            if value.get(field):
                return str(value[field])
        return ""
    return "" if value is None else str(value)


def _hint_label(value: Any) -> str:
    """The label from a hint entry.

    Structures are refused rather than stringified: `str(["合同", "销售合同"])` is truthy,
    so a list of candidate names used to be accepted and stored as the literal Python repr
    of that list -- a business term no one wrote, sitting in the vocabulary the ontology is
    built from.
    """
    if isinstance(value, dict):
        for field in _HINT_LABEL_FIELDS:
            if value.get(field):
                return str(value[field])
        return ""
    if isinstance(value, (list, tuple, set, frozenset)) or value is None:
        return ""
    return str(value)


def coerce_hints(raw: Any, *, dotted: bool = False) -> dict[str, str]:
    """Read a hints field into `{code: label}`, whichever shape it arrives in.

    Two shapes are accepted because both really occur: the mapping this platform writes,
    and the list of descriptors a model produces when a prompt names the field without
    stating its shape. Only a faithful projection is performed -- an entry's own code and
    label, or a bare string used as both -- because these labels become the business
    vocabulary of a governed ontology, and a name the author never wrote is
    indistinguishable from one they did once it is stored.

    This replaces `dict(raw)`, which failed in both directions on the descriptor form:
    a single-descriptor entry raised `dictionary update sequence element #0 has length 7;
    2 is required`, and a *two*-key entry did not raise at all -- `dict()` read the
    descriptor's keys as a key/value pair, so `[{"column": "amount", "label": "金额"}]`
    was stored as `{"column": "label"}`. An object named "column" whose label is "label",
    with nothing having reported a problem.

    `dotted` preserves the two addressing styles the consumers expect: object hints are
    keyed by bare code, attribute hints keep the `table.column` spelling and also gain the
    bare column.
    """
    if isinstance(raw, dict):
        entries = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        entries = [(_hint_key(item), item) for item in raw]
    else:
        return {}

    hints: dict[str, str] = {}
    for key, value in entries:
        name = str(key or "").strip()
        if not name:
            continue
        label = _hint_label(value).strip() or name
        if not dotted:
            name = name.split(".")[-1]
        hints.setdefault(name, label)

    if dotted:
        for name, label in list(hints.items()):
            if "." in name:
                hints.setdefault(name.split(".")[-1], label)
    return hints


def _blueprint_from_payload(payload: dict[str, Any], source: str) -> IndustryBlueprint:
    required = ("id", "name", "domain")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"行业蓝图缺少字段: {', '.join(missing)}")
    return IndustryBlueprint(
        id=str(payload["id"]),
        name=str(payload["name"]),
        domain=str(payload["domain"]),
        description=str(payload.get("description") or ""),
        object_hints=coerce_hints(payload.get("objectHints") or payload.get("object_hints")),
        attribute_hints=coerce_hints(payload.get("attributeHints") or payload.get("attribute_hints"), dotted=True),
        rule_templates=tuple(_rule_template(index, item) for index, item in enumerate(payload.get("rules") or [])),
        table_keywords=tuple(payload.get("tableKeywords") or payload.get("table_keywords") or ()),
        capability_tags=tuple(payload.get("capabilityTags") or payload.get("capability_tags") or ()),
        source=source,
    )


# Rule fields, with the spellings a model or a hand-written file may use for each.
_RULE_ALIASES: dict[str, tuple[str, ...]] = {
    "code": ("code",),
    "name": ("name",),
    "rule_type": ("rule_type", "ruleType"),
    "scope_object_code": ("scope_object_code", "scopeObjectCode"),
    "expression": ("expression",),
    "severity": ("severity",),
    "natural_language": ("natural_language", "naturalLanguage"),
}

# Fields a rule must carry to be importable. `scope_object_code` is in the list because
# `ontology._create_blueprint_rules` keeps only rules whose scope names an existing object,
# so a rule without one is discarded when the blueprint is applied -- the blueprint would
# declare more rules than it creates and say nothing about the difference. That is the
# "control the organisation believes is running" failure, and it is worth a refusal here.
_RULE_REQUIRED = ("code", "name", "scope_object_code", "expression", "severity")


def _rule_text(item: dict[str, Any], field: str) -> str:
    """The value of a rule field, or an empty string when it is absent.

    Empty rather than the string `"None"`. `str(item.get(key))` on a missing key stored the
    literal `"None"` as the rule's type and scope, which reads as a value in the database
    and matches nothing at apply time.
    """
    for key in _RULE_ALIASES[field]:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def rule_is_readable(item: Any) -> bool:
    """Whether `_rule_template` can read this element. Shared with the model normalizer,
    so a draft the platform generates is always a draft it can import."""
    if not isinstance(item, dict):
        return False
    return all(_rule_text(item, field) for field in _RULE_REQUIRED)


def _rule_template(index: int, item: Any) -> RuleTemplate:
    """One rule element, with a refusal that names what is wrong.

    The subscription form this replaced (`item["code"]`) raised `KeyError` for an element
    missing a key, and the route turns only `ValueError` into a response -- so a user
    pasting a model-generated draft got a 500 with no indication of which rule was at
    fault. Naming the position and the missing fields is the difference between a report
    and a crash.
    """
    if not isinstance(item, dict):
        raise ValueError(f"行业蓝图的第 {index + 1} 条规则不是对象，无法读取（收到 {type(item).__name__}）")
    missing = [field for field in _RULE_REQUIRED if not _rule_text(item, field)]
    if missing:
        identified = _rule_text(item, "code") or f"第 {index + 1} 条"
        raise ValueError(f"行业蓝图规则 {identified} 缺少字段: {', '.join(missing)}")
    return RuleTemplate(
        code=_rule_text(item, "code"),
        name=_rule_text(item, "name"),
        rule_type=_rule_text(item, "rule_type"),
        scope_object_code=_rule_text(item, "scope_object_code"),
        expression=_rule_text(item, "expression"),
        severity=_rule_text(item, "severity"),
        natural_language=_rule_text(item, "natural_language"),
    )
