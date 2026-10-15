"""Structured logging: one configuration, shared by `aletheia serve` and the API process.

Ship JSON when a log aggregator will parse it, plain text when a person is reading a
terminal. The choice is a deployment's, made once -- both formats carry the same fields,
including the request id, because the format that omits the id is the one you need it in.

Why the request id is attached by a filter rather than by each call site: the lines that
most need correlating are the ones nobody planned. A warning raised three frames deep in
an adapter does not know it is running inside a request, and asking every call site to pass
an id means the unplanned ones -- the interesting ones -- are exactly the ones without it.
`RequestIdFilter` is attached to every handler this module installs, so correlation is the
default rather than something to remember.

It is a filter and not a log-record factory, which was the first attempt. A factory that
stamps `request_id` onto every record makes `extra={"request_id": ...}` raise
`KeyError: Attempt to overwrite` -- `Logger.makeRecord` refuses to set an attribute the
record already has. That silently removes the ability to attach an id explicitly, which is
what a background job that knows its own identifier needs, and it fails at the call site
with a message that names the logging machinery rather than the problem.

A handler we did not install therefore stamps nothing. That is the deliberate half of the
trade: a deployment writing its own handler and its own `%(request_id)s` format string must
add `RequestIdFilter` to it, and the class is public for exactly that. Our own formatters
cannot raise either way -- `JSONFormatter` reads the attribute with a default, and
`TextFormatter` is built with that default too.

`data/logs/` is created on demand rather than assumed to exist. The configuration this
replaced named a rotating file handler for a directory nothing created, so the first
deployment to enable file logging would have failed at startup on a missing directory --
a logging change taking down the service it was meant to observe.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .tracing import current_request_id

# Marks handlers this module installed, so reconfiguring replaces them instead of stacking
# a second copy underneath. Stacked handlers are why "call setup twice" produces every
# line twice, which reads like a request being served twice.
_HANDLER_MARKER = "_aletheia_managed"

# Used when no request is in flight (startup, CLI, background work). A visible placeholder
# rather than an absent key, so a missing id reads as missing instead of as a formatter bug.
NO_REQUEST = "-"

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


class RequestIdFilter(logging.Filter):
    """Attach the current request id to a record.

    Public because a deployment that installs its own handler with a `%(request_id)s`
    format string has to attach it: filters are per-handler, and an ancestor logger's
    filter is never applied to a record that merely propagates through it.

    An id already on the record is left alone, so `extra={"request_id": ...}` wins over the
    ambient one. That is what lets a background job label its lines with its own job id
    while running inside a request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = current_request_id() or NO_REQUEST
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line, with a stable field set.

    The timestamp is ISO-8601 in UTC. The previous format used the locale-dependent
    `asctime` shape with no zone, so two services in different zones produced streams that
    interleaved incorrectly and nothing recorded which zone each line was in.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "requestId": getattr(record, "request_id", NO_REQUEST),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # `default=str` keeps an unserialisable value from raising inside the logging
        # machinery: a formatter that raises loses the log line it was called for, and the
        # traceback it prints points at the logging call rather than the original problem.
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable single line, carrying the same fields as the JSON form."""

    def __init__(self) -> None:
        # `defaults` rather than relying on the filter alone: a formatter that raises on a
        # missing field loses the log line it was called for, and the traceback it prints
        # points at the logging call rather than at the original problem.
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            defaults={"request_id": NO_REQUEST},
        )


def resolve_log_format() -> str:
    """`json` or `text`, from `ONTOLOGY_LOG_FORMAT`, defaulting to `text`.

    Text by default because the first person to run the platform is reading a terminal,
    and JSON is the deployment's decision rather than a surprise.
    """
    value = (os.environ.get("ONTOLOGY_LOG_FORMAT") or "text").strip().lower()
    return "json" if value in {"json", "structured"} else "text"


def resolve_log_level() -> str:
    """The configured level, normalised, defaulting to `INFO`."""
    value = (os.environ.get("ONTOLOGY_LOG_LEVEL") or "INFO").strip().upper()
    return value if isinstance(getattr(logging, value, None), int) else "INFO"


def resolve_log_file() -> Path | None:
    """The rotating log file, when `ONTOLOGY_LOG_FILE` names one.

    Unset by default: a process that writes a file nobody asked for fails on a read-only
    filesystem, and containers are expected to log to stdout and let the runtime collect.
    """
    value = (os.environ.get("ONTOLOGY_LOG_FILE") or "").strip()
    return Path(value).expanduser() if value else None


def _formatter() -> logging.Formatter:
    return JSONFormatter() if resolve_log_format() == "json" else TextFormatter()


def _managed_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in root.handlers if getattr(handler, _HANDLER_MARKER, False)]


def _install(root: logging.Logger, handler: logging.Handler) -> None:
    handler.setFormatter(_formatter())
    handler.addFilter(RequestIdFilter())
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)


def setup_logging(level: str | None = None) -> None:
    """Configure root logging. Safe to call more than once.

    Idempotent because it is called from more than one entry point -- the API's startup
    and the CLI -- and in a reload or test scenario both run in one process. Adding a
    handler per call is the bug this guards: the stream is still correct, just doubled.
    """
    root = logging.getLogger()

    for handler in _managed_handlers(root):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(getattr(logging, (level or resolve_log_level()), logging.INFO))

    # stderr, not stdout: the API's stdout is free for anything else a deployment pipes,
    # and a log line must not be mistaken for program output.
    _install(root, logging.StreamHandler(sys.stderr))

    log_file = resolve_log_file()
    if log_file is not None:
        # Created here, so enabling file logging cannot fail on a directory that does not
        # exist yet.
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _install(
            root,
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=DEFAULT_MAX_BYTES,
                backupCount=DEFAULT_BACKUP_COUNT,
                encoding="utf-8",
            ),
        )

    # Uvicorn's access log duplicates the access log this platform writes, in a different
    # shape and without the request id. Raising its level keeps one access log, ours.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
