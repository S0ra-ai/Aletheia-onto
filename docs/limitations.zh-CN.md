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


## 结构性表达力约束

设计上的封顶，不是 bug，构成下一阶段的改造对象：

| 约束 | 位置 |
|---|---|
| **跨源匹配在内存中进行**：逐行读副源后比对，有行数上限；副源匹配列无索引时会慢 | `entity_resolution.py` |
| **跨源不做传递推导**：A↔B、B↔C 不会自动得出 A↔C——那会引入一条没人声明过的对应关系 | `entity_resolution.py` |
| **时态只覆盖平台观测到的区间**：原地覆盖值的源系统丢掉的历史无法重建。`coverage` 会明确上报可回答区间 | `temporal.py` |
| **聚合在 Python 内计算**，不下推 SQL。换来三方言行为一致，代价是行数上限 | `aggregation.py` |
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

- **无连接池**；跨多次 `connect()` 的多步写入无统一事务边界。
- **`platform_db` 签名已全部改为 `PlatformDb`**（上下文／路径／字符串三者皆可）。
  此前标注写 `Path | str` 而运行时接受 context——**那比不标注更糟：它让类型检查器
  拒绝本来可用的代码**，于是多租户与嵌入被文档声称支持、却对任何跑 mypy 的下游不可达。
- HTTP 层共 149 个端点，**已开始拆分 APIRouter**（`routers/`）：
  工作流／权限／工具已外移，`api.py` 内仍留 113 个，按关注点继续外移是后续工作。
  共享运行时下沉到 `http_runtime.py`，避免 `api ↔ routers` 成环。
- 前端 `types/index.ts` **手写** 1143 行镜像后端模型；后端存在 camelCase／snake_case 双发。
  平台自身的类型尚不能由 OpenAPI 生成：149 个端点均返回 `dict[str, object]`，
  响应 schema 是裸 object，生成器只会产出 `unknown`。
  **但用户本体的类型已可生成**（`aletheia codegen`），且那才是手写做不对的部分。
  **请求侧的一致性已由测试守住**——
  该测试发现了一处真实缺陷：前端一直在发送 4 个模型兼容性字段，
  而 API 请求模型未声明它们，Pydantic 静默丢弃，于是 Azure 与本地 vLLM 配不上而界面报成功。
- **版本化迁移已具备**（`migrations.py`）：账本记录已应用版本，改列／回填／删表这类
  非幂等变更现在有处可去。**不采用 Alembic**——它依赖 SQLAlchemy，与内核零依赖冲突；
  而它真正提供的（版本账本 + 有序应用）只需 150 行，且自动生成在此不可用
  （DDL 是按方言声明的字符串，无模型元数据可 diff）。
- **尚未拆分为多个 PyPI 分发包**。当前是单包 `aletheia-onto` + optional extras，
  extras 承载了未来分包的接缝但不冻结边界。

架构层面的前置技术债逐项定位见 [`docs/architecture-debt.md`](architecture-debt.md)。
路线与阻塞条件见 [`ROADMAP.md`](../ROADMAP.md)。
