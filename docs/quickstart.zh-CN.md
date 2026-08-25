# 快速开始

> 从安装到接入自己的系统，含标准词汇导出与回溯判定。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

需要 Python 3.11+（前端另需 Node.js 18+）。以下命令均在干净环境中实测通过。
CI 在 3.11／3.12／3.13 上各跑一遍完整测试——声明支持而不执行的版本，
会先在用户环境里出问题。

## 作为包安装

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

**从脚手架起步。** `new` 生成一个依赖平台的项目骨架，**不是 fork**——
升级即 `pip install -U aletheia-onto`，生成的代码无需改动：

```bash
aletheia new --list-extensions          # 先看有哪些扩展点、各自适用什么场景
aletheia new mycorp --extension rule-function --domain 合同管理
cd mycorp && pip install -e . && python -m mycorp init
```

生成物包含配置模块、按需生成的扩展点骨架、一致性契约脚本，
以及不含任何可用默认值的 `.env.example`。用 `python -m mycorp` 而非 `aletheia`：
后者不会加载你注册的扩展。

接自己的系统：

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain 合同管理
aletheia model 1
aletheia assess 1 contract 1
```

**接入不限于数据库。** 拿不到生产库凭据时，导出文件与 API 同样能跑通全链路：

```bash
aletheia connect /path/to/extract --type csv --domain 合同管理   # 一个 CSV 目录
aletheia doctor        # 列出可用数据源，以及未激活的需要哪个驱动
```

Oracle／SQL Server／达梦／人大金仓／openGauss 已内置声明与方言，
装上对应驱动即出现在数据源列表里。接一个未内置的 SQL 库不需要写适配器——
声明 4 行即可，见[扩展指南](extending.md#10-接一个新的-sql-数据库)。

**由本体生成前端类型。** 手写镜像做不到的那部分：关系被类型化为它指向的**对象**，
而不是 `number`——手写版把每个外键都写成数字，于是没有任何东西阻止把合同 id
传给需要客户的地方。

```bash
aletheia codegen 1 --output src/types/ontology.ts
```

只接受**已发布**本体：草案的对象与属性会在映射审核期间变动，据此生成的类型
描述的是没人同意过的模型。产物经真实 `tsc --strict` 编译验证。

**导出为标准词汇。** 对标 GB/T 48000.3—2026 对 OWL/RDF 的采用要求，
本体可直接导出为外部 RDF 工具**能解释**（而非仅能读取）的形式：

```bash
aletheia export 1 --format owl    > ontology.ttl   # owl:Class／rdfs:domain／rdfs:range
aletheia export 1 --format shacl  > shapes.ttl     # SHACL 形状，可交给校验器
aletheia export 1 --format jsonld > asset.jsonld   # 平台词汇，字段更全
```

两套词汇并存而非替换：`owl`／`shacl` 用标准术语，换来互操作；
`jsonld`／`turtle` 用平台自有术语，保留标准词汇无对应词的字段
（来源表、规则表达式、映射置信度）。
SHACL 形状**由同一份声明生成而非手写**——手写的一份会与发布门禁漂移，
而漂移的那份会声明平台并不执行的约束。

**回溯判定。** 合规审计问的通常是过去某一刻：

```bash
aletheia assess 1 contract 1 --as-of 2026-01-31
```

按当时的属性值与**当时生效的规则**判定。拿今天的值重新判定回答的是另一个问题。

`aletheia assess` 只输出判定与未通过的规则；完整证据用 `--verbose`，
或从决策留痕里查。`aletheia publish` 受发布门禁约束，
**待审核的语义映射无法用 `--force` 跳过**——在没人看过的映射上发布，
会让由它得出的每个判定都无法追责。

## 从源码运行

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

## 登录并完成一次问答

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

## 前端（可选）

```bash
cd frontend && npm install && npm run dev
```

前端默认 `http://127.0.0.1:3000`，需通过 `ONTOLOGY_ALLOWED_ORIGINS` 允许其来源。
