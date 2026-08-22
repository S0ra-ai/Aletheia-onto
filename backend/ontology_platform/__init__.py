"""Aletheia：为传统业务系统安装可核验的业务语义内核。

Aletheia reads a legacy system's metadata and builds a business ontology beside it:
objects, attributes, relations, subtypes, events, states and rules. Every verdict it
produces cites the rule, the mapping and the source row it came from.

## Where to start

The package is deliberately shallow at the top: the entry points below are the ones a
consumer needs, and everything else is reached through the module that owns it.

```python
from ontology_platform import assess_instance, generate_ontology_draft

ontology = generate_ontology_draft(platform_db, data_source_id)
verdict = assess_instance(platform_db, ontology["ontology"]["id"], "contract", "1")
```

| Concern | Module |
|---|---|
| 接入与元数据扫描 | `metadata`, `adapters` |
| 数据源扩展 | `sql_dialects`, `generic_sql_adapter`, `file_adapter`, `rest_adapter` |
| 本体生成与导出 | `ontology`, `industry_blueprints` |
| 规则求值（安全边界） | `rule_sandbox` |
| 判定与留痕 | `semantic_kernel`, `decisions` |
| 表达力：解析器／聚合／派生／层级／事件／时态 | `instance_resolver`, `aggregation`, `derived_attributes`, `type_hierarchy`, `events`, `temporal` |
| 写回：HTTP／直写库／存储过程 | `automation`, `db_executors` |
| 治理与发布 | `governance`, `release_readiness` |
| 多租户 | `tenancy` |
| 扩展注册 | `registry` — 见 docs/extending.md |
| 扩展一致性契约 | `conformance` — 第三方自验实现是否符合内核依赖的属性 |
| HTTP 层 | `api` — 需要 `[web]` extra |

## Stability

Names re-exported here are the intended public surface. Anything else may change
between minor versions (ADR-0007): the SPI shapes need a second real use case before
they can be frozen, and freezing them early would bake one use case's accidental
features into the API.

`api` is not imported here. It requires FastAPI, which is an optional extra, so
importing it eagerly would make the kernel unusable without a web server installed.
"""

from __future__ import annotations

__version__ = "0.4.0"

__all__ = [
    "__version__",
    # Onboarding and metadata
    "register_data_source",
    "scan_data_source",
    # Ontology lifecycle
    "generate_ontology_draft",
    "export_ontology_asset",
    "explain_instance",
    "publish_ontology",
    # Assessment
    "assess_instance",
    "validate_rule_expression",
    "upsert_business_rule",
    # Expressiveness
    "declare_subtype",
    "define_aggregate",
    "define_derived_attribute",
    "declare_event_type",
    "record_event",
    "record_attribute_version",
    # Extension points
    "register_adapter",
    "register_rule_function",
    "register_resolver",
    "register_dialect",
    "register_sql_source",
    "register_rest_source",
    "register_database_target",
    "register_unit",
    "register_executor",
    # Conformance: verify an implementation against what the kernel relies on
    "check_data_source_adapter",
    "check_instance_resolver",
    "check_retrieval_backend",
    "check_embedding_model",
    "check_writeback_executor",
]


def __getattr__(name: str) -> object:
    """Resolve the public surface lazily.

    Importing every submodule eagerly would make `import ontology_platform` pull in the
    adapters, the model client and the document layer -- so a consumer who only wants to
    validate a rule expression pays for psycopg and python-docx. Lazy resolution keeps
    the top-level import cheap while the names still appear in `__all__`, so editors and
    `dir()` behave normally.
    """
    sources = {
        "register_data_source": "metadata",
        "scan_data_source": "metadata",
        "generate_ontology_draft": "ontology",
        "export_ontology_asset": "ontology",
        "explain_instance": "ontology",
        "publish_ontology": "governance",
        "upsert_business_rule": "governance",
        "assess_instance": "semantic_kernel",
        "validate_rule_expression": "rule_sandbox",
        "register_rule_function": "rule_sandbox",
        "declare_subtype": "type_hierarchy",
        "define_aggregate": "aggregation",
        "define_derived_attribute": "derived_attributes",
        "declare_event_type": "events",
        "record_event": "events",
        "record_attribute_version": "temporal",
        "register_adapter": "adapters",
        "register_resolver": "instance_resolver",
        "register_dialect": "sql_dialects",
        "register_sql_source": "generic_sql_adapter",
        "register_rest_source": "rest_adapter",
        "register_database_target": "db_executors",
        "register_unit": "derived_attributes",
        "register_executor": "automation",
        "check_data_source_adapter": "conformance",
        "check_instance_resolver": "conformance",
        "check_retrieval_backend": "conformance",
        "check_embedding_model": "conformance",
        "check_writeback_executor": "conformance",
    }
    module_name = sources.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(f".{module_name}", __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
