from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


AMOUNT_PATTERN = re.compile(r"(?:合同金额|总价|价款|金额)[：:\s]*人民币?[（(]?[大写]?[）)]?\s*([0-9,]+(?:\.[0-9]+)?)\s*元?")
DATE_PATTERN = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?")
CONTRACT_NO_PATTERN = re.compile(r"(?:合同编号|编号)[：:\s]*([A-Z]{1,8}-\d{4}-\d{2,8})", re.IGNORECASE)
PARTY_A_PATTERN = re.compile(r"(?:甲方|采购方|委托方)[：:\s]*([^\n\r]+)")
PARTY_B_PATTERN = re.compile(r"(?:乙方|供应方|服务方|受托方)[：:\s]*([^\n\r]+)")

# Chinese rule pattern for free-form paragraph extraction
RULE_IF_PATTERN = re.compile(
    r"(?:当|若|如果|如)\s*(?P<condition>[^，,。]+?)\s*(?:时|，|,)\s*(?:则|需|应|必须|不得|禁止|可以)?\s*(?P<action>[^。]+)",
)
RULE_MUST_PATTERN = re.compile(
    r"(?P<subject>[^，,。]{1,20})(?:需|应|必须|不得|禁止|可以)\s*(?P<action>[^。]+)"
)
RULE_SEVERITY_KEYWORDS = {
    "blocking": ["必须", "不得", "禁止", "严禁"],
    "warning": ["应", "应当", "不应", "不宜", "需", "需要", "建议", "推荐"],
    "info": ["可以", "可", "宜", "允许"],
}
DEFAULT_SCOPE_GUESS = re.compile(r"(合同|订单|客户|设备|工单|项目|人员|风险|支付|发票|产品)")


def _convert_doc_to_docx(content: bytes) -> tuple[bytes, str]:
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp_in:
        tmp_in.write(content)
        doc_path = Path(tmp_in.name)

    docx_path = doc_path.with_suffix(".docx")
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", str(doc_path.parent), str(doc_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not docx_path.exists():
            raise RuntimeError(f"LibreOffice 转换失败: {result.stderr.strip()}")
        return docx_path.read_bytes(), docx_path.name
    except FileNotFoundError:
        raise ValueError(
            "未检测到 LibreOffice，无法自动转换 .doc 文件。"
            "请手动将 .doc 另存为 .docx 格式，或安装 LibreOffice 后重试。"
        )
    except subprocess.TimeoutExpired:
        raise ValueError("LibreOffice 转换超时（30秒），请手动将 .doc 转换为 .docx 格式后重试。")
    finally:
        doc_path.unlink(missing_ok=True)
        docx_path.unlink(missing_ok=True)


def _ensure_docx(file_name: str, content: bytes) -> tuple[bytes, str]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".docx":
        return content, file_name
    if suffix == ".doc":
        return _convert_doc_to_docx(content)
    raise ValueError(f"不支持的文件格式: {suffix}。当前支持 .docx 和 .doc。")


def parse_contract_docx_bytes(file_name: str, content: bytes) -> dict[str, Any]:
    content, safe_name = _ensure_docx(file_name, content)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return parse_contract_docx(tmp_path, file_name=safe_name, content=content)
    finally:
        tmp_path.unlink(missing_ok=True)


def parse_contract_docx(path: Path | str, file_name: str | None = None, content: bytes | None = None) -> dict[str, Any]:
    try:
        from docx import Document
    except Exception as error:  # pragma: no cover - depends on optional runtime package
        raise ValueError("缺少 python-docx 依赖，无法解析 Word 文档。请安装 requirements.txt。") from error

    doc = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    tables = _extract_tables(doc)
    text = "\n".join(paragraphs)
    table_text = "\n".join(" | ".join(cell for cell in row if cell) for table in tables for row in table["rows"])
    full_text = "\n".join(part for part in [text, table_text] if part.strip())
    clauses = _extract_clauses(paragraphs)
    entities = _extract_entities(full_text, paragraphs)
    payment_terms = _extract_payment_terms(full_text, paragraphs, tables)
    risks = _detect_risks(entities, payment_terms, clauses, full_text)
    file_bytes = content if content is not None else Path(path).read_bytes()

    return {
        "file": {
            "name": file_name or Path(path).name,
            "size": len(file_bytes),
            "md5": hashlib.md5(file_bytes).hexdigest(),
        },
        "text": full_text,
        "textLength": len(full_text),
        "paragraphs": paragraphs,
        "tables": tables,
        "entities": entities,
        "clauses": clauses,
        "paymentTerms": payment_terms,
        "risks": risks,
        "ontologyHints": _ontology_hints(entities, clauses, payment_terms, risks),
    }


def parse_rule_docx_bytes(file_name: str, content: bytes) -> dict[str, Any]:
    content, safe_name = _ensure_docx(file_name, content)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return parse_rule_docx(tmp_path, file_name=safe_name, content=content)
    finally:
        tmp_path.unlink(missing_ok=True)


def parse_rule_docx(path: Path | str, file_name: str | None = None, content: bytes | None = None) -> dict[str, Any]:
    try:
        from docx import Document
    except Exception as error:  # pragma: no cover
        raise ValueError("缺少 python-docx 依赖，无法解析 Word 规则文档。请安装 requirements.txt。") from error

    doc = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    tables = _extract_tables(doc)
    table_rules = _extract_rules_from_tables(tables)
    paragraph_rules = _extract_rules_from_paragraphs(paragraphs)
    free_text_rules = _extract_rules_from_free_text(paragraphs)
    rules = _deduplicate_rules([*table_rules, *paragraph_rules, *free_text_rules])
    if not rules:
        raise ValueError("未从 Word 文档中识别到规则。建议使用表头：规则编码、规则名称、适用对象、规则类型、规则表达式、严重程度、自然语言说明。")
    file_bytes = content if content is not None else Path(path).read_bytes()
    return {
        "file": {
            "name": file_name or Path(path).name,
            "size": len(file_bytes),
            "md5": hashlib.md5(file_bytes).hexdigest(),
        },
        "rules": rules,
        "warnings": _rule_warnings(rules),
        "text": "\n".join(paragraphs),
    }


def _extract_tables(doc: Any) -> list[dict[str, Any]]:
    output = []
    for index, table in enumerate(doc.tables, start=1):
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        output.append({"index": index, "rows": rows})
    return output


def _extract_rules_from_tables(tables: list[dict[str, Any]]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    for table in tables:
        if not table["rows"]:
            continue
        headers = [_normalize_header(value) for value in table["rows"][0]]
        if "code" not in headers or "expression" not in headers:
            continue
        for row in table["rows"][1:]:
            values = {headers[index]: row[index].strip() for index in range(min(len(headers), len(row))) if headers[index]}
            rule = _normalize_rule(values)
            if rule:
                rules.append(rule)
    return rules


def _extract_rules_from_paragraphs(paragraphs: list[str]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for paragraph in paragraphs:
        key, value = _split_rule_field(paragraph)
        if key == "code" and current.get("code"):
            rule = _normalize_rule(current)
            if rule:
                rules.append(rule)
            current = {}
        if key:
            current[key] = value
    rule = _normalize_rule(current)
    if rule:
        rules.append(rule)
    return rules


def _extract_rules_from_free_text(paragraphs: list[str]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    for paragraph in paragraphs:
        for match in RULE_IF_PATTERN.finditer(paragraph):
            condition = match.group("condition").strip()
            action = match.group("action").strip()
            if not condition or not action:
                continue
            severity = _infer_severity(paragraph)
            scope = _infer_scope(paragraph, condition, action)
            code = _slug_code(f"rule_{len(rules) + 1}")
            if code in seen_codes:
                code = _slug_code(f"rule_{len(rules) + 1}_{hash(condition) % 1000}")
            seen_codes.add(code)
            rules.append({
                "code": code,
                "name": f"规则_{len(rules) + 1}",
                "ruleType": "validation",
                "scopeObjectCode": scope,
                "expression": _condition_to_expression(condition),
                "severity": severity,
                "naturalLanguage": f"如果{condition}，则{action}",
                "status": "draft",
            })

        for match in RULE_MUST_PATTERN.finditer(paragraph):
            subject = match.group("subject").strip()
            action = match.group("action").strip()
            if not subject or not action:
                continue
            severity = _infer_severity(paragraph)
            scope = _infer_scope(paragraph, subject, action)
            code = _slug_code(f"must_{len(rules) + 1}")
            if code in seen_codes:
                code = _slug_code(f"must_{len(rules) + 1}_{hash(subject) % 1000}")
            seen_codes.add(code)
            rules.append({
                "code": code,
                "name": f"必须规则_{len(rules) + 1}",
                "ruleType": "validation",
                "scopeObjectCode": scope,
                "expression": _condition_to_expression(f"{subject}未{action}"),
                "severity": severity,
                "naturalLanguage": f"{subject}需{action}",
                "status": "draft",
            })

    return rules


def _infer_severity(text: str) -> str:
    text_lower = text.lower()
    for severity, keywords in RULE_SEVERITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return severity
    return "warning"


def _infer_scope(text: str, *hints: str) -> str:
    for hint in hints:
        match = DEFAULT_SCOPE_GUESS.search(hint)
        if match:
            mapping = {
                "合同": "contract", "订单": "order", "客户": "customer",
                "设备": "equipment", "工单": "work_order", "项目": "project",
                "人员": "personnel", "风险": "risk", "支付": "payment",
                "发票": "invoice", "产品": "product",
            }
            return mapping.get(match.group(1), "contract")
    return "contract"


def _condition_to_expression(condition: str) -> str:
    replacements = [
        ("大于", " > "), ("小于", " < "), ("等于", " == "),
        ("不为空", " != null"), ("为空", " == null"),
        ("不包含", " not in "), ("包含", " in "),
        ("超过", " > "), ("未超过", " <= "),
        ("达到", " >= "), ("未达到", " < "),
        ("属于", " in "), ("不属于", " not in "),
        ("是", " == "), ("不是", " != "),
        ("且", " and "), ("或", " or "), ("并", " and "),
    ]
    expr = condition
    for zh, op in replacements:
        expr = expr.replace(zh, op)
    return expr.strip() or condition


def _split_rule_field(text: str) -> tuple[str, str]:
    match = re.match(r"^([^:：]{2,20})[:：]\s*(.+)$", text)
    if not match:
        return "", ""
    return _normalize_header(match.group(1)), match.group(2).strip()


def _normalize_header(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip().lower())
    aliases = {
        "规则编码": "code",
        "编码": "code",
        "code": "code",
        "规则名称": "name",
        "名称": "name",
        "name": "name",
        "规则类型": "rule_type",
        "类型": "rule_type",
        "ruletype": "rule_type",
        "rule_type": "rule_type",
        "适用对象": "scope_object_code",
        "业务对象": "scope_object_code",
        "对象": "scope_object_code",
        "scope": "scope_object_code",
        "scopeobjectcode": "scope_object_code",
        "规则表达式": "expression",
        "表达式": "expression",
        "expression": "expression",
        "严重程度": "severity",
        "级别": "severity",
        "severity": "severity",
        "自然语言说明": "natural_language",
        "业务说明": "natural_language",
        "说明": "natural_language",
        "naturallanguage": "natural_language",
        "状态": "status",
        "status": "status",
    }
    return aliases.get(normalized, "")


def _normalize_rule(values: dict[str, str]) -> dict[str, str] | None:
    code = _slug_code(values.get("code", ""))
    expression = values.get("expression", "").strip()
    scope = _slug_code(values.get("scope_object_code", "contract")) or "contract"
    if not code or not expression:
        return None
    return {
        "code": code,
        "name": values.get("name", "").strip() or code.replace("_", " ").title(),
        "ruleType": _normalize_rule_type(values.get("rule_type", "")),
        "scopeObjectCode": scope,
        "expression": expression,
        "severity": _normalize_severity(values.get("severity", "")),
        "naturalLanguage": values.get("natural_language", "").strip() or f"{code}：{expression}",
        "status": _normalize_status(values.get("status", "")),
    }


def _normalize_rule_type(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "校验": "validation",
        "验证": "validation",
        "validation": "validation",
        "派生": "derivation",
        "推导": "derivation",
        "derivation": "derivation",
        "状态流转": "transition",
        "流转": "transition",
        "transition": "transition",
        "风险": "risk",
        "risk": "risk",
        "建议": "recommendation",
        "recommendation": "recommendation",
        "权限": "permission",
        "permission": "permission",
    }
    return mapping.get(normalized, "validation")


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "阻断": "blocking",
        "严重": "blocking",
        "blocking": "blocking",
        "警告": "warning",
        "warning": "warning",
        "提示": "info",
        "信息": "info",
        "info": "info",
    }
    return mapping.get(normalized, "warning")


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "已发布": "published",
        "发布": "published",
        "published": "published",
        "草稿": "draft",
        "draft": "draft",
        "停用": "disabled",
        "disabled": "disabled",
    }
    return mapping.get(normalized, "published")


def _slug_code(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", text):
        return text
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return slug


def _deduplicate_rules(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for rule in rules:
        output[rule["code"]] = rule
    return list(output.values())


def _rule_warnings(rules: list[dict[str, str]]) -> list[str]:
    warnings = []
    for rule in rules:
        if rule["status"] != "published":
            warnings.append(f"{rule['code']} 的状态不是 published，导入后可能不会参与已发布规则研判。")
        if "." in rule["scopeObjectCode"]:
            warnings.append(f"{rule['code']} 的适用对象看起来像属性路径，请确认应为业务对象编码。")
    return warnings


def _extract_entities(text: str, paragraphs: list[str]) -> dict[str, Any]:
    dates = _extract_dates(text)
    title = _infer_title(paragraphs)
    amount = _extract_amount(text)
    return {
        "contractNo": _first_match(CONTRACT_NO_PATTERN, text),
        "title": title,
        "partyA": _extract_party_from_paragraphs(paragraphs, "甲方") or _clean_party(_first_match(PARTY_A_PATTERN, text)),
        "partyB": _extract_party_from_paragraphs(paragraphs, "乙方") or _clean_party(_first_match(PARTY_B_PATTERN, text)),
        "amount": amount,
        "currency": "CNY" if amount is not None or "人民币" in text else "",
        "dates": dates,
        "signDate": dates[0] if dates else "",
        "startDate": dates[1] if len(dates) > 1 else "",
        "endDate": dates[-1] if len(dates) > 1 else "",
    }


def _extract_clauses(paragraphs: list[str]) -> list[dict[str, str]]:
    clauses: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    heading_pattern = re.compile(r"^(第[一二三四五六七八九十百]+条|[一二三四五六七八九十]+、|\d+[.、])\s*(.+)")
    for paragraph in paragraphs:
        match = heading_pattern.match(paragraph)
        if match:
            if current:
                clauses.append(current)
            current = {"title": paragraph[:80], "content": ""}
        elif current:
            current["content"] = (current["content"] + "\n" + paragraph).strip()
    if current:
        clauses.append(current)
    if clauses:
        return clauses
    return [{"title": paragraph[:80], "content": paragraph} for paragraph in paragraphs[:12]]


def _extract_payment_terms(text: str, paragraphs: list[str], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        if any(keyword in paragraph for keyword in ("付款", "支付", "款项", "首付款", "尾款")):
            terms.append({"source": "paragraph", "text": paragraph, "amount": _extract_amount(paragraph), "date": _extract_dates(paragraph)[:1]})
    for table in tables:
        header = table["rows"][0] if table["rows"] else []
        joined_header = "".join(header)
        if any(keyword in joined_header for keyword in ("付款", "金额", "日期", "节点")):
            for row in table["rows"][1:]:
                joined = " ".join(row)
                terms.append({"source": f"table:{table['index']}", "text": joined, "amount": _extract_amount(joined), "date": _extract_dates(joined)[:1]})
    return terms[:20]


def _detect_risks(entities: dict[str, Any], payment_terms: list[dict[str, Any]], clauses: list[dict[str, str]], text: str) -> list[dict[str, str]]:
    risks = []
    if not entities.get("contractNo"):
        risks.append(_risk("missing_contract_no", "warning", "未识别到合同编号，建议补充结构化编号。"))
    if not entities.get("partyA") or not entities.get("partyB"):
        risks.append(_risk("missing_parties", "warning", "未完整识别甲乙方，建议人工核对合同主体。"))
    if entities.get("amount") is None:
        risks.append(_risk("missing_amount", "warning", "未识别到合同金额，无法与付款计划做一致性校验。"))
    if not entities.get("signDate"):
        risks.append(_risk("missing_sign_date", "warning", "未识别到签订日期，已生效合同可能无法通过规则校验。"))
    if entities.get("amount") is not None and entities["amount"] <= 0:
        risks.append(_risk("invalid_amount", "blocking", "合同金额小于或等于 0，存在阻断性风险。"))
    if payment_terms and entities.get("amount") is not None:
        total = sum(float(term["amount"] or 0) for term in payment_terms)
        if total and abs(total - float(entities["amount"])) > 0.01:
            risks.append(_risk("payment_amount_mismatch", "warning", f"付款条款合计 {total:.2f} 与合同金额 {entities['amount']:.2f} 不一致。"))
    if "黑名单" in text:
        risks.append(_risk("blacklist_customer", "warning", "文档提及黑名单客户，应进入风险复核。"))
    if not any("违约" in item["title"] or "违约" in item["content"] for item in clauses):
        risks.append(_risk("missing_breach_clause", "info", "未明显识别违约责任条款，建议补充或人工确认。"))
    return risks


def _ontology_hints(entities: dict[str, Any], clauses: list[dict[str, str]], payment_terms: list[dict[str, Any]], risks: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "objects": ["contract", "customer", "payment_plan"],
        "attributes": {
            "contract.contract_no": entities.get("contractNo"),
            "contract.title": entities.get("title"),
            "contract.amount": entities.get("amount"),
            "contract.sign_date": entities.get("signDate"),
            "contract.start_date": entities.get("startDate"),
            "contract.end_date": entities.get("endDate"),
            "customer.name": entities.get("partyA"),
            "contract.counterparty": entities.get("partyB"),
        },
        "relations": [
            {"source": "contract", "target": "customer", "type": "belongs_to"},
            {"source": "contract", "target": "payment_plan", "type": "has_many"} if payment_terms else None,
        ],
        "rulesToEvaluate": [
            "contract_amount_positive",
            "effective_contract_signed",
            "payment_plan_amount_match",
            "blacklist_customer_warning",
        ],
        "riskCodes": [risk["code"] for risk in risks],
        "clauseCount": len(clauses),
    }


def _extract_amount(text: str) -> float | None:
    match = AMOUNT_PATTERN.search(text)
    if not match:
        money = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*元", text)
        match = money
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _extract_dates(text: str) -> list[str]:
    dates = []
    for year, month, day in DATE_PATTERN.findall(text):
        dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return list(dict.fromkeys(dates))


def _infer_title(paragraphs: list[str]) -> str:
    for paragraph in paragraphs[:5]:
        if "合同" in paragraph or "协议" in paragraph:
            return paragraph[:120]
    return paragraphs[0][:120] if paragraphs else ""


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _clean_party(value: str) -> str:
    return value.split("，")[0].split(",")[0].strip()


def _extract_party_from_paragraphs(paragraphs: list[str], label: str) -> str:
    for index, paragraph in enumerate(paragraphs):
        if paragraph.startswith(label):
            inline = re.sub(rf"^{label}[（(][^）)]*[）)]\s*[:：]?", "", paragraph).strip()
            if inline and inline != paragraph:
                return _clean_party(inline)
            if index + 1 < len(paragraphs):
                return _clean_party(paragraphs[index + 1])
    return ""


def _risk(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}
