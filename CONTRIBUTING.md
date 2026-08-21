# 贡献指南

感谢你考虑为 Aletheia 做贡献。

## 开发环境

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git
cd Aletheia-onto
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && cd ..
```

需要 Python 3.9+ 与 Node.js 18+。

## 提交前必须通过

```bash
.venv/bin/python -m pytest          # 128 个测试，必须全绿
cd frontend && npm run build        # 必须无错误
```

CI 还会跑 `ruff check` 与 `ruff format --check`。本地可以先跑：

```bash
.venv/bin/python -m ruff check backend tests
.venv/bin/python -m ruff format --check backend tests
```

## 这个项目最重要的一条规矩

**不允许通过删改测试断言来让测试通过。**

如果你的改动让某个测试失败，先判断是改动错了还是测试过时了。
确实需要变更行为时，在 PR 里说明理由，并等待讨论结论——
不要先改断言再说。

尤其注意这两类测试，它们保护的是项目的核心承诺：

- `tests/test_rule_engine_safety.py` —— 规则引擎的 fail-closed 语义与沙箱边界
- `tests/test_domain_neutrality.py` —— 平台代码不得内置行业词汇（含静态守卫）

改动它们等于改动项目定位，需要先有对应的 ADR。

## 诚实性要求

README 与文档只能描述**已实现且有测试覆盖**的能力。具体地：

- 不要把「部分实现」写成「已支持」
- 不要用模糊措辞暗示不存在的能力（例如用「知识库问答」暗示具备文档 RAG）
- 不要添加伪造的 badge（覆盖率、下载量、指向不存在的 workflow）
- 新增能力时，同步更新 README 的能力矩阵与「当前限制」
- 发现字段存在但逻辑未生效，如实记进「当前限制」，不要留白

宁可写得保守，也不要写得漂亮。

## 提交信息

采用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <简短描述>

<正文：为什么这样改，不只是改了什么>
```

常用 type：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`、`perf`。

正文请说明**为什么**。「修复 MySQL 写入丢失」不如
「pymysql 的 `__exit__` 只 close 不 commit，导致上下文退出时写入被回滚」。

## Pull Request

1. 从 `main` 切分支，命名如 `feat/instance-resolver`、`fix/mysql-upsert`
2. 一个 PR 只做一件事。混合改动会让 review 变成考古
3. 填写 PR 模板，说明改动内容、验证方式、是否有破坏性变更
4. 确保 CI 通过

不要直推 `main`，不要 force push 已推送的分支。

## 架构决策

涉及以下情况时，请先提一份 ADR（见 [`docs/adr/`](docs/adr/)）讨论，
再动手实现：

- 改变数据模型（31 张表的结构）
- 引入新的外部依赖
- 改变已记录的设计决策
- 新增或改变扩展点的形状

`docs/architecture-debt.md` 列出了框架化前的技术债。
如果你的改动偿还了其中一项，请在 PR 里指明，并更新该文件的「已偿还」小节。

## 报告问题

使用 issue 模板。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，
**不要**开公开 issue。
