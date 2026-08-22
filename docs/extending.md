# 扩展 Aletheia

无需 fork 平台即可扩展。四个扩展点已开放为运行时注册表：
数据源适配器、规则函数、路由权限策略、写回执行器。

> ⚠️ **稳定性：全部为实验性。** 1.0 之前签名可能在小版本间变更，
> 变更会记入 [CHANGELOG](../CHANGELOG.md)。理由见
> [ADR-0007](adr/0007-extension-registry-without-api-stability.md)。
>
> 自证合规的方式：对你的实现跑 `tests/test_extension_registry.py`。
> 我们改签名时，这套测试会同时暴露所有受影响的实现点。

两种注册方式：

- **进程内直接注册** —— 在你的应用启动代码里调用 `register_*()`
- **打包为插件** —— 通过 entry points 声明，安装即生效，平台自动发现

---

## 1. 数据源适配器

接入平台尚不支持的数据库（Oracle、SQL Server、达梦、人大金仓等）。

```python
from ontology_platform.adapters import register_adapter

class OracleAdapter:
    def test_connection(self, connection_uri: str) -> dict:
        # 返回 {"sourceType","reachable","status","message"}
        ...

    def scan(self, connection_uri: str) -> list:
        # 返回 SourceTableInfo 列表：表、列、外键
        ...

    def runtime(self, connection_uri: str):
        # 上下文管理器，yield 一个 RuntimeDatabase
        ...

register_adapter("oracle", OracleAdapter, aliases=("ora",))
```

需实现 `DatabaseAdapter` 协议（见 `adapters.py`）。注册传入的是**工厂**
而非实例——适配器构造开销很小，每次调用视为独立对象。

查询已注册项：`supported_source_types()`

## 2. 规则函数

让业务规则表达式能调用领域特定谓词。

```python
from ontology_platform.semantic_kernel import register_rule_function

def days_between(start, end) -> int:
    ...

register_rule_function("days_between", days_between)
# 之后规则可写：days_between(sign_date, today) <= 15
```

**约束与理由：**

- 名称必须是合法标识符且不以下划线开头。沙箱按 `ast.Name` 解析，
  带点的名字永远绑定不上，下划线前缀会与沙箱内部名冲突。
- **注册只授予「可被调用」的权限，不放宽 AST 白名单。** 注册后依然禁止
  dunder 属性访问、lambda、推导式、条件表达式与关键字参数。
- **实现应当是纯函数且不抛异常。** 规则引擎是 fail-closed 的
  （[ADR-0002](adr/0002-rule-engine-fail-closed.md)）：函数抛异常会让
  该规则判为「未通过」，进而阻断作用对象的**所有实例**。
- 注册函数在合并顺序上优先于行数据，因此名为 `sum` 的列不会遮蔽 `sum` 函数。

查询已注册项：`allowed_rule_function_names()`

## 3. 路由权限策略

**如果你的插件新增了 API 端点，必须注册策略。** 否则这些端点会落入
「未登记路由默认仅管理员」的兜底规则，对非管理员用户表现为不可用。

```python
from ontology_platform.access_policy import register_route_policy
from ontology_platform.auth import CAP_READ, CAP_EXECUTE

register_route_policy(["GET"], r"/oracle/tables.*", CAP_READ, "Oracle 表浏览")
register_route_policy(["POST"], r"/oracle/sync", CAP_EXECUTE, "触发同步")
```

路径为正则，自动锚定首尾。插件规则**先于**内置表匹配，未命中的仍会
落到内置表、最后落到管理员兜底——deny-by-default 不因插件而失效。

能力取值：`platform:read`、`platform:write`、`governance:review`、
`governance:publish`、`automation:execute`、`platform:admin`。
传入未知能力会在注册时立即报错。

查询生效策略：`describe_policy()`，每行标注 `builtin` 或 `plugin`。

## 4. 写回执行器

HTTP 之外的写回通道（消息队列、RPC、直写库、存储过程）。

```python
from ontology_platform.automation import ExecutionRequest, register_executor

def publish_to_mq(request: ExecutionRequest) -> dict:
    # request.target / .plan / .timeout_seconds / .headers
    # 返回值会原样写入决策记录的 execution.remote，请包含审计所需信息
    return {"published": True, "messageId": "..."}

register_executor("amqp", publish_to_mq)
```

按数据源 `apiBaseUrl` 的 scheme 分发。返回值进入决策留痕，
因此**应包含审计者需要的信息**。

查询已注册项：`supported_executor_schemes()`

---

## 打包为插件（entry points）

```toml
# 你的插件项目的 pyproject.toml
[project.entry-points."aletheia.adapters"]
oracle = "my_plugin.adapters:OracleAdapter"

[project.entry-points."aletheia.rule_functions"]
days_between = "my_plugin.rules:days_between"

[project.entry-points."aletheia.executors"]
amqp = "my_plugin.channels:publish_to_mq"

[project.entry-points."aletheia.access_policies"]
oracle = "my_plugin.policies:route_policies"
```

`aletheia.access_policies` 的目标应是一个可调用对象，
返回 `(methods, path_regex, capability, description)` 元组序列。

安装后平台在导入时自动发现。**单个插件加载失败只记日志，不阻断平台启动**——
一个坏插件不应让整个系统起不来。

| entry point 组 | 注册目标 |
|---|---|
| `aletheia.adapters` | 数据源适配器工厂 |
| `aletheia.rule_functions` | 规则函数 |
| `aletheia.executors` | 写回执行器 |
| `aletheia.access_policies` | 返回策略元组的可调用对象 |
| `aletheia.retrieval_backends` | 检索后端 |
| `aletheia.embedding_models` | 嵌入模型 |
| `aletheia.instance_resolvers` | 实例解析器 |

## 验证你的实现

```bash
python -m pytest tests/test_extension_registry.py -v
```

这套测试既约束平台自身（开放扩展点后未削弱 deny-by-default 授权、
规则沙箱、fail-closed 语义），也是第三方的合规样板。

## 5. 检索后端与嵌入模型

默认实现为**零外部依赖**（BM25 + 哈希 n-gram），保证 clone 下来就能跑。
追求召回质量的部署可注册自己的后端。

```python
from ontology_platform.retrieval import (
    RetrievalHit, register_retrieval_backend, register_embedding_model,
)

def rank_with_pgvector(query: str, entries, limit: int) -> list[RetrievalHit]:
    # entries 已按本体锚定收窄，后端不能越过锚定扩大候选集——
    # 这正是引用可归因的前提（ADR-0009）。
    ...

register_retrieval_backend("pgvector", rank_with_pgvector)
register_embedding_model("bge-m3", lambda text: my_model.encode(text).tolist())
```

**关键约束：** 后端收到的是**已锚定过滤**的候选集。后端只负责排序，
不能自行扩大候选范围，否则引用会退化为「相似」而非「有据」。

查询已注册项：`supported_retrieval_backends()`、`supported_embedding_models()`

## 6. 多租户上下文

扩展若要访问平台数据，应通过上下文而非硬编码路径，否则在多租户部署下会读到
错误的租户数据。

```python
from ontology_platform.context import use_context
from ontology_platform.tenancy import tenant_context, require_tenant, scope_query

ctx = tenant_context(base_context, "acme")
with use_context(ctx):
    tenant = require_tenant()          # 无法确定租户时抛错，而非猜测
    query, params = scope_query("select * from data_source", ())
    with ctx.connect() as conn:
        rows = conn.execute(query, params).fetchall()
```

**要点：** `require_tenant()` 是 fail-closed 的。若你的扩展在无上下文时也要能跑，
请显式处理 `TenantError`，不要退化为「读所有租户」。

## 7. 实例解析器

决定「哪些行是这个业务对象的实例」。内置四种：`single_table`（默认）、
`joined_tables`、`discriminated`、`custom_sql`。

```python
from ontology_platform.instance_resolver import (
    InstanceResolver, ResolverSpec, register_resolver,
)

class CrossSourceResolver(InstanceResolver):
    kind = "cross_source"

    def validate(self) -> None:
        ...  # 构造时校验配置，避免错误配置在研判时才暴露

    def fetch(self, runtime, instance_id):
        ...  # 返回一条完整记录或 None

    def list_ids(self, runtime, limit=50):
        ...  # 返回的 token 必须能被 fetch() 接受

    def columns(self, runtime):
        ...  # 规则可引用的全部名称

register_resolver("cross_source", CrossSourceResolver)
```

**契约中最易写错的一点：`list_ids()` 与 `fetch()` 必须往返闭合。**
批量研判依赖它——若 `list_ids` 返回了 `fetch` 不接受的 id，批量评估会得到
「实例不存在」而非结论。

对你的实现跑 `tests/test_instance_resolvers.py` 即可验证合规。

### 标识符必须校验，不能只加引号

解析器配置由运维提供并进入 SQL 文本（join 子句、判别列）。
请使用 `validate_identifier()`——**加了引号但未校验的名字进入 join 子句仍是隐患**。

### `custom_sql` 的信任边界

`custom_sql` 执行运维提供的 SQL，**以数据源自身的权限运行**。
平台只做三项限制：必须以 `select`/`with` 开头、不含分号、标识列名经校验。
这是**刻意的信任决定**:接入遗留系统时建议使用只读账号。

## 尚未开放的扩展点

以下在 [ROADMAP](../ROADMAP.md) 中，目前**没有**扩展机制：

- 跨源实例解析（一个对象跨两个数据源）—— 需先做跨源实体消解
- 认证后端（SSO／LDAP）
- 事件钩子
- 渠道接入

这些的形状取决于第二个真实用例，过早冻结会产生错误 API
（[ADR-0001](adr/0001-three-repo-distribution.md) Consequences）。
