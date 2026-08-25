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

**Sources are not limited to databases.** When production credentials are weeks away, an
extract or an API runs the same pipeline:

```bash
aletheia connect /path/to/extract --type csv --domain 合同管理   # a directory of CSVs
aletheia doctor        # available source types, and which driver the inactive ones need
```

Oracle / SQL Server / 达梦 / 人大金仓 / openGauss ship as declarations with their dialects;
installing the driver makes them appear. Adding a SQL database that is *not* declared does
not require writing an adapter — four lines of declaration, see
[the extension guide](extending.md#10-接一个新的-sql-数据库).

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
