# Design decisions

> The key trade-offs, each covered by a test; full records in the ADRs.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

Full records, including rejected alternatives, in [`docs/adr/`](adr/).

**1. Fail-closed rules.** An expression that cannot be evaluated counts as *not
passed*, never as passed. A renamed column would otherwise silently disable a
blocking rule, let preflight through, and let automation continue — the very scenario
drift detection claims to prevent.
[ADR-0002](adr/0002-rule-engine-fail-closed.md)

**2. Enforced release gate.** Publishing is refused while blocking gates are open;
`force` is recorded in the audit log with the blocker count. Auto-generated drafts are
not production truth.

**3. No built-in domain vocabulary.** Any shipped word list degrades the platform into
a single-industry product. Terms enter only through metadata scanning and
user-imported blueprints. The cost: without a blueprint, draft labels are raw column
names. Ugly but correct beats pretty but only correct for two industries.
[ADR-0003](adr/0003-no-builtin-domain-vocabulary.md)

**4. An explicit ceiling on semantic generality: no full OWL/DL reasoning.** A DL
reasoner's conclusions are products of global entailment and cannot be explained as
"because §3.2", which is directly opposed to verifiability. Generality comes from
structural expressiveness plus escape hatches, not from inference. Open-world
assumption is also wrong here: no payment row means unpaid, not "unknown".
[ADR-0005](adr/0005-semantic-generality-ceiling.md)

**5. Relations are classified from declared structure, never from data.** A relation
inferred from a sample changes meaning when the data changes, and a verdict citing it
would be unreproducible. Every classification records the structural fact it rests on,
because a classification with no stated basis cannot be reviewed.
[ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md)

**6. Aggregates are declared data, not inline joins.** The answer to "why" has to be a
definition an operator can read, review and export -- not a query nobody looked at. An
aggregate that cannot be computed makes its rule fail rather than compare a threshold
against a fabricated zero.
[ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md)

**7. Units convert within a dimension and are refused across.** Without units, mixing
万元 and 元 makes `amount 500 > limit 1000000` report "within limit" — a wrong verdict
produced from correct data. Cross-dimension conversion raises instead of quietly passing
the number through, because comparing a duration to a mass is a modelling error.
Exchange rates stay out: a rate is time-varying data, and embedding one would make a
verdict unreproducible.
[ADR-0013](adr/0013-derived-attributes-and-units.md)

**8. Rule overrides are declared, not inferred from a name collision.** A collision is
ambiguous — two teams can pick the same code by accident, and inference would silently
disable one team's control. Weakening an inherited rule is allowed, because legitimate
business exceptions exist; weakening it *invisibly* is not.
[ADR-0014](adr/0014-type-hierarchy-and-business-events.md)

**9. Events are records, never triggers.** An event that could fire automation would
make the audit trail load-bearing for side effects, so replaying history — backfilling,
correcting, migrating — would re-execute business actions. The stream is append-only for
the same reason: a wrong event is corrected by a compensating one, because deleting
would leave a state with no explanation for how it was reached.
[ADR-0014](adr/0014-type-hierarchy-and-business-events.md)
