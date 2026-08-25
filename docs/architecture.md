# Architecture

> Layers and data flow. Every layer's status is checked against the code — an architecture
> diagram that labels a shipped capability "planned" makes a reader design around its
> absence, or reject the project for lacking it.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

```mermaid
flowchart TB
    subgraph L1["Onboarding"]
        DS["Data source adapters<br/>SQLite / MySQL / PostgreSQL<br/>+ generic DB-API (Oracle / SQL Server / Dameng / Kingbase)"]
        FILE["File and API sources<br/>CSV directory / REST·OpenAPI"]
    end

    subgraph L2["Semantic kernel"]
        META["Metadata scan<br/>column profiling / enum detection / foreign keys / drift"]
        ONTO["Ontology modelling<br/>objects / attributes / relations (cardinality + strength)"]
        RESOLVER["Instance resolvers<br/>single table / master-detail join / discriminated / custom SQL"]
        META2["Metamodel expressiveness<br/>type hierarchy / cross-object aggregates / derived attributes + units<br/>business events / attribute-level temporality / axioms"]
        MAP["Semantic mappings<br/>table_to_object / column_to_attribute"]
        RULE["Rule engine<br/>AST-whitelisted sandbox / fail-closed"]
        XSRC["Cross-source resolution<br/>declared matching, never similarity"]
    end

    subgraph L3["Governance and trail"]
        GOV["Mapping review / version publishing<br/>release gate (pending mappings cannot be --forced)"]
        TRACE["Decision trail<br/>inference_result / explanation_trace<br/>decision_record / audit_log"]
        AUTH["Auth<br/>6 capabilities x 6 roles / central policy table / SSO"]
        TENANT["Multi-tenant isolation<br/>separate schema + tenant_id / quotas"]
        AUDIT["Audit reports<br/>never-fired rules / overridden gates / trace coverage"]
    end

    subgraph L4["Semantic services"]
        NL["Natural-language Q&A<br/>intent routing / instance resolution / cited answers"]
        KB["Document knowledge<br/>clause splitting / anchoring / retrieval-time permission filter"]
        AGENT["Agents<br/>roles derived from onboarded domains"]
        PRE["Operation preflight and writeback<br/>HTTP / direct SQL / stored procedures"]
        EXPORT["Semantic asset export<br/>JSON-LD / Turtle / OWL / SHACL"]
        GEN["Code generation<br/>TypeScript types and client from the ontology"]
    end

    subgraph L5["📋 Planned"]
        CHAN["Channel integrations<br/>WeCom / DingTalk / Feishu"]
        SCHED["Scheduler"]
        PKG["Split into multiple PyPI distributions"]
    end

    DS --> META --> ONTO
    FILE --> META
    ONTO --> RESOLVER --> RULE
    ONTO --> META2 --> RULE
    ONTO --> MAP --> GOV
    ONTO --> XSRC --> RULE
    RULE --> TRACE --> AUDIT
    GOV --> ONTO
    RULE --> NL
    KB --> NL --> AGENT
    RULE --> PRE
    ONTO --> EXPORT
    ONTO --> GEN
    AUTH -.->|cross-cutting| L4
    TENANT -.->|cross-cutting| L3
    CHAN -.->|planned| NL
```

## Three invariants

These decide why the architecture looks like this, rather than "the layers are tidy".

**A verdict must trace back to a declaration.** The rule engine evaluates declared rules
and infers nothing; relation semantics come from schema declarations and never from data
distribution. So every conclusion points back at something a human declared — which is also
why [full DL reasoning is refused](adr/0005-semantic-generality-ceiling.md).

**Failure to evaluate is a failed verdict.** An expression that cannot be evaluated becomes
"not passed, with a reason" rather than being skipped. A renamed column would otherwise
silently disable a blocking control — exactly the scenario drift detection claims to catch.

**Governance sits on the write path, not beside it.** Publishing is refused while mappings
await review, and `--force` cannot skip it; a knowledge entry cannot be retrieved until it
is confirmed and anchored. A gate that can be bypassed is only advice.

## Related

- [Core concepts](concepts.md) — ontology structure, legacy mapping, the verdict trail
- [Capability matrix](capabilities.md) — per-item status and location
- [Current limitations](limitations.md) — what it cannot do, and why
- [Architecture debt](architecture-debt.md) — remaining technical debt, located
