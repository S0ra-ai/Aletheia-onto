<div align="center">

# Aletheia

**为传统业务系统安装可核验的业务语义内核。**

把埋在表结构里的业务语义变成可治理的领域本体，
并让每个判定都能回答**「凭什么」**。

[![CI](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml/badge.svg)](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1348%20passing-brightgreen.svg)](docs/testing.zh-CN.md)

[English](README.md) · 简体中文

</div>

---

## 为什么需要它

通用 RAG 框架优化的是「检索到的内容**像不像**答案」。
Aletheia 优化的是**「答案能不能被追问」**。

对权益、金额、合规、审批这类判定场景，一个「看起来对」的回答没有价值——
因为没有人能为它签字。所以每个判定必须同时给出四样东西：

| | 来源 |
|---|---|
| **结论** —— 订单 A123 不满足退款条件 | 规则引擎 |
| **依据规则** —— `refund_window_check` | 业务规则定义 |
| **证据链** —— 签收日期 2026-07-28，距今 24 天，超过 15 天窗口 | 结构化查询 |
| **决策记录** —— 落库的 `decision_record`，可审计、可复核、可追责 | 决策留痕 |

```
「订单 A123 不满足退款条件，因签收已超 15 天（规则 refund_window_check），
 依据《售后政策》第 3.2 条。」
```

「超 15 天」来自结构化查询，「不满足」来自规则引擎，「第 3.2 条」来自文档检索——
且那一条必须先锚定到具体规则、经审核确认，才可被引用。

**与 Dify／FastGPT／LangChain 的差别不在检索精度，而在结论的可追问性。**
检索精度是明确的 Non-Goal。

<div align="center">

![语义问答与判定依据](docs/images/01-semantic-qa-with-evidence.png)

*一次判定：结论、识别意图、置信度、建议动作与语义证据。*

</div>

## 快速开始

```bash
pip install aletheia-onto     # 内核零第三方依赖
aletheia demo                 # 接入 → 建模 → 判定，一条命令跑通
```

```json
{ "ontologyId": 1, "objectCode": "contract", "decision": "approved" }
```

接你自己的系统：

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain 合同管理
aletheia model 1                  # 扫描元数据，生成本体草案
aletheia assess 1 contract 1      # 对一个实例产出可核验的判定
```

用脚手架起一个依赖平台的项目——**不是 fork**，升级即 `pip install -U aletheia-onto`：

```bash
aletheia new --list-extensions
aletheia new mycorp --extension rule-function --domain 合同管理
cd mycorp && pip install -e . && python -m mycorp init
```

→ **[完整快速开始](docs/quickstart.zh-CN.md)** · [配置](docs/configuration.zh-CN.md)

## 你会得到什么

| | |
|---|---|
| 🔍 **元数据接入** | 扫描任意 SQL 库、CSV 目录或 REST／OpenAPI 服务。Oracle、SQL Server、达梦、人大金仓、openGauss 已内置声明——接一个未内置的 SQL 库只需 4 行声明，不必写适配器。 |
| 🧩 **闭合的元模型** | 实体类型、数据属性、对象属性、**公理**、规则——GB/T 48000.3—2026 的五大组件。另有子类型层级、跨对象聚合、带单位的派生属性、业务事件、属性级时态生效期。 |
| ⚖️ **fail-closed 规则引擎** | AST 白名单沙箱。表达式无法求值时判为**未通过**，绝不跳过——字段改名不该静默让阻断级规则失效。 |
| 📋 **治理门禁** | 存在待审映射时拒绝发布，且 `--force` **也不能**跳过。违反公理会阻断发布：一个自相矛盾的模型产出的每个判定都可疑。 |
| 🔗 **标准词汇** | 导出 OWL/RDFS 与 SHACL，外部工具能**解释**而非仅能解析——外部 SPARQL 查询可回答「哪个类能关联到哪个类」。 |
| 🔐 **多租户与 SSO** | 独立 schema + `tenant_id` 双保险、租户改不了的配额、JWT SSO——未映射的身份得到**零权限**而非默认角色。 |
| 🛡️ **部署前自检** | `aletheia preflight` 拦的是静默误配：残留的认证开关、CORS 通配、SQLite 配多工作进程。`serve` 拒绝在不安全配置下对外暴露。 |
| 🧾 **审计报表** | 本期**从未触发**的已发布规则、覆盖了门禁的发布、以及本期究竟有多少判定是可复核的。 |

→ **[完整能力矩阵](docs/capabilities.zh-CN.md)** · [当前限制](docs/limitations.zh-CN.md)

## 我想做什么

| 我想…… | 去这里 |
|---|---|
| 先看它能产出什么 | [界面与产出](docs/screenshots.zh-CN.md) |
| 装上并跑通一遍 | [快速开始](docs/quickstart.zh-CN.md) |
| 知道它到底做到了哪一步 | [能力矩阵](docs/capabilities.zh-CN.md) · [当前限制](docs/limitations.zh-CN.md) |
| 理解这个模型 | [核心概念](docs/concepts.zh-CN.md) · [架构](docs/architecture.zh-CN.md) |
| 接一个平台不支持的库／规则函数／检索后端 | [扩展指南](docs/extending.md) |
| 接 Azure OpenAI、vLLM 或中转网关 | [接入自定义模型服务](docs/model-endpoints.md) |
| 上生产 | [私有化部署](docs/deployment.zh-CN.md) |
| 理解某个设计为什么是这样 | [设计决策](docs/design-decisions.zh-CN.md) · [ADR 全集](docs/adr/) |
| 核对 GB/T 48000.3—2026 对标情况 | [ADR-0019](docs/adr/0019-axioms-and-standard-vocabulary.md) |
| 参与贡献 | [CONTRIBUTING](CONTRIBUTING.md) · [ROADMAP](ROADMAP.md) |

## 明确不做

写清楚这些比列功能更能建立信任。

| 不做 | 理由 |
|---|---|
| 完整 OWL/DL 推理、开放世界假设 | 与可核验性对立——由包含推理得出的结论无法回溯到某个人做过的声明（[ADR-0005](docs/adr/0005-semantic-generality-ceiling.md)） |
| 通用图数据库／任意三元组存储 | 无法保证每个结论都有可解释来源 |
| 自动改写传统系统代码 | 风险不可控，且不是语义内核的职责 |
| 通用 ETL／数据集成平台 | 我们读元数据，不做数据搬运 |
| 通用拖拽式工作流引擎 | 工作流只服务于本体实例的状态流转 |
| 追求检索精度 SOTA | 差异化在可追问，不在召回率 |

## 项目状态

1348 个测试，在 Python 3.11／3.12／3.13 上全绿。内核**零第三方依赖**——
由 CI 在裸装环境校验，因此本体、规则引擎与决策留痕可以嵌入别人的应用。

本文档里每一个可数的声明都由测试守着：测试总数、分布表、端点数、支持的 Python 版本，
以及「这里没有失效链接」这件事本身。**一个无法核验的数字比没有数字更糟。**

**稳定性：** 1.0 之前扩展点为实验性；一致性契约要求的**行为**是稳定的，
它的 Python 签名不是（[ADR-0007](docs/adr/0007-extension-registry-without-api-stability.md)）。

## 关于这个名字

Aletheia（ἀλήθεια）是古希腊语的「真理」，亦为真理女神之名。它的字面义是
**「去蔽」——使被隐藏之物显现**。业务语义被掩埋在表名、字段与外键中，
Aletheia 把它揭示为可治理的领域本体。

神话中它的对立面是 Pseudologoi（谎言之灵）——看似合理却无法核验的言说。
这正是本项目要解决的问题。

## 许可证

[Apache-2.0](LICENSE)
