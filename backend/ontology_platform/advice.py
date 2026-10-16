"""Advice: what to do next, named as well as said.

Every advice list in this platform is *derived* from findings that already carry a code -- a
readiness check, a coverage gap, a drift impact, an API binding. The lists were emitted as bare
Chinese sentences, which left a bilingual console with nothing to key a translation on: it
received 「优先审核待确认语义映射，提升证据确定性。」 and could only print it.

So a list is emitted twice, from one expression:

    "nextActions": ["优先审核待确认语义映射，提升准确性。"],
    "nextActionCodes": ["coverage_pending_mappings"],

The sentences stay for the CLI and for clients that do not know the codes. The codes are what
the console says in the reader's language, and `tests/test_ui_messages.py` holds its dictionary
to the registry below -- in both directions, because a code the console cannot name is a
Chinese sentence in an English panel, and a code nothing emits is a sentence nobody will read.

## Why codes beside the text rather than objects in place of it

Replacing the strings with `{code, text}` objects is the tidier shape and it breaks readers for
no gain: the CLI prints these lists, the scaffold's generated code reads them, and neither
wants to know about a console's languages. Two fields from one list cannot drift the way two
lists can -- both come out of `split` below, which is the only thing that builds either.
"""

from __future__ import annotations

__all__ = ["ADVICE_CODES", "PAIRS", "RECOMMENDATION_TEXTS", "recommendation_code", "split"]

# Readiness. The codes are the ones the checks themselves carry
# (`metadata.assess_data_source_readiness`), because the failing check *is* the finding: giving
# the advice its own spelling would be a second name for the same thing, and the one that gets
# updated when a check is renamed would be the wrong one.
READINESS_CONNECTION = "connection"
READINESS_METADATA_SCAN = "metadata_scan"
READINESS_PRIMARY_KEYS = "primary_keys"
READINESS_RELATIONS = "relations"
READINESS_ONTOLOGY = "ontology"
READINESS_MAPPING_GOVERNANCE = "mapping_governance"
READINESS_API_GATEWAY = "api_gateway"
READINESS_BUSINESS_APIS = "business_apis"

# Structural drift, and what to do about each kind.
DRIFT_RESCAN = "drift_rescan"
DRIFT_REVIEW = "drift_review"
DRIFT_DERIVE = "drift_derive"
DRIFT_MODEL_ADDITIONS = "drift_model_additions"
DRIFT_IN_SYNC = "drift_in_sync"

# Semantic coverage.
COVERAGE_SCAN_FIRST = "coverage_scan_first"
COVERAGE_PENDING_MAPPINGS = "coverage_pending_mappings"
COVERAGE_MISSING_RULES = "coverage_missing_rules"
COVERAGE_REGISTER_APIS = "coverage_register_apis"
COVERAGE_SEMANTIC_ACTIONS = "coverage_semantic_actions"
COVERAGE_INSTANCE_KEYS = "coverage_instance_keys"
COVERAGE_CLOSED_LOOP = "coverage_closed_loop"

# Declared but never scanned.
SCAN_METADATA_FIRST = "scan_metadata_first"

# The consistency report's advice, one branch of `_consistency_next_actions` each.
CONSISTENCY_NO_INSTANCES = "consistency_no_instances"
CONSISTENCY_ALL_PASSED = "consistency_all_passed"
CONSISTENCY_NOT_ALL_PASSED = "consistency_not_all_passed"
CONSISTENCY_ERRORS_FIRST = "consistency_errors_first"
CONSISTENCY_TOP_FAILING_RULE = "consistency_top_failing_rule"
CONSISTENCY_BLOCKED = "consistency_blocked"
CONSISTENCY_MIXED = "consistency_mixed"

# The explanation an instance carries, one sentence each. They are joined into a paragraph,
# which is why they are pairs: the console composes the paragraph, the CLI prints it.
EXPLAIN_MAPPED_TO_SOURCE = "explain_mapped_to_source"
EXPLAIN_AS_OF = "explain_as_of"
EXPLAIN_DERIVED_ATTRIBUTES = "explain_derived_attributes"
EXPLAIN_DECLARED_UNITS = "explain_declared_units"
EXPLAIN_AGGREGATES = "explain_aggregates"
EXPLAIN_AGGREGATE_TRUNCATED = "explain_aggregate_truncated"

# The verdict's own recommendation, one branch of `_decision_from_results` each.
RECOMMENDATION_BLOCKED_UNEVALUABLE = "recommendation_blocked_unevaluable"
RECOMMENDATION_BLOCKED = "recommendation_blocked"
RECOMMENDATION_REVIEW_UNEVALUABLE = "recommendation_review_unevaluable"
RECOMMENDATION_REVIEW = "recommendation_review"
RECOMMENDATION_APPROVED = "recommendation_approved"

# Operation bindings, which decide whether automation may run.
BINDINGS_INVALID_ACTIONS = "bindings_invalid_actions"
BINDINGS_UNBOUND_OBJECTS = "bindings_unbound_objects"
BINDINGS_INCOMPLETE = "bindings_incomplete"
BINDINGS_REGISTER_APIS = "bindings_register_apis"
BINDINGS_READY = "bindings_ready"

ADVICE_CODES = (
    READINESS_CONNECTION,
    READINESS_METADATA_SCAN,
    READINESS_PRIMARY_KEYS,
    READINESS_RELATIONS,
    READINESS_ONTOLOGY,
    READINESS_MAPPING_GOVERNANCE,
    READINESS_API_GATEWAY,
    READINESS_BUSINESS_APIS,
    DRIFT_RESCAN,
    DRIFT_REVIEW,
    DRIFT_DERIVE,
    DRIFT_MODEL_ADDITIONS,
    DRIFT_IN_SYNC,
    COVERAGE_SCAN_FIRST,
    COVERAGE_PENDING_MAPPINGS,
    COVERAGE_MISSING_RULES,
    COVERAGE_REGISTER_APIS,
    COVERAGE_SEMANTIC_ACTIONS,
    COVERAGE_INSTANCE_KEYS,
    COVERAGE_CLOSED_LOOP,
    SCAN_METADATA_FIRST,
    BINDINGS_INVALID_ACTIONS,
    BINDINGS_UNBOUND_OBJECTS,
    BINDINGS_INCOMPLETE,
    BINDINGS_REGISTER_APIS,
    BINDINGS_READY,
    CONSISTENCY_NO_INSTANCES,
    CONSISTENCY_ALL_PASSED,
    CONSISTENCY_NOT_ALL_PASSED,
    CONSISTENCY_ERRORS_FIRST,
    CONSISTENCY_TOP_FAILING_RULE,
    CONSISTENCY_BLOCKED,
    CONSISTENCY_MIXED,
    RECOMMENDATION_BLOCKED_UNEVALUABLE,
    RECOMMENDATION_BLOCKED,
    RECOMMENDATION_REVIEW_UNEVALUABLE,
    RECOMMENDATION_REVIEW,
    RECOMMENDATION_APPROVED,
    EXPLAIN_MAPPED_TO_SOURCE,
    EXPLAIN_AS_OF,
    EXPLAIN_DERIVED_ATTRIBUTES,
    EXPLAIN_DECLARED_UNITS,
    EXPLAIN_AGGREGATES,
    EXPLAIN_AGGREGATE_TRUNCATED,
)

# The kernel's recommendation sentences, by code. They live here rather than beside the
# decision that chooses them because two modules need them: `semantic_kernel` writes one when a
# verdict is reached, and `decisions` reads one back for records written before the code was
# stored -- a deployment that upgrades should not have its older decisions turn Chinese in the
# English console.
RECOMMENDATION_TEXTS = {
    RECOMMENDATION_APPROVED: "未发现阻断或风险规则，允许进入后续自动化流程。",
    RECOMMENDATION_REVIEW: "存在风险或警告，应进入人工复核或触发后续治理流程。",
    RECOMMENDATION_REVIEW_UNEVALUABLE: (
        "部分规则无法在当前数据结构上求值，已按未通过处理，应人工复核规则表达式与来源字段后再恢复自动化。"
    ),
    RECOMMENDATION_BLOCKED: "存在阻断级规则未通过，应暂停自动化操作并要求业务人员复核。",
    RECOMMENDATION_BLOCKED_UNEVALUABLE: (
        "存在阻断级规则未通过，且部分规则无法求值（可能由结构漂移导致）。"
        "应暂停自动化操作，先修复规则表达式或来源字段映射。"
    ),
}

_BY_SENTENCE = {sentence: code for code, sentence in RECOMMENDATION_TEXTS.items()}


def recommendation_code(sentence: str) -> str:
    """The code for a recommendation written before codes were stored, or "".

    An exact match against this platform's own sentences -- not a heuristic over Chinese text.
    These strings are written by `_decision_from_results` and by nothing else, so a match is an
    identification rather than a guess; anything that does not match keeps the empty code and
    the console falls back to the sentence it was given.
    """
    return _BY_SENTENCE.get(sentence, "")


# One piece of advice: its code, and the sentence a reader who does not know the code gets.
PAIRS = list[tuple[str, str]]


def split(actions: PAIRS) -> tuple[list[str], list[str]]:
    """The two halves of an advice list: the sentences, and the codes beside them.

    Returned in that order because `nextActions` is the field the CLI and the tests already
    read, and it should stay the one that is easy to reach for.
    """
    return [text for _code, text in actions], [code for code, _text in actions]
