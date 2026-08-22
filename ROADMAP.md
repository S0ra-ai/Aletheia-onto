# ROADMAP

**当前状态：内核元模型已闭合，包可安装，CLI 可用。**
本文件描述方向，不描述已实现的能力。已实现能力见
[README 能力矩阵](README.md#能力矩阵)，未实现项见
[当前限制](README.md#当前限制)。

## 目标形态：库 + 官方脚手架 + 代码生成器

纯库上手门槛高，纯脚手架无法平滑升级。三仓库同时满足「能升级」与「开箱可用」：

| 仓库 | 角色 | 用户如何对待 |
|---|---|---|
| `Aletheia-onto` | 内核库 | 依赖，pip 升级，不改 |
| `aletheia-scaffold` | 官方脚手架 | fork，随便改 |
| `aletheia-cli` | 脚手架与代码生成器 | 当工具用 |

完整取舍与被否决方案见
[ADR-0001](docs/adr/0001-three-repo-distribution.md)。

**当前已发布形态：单包 `aletheia-onto` + optional extras。**

```
pip install aletheia-onto            # 内核，零第三方依赖
pip install 'aletheia-onto[web]'     # + FastAPI 层
pip install 'aletheia-onto[all]'     # + PostgreSQL／MySQL／文档解析
```

extras 承载了未来分包的接缝，但不预先冻结边界：只装内核的用户，
日后迁到 `aletheia-core` 不需要改 import。

规划中的 PyPI 分包：`aletheia-core`（本体、规则、决策）、
`aletheia-web`（FastAPI 层）、`aletheia-admin`（管理界面）、
`aletheia-starter-*`（按场景预置的组合包）。

> 🚧 **分包本身仍延后**，阻塞于 SPI 形状（阶段 D 需要第二个真实用例）。
> **现在不会创建空的分包目录或占位模块**——提前建目录只会产生需要推倒的结构。

## 框架化阶段

### 阶段 A 垂直切片

单租户跑通端到端知识问答：文档摄取与检索、会话持久化、意图路由、
带引用的答案合成、反馈闭环。

**进度：阶段 A 已全部完成。** 文档摄取与检索、意图路由、带引用的答案合成
（ADR-0009，`knowledge_documents.py` / `retrieval.py`），会话持久化与反馈闭环
（`conversations.py`）。单租户端到端垂直切片已闭合。

**先窄后宽。** 先用一个真实客服场景验证护城河成立，再抽框架。
文档检索必须锚定到本体对象，不做成独立的 RAG 模块——否则就退化成
Dify 的同类产品，失去差异化。

知识条目沿用现有治理流程（`pending`／`confirmed` + 发布门禁），不自动上线。

### 阶段 B 隔离模型

多租户落地，贯穿全表，检索期权限过滤，并修掉
`permission_policy` 缺本体维度的已知缺陷。

> ✅ **已实现**（`tenancy.py`）：schema 路由已接入三方言适配器，
> 关键表带 `tenant_id`，跨租户访问会被拦截。已在真实 MySQL 与 PostgreSQL 上
> 验证「A 租户看不到 B 租户数据」。
> 🚧 **仍待完成**：检索期权限过滤与租户级配额尚未实现。

### 阶段 C 依赖倒置

上下文对象替代全局单例、消除 `platform_db` 满签名传递、拆解循环依赖、
公私 API 分离。

**进度：** 上下文对象已落地（[ADR-0010](docs/adr/0010-platform-context-replaces-global-singleton.md)），
全局单例已移除，**阶段 B 的硬前置已解除**。

✅ **循环依赖已清零。** 19 处函数内 import 提升到顶层；规则沙箱抽为
`rule_sandbox.py`，解开 `ontology ↔ semantic_kernel`。唯一保留的环是
`context ↔ database`（必然同包）。
✅ **公私边界已建立。** 跨模块私有引用清零，关键模块声明 `__all__`。
✅ **DDL 调度已统一**到 `schema.SchemaBundle`，8 处重复实现合并为一处。

两项不变量由 `tests/test_module_boundaries.py` 守住——
只靠文档记录的约束会一次一个「顺手的延迟 import」地退化。

🚧 仍待完成：172 处 `platform_db` 签名迁移、DDL 迁 Alembic（依赖分包边界）。

逐项工作清单见 [docs/architecture-debt.md](docs/architecture-debt.md)。

### 阶段 D 抽取 SPI

从**两个**真实用例反推扩展点：数据库适配器、检索后端、嵌入模型、
模型供应商、认证后端、写回执行器、渠道、事件钩子。

> 🚧 **阻塞于：缺少第二个真实用例。**
> 仅凭一个用例反推的 SPI 会把该用例的偶然特征固化成 API。
> 在此之前可以建内部注册表机制，但不对外承诺 API 稳定性。

### 阶段 E 分包发版

✅ **已完成：可安装、可版本化。**
`pyproject` 声明分发元数据与 optional extras、`py.typed`（PEP 561）、
`/v1` 前缀（裸路径与版本路径共用同一套鉴权中间件与权限策略）、
entry points 自动发现（`registry.py`）。
CI 会构建 wheel、在干净环境裸装、校验内核零第三方依赖并跑通完整闭环。

🚧 仍待完成：拆成多个分发包、Alembic 迁移按插件归属、OpenAPI 生成前端类型。
前两项阻塞于 SPI 形状（阶段 D）。

### 阶段 F 脚手架与生成器

✅ **CLI 已完成**（`cli.py`）：`init` / `connect` / `model` / `assess` /
`publish` / `demo` / `serve` / `doctor`。
`publish` 受发布门禁约束，且**待审核映射无法用 `--force` 跳过**。

🚧 仍待完成：scaffold 仓库、代码生成器。

### 阶段 G 交付配套

私有化部署、SSO、审计报表、问答回归测试集、中文文档。

## 通用性路线

目标：让 `business_object` 从「表的镜像」变成真正的语义对象。

通用性靠「**结构表达力 + 逃生舱**」实现，不靠推理能力
（理由见 [ADR-0005](docs/adr/0005-semantic-generality-ceiling.md)）。

按性价比排序：

| # | 项 | 成本 | 说明 |
|--:|---|:--:|---|
| 1 | ~~对象↔单表解耦：实例解析器 SPI~~ | — | ✅ **已完成**：单表／主从 join／判别列分区／自定义 SQL 四种内置 + 可注册（ADR-0011）。跨源解析仍待跨源实体消解 |
| 2 | ~~复合主键 → 实例键抽象~~ | — | ✅ **已完成**：`instance_key.py`，三处 `raise` 已移除（ADR-0008） |
| 3 | ~~值域映射 `value_to_state`~~ | — | ✅ **已完成**：`value_mapping.py`，走既有审核流程（ADR-0008） |
| 4 | ~~关系表达力~~ | — | ✅ **已完成**：基数 + 强弱 + 中间表折叠多对多，结构化推断（`relations.py`，ADR-0012） |
| 5 | ~~跨对象规则与聚合~~ | — | ✅ **已完成**：声明式具名聚合，fail-closed 且带行数上限（`aggregation.py`，ADR-0012） |
| 6 | ~~类型层级（继承／子类型）~~ | — | ✅ **已完成**：沿声明链确定性展开，覆盖需显式声明（`type_hierarchy.py`，ADR-0014） |
| 7 | ~~派生属性（计算字段）~~ | — | ✅ **已完成**：复用规则沙箱，多趟求值（`derived_attributes.py`，ADR-0013） |
| 8 | 时态与生效期 | 高 | 可能需独立设计 |
| 9 | ~~Event／State 一等公民~~ | — | ✅ **已完成**：只追加事件流 + 状态流转镜像为统一时间线（`events.py`，ADR-0014） |
| 10 | ~~单位与量纲~~ | — | ✅ **已完成**：同量纲换算、跨量纲拒绝（`derived_attributes.py`，ADR-0013） |
| 11 | 规则函数可注册 | 低 | 解除 `ALLOWED_RULE_FUNCTIONS` 冻结 |

> #11 与数据源／写回执行器／路由策略的可注册性已完成，见
> [扩展指南](docs/extending.md) 与 [ADR-0007](docs/adr/0007-extension-registry-without-api-stability.md)。
| 12 | 数据源扩展 | — | Oracle／SQL Server／达梦／人大金仓／REST／文件／MQ。B 端刚需 |
| 13 | 写回执行器扩展 | 中 | MQ／RPC／直写库／存储过程 |

> **元模型已闭合。** `docs/02-核心元模型设计.md` 画出的对象、属性、关系、
> Event、State、Rule、Mapping 现已全部有实现。
>
> 🚧 **剩余 #8、#12 与「跨源」阻塞于跨源实体消解与连接管理**：
> 时态存储与新数据源都要先确定跨源实例如何对齐。

### 逃生舱

当结构表达力不够时，允许用户下沉到自定义实现，而不是等我们加功能：

- 自定义 SQL 或视图作对象来源
- 自定义规则函数
- 派生属性表达式
- 写回执行器 SPI
- 数据源适配器 SPI
- 检索后端与嵌入模型 SPI

## Non-Goals

明确不做。这比功能清单更能建立信任。

| 不做 | 理由 |
|---|---|
| 完整 OWL/DL 推理与开放世界假设 | 与可核验性对立，见 ADR-0005 |
| 通用图数据库／任意三元组存储 | 无法保证每个结论都有可解释来源 |
| 自动改写传统系统代码 | 风险不可控，且不是语义内核的职责 |
| 通用 ETL／数据集成平台 | 我们读元数据，不做数据搬运 |
| 通用拖拽式工作流引擎 | 工作流只服务于本体实例的状态流转 |
| 追求检索精度 SOTA | 差异化在可追问，不在检索精度 |

## 待决问题

1. **隔离模型**：共享库带 `tenant_id` ／ 独立 schema ／ 独立库？
   建议独立 schema 起步 + 关键表带 `tenant_id` 双保险。
   阻塞阶段 B 与通用性 #1／#8／#12。
2. **SPI 形状**：需要第二个真实用例才能确定。阻塞阶段 D。
