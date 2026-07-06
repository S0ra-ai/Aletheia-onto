from __future__ import annotations

from pathlib import Path
from typing import Any

from .coverage import build_semantic_coverage
from .database import connect
from .metadata import analyze_schema_drift, assess_data_source_readiness


def assess_ontology_release_readiness(platform_db: Path | str, ontology_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        ontology = conn.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")
        objects = conn.execute(
            """
            select bo.id, bo.code, bo.name, st.id as source_table_id, st.table_name,
                   st.primary_key, st.data_source_id
            from business_object bo
            left join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ?
            order by bo.code
            """,
            (ontology_id,),
        ).fetchall()
        mapping_counts = {
            row["status"]: row["total"]
            for row in conn.execute(
                "select status, count(*) as total from semantic_mapping where ontology_id = ? group by status",
                (ontology_id,),
            ).fetchall()
        }
        rule_count = conn.execute(
            "select count(*) as total from business_rule where ontology_id = ? and status = 'published'",
            (ontology_id,),
        ).fetchone()["total"]
        object_rule_rows = conn.execute(
            """
            select bo.code, count(br.id) as total
            from business_object bo
            left join business_rule br
              on br.ontology_id = bo.ontology_id
             and br.scope_object_code = bo.code
             and br.status = 'published'
            where bo.ontology_id = ?
            group by bo.code
            """,
            (ontology_id,),
        ).fetchall()

    data_source_ids = sorted({row["data_source_id"] for row in objects if row["data_source_id"] is not None})
    data_source_reports = [_data_source_report(platform_db, data_source_id) for data_source_id in data_source_ids]
    gates = [
        _gate(
            "ontology_status",
            "本体状态",
            ontology["status"] in {"draft", "reviewing", "published"},
            "blocker",
            f"当前状态 {ontology['status']}。",
            "仅 draft、reviewing 或已发布版本可进入发布评估。",
        ),
        _gate(
            "business_objects",
            "业务对象",
            len(objects) > 0,
            "blocker",
            f"识别到 {len(objects)} 个业务对象。",
            "先基于数据源扫描结果生成本体草案。",
        ),
        _gate(
            "source_bindings",
            "来源绑定",
            bool(objects) and all(row["source_table_id"] is not None for row in objects),
            "blocker",
            f"{sum(1 for row in objects if row['source_table_id'] is not None)}/{len(objects)} 个对象绑定来源表。",
            "为每个业务对象绑定传统系统来源表。",
        ),
        _gate(
            "primary_keys",
            "实例标识",
            bool(objects) and all(row["primary_key"] for row in objects),
            "blocker",
            f"{sum(1 for row in objects if row['primary_key'])}/{len(objects)} 个对象具备主键。",
            "为缺少主键的来源表配置稳定实例标识。",
        ),
        _gate(
            "pending_mappings",
            "映射审核",
            mapping_counts.get("pending", 0) == 0,
            "blocker",
            f"待审核映射 {mapping_counts.get('pending', 0)} 条。",
            "发布前必须完成全部语义映射审核。",
        ),
        _gate(
            "confirmed_mappings",
            "确认映射",
            mapping_counts.get("confirmed", 0) > 0,
            "blocker",
            f"已确认映射 {mapping_counts.get('confirmed', 0)} 条。",
            "至少确认关键对象和关键字段映射。",
        ),
        _gate(
            "published_rules",
            "业务规则",
            rule_count > 0,
            "blocker",
            f"已发布规则 {rule_count} 条。",
            "至少为核心业务对象配置一组发布态规则。",
        ),
        _gate(
            "object_rule_coverage",
            "对象规则覆盖",
            bool(object_rule_rows) and all(row["total"] > 0 for row in object_rule_rows),
            "warning",
            f"{sum(1 for row in object_rule_rows if row['total'] > 0)}/{len(object_rule_rows)} 个对象具备规则。",
            "为缺少规则的业务对象补充校验、风险或权限规则。",
        ),
    ]
    for report in data_source_reports:
        readiness = report["readiness"]
        coverage = report["coverage"]
        drift = report["schemaDrift"]
        gates.extend(
            [
                _gate(
                    f"data_source_{report['dataSourceId']}_readiness",
                    f"数据源 {report['dataSourceId']} 接入准备度",
                    readiness["status"] != "blocked",
                    "blocker",
                    f"准备度 {readiness['score']} 分，状态 {readiness['status']}。",
                    "完成元数据扫描、实例定位、映射治理等阻断项。",
                ),
                _gate(
                    f"data_source_{report['dataSourceId']}_coverage",
                    f"数据源 {report['dataSourceId']} 语义覆盖",
                    coverage["status"] != "blocked" and coverage["status"] != "not_modeled",
                    "warning",
                    f"覆盖度 {coverage['score']} 分，状态 {coverage['status']}。",
                    "补齐对象映射、业务规则和语义 API。",
                ),
                _gate(
                    f"data_source_{report['dataSourceId']}_schema_drift",
                    f"数据源 {report['dataSourceId']} 结构漂移",
                    drift["status"] == "no_drift",
                    "blocker",
                    f"结构漂移状态 {drift['status']}。",
                    "发布前先处理结构漂移并重新确认受影响语义资产。",
                ),
            ]
        )

    blocker_failures = [gate for gate in gates if gate["severity"] == "blocker" and not gate["passed"]]
    warning_failures = [gate for gate in gates if gate["severity"] == "warning" and not gate["passed"]]
    status = "blocked" if blocker_failures else "review" if warning_failures else "ready"
    return {
        "ontologyId": ontology["id"],
        "name": ontology["name"],
        "version": ontology["version"],
        "status": status,
        "summary": {
            "objects": len(objects),
            "dataSources": len(data_source_ids),
            "confirmedMappings": mapping_counts.get("confirmed", 0),
            "pendingMappings": mapping_counts.get("pending", 0),
            "rejectedMappings": mapping_counts.get("rejected", 0),
            "publishedRules": rule_count,
            "passedGates": sum(1 for gate in gates if gate["passed"]),
            "totalGates": len(gates),
            "blockers": len(blocker_failures),
            "warnings": len(warning_failures),
        },
        "gates": gates,
        "dataSources": data_source_reports,
        "nextActions": _next_actions(blocker_failures, warning_failures),
    }


def _data_source_report(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    try:
        drift = analyze_schema_drift(platform_db, data_source_id)
    except ValueError as error:
        drift = {"status": "error", "error": str(error)}
    return {
        "dataSourceId": data_source_id,
        "readiness": assess_data_source_readiness(platform_db, data_source_id),
        "coverage": build_semantic_coverage(platform_db, data_source_id),
        "schemaDrift": drift,
    }


def _gate(code: str, name: str, passed: bool, severity: str, evidence: str, remediation: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "passed": passed,
        "severity": severity,
        "evidence": evidence,
        "remediation": remediation,
    }


def _next_actions(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    if blockers:
        return [gate["remediation"] for gate in blockers]
    if warnings:
        return [gate["remediation"] for gate in warnings]
    return ["发布门禁全部通过，可按治理流程发布本体版本。"]
