# 架构决策记录（ADR）

每份 ADR 记录一个有取舍的决定：当时的处境、决定内容、被否决的方案，以及后果。
已接受的决定不再修改；改变主意时新增一份 ADR 并把旧的标记为 Superseded。

| 编号 | 标题 | 状态 |
|---|---|---|
| [0001](0001-three-repo-distribution.md) | 采用「库 + 脚手架 + 代码生成器」三仓库分发模型 | Accepted |
| [0002](0002-rule-engine-fail-closed.md) | 规则引擎采用 fail-closed 语义 | Accepted |
| [0003](0003-no-builtin-domain-vocabulary.md) | 领域词汇不内置，运行时从本体与蓝图派生 | Accepted |
| [0004](0004-three-platform-dialects.md) | 平台库支持三方言，SQL 差异由适配层吸收 | Accepted |
| [0005](0005-semantic-generality-ceiling.md) | 语义通用性封顶：不做完整 OWL/DL 推理 | Accepted |
| [0006](0006-tenant-isolation-model.md) | 多租户隔离：独立 schema + 关键表 tenant_id | Accepted |
| [0007](0007-extension-registry-without-api-stability.md) | 先开放扩展点，暂不承诺 API 稳定 | Accepted |
| [0008](0008-instance-key-and-value-mapping.md) | 实例键抽象与值域映射 | Accepted |
| [0009](0009-document-knowledge-anchored-to-ontology.md) | 文档知识层锚定本体，不做独立 RAG | Accepted |
| [0010](0010-platform-context-replaces-global-singleton.md) | 上下文对象取代全局单例 | Accepted |
| [0011](0011-instance-resolvers.md) | 实例解析器：对象不再是表的镜像 | Accepted |
| [0012](0012-cross-object-aggregation-and-relation-semantics.md) | 跨对象聚合与关系语义 | Accepted |
| [0013](0013-derived-attributes-and-units.md) | 派生属性与单位量纲 | Accepted |
| [0014](0014-type-hierarchy-and-business-events.md) | 类型层级与业务事件 | Accepted |
| [0015](0015-open-data-sources-and-temporal-validity.md) | 数据源与写回通道开放，以及时态生效期 | Accepted |
| [0016](0016-shipped-conformance-suites.md) | 一致性契约随包发布 | Accepted |
| [0017](0017-deployment-preflight.md) | 部署前自检与私有化部署形态 | Accepted |

格式：Context（处境）／Decision（决定）／Alternatives considered（被否决的方案）／
Consequences（后果，含负面）。
