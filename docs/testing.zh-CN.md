# 测试

> 测试分布与静态检查命令，以及为什么这样断言。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

```bash
.venv/bin/python -m pytest
```

**1782 个测试**，全绿。需要某种本机没有的东西时，用例**跳过而不是失败**：
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
| `test_error_codes.py` | 8 | Refusal codes: the registry quotes sentences the platform says, and the console can name every one of them |
| `test_query_limit_clamping.py` | 8 | 调用方给的 `limit` 无法越过上限把整张表取走（SQLite 把 `LIMIT -1` 读作「不限制」） |
| `test_list_pagination.py` | 17 | 每个随客户数据增长的列表都接受分页；不传 limit 仍然返回全部 |
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
| `test_conversations_and_feedback.py` | 43 | Conversation persistence and the feedback loop |
| `test_database_writeback.py` | 35 | Writeback into a legacy database, and via stored procedures |
| `test_temporal_validity.py` | 35 | Temporal validity: what was true, and when |
| `test_metadata_flow.py` | 80 | 元数据扫描、蓝图草案（含模型响应形状）与映射流程 |
| `test_sso.py` | 32 | SSO: the provider proves who, the platform decides what |
| `test_composite_instance_keys.py` | 31 | Composite primary keys, end to end |
| `test_answer_regression.py` | 28 | 问答回归测试集。ROADMAP 阶段 G。 |
| `test_api_authentication.py` | 57 | End-to-end authentication and authorization tests |
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
| `test_backup.py` | 14 | SQLite 平台安全备份、原子恢复、恢复前留下的那份快照，以及二者各自的审计记录 |
| `test_axioms.py` | 20 | Axioms: the fifth component of an ontology, and the release gate that uses it |
| `test_scaffold.py` | 21 | Project scaffolding: generated code must actually run |
| `test_audit_reports.py` | 18 | Audit reports: the questions an auditor arrives with, not "what happened recently" |
| `test_rule_engine_safety.py` | 34 | Rule engine safety and release gate tests |
| `test_codegen.py` | 16 | Code generation from a published ontology |
| `test_tenant_quotas.py` | 16 | Tenant quotas: ROADMAP stage B's last open item |
| `test_quota_enforcement.py` | 9 | 声明的配额绑定到平台真正写入的那些行——七个资源、两个方向 |
| `test_packaging.py` | 16 | Packaging: the project is installable, and the install is usable |
| `test_workbench_and_graph.py` | 15 | Workbench aggregation and knowledge graph projection |
| `test_value_domain_mapping.py` | 13 | Value domain mapping: legacy codes to semantic states |
| `test_frontend_type_agreement.py` | 97 | The frontend's hand-written types must agree with the API they mirror, on both sides |
| `test_frontend_serving.py` | 4 | 同源生产管理端与 API 传输前缀 |
| `test_metrics.py` | 5 | Prometheus 兼容运行指标与安全重复初始化 |
| `test_migrations.py` | 12 | Versioned migrations: the schema changes `SchemaBundle` cannot express |
| `test_retrieval_permission_filtering.py` | 12 | 检索期权限过滤。ROADMAP 阶段 B 的最后一项。 |
| `test_data_source_knowledge_base.py` | 13 |  |
| `test_platform_database_dialects.py` | 11 | Platform database durability and dialect tests |
| `test_credential_protection.py` | 14 | 凭据不外泄，以及让密钥根本不落库的 `env:`／`file:` 引用 |
| `test_derive_completeness.py` | 7 | `derive` must carry forward everything that decides a verdict |
| `test_platform_db_consistency.py` | 7 | `--platform-db` must mean the same database in every command, including `serve` |
| `test_ui_smoke_guards.py` | 15 | The render check's own guards, exercised without a browser |
| `test_frontend_enum_rendering.py` | 2 | 表格列不许把枚举原样打印出来，必须走标签映射 |
| `test_demo_bootstrap.py` | 2 | 演示按钮第二次按下时，报告它清掉了什么 |
| `test_ui_messages.py` | 9 | 双语字典：两种语言都在、占位符一致、没有界面调不到的键，也没有 `as never` 关掉键检查 |
| `test_ci_workflow.py` | 3 | CI 跑的就是文件里写的那个工作流——折行与重复键 |
| `test_smoke_seeding.py` | 4 | 渲染检查的种子数据真的给每个页面填了行，且只报告它做过的事 |
| `test_every_route_answers.py` | 1 | Every route called once; none may crash |
| `test_documented_claims.py` | 14 | Documented numbers match the code they describe |
| `test_module_boundaries.py` | 6 | Module boundaries: no import cycles, and no reaching into private names |
| `test_object_service.py` | 14 | 通用业务对象浏览（HTTP 与服务层）、元数据、分页代价与行级权限过滤 |

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
**前端现在有测试运行器了**（`npm test`），但它跑在 `node` 里、没有 DOM，
所以**仍然没有渲染组件的测试**——不存在「渲染了表格但没断言单元格有文字」的那一种。
补上它意味着引入 jsdom 与渲染库，那是与「加一个运行器」不同的另一个决定。

治理审计表的 3 列与模型调用表的 4 列就这样**每一行都是空白**，只有浏览器能看见。
现在盯这一类的是两处：下面的渲染检查读**画出来的行**，
以及 `test_frontend_type_agreement.py` 把每个界面读的字段与该端点发的字段对齐。

`scripts/ui_smoke.py` 以无头浏览器驱动运行中的应用，报告**每一行都为空**的列。
它需要浏览器与一个跑着的实例——这正是它**不在测试套件里**的原因：
依赖这两者中任何一个的套件会因为与改动无关的原因失败。

但它在 CI 里作为**独立 job** 运行：在那里浏览器是主角而不是附带依赖，
起不来浏览器就是这份工作真的做不了。该 job 会构建前端、载入一份演示实例，
并扫过 **43 条路由**——每一张画表格的页面、每个把表格藏在后面的标签页、登录页，
以及首个本体与首个数据源详情页（id 从实例里读出来，不是写死的）。

登录页扫的是 **`/admin/login`**，而缺陷正在这里。生产构建把 SPA 挂在 `/admin` 下，
所以路由里的 `/login` **根本不是一个页面**：认证中间件会用
`401 {"detail":"缺少访问令牌"}` 回答它，Chrome 把这段 JSON 渲染成一个 `<pre>`。
而扫描清单从它存在那天起写的就是 `/login`：它读到 `0 table(s), 0 row(s)`，
什么也没报——**「没有表格」正是登录页的样子**，而那几个失败标记读的是应用自己渲染的文案，
一条都不会命中。**它从来没有真正渲染过一次登录页。**
同一个错误还在「会话过期后的跳转」里（`window.location.assign('/login')`），
于是过期的人落在那一页 JSON 上。两处都已修，并且扫描现在会检查**每一个 dump 出来的文档有没有前端的挂载点**：
没有 `<div id="root">` 的文档是别处生成的，不管它写着什么。

路由清单由 `tests/test_ui_smoke_guards.py` **双向**对齐前端路由表：
`App.tsx` 服务的每个路径都要被扫，被扫的每个路径也都要是它服务的。
此前有两个页面从未被访问过（`/admin/demo` 与 `/admin/model`，不是拼错，是压根不在清单里），
而清单里还留着 `/admin/backup`——那是**接口**的命名空间而不是前端路由，浏览器访问它会收到
`401 {"detail":"缺少访问令牌"}`，于是那行读起来是 `0 table(s), 0 row(s)`，
真正的备份页 `/admin/data-backup` 反而一次都没被加载过。

**没有渲染出表格的路由现在会让扫描失败**，除非它连同理由列在 `NO_TABLE_ROUTES` 里；
而列在那里的路由一旦渲染出了表格，同样失败。两个方向都要断言，因为它们是两种不同的失效：
前者是页面坏了，后者是豁免过期了、开始掩盖真问题。

每条路由还会被读一遍「页面没加载出来时应用会渲染的那句话」
（错误边界的「页面加载失败」、兜底路由的「页面不存在」）。
没有这一步，**渲染时抛错的页面与本来就没有表格的页面印出的是同一行**——而后者正躺在那张豁免清单上。

**要答一次表单、或要先挑一条记录的页面，通过把要显示的内容写进 URL 来扫**
（`/admin/semantic?tab=explain&object=contract&instance=1&ontology=1`、`/admin/knowledge?ontology=1`、
`/admin/objects?ontology=1&object=contract&instance=1`）：
每个页面都从 URL 读查询，理由和标签页写进 URL 一样——顺带让「某实例的解释」成为一条可以贴进工单的链接。
对象编码与实例 ID 都从实例里读出来，因此扫的是**真实存在的那一行**：
为一个不存在的实例渲染的解释表，和「字段名对不上」渲染出来的空表长得一模一样，
而这个检查分不出这两者。

**因数据为空而整列为空的列**写在 `KNOWN_SPARSE` 里，并且每次运行都打印出来。
job 随后会**把豁免关掉再扫一遍**，断言它报出的正好是清单里那几条——
**豁免是用来压掉发现的，所以一条过期的豁免压掉的正是这个检查存在的理由**；
这条断言第一次跑就删掉了一条被播种数据变得过期的条目。
脚本分不清「数据里没有」与「字段名对不上」，而靠猜的检查要么漏掉真缺陷、要么在真数据上失败——
所以这份豁免是显式的，**不在豁免里的任何一处仍然会让 job 失败**。动过表格之后手动跑一次：

它会为每条路由打印检查了几张表、几行数据：**什么都没访问到的检查与什么都没发现的检查
输出完全一样**。表格在标签页里的路由写成带标签的查询形式（`/admin/governance?tab=report`）——
该工具只是加载路由再读 DOM，页面若不把当前标签写进 URL，第一个标签页之外的内容就在它的视野之外。

## 最初的五分钟：一个数据都没有的时候

上面的渲染扫描跑在**有种子数据**的实例上，因为没有行的表格什么都检查不了。
于是**每个部署都会经过的那个状态**反而没人看——而没有数据的时候，一屏坏了代价最大，因为读者没有别的路可走。

`python scripts/ui_smoke.py --expect-empty` 用同一批路由走一个平台库为空的实例，对每一屏只问一件事：
**它渲染出来了吗？** 这里不该有表格、不该有「整列为空」、也不该有行，
所以与数据有关的判定全部关掉，只剩下两个在这里真正有意义的检查——**页面崩了**，以及**返回的根本不是这个应用**。
需要实例里还不存在的 id 的详情路由会被**逐条列出**，而不是悄悄跳过。

手工跑一次就抓到了它被造出来要找的那两屏：`/admin/mapping` 说「没有可审核的本体」就没了下文，
工作台的决策卡片说「尚无决策记录」。两处都没有说出下一步——而那一刻读者手里只有这句话。
现在两处都说了。

它作为独立的 CI 步骤运行，实例起在 8078 端口。

## 英文界面真的是英文吗

`scripts/i18n_audit.py` 回答的是双语控制台带来的另一个问题，也是此前**没有任何东西在查**的那个。
字典测试只能读字典：一个自己留了一份中文的页面照样能编译、能过类型检查、能过全套测试。
就有一个这样的页面：侧边栏把「本体改造研发平台」写成字面量，
而 `shell.app.name` 一直躺在字典里没人用——它在每一屏上，贯穿整场迁移的始终。

它带着 `?lang=en` 走同一批路由，读渲染出来的文字，再减掉实例自己持有的内容：
本体名、业务对象、知识条款、读者的显示名。**这些在英文界面上就该是中文**——
翻译别人的数据本身就是一个缺陷——所以它先问接口要一遍这些字符串，
一个片段能活下来才算界面自己的话。

第一次跑出来的结果是三件事：侧边栏写死的品牌名、`index.html` 里的静态 `<title>`，
以及**服务端拼出来的句子**——审计报告、发布门禁的措辞、推理链、一致性建议。
43 条路由里有 20 条本来就是干净的，剩下的如今都拿到了控制台能翻译的 code。
那些服务端句子此前在 `KNOWN_BACKEND_PROSE` 里逐条豁免、逐条写明理由；
**这份清单现在是空的**，留着它是因为机制本身有价值：它能抓住**下一句**没带 code 就发出的服务端措辞。
**一条什么都没匹配上的豁免仍然会让这次运行失败**——豁免会活过它的理由，而它接着掩盖的就是缺陷。

语言可以用 `?lang=en` 或 `?lang=zh` 钉住，这先是功能、然后才是测试钩子：
一条在另一种语言里打开的链接，给控制台设成中文的读者用。
链接里的选择会被采纳，参数随后从地址里取走，所以页眉上的开关不会被 URL 在下一次刷新时推翻。

它不是校对。它读的是中日韩字符，所以它能抓到「这句话从来没被翻译」，
抓不到「这句话翻译得很差」——后半边归 `tests/test_ui_messages.py`，那里管的是两种语言占位符与键一致。

## 规模

89 个后端模块约 38100 行，156 个 API 端点，45 张平台表，前端 React + antd。

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
