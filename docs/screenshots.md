# Screens and output

> Ten screenshots, each captioned with what it proves rather than how it looks.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

All captured from a running instance, not mockups. The data comes from the
bundled synthetic examples and contains no real business information.

## Workbench: what to do next, in one screen

![Workbench](images/06-workbench.png)

Action items are ordered blockers-first and each one links to the screen that
resolves it. Every figure is a read-only projection of existing tables, so the
workbench cannot disagree with the screens it summarises.

## Semantic Q&A: verdict, governing rules, evidence

![Semantic Q&A with evidence](images/01-semantic-qa-with-evidence.png)

Answers come back structured, not as a paragraph of prose: a bolded conclusion,
one bullet per rule carrying the rule code (`clause_content_required`) so it can
be looked up, and result distributions as tables. Answers render as Markdown, so
which rule fired, why, and what the verdict is stay distinguishable.

The agent role shown ("设备运维业务专家", equipment-maintenance expert) is derived
at runtime from the onboarded domain; no industry roles are built in.

## Data source onboarding and metadata scan

![Data source onboarding](images/02-data-source-onboarding.png)

Tables, columns, types, foreign keys, enum candidates and a readiness score,
scanned from an existing database. The password segment of the connection string
is redacted.

## Domain ontology and business objects

![Ontology objects](images/03-ontology-objects.png)

## Governance and the release gate

![Governance and release gate](images/04-governance-release-gate.png)

Publishing is refused while blocking gates are open; a `force` override is
written to the audit log together with the count of failed gates.

## Roles and object permissions

![Roles and permissions](images/05-roles-and-permissions.png)

> ⚠️ The row-filter expression field visible here is **stored but inert** --
> `check_permission` returns it verbatim and applies no filtering. See
> [Current limitations](../README.md#current-limitations).

## Knowledge graph preview

![Knowledge graph preview](images/07-knowledge-graph.png)

An ontology is a graph, but every other screen renders it as tables, which hides
the problems a reviewer needs to see: isolated objects nothing points at,
self-referencing hierarchies, and clusters that produce no verdict. Colour encodes
a diagnosis rather than decoration -- red for unbound to a source table, amber for
carries no rules. The relation-expressiveness limitation is stated in the view
itself: `relation_type` is always `references`, with no cardinality and no
many-to-many.

## Document knowledge base

![Document knowledge base](images/09-knowledge-base.png)

Policy and contract clauses are split on their numbering (`第3.2条`, `3.1`,
`一、`, `Article 7`), preserving a locator a human can quote. Two governance
constraints are enforced by the workflow:

1. **Entries are pending by default and are not retrievable until confirmed.** A
   mis-split clause that silently became judgement evidence would produce a
   verdict that looks sourced but is not -- worse than no citation.
2. **Confirming requires an anchor** (business object or rule). Unanchored text
   cannot answer "why does this passage support this verdict".

Retrieval narrows by anchor *before* ranking, which is the opposite of searching
everything and inspecting the hits. That ordering is what makes a citation
attributable rather than merely similar.

## Feedback loop

![Feedback loop](images/10-feedback-loop.png)

Ratings attach to a specific message and its decision record -- "this verdict is
wrong" is only actionable when you know which verdict.

Two deliberate omissions: there is no average satisfaction score, because an
average does not tell you which answer to fix; and there is no one-click "apply
correction", because a correction is one user's claim rather than a new rule, and
promoting it goes through governance (ADR-0002).

## Model configuration for custom endpoints

![Model configuration](images/08-model-config.png)

The platform speaks the OpenAI chat-completions protocol, so any service
implementing it works. A configurable base URL alone is not enough, because
providers differ in how they pass credentials and which extra body fields they
tolerate:

| Setting | Problem it solves |
|---|---|
| Auth style (bearer / api-key / custom / none) | Azure uses an `api-key` header; local servers often need no key |
| Provider extras toggle | vLLM and LM Studio reject unknown body fields with a 400 |
| Extra headers (JSON) | Some gateways require a tenant or group identifier |

Presets ship for OpenRouter, OpenAI, relay gateways, Azure, self-hosted vLLM and
DashScope, and the screen shows the full URL that will actually be called.
