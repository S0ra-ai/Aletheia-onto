# ADR-0004 平台库支持三方言，SQL 差异由适配层统一吸收

- 状态：Accepted
- 日期：2026-08-21

## Context

平台自身需要一个数据库来存本体、映射、规则、决策留痕等 31 张表。

B 端交付的现实约束：客户的 DBA 团队通常只维护一种数据库，
并且会拒绝为一个新系统引入第二种。要求客户「必须用 PostgreSQL」
会在采购环节直接被否掉。同时，开发和演示需要零配置就能跑起来。

## Decision

平台库支持 SQLite、MySQL、PostgreSQL 三种方言，三者都是一等公民，
都有集成测试覆盖。SQLite 为默认，无需任何外部服务。

SQL 差异集中在 `database.py` 的适配层吸收，业务代码只写一种风味的 SQL
（SQLite 风味，用 `?` 占位符与 `on conflict ... do update`）。
适配层负责：

| 差异 | 处理 |
|---|---|
| 占位符 `?` vs `%s` | `_adapt_sql()` 按方言替换 |
| upsert 语法 | `on conflict (...) do update set` → MySQL 的 `on duplicate key update`，`excluded.col` → `values(col)` |
| TEXT 列默认值 | MySQL 禁止字面量默认值，改用表达式默认值 `default ('[]')` |
| 列类型 | `ColumnMigration` 按方言分别声明（`text`／`timestamp`／`datetime` 不可移植） |
| 行工厂 | psycopg 需显式 `dict_row` 才能按列名取值 |
| 自增主键 | `_scalar()` 同时处理 tuple 与 dict 行 |
| 提交语义 | `PlatformConnection.__exit__` 自己决定 commit／rollback／close |

最后一项是本决定中最容易被低估的部分。三个驱动在上下文管理器退出时行为
各不相同：sqlite3 提交但不关闭，psycopg 提交并关闭，**pymysql 只关闭不提交**。
原实现委托给驱动的 `__exit__`，导致 MySQL 上所有写入在退出时被回滚。

迁移采用「先查目录再执行」而非「执行后捕获错误」：
PostgreSQL 上一条失败的语句会中断整个事务，导致同事务内已建的表全部回滚。
因此 `_apply_column_migrations()` 先读 `information_schema` / `pragma table_info`，
只对确实缺失的列发 DDL。

## Alternatives considered

**只支持 PostgreSQL。** 拒绝理由：采购阻力。国内 B 端大量存量是 MySQL。

**用 SQLAlchemy Core 抹平方言。** 拒绝理由：本项目对 SQL 的使用是浅的
（CRUD + 少量 join），引入 ORM 层的收益不足以抵偿它带来的抽象成本与
调试难度；且 DDL 的方言差异 SQLAlchemy 也不能完全抹平。
这个决定值得在阶段 E 迁移 Alembic 时重新评估。

**只支持 SQLite，让客户自己换。** 拒绝理由：SQLite 不适合多写入并发，
且「自己换」意味着客户要改我们的代码。

## Consequences

正面：客户可以用自己的运维栈；开发零配置。三方言的一致性有测试保证，
不是「理论上支持」。

负面：每加一张表要考虑三份 DDL 的方言细节，写错只会在对应后端暴露。
目前 DDL 分散在 4 个模块各自手写三方言
（`database.py`、`workflow_permission.py`、`auth.py`、`agent_roles.py`），
这是已记录的技术债，应迁移 Alembic 统一管理。

负面：CI 需要拉起 MySQL 与 PostgreSQL service 容器。本地无服务时
对应测试自动跳过，避免把「没装数据库」误报成「代码有问题」。

## 证据

`tests/test_platform_database_dialects.py`（10 个测试）。
CI 在 MySQL 8.4 与 PostgreSQL 16 上跑全量测试。
