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

## 8. 单位与量纲

属性可以声明单位，同量纲比较自动换算。内置单位覆盖货币刻度、时长、
质量、长度与比率——刻意保持小而领域中立，
行业专有单位由部署方注册，理由同 [ADR-0003](adr/0003-no-builtin-domain-vocabulary.md)。

```python
from ontology_platform.derived_attributes import Unit, register_unit

register_unit(Unit(code="jin", name="斤", dimension="mass", to_canonical=500.0))
```

`to_canonical` 是「1 个该单位等于多少个该量纲的规范单位」。
换算统一经规范单位而非两两系数：N 个单位只需 N 个系数而不是 N²，
且只有一处需要核对。

覆盖已有单位必须显式传 `replace=True`——**静默重定义「吨」
会改变所有已存值的含义，且不留任何记录**。

新量纲需要恰好一个 `to_canonical == 1.0` 的单位，否则该量纲无法换算。

### 跨量纲不会被换算

`convert(1, "day", "kilogram")` 抛错而不是返回 1。
这通常意味着建模有误，静默透传数字会让由此得出的判定看起来完全有效。

## 9. 建表：SchemaBundle

插件自带的表通过 `SchemaBundle` 声明，而不是自己写「按方言挑 DDL 再执行」的循环。

```python
from ontology_platform.schema import SchemaBundle

SCHEMA = SchemaBundle(
    name="my_plugin",
    tables=(
        {
            "sqlite": "create table if not exists my_table (id integer primary key, note text not null default '')",
            "postgresql": "create table if not exists my_table (id serial primary key, note text not null default '')",
            "mysql": "create table if not exists my_table (id integer primary key auto_increment, note text)",
        },
    ),
    indexes=(
        {
            "sqlite": "create index if not exists idx_my_table_note on my_table (note)",
            "postgresql": "create index if not exists idx_my_table_note on my_table (note)",
            # MySQL 没有 `create index if not exists`
            "mysql": "create index idx_my_table_note on my_table (note)",
        },
    ),
    table_names=("my_table",),
)
SCHEMA.verify_declared_names()   # 导入时校验声明与 DDL 一致


def init_my_schema(conn):
    SCHEMA.apply(conn)
```

### 为什么表和索引分开声明

两者的失败方式不同：`create table if not exists` 在三方言上都幂等，
而 MySQL 没有 `create index if not exists`，重跑会抛错。
放在一个列表里会迫使每个调用方去嗅探语句文本来判断错误是否预期——
而这正是此前在 8 个模块副本之间漂移掉的那个检查。

### 表存在性用目录探测，不要捕获异常

特性 schema 可选时，用 `SCHEMA.has_tables(conn)` 而不是 `try/except`。
PostgreSQL 上一条失败语句会中止整个事务，
同一连接上后续每条命令都会以 `InFailedSqlTransaction` 失败
（同 [ADR-0004](adr/0004-three-platform-dialects.md)）。

`verify_declared_names()` 防的是另一种错：改了 DDL 却忘改 `table_names`，
会让探测对存在的表报「未配置」，**于是功能静默返回空结果而不是报错**。

## 10. 接一个新的 SQL 数据库

**不需要写适配器。** `information_schema` 是标准，扫描器完全共用；
差异只有 6 个，声明为 `SqlDialect`：

```python
from ontology_platform.generic_sql_adapter import DriverSpec, register_sql_source
from ontology_platform.sql_dialects import SqlDialect, get_dialect, register_dialect

register_dialect(SqlDialect(
    name="gaussdb",
    current_schema_expression="current_schema()",  # 或 database()／sys_context(...)
    quote_open='"', quote_close='"',
    paramstyle="format",                            # format(%s)／qmark(?)／numeric(:1)
    row_limit_style="limit_offset",                 # 或 fetch_first（Oracle／SQL Server／达梦）
    catalog_uppercases_identifiers=False,           # Oracle／达梦 为 True
    foreign_keys_via_referenced_columns=False,      # MySQL 为 True
))

register_sql_source(DriverSpec(
    source_type="gaussdb",
    dialect=get_dialect("gaussdb"),
    module="psycopg2",
    install_hint="GaussDB 接入需要安装 psycopg2。",
    passes_uri_positionally=True,   # 驱动把整个连接串作为第一个位置参数
))
```

这就是全部。它随即获得元数据扫描、列剖析、外键发现、实例解析、
全部规则能力与运行时读取。

### 三个容易踩的点

**`catalog_uppercases_identifiers` 写错的后果是静默的。**
Oracle 与达梦在目录里把未加引号的标识符折成大写，
查 `contracts` 匹配不到任何行——于是表看起来**没有列**，而不是报错。

**分页语法。** 硬编码 `limit n` 在 Oracle／SQL Server／达梦上会失败，
而列剖析会吞掉查询异常，于是每一列都会「剖析为空」而不是抛错。

**连接串的参数名各驱动不同**：psycopg 叫 `conninfo`、oracledb 叫 `dsn`、
sqlite3 是位置参数。猜错会得到 `invalid connection option "dsn"`，
看起来像配置错误而不是声明错误。因此有 `passes_uri_positionally`。

### 内置声明

Oracle／SQL Server／达梦／人大金仓／openGauss 已在
`generic_sql_adapter.BUNDLED_SPECS` 中声明，驱动装上后
`register_bundled_sql_sources()` 即会激活。
`aletheia doctor` 会列出每个的驱动与安装提示。

> ⚠️ 这些声明**未在 CI 中实测**：驱动与客户端库无法在 CI 环境安装。
> 通用路径本身以真实 PostgreSQL 做了「声明式接入一个无专用适配器的库」的实证。

## 11. 数据库写回执行器

这是最危险的扩展点，因此约束最严。

```python
from ontology_platform.db_executors import DatabaseTarget, SqlWriteback, register_database_target

register_database_target(DatabaseTarget(
    scheme="orders",
    connection_uri="postgresql://user:pass@host/orders",
    dialect_name="postgresql",
    driver_module="psycopg2",
    writebacks={
        "approve": SqlWriteback(
            name="approve", kind="update", table="contracts",
            columns=("status",), key_columns=("id",),
            dialect_name="postgresql",
        ),
    },
))
```

此后 `orders://` 成为可用的写回协议，操作路径末段选择写回名。

### 平台会拒绝什么

| 拒绝 | 理由 |
|---|---|
| 无 `keyColumns` 的 update／delete | 缺 WHERE 会改写整张表，而事后从判定记录看不出这一点 |
| 含分号或多语句 | 绕过单语句审计 |
| DDL 与权限语句（drop／alter／grant…） | 自动化用于推进业务状态，不用于变更结构 |
| 未显式 `allowDelete=True` 的删除 | 销毁数据需要单独的授权决定 |
| 缺失的参数值 | 静默变成 NULL 是「更新时把不该动的列清空」的成因 |
| 请求提供的连接串 | 那会让调用方把自动化指向任何可达的数据库 |

**语句由声明提供标识符，由请求提供值，且值一律绑定。**
从操作载荷拼 SQL 会造出一个从 HTTP 请求体可达的注入面。

**影响 0 行默认按失败处理**：UPDATE 匹配到 0 行意味着目标实例不在或条件写错。
确实幂等的写回显式声明 `requireAffectedRows=False`。

## 12. 声明一个 REST 数据源

REST 响应没有可发现的模式，因此字段必须声明——
从一次响应采样出的模式会随响应变化，引用它的判定不可复现。

```python
from ontology_platform.rest_adapter import RestResource, RestSpec, register_rest_source

register_rest_source(RestSpec(
    source_type="crm",
    resources=(
        RestResource(
            name="customers",
            list_path="/api/customers",
            detail_path="/api/customers/{id}",
            primary_key="id",
            fields=("id", "name", "credit_status"),
            field_types={"id": "integer"},
            items_path="data.items",   # 响应被包裹时指明行列表位置
        ),
    ),
))
```

已有 OpenAPI 文档时用 `register_openapi_source(source_type, document)`——
那仍然是声明，只是由 API 的所有者写的。

**未声明的字段不会下发**：声明就是契约，
把响应里的一切透传会让规则可用的名字取决于当下的载荷。

## 13. CSV／REST 源上的一个必然后果

这两类源不推断外键，因此**引用关联对象的规则会 fail-closed**。
例如合同管理蓝图自带的

```
customer.credit_status != 'blacklist'
```

在 CSV 源上会以 `name 'customer' is not defined` 记为「未通过」，
而不是静默通过。

**这是正确行为，不是缺陷。** 规则引用了一个此处不存在的关联，
静默通过等于在未验证的数据上放行（ADR-0002）。

处理方式有三种，按推荐顺序：

1. 声明真实的关系——`describe_file_source()` 会给出外键候选，
   由建模人员确认后建立
2. 把该规则的作用域改到确实有该关联的对象上
3. 给规则设生效期或改用 `guard_expression`，使其只在具备条件时参与判定

`aletheia assess` 会在 `evaluationError` 里写明是哪个名字不存在，
因此这类情形可以被发现，而不是变成一个说不清的判定。

## 14. 验证你的实现：一致性契约

**先跑契约，再上生产。** 契约随包发布，不需要 clone 本仓库、也不需要 pytest：

```bash
aletheia verify --list                                    # 全部契约与对应扩展点
aletheia verify data_source_adapter --source-type mydb --uri "mydb://host/db" --table contracts
aletheia verify retrieval_backend --name pgvector
aletheia verify embedding_model --name my-model
```

失败时退出码为 1，因此可以直接当 CI 门禁用。

需要活的被测对象的契约（实例解析器、写回执行器）在代码中调用：

```python
from ontology_platform.conformance import check_instance_resolver
from ontology_platform.adapters import get_adapter

with get_adapter("sqlite").runtime("/path/to/db.sqlite3") as runtime:
    report = check_instance_resolver(MyResolver(spec), runtime, subject="my_resolver")

print(report.summary())
report.raise_for_failures()   # 抛 ConformanceError（继承 AssertionError），可直接用在测试里
```

### 契约检查的是什么

**只检查内核真正依赖的属性。** 每一项都对应一个具体的错误后果，
失败信息会把后果一起说出来——不该让实现者去猜某条规则为什么重要。

| 契约 | 检查项数 | 最容易写错的一项 |
|---|:--:|---|
| `instance_resolver` | 9 | `list_ids()` 的 token 必须能被自己的 `fetch()` 接受 |
| `data_source_adapter` | 9 | `fetch_primary_keys()` 给出的键必须能被 `fetch_one()` 取回 |
| `retrieval_backend` | 6 | 不得返回候选集之外的条目 |
| `embedding_model` | 4 | 同一输入必须返回同一向量 |
| `writeback_executor` | 3 | 结果必须表明写回效果 |

### 为什么往返闭合被单独强调

适配器上真正会发生的 bug 不是崩溃，而是**不对称**：

`list_ids()` 发出的 token 自己的 `fetch()` 不接受——这能通过实现者想得到的每一个单元测试，
然后在批量研判时**静默地什么都不返回**，而单实例研判看起来完全正常。
这类失败最难定位，因此契约把每一对往返都显式检查。

### 必需项与建议项

`required` 失败意味着**正常运行下会产出错误结果**；
`advisory` 意味着能用但少了一项能力（例如非表数据源无法报告 `tables()`，
于是漂移检测覆盖不到它）。
两者刻意区分：混在一起会让报告无法用于「能不能上线」的判断。

### 契约不是 API 稳定承诺

注册表仍是实验性的（[ADR-0007](adr/0007-extension-registry-without-api-stability.md)）。
稳定的是**被要求的行为**，不是要求它的函数签名。

> 内核自身的全部实现（4 种解析器、SQLite／CSV 适配器、BM25／嵌入检索后端、
> 数据库写回执行器）都在 CI 中跑同一套契约。
> 只对作者自己的例子成立的契约会漂移成「要求平台自己都不做的事」，
> 那样第一个跑它的集成方拿到的失败是我们造成的。

## 尚未开放的扩展点

以下在 [ROADMAP](../ROADMAP.md) 中，目前**没有**扩展机制：

- 跨源实例解析（一个对象跨两个数据源）—— 需先回答「两个源里哪两行是同一个业务实例」，
  且该判断本身必须可核验，否则跨源判定无法解释
- 认证后端（SSO／LDAP）
- 事件钩子
- 渠道接入
- 关系分类策略（目前是固定的结构化规则，见
  [ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md)）
- 聚合函数（`sum`／`count`／`min`／`max`／`avg`，需要窗口函数请改用
  `custom_sql` 解析器）

> **事件钩子刻意不开放。** 事件是记录而非触发器：能触发自动化的事件
> 会让回放历史重新执行业务动作。需要「事件驱动动作」请走
> `automation.py` 的写回执行器，由决策驱动
> （[ADR-0014](adr/0014-type-hierarchy-and-business-events.md)）。

这些的形状取决于第二个真实用例，过早冻结会产生错误 API
（[ADR-0001](adr/0001-three-repo-distribution.md) Consequences）。
