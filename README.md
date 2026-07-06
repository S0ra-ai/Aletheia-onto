# 本体改造研发平台原型

这是“本体改造研发平台”的第一版可运行原型，目标是先跑通 MVP 主链路：

1. 创建合同管理、设备运维等样例传统数据库。
2. 注册传统数据库与业务系统接口为平台数据源。
3. 扫描表、字段、主键、外键和字段画像。
4. 生成领域本体草案。
5. 建立基础语义映射。
6. 对业务记录输出语义解释与语义研判。
7. 对传统业务系统 API 做语义预检、自动化执行计划和决策留痕。
8. 通过 OpenRouter 兼容模型层生成本体、规则和行业蓝图建议。
9. 输出语义覆盖度、结构漂移影响和可安装语义内核包。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_demo.py
uvicorn ontology_platform.api:app --reload --app-dir backend
```

启动后访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## 关键 API

- `POST /demo/bootstrap`：创建合同管理样例系统并生成本体草案。
- `POST /demo/bootstrap/equipment`：创建设备运维样例系统并生成本体草案。
- `POST /data-sources/test-connection`：登记前测试数据库连接。
- `POST /data-sources`：登记传统业务系统数据库。
- `POST /data-sources/{id}/test-connection`：测试已登记数据源连接。
- `POST /data-sources/{id}/apis`：登记传统业务系统 API 或业务动作。
- `POST /data-sources/{id}/apis/import-openapi`：从 OpenAPI 文档批量导入业务 API。
- `POST /data-sources/{id}/scan`：扫描数据库元数据。
- `GET /data-sources/{id}/readiness`：查看数据源接入准备度。
- `GET /data-sources/{id}/semantic-coverage`：查看业务对象、映射、规则和 API 的语义覆盖度。
- `GET /data-sources/{id}/schema-drift`：对比实时数据库结构与最近扫描基线，分析结构漂移影响。
- `GET /data-sources/{id}/kernel-package/download`：导出可安装的业务语义内核包。
- `GET /industry-blueprints`：查看内置和自定义行业蓝图。
- `POST /industry-blueprints`：导入或更新行业蓝图。
- `POST /ontologies/draft`：生成领域本体草案。
- `GET /ontologies/{id}/export`：导出 JSON-LD 或 Turtle 语义资产。
- `GET /ontologies/{id}/mappings`：查看语义映射候选。
- `POST /semantic-mappings/{id}/review`：审核单条语义映射。
- `POST /ontologies/{id}/mappings/review`：批量审核语义映射。
- `POST /ontologies/{id}/publish`：发布已审核本体版本。
- `GET /ontologies/{id}/release-readiness`：评估本体发布门禁，汇总映射、规则、数据源准备度、语义覆盖和结构漂移证据。
- `POST /ontologies/{id}/derive`：从已发布本体派生新的草案版本。
- `GET /ontologies/{id}/rules`：查看业务规则。
- `POST /ontologies/{id}/rules`：登记或更新业务规则。
- `GET /semantic/objects/{objectCode}/instances/{id}/explain`：解释业务实例。
- `POST /semantic/objects/{objectCode}/instances/{id}/assess`：执行业务规则研判。
- `POST /semantic/objects/{objectCode}/consistency`：批量评估业务对象实例，验证决策一致性和规则失败分布。
- `POST /automation/operations/{operationCode}/preflight`：对传统业务系统操作执行语义预检，判断是否允许自动化。
- `POST /automation/operations/{operationCode}/execute`：在语义预检通过后生成执行计划，或调用 HTTP/HTTPS 传统业务系统 API。
- `POST /ai/data-sources/{id}/ontology-suggestions`：生成 AI 本体建议。
- `POST /ai/data-sources/{id}/blueprint-draft`：生成行业蓝图草案。
- `GET /model/status`：查看 OpenRouter 模型层配置状态。
- `GET /model/config` / `POST /model/config` / `DELETE /model/config`：查看、保存或重置 OpenRouter 配置。
- `GET /governance/audit-log`：查看治理审计记录。
- `GET /governance/decisions`：查看语义研判、预检和执行的决策记录。

## OpenRouter 配置

平台模型层兼容 OpenRouter 的 OpenAI 风格 Chat Completions API。可以通过环境变量提供默认值，也可以在平台页面或 `/model/config` API 中保存配置。平台会传递 `service_tier`，可兼容 OpenRouter 的订阅模式、自动路由和额度策略。

```bash
export OPENROUTER_API_KEY="你的 OpenRouter API Key"
export OPENROUTER_MODEL="~openai/gpt-latest"
export OPENROUTER_HTTP_REFERER="https://your-company.example"
export OPENROUTER_APP_TITLE="Ontology Transformation Platform"
export OPENROUTER_SERVICE_TIER="auto"
```

也可以通过 API 持久化配置：

```bash
curl -X POST http://127.0.0.1:8000/model/config \
  -H 'Content-Type: application/json' \
  -d '{
    "apiKey": "你的 OpenRouter API Key",
    "model": "~openai/gpt-latest",
    "baseUrl": "https://openrouter.ai/api/v1",
    "httpReferer": "https://your-company.example",
    "appTitle": "Ontology Transformation Platform",
    "serviceTier": "auto"
  }'
```

未配置 API Key 时，AI 建模能力会回退到本地启发式建议，核心接入、建模、映射、研判、自动化和治理流程仍可运行。

## 治理发布流程

平台不会把自动生成的本体草案直接当作生产真值。推荐流程：

1. 扫描传统业务系统数据库。
2. 生成领域本体草案和语义映射候选。
3. 业务专家审核语义映射，状态从 `pending` 变为 `confirmed` 或 `rejected`。
4. 规则管理员补充或调整业务规则。
5. 所有映射审核完成后发布本体版本。
6. 已发布本体不可直接修改映射和规则。
7. 业务变化时，从已发布本体派生新的草案版本，重新审核映射并调整规则。

## 测试

```bash
python -m pytest
```

## 当前范围

当前版本使用 SQLite 作为开发期平台库和样例传统库，便于快速验证。架构上已经区分数据源、业务系统 API、领域本体、语义映射、规则研判、模型适配和治理审计；后续可扩展 PostgreSQL、MySQL、Oracle、SQL Server 和国产数据库适配器。

当前已内置两个行业样例：

- 合同管理：客户、合同、付款计划、发票。
- 设备运维：设备、工单、点检记录、备件。

## 数据库接入适配器

接入层已经抽象为数据库适配器：

- `sqlite`：当前完整可运行，用于样例库和本地验证。
- `postgresql`：使用 `psycopg`，支持连接测试、元数据扫描和运行时读取。
- `mysql`：使用 `PyMySQL`，支持连接测试、元数据扫描和运行时读取。

登记 PostgreSQL 数据源示例：

```json
{
  "name": "某行业生产业务系统",
  "sourceType": "postgresql",
  "connectionUri": "postgresql://user:password@host:5432/database",
  "domain": "供应链采购",
  "systemCategory": "database+api"
}
```

登记 MySQL 数据源示例：

```json
{
  "name": "某行业生产业务系统",
  "sourceType": "mysql",
  "connectionUri": "mysql://user:password@host:3306/database",
  "domain": "设备运维",
  "systemCategory": "database+api"
}
```

生产接入建议使用只读账号，并先在测试库执行元数据扫描。

登记前连接测试示例：

```bash
curl -X POST http://127.0.0.1:8000/data-sources/test-connection \
  -H 'Content-Type: application/json' \
  -d '{
    "sourceType": "postgresql",
    "connectionUri": "postgresql://user:password@host:5432/database"
  }'
```
