# Changelog

本文件记录值得用户知道的变更。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

项目尚未发布正式版本。API 不承诺稳定（ADR-0007）。

## [0.4.0] - 2026-08-23

**通用性清单全部完成。** 数据源不再限于三种数据库，写回不再限于 HTTP，
属性有了时态。ROADMAP 通用性 13 项全部落地。

### Added

- **SQL 方言 profile**（通用性 #12 的前置）：方言差异只有 6 个且都是机械的
  （当前 schema 表达式、标识符引号、参数占位符、分页语法、外键目录形状、
  目录标识符大小写），现声明为 `SqlDialect` 数据对象。
  此前写成 `if dialect == "postgresql" else ...`——**二元分支表达不了第三个数据库**，
  于是接任何新库都必须改扫描代码，也就是 fork。（ADR-0015）
- **通用 DB-API 适配器**：接一个新 SQL 库变成声明 4 行 `DriverSpec`，
  随即获得元数据扫描、列剖析、外键发现、实例解析与全部规则能力。
  Oracle／SQL Server／达梦／人大金仓／openGauss 已内置声明，驱动装上即可用。
  已用真实 PostgreSQL 作为「一个平台没有专用适配器的库」实证整条通用路径。
- **CSV／TSV 目录数据源**：类型与主键从数据推断，**外键不推断**——
  关系语义要求结构是声明的，从命名巧合推出的关系其基数与强弱无法解释。
  外键候选会上报供建模人员声明。这类源的意义常被低估：
  **客户第一次评估平台时用的就是导出文件**，因为拿生产库凭据要走几周流程。
- **REST／OpenAPI 数据源**：字段必须声明，不从响应采样——
  采样出的模式会随响应变化，引用它的判定不可复现。有 OpenAPI 文档时可由它派生。
  未声明的字段不下发：声明就是契约。
- **直写库与存储过程写回**（通用性 #13）：大量遗留系统没有 API，
  集成面就是一张表或一个存储过程。此前平台能判定一个操作却无法执行它。
  语句由声明提供标识符、由请求提供值且一律绑定；
  **无 WHERE 的 UPDATE／DELETE 被拒绝**，DDL 与权限语句被拒绝，
  删除需逐条 opt-in，**影响 0 行按失败处理**。（ADR-0015）
- **属性级时态与 as-of 判定**（通用性 #8）：区分有效时间与事务时间，
  因为回溯更正改变了「当时为真」却没改变「当时已知」，而审计要区分这两者。
  `assess_instance(..., as_of=...)` 按当时的值与**当时生效的规则**判定——
  三月的审计问的是「一月那次放行，按一月已知的信息，对不对」，
  拿今天的值重新判定会给出一个自信的错误答案。
  无版本覆盖该时刻的属性**缺席而非取最近邻**：插值会编造一个从未被记录的事实。
- `aletheia doctor` 新增 `declaredSqlSources`、`sqlDialects`、`writebackSchemes`，
  直接回答「为什么 Oracle 不在数据源列表里」。
- `aletheia assess --as-of` 与 `POST /semantic/objects/{code}/instances/{id}/assess?asOf=`。
- `POST|GET /ontologies/{id}/objects/{code}/instances/{id}/versions` 记录与查询属性历史。

### Changed

- 元数据扫描器与 `SQLRuntime` 改由方言 profile 驱动，消除 5 处二元分支。
- 列剖析的 `limit 5` 改为按方言生成：硬编码在 Oracle／SQL Server／达梦上会失败，
  而剖析会吞掉查询异常——于是**每一列都会静默「剖析为空」而不是报错**。
- `scan_information_schema` 与 `connection_status` 提升为公开 API：
  第三方适配器的全部工作就是提供连接与方言后调用它们。
- CSV 数据源默认可用（无需驱动），因此内置数据源类型从 3 种变为 4 种。

### Fixed

- `aletheia init` 补齐事件表与时态表：此前事件表在 `cmd_init` 里单独调用、
  与其他特性 schema 不一致，容易在新增特性时漏掉。

## [0.3.0] - 2026-08-23

**元模型闭合，包可安装。** `docs/02-核心元模型设计.md` 里画出的对象、属性、
关系、Event、State、Rule、Mapping 现已全部有实现；项目可以 `pip install`。

### Added

- **关系语义**（通用性 #4）：关系带基数（一对一／多对一／一对多／多对多）
  与强弱（组成／聚合／关联）。中间表折叠为直接多对多，中间表对象保留其自身属性。
  分类只依据声明结构（主键、可空性、外键目标），绝不看数据分布。
  每条关系记录判定依据——没有依据的分类无法被审阅。（ADR-0012）
- **跨对象聚合**（通用性 #5）：具名、可审阅的组级取值，如
  「该客户所有生效合同总额」，规则因此能表达「总额不得超过信用额度」。
  算不出来时让规则 fail-closed，而不是与伪造的 0 比较。（ADR-0012）
- **派生属性**（通用性 #7）：表达式计算的属性，如
  `毛利率 = (收入 - 成本) / 收入`。定义一次，所有规则共用。
  复用规则沙箱求值——第二个求值器会漂移，较松的那个会成为突破口。（ADR-0013）
- **单位与量纲**（通用性 #10）：属性可声明单位，同量纲比较自动换算，
  跨量纲比较直接拒绝。修掉一类真实错误判定：万元与元混用时，
  `合同金额 500 > 额度 1000000` 会得出「未超额」。（ADR-0013）
- **类型层级**（通用性 #6）：声明「企业客户是客户的子类型」，
  子类型继承祖先的规则、聚合与派生属性。共性规则只写一次，
  判定结果不再依赖实例属于哪个子类型。覆盖需**显式声明**而非同名推断——
  同名有歧义，推断会静默停用某个团队的管控。（ADR-0014）
- **业务事件**（通用性 #9）：只追加的事件流，带载荷、来源时间与操作者。
  状态流转自动镜像进来，因此实例只有一条统一时间线。
  事件**不触发任何东西**——能触发自动化的事件会让回放历史重新执行业务动作。（ADR-0014）
- **可安装分发**：`pip install aletheia-onto`，内核零第三方依赖。
  optional extras：`web`／`postgresql`／`mysql`／`documents`／`all`。
  含 `py.typed`（PEP 561），否则消费方的类型检查器会静默忽略我们的标注。
- **命令行**：`aletheia init` / `connect` / `model` / `assess` / `publish` /
  `demo` / `serve` / `doctor`。`aletheia demo` 一条命令跑通
  接入 → 建模 → 判定。`publish` 受发布门禁约束，且**待审核的语义映射
  无法用 `--force` 跳过**。
- **`/v1` 路径前缀**：每个端点同时以裸路径与 `/v1` 提供，两条路径经过
  同一套鉴权中间件与同一份权限策略。没有版本前缀，破坏性变更就无处安放。
- README 新增本体词汇表（中英双语），按「本体结构 → 与遗留系统的对应 →
  判定与留痕」三层组织，每条说明它**刻意不是什么**。

### Changed

- **规则沙箱抽为独立模块** `rule_sandbox.py`：安全边界不该埋在
  1200 行的模块里。所有决定「规则表达式能做什么」的代码集中在一处——
  节点白名单、私有属性前缀、可调用函数注册表，以及代码库中唯一的 `eval`。
- **建表 DDL 调度统一**到 `schema.SchemaBundle`，8 处重复实现合并为一处，
  顺带修掉两处漂移：MySQL 索引重跑抛错、「表是否存在」的探测在 PostgreSQL 上
  会中止事务。
- **默认平台库路径改为绝对路径**：源码 checkout 下仍是 `./data`，
  已安装的包用 `~/.aletheia`，可用 `ONTOLOGY_DATA_DIR` 覆盖。
  相对路径会让同一条命令因工作目录不同而找到不同的库，且失败是静默的。
- 规则可在本体语言中引用关联对象（`customer.credit_status`），
  而不再只能用物理表名（`customers`）。
- 一对一子表注入为单行而非集合。此前
  `contract_signature.status != 'void'` 在集合上求值为 `[False]`——
  非空列表为真，于是按常规写法写出的规则会静默通过。

### Fixed

- 循环依赖清零：19 处函数内 import 提升到顶层。
  唯一保留的 `context ↔ database` 必然同包。
- 跨模块私有引用清零。两项不变量由 `tests/test_module_boundaries.py` 守住。
- `aletheia init` 创建的库不再缺少表：此前只有 HTTP 启动会创建可选特性的 schema，
  缺表会在很久之后表现为「这个功能什么都不返回」。

### Added

- 令牌认证与能力授权：PBKDF2-SHA256 加盐存储口令，令牌仅存摘要，
  会话可撤销与过期，改密使旧会话失效。6 种能力 × 6 种角色，
  集中式路由→能力策略表，未登记路由默认仅管理员可访问。
- 审计身份可信：`actor` 取自认证身份，不再接受客户端自报。
- 规则引擎 fail-closed 语义：表达式无法求值时判为「未通过」，
  阻断级→`blocked`，提示级→`review`，并在证据中区分求值失败与业务不满足。
- 写入时表达式校验：不可执行的规则被直接拒绝；
  新增 `POST /ontologies/{id}/rules/validate-expression` 可预校验并提示未知字段。
- 发布门禁：`publish` 前评估 release-readiness，存在阻断项则拒绝发布；
  `force` 覆盖会连同未通过门禁数一并写入审计。
- 凭据脱敏：连接串只隐藏密码段，API Key 仅返回首尾。
- 实例工作流与对象权限存储，含工作流状态、转移、历史、角色、
  对象级策略与工具授权。
- 智能体角色按已接入领域派生，提示词由该领域本体实时渲染。
- 平台库三方言支持（SQLite／MySQL／PostgreSQL），均有集成测试覆盖。
- 新增测试套件：方言（10）、规则安全（17）、凭据（8）、认证（26）、
  领域中立性（25，含静态守卫）。
- 开源基建：Apache-2.0 许可证、贡献指南、行为准则、安全策略、
  ADR-0001~0005、架构技术债清单、ROADMAP。

### Changed

- **破坏性**：请求体不再接受 `actor`／`reviewer`／`publisher` 字段，
  这些值改为从认证身份读取。调用方需改为携带 Bearer 令牌。
- **破坏性**：领域词汇不再内置。删除 `ontology.py` 的 `NAME_HINTS`
  与 `ATTRIBUTE_HINTS`，删除硬编码的 `"contract"` 回退与写死的智能体角色。
  未导入行业蓝图时，草案标签为原始列名。
- 可配置项集中到 `backend/ontology_platform/config.py`，环境变量可覆盖。
- `test-projects/` 移至 `examples/`，并说明其中数据均为合成示例。
- 移除内部项目标识「OpenCode」：脚本改名为 `connect_example_contracts.py`，
  环境变量前缀改为 `EXAMPLE_CONTRACT_*` 与 `ALETHEIA_EXTERNAL_SYSTEM_*`。
- `start_dev.sh` 不再假定存在同级目录的外部项目，改为可选启用。

### Fixed

- MySQL 上写入丢失：`PlatformConnection.__exit__` 委托驱动的上下文管理器，
  而 pymysql 只 close 不 commit，导致块退出时写入被回滚。
  现由适配层自己决定 commit／rollback／close。
- PostgreSQL 上建表全部回滚：`init_schema` 靠捕获驱动错误文本判断列是否存在，
  而一条失败语句会中断整个事务。改为先查 `information_schema`／`pragma`
  再执行 DDL。
- MySQL 不支持 `on conflict ... do update`，适配层改译为
  `on duplicate key update`，并将 `excluded.col` 重写为 `values(col)`。
- MySQL TEXT 列禁止字面量默认值，改用表达式默认值。
- psycopg 缺 `dict_row` 导致按列名取值失败；自增主键读取兼容 tuple 与 dict 行。
- SQLite 启用 WAL 与 `busy_timeout`，消除并发写入时的 database is locked。
- 数据源序列化改用 `public_dict()`，此前 `__dict__` 会连同密码一起返回。
- 同一领域接入两个系统时本体草案重名，改为按数据源命名。

### Security

- 沙箱加固：拒绝规则函数的关键字参数，拒绝任何 dunder 属性访问
  （`__class__`／`__globals__` 是逃逸入口）。
- 见 [SECURITY.md](SECURITY.md) 中「已知的安全相关限制」，
  其中 `filter_expression` 与 `guard_expression` 均为**未生效**字段，
  不可依赖其做隔离或准入。

[Unreleased]: https://github.com/S0ra-ai/Aletheia-onto/commits/main
