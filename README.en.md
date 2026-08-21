# Aletheia

> Surface the business semantics buried in your schema, and make every verdict verifiable.

[![CI](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml/badge.svg)](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

English | [简体中文](README.md)

Aletheia (ἀλήθεια) is the ancient Greek word for truth and the name of its goddess.
Literally it means **"un-concealment" — making hidden things appear**. That is the
job here: business meaning is buried in table names, columns and foreign keys, and
Aletheia surfaces it as a governed domain ontology where every verdict can be checked.

Its mythological opposite is Pseudologoi, the spirit of lies — plausible speech that
cannot be verified. That is precisely the problem this project exists to solve.

---

## The problem

General RAG frameworks optimise for whether retrieved text *looks like* an answer.
Aletheia optimises for whether **an answer can withstand being questioned**.

For decisions about entitlements, amounts, compliance or approvals, an answer that
merely looks right is worthless, because nobody can sign off on it. Every verdict
here carries four things:

| | Source |
|---|---|
| **Verdict** — order A123 does not qualify for a refund | rule engine |
| **Governing rule** — `refund_window_check` | business rule definition |
| **Evidence** — delivered 2026-07-28, 24 days ago, past the 15-day window | structured query |
| **Decision record** — a persisted `decision_record`, auditable and attributable | decision trail |

The target is a support reply like:

> "Order A123 does not qualify for a refund: it was delivered more than 15 days ago
> (rule `refund_window_check`), per After-Sales Policy §3.2."

"more than 15 days" comes from a structured query, "does not qualify" from the rule
engine, "§3.2" from document retrieval.

**The first two work today. The third does not.** Document retrieval is not
implemented — see [Current limitations](#current-limitations). This project will not
use phrasing like "knowledge-base Q&A" to imply document RAG it does not have.

The difference from Dify / FastGPT / LangChain is not retrieval quality. It is
whether a conclusion can be interrogated.

## Quick start

Requires Python 3.9+ (Node.js 18+ for the frontend). Every command below was run in
a clean clone.

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git && cd Aletheia-onto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ONTOLOGY_ADMIN_PASSWORD=change-me-please .venv/bin/python -m uvicorn \
    ontology_platform.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then:

- Health check `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- API docs `http://127.0.0.1:8000/docs`

The default platform database is SQLite, so **no external database service is
needed**. If `ONTOLOGY_ADMIN_PASSWORD` is unset, a random admin password is generated
and printed to the startup log.

### Log in and ask one question

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

### Frontend (optional)

```bash
cd frontend && npm install && npm run dev
```

## Capability matrix

✅ implemented and covered by tests　⚠️ partially implemented (logic inert)　📋 planned (no implementation)

| Capability | Status | Location |
|---|:--:|---|
| SQLite / MySQL / PostgreSQL source adapters | ✅ | `adapters.py` |
| Metadata scan, column profiling, enum detection, foreign keys | ✅ | `metadata.py` |
| Structural drift comparison | ✅ | `metadata.py` |
| OpenAPI import of business operations | ✅ | `operation_bindings.py` |
| All three dialects as the platform's own store | ✅ | `database.py` |
| Ontology drafting from blueprints | ✅ | `ontology.py` |
| AST-allowlist rule sandbox | ✅ | `semantic_kernel.py` |
| Fail-closed rule semantics | ✅ | `semantic_kernel.py` |
| Expression validation at write time | ✅ | `governance.py` |
| Mapping review, version publish, derive | ✅ | `governance.py` |
| Release-readiness gate (force is audited) | ✅ | `release_readiness.py` |
| Four-layer decision trail | ✅ | `decisions.py` |
| Token auth (PBKDF2-SHA256, digest-only storage) | ✅ | `auth.py` |
| 6 capabilities × 6 roles, central route policy | ✅ | `access_policy.py` |
| Audit actor taken from identity, never client-supplied | ✅ | `api.py` |
| Credential redaction | ✅ | `credentials.py` |
| Domain neutrality (no built-in industry vocabulary) | ✅ | `vocabulary.py` |
| Natural-language semantic Q&A | ✅ | `natural_language.py` |
| Agent roles derived from onboarded domains | ✅ | `agent_roles.py` |
| Operation preflight and HTTP writeback | ✅ | `automation.py` |
| JSON-LD / Turtle export | ✅ | `ontology.py` |
| Workflow `guard_expression` | ⚠️ | stored and exposed, **never evaluated** |
| Permission `filter_expression` | ⚠️ | stored, `check_permission` **returns it verbatim** |
| Rule `depends_on` | ⚠️ | read and written, **unused** during evaluation |
| Permission policy ontology dimension | ⚠️ | keyed on bare `object_code`; same-named objects **share a policy** |
| Manual CRUD for objects/attributes/relations | ⚠️ | no endpoints |
| List endpoint pagination | ⚠️ | mostly absent |
| Vector retrieval / embeddings / document RAG | 📋 | **none** |
| Document knowledge base | 📋 | none |
| Conversation persistence | 📋 | history passed in per call, not stored |
| Multi-tenancy | 📋 | 31 tables have no tenant concept |
| Channel integrations, scheduler, feedback loop | 📋 | none |
| Ontology import (SHACL / reasoner) | 📋 | export only |
| Cross-source entity resolution | 📋 | none |

## Current limitations

### Stored but inert

Most dangerous category: the API looks functional.

- `workflow_transition.guard_expression` is never evaluated on transition.
- `permission_policy.filter_expression` is returned verbatim; no row filtering.
  **Do not rely on it for data isolation.**
- `business_rule.depends_on` is unused; rules are ordered by `priority` only.
- `permission_policy` has no ontology dimension — two ontologies with the same
  object code share one policy row. **Known defect.**
- Deriving a new ontology version does not copy workflow configuration.
- `docs/02` documents Event and State; no such tables exist.

### Structural expressiveness ceiling

By design, not bugs. These are the next phase's work.

| Constraint | Location |
|---|---|
| `business_object.source_table_id` is a single FK: **one object, one table** | `database.py:363` |
| **Composite primary keys unsupported**, three explicit raises | `ontology.py:132`, `semantic_kernel.py:416`, `semantic_kernel.py:663` |
| `relation_type` is hardcoded `"references"`; **no cardinality, no many-to-many** | `ontology.py:606` |
| Only `table_to_object` and `column_to_attribute` mappings; **no value-domain mapping** | `ontology.py` |
| **No type hierarchy** (no parent_object / subclass / inherit) | — |
| Rules scope to a single object; **no cross-object aggregation** | `semantic_kernel.py` |
| `ALLOWED_RULE_FUNCTIONS` is frozen (5 functions); **third parties cannot register** | `semantic_kernel.py:113` |
| `get_adapter()` is a hardcoded if/elif; `access_policy.RULES` is a static tuple | `adapters.py:74` |
| Writeback executor supports HTTP/HTTPS only | `automation.py` |

### Engineering limitations

- No connection pooling; no unified transaction boundary across `connect()` calls.
- `api.py` holds 98 endpoints in one file, with no `/v1` prefix.
- `frontend/src/types/index.ts` hand-mirrors backend models in 889 lines.
- DDL is duplicated across 4 modules, each hand-writing three dialects.

See [`docs/architecture-debt.md`](docs/architecture-debt.md) for located details and
[`ROADMAP.md`](ROADMAP.md) for sequencing and blockers.

## Design decisions

Full records, including rejected alternatives, in [`docs/adr/`](docs/adr/).

**1. Fail-closed rules.** An expression that cannot be evaluated counts as *not
passed*, never as passed. A renamed column would otherwise silently disable a
blocking rule, let preflight through, and let automation continue — the very scenario
drift detection claims to prevent.
[ADR-0002](docs/adr/0002-rule-engine-fail-closed.md)

**2. Enforced release gate.** Publishing is refused while blocking gates are open;
`force` is recorded in the audit log with the blocker count. Auto-generated drafts are
not production truth.

**3. No built-in domain vocabulary.** Any shipped word list degrades the platform into
a single-industry product. Terms enter only through metadata scanning and
user-imported blueprints. The cost: without a blueprint, draft labels are raw column
names. Ugly but correct beats pretty but only correct for two industries.
[ADR-0003](docs/adr/0003-no-builtin-domain-vocabulary.md)

**4. An explicit ceiling on semantic generality: no full OWL/DL reasoning.** A DL
reasoner's conclusions are products of global entailment and cannot be explained as
"because §3.2", which is directly opposed to verifiability. Generality comes from
structural expressiveness plus escape hatches, not from inference. Open-world
assumption is also wrong here: no payment row means unpaid, not "unknown".
[ADR-0005](docs/adr/0005-semantic-generality-ceiling.md)

## Roles and capabilities

Six capabilities across six roles. The central route-to-capability table lives in
`access_policy.py`, and **unlisted routes default to admin-only**.

| Role | `platform:read` | `platform:write` | `governance:review` | `governance:publish` | `automation:execute` | `platform:admin` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ontology_engineer` | ✅ | ✅ | | ✅ | | |
| `business_expert` | ✅ | ✅ | ✅ | | | |
| `operator` | ✅ | | | | ✅ | |
| `analyst` | ✅ | | | | | |
| `ai_agent` | ✅ | | | | | |

New users default to `analyst`. Tokens are stored as digests only; sessions expire and
can be revoked, and changing a password invalidates all existing sessions.

## Tests

```bash
.venv/bin/python -m pytest
```

**128 tests**, all passing:

| File | Count | Covers |
|---|--:|---|
| `test_metadata_flow.py` | 34 | onboarding, scanning, drafting, readiness |
| `test_api_authentication.py` | 26 | auth, sessions, capability policy, trusted actor |
| `test_domain_neutrality.py` | 25 | unknown domain end to end, plus static guards |
| `test_rule_engine_safety.py` | 17 | sandbox escapes, fail-closed, release gate |
| `test_platform_database_dialects.py` | 10 | all three dialects as platform store |
| `test_credential_protection.py` | 8 | connection string and API key redaction |
| `test_data_source_knowledge_base.py` | 8 | data source knowledge base |

Dialect tests skip automatically when no server is reachable, so CI without service
containers stays green rather than falsely red.

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## Scale

29 backend modules, roughly 13,400 lines, 98 API endpoints, 31 platform tables,
React + antd frontend.

## Examples

[`examples/contract-system/`](examples/contract-system/) is a minimal contract system
standing in for a legacy application. **All company names, contacts, phone numbers,
emails and credit codes in it are synthetic placeholders** and correspond to no real
entity.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Two hard rules:

1. **Never make a test pass by editing its assertions.**
2. **Documentation may only describe capabilities that exist and are covered by tests.**

Report security issues privately per [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE), including the patent grant.
