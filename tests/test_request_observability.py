"""Request identity and the access log: the id, where it travels, and what is recorded.

These drive the real middleware through HTTP rather than calling it directly, because the
properties that matter are end-to-end: an id that reaches the response but not the log
lines is not correlation, and one that reaches the endpoint but is not on the response
cannot be quoted in a bug report.

What is deliberately not asserted: timing values. A duration is asserted to be present
and numeric, never compared against a threshold -- a latency assertion on a loaded CI
machine fails for reasons unrelated to the code, gets relaxed, and then asserts nothing.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from ontology_platform.logging_config import (
    JSONFormatter,
    RequestIdFilter,
    TextFormatter,
    setup_logging,
)
from ontology_platform.request_logger import (
    request_logging_middleware,
    unhandled_exception_response,
)
from ontology_platform.tracing import (
    MAX_REQUEST_ID_LENGTH,
    current_request_id,
    request_id_context,
    sanitize_request_id,
)


def _remove_managed_handlers(root: logging.Logger) -> None:
    """Drop the handlers `setup_logging` installed, leaving anything else alone."""
    for handler in root.handlers[:]:
        if getattr(handler, "_aletheia_managed", False):
            root.removeHandler(handler)
            handler.close()


@pytest.fixture
def app() -> FastAPI:
    """The middleware under test over a minimal app, in the production nesting order."""
    application = FastAPI()

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        return await request_logging_middleware(request, call_next)

    @application.get("/probe")
    def probe() -> dict[str, str]:
        return {"observed": current_request_id()}

    @application.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    # Registered as `api.py` registers it, so the 500 path under test is the shipped one.
    application.add_exception_handler(Exception, unhandled_exception_response)

    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: a 500 is one of the cases under test, and the default
    # re-raises it in the test process instead of exercising the handler.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


class TestRequestIdOnTheWire:
    def test_a_generated_id_is_returned_to_the_caller(self, client: TestClient) -> None:
        """The id has to come back, or there is nothing for a user to quote."""
        response = client.get("/probe")
        assert response.status_code == 200
        returned = response.headers["X-Request-Id"]
        assert returned
        assert len(returned) == 32  # full uuid4 hex

    def test_ids_differ_between_requests(self, client: TestClient) -> None:
        first = client.get("/probe").headers["X-Request-Id"]
        second = client.get("/probe").headers["X-Request-Id"]
        assert first != second

    def test_a_caller_supplied_id_is_honoured(self, client: TestClient) -> None:
        """A gateway correlating its own id with this service's has to be able to."""
        response = client.get("/probe", headers={"X-Request-Id": "gateway-7f3a"})
        assert response.headers["X-Request-Id"] == "gateway-7f3a"

    def test_the_id_reaches_the_endpoint_not_only_the_response(self, client: TestClient) -> None:
        """Correlation requires the endpoint's own log lines to carry it.

        Without this the id on the response is decoration: it names a request whose detail
        lines still cannot be told apart from any other request's.
        """
        response = client.get("/probe", headers={"X-Request-Id": "endpoint-42"})
        assert response.json()["observed"] == "endpoint-42"

    @pytest.mark.parametrize(
        "forged",
        [
            "with space",
            "with\nnewline",
            "ansi\x1b[31m",
            "semi;colon",
            'quote"',
            "x" * (MAX_REQUEST_ID_LENGTH + 1),
        ],
    )
    def test_an_unloggable_id_is_replaced_not_trusted(self, client: TestClient, forged: str) -> None:
        """A caller-supplied id ends up in log lines, so it is a log-injection vector.

        A forged entry is worse than a missing one: it is indistinguishable from a real
        line. The value is replaced rather than stripped, so the caller sees a mismatch
        instead of silently correlating against a rewritten id.
        """
        response = client.get("/probe", headers={"X-Request-Id": forged})
        returned = response.headers["X-Request-Id"]
        assert returned != forged
        assert sanitize_request_id(returned) == returned

    def test_the_id_is_present_even_when_the_session_is_refused(self, client: TestClient) -> None:
        """The responses most likely to be reported are the failures."""
        response = client.get("/boom", headers={"X-Request-Id": "failed-req"})
        assert response.status_code == 500
        assert response.headers["X-Request-Id"] == "failed-req"
        assert response.json()["requestId"] == "failed-req"

    def test_a_500_does_not_disclose_the_exception(self, client: TestClient) -> None:
        """The traceback goes to the log, not to whoever can reach the endpoint.

        Exception text carries paths, SQL and occasionally row values, so echoing it turns
        an error report into a disclosure.
        """
        response = client.get("/boom")
        assert "kaboom" not in response.text
        assert "RuntimeError" not in response.text
        assert "Traceback" not in response.text


class TestSanitize:
    def test_acceptable_forms_pass_through(self) -> None:
        for value in ("abc", "A-1_b.2:c", "a" * MAX_REQUEST_ID_LENGTH, "traceparent-00-abc-def-01"):
            assert sanitize_request_id(value) == value

    @pytest.mark.parametrize("value", [None, "", "   ", "a b", "a\nb", "a\tb", "é"])
    def test_unacceptable_forms_become_empty(self, value: str | None) -> None:
        assert sanitize_request_id(value) == ""

    def test_length_is_capped(self) -> None:
        assert sanitize_request_id("a" * (MAX_REQUEST_ID_LENGTH + 1)) == ""


class TestContext:
    def test_ids_restore_after_a_nested_scope(self) -> None:
        """A nested scope must not blank the outer id.

        Clearing instead of restoring means every log line emitted after the inner scope
        loses its correlation, which shows up as a request whose later half is unlabelled.
        """
        with request_id_context("outer") as outer:
            assert outer == "outer"
            assert current_request_id() == "outer"
            with request_id_context("inner"):
                assert current_request_id() == "inner"
            assert current_request_id() == "outer"
        assert current_request_id() == ""

    def test_no_request_bound_reads_as_empty(self) -> None:
        assert current_request_id() == ""


class TestAccessLog:
    """One line per request, and what must not appear in it."""

    def test_one_line_per_request_with_the_essentials(self, client: TestClient, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="ontology_platform.request_logger"):
            client.get("/probe", headers={"X-Request-Id": "logged-req"})

        lines = [record for record in caplog.records if record.name.endswith("request_logger")]
        assert len(lines) == 1
        message = lines[0].getMessage()
        assert "/probe" in message
        assert "200" in message
        assert "logged-req" in message
        assert "ms" in message

    def test_the_query_string_is_not_logged(self, client: TestClient, caplog) -> None:
        """Query strings carry credentials, and access logs get shipped to aggregators.

        Scoped to this platform's own records. A foreign library logging the full URL is
        outside our control -- the HTTP client and uvicorn's own access log both do it --
        so asserting over the whole captured stream would test the client library, fail
        depending on which other tests raised the root log level first, and be deleted
        rather than fixed. What the platform must get right is its own line, and that
        uvicorn's duplicate is silenced, which the next test covers.
        """
        with caplog.at_level(logging.INFO, logger="ontology_platform.request_logger"):
            client.get("/probe?token=super-secret-value")

        ours = [record for record in caplog.records if record.name.endswith("request_logger")]
        assert ours, "访问日志未记录"
        assert all("super-secret-value" not in record.getMessage() for record in ours)

    def test_uvicorns_duplicate_access_log_is_silenced(self, monkeypatch) -> None:
        """Uvicorn's access line contains the full request line, query string included.

        It is also in a different shape and carries no request id, so leaving it on gives
        two access logs -- one of which leaks the parameters the other deliberately omits.
        """
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        uvicorn_access = logging.getLogger("uvicorn.access")
        previous = uvicorn_access.level
        try:
            uvicorn_access.setLevel(logging.INFO)
            setup_logging()
            assert uvicorn_access.level == logging.WARNING
        finally:
            uvicorn_access.setLevel(previous)
            _remove_managed_handlers(logging.getLogger())

    def test_a_server_error_is_logged_as_an_error(self, client: TestClient, caplog) -> None:
        """5xx and 4xx are separated so an alert can key on one without paging on both."""
        with caplog.at_level(logging.INFO, logger="ontology_platform.request_logger"):
            client.get("/boom")

        records = [record for record in caplog.records if record.name.endswith("request_logger")]
        assert records
        assert records[-1].levelno == logging.ERROR
        assert records[-1].exc_info is not None

    def test_an_unmatched_route_is_still_logged(self, client: TestClient, caplog) -> None:
        """A 404 is traffic, and traffic that arrives is what an access log records."""
        with caplog.at_level(logging.INFO, logger="ontology_platform.request_logger"):
            response = client.get("/definitely-not-a-route")

        assert response.status_code == 404
        assert any(record.name.endswith("request_logger") for record in caplog.records)


class TestStructuredLogging:
    def test_json_carries_the_fields_an_aggregator_searches_on(self) -> None:
        record = logging.LogRecord(
            name="ontology_platform.demo",
            level=logging.WARNING,
            pathname=__file__,
            lineno=7,
            msg="something %s",
            args=("happened",),
            exc_info=None,
        )
        record.request_id = "abc123"

        payload = json.loads(JSONFormatter().format(record))
        assert payload["level"] == "WARNING"
        assert payload["message"] == "something happened"
        assert payload["logger"] == "ontology_platform.demo"
        assert payload["requestId"] == "abc123"
        # ISO-8601 with an explicit zone: two services in different zones must interleave
        # into one correct stream, and the zone has to be recorded for that to be possible.
        assert payload["timestamp"].endswith("+00:00")

    def test_an_exception_is_serialised_rather_than_lost(self) -> None:
        try:
            raise ValueError("inner failure")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="ontology_platform.demo",
                level=logging.ERROR,
                pathname=__file__,
                lineno=9,
                msg="outer",
                args=(),
                exc_info=sys.exc_info(),
            )
        record.request_id = "-"

        payload = json.loads(JSONFormatter().format(record))
        assert payload["exception"]["type"] == "ValueError"
        assert "inner failure" in payload["exception"]["traceback"]

    def test_an_unserialisable_value_does_not_lose_the_line(self) -> None:
        """A formatter that raises loses the log line it was called for."""
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="%s",
            args=(object(),),
            exc_info=None,
        )
        record.request_id = "-"
        assert json.loads(JSONFormatter().format(record))["message"]


class TestRequestIdFilter:
    """The filter is what makes `request_id` present on records we did not plan for.

    Records are produced by logging through a real logger rather than by calling
    `logging.LogRecord(...)` and then the filter by hand: the point of the filter is where
    it sits in the pipeline, so a test that invokes it directly would pass even if it were
    attached to nothing.
    """

    @staticmethod
    def _capture(log_call, attach_filter: bool = True) -> logging.LogRecord:
        captured: list[logging.LogRecord] = []

        class Sink(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        logger = logging.getLogger("ontology_platform.filter_check")
        sink = Sink()
        if attach_filter:
            sink.addFilter(RequestIdFilter())
        logger.addHandler(sink)
        previous = logger.level
        logger.setLevel(logging.INFO)
        try:
            log_call(logger)
        finally:
            logger.removeHandler(sink)
            logger.setLevel(previous)
        assert captured, "没有捕获到日志记录"
        return captured[0]

    def test_the_ambient_id_is_attached(self) -> None:
        with request_id_context("filter-req"):
            record = self._capture(lambda log: log.info("hello"))
        assert record.request_id == "filter-req"

    def test_outside_a_request_it_reads_as_a_placeholder(self) -> None:
        """A visible placeholder, so a missing id reads as missing rather than as a bug."""
        record = self._capture(lambda log: log.info("hello"))
        assert record.request_id == "-"

    def test_an_explicitly_supplied_id_wins(self) -> None:
        """`extra={"request_id": ...}` must keep working.

        This is why the id is attached by a filter and not by a log-record factory: a
        factory stamps the attribute at creation, after which `Logger.makeRecord` raises
        `KeyError: Attempt to overwrite 'request_id'` for any call that passes one. The
        cost of that is invisible until a background job tries to label its own lines.
        """

        def emit(log: logging.Logger) -> None:
            log.info("hello", extra={"request_id": "explicit"})

        with request_id_context("ambient"):
            record = self._capture(emit)
        assert record.request_id == "explicit"

    def test_our_formatters_survive_a_record_the_filter_never_saw(self) -> None:
        """Our own formatters must not raise on an unstamped record.

        A formatter that raises loses the line it was called for, and the traceback points
        at the logging call rather than at the original problem.

        The record is built directly rather than logged. Going through the logging
        machinery makes this depend on whether some other handler already stamped the same
        record object -- which depends on which tests ran first, so the assertion would
        pass alone and fail in the suite.
        """
        record = logging.LogRecord(
            name="ontology_platform.unstamped",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="unstamped",
            args=(),
            exc_info=None,
        )
        assert not hasattr(record, "request_id")

        assert json.loads(JSONFormatter().format(record))["requestId"] == "-"
        assert "[-]" in TextFormatter().format(record)


class TestSetupLogging:
    """Configuration, including the parts that only bite on the second call."""

    @pytest.fixture
    def clean_root(self) -> Iterator[logging.Logger]:
        root = logging.getLogger()
        original = root.handlers[:]
        original_level = root.level
        try:
            yield root
        finally:
            _remove_managed_handlers(root)
            root.handlers[:] = original
            root.setLevel(original_level)

    def test_repeated_configuration_does_not_double_every_line(
        self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calling it twice is normal -- the CLI and the API's startup both do.

        A stacked handler does not break anything visibly: the stream is correct, just
        doubled, which reads like a request served twice.
        """
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        setup_logging()
        first = len(clean_root.handlers)
        setup_logging()
        assert len(clean_root.handlers) == first

    def test_json_is_opt_in_and_text_is_the_default(
        self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        monkeypatch.delenv("ONTOLOGY_LOG_FORMAT", raising=False)
        setup_logging()
        assert not isinstance(clean_root.handlers[-1].formatter, JSONFormatter)

        monkeypatch.setenv("ONTOLOGY_LOG_FORMAT", "json")
        setup_logging()
        assert isinstance(clean_root.handlers[-1].formatter, JSONFormatter)

    def test_enabling_a_log_file_creates_its_directory(
        self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The configuration this replaced would have failed on a missing directory.

        A logging change taking down the service it was meant to observe is the worst
        available failure mode for a logging change.
        """
        target = tmp_path / "nested" / "dir" / "platform.log"
        monkeypatch.setenv("ONTOLOGY_LOG_FILE", str(target))
        setup_logging()

        clean_root.info("into the file")
        for handler in clean_root.handlers:
            handler.flush()

        assert target.exists()
        assert "into the file" in target.read_text(encoding="utf-8")

    def test_no_log_file_is_created_unless_asked_for(
        self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A process that writes files nobody asked for fails on a read-only filesystem."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        setup_logging()
        assert not (tmp_path / "data" / "logs").exists()

    def test_the_configured_level_is_applied(self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        monkeypatch.setenv("ONTOLOGY_LOG_LEVEL", "warning")
        setup_logging()
        assert clean_root.level == logging.WARNING

    def test_an_unusable_level_falls_back_to_info(
        self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        monkeypatch.setenv("ONTOLOGY_LOG_LEVEL", "loud")
        setup_logging()
        assert clean_root.level == logging.INFO

    def test_a_json_line_is_one_line(self, clean_root: logging.Logger, monkeypatch: pytest.MonkeyPatch) -> None:
        """One object per line is what makes a JSON log greppable and line-delimited."""
        monkeypatch.setenv("ONTOLOGY_LOG_FORMAT", "json")
        monkeypatch.delenv("ONTOLOGY_LOG_FILE", raising=False)
        setup_logging()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger = logging.getLogger("ontology_platform.json_check")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("one line")
        finally:
            logger.removeHandler(handler)

        lines = stream.getvalue().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["message"] == "one line"
