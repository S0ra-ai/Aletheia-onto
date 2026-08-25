# 测试

> 测试分布与静态检查命令，以及为什么这样断言。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

```bash
.venv/bin/python -m pytest
```

**1348 个测试**，全绿。其中 2 个按环境跳过：无本地 MySQL／PostgreSQL 服务时对应用例自动跳过。

CI 在 3.11／3.12／3.13 上各跑一遍完整测试——**声明支持而不执行的版本，
会先在用户环境里出问题**：Python 保持语法兼容，但会移除标准库模块、改变默认行为，
而本平台通过 sqlite3 读 schema、通过 `ast` 实施规则沙箱。

## 断言行为，而非源码文本

多处断言经历过从「查源码包含某字符串」改为「验实际行为」的重写，理由是前者曾让真实缺陷长期存活：

- **Turtle 导出**曾断言输出「包含」某些子串——而一个语法错误的文档包含子串的能力
  与合法文档毫无差别。它自上线起无法被任何 RDF 解析器读取。现在用 rdflib 解析并 SPARQL 查询。
- **`/v1` 覆盖**曾比对声明的路径列表——在 `/v1` 实际不可达时它是绿的。
  现在发真实未鉴权请求，两种形式都必须返回 401。
- **端点计数**曾 grep 装饰器——把路由挪到 `APIRouter` 上就让数字下降，而没有任何端点消失。

## 反例是断言有效性的证明

每条安全与正确性断言都注入过反例并确认失败：认证默认开启、公理阻断发布、
配额不可被租户修改、IRI 命名空间稳定、签名伪造被拒。
**一个从未被证明能失败的断言与空断言无法区分。**

## 分布

| 文件 | 数量 | 覆盖 |
|---|--:|---|
| `test_documentation_links.py` | 120 | Documentation links resolve, and the entry points a newcomer needs exist |
| `test_instance_resolvers.py` | 57 | Instance resolvers: the conformance suite |
| `test_sql_dialects_and_generic_adapter.py` | 54 | SQL dialect profiles and the generic DB-API adapter |
| `test_cross_object_aggregation.py` | 46 | Cross-object aggregation: rules that reason over more than one instance |
| `test_cross_source_resolution.py` | 46 | 跨源实体消解。ROADMAP 通用性清单最后一项结构性空白。 |
| `test_file_and_rest_sources.py` | 46 | CSV directories and REST APIs as data sources |
| `test_extension_registry.py` | 45 | Contract tests for the platform's extension points |
| `test_conformance_suites.py` | 44 | Executable conformance suites for the extension points |
| `test_derived_attributes_and_units.py` | 42 | Derived attributes and units of measure |
| `test_multi_tenancy.py` | 42 | Multi-tenant isolation: separate schema plus a tenant_id column |
| `test_type_hierarchy_and_events.py` | 42 | Type hierarchy and business events |
| `test_deployment_preflight.py` | 41 | Pre-flight checks for a production deployment |
| `test_cli.py` | 35 | The `aletheia` command line |
| `test_conversations_and_feedback.py` | 35 | Conversation persistence and the feedback loop |
| `test_database_writeback.py` | 35 | Writeback into a legacy database, and via stored procedures |
| `test_temporal_validity.py` | 35 | Temporal validity: what was true, and when |
| `test_metadata_flow.py` | 34 |  |
| `test_sso.py` | 32 | SSO: the provider proves who, the platform decides what |
| `test_composite_instance_keys.py` | 31 | Composite primary keys, end to end |
| `test_answer_regression.py` | 28 | 问答回归测试集。ROADMAP 阶段 G。 |
| `test_api_authentication.py` | 28 | End-to-end authentication and authorization tests |
| `test_inert_fields_activated.py` | 28 | Three fields that were stored but never evaluated |
| `test_document_knowledge.py` | 27 | Document knowledge layer: citations anchored to the ontology |
| `test_domain_neutrality.py` | 25 | Domain neutrality tests |
| `test_standard_vocabulary.py` | 24 | OWL/RDFS/SHACL export: the same ontology in vocabulary other tools can act on |
| `test_platform_context.py` | 23 | Platform context: the object that replaced the module-level singleton |
| `test_relation_expressiveness.py` | 22 | Relation semantics: cardinality, strength and many-to-many |
| `test_api_versioning.py` | 21 | The `/v1` prefix: every route served twice, with identical protection |
| `test_custom_model_endpoints.py` | 21 | Custom model endpoint compatibility |
| `test_axioms.py` | 20 | Axioms: the fifth component of an ontology, and the release gate that uses it |
| `test_scaffold.py` | 19 | Project scaffolding: generated code must actually run |
| `test_audit_reports.py` | 18 | Audit reports: the questions an auditor arrives with, not "what happened recently" |
| `test_rule_engine_safety.py` | 17 | Rule engine safety and release gate tests |
| `test_codegen.py` | 16 | Code generation from a published ontology |
| `test_tenant_quotas.py` | 16 | Tenant quotas: ROADMAP stage B's last open item |
| `test_packaging.py` | 15 | Packaging: the project is installable, and the install is usable |
| `test_workbench_and_graph.py` | 14 | Workbench aggregation and knowledge graph projection |
| `test_value_domain_mapping.py` | 13 | Value domain mapping: legacy codes to semantic states |
| `test_frontend_type_agreement.py` | 12 | The frontend's hand-written types must agree with the API they mirror |
| `test_migrations.py` | 12 | Versioned migrations: the schema changes `SchemaBundle` cannot express |
| `test_retrieval_permission_filtering.py` | 12 | 检索期权限过滤。ROADMAP 阶段 B 的最后一项。 |
| `test_data_source_knowledge_base.py` | 11 |  |
| `test_platform_database_dialects.py` | 10 | Platform database durability and dialect tests |
| `test_credential_protection.py` | 8 | Credential exposure tests |
| `test_derive_completeness.py` | 7 | `derive` must carry forward everything that decides a verdict |
| `test_platform_db_consistency.py` | 7 | `--platform-db` must mean the same database in every command, including `serve` |
| `test_documented_claims.py` | 6 | Documented numbers match the code they describe |
| `test_module_boundaries.py` | 6 | Module boundaries: no import cycles, and no reaching into private names |

## 静态检查与前端构建

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m ruff format --check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## 规模

75 个后端模块约 32700 行，149 个 API 端点，45 张平台表，前端 React + antd。

CI 另有一个 `quickstart` job，在干净环境重跑 README 的快速开始链路，
并校验此处声明的测试数量与实际收集数一致。
