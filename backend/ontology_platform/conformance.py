"""Executable conformance suites for every extension point.

ROADMAP stage D, and the piece that makes the extension registries actually usable.

The registries have existed since ADR-0007, and the contracts each implementation must
satisfy were written down -- in ADR prose and in this repository's test files. Neither is
reachable by a third party: prose cannot be executed, and `tests/` is not in the wheel.
So an integrator could register an adapter and have **no way to find out whether it was
correct** short of running a real assessment and interpreting a wrong verdict.

That gap is also why stage D was stuck. It was recorded as "blocked on a second real use
case", but that is circular: nobody can build the second use case while verifying an
implementation requires reading our test suite. Shipping the contract breaks the loop.

## What a conformance suite is, and is not

It **is** the set of properties the platform genuinely relies on. Each check exists
because violating it produces a specific wrong outcome, and the failure message says
which -- an integrator should never have to guess why a rule matters.

It is **not** an API stability promise. The registries remain experimental (ADR-0007);
what is stable is the *behaviour* being demanded, not the signatures demanding it.

## Why not pytest

A third party's project may not use pytest, and requiring a test framework to validate a
plugin is a barrier for exactly the integrator who most needs the check. Each suite
returns structured results, so it can be called from a script, a CI step, a pytest test,
or `aletheia verify`.

## Round-trip properties get the most attention

The bugs that actually happen in adapters are not crashes -- they are asymmetries. A
resolver whose `list_ids()` emits tokens its own `fetch()` rejects passes every unit test
an author would think to write, and then silently returns nothing during batch
assessment. Those pairings are checked explicitly.

Stability: the suite's *findings* are meaningful; its Python signatures are experimental
(ADR-0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger(__name__)

# Severity of a finding. `required` failures mean the implementation will produce wrong
# results in normal operation; `advisory` ones mean it works but loses a capability.
REQUIRED = "required"
ADVISORY = "advisory"


@dataclass(frozen=True)
class Finding:
    """One conformance check and its outcome.

    `why` is not documentation -- it is the point. A failure that says
    "list_ids/fetch round trip failed" tells an author what broke; one that also says
    "batch assessment will silently return nothing" tells them why it matters, which is
    what gets it fixed rather than worked around.
    """

    check: str
    passed: bool
    severity: str = REQUIRED
    detail: str = ""
    why: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "why": self.why,
        }


@dataclass
class ConformanceReport:
    """The result of running one suite against one implementation."""

    suite: str
    subject: str
    findings: list[Finding] = field(default_factory=list)

    def record(
        self,
        check: str,
        passed: bool,
        *,
        severity: str = REQUIRED,
        detail: str = "",
        why: str = "",
    ) -> None:
        self.findings.append(Finding(check=check, passed=passed, severity=severity, detail=detail, why=why))

    @property
    def failures(self) -> list[Finding]:
        """Required checks that failed. Advisory failures are excluded deliberately:
        conflating "will produce wrong results" with "loses a capability" makes the
        report unusable for deciding whether to ship."""
        return [finding for finding in self.findings if not finding.passed and finding.severity == REQUIRED]

    @property
    def advisories(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.passed and finding.severity == ADVISORY]

    @property
    def conformant(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "subject": self.subject,
            "conformant": self.conformant,
            "checked": len(self.findings),
            "failures": [finding.as_dict() for finding in self.failures],
            "advisories": [finding.as_dict() for finding in self.advisories],
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def summary(self) -> str:
        """A one-line verdict plus each failure's reason, for a CLI or a CI log."""
        if self.conformant:
            extra = f"，{len(self.advisories)} 项建议" if self.advisories else ""
            return f"✓ {self.subject} 通过 {self.suite} 契约（{len(self.findings)} 项检查{extra}）"
        lines = [f"✗ {self.subject} 未通过 {self.suite} 契约，{len(self.failures)} 项必需检查失败:"]
        for finding in self.failures:
            lines.append(f"  - {finding.check}: {finding.detail}")
            if finding.why:
                lines.append(f"    后果: {finding.why}")
        return "\n".join(lines)

    def raise_for_failures(self) -> "ConformanceReport":
        """Raise when a required check failed, for use in a test or a CI gate."""
        if not self.conformant:
            raise ConformanceError(self.summary())
        return self


class ConformanceError(AssertionError):
    """Raised when an implementation fails a required conformance check.

    Subclasses AssertionError so a pytest test that simply calls
    `raise_for_failures()` reports it the way it would report an assertion.
    """


def _guard(
    report: ConformanceReport,
    check: str,
    why: str,
    action: Callable[[], Optional[str]],
    *,
    severity: str = REQUIRED,
) -> bool:
    """Run one check, converting an exception into a finding.

    A conformance suite must not itself crash on a broken implementation: the whole
    point is to *report* what is wrong. `action` returns an error string, or None when
    the check passed.
    """
    try:
        detail = action()
    except Exception as error:
        report.record(check, False, severity=severity, detail=f"{type(error).__name__}: {error}", why=why)
        return False
    report.record(check, detail is None, severity=severity, detail=detail or "", why=why)
    return detail is None


# -- Instance resolvers ------------------------------------------------------


def check_instance_resolver(resolver: Any, runtime: Any, *, subject: str = "") -> ConformanceReport:
    """Verify a resolver against the properties assessment depends on (ADR-0011).

    `runtime` must be a live runtime for a data source holding at least one instance of
    the object the resolver resolves -- the checks are behavioural, and a resolver that
    only works on an empty source is not a resolver anyone can use.
    """
    report = ConformanceReport(suite="instance_resolver", subject=subject or type(resolver).__name__)

    for name in ("fetch", "list_ids", "columns"):
        report.record(
            f"实现 {name}()",
            callable(getattr(resolver, name, None)),
            detail="" if callable(getattr(resolver, name, None)) else f"缺少 {name}()",
            why="内核在建立运行时上下文时会调用这三个方法，缺一个就无法产出判定。",
        )
    if not report.conformant:
        # No point probing behaviour when the interface is absent; further checks would
        # produce confusing AttributeErrors that hide the real problem.
        return report

    ids: list[str] = []

    def list_ids_returns_strings() -> Optional[str]:
        nonlocal ids
        ids = list(resolver.list_ids(runtime, limit=5))
        if not ids:
            return "list_ids() 返回空列表（请对含至少一个实例的数据源运行本契约）"
        bad = [item for item in ids if not isinstance(item, str)]
        return f"list_ids() 返回了非字符串 token: {bad[:3]}" if bad else None

    _guard(
        report,
        "list_ids() 返回字符串 token",
        "token 会进入 URL、判定记录与审计行；非字符串会在序列化时才暴露，而那已经在判定之后。",
        list_ids_returns_strings,
    )

    def round_trip() -> Optional[str]:
        if not ids:
            return "没有可用 token，无法验证往返"
        failed = [token for token in ids if resolver.fetch(runtime, token) is None]
        return f"以下 token 无法被 fetch() 接受: {failed[:3]}" if failed else None

    _guard(
        report,
        "list_ids() 的 token 能被 fetch() 接受",
        "批量研判先列 token 再逐个 fetch。往返不闭合时批量研判静默地什么都不返回——"
        "这是自定义解析器最常见也最难发现的错误。",
        round_trip,
    )

    def fetch_returns_mapping() -> Optional[str]:
        if not ids:
            return "没有可用 token"
        record = resolver.fetch(runtime, ids[0])
        if not isinstance(record, dict):
            return f"fetch() 返回了 {type(record).__name__}，应为 dict 或 None"
        return None if record else "fetch() 返回了空 dict"

    _guard(
        report,
        "fetch() 返回完整记录",
        "规则按名字读取字段。返回空或非映射会让每条规则以 NameError fail-closed，把接线问题变成业务违规（ADR-0002）。",
        fetch_returns_mapping,
    )

    def missing_instance_is_none() -> Optional[str]:
        sentinel = "__aletheia_conformance_absent__"
        result = resolver.fetch(runtime, sentinel)
        return None if result is None else f"不存在的实例返回了 {type(result).__name__}，应为 None"

    _guard(
        report,
        "不存在的实例返回 None",
        "返回任意一行会让判定作用在错误的记录上，而结果看起来完全正常。",
        missing_instance_is_none,
    )

    def columns_cover_record() -> Optional[str]:
        if not ids:
            return "没有可用 token"
        declared = set(resolver.columns(runtime))
        record = resolver.fetch(runtime, ids[0]) or {}
        missing = sorted(set(record) - declared)
        return f"记录中存在未在 columns() 中声明的字段: {missing[:5]}" if missing else None

    _guard(
        report,
        "columns() 覆盖记录中的字段",
        "写规则时的字段校验依据 columns()。漏报字段会让一条本可执行的规则在写入时被拒绝。",
        columns_cover_record,
    )

    def tables_reported() -> Optional[str]:
        tables = getattr(resolver, "tables", None)
        if not callable(tables):
            return "未实现 tables()"
        reported = tables()
        if not isinstance(reported, (tuple, list)):
            return f"tables() 返回了 {type(reported).__name__}，应为元组或列表"
        return None if reported else "tables() 返回空"

    # Advisory, not required: a resolver over a non-table source -- an API, a computed set
    # -- legitimately has no tables to report, and demanding one would exclude a whole
    # class of valid implementation.
    _guard(
        report,
        "tables() 报告所读取的表",
        "漂移检测与血缘依赖它。未报告的表发生结构变化时不会被检测到，而基于它的判定仍在继续。"
        "（非表数据源可以合理地无表可报，因此仅为建议项）",
        tables_reported,
        severity=ADVISORY,
    )
    return report


# -- Data source adapters ---------------------------------------------------


def check_data_source_adapter(
    adapter: Any,
    connection_uri: str,
    *,
    subject: str = "",
    expected_table: str = "",
) -> ConformanceReport:
    """Verify an adapter against the properties onboarding and assessment depend on.

    `connection_uri` must point at a reachable source with at least one table and one
    row: the checks are behavioural, because the failures worth catching are behavioural.
    """
    report = ConformanceReport(suite="data_source_adapter", subject=subject or type(adapter).__name__)

    report.record(
        "声明 source_type",
        bool(getattr(adapter, "source_type", "")),
        detail="" if getattr(adapter, "source_type", "") else "缺少 source_type 属性",
        why="注册表与数据源登记都按 source_type 索引，缺失会让适配器无法被解析。",
    )
    for name in ("test_connection", "scan", "runtime"):
        present = callable(getattr(adapter, name, None))
        report.record(
            f"实现 {name}()",
            present,
            detail="" if present else f"缺少 {name}()",
            why="接入、扫描与运行时读取分别依赖这三个方法。",
        )
    if not report.conformant:
        return report

    def status_shape() -> Optional[str]:
        status = adapter.test_connection(connection_uri)
        if not isinstance(status, dict):
            return f"test_connection() 返回了 {type(status).__name__}，应为 dict"
        missing = sorted({"sourceType", "reachable", "status", "message"} - set(status))
        if missing:
            return f"缺少字段: {missing}"
        if not status["reachable"]:
            return f"连接不可达: {status.get('message')}"
        return None

    _guard(
        report,
        "test_connection() 返回约定形状且可达",
        "前端据此区分「缺驱动」与「连不上」。前者装个包就能解决，后者要查网络或凭据；"
        "合并成「失败」会把人引向错误的方向。",
        status_shape,
    )

    tables: list[Any] = []

    def scan_shape() -> Optional[str]:
        nonlocal tables
        tables = list(adapter.scan(connection_uri))
        if not tables:
            return "scan() 返回空（请对含至少一张表的数据源运行本契约）"
        for table in tables:
            for field_name in ("name", "row_count", "primary_key", "columns", "foreign_keys"):
                if not hasattr(table, field_name):
                    return f"表信息缺少 {field_name}"
        if expected_table and expected_table not in {table.name for table in tables}:
            return f"未扫描到预期的表 {expected_table}，实际: {sorted(t.name for t in tables)[:5]}"
        return None

    _guard(
        report,
        "scan() 返回 SourceTableInfo 序列",
        "本体草案、语义映射与关系推断都建立在扫描结果之上；字段缺失会让建模在更下游才失败。",
        scan_shape,
    )

    def columns_have_types() -> Optional[str]:
        if not tables:
            return "没有可检查的表"
        for table in tables:
            for column in table.columns:
                for field_name in ("name", "data_type", "nullable", "ordinal", "is_primary_key"):
                    if not hasattr(column, field_name):
                        return f"{table.name}.{getattr(column, 'name', '?')} 缺少 {field_name}"
        return None

    _guard(
        report,
        "列信息完整",
        "属性类型、必填性与主键标记直接决定生成的本体；缺失会静默降级为文本属性。",
        columns_have_types,
    )

    def runtime_reads() -> Optional[str]:
        if not tables:
            return "没有可检查的表"
        target = next((table for table in tables if table.row_count > 0), None)
        if target is None:
            return "没有任何非空表（请对含至少一行数据的数据源运行本契约）"
        primary_key = target.primary_key or "id"
        with adapter.runtime(connection_uri) as runtime:
            for name in ("browse_rows", "fetch_primary_keys", "fetch_one", "fetch_related_one", "fetch_related_many"):
                if not callable(getattr(runtime, name, None)):
                    return f"运行时缺少 {name}()"
            keys = list(runtime.fetch_primary_keys(target.name, primary_key, limit=3))
            if not keys:
                return f"fetch_primary_keys() 对非空表 {target.name} 返回空"
            record = runtime.fetch_one(target.name, primary_key, str(keys[0]))
            if not isinstance(record, dict) or not record:
                return f"fetch_one() 未能取回 {target.name} 的实例 {keys[0]}"
            rows, total = runtime.browse_rows(target.name, 1, 0)
            if not isinstance(rows, list) or not isinstance(total, int):
                return "browse_rows() 应返回 (list, int)"
        return None

    _guard(
        report,
        "运行时读取往返闭合",
        "fetch_primary_keys() 给出的键必须能被 fetch_one() 取回。不闭合时批量研判静默为空，"
        "而单实例研判看起来正常——这是最难定位的一类失败。",
        runtime_reads,
    )

    def foreign_keys_shape() -> Optional[str]:
        for table in tables:
            for key in table.foreign_keys:
                for field_name in ("column_name", "target_table", "target_column"):
                    if not hasattr(key, field_name):
                        return f"{table.name} 的外键缺少 {field_name}"
        return None

    _guard(
        report,
        "外键信息完整",
        "关系基数与强弱由外键结构推断（ADR-0012）。外键缺失不会报错，但生成的本体会没有任何关系。",
        foreign_keys_shape,
    )
    return report


# -- Retrieval backends and embedding models --------------------------------


# Domain-neutral on purpose (ADR-0003): a platform module must contain no industry
# vocabulary, or the neutrality guard in `tests/test_domain_neutrality.py` fails -- and it is
# right to. Terms like `alpha` carry no domain, and the checks only need *some* text with
# overlapping and non-overlapping tokens to exercise ranking.
_SAMPLE_ENTRIES: tuple[dict[str, Any], ...] = (
    {"id": 1, "title": "alpha limit", "content": "alpha 上限为一千。", "objectCode": "alpha"},
    {"id": 2, "title": "beta status", "content": "beta 状态为受限时需复核。", "objectCode": "beta"},
    {"id": 3, "title": "alpha plan", "content": "alpha 计划总额应等于 alpha 金额。", "objectCode": "alpha"},
)

# The query used by the ranking checks. Shares tokens with entries 1 and 3 but not 2, so a
# backend that ignores relevance entirely is still visible in the ordering check.
_SAMPLE_QUERY = "alpha 上限"


def check_retrieval_backend(
    backend: Callable[..., Any],
    *,
    subject: str = "",
    entries: Sequence[dict[str, Any]] = (),
) -> ConformanceReport:
    """Verify a ranking backend against the properties citation attribution depends on."""
    report = ConformanceReport(suite="retrieval_backend", subject=subject or getattr(backend, "__name__", "backend"))
    candidates = list(entries) or list(_SAMPLE_ENTRIES)

    hits: list[Any] = []

    def returns_hits() -> Optional[str]:
        nonlocal hits
        hits = list(backend(_SAMPLE_QUERY, candidates, 3))
        if not hits:
            return "对明显相关的查询返回空"
        for hit in hits:
            for field_name in ("entry_id", "score"):
                if not hasattr(hit, field_name):
                    return f"命中缺少 {field_name}（应为 RetrievalHit 或兼容对象）"
        return None

    _guard(
        report,
        "返回带 entry_id 与 score 的命中",
        "引用要靠 entry_id 归因到具体条目。缺失会让答案给不出依据，而这正是本平台与通用 RAG 的差别（ADR-0009）。",
        returns_hits,
    )

    def respects_limit() -> Optional[str]:
        limited = list(backend(_SAMPLE_QUERY, candidates, 1))
        return None if len(limited) <= 1 else f"limit=1 时返回了 {len(limited)} 条"

    _guard(
        report,
        "遵守 limit",
        "超限返回会让提示词超出模型上下文，表现为答案被截断而非报错。",
        respects_limit,
    )

    def stays_within_candidates() -> Optional[str]:
        allowed = {entry["id"] for entry in candidates}
        returned = {hit.entry_id for hit in hits}
        extra = sorted(returned - allowed)
        return f"返回了候选集之外的条目: {extra}" if extra else None

    _guard(
        report,
        "不越过候选集",
        "候选集已按本体锚点过滤。越界返回会绕过锚定，让答案引用与该对象无关的条目——这既是可解释性问题也是越权问题。",
        stays_within_candidates,
    )

    def scores_are_ordered() -> Optional[str]:
        scores = [float(hit.score) for hit in hits]
        return None if scores == sorted(scores, reverse=True) else f"命中未按分数降序: {scores}"

    _guard(
        report,
        "命中按分数降序",
        "上层按顺序截断。乱序会让最相关的条目被丢弃，而结果看起来仍然合理。",
        scores_are_ordered,
    )

    def empty_query_is_safe() -> Optional[str]:
        result = backend("", candidates, 3)
        return None if isinstance(result, list) else f"空查询返回了 {type(result).__name__}"

    _guard(
        report,
        "空查询不抛异常",
        "问答链路会传入未识别意图的空查询；抛异常会让整次问答失败而不是给出空结果。",
        empty_query_is_safe,
    )

    def no_candidates_is_safe() -> Optional[str]:
        result = backend(_SAMPLE_QUERY, [], 3)
        return None if isinstance(result, list) and not result else "空候选集应返回空列表"

    _guard(
        report,
        "空候选集返回空列表",
        "锚点过滤后候选集常常为空。此时应返回空而不是报错，否则「无相关文档」会变成一次故障。",
        no_candidates_is_safe,
    )
    return report


def check_embedding_model(model: Callable[[str], Sequence[float]], *, subject: str = "") -> ConformanceReport:
    """Verify an embedding function against the properties similarity scoring depends on."""
    report = ConformanceReport(suite="embedding_model", subject=subject or getattr(model, "__name__", "model"))

    vectors: dict[str, Sequence[float]] = {}

    def returns_numbers() -> Optional[str]:
        nonlocal vectors
        for text in (_SAMPLE_QUERY, "beta status", ""):
            vector = model(text)
            if not isinstance(vector, (list, tuple)):
                return f"对 {text!r} 返回了 {type(vector).__name__}，应为数值序列"
            bad = [value for value in vector if not isinstance(value, (int, float))]
            if bad:
                return f"向量含非数值元素: {bad[:3]}"
            vectors[text] = vector
        return None

    _guard(
        report,
        "返回数值向量",
        "余弦相似度按元素相乘。非数值元素会在检索时抛 TypeError，让整次问答失败。",
        returns_numbers,
    )

    def dimensions_are_stable() -> Optional[str]:
        sizes = {len(vector) for vector in vectors.values()}
        return None if len(sizes) == 1 else f"不同输入返回了不同维度: {sorted(sizes)}"

    _guard(
        report,
        "维度恒定",
        "维度不一致时相似度计算会静默返回 0，表现为「什么都不相关」而不是报错。",
        dimensions_are_stable,
    )

    def is_deterministic() -> Optional[str]:
        first = list(model(_SAMPLE_QUERY))
        second = list(model(_SAMPLE_QUERY))
        return None if first == second else "同一输入两次返回了不同向量"

    _guard(
        report,
        "确定性",
        "同一问题两次得到不同引用，判定就不可复现——而可核验性是本平台的立足点（ADR-0005）。",
        is_deterministic,
    )

    def empty_text_is_safe() -> Optional[str]:
        vector = model("")
        return None if isinstance(vector, (list, tuple)) else f"空文本返回了 {type(vector).__name__}"

    _guard(
        report,
        "空文本不抛异常",
        "条目内容可能为空。抛异常会让一条空条目破坏整次检索。",
        empty_text_is_safe,
    )
    return report


# -- Writeback executors ----------------------------------------------------


def check_writeback_executor(
    executor: Callable[[Any], dict[str, Any]],
    request: Any,
    *,
    subject: str = "",
) -> ConformanceReport:
    """Verify a writeback executor against the properties provenance depends on.

    `request` must be an `ExecutionRequest` the executor can actually perform -- this
    check *executes* it, because an executor that looks right and writes nothing is the
    failure worth catching.
    """
    report = ConformanceReport(suite="writeback_executor", subject=subject or getattr(executor, "__name__", "executor"))

    outcome: dict[str, Any] = {}

    def returns_mapping() -> Optional[str]:
        nonlocal outcome
        result = executor(request)
        if not isinstance(result, dict):
            return f"返回了 {type(result).__name__}，应为 dict"
        outcome = result
        return None if result else "返回了空 dict"

    _guard(
        report,
        "返回可留痕的结果字典",
        "返回值会原样写入判定记录的 execution.remote。空结果意味着事后无法证明那次写回做了什么。",
        returns_mapping,
    )

    def reports_effect() -> Optional[str]:
        # Either a row count or an explicit remote status; something must indicate what
        # happened, or "succeeded" is an unfalsifiable claim.
        keys = {str(key).lower() for key in outcome}
        if any("affected" in key or "row" in key or "status" in key or "code" in key for key in keys):
            return None
        return f"结果中没有任何表明写回效果的字段: {sorted(outcome)[:5]}"

    _guard(
        report,
        "结果表明写回效果",
        "「返回正常、什么也没改」是运维最难察觉的失败。结果里必须能看出影响了什么。",
        reports_effect,
    )

    def survives_a_json_round_trip() -> Optional[str]:
        """Provenance is stored as JSON with `default=str`, so nothing *fails* to serialise.

        That is the trap: a value that only `str()` could encode is written to the decision
        record as `"<object at 0x...>"`. The write succeeds, the verdict looks fine, and the
        audit trail contains a memory address instead of what happened. So the check is
        round-trip fidelity, not serialisability.
        """
        import json

        encoded = json.dumps(outcome, ensure_ascii=False, default=str)
        restored = json.loads(encoded)
        lossy = sorted(
            key
            for key, value in outcome.items()
            if not isinstance(value, (str, int, float, bool, type(None), list, dict)) and restored.get(key) != value
        )
        return f"以下字段只能经 str() 编码，留痕中会变成无意义的文本: {lossy}" if lossy else None

    _guard(
        report,
        "结果能如实往返 JSON",
        "判定记录以 JSON 存储且带 default=str，因此写入不会失败——"
        "而是把无法编码的值静默写成 <object at 0x...>。审计留下的是内存地址，不是发生了什么。",
        survives_a_json_round_trip,
    )
    return report


# -- Suite registry ---------------------------------------------------------

SUITES = {
    "instance_resolver": check_instance_resolver,
    "data_source_adapter": check_data_source_adapter,
    "retrieval_backend": check_retrieval_backend,
    "embedding_model": check_embedding_model,
    "writeback_executor": check_writeback_executor,
}


def available_suites() -> tuple[str, ...]:
    return tuple(sorted(SUITES))


def describe_suites() -> list[dict[str, Any]]:
    """What each suite verifies, for `aletheia verify --list` and the docs."""
    return [
        {
            "suite": name,
            "subject": _SUITE_SUBJECTS[name],
            "extensionPoint": _SUITE_ENTRY_POINTS[name],
            "docstring": (SUITES[name].__doc__ or "").strip().split("\n")[0],
        }
        for name in available_suites()
    ]


_SUITE_SUBJECTS = {
    "instance_resolver": "实例解析器（哪些行是这个对象的实例）",
    "data_source_adapter": "数据源适配器（接入、扫描、运行时读取）",
    "retrieval_backend": "检索后端（候选条目排序）",
    "embedding_model": "嵌入模型（相似度打分）",
    "writeback_executor": "写回执行器（对遗留系统执行操作）",
}

_SUITE_ENTRY_POINTS = {
    "instance_resolver": "aletheia.resolvers",
    "data_source_adapter": "aletheia.adapters",
    "retrieval_backend": "aletheia.retrieval_backends",
    "embedding_model": "aletheia.embedding_models",
    "writeback_executor": "aletheia.executors",
}
