# 框架化前置技术债

这份清单不美化。每一项都给出可核对的定位，都是把 Aletheia 从
「可运行的产品」变成「可被第三方扩展的框架」之前必须偿还的债。
对应 [ROADMAP](../ROADMAP.md) 的**阶段 C：依赖倒置**。

核对时间：2026-08-21，基于 `codex/repo-normalization` 分支。

## 1. 全局状态：一个进程只能有一个平台实例

`backend/ontology_platform/database.py:20`

```python
_platform_adapter: Optional["PlatformAdapter"] = None
```

模块级全局单例，由 `configure_platform_db()` 写入（`database.py:48`），
被 `connect()` 与 `initialize_platform_db()` 读取（`database.py:589`、`600`）。

后果：**一个进程无法同时运行两个不同配置的平台实例。** 这直接堵死两件事：

- 多租户（阶段 B）中「每租户一个 schema 或一个库」的实现方式
- 在同一个测试进程内并行验证三种方言

## 2. `platform_db` 满签名传递

`platform_db: Path | str` 出现在 20 个模块的函数签名里，
其中 `workflow_permission.py` 26 处、`agent.py` 12 处、`governance.py` 12 处、
`metadata.py` 11 处、`model_client.py` 11 处。

它实际上是「连接 + 配置 + 注册表」三件事的贫血替身。每引入一个跨切面关注点
（租户标识、请求上下文、插件注册表、当前 principal），就要再改一遍
这上百个签名。

应改为携带连接、配置与注册表的上下文对象，一次性把这类关注点收进去。

## 3. 循环依赖：12 处函数内 import

函数体内 import 是规避循环依赖的手段，能跑，但它掩盖了真实的依赖方向。
分包（阶段 E）时这些环会变成硬错误——跨包的循环无法用延迟 import 化解。

| 位置 | 延迟导入的目标 |
|---|---|
| `database.py:27` | `config.MODEL_PROVIDER_DEFAULTS` |
| `governance.py:22` | `semantic_kernel.validate_rule_expression` |
| `governance.py:214` | `release_readiness.assess_ontology_release_readiness` |
| `ontology.py:510` | `vocabulary.blueprint_*_labels` |
| `ontology.py:733` | `semantic_kernel.validate_rule_expression` |
| `vocabulary.py:186`、`199` | `industry_blueprints.list_industry_blueprints` |
| `agent.py:209` | `natural_language.query_natural_language` |
| `api.py:1468` | `workflow_permission.enter_workflow` |
| `auth.py:183`、`agent_roles.py:98`、`workflow_permission.py:421` | `database._{sqlite,postgresql,mysql}_ddl` |

最后三处同时暴露了问题 5：三个模块都要伸手进 `database.py` 拿私有的
DDL 辅助函数，因为它们各自手写建表语句。

## 4. 公私边界缺失

**`agent.py` 从 `natural_language.py` 导入 8 个下划线私有函数：**
`_compact_evidence`、`_compact_json`、`_detect_intent`、`_detect_object_code`、
`_extract_instance_hint`、`_extract_json_object`、`_identifier_columns`、
`_resolve_instance_id`。

框架化前必须建立 `__all__` 与 `_internal/` 边界。否则第三方会依赖
我们并不打算稳定的符号，而我们也无法在不破坏下游的前提下重构内部实现。
这 8 个函数要么提升为公开 API，要么下沉到共享的内部模块。

**前端 `frontend/src/types/index.ts` 手写 889 行镜像后端模型。**
后端同时下发 camelCase 与 snake_case 两份字段
（见 `metadata.py` 的 `DataSource.public_dict()`），前端类型靠手工同步。
应改为从 OpenAPI 生成，并把响应收敛为单一命名风格。

## 5. DDL 分散在 4 个模块

建表语句分散在 `database.py`、`workflow_permission.py`、`auth.py`、
`agent_roles.py`，每个模块各自手写三方言。

后果：每加一张表要写三份 DDL，而三份中任何一份的方言细节写错
（MySQL 的 TEXT 列不能有字面量默认值、PostgreSQL 的 `timestamp` vs
SQLite 的 `text`）只会在对应后端上暴露。

应迁移 Alembic 并按插件归属管理迁移。

## 6. 单体路由：`api.py` 98 个端点

需拆 `APIRouter` 并加 `/v1` 前缀。没有版本前缀意味着一旦有外部调用方，
任何破坏性变更都无处安放。

`api.py:1268` 还有一处模块中段的 import 块（工作流与权限的 20 多个符号），
拆分时应一并整理到文件头部。

## 7. 扩展点硬编码

这四处是「第三方能不能在不改我们代码的前提下扩展」的分水岭。

| 位置 | 现状 | 应为 |
|---|---|---|
| `adapters.py:74` `get_adapter()` | 硬编码 if/elif，三种类型 | 注册表 + entry points |
| `semantic_kernel.py:113` `ALLOWED_RULE_FUNCTIONS` | `frozenset({"sum","len","count","any","all"})` | 可注册，带沙箱审计 |
| `access_policy.py` `RULES` | 模块级静态元组 | 插件可注册路由与能力 |
| `automation.py` 写回执行器 | 只支持 HTTP/HTTPS | 执行器 SPI |

## 8. 事务与连接

**无连接池。** 每次 `connect()` 新建连接。

**跨多次 `connect()` 的多步写入无统一事务边界。**
典型例子是 `governance.publish_ontology()`：先在一个连接里校验前置条件，
退出该连接后评估发布门禁（因为门禁要读活的来源库做漂移检测），
再开一个新连接写入发布状态。中间窗口内状态可变。

目前靠「同一时刻只有一个管理员在做发布」的隐含假设成立。
多租户后这个假设不再成立。

## 已偿还

记录在此以免重复讨论：

- ~~四处扩展点硬编码，第三方必须 fork 才能扩展~~
  → 运行时注册表 + entry points（`registry.py`，ADR-0007）
- ~~复合主键三处 `raise ValueError`，连接表与版本化表无法建模~~
  → 实例键抽象（`instance_key.py`，ADR-0008）
- ~~会话不落库、无反馈闭环，答案对错无法追溯~~
  → `conversations.py`：会话持久化 + 反馈锚定决策记录 + 转人工
- ~~`guard_expression` / `filter_expression` / `depends_on` 有存储但从不求值~~
  → 三者均已真实生效且 fail-closed（`workflow_permission.py`、`semantic_kernel.py`）
- ~~`permission_policy` 缺本体维度，同名对象共享策略~~
  → 按 `(role_id, ontology_id, object_code)` 索引，`0` 为通配以兼容既有部署
- ~~护城河第三段缺失：无文档检索，判定给不出条款依据~~
  → 锚定本体的文档知识层（`knowledge_documents.py`、`retrieval.py`，ADR-0009）
- ~~无值域映射，规则只能写魔法值~~
  → `value_to_state` 走既有审核流程（`value_mapping.py`，ADR-0008）
- ~~`PlatformConnection.__exit__` 委托驱动的上下文管理器，
  pymysql 只关闭不提交，导致 MySQL 上所有写入被回滚~~
  → 适配层自己拥有 commit／rollback／close 决策
- ~~`init_schema` 靠捕获驱动错误文本判断列是否已存在，
  PostgreSQL 上一条失败语句会回滚同事务内所有建表~~
  → `COLUMN_MIGRATIONS` 先查 `information_schema`／`pragma` 再执行 DDL
- ~~`MIGRATION_STATEMENTS` 假定 SQLite 列类型~~
  → `ColumnMigration` 按方言分别声明类型
- ~~魔法数字散落在各模块~~ → 集中到 `config.py`，环境变量可覆盖
