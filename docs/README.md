# Documentation

English · [简体中文](#文档)

Start with the [README](../README.md). This tree holds the depth the entry point links to.

| Page | Contents |
|---|---|
| [Quick start](quickstart.md) | Install, onboard a system, export standard vocabulary |
| [Core concepts](concepts.md) | Ontology structure, legacy mapping, the verdict trail |
| [Architecture](architecture.md) | Layers, data flow, and the three invariants behind them |
| [Capability matrix](capabilities.md) | Per-item implementation status and location |
| [Current limitations](limitations.md) | What it cannot do, and why that is design |
| [Design decisions](design-decisions.md) | Key trade-offs, each covered by a test |
| [Configuration](configuration.md) | Every environment variable |
| [Self-hosted deployment](deployment.md) | Images, orchestration, preflight |
| [Roles and capabilities](roles.md) | Six capabilities across six roles |
| [Extension guide](extending.md) | Data sources, rule functions, retrieval backends, writeback |
| [Model endpoints](model-endpoints.md) | Azure OpenAI, vLLM, gateways |
| [Tests](testing.md) | Distribution, static checks, why assertions are shaped that way |
| [Screenshots](screenshots.md) | Ten screens, each captioned with what it proves |
| [ADRs](adr/) | Architecture decisions, including rejected alternatives |
| [Architecture debt](architecture-debt.md) | Remaining technical debt, located |

## Design documents

`01`–`04` record design intent, not a checklist of delivered capability. They are kept
because the reasoning is still useful, and because the gap between intent and implementation
is itself worth being able to see.

| Document | Contents | Gap vs implementation |
|---|---|---|
| [01 Overall architecture](01-总体架构.md) | Layers, component responsibilities, the onboarding loop | Broadly matches; [architecture.md](architecture.md) is current |
| [02 Core metamodel](02-核心元模型设计.md) | Objects, attributes, relations, events, states, rules | ✅ All implemented: events (`events.py`), relation cardinality (`relations.py`), type hierarchy (`type_hierarchy.py`), axioms (`axioms.py`) |
| [03 MVP scope and roadmap](03-MVP功能范围与开发路线图.md) | Early scope and plan | Superseded by [ROADMAP.md](../ROADMAP.md); kept as history |
| [04 Semantic kernel and model layer](04-通用语义内核与OpenRouter模型层.md) | Model adapter design | Matches; falls back to a local heuristic with no API key |

> **To judge whether a capability is available, use the
> [capability matrix](capabilities.md) and [limitations](limitations.md).** Those two are
> asserted by tests and cannot drift from the code; a design document can.

---

# 文档

[English](#documentation) · 简体中文

先读 [README](../README.zh-CN.md)。这里放的是入口页链接过去的深度内容。

| 页面 | 内容 |
|---|---|
| [快速开始](quickstart.zh-CN.md) | 安装、接入自己的系统、导出标准词汇 |
| [核心概念](concepts.zh-CN.md) | 本体结构、与遗留系统的对应、判定与留痕 |
| [架构](architecture.zh-CN.md) | 分层、数据流，以及背后的三条不变量 |
| [能力矩阵](capabilities.zh-CN.md) | 逐项实现状态与位置 |
| [当前限制](limitations.zh-CN.md) | 做不到什么，以及为什么那是设计 |
| [设计决策](design-decisions.zh-CN.md) | 关键取舍，均有测试覆盖 |
| [配置](configuration.zh-CN.md) | 全部环境变量 |
| [私有化部署](deployment.zh-CN.md) | 镜像、编排、部署前自检 |
| [扩展指南](extending.md) | 数据源、规则函数、检索后端、写回执行器 |
| [接入自定义模型服务](model-endpoints.md) | Azure OpenAI、vLLM、中转网关 |
| [测试](testing.zh-CN.md) | 分布、静态检查，以及为什么这样断言 |
| [界面与产出](screenshots.zh-CN.md) | 十张截图，每张说明它证明了什么 |
| [ADR](adr/) | 架构决策记录，含被否决方案 |
| [架构债](architecture-debt.md) | 前置技术债逐项定位 |

## 设计文档

`01`–`04` 记录设计意图，而非已交付能力清单。保留它们是因为其中的推理仍有价值，
也因为「意图与实现之间的差距」本身值得被看见。

| 文档 | 内容 | 与实现的差距 |
|---|---|---|
| [01 总体架构](01-总体架构.md) | 分层架构、组件职责、接入闭环 | 大体对应；最新版见 [architecture.zh-CN.md](architecture.zh-CN.md) |
| [02 核心元模型设计](02-核心元模型设计.md) | 对象、属性、关系、事件、状态、规则 | ✅ 已全部实现：事件（`events.py`）、关系基数（`relations.py`）、类型层级（`type_hierarchy.py`）、公理（`axioms.py`） |
| [03 MVP 功能范围与开发路线图](03-MVP功能范围与开发路线图.md) | 早期范围与路线 | 已被 [ROADMAP.md](../ROADMAP.md) 取代，保留作历史记录 |
| [04 通用语义内核与模型层](04-通用语义内核与OpenRouter模型层.md) | 模型适配层设计 | 对应现状；未配置密钥时回退本地启发式 |

> **判断某项能力是否可用，请以[能力矩阵](capabilities.zh-CN.md)与
> [当前限制](limitations.zh-CN.md)为准。** 那两处由测试守着，不会与代码漂移；
> 设计文档会。
