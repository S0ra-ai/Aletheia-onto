# Aletheia

> 让埋在表结构里的业务语义显形，并让每个判定都可核验。

[![CI](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml/badge.svg)](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

[English](README.en.md) | 简体中文

Aletheia（ἀλήθεια）是古希腊语的「真理」，亦为真理女神之名。它的字面义是
**「去蔽」——使被隐藏之物显现**。这与本项目要做的事高度一致：业务语义被掩埋在
表名、字段与外键中，Aletheia 把它揭示为可治理的领域本体，并让每个判定结论都可核验。

神话中它的对立面是 Pseudologoi（谎言之灵）——看似合理却无法核验的言说。
这正是本项目要解决的问题。

---

## 解决什么问题

通用 RAG 框架优化的是「检索到的内容像不像答案」。Aletheia 优化的是
**「答案能不能被追问」**。

对权益、金额、合规、审批这类判定场景，一个「看起来对」的回答没有价值，
因为没有人能为它签字。Aletheia 的判定类结论必须同时给出四样东西：

| | 来源 |
|---|---|
| **结论** —— 订单 A123 不满足退款条件 | 规则引擎 |
| **依据规则** —— `refund_window_check` | 业务规则定义 |
| **证据链** —— 签收日期 2026-07-28，距今 24 天，超过 15 天窗口 | 结构化查询 |
| **决策记录** —— 落库的 `decision_record`，可审计、可复核、可追责 | 决策留痕 |

目标形态是这样一句客服回答：

> 「订单 A123 不满足退款条件，因签收已超 15 天（规则 `refund_window_check`），
> 依据《售后政策》第 3.2 条。」

其中「超 15 天」来自结构化查询，「不满足」来自规则引擎，
「第 3.2 条」来自文档检索。

**前两段今天已经能做，第三段还不能。** 文档检索尚未实现——
见 [当前限制](#当前限制)。本项目不会用「知识库问答」这类措辞暗示自己具备文档 RAG。

与 Dify／FastGPT／LangChain 的差别不在检索精度，而在结论的可追问性。

## 效果图

以下均为真实运行截图，非示意图或设计稿。数据来自内置的合成示例系统
（`examples/contract-system` 与设备运维样例），不含任何真实业务信息。

### 工作台：一屏看清「接下来该做什么」

![工作台](docs/images/06-workbench.png)

待处理事项按阻断优先排序，每条都指向可以处理它的页面。
所有数字都是既有表的只读投影，不会与它所汇总的页面产生分歧。

### 语义问答：结论 + 依据规则 + 证据

![语义问答与判定依据](docs/images/01-semantic-qa-with-evidence.png)

返回的不是一段自由文本，而是有结构的判定：**加粗的结论**、
**逐条规则的判定与原因**（每条带规则编码，如 `clause_content_required`，可回查）、
以及以表格呈现的批量决策分布。回答以 Markdown 渲染，
因此「哪条规则、为什么、结论是什么」可以分辨，而不是糊成一段。

左侧角色「设备运维业务专家」由已接入领域运行时派生——平台没有内置任何行业角色。

### 数据接入与元数据扫描

![数据源接入与元数据扫描](docs/images/02-data-source-onboarding.png)

接入既有数据库后自动扫描：表、字段、类型、外键关系、枚举候选、接入准备度评分。
连接串中的密码段已脱敏。

### 领域本体与业务对象

![领域本体与业务对象](docs/images/03-ontology-objects.png)

由元数据生成的本体草案：业务对象、属性、关系，以及每条语义映射的置信度与审核状态。

### 治理与发布门禁

![治理与发布门禁](docs/images/04-governance-release-gate.png)

发布前评估 release-readiness。存在阻断项时拒绝发布，`force` 覆盖会连同
未通过门禁数一并写入审计。

### 角色与对象权限

![角色与对象权限](docs/images/05-roles-and-permissions.png)

6 种能力 × 6 种角色，对象级读写执行删除策略。

> ⚠️ 图中的「行级过滤表达式」字段目前**有存储但未生效**，
> `check_permission` 只原样返回、不做过滤。详见[当前限制](#当前限制)。

### 知识图谱预览

![知识图谱预览](docs/images/07-knowledge-graph.png)

本体是图，但其余页面都以表格呈现，这会掩盖恰恰需要被看见的问题：
没有任何关联的孤立对象、自引用层级、以及不产出判定的对象簇。
颜色编码的是**诊断**而非装饰——红色表示未绑定来源表，橙色表示无规则。
圆圈大小为关联数量，悬停显示该关联依据的外键列。

图中如实标注了关系表达力的限制：`relation_type` 恒为 `references`、无基数、无多对多。

### 模型配置：适配自定义订阅

![模型配置](docs/images/08-model-config.png)

平台使用 OpenAI 兼容的 chat/completions 协议，因此任何实现该协议的服务都可接入。
仅可配 Base URL 是不够的——各家在**如何传密钥**与**能容忍哪些额外字段**上并不一致，
因此另有兼容性设置：

| 设置 | 解决的问题 |
|---|---|
| 鉴权方式（bearer／api-key／自定义／不发送） | Azure 用 `api-key` 头；本地服务常无需密钥 |
| 发送 OpenRouter 扩展字段（可关闭） | vLLM、LM Studio 等对未知字段直接返回 400 |
| 附加请求头（JSON） | 部分网关需要租户或分组标识 |

内置 OpenRouter／OpenAI／中转站／Azure／自建 vLLM／阿里云百炼预设，
并显示**实际会被调用的完整地址**。未配置密钥时回退本地启发式，功能不中断。

## 快速开始

需要 Python 3.9+（前端另需 Node.js 18+）。以下命令在干净 clone 中逐条实测通过。

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git && cd Aletheia-onto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ONTOLOGY_ADMIN_PASSWORD=change-me-please .venv/bin/python -m uvicorn \
    ontology_platform.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

服务起来后：

- 健康检查 `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- API 文档 `http://127.0.0.1:8000/docs`

默认平台库是 SQLite，**无需任何外部数据库服务**。
未设置 `ONTOLOGY_ADMIN_PASSWORD` 时会生成随机管理员口令并打印在启动日志中。

### 登录并完成一次问答

```bash
# 1. 登录，取得令牌
TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me-please"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 2. 载入示例本体（合同管理样例，4 张表）
curl -fsS -X POST http://127.0.0.1:8000/demo/bootstrap \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'

# 3. 问一个问题
curl -fsS -X POST http://127.0.0.1:8000/semantic/natural-language/query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"整体合规情况如何？","ontologyId":1,"useModel":false}'
```

第 3 步的实际返回（未配置模型密钥，走本地启发式）：

```json
{
  "answer": "合同 的批量决策一致性为 mixed。已评估 3 条：通过 2、复核 1、阻断 0、错误 0。",
  "intent": "decision_consistency",
  "confidence": 0.82
}
```

不带令牌访问受保护端点会得到 `401`。CI 的 `quickstart` job 每次都会重跑上面这条链路。

### 前端（可选）

```bash
cd frontend && npm install && npm run dev
```

前端默认 `http://127.0.0.1:3000`，需通过 `ONTOLOGY_ALLOWED_ORIGINS` 允许其来源。

## 架构

```mermaid
flowchart TB
    subgraph L1["接入层 ✅"]
        DS["数据源适配器<br/>SQLite / MySQL / PostgreSQL"]
        OAPI["OpenAPI 导入<br/>业务操作登记"]
    end

    subgraph L2["语义内核 ✅"]
        META["元数据扫描<br/>字段画像 / 枚举识别 / 外键 / 结构漂移"]
        ONTO["本体建模<br/>业务对象 / 属性 / 关系"]
        MAP["语义映射<br/>table_to_object / column_to_attribute"]
        RULE["规则引擎<br/>AST 白名单沙箱 / fail-closed"]
    end

    subgraph L3["治理与留痕 ✅"]
        GOV["映射审核 / 版本发布<br/>发布门禁 release-readiness"]
        TRACE["决策留痕<br/>inference_result / explanation_trace<br/>decision_record / audit_log"]
        AUTH["认证授权<br/>6 能力 × 6 角色 / 集中式策略表"]
    end

    subgraph L4["语义服务 ✅"]
        NL["自然语言问答<br/>意图路由 / 实例识别"]
        AGENT["智能体<br/>角色由已接入领域派生"]
        PRE["操作预检<br/>写回执行（HTTP）"]
        EXPORT["语义资产导出<br/>JSON-LD / Turtle"]
    end

    subgraph L5["📋 规划中，尚无实现"]
        RAG["文档摄取与检索"]
        TENANT["多租户隔离"]
        RESOLVER["实例解析器 SPI<br/>多表 join / 判别列分区 / 跨源"]
        CHAN["渠道接入"]
    end

    DS --> META --> ONTO --> MAP --> RULE
    OAPI --> ONTO
    MAP --> GOV
    RULE --> TRACE
    GOV --> ONTO
    RULE --> NL --> AGENT
    RULE --> PRE
    ONTO --> EXPORT
    AUTH -.->|贯穿| L4
    RAG -.->|规划| NL
    RESOLVER -.->|规划| ONTO
    TENANT -.->|规划| L3
```

## 核心概念

**领域本体** —— 对业务对象、属性、关系的形式化表达。由元数据扫描生成草案，
经人工审核后发布为不可变版本；已发布本体不可修改，只能派生新版本。

**语义映射** —— 遗留系统的表与字段到本体概念的可追踪对应关系。
每条映射有 `pending`／`confirmed` 状态与审核人留痕。

**业务规则** —— 可解释的判定条件，在 AST 白名单沙箱中求值。
写入时即校验表达式可执行性，不可执行的规则被直接拒绝。

**决策留痕** —— 一次判定产生四层记录：规则级 `inference_result`、
证据链 `explanation_trace`、决策级 `decision_record`、操作级 `audit_log`。

**发布门禁** —— 发布前评估 release-readiness，存在阻断项则拒绝发布。
`force` 覆盖会连同未通过门禁数一并写入审计。

## 能力矩阵

✅ 已实现且有测试覆盖　⚠️ 部分实现（逻辑未生效）　📋 计划中（零实现）

### 数据接入

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| SQLite／MySQL／PostgreSQL 适配器 | ✅ | `adapters.py` |
| 元数据扫描、字段画像、枚举识别、外键关系 | ✅ | `metadata.py`、`adapters.py` |
| 结构漂移对比 | ✅ | `metadata.py` |
| OpenAPI 导入业务操作 | ✅ | `operation_bindings.py`、`onboarding.py` |
| 平台库三方言（作为平台自身存储） | ✅ | `database.py` |
| **数据源适配器可注册**（第三方无需 fork） | ✅ | `registry.py`、`adapters.py` |
| Oracle／SQL Server／达梦／人大金仓内置适配器 | 📋 | 未内置，但可自行注册，见[扩展指南](docs/extending.md) |

### 本体与规则

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 按行业蓝图生成对象／属性／关系／映射候选 | ✅ | `ontology.py`、`industry_blueprints.py` |
| 行业蓝图导入 | ✅ | `industry_blueprints.py` |
| 规则引擎 AST 白名单沙箱求值 | ✅ | `semantic_kernel.py` |
| **规则函数可注册**（不放宽沙箱） | ✅ | `semantic_kernel.py`、`registry.py` |
| 规则 fail-closed 语义 | ✅ | `semantic_kernel.py` |
| 写入时表达式校验（含未知字段提示） | ✅ | `governance.py`、`semantic_kernel.py` |
| 语义资产导出 JSON-LD／Turtle | ✅ | `ontology.py` |
| 业务对象／属性／关系手工 CRUD | ⚠️ | 无端点，只能重新生成草案或审核映射 |
| 规则依赖 `depends_on` | ⚠️ | 有读写，求值时不使用，仅按 `priority` 排序 |
| 本体导入（SHACL／reasoner／命名空间管理） | 📋 | 只能导出 |
| 值域映射 `value_to_state`（走审核流程） | ✅ | `value_mapping.py` |
| 复合主键（实例键抽象） | ✅ | `instance_key.py` |
| 类型层级、关系基数、跨对象聚合 | 📋 | 见[结构性表达力约束](#结构性表达力约束) |

### 治理与留痕

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 语义映射审核（单条与批量） | ✅ | `governance.py` |
| 本体版本发布、已发布不可改、派生新版本 | ✅ | `governance.py` |
| 发布门禁 release-readiness（force 写审计） | ✅ | `release_readiness.py`、`governance.py` |
| 决策留痕四层记录 | ✅ | `decisions.py`、`semantic_kernel.py` |
| 语义覆盖度报告 | ✅ | `coverage.py` |
| 实例工作流状态与历史 | ✅ | `workflow_permission.py` |
| 工作流 `guard_expression` | ⚠️ | 有存储有接口，transition 时**从不求值** |
| 工作流与本体版本联动 | ⚠️ | derive 新版本**不复制**工作流配置 |
| 列表端点分页 | ⚠️ | 基本无分页（audit-log 等少数除外） |

### 认证与安全

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 令牌认证（PBKDF2-SHA256 加盐，仅存摘要） | ✅ | `auth.py` |
| 会话可撤销与过期，改密失效旧会话 | ✅ | `auth.py` |
| 6 能力 × 6 角色 | ✅ | `auth.py` |
| 集中式路由→能力策略表（未登记默认仅管理员） | ✅ | `access_policy.py` |
| **插件可注册路由权限策略** | ✅ | `access_policy.py` |
| 审计 actor 取自认证身份，不接受客户端自报 | ✅ | `api.py`、`auth.py` |
| 凭据脱敏（连接串密码段、API Key 首尾） | ✅ | `credentials.py` |
| 权限行级过滤 `filter_expression` | ⚠️ | 有存储，`check_permission` **只原样返回** |
| 权限策略本体维度 | ⚠️ | 只按裸 `object_code` 索引，**同名对象共享策略**（已知缺陷） |
| 多租户／租户隔离 | 📋 | 31 张表零租户概念 |
| 数据字典、部门／岗位数据权限 | 📋 | — |

### 语义服务

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 领域中立性（平台代码零内置行业词汇） | ✅ | `vocabulary.py`、`config.py` |
| 自然语言语义问答（意图路由、实例识别） | ✅ | `natural_language.py` |
| 智能体角色按已接入领域运行时派生 | ✅ | `agent_roles.py`、`agent.py` |
| 操作预检与写回执行（HTTP／HTTPS） | ✅ | `automation.py` |
| **写回执行器可注册**（按 scheme 分发） | ✅ | `automation.py`、`registry.py` |
| 模型层 OpenAI 兼容协议，自定义 Base URL 与订阅 | ✅ | `model_client.py` |
| 鉴权方式可选 / 扩展字段可关闭 / 附加请求头 | ✅ | `model_client.py` |
| 未配置密钥时回退本地启发式 | ✅ | `model_client.py` |
| 工作台聚合视图（待处理事项按阻断优先） | ✅ | `workbench.py` |
| 知识图谱预览（含建模缺口诊断） | ✅ | `graph_view.py` |
| 向量检索／嵌入／文档 RAG | 📋 | **零实现**，无 embedding／vector／chunk／rerank |
| 文档知识库 | 📋 | `contract_documents.py` 只从 Word 抽规则，不建检索语料 |
| 多轮对话持久化 | 📋 | history 由调用方每次传入，不落库 |
| 渠道接入（企微／钉钉／飞书／网页挂件） | 📋 | — |
| 定时调度器 | 📋 | 无任何 scheduler／cron |
| 反馈闭环、满意度、转人工 | 📋 | — |
| 跨源实体消解 | 📋 | — |
| MQ／RPC／直写库／存储过程内置执行器 | 📋 | 未内置，但可自行注册，见[扩展指南](docs/extending.md) |

## 当前限制

诚实优先。以下每一项都在代码中逐项确认过。

### 字段存在但逻辑未生效

这类最危险，因为接口看起来能用：

- **`workflow_transition.guard_expression`** —— 有存储有接口，transition 时从不求值。
  不要依赖它做状态流转准入。
- **`permission_policy.filter_expression`** —— 有存储，`check_permission` 只原样返回，
  不做行级过滤。不要依赖它做数据隔离。
- **`business_rule.depends_on`** —— 有读写，求值时完全不用，只按 `priority` 排序。
- **`permission_policy` 缺本体维度** —— 只按裸 `object_code` 建索引，
  两个本体定义同名对象时会共享同一条策略。**已知缺陷。**
- **工作流与本体版本脱钩** —— `derive` 新版本不复制工作流配置。
- **元模型文档超前** —— `docs/02` 画了 Event 与 State，schema 中无对应表。

### 结构性表达力约束

设计上的封顶，不是 bug，构成下一阶段的改造对象：

| 约束 | 位置 |
|---|---|
| `business_object.source_table_id` 是单外键，**一个对象只能绑一张表** | `database.py:363`（表定义） |
| `relation_type` 恒为硬编码 `"references"`，只能由外键派生，**无基数、无多对多** | `ontology.py:606` |
| **无类型层级**（无 parent_object／subclass／inherit） | — |
| 规则作用域为单对象 `scope_object_code`，**无跨对象聚合** | `semantic_kernel.py` |

> 扩展点已不在此列：数据源适配器、规则函数、路由策略、写回执行器
> 现已开放注册，见[扩展指南](docs/extending.md)。

### 工程限制

- **无连接池**；跨多次 `connect()` 的多步写入无统一事务边界。
- `api.py` 单文件 98 个端点，无 `/v1` 前缀。
- 前端 `types/index.ts` 手写 889 行镜像后端模型；后端存在 camelCase／snake_case 双发。
- DDL 分散在 4 个模块各自手写三方言。

架构层面的前置技术债逐项定位见 [`docs/architecture-debt.md`](docs/architecture-debt.md)。
路线与阻塞条件见 [`ROADMAP.md`](ROADMAP.md)。

## 设计决策

四项关键取舍，均有测试覆盖。完整记录（含被否决方案）见 [`docs/adr/`](docs/adr/)。

### 1. 规则引擎 fail-closed

表达式无法求值（字段更名、类型不匹配、语法错误）时**判为「未通过」**，
而非跳过后视为通过。阻断级→`blocked`，提示级→`review`。

理由：字段改名会让阻断级规则静默失效、预检放行、自动化继续执行——
而这恰恰是结构漂移检测声称要防的场景。宁可误报，不可漏报。

配套：写入时静态校验表达式。没有这一步，fail-closed 会把一个笔误
变成该对象所有实例的永久阻断。

证据：`tests/test_rule_engine_safety.py` ·
[ADR-0002](docs/adr/0002-rule-engine-fail-closed.md)

### 2. 发布强制门禁

`publish` 前评估 release-readiness，存在阻断项则拒绝发布。
`force` 覆盖会连同未通过门禁数一并写入审计。

理由：自动生成的本体草案不能直接当作生产真值。

### 3. 领域词汇不内置

任何内置行业词表都会让平台退化为单行业产品。业务术语只通过两条途径进入：
元数据扫描，以及用户可导入的行业蓝图。对象识别／默认对象／实例识别／
智能体角色／权限策略全部运行时派生。

代价：未导入蓝图时，草案标签就是原始列名（`total_amount` 而非「合同总金额」）。
难看但正确，好过漂亮但只对两个行业正确。

证据：`tests/test_domain_neutrality.py` 用平台完全未知的领域（宠物诊疗）
验证建模／识别／角色／权限全链路，并含静态守卫防止回归 ·
[ADR-0003](docs/adr/0003-no-builtin-domain-vocabulary.md)

### 4. 语义通用性明确封顶：不做完整 OWL/DL 推理

理由：DL reasoner 的结论是全局蕴含的产物，无法解释成「因为第 3.2 条」，
与本项目的可核验性直接对立。通用性靠「结构表达力 + 逃生舱」实现，
而非靠推理能力。

另一层：开放世界假设意味着「没查到就是未知」，而业务判定需要封闭世界语义——
库里没有付款记录就是没付款，不是「未知是否付款」。

证据：[ADR-0005](docs/adr/0005-semantic-generality-ceiling.md) ·
[Non-Goals](ROADMAP.md#non-goals)

## 配置

可配置项集中在 [`backend/ontology_platform/config.py`](backend/ontology_platform/config.py)，
全部可由环境变量覆盖。

### 运行与安全

| 变量 | 作用 | 默认 |
|---|---|---|
| `ONTOLOGY_ADMIN_USERNAME` | 引导管理员用户名 | `admin` |
| `ONTOLOGY_ADMIN_PASSWORD` | 引导管理员口令 | 未设则生成随机口令并打印 |
| `ONTOLOGY_SESSION_TTL_HOURS` | 会话有效期（小时） | `12` |
| `ONTOLOGY_AUTH_DISABLED` | 设为 `1` 关闭全部认证，**仅限本地开发** | 未设（认证开启） |
| `ONTOLOGY_ALLOWED_ORIGINS` | CORS 允许来源，逗号分隔 | `http://127.0.0.1:3000,http://localhost:3000` |

### 平台库

| 变量 | 作用 | 默认 |
|---|---|---|
| `ONTOLOGY_PLATFORM_DB_TYPE` | `sqlite`／`mysql`／`postgresql` | `sqlite` |
| `ONTOLOGY_PLATFORM_DB_URI` | 平台库连接串 | 本地 SQLite 文件 |
| `ONTOLOGY_PLATFORM_SQLITE_BUSY_TIMEOUT_MS` | SQLite busy_timeout | `5000` |

### 阈值与命名

| 组 | 内容 | 环境变量前缀 |
|---|---|---|
| `QUERY_LIMITS` | 分页上限、一致性采样、枚举识别 distinct 上下界 | `ONTOLOGY_DEFAULT_PAGE_SIZE`、`ONTOLOGY_MAX_PAGE_SIZE`、`ONTOLOGY_ENUM_*` |
| `MAPPING_CONFIDENCE` | 映射候选置信度（蓝图／结构／词表／弱匹配） | `ONTOLOGY_CONFIDENCE_*` |
| `ANSWER_CONFIDENCE` | 问答置信度 | `ONTOLOGY_ANSWER_CONFIDENCE_*` |
| `RESOLUTION_CONFIDENCE` | 实例识别置信度与加成 | `ONTOLOGY_RESOLUTION_*` |
| `SEMANTIC_ASSET_NAMING` | JSON-LD／Turtle 的 IRI 命名空间 | `ONTOLOGY_VOCABULARY_BASE_IRI`、`ONTOLOGY_ASSET_BASE_IRI` |
| `MODEL_PROVIDER_DEFAULTS` | 模型端点、模型名、超时、service tier | `OPENROUTER_*` |

模型密钥 `OPENROUTER_API_KEY` 未配置时，问答与建模回退本地启发式，功能不中断。

## 平台库三方言

平台自身的存储可以是 SQLite、MySQL 或 PostgreSQL，三者都有集成测试覆盖。

| 方言 | 连接串示例 | 说明 |
|---|---|---|
| SQLite | 默认，无需配置 | 启用 WAL 与 busy_timeout |
| MySQL | `mysql://root:password@127.0.0.1:3306/ontology_platform` | 8.0+ |
| PostgreSQL | `postgresql://postgres:postgres@127.0.0.1:5432/ontology_platform` | 14+ |

无本地数据库服务时，对应测试**自动跳过**，不会导致 CI 失败。

SQL 差异由 `database.py` 的适配层统一吸收：占位符转换、
`on conflict` → `on duplicate key update`、TEXT 列表达式默认值、
`dict_row` 行工厂、自增主键读取，以及提交与回滚语义。
详见 [ADR-0004](docs/adr/0004-three-platform-dialects.md)。

## 角色与能力

6 种能力 × 6 种角色。集中式路由→能力策略表在 `access_policy.py`，
**未登记的路由默认仅管理员可访问**。

| 角色 | `platform:read` | `platform:write` | `governance:review` | `governance:publish` | `automation:execute` | `platform:admin` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ontology_engineer` | ✅ | ✅ | | ✅ | | |
| `business_expert` | ✅ | ✅ | ✅ | | | |
| `operator` | ✅ | | | | ✅ | |
| `analyst` | ✅ | | | | | |
| `ai_agent` | ✅ | | | | | |

新用户默认角色为 `analyst`。令牌认证使用 PBKDF2-SHA256 加盐，**token 仅存摘要**；
会话可撤销与过期，改密使旧会话全部失效；审计身份取自认证身份。

## 测试

```bash
.venv/bin/python -m pytest
```

**256 个测试**，全绿。分布：

| 文件 | 数量 | 覆盖 |
|---|--:|---|
| `test_extension_registry.py` | 45 | 扩展点注册表 + 第三方合规样板 |
| `test_composite_instance_keys.py` | 31 | 复合主键端到端 + 实例键往返 |
| `test_value_domain_mapping.py` | 13 | 值域映射与向后兼容 |
| `test_custom_model_endpoints.py` | 21 | 自定义模型端点兼容性 |
| `test_workbench_and_graph.py` | 14 | 工作台聚合与图谱投影 |
| `test_metadata_flow.py` | 34 | 接入、扫描、本体生成、接入准备度 |
| `test_api_authentication.py` | 27 | 认证、会话、能力策略、actor 可信 |
| `test_domain_neutrality.py` | 25 | 未知领域全链路 + 静态守卫 |
| `test_rule_engine_safety.py` | 17 | 沙箱逃逸、fail-closed 语义、发布门禁 |
| `test_platform_database_dialects.py` | 10 | 三方言作为平台库 |
| `test_credential_protection.py` | 8 | 连接串与 API Key 脱敏 |
| `test_data_source_knowledge_base.py` | 11 | 数据源知识库 |

静态检查与前端构建：

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m ruff format --check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

CI 另有一个 `quickstart` job，在干净环境重跑本 README 的快速开始链路，
并校验此处声明的测试数量与实际收集数一致。

## 规模

29 个后端模块约 13400 行，98 个 API 端点，31 张平台表，前端 React + antd。

## 示例

[`examples/contract-system/`](examples/contract-system/) 是一个模拟遗留系统的
最小合同管理应用，用于演示完整接入流程。
**其中公司名、联系人、手机号、邮箱与统一社会信用代码全部为合成占位，
不对应任何真实主体。**

## 文档

| 文档 | 内容 |
|---|---|
| [ROADMAP](ROADMAP.md) | 三仓库形态、框架化 A–G、通用性 #1–#13、Non-Goals |
| [docs/adr/](docs/adr/) | 架构决策记录，含被否决方案与后果 |
| [docs/architecture-debt.md](docs/architecture-debt.md) | 框架化前置技术债 |
| [docs/](docs/) | 设计文档索引（⚠️ 部分内容超前于当前实现） |
| [CHANGELOG](CHANGELOG.md) | 变更记录 |

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。两条硬要求：

1. **不允许通过删改测试断言来让测试通过。**
2. **文档只能描述已实现且有测试覆盖的能力。**

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 issue。
行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可证

[Apache-2.0](LICENSE)，含专利授权条款。
