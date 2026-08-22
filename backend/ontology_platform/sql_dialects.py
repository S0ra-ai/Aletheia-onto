"""SQL dialect profiles: what differs between databases, stated as data.

Generality item #12. The metadata scanner already worked against
`information_schema`, which every SQL database of consequence implements -- so most of
a new database's support is already written. What blocked reuse was that the five
places where dialects differ were written as `if dialect == "postgresql" else ...`.
A binary branch cannot express a third database, so adding Oracle, SQL Server, 达梦 or
人大金仓 meant editing the scanner. That is a fork, which is exactly what the extension
registry exists to avoid (ADR-0007).

The differences turn out to be few and mechanical:

| Difference | Why it differs |
|---|---|
| current schema expression | `current_schema()` vs `database()` vs `sys_context(...)` |
| identifier quoting | backtick vs double quote |
| parameter placeholder | `%s` vs `?` vs `:1` |
| row-limit syntax | `limit n` vs `fetch first n rows only` vs `top n` |
| foreign-key catalog shape | `constraint_column_usage` vs `referenced_table_name` |
| catalog identifier case | Oracle upper-cases unquoted names |

Six knobs, declared per database. Nothing here executes SQL: a profile is a value
object, so a third party can add one without the platform having a driver for it, and
the profile can be unit-tested without a server.

## Why not SQLAlchemy

It would solve this and more. Rejected because the kernel is deliberately
dependency-free (see `pyproject.toml`): a semantic layer that a customer must install
an ORM to embed is harder to place inside an existing application, and the reason to
read metadata is not to become a data-access layer. We use ~200 lines of catalog
queries; SQLAlchemy is a different order of commitment.

A deployment that *wants* SQLAlchemy can register an adapter that uses it -- that is
what the adapter registry is for.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

from dataclasses import dataclass

# How a dialect spells "the schema this connection is looking at". Used in every
# catalog query, because scanning must not leak into another tenant's schema
# (ADR-0006) or into the system catalogs.
SCHEMA_CURRENT = "current_schema()"
SCHEMA_DATABASE = "database()"


@dataclass(frozen=True)
class SqlDialect:
    """Everything the scanner and runtime need to know about one SQL database.

    Frozen and free of behaviour on purpose: a profile is reviewable data, and a
    third-party dialect can be declared, exported and diffed. A profile that could run
    SQL would be a plugin, and plugins are the adapter's job, not the dialect's.
    """

    name: str
    # Expression yielding the active schema, e.g. `current_schema()`.
    current_schema_expression: str = SCHEMA_CURRENT
    # Quote character pair for identifiers. Doubling the closing char escapes it, which
    # is standard SQL and true for every dialect here.
    quote_open: str = '"'
    quote_close: str = '"'
    # DB-API parameter style: "format" (%s), "qmark" (?), or "numeric" (:1).
    paramstyle: str = "format"
    # Whether the catalog stores unquoted identifiers upper-cased (Oracle, 达梦).
    # Getting this wrong makes every table appear to have no columns, because the
    # catalog lookup silently matches nothing.
    catalog_uppercases_identifiers: bool = False
    # Foreign keys: standard uses constraint_column_usage; MySQL puts the target
    # directly on key_column_usage.
    foreign_keys_via_referenced_columns: bool = False
    # Row limiting. `limit_offset` is the MySQL/PostgreSQL form; `fetch_first` is
    # SQL:2008, which Oracle 12c+, SQL Server 2012+ and 达梦 all accept.
    row_limit_style: str = "limit_offset"
    # Some drivers cannot bind a parameter in a LIMIT clause, so the value is
    # interpolated. Safe only because it is always an int the platform produced.
    inline_row_limit: bool = False

    def quote(self, identifier: str) -> str:
        """Quote an identifier, escaping the closing character by doubling it."""
        return f"{self.quote_open}{identifier.replace(self.quote_close, self.quote_close * 2)}{self.quote_close}"

    def placeholder(self, position: int = 1) -> str:
        """A parameter marker. `position` is 1-based, used only by numeric styles."""
        if self.paramstyle == "qmark":
            return "?"
        if self.paramstyle == "numeric":
            return f":{position}"
        return "%s"

    def placeholders(self, count: int) -> list[str]:
        return [self.placeholder(index + 1) for index in range(count)]

    def catalog_name(self, identifier: str) -> str:
        """An identifier as the catalog stores it.

        Oracle and 达梦 fold unquoted names to upper case, so a lookup for `contracts`
        finds nothing while `CONTRACTS` succeeds. The failure is silent -- the table
        appears to have no columns -- which is why this is a declared property rather
        than something each query remembers.
        """
        return identifier.upper() if self.catalog_uppercases_identifiers else identifier

    def limit_clause(self, limit: int, offset: int = 0) -> str:
        """A row-limiting clause for a query that already has an ORDER BY where needed.

        Returns SQL text with the numbers inlined rather than parameterised: several
        drivers refuse a bound parameter in a limit position, and the values are always
        integers the platform itself produced, never caller input.
        """
        limit = max(0, int(limit))
        offset = max(0, int(offset))
        if self.row_limit_style == "fetch_first":
            clause = f"offset {offset} rows " if offset else ""
            return f"{clause}fetch first {limit} rows only"
        if offset:
            return f"limit {limit} offset {offset}"
        return f"limit {limit}"


# -- Built-in profiles -------------------------------------------------------

POSTGRESQL = SqlDialect(name="postgresql")

MYSQL = SqlDialect(
    name="mysql",
    current_schema_expression=SCHEMA_DATABASE,
    quote_open="`",
    quote_close="`",
    foreign_keys_via_referenced_columns=True,
)

SQLITE = SqlDialect(name="sqlite", paramstyle="qmark")

# Oracle. `sys_context` is the portable way to get the current schema; `user` also
# works but differs under proxy authentication.
ORACLE = SqlDialect(
    name="oracle",
    current_schema_expression="sys_context('USERENV', 'CURRENT_SCHEMA')",
    paramstyle="numeric",
    catalog_uppercases_identifiers=True,
    row_limit_style="fetch_first",
    inline_row_limit=True,
)

SQLSERVER = SqlDialect(
    name="sqlserver",
    current_schema_expression="schema_name()",
    quote_open="[",
    quote_close="]",
    row_limit_style="fetch_first",
    inline_row_limit=True,
)

# 达梦 (DM8) is Oracle-compatible: same catalog case folding, same fetch-first syntax.
DAMENG = SqlDialect(
    name="dameng",
    current_schema_expression="sys_context('USERENV', 'CURRENT_SCHEMA')",
    paramstyle="qmark",
    catalog_uppercases_identifiers=True,
    row_limit_style="fetch_first",
    inline_row_limit=True,
)

# 人大金仓 (KingbaseES) is PostgreSQL-compatible, including `current_schema()`.
KINGBASE = SqlDialect(name="kingbase")

_DIALECTS: dict[str, SqlDialect] = {
    dialect.name: dialect for dialect in (POSTGRESQL, MYSQL, SQLITE, ORACLE, SQLSERVER, DAMENG, KINGBASE)
}

# Names the same database is known by. Kept separate from the profile table so an alias
# cannot silently shadow a real dialect with different behaviour.
_ALIASES = {
    "postgres": "postgresql",
    "pg": "postgresql",
    "mssql": "sqlserver",
    "dm": "dameng",
    "dm8": "dameng",
    "kingbasees": "kingbase",
}


class DialectError(ValueError):
    """Raised when a dialect is unknown or a profile is invalid."""


def register_dialect(dialect: SqlDialect, *, replace: bool = False) -> SqlDialect:
    """Add a dialect profile.

    Replacement is opt-in: silently redefining `mysql` would change how every existing
    MySQL source is scanned, with no record of it having happened.
    """
    if not dialect.name or not dialect.name.replace("_", "").isalnum():
        raise DialectError(f"方言名必须是字母数字或下划线: {dialect.name!r}")
    if dialect.paramstyle not in ("format", "qmark", "numeric"):
        raise DialectError(f"不支持的参数风格: {dialect.paramstyle!r}。可选: format、qmark、numeric")
    if dialect.row_limit_style not in ("limit_offset", "fetch_first"):
        raise DialectError(f"不支持的分页风格: {dialect.row_limit_style!r}。可选: limit_offset、fetch_first")
    if not dialect.quote_open or not dialect.quote_close:
        raise DialectError("标识符引号不能为空")
    if dialect.name in _DIALECTS and not replace:
        raise DialectError(f"方言已存在: {dialect.name}。要覆盖请显式传 replace=True。")
    _DIALECTS[dialect.name] = dialect
    return dialect


def get_dialect(name: str) -> SqlDialect:
    key = (name or "").strip().lower()
    key = _ALIASES.get(key, key)
    dialect = _DIALECTS.get(key)
    if dialect is None:
        raise DialectError(f"未知 SQL 方言: {name!r}。已登记: {'、'.join(sorted(_DIALECTS))}")
    return dialect


def known_dialects() -> tuple[str, ...]:
    return tuple(sorted(_DIALECTS))


def resolve_dialect(value: "str | SqlDialect") -> SqlDialect:
    """Accept either a profile or a name.

    The scanner used to take a dialect *string*; accepting both means the existing call
    sites keep working while new code passes a profile.
    """
    return value if isinstance(value, SqlDialect) else get_dialect(value)


# -- Catalog queries, built from a profile ----------------------------------
#
# One implementation for every dialect, because `information_schema` is standard. The
# profile supplies only the parts that genuinely differ.


def tables_query(dialect: SqlDialect) -> str:
    return f"""
        select table_name
        from information_schema.tables
        where table_schema = {dialect.current_schema_expression}
          and table_type = 'BASE TABLE'
        order by table_name
    """


def columns_query(dialect: SqlDialect) -> str:
    return f"""
        select column_name, data_type, is_nullable, ordinal_position
        from information_schema.columns
        where table_schema = {dialect.current_schema_expression}
          and table_name = {dialect.placeholder(1)}
        order by ordinal_position
    """


def primary_keys_query(dialect: SqlDialect) -> str:
    return f"""
        select kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
         and tc.table_name = kcu.table_name
        where tc.constraint_type = 'PRIMARY KEY'
          and tc.table_schema = {dialect.current_schema_expression}
          and tc.table_name = {dialect.placeholder(1)}
        order by kcu.ordinal_position
    """


def foreign_keys_query(dialect: SqlDialect) -> str:
    """Foreign keys with their targets.

    Two shapes, not two dialects: MySQL denormalises the target onto
    `key_column_usage`, while the SQL standard puts it in `constraint_column_usage`.
    Any dialect can declare either shape.
    """
    if dialect.foreign_keys_via_referenced_columns:
        return f"""
            select kcu.column_name,
                   kcu.referenced_table_name as target_table,
                   kcu.referenced_column_name as target_column
            from information_schema.key_column_usage kcu
            where kcu.table_schema = {dialect.current_schema_expression}
              and kcu.table_name = {dialect.placeholder(1)}
              and kcu.referenced_table_name is not null
        """
    return f"""
        select kcu.column_name,
               ccu.table_name as target_table,
               ccu.column_name as target_column
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name
         and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY'
          and tc.table_schema = {dialect.current_schema_expression}
          and tc.table_name = {dialect.placeholder(1)}
    """


def describe_dialect(dialect: SqlDialect) -> dict[str, object]:
    """A profile as reviewable data, for `aletheia doctor` and the API."""
    return {
        "name": dialect.name,
        "currentSchema": dialect.current_schema_expression,
        "quoting": f"{dialect.quote_open}…{dialect.quote_close}",
        "paramstyle": dialect.paramstyle,
        "rowLimitStyle": dialect.row_limit_style,
        "catalogUppercasesIdentifiers": dialect.catalog_uppercases_identifiers,
        "foreignKeysViaReferencedColumns": dialect.foreign_keys_via_referenced_columns,
        "aliases": sorted(alias for alias, target in _ALIASES.items() if target == dialect.name),
    }
