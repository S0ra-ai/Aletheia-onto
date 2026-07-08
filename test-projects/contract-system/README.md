# 合同管理系统接入测试样例

这是一个用于本体改造研发平台接入测试的传统合同管理系统。它模拟企业已有业务系统，包含：

- SQLite 业务数据库：客户、合同、付款计划、发票、审批记录、合同变更记录。
- FastAPI 业务接口：合同查询、合同审批提交、付款确认、发票、Word 合同文档下载。
- Word 合同文件：合同正文以 `.docx` 存储，路径为 `documents/`。
- 前端页面：合同工作台、客户、合同、付款、发票。
- 本体接入 OpenAPI：`http://127.0.0.1:8001/api/openapi-for-ontology.json`。

## 启动

```bash
cd test-projects/contract-system
./start.sh
```

默认地址：

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8001`
- API 文档：`http://127.0.0.1:8001/docs`

## 本体平台接入参数

- 数据源名称：`Word合同管理测试系统`
- 数据库类型：`sqlite`
- 数据库连接地址：`/Users/s0ra/code/本体通用系统/test-projects/contract-system/data/contracts.sqlite3`
- 业务领域：`合同管理`
- 系统分类：`database+api`
- 业务 API 基址：`http://127.0.0.1:8001`
- OpenAPI URL：`http://127.0.0.1:8001/api/openapi-for-ontology.json`
- 行业蓝图：`合同管理蓝图`

## Word 合同样例

`documents/` 下包含多个 `.docx` 合同文件，种子数据会把文件名、路径、大小、MD5 和提取文本写入合同表，便于本体平台扫描和规则测试。
