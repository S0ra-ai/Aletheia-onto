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

**三段现已全部打通。** 「第 3.2 条」由文档知识层提供：条款按编号切分、
锚定到具体规则、经审核后才可被引用（见[文档知识库](#文档知识库)）。

检索质量不是本项目的优势，也明确列在 Non-Goals 中；默认实现为零外部依赖的
BM25，追求召回质量的部署可注册 pgvector 等后端。**可核验的引用**才是差异点。

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

### 多租户隔离

按 [ADR-0006](docs/adr/0006-tenant-isolation-model.md) 落地**双层隔离**——
两层的失效模式不重叠,任何单层出问题另一层仍拦得住:

| 层 | 作用 | 各方言实现 |
|---|---|---|
| **schema** | 挡住忘写租户过滤的查询 | PG `search_path`／MySQL database／SQLite 独立文件 |
| **`tenant_id`** | 把路由错误变成可见报错,而非静默跨租户读取 | 关键表加列 + 写入自动填充 |

共享表方案被否决的原因很具体:它把正确性押在「每条查询都记得加过滤」上,
而**漏写过滤在单租户测试数据下完全看不出来**。

租户标识受严格校验(`^[a-z][a-z0-9_]{0,38}$`)——它会被插入 DDL 与 `search_path`,
而这两处无法用绑定参数,因此必须先证明其安全。

`require_tenant()` 在无法确定租户时**拒绝而非猜测**,与 ADR-0002 同一立场。

### 文档知识库

![文档知识库](docs/images/09-knowledge-base.png)

制度与合同条款按**条款编号**切分（`第3.2条`、`3.1`、`一、`、`Article 7`），
保留人类可引用的定位。两条治理约束写进了流程：

1. **条目默认 pending，未确认不可被检索。** 一段被错误切分的条款若直接成为判定依据，
   产生的是「看起来有据可查但依据是错的」——比没有依据更危险。
2. **确认时必须锚定**业务对象或规则。未锚定的文本无法回答
   「这段话凭什么支持这个结论」，因此不构成依据。

检索顺序是**先按锚定收窄候选，再排序**——这与「全库检索后看命中什么」方向相反，
也是引用可归因而非仅相似的原因。

### 反馈闭环

![反馈闭环](docs/images/10-feedback-loop.png)

用户对判定结论的评价会**锚定到具体消息与决策记录**——「这个判定不对」只有在
知道是哪个判定时才可行动。

两处刻意不做的设计：

1. **不提供满意度平均分。** 平均分不告诉你该修哪一条;按评价分类计数、
   「结论错误」排在最前，才是可行动的。
2. **不提供「一键应用纠正」。** 纠正是一方主张而非新规则，
   要成为规则或知识条目须走治理流程（ADR-0002）。

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

完整配置项与排错见[接入自定义模型服务](docs/model-endpoints.md)。

## 快速开始

需要 Python 3.9+（前端另需 Node.js 18+）。以下命令均在干净环境中实测通过。

### 作为包安装

内核**零第三方依赖**，不装 web 服务器也能跑通完整闭环。

```bash
pip install aletheia-onto          # 内核：本体、规则、判定、留痕
pip install 'aletheia-onto[all]'   # 加上 HTTP 层、PostgreSQL／MySQL、文档解析
```

```bash
aletheia demo      # 用内置样例系统跑通：接入 → 建模 → 判定
aletheia doctor    # 报告当前配置、已安装 extra 与已注册扩展点
```

`aletheia demo` 的输出（内核裸装，无任何 extra）：

```json
{
  "platformDb": "~/.aletheia/platform.sqlite3",
  "ontologyId": 1,
  "objectCode": "contract",
  "decision": "approved",
  "next": "aletheia serve  # 打开 http://127.0.0.1:8000/docs"
}
```

接自己的系统：

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain 合同管理
aletheia model 1
aletheia assess 1 contract 1
```

`aletheia assess` 只输出判定与未通过的规则；完整证据用 `--verbose`，
或从决策留痕里查。`aletheia publish` 受发布门禁约束，
**待审核的语义映射无法用 `--force` 跳过**——在没人看过的映射上发布，
会让由它得出的每个判定都无法追责。

### 从源码运行

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git && cd Aletheia-onto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ONTOLOGY_ADMIN_PASSWORD=change-me-please .venv/bin/python -m uvicorn \
    ontology_platform.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

服务起来后：

- 健康检查 `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- API 文档 `http://127.0.0.1:8000/docs`

每个端点同时以裸路径与 `/v1` 前缀提供（`/ontologies/1` 与 `/v1/ontologies/1`），
两条路径经过同一套鉴权中间件与同一份权限策略。新接入方请固定 `/v1`。

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

这一节是平台的本体词汇表。术语按「本体结构 → 与遗留系统的对应 → 判定与留痕」
三层排列，每条给出它在平台里的确切含义，以及**它刻意不是什么**——
本体领域的词被用得很松，说清边界比给定义更有用。

### 一、本体结构

**领域本体（Ontology）** —— 对业务对象、属性、关系、事件、状态、规则的形式化表达，
带版本。由元数据扫描生成草案，经人工审核后发布为不可变版本；
已发布本体不可修改，只能派生新版本。
_不是_：知识图谱、数据模型、数据字典。

**元模型（Metamodel）** —— 描述领域本体自身结构的模型：规定一个本体可以包含
哪些对象、哪些关系类型、哪些生命周期信息。行业本体是元模型的实例。
完整定义见 [核心元模型设计](docs/02-核心元模型设计.md)。

**业务对象（BusinessObject）** —— 业务人员能稳定识别并讨论的对象：客户、合同、
设备、工单。它**不等于一张表**——由实例解析器决定哪些行构成它的实例
（ADR-0011）。
_不是_：实体、表记录、DTO。

**实例（Instance）** —— 业务对象的一个具体个体，由实例键标识。

**实例键（InstanceKey）** —— 标识一个实例的列组合。支持复合主键：
连接表、版本化表、分区历史表在遗留 schema 中很常见（ADR-0008）。

**实例解析器（InstanceResolver）** —— 「哪些行是这个对象的实例」的可替换策略。
四种内置：单表、主从 join、判别列分区、自定义 SQL；可注册第三方实现（ADR-0011）。

**属性（Attribute）** —— 业务对象的一个具名特征。分两种来源：

- **映射属性**：镜像一个来源列
- **派生属性（DerivedAttribute）**：由表达式算出，如 `毛利率 = (收入 - 成本) / 收入`。
  定义一次，所有规则共用，避免同一口径在多条规则里漂移（ADR-0013）

**单位与量纲（Unit / Dimension）** —— 属性可声明单位。同量纲比较自动换算，
跨量纲比较直接拒绝。这不是便利功能：万元与元混用时，
`合同金额 500 > 额度 1000000` 会得出「未超额」——用正确数据产出的错误判定（ADR-0013）。

**关系（Relation）** —— 两个业务对象之间的链接，带**基数**（一对一／多对一／
一对多／多对多）与**强弱**：

| 类型 | 含义 | 判定依据 |
|---|---|---|
| 组成（composition） | 身份依赖，子离开父即无意义 | 外键在子表主键内 |
| 聚合（aggregation） | 父必需，但子身份独立 | 外键非空且不在主键内 |
| 关联（association） | 父可选 | 外键可空 |

分类只依据声明结构，不看数据分布——从采样推断的关系会随数据改变含义，
引用它的判定就不可复现（ADR-0012）。

**类型层级（TypeHierarchy）** —— 声明「企业客户是客户的子类型」。
子类型继承祖先的规则、聚合与派生属性。这是沿声明链的确定性展开，
**不是 DL 包含推理**：平台不推断谁是谁的子类型，只展开已声明的链（ADR-0014）。

**规则覆盖（Override）** —— 子类型可声明某条规则取代祖先的某条规则，
用于合法业务例外。必须显式声明而非同名推断：同名有歧义，
推断会静默停用某个团队的管控。削弱允许，不可见地削弱不允许（ADR-0014）。

**跨对象聚合（Aggregate）** —— 具名的、可审阅的组级取值，如
「该客户所有生效合同总额」。规则因此能表达「总额不得超过信用额度」。
声明为数据而不是规则里的内联 join——「为什么」的答案必须是一份运维能读的定义，
而不是一句没人审过的查询（ADR-0012）。

**状态（State）与工作流** —— 业务对象实例的生命周期位置与允许的流转。
流转守卫（guard）在规则沙箱中求值，求值失败即阻断流转。

**业务事件（Event）** —— 实例上发生过的事，只追加。声明类型后记录，
带载荷、发生时间与操作者。事件**不触发任何东西**：
能触发自动化的事件会让回放历史重新执行业务动作（ADR-0014）。
_不是_：消息、日志、埋点。

**时间线（Timeline）** —— 一个实例的完整事件序列，按来源时间排序。
状态流转自动镜像进来，所以实例只有一条时间线而不是每个子系统一条。

**行业蓝图（IndustryBlueprint）** —— 一个行业的对象命名、属性命名与规则模板集合。
平台**不内置领域词汇**，词汇由蓝图在运行时提供，新行业靠导入蓝图而不是改平台代码
（ADR-0003）。

### 二、与遗留系统的对应

**业务系统接入** —— 把遗留系统的表、接口、动作与能力边界登记到平台。
平台**读元数据，不搬运数据**。

**语义映射（SemanticMapping）** —— 遗留系统的表与字段到本体概念的可追踪对应关系。
每条映射有 `pending`／`confirmed` 状态与审核人留痕。
_不是_：ETL 映射、数据同步关系。

**值域映射（ValueMapping）** —— 遗留编码到语义状态的对应，如 `status='A'` ↔ 生效中。
映射后两种写法在规则里等价，业务人员不必背魔法值（ADR-0008）。

**结构漂移（Drift）** —— 来源库结构与已扫描元数据的差异。
发布门禁会做漂移检测，因为在漂移的映射上判定等于在未验证数据上判定。

### 三、判定与留痕

**业务规则（BusinessRule）** —— 可解释的判定条件，在 AST 白名单沙箱中求值。
写入时即校验表达式可执行性，不可执行的规则被直接拒绝。
_不是_：算法、模型、策略引擎脚本。

**fail-closed** —— 表达式无法求值（列改名、类型不符、语法错误）时按**未通过**处理，
并附上原因。反过来会让结构漂移静默停用一条阻断规则，而自动化仍在跑（ADR-0002）。

**语义研判（Assessment）** —— 对某个实例输出通过状态、阻断原因与建议动作。
一次研判会展开类型层级、计算聚合与派生属性、施加单位、求值全部适用规则。

**决策留痕** —— 一次判定产生四层记录：规则级 `inference_result`、
证据链 `explanation_trace`、决策级 `decision_record`、操作级 `audit_log`。

**解释（Explanation）** —— 一个实例的可读说明：属性取值、来源表、上级类型、
近期事件时间线。回答的是「它是什么、它怎么变成现在这样」。

**发布门禁（ReleaseGate）** —— 发布前评估 release-readiness，存在阻断项则拒绝发布。
`force` 覆盖会连同未通过门禁数一并写入审计。

**逃生舱（Escape Hatch）** —— 结构表达力不够时下沉到自定义实现的口子：
自定义 SQL 作对象来源、自定义规则函数、派生属性表达式、写回执行器 SPI、
数据源适配器 SPI。通用性靠「结构表达力 + 逃生舱」实现，不靠推理能力（ADR-0005）。

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
| **SQL 方言 profile**（6 个差异点声明为数据，非分支） | ✅ | `sql_dialects.py` |
| **通用 DB-API 适配器**：新 SQL 库靠声明接入，无需写适配器 | ✅ | `generic_sql_adapter.py` |
| Oracle／SQL Server／达梦／人大金仓／openGauss 内置声明 | ⚠️ | 已内置声明与方言，驱动装上即可用；**CI 无法安装驱动，故未实测** |
| **CSV／TSV 目录数据源**（类型与主键推断，外键不猜） | ✅ | `file_adapter.py` |
| **REST／OpenAPI 数据源**（字段声明式，非采样） | ✅ | `rest_adapter.py` |

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
| **实例解析器**：主从表／判别列分区／自定义 SQL | ✅ | `instance_resolver.py` |
| 解析器可注册（第三方策略） | ✅ | `instance_resolver.py` |
| **关系基数与强弱**（一对一／多对一／多对多，组成／聚合／关联） | ✅ | `relations.py` |
| **中间表折叠为多对多**，且中间表对象保留其属性 | ✅ | `relations.py`、`semantic_kernel.py` |
| **跨对象聚合**（客户所有合同总额等组级取值） | ✅ | `aggregation.py` |
| **派生属性**（表达式计算，复用规则沙箱） | ✅ | `derived_attributes.py` |
| **单位与量纲**（同量纲换算，跨量纲拒绝） | ✅ | `derived_attributes.py` |
| **类型层级**（子类型继承规则／聚合／派生属性） | ✅ | `type_hierarchy.py` |
| **规则覆盖**（显式声明，校验必须在上级链内） | ✅ | `type_hierarchy.py`、`governance.py` |
| 跨源实例解析（一个对象跨两个数据源） | 📋 | 需先做跨源实体消解 |
| 时态与生效期（属性级历史） | 📋 | 规则有生效期，属性无 |

### 治理与留痕

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 语义映射审核（单条与批量） | ✅ | `governance.py` |
| 本体版本发布、已发布不可改、派生新版本 | ✅ | `governance.py` |
| 发布门禁 release-readiness（force 写审计） | ✅ | `release_readiness.py`、`governance.py` |
| 决策留痕四层记录 | ✅ | `decisions.py`、`semantic_kernel.py` |
| 语义覆盖度报告 | ✅ | `coverage.py` |
| 实例工作流状态与历史 | ✅ | `workflow_permission.py` |
| 工作流 `guard_expression` | ✅ | transition 时真实求值，fail-closed |
| **业务事件**（声明类型、只追加、带载荷与来源时间） | ✅ | `events.py` |
| **统一时间线**（状态流转自动镜像，实例只有一条时间线） | ✅ | `events.py`、`workflow_permission.py` |
| **事件计数**（「上个月被驳回多少次」无需读文本） | ✅ | `events.py` |
| **属性级时态**（版本化、有效时间与事务时间分离） | ✅ | `temporal.py` |
| **as-of 判定**（按当时的值与当时生效的规则回溯判定） | ✅ | `temporal.py`、`semantic_kernel.py` |
| **历史覆盖区间上报**（区间外为「未知」，不是「无变化」） | ✅ | `temporal.py` |
| **直写库／存储过程写回**（语句声明、值绑定、无 WHERE 拒绝） | ✅ | `db_executors.py` |
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
| 权限行级过滤 `filter_expression` | ✅ | `check_permission` 传入实例时真实求值 |
| 权限策略本体维度 | ✅ | 按 `(role, ontology, object)` 索引，0 表示通配 |
| 多租户隔离（独立 schema + `tenant_id` 双保险） | ✅ | `tenancy.py` |
| 租户开通与枚举 | ✅ | `tenancy.py` |
| 跨租户访问检测（fail-closed） | ✅ | `tenancy.py` |
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
| 文档知识库（条款切分 + 可引用定位） | ✅ | `knowledge_documents.py` |
| 知识条目锚定本体对象／规则 | ✅ | `knowledge_documents.py` |
| 检索后端 SPI（默认 BM25，零外部依赖） | ✅ | `retrieval.py` |
| 嵌入模型 SPI（默认哈希 n-gram） | ✅ | `retrieval.py` |
| 带引用的判定答案（护城河第三段） | ✅ | `natural_language.py` |
| 向量数据库内置集成（pgvector／Milvus） | 📋 | 未内置，可通过 SPI 注册 |
| 多轮对话持久化 | ✅ | `conversations.py`，刷新不丢上下文 |
| 反馈闭环（满意度／纠正／转人工） | ✅ | `conversations.py` |
| 反馈锚定到决策记录 | ✅ | `conversations.py` |
| 渠道接入（企微／钉钉／飞书／网页挂件） | 📋 | — |
| 定时调度器 | 📋 | 无任何 scheduler／cron |
| 跨源实体消解 | 📋 | — |
| MQ／RPC／直写库／存储过程内置执行器 | 📋 | 未内置，但可自行注册，见[扩展指南](docs/extending.md) |

## 当前限制

诚实优先。以下每一项都在代码中逐项确认过。

### 字段存在但逻辑未生效

这类最危险，因为接口看起来能用：

> 此前列在本节的四项已修复：`guard_expression`、`filter_expression`、
> `depends_on` 现已真实生效，`permission_policy` 已带本体维度。三者均为
> fail-closed：无法求值时拒绝而非放行。

- **工作流与本体版本脱钩** —— `derive` 新版本不复制工作流配置。
- **元模型文档超前** —— `docs/02` 画了 Event 与 State，schema 中无对应表。

### 结构性表达力约束

设计上的封顶，不是 bug，构成下一阶段的改造对象：

| 约束 | 位置 |
|---|---|
| **跨源不支持**：一个对象不能跨两个数据源，聚合也不能跨源。需先回答「两源里哪两行是同一实例」，且该判断本身必须可核验 | `instance_resolver.py`、`aggregation.py` |
| **时态只覆盖平台观测到的区间**：原地覆盖值的源系统丢掉的历史无法重建。`coverage` 会明确上报可回答区间 | `temporal.py` |
| **聚合在 Python 内计算**，不下推 SQL。换来三方言行为一致，代价是行数上限 | `aggregation.py` |
| **关系分类依赖 schema 声明质量**：不写外键、不写 NOT NULL 的库只能得到最弱分类 | `relations.py` |
| **CSV 与 REST 不推断外键**：关系语义要求结构是声明的，从命名巧合推出的关系无法解释 | `file_adapter.py`、`rest_adapter.py` |
| **CSV 每次查询整文件读取**：适合导出规模，不适合仓库规模 | `file_adapter.py` |
| **类型层级上限 16 层**，派生链上限 5 趟 | `type_hierarchy.py`、`derived_attributes.py` |
| **不做完整 OWL/DL 推理**，不做开放世界假设 | 刻意，见 [ADR-0005](docs/adr/0005-semantic-generality-ceiling.md) |

> 关系基数、类型层级、跨对象聚合、派生属性、单位量纲、业务事件、时态生效期、
> 数据源与写回通道扩展均已不在此列，
> 见[本体与规则](#本体与规则)能力矩阵与
> [ADR-0012](docs/adr/0012-cross-object-aggregation-and-relation-semantics.md)、
> [ADR-0013](docs/adr/0013-derived-attributes-and-units.md)、
> [ADR-0014](docs/adr/0014-type-hierarchy-and-business-events.md)、
> [ADR-0015](docs/adr/0015-open-data-sources-and-temporal-validity.md)。
> 扩展点也不在此列：数据源适配器、规则函数、路由策略、写回执行器
> 现已开放注册，见[扩展指南](docs/extending.md)。

### 工程限制

- **无连接池**；跨多次 `connect()` 的多步写入无统一事务边界。
- 172 处 `platform_db: Path | str` 签名**尚未改为上下文对象**——现在能接受它，
  但逐模块迁移是后续工作（[ADR-0010](docs/adr/0010-platform-context-replaces-global-singleton.md)）。
- `api.py` 单文件 130 个端点，**尚未拆分为 APIRouter**（`/v1` 前缀已有）。
- 前端 `types/index.ts` 手写 1143 行镜像后端模型；后端存在 camelCase／snake_case 双发。
- DDL 调度已统一到 `schema.py`，但**尚未迁移 Alembic**——迁移需归属于某个分发包，
  因此阻塞于分包边界。
- **尚未拆分为多个 PyPI 分发包**。当前是单包 `aletheia-onto` + optional extras，
  extras 承载了未来分包的接缝但不冻结边界。

架构层面的前置技术债逐项定位见 [`docs/architecture-debt.md`](docs/architecture-debt.md)。
路线与阻塞条件见 [`ROADMAP.md`](ROADMAP.md)。

## 设计决策

九项关键取舍，均有测试覆盖。完整记录（含被否决方案）见 [`docs/adr/`](docs/adr/)。

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

### 5. 关系语义只从声明结构推断，绝不看数据分布

从采样推断出的关系会在数据变化时改变含义，引用它的判定就不可复现。
每条关系都记录它所依据的结构事实——**没有依据的分类无法被审阅**，
运维要纠正一条生成的关系，必须先知道它为何被这样分类。

证据：`tests/test_relation_expressiveness.py` ·
[ADR-0012](docs/adr/0012-cross-object-aggregation-and-relation-semantics.md)

### 6. 聚合是声明的数据，不是规则里的内联查询

「为什么」的答案必须是一份运维能读、能审阅、能随语义资产导出的定义，
而不是一句没人审过的 join。算不出来的聚合让规则失败，
而不是拿阈值去和一个伪造的 0 比较。

读行后在 Python 内计算而非下推聚合 SQL——**牺牲下推性能，换三方言行为完全一致**，
代价是行数上限，且触顶会上报而非静默截断。

证据：`tests/test_cross_object_aggregation.py` ·
[ADR-0012](docs/adr/0012-cross-object-aggregation-and-relation-semantics.md)

### 7. 单位同量纲换算，跨量纲直接拒绝

没有单位时，万元与元混用会让 `合同金额 500 > 额度 1000000` 得出「未超额」——
**用正确数据产出的错误判定**。跨量纲（时长比质量）抛错而非原样透传数字，
因为那通常意味着建模有误，静默透传会让由此得出的判定看起来完全有效。

汇率被刻意排除：汇率是随时间变化的数据，内嵌一个会让判定不可复现。

证据：`tests/test_derived_attributes_and_units.py` ·
[ADR-0013](docs/adr/0013-derived-attributes-and-units.md)

### 8. 规则覆盖必须显式声明，不靠同名推断

同名有歧义——两个团队可能各自取到同一个 code，而推断会**静默停用其中一个团队的管控**。
削弱继承来的规则是允许的，因为存在合法业务例外（国资交易对手豁免信用审查）；
**不可见地**削弱则不允许。

证据：`tests/test_type_hierarchy_and_events.py` ·
[ADR-0014](docs/adr/0014-type-hierarchy-and-business-events.md)

### 9. 事件是记录，绝不是触发器

能触发自动化的事件会让审计轨迹承载副作用，于是回放历史（回补、纠错、迁移）
会重新执行业务动作。只追加也是同一个理由：记错的事件靠补偿事件纠正，
删除会留下一个无法解释自己如何形成的状态。

证据：`tests/test_type_hierarchy_and_events.py` ·
[ADR-0014](docs/adr/0014-type-hierarchy-and-business-events.md)

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

**839 个测试**，全绿（3 个按环境跳过：无本地 MySQL／PostgreSQL，
以及仅在 CI 上执行的 wheel 构建）。分布：

| 文件 | 数量 | 覆盖 |
|---|--:|---|
| `test_extension_registry.py` | 45 | 扩展点注册表 + 第三方合规样板 |
| `test_composite_instance_keys.py` | 31 | 复合主键端到端 + 实例键往返 |
| `test_value_domain_mapping.py` | 13 | 值域映射与向后兼容 |
| `test_custom_model_endpoints.py` | 21 | 自定义模型端点兼容性 |
| `test_workbench_and_graph.py` | 14 | 工作台聚合与图谱投影 |
| `test_document_knowledge.py` | 27 | 条款切分、锚定检索、带引用答案 |
| `test_inert_fields_activated.py` | 28 | 守卫、行级过滤、规则依赖、策略本体维度 |
| `test_conversations_and_feedback.py` | 35 | 会话持久化、反馈归因、转人工 |
| `test_platform_context.py` | 23 | 多实例隔离、线程绑定、向后兼容 |
| `test_multi_tenancy.py` | 42 | schema 路由、tenant_id 双保险、跨租户拦截 |
| `test_instance_resolvers.py` | 57 | 四种解析器 + 一致性契约 + 注入防护 |
| `test_cross_object_aggregation.py` | 46 | 聚合定义校验、fail-closed、行数上限、端到端 |
| `test_type_hierarchy_and_events.py` | 42 | 继承展开、覆盖声明、环检测、事件只追加与时间线 |
| `test_derived_attributes_and_units.py` | 42 | 派生多趟求值、量纲换算、跨量纲拒绝 |
| `test_relation_expressiveness.py` | 22 | 基数与强弱推断、中间表折叠、一对一注入为单行 |
| `test_sql_dialects_and_generic_adapter.py` | 54 | 方言 profile、通用 DB-API 适配器（对真实 PostgreSQL 声明式接入实证） |
| `test_file_and_rest_sources.py` | 43 | CSV 类型／主键推断、REST 声明式接入、端到端至判定 |
| `test_database_writeback.py` | 35 | 语句声明、值绑定、无 WHERE 拒绝、影响 0 行按失败、真实写入与回滚 |
| `test_temporal_validity.py` | 35 | 半开区间、回溯插入、as-of 判定用当时的值、缺席不插值 |
| `test_cli.py` | 19 | 命令行闭环、发布门禁不可绕过、错误不抛栈 |
| `test_api_versioning.py` | 17 | `/v1` 与裸路径鉴权一致、公开路径不被版本化破坏 |
| `test_packaging.py` | 13 | 内核零依赖、版本一致、PEP 561、默认路径不依赖工作目录 |
| `test_module_boundaries.py` | 6 | 无循环依赖、无跨模块私有引用、`__all__` 可解析 |
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
| [docs/extending.md](docs/extending.md) | 扩展点注册与插件打包 |
| [docs/model-endpoints.md](docs/model-endpoints.md) | 接入自定义模型服务与订阅 |
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
