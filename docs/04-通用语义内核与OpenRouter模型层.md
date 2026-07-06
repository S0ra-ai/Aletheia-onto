# 通用语义内核与 OpenRouter 模型层

## 1. 本次实现目标

本阶段把系统从“合同管理样例原型”推进为“可接入多行业传统业务系统的通用语义内核原型”。

已经实现的方向包括：

1. 数据源登记支持行业域、系统类别和能力标签。
2. 数据库接入层已经抽象为适配器，当前支持 SQLite，并提供 PostgreSQL、MySQL 适配入口。
3. 业务系统接口可登记为语义动作。
4. 本体草案生成不再固定为合同管理，而是按数据源行业域和表画像生成。
5. 内置合同管理与设备运维两个行业样例。
6. 语义内核运行时支持实例解释、上下文装载、规则执行、风险研判和建议动作。
7. 业务系统操作预检支持把语义研判结果转成自动化放行、人工复核或阻断。
8. 治理层支持语义映射审核、本体版本发布、规则登记和发布后不可直接修改。
9. 治理层记录元数据扫描、本体生成、映射审核、本体发布、语义研判、操作预检和模型调用。
10. 模型层兼容 OpenRouter 的订阅密钥模式。

## 2. 运行时语义内核

语义内核的职责是把传统业务系统中的一条记录转化为可判断的业务上下文。

当前运行时过程：

1. 根据本体找到业务对象。
2. 根据语义映射找到来源表和主键。
3. 从传统数据库读取实例记录。
4. 根据外键读取直接关联对象。
5. 根据反向外键读取从属对象集合。
6. 执行该业务对象作用域内的业务规则。
7. 输出解释、风险、阻断状态和建议动作。
8. 写入推理结果、解释链和审计日志。

示例：

合同实例会自动装载客户与付款计划上下文，因此可以执行“黑名单客户合同风险”和“付款计划总额应等于合同金额”等跨表规则。

设备实例会自动装载工单上下文，因此可以执行“重要设备存在未关闭工单风险”等跨表规则。

## 3. 数据库适配器

数据库接入已从 SQLite 硬编码拆分为适配器接口。

当前适配器能力：

1. `sqlite`：完整支持表、字段、主键、外键、字段画像、实例读取和关联上下文读取。
2. `postgresql`：支持连接测试，通过 `information_schema` 扫描表、字段、主键、外键和字段画像；运行时读取使用同一适配器。需要安装 `psycopg`。
3. `mysql`：支持连接测试，通过 `information_schema` 扫描表、字段、主键、外键和字段画像；运行时读取使用同一适配器。需要安装 `PyMySQL`。

适配器让平台可以逐步接入 Oracle、SQL Server、达梦、人大金仓等数据库，而不影响本体、映射、规则和语义服务层。

连接测试端点：

1. `POST /data-sources/test-connection`：登记前测试连接串、驱动和网络可达性。
2. `POST /data-sources/{id}/test-connection`：测试已登记数据源。

连接测试返回 `reachable`、`status` 和 `message`，便于实施人员区分驱动缺失、连接失败和成功连接。

## 4. 规则表达范围

当前规则表达式面向工程落地，支持：

1. 字段比较：`amount > 0`。
2. 空值判断：`signed_date != null`。
3. 布尔组合：`status != 'effective' or signed_date != null`。
4. 关联对象访问：`customer.credit_status != 'blacklist'`。
5. 从属集合聚合：`sum(payment_plan.planned_amount) == amount`。
6. 条件计数：`count(work_order.status == 'open') == 0`。

后续可演进到 SHACL、Datalog 或专业规则引擎，但首版优先保证可解释、可调试、可审计。

## 5. 业务操作自动化预检

业务系统接口登记后，可以通过操作预检把语义内核接到传统系统操作之前。

当前预检过程：

1. 根据数据源和操作编码找到传统业务系统 API。
2. 根据语义动作推断业务对象，例如 `contract.submit_for_approval` 推断为 `contract`。
3. 对目标实例执行语义研判。
4. 如果研判结果为 `approved`，返回 `allow_automation`。
5. 如果研判结果为 `review`，返回 `route_to_human_review`。
6. 如果研判结果为 `blocked`，返回 `block_and_require_correction`。

这使传统系统可以在执行提交、审批、关闭、派单、结算等操作前，统一调用语义内核获得一致的决策依据。

## 6. 治理与发布控制

自动生成的本体草案不是生产真值。平台引入一个轻量但明确的治理流程：

1. 语义映射初始状态为 `pending`。
2. 业务专家可以把映射审核为 `confirmed` 或 `rejected`。
3. 本体发布前不允许存在 `pending` 映射。
4. 本体发布前必须至少存在一条 `confirmed` 映射。
5. 规则管理员可以在草案阶段登记或更新业务规则。
6. 本体发布后，映射和规则不可直接修改。
7. 业务变化时，从已发布本体派生新的草案版本，新版本映射回到 `pending`，规则可重新调整。

相关端点：

1. `GET /ontologies/{id}/mappings`。
2. `POST /semantic-mappings/{id}/review`。
3. `POST /ontologies/{id}/mappings/review`。
4. `POST /ontologies/{id}/publish`。
5. `POST /ontologies/{id}/derive`。
6. `GET /ontologies/{id}/rules`。
7. `POST /ontologies/{id}/rules`。

这个流程保证“AI 生成候选、专家确认、版本发布、运行时执行”之间有明确边界。

## 7. OpenRouter 兼容方式

平台模型层通过后端环境变量读取 OpenRouter API key，并调用 OpenRouter 的 OpenAI 兼容 Chat Completions 接口。

关键环境变量：

1. `OPENROUTER_API_KEY`：OpenRouter API key。
2. `OPENROUTER_MODEL`：模型 slug，默认 `~openai/gpt-latest`。
3. `OPENROUTER_BASE_URL`：默认 `https://openrouter.ai/api/v1`。
4. `OPENROUTER_HTTP_REFERER`：应用来源标识。
5. `OPENROUTER_APP_TITLE`：应用名称。
6. `OPENROUTER_SERVICE_TIER`：服务层级，默认 `auto`。

平台不会把 OpenRouter key 返回给前端，也不会把 key 写入仓库。

## 8. 当前可验证能力

自动化测试覆盖：

1. 合同管理数据库接入、扫描、本体草案生成、语义解释和风险研判。
2. 设备运维数据库接入、业务 API 登记、本体草案生成和风险研判。
3. 数据库适配器登记，覆盖 SQLite、PostgreSQL、MySQL 三类企业常见数据库入口。
4. 数据源连接测试，覆盖 SQLite 成功、SQLite 缺失文件和 PostgreSQL 不可达状态。
5. 语义映射审核、本体发布、规则登记、发布后不可直接修改和派生新版本。
6. 传统业务系统操作预检，能把语义研判转成自动化放行或人工复核。
7. OpenRouter 请求形态，包括 Bearer key、应用标题、来源标识、模型 slug、服务层级和 session id。

运行命令：

```bash
.venv/bin/python -m pytest
```

## 9. 后续工程方向

下一阶段建议继续推进：

1. 增加 Oracle、SQL Server、达梦、人大金仓等适配器。
2. 增加本体编辑与映射确认界面。
3. 增加规则管理界面和规则版本发布流程。
4. 增加操作自动化编排，把研判结果转为可执行动作。
5. 增加权限、脱敏、字段级安全和生产数据接入策略。
6. 增加 OpenRouter 流式调用、模型重试和预算控制。
