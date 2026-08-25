<div align="center">

# Aletheia

**A verifiable semantic kernel for legacy business systems.**

Turn the meaning buried in your database schema into a governed domain ontology —
and make every verdict answer *why*.

[![CI](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml/badge.svg)](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1348%20passing-brightgreen.svg)](docs/testing.md)

English · [简体中文](README.zh-CN.md)

</div>

---

## Why Aletheia

Retrieval frameworks optimise for *"does this look like an answer"*.
Aletheia optimises for **"can this answer be questioned"**.

For decisions about entitlements, money, compliance or approvals, an answer that merely
looks right is worthless — nobody can sign off on it. So every verdict carries four things:

| | Comes from |
|---|---|
| **Verdict** — order A123 does not qualify for a refund | rule engine |
| **Governing rule** — `refund_window_check` | business rule definition |
| **Evidence** — delivered 2026-07-28, 24 days ago, past the 15-day window | structured query |
| **Decision record** — a persisted `decision_record`, auditable and attributable | decision trail |

```
「Order A123 does not qualify for a refund: delivered more than 15 days ago
 (rule refund_window_check), per Article 3.2 of the After-Sales Policy.」
```

"More than 15 days" comes from a structured query. "Does not qualify" comes from the rule
engine. "Article 3.2" comes from document retrieval, anchored to that rule and confirmed
through governance before it can be cited.

**The difference from Dify / FastGPT / LangChain is not retrieval quality — it is whether
the conclusion can be interrogated.** Retrieval precision is an explicit non-goal.

<div align="center">

![Semantic Q&A with evidence](docs/images/01-semantic-qa-with-evidence.png)

*A verdict with its intent, confidence, recommended action and semantic evidence.*

</div>

## Quick start

```bash
pip install aletheia-onto     # dependency-free kernel
aletheia demo                 # connect → model → assess, in one command
```

```json
{ "ontologyId": 1, "objectCode": "contract", "decision": "approved" }
```

Point it at your own system:

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain contracts
aletheia model 1                  # scan metadata, draft an ontology
aletheia assess 1 contract 1      # produce a verifiable verdict for one instance
```

Scaffold a project that depends on the platform — **not a fork**, so upgrading is
`pip install -U aletheia-onto`:

```bash
aletheia new --list-extensions
aletheia new mycorp --extension rule-function --domain contracts
cd mycorp && pip install -e . && python -m mycorp init
```

→ **[Full quick start](docs/quickstart.md)** · [Configuration](docs/configuration.md)

## What you get

| | |
|---|---|
| 🔍 **Metadata onboarding** | Scan any SQL database, a CSV directory, or a REST/OpenAPI service. Oracle, SQL Server, DamengDB, KingbaseES and openGauss ship as declarations — a new SQL engine needs 4 lines, not an adapter. |
| 🧩 **Closed metamodel** | Entity types, data properties, object properties, **axioms** and rules — the five components of GB/T 48000.3—2026. Plus subtype hierarchies, cross-object aggregates, derived attributes with units, business events and attribute-level temporal validity. |
| ⚖️ **Fail-closed rule engine** | AST-whitelisted sandbox. An expression that cannot be evaluated is a **failed** verdict, never a skipped one — a renamed column must not silently disable a blocking control. |
| 📋 **Governance gates** | Publishing is refused while mappings await review, and `--force` **cannot** skip that. Axiom violations block publication: a self-contradictory model makes every verdict it produces suspect. |
| 🔗 **Standard vocabulary** | Export OWL/RDFS and SHACL that external tools can *interpret*, not merely parse — an outside SPARQL query can answer "which class may relate to which". |
| 🔐 **Multi-tenant & SSO** | Separate schema plus a `tenant_id` column, quotas the tenant cannot raise, and JWT SSO where an unmapped identity gets **no** access rather than a default role. |
| 🛡️ **Deployment preflight** | `aletheia preflight` blocks the silent misconfigurations: a leftover auth switch, a wildcard CORS, SQLite with multiple workers. `serve` refuses to expose an unsafe config. |
| 🧾 **Audit reports** | Which published rules **never fired** this period, which publications overrode the gate, and how much of the period is re-examinable at all. |

→ **[Full capability matrix](docs/capabilities.md)** · [Current limitations](docs/limitations.md)

## Where to go

| I want to… | Go to |
|---|---|
| See what it produces | [Screenshots](docs/screenshots.md) |
| Install and run it once | [Quick start](docs/quickstart.md) |
| Know exactly how far it got | [Capability matrix](docs/capabilities.md) · [Limitations](docs/limitations.md) |
| Understand the model | [Core concepts](docs/concepts.md) · [Architecture](docs/architecture.md) |
| Plug in a database / rule function / retrieval backend | [Extension guide](docs/extending.md) |
| Connect Azure OpenAI, vLLM or a gateway | [Model endpoints](docs/model-endpoints.md) |
| Ship to production | [Self-hosted deployment](docs/deployment.md) |
| Know why a design is the way it is | [Design decisions](docs/design-decisions.md) · [All ADRs](docs/adr/) |
| Check GB/T 48000.3—2026 alignment | [ADR-0019](docs/adr/0019-axioms-and-standard-vocabulary.md) |
| Contribute | [CONTRIBUTING](CONTRIBUTING.md) · [ROADMAP](ROADMAP.md) |

## What this is not

Stated plainly, because it builds more trust than a feature list.

| Not doing | Why |
|---|---|
| Full OWL/DL reasoning, open-world assumption | At odds with verifiability — a conclusion reached by subsumption cannot be traced to a declaration a human made ([ADR-0005](docs/adr/0005-semantic-generality-ceiling.md)) |
| A general graph database / arbitrary triple store | Cannot guarantee every conclusion has an explainable source |
| Rewriting your legacy code automatically | Uncontrollable risk, and not a semantic kernel's job |
| A general-purpose ETL platform | We read metadata; we do not move data |
| A drag-and-drop workflow engine | Workflow exists to serve ontology instance state transitions |
| State-of-the-art retrieval precision | The moat is interrogability, not recall |

## Project status

1348 tests, green on Python 3.11 / 3.12 / 3.13. The kernel has **zero third-party
dependencies** — verified in CI on a bare install, so the ontology, rule engine and
decision records can be embedded in someone else's application.

Every countable claim in this documentation is asserted by a test: the test count, the
per-file breakdown, the endpoint count, the supported Python versions, and the fact that
no link here is broken. A number nobody can verify is worse than no number.

**Stability:** extension points are experimental before 1.0; the *behaviour* the
conformance suites require is stable, its Python signatures are not
([ADR-0007](docs/adr/0007-extension-registry-without-api-stability.md)).

## The name

Aletheia (ἀλήθεια) is Ancient Greek for *truth*, and the name of its goddess. Literally it
means **un-concealment — making the hidden appear**. Business semantics lie buried in table
names, columns and foreign keys; Aletheia surfaces them as a governable ontology.

Its mythological opposite is Pseudologoi, the spirit of falsehood — speech that sounds
plausible and cannot be verified. That is the problem this project exists to solve.

## License

[Apache-2.0](LICENSE)
