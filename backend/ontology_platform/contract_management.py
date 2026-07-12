from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contract_documents import parse_contract_docx_bytes
from .database import connect, last_insert_id


def create_contract(database: Path | str, file_name: str, content: bytes, actor: str = "system") -> dict[str, Any]:
    """Create a contract whose authoritative representation is a DOCX document."""
    if Path(file_name).suffix.lower() != ".docx":
        raise ValueError("合同主文档必须是 .docx Word 格式")
    parsed = parse_contract_docx_bytes(file_name, content)
    entities = parsed["entities"]
    contract_no = entities.get("contractNo")
    if not contract_no:
        raise ValueError("Word 合同中未识别到合同编号")
    sha256 = hashlib.sha256(content).hexdigest()

    with connect(database) as conn:
        _ensure_schema(conn)
        existing = conn.execute("select id from managed_contract where contract_no = ?", (contract_no,)).fetchone()
        if existing:
            raise ValueError(f"合同编号已存在: {contract_no}")
        conn.execute(
            """insert into managed_contract
            (contract_no, title, party_a, party_b, amount, currency, status, current_version, semantic_snapshot)
            values (?, ?, ?, ?, ?, ?, 'draft', 1, ?)""",
            (
                contract_no, entities.get("title") or file_name, entities.get("partyA") or "",
                entities.get("partyB") or "", entities.get("amount"), entities.get("currency") or "CNY",
                json.dumps(parsed, ensure_ascii=False),
            ),
        )
        contract_id = last_insert_id(conn)
        conn.execute(
            """insert into contract_document_version
            (contract_id, version_no, file_name, mime_type, byte_size, sha256, content, extracted_text, semantic_snapshot, created_by)
            values (?, 1, ?, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', ?, ?, ?, ?, ?, ?)""",
            (contract_id, file_name, len(content), sha256, content, parsed["text"], json.dumps(parsed, ensure_ascii=False), actor),
        )
        conn.commit()
    return get_contract(database, contract_id)


def list_contracts(database: Path | str) -> list[dict[str, Any]]:
    with connect(database) as conn:
        _ensure_schema(conn)
        rows = conn.execute("select * from managed_contract order by id desc").fetchall()
        return [_contract_dict(row) for row in rows]


def add_contract_version(database: Path | str, contract_id: int, file_name: str, content: bytes, actor: str = "system") -> dict[str, Any]:
    if Path(file_name).suffix.lower() != ".docx":
        raise ValueError("合同主文档必须是 .docx Word 格式")
    parsed = parse_contract_docx_bytes(file_name, content)
    entities = parsed["entities"]
    with connect(database) as conn:
        _ensure_schema(conn)
        row = conn.execute("select contract_no, current_version from managed_contract where id = ?", (contract_id,)).fetchone()
        if not row:
            raise ValueError("合同不存在")
        current = dict(row)
        if entities.get("contractNo") != current["contract_no"]:
            raise ValueError("新版 Word 的合同编号必须与原合同一致")
        version = int(current["current_version"]) + 1
        sha256 = hashlib.sha256(content).hexdigest()
        conn.execute(
            """insert into contract_document_version
            (contract_id, version_no, file_name, mime_type, byte_size, sha256, content, extracted_text, semantic_snapshot, created_by)
            values (?, ?, ?, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', ?, ?, ?, ?, ?, ?)""",
            (contract_id, version, file_name, len(content), sha256, content, parsed["text"], json.dumps(parsed, ensure_ascii=False), actor),
        )
        conn.execute(
            """update managed_contract set title = ?, party_a = ?, party_b = ?, amount = ?, currency = ?,
            current_version = ?, semantic_snapshot = ?, updated_at = current_timestamp where id = ?""",
            (entities.get("title") or file_name, entities.get("partyA") or "", entities.get("partyB") or "", entities.get("amount"), entities.get("currency") or "CNY", version, json.dumps(parsed, ensure_ascii=False), contract_id),
        )
        conn.commit()
    return get_contract(database, contract_id)


def get_contract(database: Path | str, contract_id: int) -> dict[str, Any]:
    with connect(database) as conn:
        _ensure_schema(conn)
        row = conn.execute("select * from managed_contract where id = ?", (contract_id,)).fetchone()
        if not row:
            raise ValueError("合同不存在")
        result = _contract_dict(row)
        document = conn.execute(
            "select version_no, file_name, byte_size, sha256, created_at, created_by from contract_document_version where contract_id = ? and version_no = ?",
            (contract_id, result["currentVersion"]),
        ).fetchone()
        result["document"] = _document_dict(document)
        return result


def get_contract_document(database: Path | str, contract_id: int, version: int | None = None) -> dict[str, Any]:
    with connect(database) as conn:
        _ensure_schema(conn)
        if version is None:
            contract = conn.execute("select current_version from managed_contract where id = ?", (contract_id,)).fetchone()
            if not contract:
                raise ValueError("合同不存在")
            version = int(dict(contract)["current_version"])
        row = conn.execute(
            "select file_name, mime_type, content, sha256 from contract_document_version where contract_id = ? and version_no = ?",
            (contract_id, version),
        ).fetchone()
        if not row:
            raise ValueError("Word 文档版本不存在")
        data = dict(row)
        return {"fileName": data["file_name"], "mimeType": data["mime_type"], "content": bytes(data["content"]), "sha256": data["sha256"]}


def compare_contract_engines(database: Path | str, contract_id: int, question: str) -> dict[str, Any]:
    with connect(database) as conn:
        _ensure_schema(conn)
        row = conn.execute("select * from managed_contract where id = ?", (contract_id,)).fetchone()
        doc = conn.execute(
            "select extracted_text, semantic_snapshot, sha256 from contract_document_version where contract_id = ? order by version_no desc limit 1",
            (contract_id,),
        ).fetchone()
        if not row or not doc:
            raise ValueError("合同不存在")
        contract, document = dict(row), dict(doc)
    passages = [part.strip() for part in document["extracted_text"].splitlines() if part.strip()]
    terms = {term for term in re.findall(r"[\w\u4e00-\u9fff]+", question.lower()) if len(term) > 1}
    ranked = sorted(passages, key=lambda item: sum(term in item.lower() for term in terms), reverse=True)[:3]
    snapshot = json.loads(document["semantic_snapshot"])
    facts = snapshot["entities"]
    return {
        "question": question,
        "contractId": contract_id,
        "rag": {
            "method": "lexical_retrieval",
            "answer": "\n".join(ranked) if ranked else "未检索到相关片段。",
            "citations": [{"documentVersion": contract["current_version"], "passage": item} for item in ranked],
            "limitations": ["答案基于文本相似度，不执行跨对象规则。", "召回片段不等于确定性业务事实。"],
        },
        "ontology": {
            "method": "semantic_reasoning",
            "answer": f"合同 {facts.get('contractNo')} 由 {facts.get('partyA')} 与 {facts.get('partyB')} 签订，金额 {facts.get('amount')} {facts.get('currency')} 。",
            "facts": facts,
            "relations": ["甲方-签订-合同", "乙方-承接-合同", "合同-约定-付款条款"],
            "evidence": {"documentSha256": document["sha256"], "documentVersion": contract["current_version"], "riskCount": len(snapshot["risks"])},
        },
        "differences": [
            {"dimension": "answer_basis", "rag": "非结构化文本召回", "ontology": "已映射的业务对象、属性与关系"},
            {"dimension": "determinism", "rag": "结果受切片和措辞影响", "ontology": "可依版本化事实和规则复现"},
            {"dimension": "actionability", "rag": "用于检索与摘要", "ontology": "可用于校验、影响分析和操作预检"},
        ],
    }


def _ensure_schema(conn: Any) -> None:
    dialect = getattr(getattr(conn, "_adapter", None), "db_type", "sqlite")
    if dialect == "mysql":
        id_column, text_type, blob_type, timestamp = "integer primary key auto_increment", "longtext", "longblob", "datetime not null default current_timestamp"
    elif dialect in {"postgresql", "postgres"}:
        id_column, text_type, blob_type, timestamp = "serial primary key", "text", "bytea", "timestamp not null default current_timestamp"
    else:
        id_column, text_type, blob_type, timestamp = "integer primary key autoincrement", "text", "blob", "text not null default current_timestamp"
    conn.execute(f"""create table if not exists managed_contract (
        id {id_column}, contract_no varchar(255) not null unique, title varchar(500) not null,
        party_a varchar(500) not null default '', party_b varchar(500) not null default '', amount double,
        currency varchar(20) not null default 'CNY', status varchar(50) not null default 'draft',
        current_version integer not null default 1, semantic_snapshot {text_type} not null, created_at {timestamp}, updated_at {timestamp})""")
    conn.execute(f"""create table if not exists contract_document_version (
        id {id_column}, contract_id integer not null references managed_contract(id), version_no integer not null,
        file_name varchar(500) not null, mime_type varchar(255) not null, byte_size integer not null,
        sha256 varchar(64) not null, content {blob_type} not null, extracted_text {text_type} not null,
        semantic_snapshot {text_type} not null, created_by varchar(255) not null default 'system',
        created_at {timestamp}, unique(contract_id, version_no))""")
    conn.commit()


def _contract_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    return {"id": item["id"], "contractNo": item["contract_no"], "title": item["title"], "partyA": item["party_a"], "partyB": item["party_b"], "amount": item["amount"], "currency": item["currency"], "status": item["status"], "currentVersion": item["current_version"], "createdAt": str(item["created_at"])}


def _document_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    return {"version": item["version_no"], "fileName": item["file_name"], "byteSize": item["byte_size"], "sha256": item["sha256"], "createdAt": str(item["created_at"]), "createdBy": item["created_by"]}
