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

__all__ = ["ADVICE_CODES", "PAIRS", "split"]

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
)

# One piece of advice: its code, and the sentence a reader who does not know the code gets.
PAIRS = list[tuple[str, str]]


def split(actions: PAIRS) -> tuple[list[str], list[str]]:
    """The two halves of an advice list: the sentences, and the codes beside them.

    Returned in that order because `nextActions` is the field the CLI and the tests already
    read, and it should stay the one that is easy to reach for.
    """
    return [text for _code, text in actions], [code for code, _text in actions]
