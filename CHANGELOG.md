# Changelog

本文件记录值得用户知道的变更。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

项目尚未发布正式版本。当前处于仓库规范化阶段，API 不承诺稳定。

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
