# 当前限制

> 诚实优先：做不到什么，以及为什么那是设计而非缺陷。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

诚实优先。以下每一项都在代码中逐项确认过。

## 字段存在但逻辑未生效

**本节已清空。** 这类最危险，因为接口看起来能用——所以逐项记录它们是如何消失的：

> - `guard_expression`、`filter_expression`、`depends_on` 现已真实生效，
>   `permission_policy` 已带本体维度。四者均为 fail-closed：无法求值时拒绝而非放行。
> - `derive` 新版本现已复制工作流定义与规则的求值列（`priority`、生效期、`depends_on`）。
>   此前它们被丢弃，而那不只是丢元数据：派生版本会以不同顺序、在不同生效期内求值同一批规则——
>   「新版本给出不同判定」恰恰是 `derive` 最不该静默做的事。
>   实例状态**刻意不复制**：定义属于模型，而某份合同当前在哪个状态属于数据。
> - 模型配置的四个兼容性字段（`authStyle` 等）现已声明。此前前端一直在发、
>   而 Pydantic 静默丢弃，于是界面报成功而 Azure 与本地 vLLM 配不上。

**列表端点：行数随客户数据增长的那些可以分页，其余刻意不分。**
八个取 `limit` 并返回 `pagination` 块：`/ontologies/{id}/mappings`（最可能真的涨到几万——一列映射一行）、
`/ontologies/{id}/rules`、`/ontologies`、`/data-sources`、`/data-sources/{id}/apis`、`/auth/users`、
`/ontologies/{id}/knowledge/documents`，加上原本就分页的两个，以及按上限截断并带 `truncated` 标志的三处历史
（事件 500 条、属性版本 1000 条）。**不传 `limit` 仍然返回全部**——这是现有界面依赖的性质：
好几处拿 `array.length` 当标签页计数，还有几处用它判断空状态，所以悄悄加一个默认上限
会让这些数字出错而不让任何东西失败。

没分页的那些，长度由**平台配置**而不是客户的库结构决定：`/permissions/roles`、
`/permissions/policies`、`/tools`、`/tenants`、`/industry-blueprints`、配额资源、
以及那些静态目录（`/units`、`/resolvers`、`/axiom-kinds`、`/source-types`、`/writeback-channels`）。
给六个内置角色配一个分页器是仪式，如实说明比加上去好。
`/conversations/{id}` 的消息是唯一一处判断口径：它的长度由一个人愿意打多久决定，
而这个控制台上不存在长到需要翻页的会话。

**两个只追加的列表改为游标分页。** `limit`/`offset` 每次都从顶部重新数，
于是第一页与第二页之间到达的一行会把所有行往下推一格，读者要么看到重复行，要么——在审计留痕上，这才是要紧的那个——**永远看不到某一行**。
`/governance/audit-log` 与 `/governance/model-invocations` 现在接受 `beforeId`/`afterId` 并返回 `cursors` 块；
`tests/test_list_pagination.py` 先**复现**偏移分页的丢行，再证明游标能在行不断插入的情况下走完整个审计日志。
其余列表保留偏移分页：它们是审核队列与配置表，没人在读的同时写。

同一句话的另一半**曾经是缺陷，已修**：四个端点（`/governance/audit-log`、
`/governance/model-invocations`、`/governance/decisions`、`/tools/pending-reviews`）
接受 `limit` 之后原样送进 SQL，而 SQLite 把 `LIMIT -1` 读作「不限制」——
`?limit=-1` 会把这个部署写过的一切一次返回。那不是「响应有点大」，是一个没人决定要建的导出端点。
`tests/test_query_limit_clamping.py` 从两个方向守住它，`tests/test_list_pagination.py`
守住上面那两条性质：不传 limit 就是全部，`total` 是真计数而不是一页的大小。

## 结构性表达力约束

设计上的封顶，不是 bug，构成下一阶段的改造对象：

| 约束 | 位置 |
|---|---|
| **跨源匹配在内存中进行**：逐行读副源后比对，有行数上限；副源匹配列无索引时会慢 | `entity_resolution.py` |
| **跨源不做传递推导**：A↔B、B↔C 不会自动得出 A↔C——那会引入一条没人声明过的对应关系 | `entity_resolution.py` |
| **时态只覆盖平台观测到的区间**：原地覆盖值的源系统丢掉的历史无法重建。`coverage` 会明确上报可回答区间 | `temporal.py` |
| **聚合在 Python 内计算**，不下推 SQL。换来三方言行为一致，代价是行数上限 | `aggregation.py` |
| **行级权限过滤逐候选行判定**。过滤表达式是沙箱中求值的任意表达式，无法下推 SQL：配置了过滤时，列出一个对象要读取每个候选行（至多到候选上限）；未配置时只读返回的那一页 | `object_service.py`、`workflow_permission.py` |
| **业务对象列表最多考察 10 万个候选行**，因此 `total` 是该窗口内的计数，而非对数据源的 `COUNT(*)` | `object_service.py` |
| **关系分类依赖 schema 声明质量**：不写外键、不写 NOT NULL 的库只能得到最弱分类 | `relations.py` |
| **CSV 与 REST 不推断外键**：关系语义要求结构是声明的，从命名巧合推出的关系无法解释 | `file_adapter.py`、`rest_adapter.py` |
| **CSV 每次查询整文件读取**：适合导出规模，不适合仓库规模 | `file_adapter.py` |
| **类型层级上限 16 层**，派生链上限 5 趟 | `type_hierarchy.py`、`derived_attributes.py` |
| **不做完整 OWL/DL 推理**，不做开放世界假设 | 刻意，见 [ADR-0005](adr/0005-semantic-generality-ceiling.md) |

> 关系基数、类型层级、跨对象聚合、派生属性、单位量纲、业务事件、时态生效期、
> 数据源与写回通道扩展均已不在此列，见[能力矩阵](capabilities.zh-CN.md)与
> [ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md)、
> [ADR-0013](adr/0013-derived-attributes-and-units.md)、
> [ADR-0014](adr/0014-type-hierarchy-and-business-events.md)、
> [ADR-0015](adr/0015-open-data-sources-and-temporal-validity.md)。
>
> 扩展点也不再此列：数据源适配器、规则函数、路由策略与写回执行器都可注册，
> 见[扩展指南](extending.zh-CN.md)。
> 扩展点也不在此列：数据源适配器、规则函数、路由策略、写回执行器
> 现已开放注册，见[扩展指南](extending.md)。

## 工程限制

- **连接池已经有了，默认关闭。** `ONTOLOGY_CONNECTION_POOL_SIZE` 让 PostgreSQL 与 MySQL 复用平台库连接；
  `0` 保持旧行为（每次 `connect()` 新建），也就是每个既有部署现在的样子，以及运维升级后
  除非主动要求否则应该得到的东西。默认关闭而不是默认开启，因为打开它会改变部署持有的连接数，
  那是容量规划的决定，不该替别人默默做。

  分键是它安全的原因。池的条目是 `(数据库类型, 连接串, schema)`——正好是每个适配器开连接时
  在会话上配置的东西（PostgreSQL 的 `search_path`、MySQL 的时区）。为一个租户借用不可能命中
  另一个租户留下的条目，而 `tests/test_connection_pool.py` 是**直接断言**这件事，不是论证它。
  归还前会回滚，回滚本身失败就关闭而不是放回，因此没有借用者会继承一个未结束的事务。

  **SQLite 无论设置如何都不池化。** `sqlite3.connect` 把连接绑定在打开它的那个线程上，
  而池按构造是线程安全的——池化后交给另一个线程，会在**第一个跑到它的查询**里抛错。
  多数部署的平台库就是 SQLite，所以这是正确性边界而不是调优选择。

- **凭据仍没有静态加密——但已经可以不必存储。** 直接写进行的数据源密码或模型 API key 仍以明文
  存放在平台库中，那种配置下**平台库本身就是凭据存储**：请用文件权限与数据库访问控制保护它。
  变的是现在有了另一条路，两个值都可以写成**引用**而不是密钥本身：

      connection_uri = "env:CONTRACTS_DSN"
      api_key        = "file:/run/secrets/azure-openai-key"

  在连接时解析，且只在**所有适配器都要经过的那一处**（`get_adapter`）；绝不在显示路径上解析——
  设置页显示的是那条引用，而「用的是哪个密钥」正需要让运维看得见。
  引用指不到东西时**报错而不是用空值去连**：空密码会失败在「密码不对」，把读者引向错误的问题。

  这刻意不是加密。逐行加密需要零依赖内核不携带的密码学依赖，而**密钥与密文放在一起的加密
  比不加密更糟——它看起来像保护**。不存密钥是不需要任何依赖的那条路，而且它是**移除那一行**，
  而不是把它遮起来。
- **请求限流默认关闭**，需设置 `ONTOLOGY_RATE_LIMIT_PER_MINUTE`；
  `aletheia preflight` 会报告「可从网络访问但未设限流」的部署。
  计数器按进程独立，因此实际额度是配置值乘以 worker 数。
- **CSRF 防护未实现，且以当前形态并不适用。** 平台用 `Authorization: Bearer` 头认证、
  不设置任何 cookie，浏览器不会自行把凭据附到跨站请求上。若将来引入基于 cookie 的会话，
  这一条就不再成立——见 [`SECURITY.md`](../SECURITY.md)。
- **`platform_db` 签名已全部改为 `PlatformDb`**（上下文／路径／字符串三者皆可）。
  此前标注写 `Path | str` 而运行时接受 context——**那比不标注更糟：它让类型检查器
  拒绝本来可用的代码**，于是多租户与嵌入被文档声称支持、却对任何跑 mypy 的下游不可达。
- HTTP 层共 156 个端点，全部在 `routers/` 里，按关注点分组：认证、数据源、知识、元模型、
  模型治理、语义／智能体／自动化、租户、工作流与权限。另有 4 个直接声明在 app 上、不计入这 156：
  `/`、`/admin`、`/admin/`、`/admin/{frontend_path:path}`——就是单页应用的外壳本身。
  这一段此前写的是「其中 **31 个仍在 `api.py` 里**——应用外壳（`/`、`/admin/*`、
  `/health`、`/files`、`/metrics`）、备份、演示引导」，三处都漂了：数字、清单，以及那个区分本身。
  `/health`、`/files`、`/metrics` 和演示引导现在都在 `routers/` 里，
  而数字没能跟着它们动，因为它是散文。真正属于应用自己边缘、而不是某个领域的，是那层外壳；
  把它留在这里是一个决定，而不是一条待清空的队列——挪走它只会让
  「单页应用是从哪儿发出的」多一个文件要翻。现在两个数字、两种语言都由
  `tests/test_documented_claims.py` 数出来。
  共享运行时下沉到 `http_runtime.py`，避免 `api ↔ routers` 成环。
- **响应类型由生成器产出，界面在有条件的地方直接读它。** 七个行类型
  （`Ontology`、`SemanticMapping`、`BusinessRule`、`PermissionRole`、`AuditLogItem`、
  `ModelInvocationItem`、`DecisionRecordItem`）现在是指向 `frontend/src/types/generated.ts`
  声明的别名，而该文件过期的会让 CI 失败。

  其余仍是手写，**而且是刻意的——理由值得写下来，而不是留成一句待办**。生成文件描述的是**线上格式**；
  控制台有一半端点在进入页面前会先经 `api/index.ts` 归一化——
  `/permissions/policies` 发的是 `can_read`，策略表读的是 `canRead`。
  对这些端点，界面的类型就是**归一化之后**的形状，硬把它换成生成声明，
  等于删掉那七次「整列为空」赖以修复的归一化函数。**这条是试出来的**：
  四个类型用别名替换后 `tsc` 直接拒绝，点名的正是 `canRead`、`toolType`、`tableName` 这些字段。

  所以这里是两套机制而不是一套，且各有一个测试：
  `test_generated_types.py` 守线上形状，`normalise.test.ts` 守「界面读到的形状」。
  后台改一次字段名，二者必有一个会响，而生成文件里写清了它属于哪一类。

- **对象浏览器过去会把所有相关表的列画在一张网格里，这已经修好**：现在只渲染所选对象的属性。
  一行数据属于一张表，所以属于其他表的每一列在每一行里都是横杠——演示库上有十四列——
  而读者分不出哪些列是在说他面前这一行。修法就是这一页自己写的那句：
  **只渲染这个实例真正来自的那张表的列。**

  发现它的是「占位符也算空」那条规则：`render: (x) => x || '-'` 曾经同时骗过组件测试与浏览器扫描，
  因为横杠也是文字。现在两者都把 `-`、`—`、`暂无`、`N/A` 当作空，这十四列才被看见。

- **界面是双语的，服务端说的话大部分也已经能翻译；剩下的是 CLI，以及还没登记的那些拒绝语。**
  19 个页面走 `i18n/messages/`，语言开关也切换 antd 自己的文案；
  服务端拼出来的**建议、门禁评语、审计发现、判定建议、推理链句子**现在都**带着稳定的 code 与
  它要说的那几个数**发出来，控制台按 code 说自己的话，认不出的 code 才回落到服务端那句。
  `scripts/i18n_audit.py` 在 CI 里核对这件事：**英文界面上不该出现没翻译的界面文案**，
  而它现在一条豁免都不需要——`KNOWN_BACKEND_PROSE` 是空的，留着是因为机制本身有价值：
  新加一句服务端措辞会被它抓住，而一条什么都没匹配上的豁免会让运行失败。
  **失败**这一类现在也接上了：`error_codes.py` 按领域层抛出的句子识别出这是哪一次拒绝，
  `decorate` 把 `code` 与 `facts` 放在 `detail` 旁边一起发出，控制台认得这个 code 就说自己的话。
  覆盖了认证与鉴权、登录与口令规则，以及读者最可能撞上的那几条治理拒绝——
  未确认映射就发布、直接改已发布本体、对象没有绑定来源表。

  还剩多少是**可以数的**，不是含糊的说法：后端字面抛出的中文单句拒绝语共 101 条，**已登记 91 条**。
  这是「单句」那一半；由 f-string 拼出来、读者会看到里面带着取值的那一半（注册表整体 **229 个码**）
  也已登记，**还剩 10 条**。差额大部分来自「面向扩展作者」那一批：框架的扩展作者也是用户，
  写适配器、解析器、写回执行器或方言档案的人，就是在 `aletheia verify`、建模界面
  和他们自己的第一次运行里读这些句子的。`tests/test_error_codes.py` 把 10 当作**上限**断言，因此它只会下降。
  未登记的拒绝语不是坏了——控制台显示服务端那句，它依然成立、依然可读，只是另一种语言。
  剩下的大多是读者根本够不到的内部不变量（`instance_key` 拒绝格式错误的实例键、
  `schema` 拒绝空的 DDL 声明、扩展注册表拒绝重名），给这些写翻译只会看起来像覆盖。
  扩展作者那批之后剩下的，是只有平台自己被装错时才会触发的那一组——
  声明了 DDL 里没有的表的那种 `SchemaBundle`、占位符没被替换的模板。
  **CLI 现在也是双语的**（`--lang en`，或 `ONTOLOGY_LANG`），覆盖它**关于自己所说的一切**：
  帮助文本、自己的错误、它拼出来描述刚做完什么的句子，以及 `doctor` 里解释「为什么这个驱动不可用」的提示。
  它不翻译的是打印出来的 JSON——那是 API 的输出，保持中文的理由与英文控制台回落到它相同：
  载荷的形状与词汇是流水线解析的契约，翻译它会让同一个响应向不同调用方说不同的话。
  界面在英文模式下会回落到这些中文句子——这仍然是「界面是英文的」与「读到的东西都是英文的」
  之间的那条缝，只是它现在只出现在**出错**和自我描述的场景里。

- **前端现在有测试运行器了，覆盖的是它能覆盖的那一层。** `npm test` 跑 vitest，
  环境是 `node`、**没有 DOM**——不引 jsdom、不引 Testing Library、不渲染组件——
  测的是「线上格式到界面之间」的那层纯代码：载荷归一化函数（为此从 `api/index.ts` 移到了
  `api/normalise.ts`）、`label()` 的回退、`i18n/text.ts` 的句子助手、`i18n/translate.ts` 的查表。
  静默失效一直就住在这儿：**四次**「整列为空」都是归一化函数从 `snake_case` 的载荷上读 `camelCase`，
  而没有任何东西失败。
  它**刻意不覆盖**需要渲染组件的东西——排序错、按钮接错处理函数、布局。
  那些仍归 `scripts/ui_smoke.py` 与 `scripts/i18n_audit.py`（驱动真浏览器），
  以及 `tests/test_frontend_type_agreement.py`（把每个界面读的字段与该端点发的字段对齐）。
  三处检查、三个问题，没有互相冒充覆盖。
- **版本化迁移已具备**（`migrations.py`）：账本记录已应用版本，改列／回填／删表这类
  非幂等变更现在有处可去。**不采用 Alembic**——它依赖 SQLAlchemy，与内核零依赖冲突；
  而它真正提供的（版本账本 + 有序应用）只需 150 行，且自动生成在此不可用
  （DDL 是按方言声明的字符串，无模型元数据可 diff）。
- **还没有发布到任何包索引。** `pip install aletheia-onto` 装不到任何东西——这个名字不在 PyPI 上，
  而 PyPI 上的 `aletheia` 是另一位作者的不相关项目。wheel 从仓库可以构建并安装
  （CI 就是把它装进一个干净的 venv 来验证的），但没有可钉住的版本号，也没有 `pip install -U`
  可用来升级。发布工作流已经写好（打标签、校验版本号、构建、把构建出的 wheel 装进干净环境跑通闭环、
  再上传），它等的是一个 PyPI trusted publisher，不是代码。**发布**正是「一个你克隆下来的仓库」
  与「一个你采用的框架」之间差的那一步，
  它写在[框架成熟度](framework-readiness.zh-CN.md#还没有的部分)。

  **尚未拆分为多个 PyPI 分发包**是更晚一步的问题：先发布，再谈单包 + extras，
  让 extras 承载未来的接缝而不冻结边界。

架构层面的前置技术债逐项定位见 [`docs/architecture-debt.md`](architecture-debt.md)。
路线与阻塞条件见 [`ROADMAP.md`](../ROADMAP.md)。
