# 本体改造研发平台原型

这是“本体改造研发平台”的第一版可运行原型，目标是先跑通 MVP 主链路：

1. 创建合同管理、设备运维等样例传统数据库。
2. 注册传统数据库与业务系统接口为平台数据源。
3. 扫描表、字段、主键、外键和字段画像。
4. 生成领域本体草案。
5. 建立基础语义映射。
6. 对业务记录输出语义解释与语义研判。
7. 通过 OpenRouter 兼容模型层生成本体与规则建议。

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
- `POST /data-sources`：登记传统业务系统数据库。
- `POST /data-sources/{id}/apis`：登记传统业务系统 API 或业务动作。
- `POST /data-sources/{id}/scan`：扫描数据库元数据。
- `POST /ontologies/draft`：生成领域本体草案。
- `GET /semantic/objects/{objectCode}/instances/{id}/explain`：解释业务实例。
- `POST /semantic/objects/{objectCode}/instances/{id}/assess`：执行业务规则研判。
- `POST /automation/operations/{operationCode}/preflight`：对传统业务系统操作执行语义预检，判断是否允许自动化。
- `POST /ai/data-sources/{id}/ontology-suggestions`：生成 AI 本体建议。
- `GET /model/status`：查看 OpenRouter 模型层配置状态。
- `GET /governance/audit-log`：查看治理审计记录。

## OpenRouter 配置

平台模型层兼容 OpenRouter 的 OpenAI 风格 Chat Completions API。密钥只从后端环境变量读取。

```bash
export OPENROUTER_API_KEY="你的 OpenRouter API Key"
export OPENROUTER_MODEL="~openai/gpt-latest"
export OPENROUTER_HTTP_REFERER="https://your-company.example"
export OPENROUTER_APP_TITLE="Ontology Transformation Platform"
export OPENROUTER_SERVICE_TIER="auto"
```

未配置 `OPENROUTER_API_KEY` 时，`/ai/data-sources/{id}/ontology-suggestions` 会回退到本地启发式建议，核心接入、建模、映射和研判流程仍可运行。

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
- `postgresql`：适配入口已实现，扫描时需要安装 `psycopg` 并提供 PostgreSQL 连接串。
- `mysql`：适配入口已实现，扫描时需要安装 `PyMySQL` 并提供 MySQL 连接串。

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
