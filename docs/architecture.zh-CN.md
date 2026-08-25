# 架构

> 分层结构与数据流。图中每一层的状态都与代码核对过——
> 一张把已实现能力标为「规划中」的架构图，会让读者绕开它，或据此否决整个项目。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

```mermaid
flowchart TB
    subgraph L1["接入层"]
        DS["数据源适配器<br/>SQLite / MySQL / PostgreSQL<br/>+ 通用 DB-API（Oracle / SQL Server / 达梦 / 人大金仓）"]
        FILE["文件与接口源<br/>CSV 目录 / REST·OpenAPI"]
    end

    subgraph L2["语义内核"]
        META["元数据扫描<br/>字段画像 / 枚举识别 / 外键 / 结构漂移"]
        ONTO["本体建模<br/>对象 / 属性 / 关系（含基数与强弱）"]
        RESOLVER["实例解析器<br/>单表 / 主从 join / 判别列分区 / 自定义 SQL"]
        META2["元模型表达力<br/>类型层级 / 跨对象聚合 / 派生属性与单位<br/>业务事件 / 属性级时态 / 公理"]
        MAP["语义映射<br/>table_to_object / column_to_attribute"]
        RULE["规则引擎<br/>AST 白名单沙箱 / fail-closed"]
        XSRC["跨源实体消解<br/>声明式匹配，不做相似度"]
    end

    subgraph L3["治理与留痕"]
        GOV["映射审核 / 版本发布<br/>发布门禁（待审映射不可 --force 跳过）"]
        TRACE["决策留痕<br/>inference_result / explanation_trace<br/>decision_record / audit_log"]
        AUTH["认证授权<br/>6 能力 × 6 角色 / 集中式策略表 / SSO"]
        TENANT["多租户隔离<br/>独立 schema + tenant_id / 租户配额"]
        AUDIT["审计报表<br/>从未触发的规则 / 覆盖门禁的发布 / 留痕完整率"]
    end

    subgraph L4["语义服务"]
        NL["自然语言问答<br/>意图路由 / 实例识别 / 带引用的答案"]
        KB["文档知识层<br/>条款切分 / 锚定 / 检索期权限过滤"]
        AGENT["智能体<br/>角色由已接入领域派生"]
        PRE["操作预检与写回<br/>HTTP / 直写库 / 存储过程"]
        EXPORT["语义资产导出<br/>JSON-LD / Turtle / OWL / SHACL"]
        GEN["代码生成<br/>由本体产出 TypeScript 类型与客户端"]
    end

    subgraph L5["📋 规划中"]
        CHAN["渠道接入<br/>企微 / 钉钉 / 飞书"]
        SCHED["定时调度器"]
        PKG["拆分为多个 PyPI 分发包"]
    end

    DS --> META --> ONTO
    FILE --> META
    ONTO --> RESOLVER --> RULE
    ONTO --> META2 --> RULE
    ONTO --> MAP --> GOV
    ONTO --> XSRC --> RULE
    RULE --> TRACE --> AUDIT
    GOV --> ONTO
    RULE --> NL
    KB --> NL --> AGENT
    RULE --> PRE
    ONTO --> EXPORT
    ONTO --> GEN
    AUTH -.->|贯穿| L4
    TENANT -.->|贯穿| L3
    CHAN -.->|规划| NL
```

## 三条不变量

这三条决定了架构为什么长这样，而不是「分层比较整齐」。

**判定必须可回溯到声明。** 规则引擎不做推理，只对声明过的规则求值；
关系语义只从 schema 声明推断，绝不看数据分布。因此每个结论都能指回
某个人做过的声明——这也是[拒绝完整 DL 推理](adr/0005-semantic-generality-ceiling.md)的理由。

**求值失败等于未通过。** 表达式无法求值时判为「不通过 + 原因」，绝不跳过。
字段改名会让阻断级规则静默失效，而那恰恰是结构漂移检测声称要防的场景。

**治理在写入路径上，不在旁路。** 映射未审核则不能发布，且 `--force` 也不能跳过；
知识条目未确认锚定则不可被检索。门禁若可绕过，它就只是一份建议。

## 相关文档

- [核心概念](concepts.zh-CN.md) —— 本体结构、与遗留系统的对应、判定与留痕
- [能力矩阵](capabilities.zh-CN.md) —— 逐项实现状态与位置
- [当前限制](limitations.zh-CN.md) —— 做不到什么，以及为什么
- [架构债](architecture-debt.md) —— 前置技术债逐项定位
