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

格式：Context（处境）／Decision（决定）／Alternatives considered（被否决的方案）／
Consequences（后果，含负面）。
