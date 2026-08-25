# 能力矩阵

> 逐项列出已实现／部分实现／未实现，以及实现位置。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

✅ 已实现且有测试覆盖　⚠️ 部分实现（逻辑未生效）　📋 计划中（零实现）

## 数据接入

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| SQLite／MySQL／PostgreSQL 适配器 | ✅ | `adapters.py` |
| 元数据扫描、字段画像、枚举识别、外键关系 | ✅ | `metadata.py`、`adapters.py` |
| 结构漂移对比 | ✅ | `metadata.py` |
| OpenAPI 导入业务操作 | ✅ | `operation_bindings.py`、`onboarding.py` |
| 平台库三方言（作为平台自身存储） | ✅ | `database.py` |
| **数据源适配器可注册**（第三方无需 fork） | ✅ | `registry.py`、`adapters.py` |
| **可执行一致性契约随包发布**（5 个扩展点，第三方可自验） | ✅ | `conformance.py` |
| **部署前自检**（免鉴权暴露等静默误配置在流水线阶段被拦） | ✅ | `deployment.py`、`deploy/` |
| **问答回归测试集**（断言结构性属性，不锚定措辞） | ✅ | `tests/test_answer_regression.py` |
| **SQL 方言 profile**（6 个差异点声明为数据，非分支） | ✅ | `sql_dialects.py` |
| **通用 DB-API 适配器**：新 SQL 库靠声明接入，无需写适配器 | ✅ | `generic_sql_adapter.py` |
| Oracle／SQL Server／达梦／人大金仓／openGauss 内置声明 | ⚠️ | 已内置声明与方言，驱动装上即可用；**CI 无法安装驱动，故未实测** |
| **CSV／TSV 目录数据源**（类型与主键推断，外键不猜） | ✅ | `file_adapter.py` |
| **REST／OpenAPI 数据源**（字段声明式，非采样） | ✅ | `rest_adapter.py` |

## 本体与规则

| 能力 | 状态 | 实现位置 |
|---|:--:|---|
| 按行业蓝图生成对象／属性／关系／映射候选 | ✅ | `ontology.py`、`industry_blueprints.py` |
| 行业蓝图导入 | ✅ | `industry_blueprints.py` |
| 规则引擎 AST 白名单沙箱求值 | ✅ | `semantic_kernel.py` |
| **规则函数可注册**（不放宽沙箱） | ✅ | `semantic_kernel.py`、`registry.py` |
| 规则 fail-closed 语义 | ✅ | `semantic_kernel.py` |
| 写入时表达式校验（含未知字段提示） | ✅ | `governance.py`、`semantic_kernel.py` |
| 语义资产导出 JSON-LD／Turtle（平台词汇，字段更全） | ✅ | `ontology.py` |
| **OWL/RDFS 导出**（`owl:Class`／`rdfs:domain`／`rdfs:range`／`rdfs:subClassOf`） | ✅ | `standard_vocabulary.py` |
| **SHACL 形状导出**（由同一份声明生成，非手写） | ✅ | `standard_vocabulary.py` |
| 业务对象／属性／关系手工 CRUD | ⚠️ | 无端点，只能重新生成草案或审核映射 |
| 规则依赖 `depends_on` | ⚠️ | 有读写，求值时不使用，仅按 `priority` 排序 |
| 本体导入（reasoner／命名空间管理） | 📋 | 只能导出 |
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
| **跨源实体消解**（一个对象跨两个数据源，匹配是声明的） | ✅ | `entity_resolution.py` |
| **跨源聚合**（「这个客户在 ERP 里的订单总额」） | ✅ | `aggregation.py`：`targetDataSourceId` |
| **时态与生效期**（属性级版本 + as-of 回溯判定） | ✅ | `temporal.py` |
| **业务事件**（只追加事件流 + 状态流转统一时间线） | ✅ | `events.py` |
| **公理**（六类模型级约束，违反阻断发布） | ✅ | `axioms.py` |

## 治理与留痕

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
| **审计报表**（从未触发的规则、覆盖门禁的发布、留痕完整性） | ✅ | `audit_reports.py` |
| **租户配额**（存于基础库，租户无法自行调高） | ✅ | `quotas.py` |
| **as-of 判定**（按当时的值与当时生效的规则回溯判定） | ✅ | `temporal.py`、`semantic_kernel.py` |
| **历史覆盖区间上报**（区间外为「未知」，不是「无变化」） | ✅ | `temporal.py` |
| **直写库／存储过程写回**（语句声明、值绑定、无 WHERE 拒绝） | ✅ | `db_executors.py` |
| 工作流与本体版本联动 | ⚠️ | derive 新版本**不复制**工作流配置 |
| 列表端点分页 | ⚠️ | 基本无分页（audit-log 等少数除外） |

## 认证与安全

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
| **检索期权限过滤**（引用不得越过调用者可读的对象） | ✅ | `retrieval.py`：锚定后、排序前，判定失败按拒绝 |
| 权限策略本体维度 | ✅ | 按 `(role, ontology, object)` 索引，0 表示通配 |
| 多租户隔离（独立 schema + `tenant_id` 双保险） | ✅ | `tenancy.py` |
| 租户开通与枚举 | ✅ | `tenancy.py` |
| 跨租户访问检测（fail-closed） | ✅ | `tenancy.py` |
| **SSO 单点登录**（JWT 断言校验，组→角色映射） | ✅ | `sso.py` |
| **SSO 未映射即拒绝**（不给默认角色） | ✅ | `sso.py` |
| 数据字典、部门／岗位数据权限 | 📋 | — |

## 语义服务

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

| MQ／RPC／直写库／存储过程内置执行器 | 📋 | 未内置，但可自行注册，见[扩展指南](extending.md) |
