# Quick start

> From install to onboarding your own system, including standard-vocabulary export.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

Requires Python 3.11+ (Node.js 18+ for the frontend). CI runs the full suite on
3.11, 3.12 and 3.13 -- a version that is claimed but never executed breaks in a
user's environment first. Every command below was run in a
clean environment.

## Install as a package

The kernel has **no third-party dependencies** -- it runs the whole loop without a web
server installed.

```bash
pip install aletheia-onto          # kernel: ontology, rules, verdicts, provenance
pip install 'aletheia-onto[all]'   # plus HTTP layer, PostgreSQL/MySQL, document parsing
```

```bash
aletheia demo      # onboard → model → assess, against a built-in sample system
aletheia doctor    # report configuration, installed extras, registered extension points
```

Connect a real system:

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain 合同管理
aletheia model 1
aletheia assess 1 contract 1
```

### What your first verdict on your own schema looks like

`model` drafts an ontology from your metadata and infers an industry blueprint, then
`assess` runs immediately -- there is no separate publish step in the way, because a draft
is usable for assessment. Two things about that first output are worth knowing before you
see them, since both look like faults and neither is:

**Some rules will report that they could not be evaluated.** A blueprint contributes rules
written for its own domain, and your schema may not have the associations they reference:

```
rule payment_plan_amount_match -> 表达式引用了此处不可用的名称「payment_plan」。
    常见原因是该规则来自行业蓝图而本对象没有这个关联，或该字段尚未映射到本对象
```

That is fail-closed working as designed ([ADR-0002](adr/0002-rule-engine-fail-closed.md)):
a rule whose precondition cannot be checked must not count as passing, or a renamed column
would silently disable a blocking control. The extension guide's
[§13](extending.md#13-a-consequence-on-csv-and-rest-sources) covers the three ways to deal
with it; the shortest is to review the draft and delete or rescope the rules that do not
apply to you.

**The draft's mappings are `pending`.** You can assess with them, but `aletheia publish` is
gated until someone reviews them, and unreviewed mappings cannot be forced through. That is
the point: a verdict derived from a mapping nobody looked at is a verdict nobody can
account for.

**Sources are not limited to databases.** When production credentials are weeks away, an
extract or an API runs the same pipeline:

```bash
aletheia connect /path/to/extract --type csv --domain 合同管理   # a directory of CSVs
aletheia doctor        # available source types, and which driver the inactive ones need
```

Oracle / SQL Server / 达梦 / 人大金仓 / openGauss ship as declarations with their dialects;
installing the driver makes them appear. Adding a SQL database that is *not* declared does
not require writing an adapter — four lines of declaration, see
[the extension guide](extending.md#10-connecting-a-new-sql-database).

**Assess as of a past moment.** A compliance audit usually asks about the past:

```bash
aletheia assess 1 contract 1 --as-of 2026-01-31
```

It uses the values that were valid then, and the rules that were in force then. Assessing
against today's values answers a different question.

`aletheia assess` prints the verdict and the rules that failed; use `--verbose` for the
full evidence. `aletheia publish` is subject to the release gate, and **unreviewed
mappings cannot be skipped with `--force`** -- publishing on mappings nobody looked at
would make every verdict derived from them unaccountable.

## Run from source

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git && cd Aletheia-onto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ONTOLOGY_ADMIN_PASSWORD=change-me-please .venv/bin/python -m uvicorn \
    ontology_platform.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then:

- Health check `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- API docs `http://127.0.0.1:8000/docs`

Every endpoint is served both bare and under `/v1` (`/ontologies/1` and
`/v1/ontologies/1`), through the same authorization middleware and the same policy
table. New integrations should pin `/v1`.

The default platform database is SQLite, so **no external database service is
needed**. If `ONTOLOGY_ADMIN_PASSWORD` is unset, a random admin password is generated
and printed to the startup log.

## Log in and ask one question

```bash
TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me-please"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -fsS -X POST http://127.0.0.1:8000/demo/bootstrap \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'

curl -fsS -X POST http://127.0.0.1:8000/semantic/natural-language/query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"整体合规情况如何？","ontologyId":1,"useModel":false}'
```

Actual response from step 3 (no model key configured, so the local heuristic answers):

```json
{
  "answer": "合同 的批量决策一致性为 mixed。已评估 3 条：通过 2、复核 1、阻断 0、错误 0。",
  "intent": "decision_consistency",
  "confidence": 0.82
}
```

Answers are currently rendered in Chinese. Calling a protected endpoint without a
token returns `401`. CI re-runs this exact sequence on every push.

## Frontend (optional)

```bash
cd frontend && npm install && npm run dev
```
