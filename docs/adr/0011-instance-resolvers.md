# ADR-0011 实例解析器：对象不再是表的镜像

- 状态：Accepted
- 日期：2026-08-23

## Context

`business_object.source_table_id` 是单个外键，因此一个业务对象只能镜像一张表。
这是 ROADMAP 通用性 #1，也是**其他通用性项的地基**——正是这个假设让下列建模无法表达：

| 真实场景 | 为何做不到 |
|---|---|
| 订单 = `order` + `order_line` | 一个对象绑不了两张表 |
| `party` 表按 `party_type` 分出客户与供应商 | 两个对象会解析到全部行 |
| 对象的真实定义是一个视图或手写查询 | 只能指向物理表 |
| 对象跨两个数据源 | 单外键无法跨源 |

第二项后果最严重：**作用于客户的规则会静默地对供应商求值**——那是错误判定，
不只是建模不便。

## Decision

把「哪些行是这个对象的实例」变成可替换策略。四种内置解析器：

| kind | 用途 |
|---|---|
| `single_table` | **默认**，行为与此前逐字节一致 |
| `joined_tables` | 主从表，子行按子表名挂载 |
| `discriminated` | 一张物理表按判别列分区 |
| `custom_sql` | 视图或手写查询（ADR-0005 的逃生舱） |

### 配置是数据，不是代码

`ResolverSpec` 以 JSON 存在 `business_object.resolver_spec`。理由：只以 Python
callable 存在的解析器**无法被审阅、版本化,也无法随语义资产导出**。

### 向后兼容是硬要求

`resolver_spec` 为空即为单表，行为不变。这不是体贴，而是必需——这些代码路径产出
合规判定，静默改变解析方式等于静默改变结论。

### 标识符校验而非转义

解析器配置由运维提供并进入 SQL 文本（join 子句、判别列）。**加了引号但未校验的
名字进入 join 子句仍是隐患**，因此 `validate_identifier()` 直接拒绝非法标识符。
`custom_sql` 额外要求以 `select`/`with` 开头且不含分号。

### 一致性契约

任何实现（含第三方）必须满足 `tests/test_instance_resolvers.py`：

1. `fetch()` 返回一条完整记录或 None
2. **`list_ids()` 返回的 token 必须能被 `fetch()` 接受**——往返闭合是批量研判
   得以工作的前提，也是最容易写错的一点
3. `columns()` 报告规则可引用的全部名称
4. 配置中的标识符经校验，绝不盲目插值

## Alternatives considered

**在 `business_object` 上加 `source_table_id_2`。** 拒绝理由：只解决主从一种情形，
且第三张表又要加一列。

**要求所有多表对象都建数据库视图。** 拒绝理由：把建模负担推给 DBA，
且许多部署对遗留库没有建视图权限。`custom_sql` 保留这条路作为可选项而非唯一路径。

**解析器作为 Python 插件而非声明式配置。** 部分保留：注册表允许第三方注册新 kind
（`register_resolver`），但**内置四种的配置仍是数据**，以保持可审阅与可导出。

## Consequences

正面：主从表、判别列分区、视图支撑的对象、以及第三方自定义解析策略均可表达。
通用性 #4（关系基数）、#5（跨对象聚合）的地基就位。

负面：`business_object` 多了一个可能与 `source_table_id` 不一致的配置来源。
`get_object_resolver()` 明确报告 `configured` 字段以便区分。

负面：`custom_sql` 运行运维提供的 SQL，以数据源自身权限执行。**这是刻意的信任决定**，
已在 `docs/extending.md` 写明，而非当作疏漏。

### 实现过程中发现并修复的真实缺陷

解析器挂载的子行是普通 `list`，而规则以属性方式访问（`sum(order_line.amount)`），
导致 `'list' object has no attribute 'amount'`。**由于求值 fail-closed，
这个错误表现为阻断级违规**——一个接线细节变成了错误判定，正是 ADR-0002 要防的形态。
已在 `_wrap_resolver_children()` 统一包装，并加回归测试固定。

**仍未实现：**

- **跨源解析器**（一个对象跨两个数据源）——需要跨源实体消解，仍是 📋
- `source_table_id` 列**仍然存在**：`single_table` 与漂移检测都在用它，
  移除它需要先迁移这 66 处引用
