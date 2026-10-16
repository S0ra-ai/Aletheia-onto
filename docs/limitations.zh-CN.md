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
> 数据源与写回通道扩展均已不在此列，
> 见[本体与规则](../README.zh-CN.md#本体与规则)能力矩阵与
> [ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md)、
> [ADR-0013](adr/0013-derived-attributes-and-units.md)、
> [ADR-0014](adr/0014-type-hierarchy-and-business-events.md)、
> [ADR-0015](adr/0015-open-data-sources-and-temporal-validity.md)。
> 扩展点也不在此列：数据源适配器、规则函数、路由策略、写回执行器
> 现已开放注册，见[扩展指南](extending.md)。

## 工程限制

- **无连接池**，每次 `connect()` 新建连接。连接池不是可以随手加的优化：这里的连接带租户
  schema，把连接还给共享池而不区分它当初开在哪个 schema 上，就是把另一个租户的数据交给
  调用方。跨多次 `connect()` 的多步写入同样没有统一事务边界。
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
- HTTP 层共 156 个端点，**已开始拆分 APIRouter**（`routers/`）：
  工作流／权限／工具等已外移，`api.py` 内仍留大部分，按关注点继续外移是后续工作。
  共享运行时下沉到 `http_runtime.py`，避免 `api ↔ routers` 成环。
- 前端 `types/index.ts` **手写**镜像后端模型，而**命名约定并不统一**：
  `decisions._decision_row` 刻意双发两种拼写，而 `/governance/audit-log` 与
  `/governance/model-invocations` 直接 `dict(row)`，**只有 snake_case**。
  审计表的 3 列与模型调用表的 4 列按 camelCase 取值，于是**每一行都渲染成空白**——
  测试与 linter 都发现不了：**antd 的列在 `dataIndex` 不存在时就是空白，不报错**。
  本次修法是让每张表对齐它自己的接口；真正的修法是让一种命名约定胜出。
  **同一处会反复复发**：后来又查出 `/permissions/policies` 七列全空、
  `/tools` 的「类型／风险等级」两列空、`/ontologies/{id}/mappings` 七列里五列空
  （这一处更刺眼——产出正确字段的序列化函数一直就在同一个仓库里，只是那个端点没调它）。
  现在这三处都在 `api/index.ts` 归一化，因为**线上格式与界面形状之间的转换本来就是该文件的职责**，
  逐页修补正是同一个缺陷反复出现的原因。
  平台自身的类型尚不能由 OpenAPI 生成：156 个端点均返回 `dict[str, object]`，
  响应 schema 是裸 object，生成器只会产出 `unknown`。
  **但用户本体的类型已可生成**（`aletheia codegen`），且那才是手写做不对的部分。
  **请求侧的一致性已由测试守住**——
  该测试发现了一处真实缺陷：前端一直在发送 4 个模型兼容性字段，
  而 API 请求模型未声明它们，Pydantic 静默丢弃，于是 Azure 与本地 vLLM 配不上而界面报成功。
  **响应侧目前有两道检查，但都不是完整的。**
  `tests/test_frontend_type_agreement.py` 逐屏列出「界面读取的字段」，断言端点仍在发这些字段——
  这是把契约写下来，不是生成式一致性。它覆盖的是**有界面在读的端点**；
  没有界面读的端点不在覆盖范围内，而「给界面加了字段却没加进这张表」也不会被抓到。
  它读得出「端点还在发这些字段」，**读不出「界面在用这些字段」**：
  `/workflows/{id}/instances/{id}/actions` 与 `.../history` 两个端点的 wire 拼写（`action_code`／`to_state`）
  一直写在契约表里、也一直在被测，而客户端只是把它们 `as` 成了 camelCase——
  于是动作按钮不显示目标状态、点下去必然 422，历史时间线渲染成「初始 → 」，
  而契约表与它那条「字段仍被读到」的反向检查都是绿的（那两个词在别处的归一化函数里出现过）。
  这类「类型断言代替归一化」写法的**行为**现在由前端测试守（见下），而不再只是写进文档。
  `scripts/ui_smoke.py` 以人工检查补上其余部分，报告「每一行都为空的列」；
  它需要浏览器与一个跑着的实例，这正是它属于诊断工具而非门禁的原因。
  它自己也刚刚补上三处盲区——标签页（页面需把当前标签写进 URL）、
  需要先点选才渲染的表格、以及只有图标没有文字的单元格
  （图标列一直被误报为「整列为空」，而**持续报假发现就是在教使用者跳过输出**）。
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

  还剩多少是**可以数的**，不是含糊的说法：后端单句中文拒绝语共 101 条，**已登记 51 条**，
  `tests/test_error_codes.py` 把这个数当作**上限**断言，因此它只会下降。
  未登记的拒绝语不是坏了——控制台显示服务端那句，它依然成立、依然可读，只是另一种语言。
  剩下的大多是读者根本够不到的内部不变量（`instance_key` 拒绝格式错误的实例键、
  `schema` 拒绝空的 DDL 声明、扩展注册表拒绝重名），给这些写翻译只会看起来像覆盖。
  CLI 的输出整体仍是中文优先、没有 `--lang`；它是给部署这套平台的人用的工具，
  而不是控制台读者面对的界面。
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
- **尚未拆分为多个 PyPI 分发包**。当前是单包 `aletheia-onto` + optional extras，
  extras 承载了未来分包的接缝但不冻结边界。

架构层面的前置技术债逐项定位见 [`docs/architecture-debt.md`](architecture-debt.md)。
路线与阻塞条件见 [`ROADMAP.md`](../ROADMAP.md)。
