# 测试

> 测试分布与静态检查命令，以及为什么这样断言。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

```bash
.venv/bin/python -m pytest
```

**1680 个测试**，全绿。需要某种本机没有的东西时，用例**跳过而不是失败**：
MySQL／PostgreSQL 相关用例在缺驱动或连不上服务时跳过，前端相关用例在没有构建产物时跳过。
在没装这两个驱动的开发机上这是 **9 个**跳过，在 CI 上是 **3 个**——CI 两个驱动都装，
并把两个数据库作为 service container 起起来。把数字写死在这里，描述的是读文档那台机器而不是测试套件，
所以这里不写死。

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
| `test_documentation_links.py` | 126 | Documentation links resolve, and the entry points a newcomer needs exist |
| `test_instance_resolvers.py` | 57 | Instance resolvers: the conformance suite |
| `test_sql_dialects_and_generic_adapter.py` | 54 | SQL dialect profiles and the generic DB-API adapter |
| `test_cross_object_aggregation.py` | 46 | Cross-object aggregation: rules that reason over more than one instance |
| `test_cross_source_resolution.py` | 46 | 跨源实体消解。ROADMAP 通用性清单最后一项结构性空白。 |
| `test_file_and_rest_sources.py` | 46 | CSV directories and REST APIs as data sources |
| `test_extension_registry.py` | 45 | Contract tests for the platform's extension points |
| `test_conformance_suites.py` | 44 | Executable conformance suites for the extension points |
| `test_derived_attributes_and_units.py` | 42 | Derived attributes and units of measure |
| `test_multi_tenancy.py` | 42 | Multi-tenant isolation: separate schema plus a tenant_id column |
| `test_request_observability.py` | 42 | 请求标识、访问日志与结构化日志 |
| `test_type_hierarchy_and_events.py` | 42 | Type hierarchy and business events |
| `test_deployment_preflight.py` | 45 | Pre-flight checks for a production deployment |
| `test_cli.py` | 41 | The `aletheia` command line |
| `test_conversations_and_feedback.py` | 41 | Conversation persistence and the feedback loop |
| `test_database_writeback.py` | 35 | Writeback into a legacy database, and via stored procedures |
| `test_temporal_validity.py` | 35 | Temporal validity: what was true, and when |
| `test_metadata_flow.py` | 72 | 元数据扫描、蓝图草案（含模型响应形状）与映射流程 |
| `test_sso.py` | 32 | SSO: the provider proves who, the platform decides what |
| `test_composite_instance_keys.py` | 31 | Composite primary keys, end to end |
| `test_answer_regression.py` | 28 | 问答回归测试集。ROADMAP 阶段 G。 |
| `test_api_authentication.py` | 55 | End-to-end authentication and authorization tests |
| `test_inert_fields_activated.py` | 29 | Three fields that were stored but never evaluated |
| `test_document_knowledge.py` | 27 | Document knowledge layer: citations anchored to the ontology |
| `test_domain_neutrality.py` | 25 | Domain neutrality tests |
| `test_standard_vocabulary.py` | 24 | OWL/RDFS/SHACL export: the same ontology in vocabulary other tools can act on |
| `test_platform_context.py` | 23 | Platform context: the object that replaced the module-level singleton |
| `test_rate_limiter.py` | 24 | 固定窗口请求限流，以及施加限流的中间件 |
| `test_relation_expressiveness.py` | 22 | Relation semantics: cardinality, strength and many-to-many |
| `test_api_versioning.py` | 23 | The `/v1` prefix: every route served twice, with identical protection |
| `test_custom_model_endpoints.py` | 28 | Custom model endpoint compatibility |
| `test_error_messages.py` | 21 | 失败时用户读到什么：驱动与解释器原文不再直接示人 |
| `test_backup.py` | 10 | SQLite 平台安全备份、列表与原子恢复 |
| `test_axioms.py` | 20 | Axioms: the fifth component of an ontology, and the release gate that uses it |
| `test_scaffold.py` | 21 | Project scaffolding: generated code must actually run |
| `test_audit_reports.py` | 18 | Audit reports: the questions an auditor arrives with, not "what happened recently" |
| `test_rule_engine_safety.py` | 34 | Rule engine safety and release gate tests |
| `test_codegen.py` | 16 | Code generation from a published ontology |
| `test_tenant_quotas.py` | 16 | Tenant quotas: ROADMAP stage B's last open item |
| `test_packaging.py` | 15 | Packaging: the project is installable, and the install is usable |
| `test_workbench_and_graph.py` | 15 | Workbench aggregation and knowledge graph projection |
| `test_value_domain_mapping.py` | 13 | Value domain mapping: legacy codes to semantic states |
| `test_frontend_type_agreement.py` | 90 | The frontend's hand-written types must agree with the API they mirror, on both sides |
| `test_frontend_serving.py` | 4 | 同源生产管理端与 API 传输前缀 |
| `test_metrics.py` | 5 | Prometheus 兼容运行指标与安全重复初始化 |
| `test_migrations.py` | 12 | Versioned migrations: the schema changes `SchemaBundle` cannot express |
| `test_retrieval_permission_filtering.py` | 12 | 检索期权限过滤。ROADMAP 阶段 B 的最后一项。 |
| `test_data_source_knowledge_base.py` | 13 |  |
| `test_platform_database_dialects.py` | 10 | Platform database durability and dialect tests |
| `test_credential_protection.py` | 8 | Credential exposure tests |
| `test_derive_completeness.py` | 7 | `derive` must carry forward everything that decides a verdict |
| `test_platform_db_consistency.py` | 7 | `--platform-db` must mean the same database in every command, including `serve` |
| `test_ui_smoke_guards.py` | 6 | The render check's own guards, exercised without a browser |
| `test_ci_workflow.py` | 2 | CI 跑的就是文件里写的那个工作流——折行与重复键 |
| `test_every_route_answers.py` | 1 | Every route called once; none may crash |
| `test_documented_claims.py` | 13 | Documented numbers match the code they describe |
| `test_module_boundaries.py` | 6 | Module boundaries: no import cycles, and no reaching into private names |
| `test_object_service.py` | 13 | 通用业务对象浏览（HTTP 与服务层）、元数据、分页代价与行级权限过滤 |

## 静态检查与前端构建

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m ruff format --check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## 静态检查看不见的东西：一张表里整列为空

以上都抓不到「列的 `dataIndex` 与接口返回的字段名不一致」。antd 对不存在的键什么都不画，
linter 看到的是一个合法字符串，mypy 看到的是合法 `string`。
**而前端根本没有测试运行器**——没有 vitest、没有 Testing Library、`package.json` 里没有 test 脚本，
所以不存在「渲染了表格但没断言单元格有文字」的那种组件测试。这一段此前声称它存在。

治理审计表的 3 列与模型调用表的 4 列就这样**每一行都是空白**，只有浏览器能看见。
现在盯这一类的是两处：下面的渲染检查读**画出来的行**，
以及 `test_frontend_type_agreement.py` 把每个界面读的字段与该端点发的字段对齐。

`scripts/ui_smoke.py` 以无头浏览器驱动运行中的应用，报告**每一行都为空**的列。
它需要浏览器与一个跑着的实例——这正是它**不在测试套件里**的原因：
依赖这两者中任何一个的套件会因为与改动无关的原因失败。

但它在 CI 里作为**独立 job** 运行：在那里浏览器是主角而不是附带依赖，
起不来浏览器就是这份工作真的做不了。该 job 会构建前端、载入一份演示实例，
并扫过 **35 条路由**——每一张画表格的页面、每个把表格藏在后面的标签页，
以及首个本体与首个数据源详情页（id 从实例里读出来，不是写死的）。

**因数据为空而整列为空的列**写在 `KNOWN_SPARSE` 里，并且每次运行都打印出来。
job 随后会**把豁免关掉再扫一遍**，断言它报出的正好是清单里那几条——
**豁免是用来压掉发现的，所以一条过期的豁免压掉的正是这个检查存在的理由**；
这条断言第一次跑就删掉了一条被播种数据变得过期的条目。
脚本分不清「数据里没有」与「字段名对不上」，而靠猜的检查要么漏掉真缺陷、要么在真数据上失败——
所以这份豁免是显式的，**不在豁免里的任何一处仍然会让 job 失败**。动过表格之后手动跑一次：

它会为每条路由打印检查了几张表、几行数据：**什么都没访问到的检查与什么都没发现的检查
输出完全一样**。表格在标签页里的路由写成带标签的查询形式（`/admin/governance?tab=report`）——
该工具只是加载路由再读 DOM，页面若不把当前标签写进 URL，第一个标签页之外的内容就在它的视野之外。
## 规模

86 个后端模块约 36100 行，156 个 API 端点，45 张平台表，前端 React + antd。

CI 另有一个 `scaffold` job，走的是**新部署**那条路——`aletheia new`、安装、`init`、
`connect`、`model`、`verify.py`——因为那条路上的三个缺陷都是**靠人工走一遍**发现的，
没有任何检查看见过它们。

CI 另有一个 `quickstart` job，在干净环境重跑 README 的快速开始链路，
并校验此处声明的测试数量与实际收集数一致。

工作流文件本身也在检查范围内。`ci.yml` 是手写的，而两个手写错误都是到了 GitHub 才暴露、
本地一样都没拦住：一是 `run:` 用 shell 反斜杠续行——YAML 会先把换行折叠成空格，
那个 `\` 于是落在空格上，脚本收到的是 `" --base-url"` 这样一个带前导空格的参数，
argparse 于是报「无法识别的参数」；二是三个 job 键重复，`yaml.safe_load` 取最后一份不吭声，
GitHub 直接拒绝整个文件，于是一个 job 都没跑起来。
`test_ci_workflow.py` 把文件当作 YAML **节点**来读——源码书写风格与被丢弃的重复键都还在——
两条都能拦住，且两条都已在真实缺陷上确认会失败。
