"""What a user reads when something fails.

The platform's prose is written for a reader; this file exists because its runtime messages
were not. Each case below is a message that reached a user as the text of a Python, sqlite,
urllib or JSON exception — verified by an audit and, for three of them, reproduced live
through the HTTP API.

What is asserted is the property, not the wording: **the driver's or interpreter's own text
is not what the user is shown, and what they are shown names the thing they can change.**
Pinning exact sentences here would make every future wording improvement a test edit, which
is how message tests get deleted.
"""

from __future__ import annotations

import errno
import json
import socket
import sqlite3
from urllib.error import HTTPError, URLError

import pytest
from ontology_platform.errors import describe_data_source_failure, describe_model_failure
from ontology_platform.rule_sandbox import _describe_evaluation_failure, evaluate_rule_expression

# Text that must never be the whole of what a user reads, with the exception that produced it.
DRIVER_TEXT = [
    pytest.param(sqlite3.OperationalError("unable to open database file"), "unable to open", id="sqlite-open"),
    pytest.param(sqlite3.DatabaseError("file is not a database"), "file is not a database", id="sqlite-format"),
    pytest.param(sqlite3.OperationalError("no such table: contract"), "no such table", id="sqlite-table"),
    pytest.param(
        sqlite3.OperationalError('password authentication failed for user "svc"'),
        "password authentication failed",
        id="auth",
    ),
    pytest.param(
        URLError(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")),
        "Connection refused",
        id="refused",
    ),
    pytest.param(URLError(socket.gaierror(-2, "Name or service not known")), "Name or service", id="dns"),
    pytest.param(HTTPError("u", 404, "Not Found", None, None), "Not Found", id="http"),
    pytest.param(json.JSONDecodeError("Expecting value", "", 0), "Expecting value", id="json"),
    pytest.param(PermissionError(errno.EACCES, "Permission denied"), "Permission denied", id="permission"),
]


class TestDataSourceFailures:
    @pytest.mark.parametrize("error, raw", DRIVER_TEXT)
    def test_the_drivers_own_text_is_not_what_the_user_is_told(self, error: Exception, raw: str) -> None:
        message = describe_data_source_failure(error)
        assert message != str(error)
        if raw not in message:
            assert raw not in message
        assert any("一" <= ch <= "鿿" for ch in message), message

    def test_the_classification_distinguishes_what_needs_different_fixes(self) -> None:
        """A missing file, a refused connection and a rejected password are three different
        mornings for whoever has to fix them, and they arrive as the same exception type."""
        missing = describe_data_source_failure(sqlite3.OperationalError("unable to open database file"))
        refused = describe_data_source_failure(URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused")))
        denied = describe_data_source_failure(sqlite3.OperationalError("password authentication failed"))

        assert len({missing, refused, denied}) == 3

    def test_a_sqlite_error_keeps_the_identifier_the_user_mistyped(self) -> None:
        """The table name is the one detail worth keeping: they typed it."""
        message = describe_data_source_failure(sqlite3.OperationalError("no such table: contract"))
        assert "contract" in message

    def test_an_unclassifiable_error_names_its_type_rather_than_inventing_a_cause(self) -> None:
        message = describe_data_source_failure(ValueError("something odd"))
        assert "ValueError" in message
        assert "something odd" in message


class TestModelFailures:
    def test_an_http_failure_names_the_status_and_the_setting(self) -> None:
        message = describe_model_failure(HTTPError("u", 401, "Unauthorized", None, None))
        assert "401" in message
        assert "鉴权" in message

    def test_a_non_json_response_is_described_as_such(self) -> None:
        """The common cause is a base URL pointing at a web page rather than the endpoint."""
        message = describe_model_failure(json.JSONDecodeError("Expecting value", "", 0))
        assert "JSON" in message
        assert "Expecting value" not in message

    def test_a_transport_failure_is_not_reported_as_an_endpoint_misconfiguration(self) -> None:
        message = describe_model_failure(URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused")))
        assert "无法连接" in message


class TestRuleEvaluationFailures:
    """The message a modeller reads inside a verdict.

    Reached from `ruleResults[].evaluationError` and `.explanation`, and — per §13 of the
    extension guide — a rule referencing an absent association is an expected outcome, not
    an edge case, so this text is routine rather than rare.
    """

    def test_a_name_that_is_not_available_names_itself_and_the_usual_cause(self) -> None:
        message = _describe_evaluation_failure(NameError("name 'signed_date' is not defined"))
        assert "signed_date" in message
        assert "蓝图" in message

    def test_a_type_clash_translates_the_two_types(self) -> None:
        message = _describe_evaluation_failure(TypeError("'>' not supported between instances of 'str' and 'int'"))
        assert "文本" in message and "整数" in message
        assert "not supported between" not in message

    def test_the_explanation_follows_the_types_rather_than_the_branch(self) -> None:
        """A comparison against an absent value and one against text are fixed differently.

        Asserting the wrong cause is worse than asserting none: the reader acts on it.
        """
        text_clash = _describe_evaluation_failure(TypeError("'>' not supported between instances of 'str' and 'int'"))
        null_clash = _describe_evaluation_failure(TypeError("unsupported operand type(s) for +: 'NoneType' and 'int'"))
        assert text_clash != null_clash
        assert "空值" in null_clash and "为空值" in null_clash

    def test_a_conversion_failure_quotes_the_value_that_could_not_be_converted(self) -> None:
        message = _describe_evaluation_failure(ValueError("could not convert string to float: 'abc'"))
        assert "abc" in message
        assert "float" not in message

    def test_an_unexpected_failure_withholds_the_detail_and_says_where_it_is(self) -> None:
        """Otherwise every verdict that rule appears in carries the internals."""
        message = _describe_evaluation_failure(AttributeError("'NoneType' object has no attribute 'x'"))
        assert "NoneType" not in message
        assert "日志" in message

    def test_the_sandbox_still_fails_closed_whatever_the_message(self) -> None:
        """The behaviour this file is about must not drift while the wording improves."""
        passed, error = evaluate_rule_expression("status > 0", {"status": "effective"})
        assert passed is False
        assert error and "类型" in error

        passed, error = evaluate_rule_expression("amount + 1", {"amount": None})
        assert passed is False
        assert error and "空值" in error

        passed, error = evaluate_rule_expression("nope > 1", {})
        assert passed is False
        assert error and "nope" in error
