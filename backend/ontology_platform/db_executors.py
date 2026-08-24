"""Writeback straight into a legacy database, and via stored procedures.

Generality item #13. HTTP was the only writeback channel, which quietly excludes the
systems this platform exists for: a large share of legacy business systems have no API at
all. Their integration surface is a table you insert into, or a stored procedure the
vendor tells you to call. Refusing those means the platform can *judge* an operation and
then not perform it -- the automation loop stops one step short.

## This is the most dangerous thing in the codebase, and it is built accordingly

A writeback executor runs after a verdict, with the platform's credentials, against a
production business system. Three constraints follow, and none of them is optional:

**Statements are declared, never composed from a request.** An executor that built SQL
from an operation's payload would be an injection surface reachable from an HTTP request
body. Instead a deployment registers a named `SqlWriteback` -- table, columns, or an
explicit statement -- and the request supplies only *values*, always as bound parameters.

**Every statement is single-shot and bounded.** No semicolons, no multi-statement bodies,
and an UPDATE or DELETE without a WHERE clause is refused. `update customers set status =
'x'` with a forgotten WHERE is one keystroke away from rewriting a whole table, and by the
time anyone notices, the verdict that authorised it looks perfectly reasonable.

**DDL and DELETE are refused by default.** Automation exists to advance business state,
not to change schemas or destroy rows. A deployment that genuinely needs deletion opts in
per-writeback, so the decision is recorded in the declaration rather than implied by a
URI.

## Transactions end with the operation

Each execution opens a connection, runs one statement, commits, and closes. No shared
connection and no ambient transaction: a writeback that participated in someone else's
transaction could be rolled back after the decision record already said it succeeded --
leaving provenance that contradicts the database.

## Rowcount is part of the outcome, not a detail

An UPDATE that matched zero rows is *not* a success: the instance it targeted was not
there, or the WHERE clause was wrong. Reported as `affectedRows` and treated as a failure
when nothing matched, because "the call returned 200 and changed nothing" is the failure
mode operators find hardest to notice.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .automation import ExecutionRequest, register_executor
from .instance_resolver import ResolverError, validate_identifier
from .sql_dialects import SqlDialect, resolve_dialect

logger = logging.getLogger(__name__)

# Statement kinds a writeback may perform. `delete` is absent from the defaults on
# purpose; see the module docstring.
INSERT = "insert"
UPDATE = "update"
DELETE = "delete"
CALL = "call"
WRITEBACK_KINDS = (INSERT, UPDATE, DELETE, CALL)

# Anything that changes structure or bypasses the declared statement. Matched as whole
# words so a column named `granted` or a value containing "create" is unaffected.
FORBIDDEN_KEYWORDS = (
    "drop",
    "truncate",
    "alter",
    "create",
    "grant",
    "revoke",
    "attach",
    "vacuum",
    "pragma",
)


class WritebackError(ValueError):
    """Raised when a writeback declaration or invocation is unsafe or invalid."""


def _reject_forbidden(statement: str, *, what: str) -> None:
    """Refuse structural or privilege statements.

    Checked on the *declared* statement rather than on runtime input, because runtime
    input never reaches SQL text -- it is always bound. This guards against a declaration
    that would let automation change a schema.
    """
    lowered = statement.lower()
    if ";" in statement.strip().rstrip(";"):
        raise WritebackError(f"{what}不允许包含分号（多语句会绕过单语句审计）")
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise WritebackError(f"{what}不允许使用 {keyword.upper()}：自动化用于推进业务状态，不用于变更结构或权限")


@dataclass(frozen=True)
class SqlWriteback:
    """One declared write against a legacy database.

    Either a structured form (`kind` + `table` + `columns`) or an explicit `statement`.
    Both are declared configuration; neither is built from a request. The request supplies
    values, which are always bound.
    """

    name: str
    kind: str
    # Structured form.
    table: str = ""
    columns: Sequence[str] = ()
    # Columns forming the WHERE clause for an update or delete. Required for those:
    # a missing WHERE would rewrite the table.
    key_columns: Sequence[str] = ()
    # Explicit form. Placeholders are `:name`, substituted with bound parameters.
    statement: str = ""
    # Stored procedure name for `call`.
    procedure: str = ""
    parameters: Sequence[str] = ()
    # Opt-in, because deletion is not what automation is for.
    allow_delete: bool = False
    # Refuse the write when it matched no rows. Default on: an update that changed
    # nothing is the failure operators find hardest to notice.
    require_affected_rows: bool = True
    description: str = ""
    dialect_name: str = "postgresql"

    def validate(self) -> "SqlWriteback":
        if not self.name or not self.name.replace("_", "").replace("-", "").isalnum():
            raise WritebackError(f"写回名称必须是字母数字、下划线或连字符: {self.name!r}")
        kind = (self.kind or "").strip().lower()
        if kind not in WRITEBACK_KINDS:
            raise WritebackError(f"不支持的写回类型: {self.kind!r}。可选: {'、'.join(WRITEBACK_KINDS)}")
        object.__setattr__(self, "kind", kind)
        if kind == DELETE and not self.allow_delete:
            raise WritebackError(
                f"{self.name}: 删除类写回必须显式设置 allowDelete=True。"
                "自动化用于推进业务状态，销毁数据需要单独的授权决定。"
            )
        resolve_dialect(self.dialect_name)

        if self.statement:
            _reject_forbidden(self.statement, what="写回语句")
            self._require_where_when_needed(self.statement)
            return self
        if kind == CALL:
            if not self.procedure:
                raise WritebackError(f"{self.name}: call 类写回必须指定 procedure")
            _identifier(self.procedure, what="存储过程名")
            for parameter in self.parameters:
                if not str(parameter).isidentifier():
                    raise WritebackError(f"{self.name}: 参数名必须是合法标识符: {parameter!r}")
            return self

        if not self.table:
            raise WritebackError(f"{self.name}: 结构化写回必须指定 table")
        _identifier(self.table, what="写回目标表名")
        if not self.columns and kind != DELETE:
            raise WritebackError(f"{self.name}: {kind} 写回必须指定 columns")
        for column in (*self.columns, *self.key_columns):
            _identifier(column, what="写回列名")
        if kind in (UPDATE, DELETE) and not self.key_columns:
            raise WritebackError(
                f"{self.name}: {kind} 写回必须指定 keyColumns。"
                "缺少 WHERE 条件的更新会改写整张表，且事后无法从判定记录看出这一点。"
            )
        return self

    def _require_where_when_needed(self, statement: str) -> None:
        lowered = statement.lower()
        if lowered.lstrip().startswith(("update", "delete")) and " where " not in lowered:
            raise WritebackError(f"{self.name}: UPDATE／DELETE 语句必须包含 WHERE 条件，否则会作用于整张表。")
        if lowered.lstrip().startswith("delete") and not self.allow_delete:
            raise WritebackError(f"{self.name}: 删除类写回必须显式设置 allowDelete=True。")

    @property
    def dialect(self) -> SqlDialect:
        return resolve_dialect(self.dialect_name)

    def render(self, values: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        """Build the statement text and its bound parameters.

        Identifiers come from the declaration and are validated; values come from the
        request and are *only ever bound*. That separation is the whole safety argument:
        no request content reaches SQL text.
        """
        profile = self.dialect
        if self.statement:
            return _bind_named(self.statement, values, profile)
        if self.kind == CALL:
            markers = ", ".join(profile.placeholders(len(self.parameters)))
            parameters = tuple(_require(values, name, self.name) for name in self.parameters)
            return f"call {profile.quote(self.procedure)}({markers})", parameters

        table = profile.quote(self.table)
        if self.kind == INSERT:
            columns = ", ".join(profile.quote(column) for column in self.columns)
            markers = ", ".join(profile.placeholders(len(self.columns)))
            parameters = tuple(_require(values, column, self.name) for column in self.columns)
            return f"insert into {table} ({columns}) values ({markers})", parameters

        conditions, key_values = self._where(profile, values, offset=len(self.columns))
        if self.kind == DELETE:
            return f"delete from {table} where {conditions}", key_values

        assignments = ", ".join(
            f"{profile.quote(column)} = {profile.placeholder(index + 1)}" for index, column in enumerate(self.columns)
        )
        set_values = tuple(_require(values, column, self.name) for column in self.columns)
        return f"update {table} set {assignments} where {conditions}", set_values + key_values

    def _where(self, profile: SqlDialect, values: dict[str, Any], *, offset: int) -> tuple[str, tuple[Any, ...]]:
        clauses = []
        parameters = []
        for index, column in enumerate(self.key_columns):
            clauses.append(f"{profile.quote(column)} = {profile.placeholder(offset + index + 1)}")
            parameters.append(_require(values, column, self.name))
        return " and ".join(clauses), tuple(parameters)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "table": self.table,
            "columns": list(self.columns),
            "keyColumns": list(self.key_columns),
            "procedure": self.procedure,
            "parameters": list(self.parameters),
            "statement": self.statement,
            "allowDelete": self.allow_delete,
            "requireAffectedRows": self.require_affected_rows,
            "dialect": self.dialect_name,
            "description": self.description,
        }


def _identifier(name: str, *, what: str) -> str:
    """Validate an identifier destined for SQL text.

    Shared with the resolver module so there is one place to audit for identifier safety;
    the error is re-raised as a writeback error so callers handle one exception type.
    """
    try:
        return validate_identifier(name, what=what)
    except ResolverError as error:
        raise WritebackError(str(error)) from error


def _require(values: dict[str, Any], name: str, writeback: str) -> Any:
    """Fetch a required value, refusing rather than substituting None.

    A missing value silently becoming NULL is how an update wipes a column it was meant to
    leave alone.
    """
    if name not in values:
        raise WritebackError(f"{writeback}: 缺少参数 {name!r}。写回不会用 NULL 代替缺失值。")
    return values[name]


_NAMED_PARAMETER = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def _bind_named(statement: str, values: dict[str, Any], profile: SqlDialect) -> tuple[str, tuple[Any, ...]]:
    """Replace `:name` placeholders with the dialect's markers, in order.

    Named placeholders are used in declarations because a positional declaration silently
    breaks when someone reorders the columns; the conversion to positional markers happens
    here, once.
    """
    parameters: list[Any] = []

    def substitute(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in values:
            raise WritebackError(f"缺少参数 {name!r}。写回不会用 NULL 代替缺失值。")
        parameters.append(values[name])
        return profile.placeholder(len(parameters))

    rendered = _NAMED_PARAMETER.sub(substitute, statement)
    return rendered, tuple(parameters)


@dataclass(frozen=True)
class DatabaseTarget:
    """How to reach the legacy database, and which writes are allowed against it.

    Registered per scheme, so `dbwrite://orders` names a target a deployment declared
    rather than a connection string a request supplied. A request that could name its own
    connection string would let a caller point automation at any reachable database.
    """

    scheme: str
    connection_uri: str
    dialect_name: str = "postgresql"
    # Driver module providing PEP 249 `connect`.
    driver_module: str = ""
    writebacks: dict[str, SqlWriteback] = field(default_factory=dict)
    passes_uri_positionally: bool = True

    def validate(self) -> "DatabaseTarget":
        if not self.scheme or not self.scheme.replace("_", "").isalnum():
            raise WritebackError(f"写回 scheme 必须是字母数字或下划线: {self.scheme!r}")
        if not self.connection_uri:
            raise WritebackError(f"{self.scheme}: 必须提供连接串")
        if not self.driver_module:
            raise WritebackError(f"{self.scheme}: 必须指定驱动模块")
        resolve_dialect(self.dialect_name)
        for writeback in self.writebacks.values():
            writeback.validate()
        return self

    def writeback(self, name: str) -> SqlWriteback:
        found = self.writebacks.get(name)
        if found is None:
            raise WritebackError(
                f"{self.scheme}: 未声明的写回 {name!r}。已声明: {'、'.join(sorted(self.writebacks)) or '(无)'}。"
                "写回语句必须预先声明，不能由请求构造。"
            )
        return found


def _connect(target: DatabaseTarget) -> Any:
    import importlib

    try:
        driver = importlib.import_module(target.driver_module)
    except ImportError as error:
        raise WritebackError(f"{target.scheme}: 写回需要安装驱动 {target.driver_module}") from error
    if target.passes_uri_positionally:
        return driver.connect(target.connection_uri)
    return driver.connect(dsn=target.connection_uri)


def execute_sql_writeback(target: DatabaseTarget, request: ExecutionRequest) -> dict[str, Any]:
    """Perform one declared write and report the outcome.

    The operation's `path` selects which declared writeback to run -- so the platform's
    existing operation registry keeps naming what happens, and the *only* thing the
    request contributes is values.
    """
    plan = request.plan or {}
    name = str(plan.get("path") or "").strip("/").split("/")[-1]
    if not name:
        raise WritebackError(f"{target.scheme}: 无法从操作路径识别写回名称: {plan.get('path')!r}")
    writeback = target.writeback(name).validate()
    values = dict(plan.get("payload") or {})
    statement, parameters = writeback.render(values)

    conn = _connect(target)
    try:
        cursor = conn.cursor()
        cursor.execute(statement, parameters)
        affected = getattr(cursor, "rowcount", -1)
        # Commit before reporting success: a decision record that says "written" while the
        # transaction is still open would be provenance contradicting the database.
        conn.commit()
    except Exception as error:
        try:
            conn.rollback()
        except Exception:  # pragma: no cover - driver dependent
            logger.debug("回滚失败", exc_info=True)
        raise WritebackError(f"{target.scheme}/{name}: 写回失败: {error}") from error
    finally:
        conn.close()

    if writeback.require_affected_rows and affected == 0:
        # Not a success. The targeted instance was not there, or the WHERE clause was
        # wrong -- and "returned fine, changed nothing" is the hardest failure to notice.
        raise WritebackError(f"{target.scheme}/{name}: 语句执行成功但影响 0 行，目标实例可能不存在或条件不匹配。")
    return {
        "channel": target.scheme,
        "writeback": name,
        "kind": writeback.kind,
        "affectedRows": affected,
        # The statement text, not the values: an auditor needs to know what ran, and the
        # values are already in the decision record's input reference.
        "statement": statement,
        "dialect": writeback.dialect_name,
    }


_TARGETS: dict[str, DatabaseTarget] = {}


def register_database_target(target: DatabaseTarget, *, replace: bool = False) -> DatabaseTarget:
    """Register a database writeback channel under its own scheme.

    Registering the target *and* its allowed writebacks together is deliberate: a channel
    with no declared writebacks can perform nothing, so a misconfiguration fails closed
    rather than exposing an open SQL endpoint.
    """
    target.validate()
    if target.scheme in _TARGETS and not replace:
        raise WritebackError(f"写回通道已存在: {target.scheme}。要覆盖请显式传 replace=True。")
    _TARGETS[target.scheme] = target

    scheme = target.scheme

    def executor(request: ExecutionRequest) -> dict[str, Any]:
        # Looked up at call time rather than captured, so re-registering a target with
        # `replace=True` takes effect instead of leaving the old connection in a closure.
        return execute_sql_writeback(_TARGETS[scheme], request)

    register_executor(scheme, executor, replace=True)
    return target


def registered_database_targets() -> dict[str, dict[str, Any]]:
    """The declared channels and their writebacks, for review and for `doctor`."""
    return {
        scheme: {
            "dialect": target.dialect_name,
            "driverModule": target.driver_module,
            "writebacks": {name: item.to_json() for name, item in target.writebacks.items()},
        }
        for scheme, target in _TARGETS.items()
    }


def get_database_target(scheme: str) -> Optional[DatabaseTarget]:
    return _TARGETS.get(scheme)
