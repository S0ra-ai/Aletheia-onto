"""Code generation from a published ontology: types and a client that cannot drift.

ROADMAP stage F's last item. The frontend maintains 1143 hand-written lines mirroring the
backend, and `docs/architecture-debt.md` records why that is debt: not the duplication, but
that **the two copies can disagree with nothing failing**. That is not hypothetical -- the
model configuration endpoint silently discarded four fields the frontend had always sent.

Generating the *platform's* own types from OpenAPI remains blocked, and for a reason worth
stating precisely: every endpoint returns `dict[str, object]`, so no response schema exists
to generate from. Annotating 144 response models would freeze the response shapes into the
API layer, which is a larger commitment than the debt justifies.

What *is* generatable, and more valuable, is the layer nobody could hand-write correctly:
**the types of a user's own business objects.** `contract.amount` is a decimal with a unit,
`contract.customer_id` points at a customer, `signature.status` is one of four declared
states -- all of that is already in the ontology, and none of it is in any TypeScript file
today. A developer building a form over `contract` reads the database schema and guesses.

So this generates from the ontology rather than from the API:

- one interface per business object, with declared types, units and optionality
- relation fields typed as the object they point at, not as `number`
- a typed client for the endpoints whose shape *is* known: assess, explain, events
- a stable header naming the ontology and version the output came from

## Regenerating is the point, so output is overwritten

The opposite decision from `scaffold.py`, and deliberately. A scaffold is a starting point
the user then owns; generated types are a *projection* of the ontology and must be
regenerated whenever it changes. Refusing to overwrite would mean a stale projection is the
default, which defeats the purpose.

The generated file therefore says, in its first line, that it is generated and must not be
edited -- and includes the ontology version, so a reviewer seeing a conflict knows whether
they are looking at a regeneration or at someone's edit.

## Only published ontologies

A draft's objects and attributes change while someone is still reviewing mappings.
Generating from one produces types that describe a model nobody has agreed to, and the
first sign of trouble is a compile error in code that was correct yesterday. Publishing is
the point at which the shape is a commitment (ADR-0002's release gate), so that is the
point at which it can be projected.

Stability: experimental (ADR-0007). Generated files are outputs, never sources.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import PlatformDb
from .database import connect
from .ontology import summarize_ontology

__all__ = [
    "TS_BY_DATA_TYPE",
    "CodegenError",
    "generate_typescript",
    "write_typescript",
]

# Platform data types to TypeScript. `string` is the fallback rather than an error: an
# unmapped type must still produce a field, because a missing field is a field the developer
# does not know exists, while a string-typed one is merely imprecise.
#
# `decimal`/`numeric` map to `number` and not to a decimal library. That loses precision in
# JavaScript, and the honest place to say so is the generated comment on the field -- a
# generator that silently emitted `string` for money would break every arithmetic the
# developer writes.
TS_BY_DATA_TYPE = {
    "string": "string",
    "text": "string",
    "integer": "number",
    "int": "number",
    "number": "number",
    "numeric": "number",
    "decimal": "number",
    "float": "number",
    "double": "number",
    "boolean": "boolean",
    "bool": "boolean",
    "date": "string",
    "datetime": "string",
    "timestamp": "string",
    "json": "unknown",
}

# Types where the JSON representation differs from the name, and a developer will otherwise
# assume wrong. Emitted as a trailing comment on the field.
_TYPE_NOTES = {
    "date": "ISO 日期字符串，如 2026-08-01",
    "datetime": "ISO 时间戳字符串",
    "timestamp": "ISO 时间戳字符串",
    # `number` is what the scanner normalises numeric/decimal columns to, so the note has to
    # hang off that name -- attaching it only to `decimal` would mean it never appeared.
    "number": "JavaScript number 精度有限，金额比较请在服务端做",
    "decimal": "JavaScript number 精度有限，金额比较请在服务端做",
    "numeric": "JavaScript number 精度有限，金额比较请在服务端做",
    "json": "结构由业务系统决定，平台不解释",
}


class CodegenError(ValueError):
    """Raised when an ontology cannot be projected into code."""


def _identifier(code: str) -> str:
    """A code as a TypeScript interface name.

    Non-ASCII is transliterated away rather than encoded, unlike IRIs: an interface name is
    read and typed by a developer, and a percent-encoded one is neither. A code that survives
    to nothing falls back to a stable prefix plus its original, so two different objects
    cannot collapse into one name.
    """
    parts = [part for part in re.split(r"[^0-9a-zA-Z]+", code) if part]
    if not parts:
        raise CodegenError(f"业务对象编码 {code!r} 不含可用于类型名的字符，请改为 ASCII 编码")
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _field_name(code: str) -> str:
    """An attribute code as an object key.

    Quoted when it is not a valid identifier rather than rewritten: renaming would break the
    correspondence with the API's actual key, and a form binding to the renamed field would
    read undefined.
    """
    return code if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", code) else f'"{code}"'


def generate_typescript(platform_db: PlatformDb, ontology_id: int, *, allow_draft: bool = False) -> str:
    """Project one ontology into TypeScript declarations plus a typed client.

    `allow_draft` exists for local iteration and defaults to off. A draft's shape changes
    while mappings are still under review, so generating from one produces types describing a
    model nobody has agreed to -- and the first symptom is a compile error in code that was
    correct yesterday.
    """
    with connect(platform_db) as conn:
        detail = summarize_ontology(conn, ontology_id)

    ontology = detail["ontology"]
    if ontology["status"] != "published" and not allow_draft:
        raise CodegenError(
            f"本体 {ontology_id} 当前为 {ontology['status']}，仅已发布本体可生成代码。"
            "草案的对象与属性会在映射审核期间变动，据此生成的类型描述的是没人同意过的模型。"
            "本地迭代可传 allow_draft=True。"
        )

    objects = detail["objects"]
    if not objects:
        raise CodegenError(f"本体 {ontology_id} 没有业务对象，无可生成内容")

    attributes_by_object: dict[str, list[dict[str, Any]]] = {}
    for item in detail["attributes"]:
        attributes_by_object.setdefault(item["objectCode"], []).append(item)

    relations_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in detail["relations"]:
        relations_by_source.setdefault(item["sourceCode"], []).append(item)

    rules_by_object: dict[str, list[dict[str, Any]]] = {}
    for item in detail["rules"]:
        rules_by_object.setdefault(item["scopeObjectCode"], []).append(item)

    lines = [
        "// 由 Aletheia 从本体生成，请勿手工编辑。",
        f"// 本体: {ontology['name']}  版本: {ontology['version']}  域: {ontology['domain']}",
        "//",
        "// 重新生成: aletheia codegen <ontologyId> --output <path>",
        "// 本体变更后必须重新生成——手工修改会在下一次生成时丢失，",
        "// 而「手工改过的生成文件」与「已过期的生成文件」在评审时无从区分。",
        "",
    ]

    for item in objects:
        code = item["code"]
        interface = _identifier(code)
        lines.append(f"/** {item['name']}" + (f" —— {item['description']}" if item["description"] else "") + " */")
        lines.append(f"export interface {interface} {{")

        for attribute in attributes_by_object.get(code, []):
            lines.extend(_attribute_field(attribute))

        for relation in relations_by_source.get(code, []):
            lines.extend(_relation_field(relation))

        lines.append("}")
        lines.append("")

        codes = [rule["code"] for rule in rules_by_object.get(code, [])]
        if codes:
            union = " | ".join(f'"{value}"' for value in sorted(codes))
            lines.append(f"/** {item['name']}上已发布的规则编码。判定结果按这些编码归因。 */")
            lines.append(f"export type {interface}RuleCode = {union};")
            lines.append("")

    lines.extend(_client_section(ontology, objects))
    return "\n".join(lines).rstrip() + "\n"


def _attribute_field(attribute: dict[str, Any]) -> list[str]:
    data_type = (attribute.get("dataType") or "").strip().lower()
    ts_type = TS_BY_DATA_TYPE.get(data_type, "string")
    optional = "" if attribute.get("required") else "?"

    notes = []
    if attribute.get("name"):
        notes.append(attribute["name"])
    if attribute.get("unit"):
        # Without the unit a number is uninterpretable, and the platform refuses
        # cross-dimension comparison precisely because callers get this wrong.
        notes.append(f"单位: {attribute['unit']}")
    if attribute.get("derivedExpression"):
        # Derived attributes are computed by the platform. Writing one back is meaningless,
        # and a developer who does not know it is derived will try.
        notes.append(f"派生（只读）: {attribute['derivedExpression']}")
    if data_type in _TYPE_NOTES:
        notes.append(_TYPE_NOTES[data_type])

    field = f"  {_field_name(attribute['code'])}{optional}: {ts_type};"
    if notes:
        return [f"  /** {'；'.join(notes)} */", field]
    return [field]


def _relation_field(relation: dict[str, Any]) -> list[str]:
    """A relation as a typed field, shaped by its declared cardinality.

    Typed as the target object rather than as `number`, which is the single most useful thing
    generation adds: a hand-written mirror types every foreign key as a number, so nothing
    stops a developer passing a contract id where a customer is expected.
    """
    target = _identifier(relation["targetCode"])
    cardinality = (relation.get("cardinality") or "").strip()
    plural = cardinality in ("one_to_many", "many_to_many")
    # Always optional. A relation field is injected by the platform at assessment time, so a
    # caller constructing an object for a form never has it -- declaring it required would
    # make every construction site a type error for a field they must not supply.

    notes = [relation["name"]]
    if cardinality:
        notes.append(f"基数: {cardinality}")
    if relation.get("relationKind"):
        notes.append(f"强弱: {relation['relationKind']}")
    notes.append("由平台在研判时按声明注入，不必自行拼接")

    field_type = f"{target}[]" if plural else target
    return [
        f"  /** {'；'.join(notes)} */",
        f"  {_field_name(relation['code'])}?: {field_type};",
    ]


def _client_section(ontology: dict[str, Any], objects: list[dict[str, Any]]) -> list[str]:
    """A typed client for the endpoints whose response shape is actually known.

    Only these three. The rest of the API returns `dict[str, object]`, and generating a client
    that claimed to know their shape would be asserting something the platform does not
    guarantee -- a lie that compiles.
    """
    union = " | ".join(f'"{item["code"]}"' for item in objects)
    return [
        "/** 本体中的业务对象编码。 */",
        f"export type ObjectCode = {union};",
        "",
        "/** 判定结论。三值而非布尔：`review` 是「需要人看」，与「不通过」是不同的业务动作。 */",
        'export type Decision = "approved" | "review" | "blocked";',
        "",
        "export interface RuleResult {",
        "  code: string;",
        "  name: string;",
        "  passed: boolean;",
        '  severity: "blocker" | "warning" | "info";',
        "  /** 该规则为何得出此结论。空字符串表示平台未能给出解释，应按未通过处理。 */",
        "  explanation: string;",
        "}",
        "",
        "export interface Assessment {",
        "  objectCode: ObjectCode;",
        "  instanceId: string;",
        "  decision: Decision;",
        "  /** 逐条规则结论。**判定的依据在这里**，不要只读 decision。 */",
        "  ruleResults: RuleResult[];",
        "  /** 回溯判定的时刻。存在即表示这是对过去某一刻的判断，不是对现在的。 */",
        "  asOf?: string;",
        "}",
        "",
        "/** 平台 HTTP 客户端所需的最小接口。自带 fetch 封装即可传入。 */",
        "export interface Transport {",
        "  request(method: string, path: string, body?: unknown): Promise<unknown>;",
        "}",
        "",
        f"const ONTOLOGY_ID = {ontology['id']};",
        "",
        "/** 只封装响应形状已确定的端点。其余端点返回结构由平台决定，",
        "  * 在此声明类型等于断言平台并未保证的事——那是一个能通过编译的谎。 */",
        "export class OntologyClient {",
        "  constructor(private readonly transport: Transport) {}",
        "",
        "  /** 对一个实例产出判定。`asOf` 用于回溯：合规审计问的通常是过去某一刻。 */",
        "  async assess(objectCode: ObjectCode, instanceId: string, asOf?: string): Promise<Assessment> {",
        "    const query = new URLSearchParams({ ontologyId: String(ONTOLOGY_ID) });",
        '    if (asOf) query.set("asOf", asOf);',
        "    return (await this.transport.request(",
        '      "POST",',
        "      `/v1/semantic/objects/${objectCode}/instances/${encodeURIComponent(instanceId)}/assess?${query}`,",
        "    )) as Assessment;",
        "  }",
        "",
        "  /** 实例的完整语义解释：属性、关系、适用规则与来源。 */",
        "  async explain(objectCode: ObjectCode, instanceId: string): Promise<unknown> {",
        "    const query = new URLSearchParams({ ontologyId: String(ONTOLOGY_ID) });",
        "    return this.transport.request(",
        '      "GET",',
        "      `/v1/semantic/objects/${objectCode}/instances/${encodeURIComponent(instanceId)}/explain?${query}`,",
        "    );",
        "  }",
        "",
        "  /** 实例的统一时间线：业务事件与状态流转。只追加，不可改。 */",
        "  async timeline(objectCode: ObjectCode, instanceId: string): Promise<unknown> {",
        "    return this.transport.request(",
        '      "GET",',
        "      `/v1/ontologies/${ONTOLOGY_ID}/objects/${objectCode}/instances/${encodeURIComponent(instanceId)}/events`,",
        "    );",
        "  }",
        "}",
    ]


def write_typescript(
    platform_db: PlatformDb,
    ontology_id: int,
    output: Path | str,
    *,
    allow_draft: bool = False,
) -> dict[str, Any]:
    """Generate and write, overwriting any existing output.

    Overwriting is correct here and wrong in `scaffold.py`, and the difference is what the
    output *is*: a scaffold is a starting point the user then owns, while generated types are
    a projection of the ontology that must be regenerated whenever it changes. Refusing to
    overwrite would make a stale projection the default.
    """
    content = generate_typescript(platform_db, ontology_id, allow_draft=allow_draft)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existed = destination.exists()
    destination.write_text(content, encoding="utf-8")
    return {
        "ontologyId": ontology_id,
        "output": str(destination.resolve()),
        "bytes": len(content.encode("utf-8")),
        "overwritten": existed,
    }
