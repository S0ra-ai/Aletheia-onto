"""CSV directories as a data source.

Generality item #12. The case this exists for is not "someone likes spreadsheets": it is
that a large share of legacy business data is only reachable as an export. A department's
authoritative record is a nightly dump on a share; a system being decommissioned leaves
behind CSVs and no server; a customer's first evaluation of this platform is against an
extract, because getting production database credentials takes weeks.

Without this, that first evaluation cannot happen at all.

## What is inferred, and what is not

A CSV has no schema, so the adapter infers one -- but only the parts that can be
inferred *soundly*:

| Inferred | How |
|---|---|
| column names | header row |
| data type | every non-empty value parses as the type, or it is text |
| nullability | an empty value appears |
| primary key | column named `id`, or `<file>_id`, whose values are unique and complete |

**Foreign keys are not inferred.** A `customer_id` column in `contracts.csv` alongside a
`customers.csv` looks like a foreign key, and usually is -- but relation semantics
(ADR-0012) are built on the premise that structure is *declared*, never guessed. A
guessed foreign key would produce a relation whose cardinality and strength rest on a
coincidence of naming, and a verdict citing it would be unexplainable. So relations for
file sources are declared by the modeller, and the adapter reports the candidates it
noticed rather than acting on them.

Type inference is different: a column's type is a property of its values, it is
re-derived identically on every scan, and being wrong about it degrades a label rather
than fabricating a relationship.

## Files are read, never written

There is no write path. The platform reads metadata and produces verdicts; a CSV source
is an inbound extract, and writing back into someone's export directory would be a
silent, untraceable mutation of a file another system owns.

## Bounded reads

A CSV is read fully to answer `count(*)`, which is fine at extract scale and wrong at
warehouse scale. `MAX_FILE_ROWS` caps it and the cap being hit is reported, because a
silently truncated row count makes a coverage report wrong rather than partial.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import csv
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import unquote, urlparse

from .adapters import (
    ColumnProfile,
    SourceColumnInfo,
    SourceTableInfo,
    connection_status,
    register_adapter,
)
from .config import QUERY_LIMITS
from .instance_key import InstanceKey, parse_key_columns

logger = logging.getLogger(__name__)

# One CSV is read fully per query. Fine at extract scale, wrong at warehouse scale; the
# cap being hit is reported rather than silently truncating.
MAX_FILE_ROWS = 200_000

CSV_SUFFIXES = (".csv", ".tsv")


class FileSourceError(ValueError):
    """Raised when a file source path or layout is unusable."""


def resolve_directory(connection_uri: str) -> Path:
    """Interpret a connection URI as a directory of CSV files.

    Accepts `file:///abs/path`, `csv:///abs/path` or a bare path. Percent-decoded because
    a Windows share or a Chinese directory name arrives encoded when it came through a
    URL field.
    """
    text = (connection_uri or "").strip()
    if not text:
        raise FileSourceError("文件数据源需要一个目录路径")
    parsed = urlparse(text)
    if parsed.scheme in ("file", "csv"):
        raw = unquote(parsed.path or "")
        # `file://./relative` puts the first segment in netloc.
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            raw = f"{unquote(parsed.netloc)}{raw}"
    else:
        raw = text
    path = Path(raw).expanduser()
    if not path.exists():
        raise FileSourceError(f"目录不存在: {path}")
    if not path.is_dir():
        # A single file is accepted too, treated as a one-table source: that is what a
        # user pointing at `contracts.csv` means.
        return path.parent
    return path


def _table_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in CSV_SUFFIXES and not path.name.startswith(".")
    )


def _delimiter_for(path: Path) -> str:
    return "\t" if path.suffix.lower() == ".tsv" else ","


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]], bool]:
    """Read one CSV, returning (header, rows, truncated)."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=_delimiter_for(path))
        header = [name for name in (reader.fieldnames or []) if name]
        if not header:
            return [], [], False
        rows: list[dict[str, str]] = []
        truncated = False
        for index, row in enumerate(reader):
            if index >= MAX_FILE_ROWS:
                truncated = True
                logger.warning("%s 超过 %s 行上限，已截断", path.name, MAX_FILE_ROWS)
                break
            rows.append({key: (value if value is not None else "") for key, value in row.items() if key})
        return header, rows, truncated


def _looks_like(value: str, kind: str) -> bool:
    if kind == "integer":
        text = value.strip()
        if text.startswith(("-", "+")):
            text = text[1:]
        return text.isdigit()
    if kind == "number":
        try:
            float(value)
            return True
        except ValueError:
            return False
    if kind == "boolean":
        return value.strip().lower() in ("true", "false", "0", "1", "yes", "no", "y", "n")
    if kind == "date":
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                datetime.strptime(value.strip(), pattern)
                return True
            except ValueError:
                continue
        return False
    if kind == "timestamp":
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                datetime.strptime(value.strip(), pattern)
                return True
            except ValueError:
                continue
        return False
    return False


def infer_column_type(values: list[str]) -> str:
    """The narrowest type every non-empty value satisfies.

    Ordered narrowest-first so `1` reads as integer rather than number, and falls back to
    `text` rather than guessing: a column that is 99% integers and 1% `"N/A"` is text, and
    calling it integer would make a rule comparing it fail closed on those rows.
    """
    present = [value for value in values if value != "" and value is not None]
    if not present:
        return "text"
    for kind in ("integer", "number", "boolean", "date", "timestamp"):
        if all(_looks_like(value, kind) for value in present):
            return kind
    return "text"


def coerce_value(value: str, data_type: str) -> Any:
    """Convert a cell to its inferred type, leaving unparseable values as text.

    Rules compare against real numbers and dates, so a numeric column arriving as
    strings would make `amount > 0` compare `str > int` -- which fail-closed then reports
    as a violation, turning a parsing detail into a wrong verdict (ADR-0002).
    """
    if value == "" or value is None:
        return None
    try:
        if data_type == "integer":
            return int(value)
        if data_type == "number":
            return float(value)
        if data_type == "boolean":
            return value.strip().lower() in ("true", "1", "yes", "y")
        if data_type == "date":
            for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(value.strip(), pattern).date().isoformat()
                except ValueError:
                    continue
        if data_type == "timestamp":
            for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(value.strip(), pattern).isoformat(sep=" ")
                except ValueError:
                    continue
    except (TypeError, ValueError):
        return value
    return value


def infer_primary_key(table_name: str, header: list[str], rows: list[dict[str, str]]) -> str:
    """A single-column key, only when the data proves it is one.

    Requires the column to be complete *and* unique across the rows read. A key inferred
    from the name alone would make `fetch_one` return an arbitrary row when the values
    repeat -- an instance identity that silently points at the wrong record.
    """
    stem = table_name.rstrip("s")
    candidates = [name for name in ("id", f"{table_name}_id", f"{stem}_id") if name in header]
    candidates += [name for name in header if name.lower().endswith("_id") and name not in candidates]
    for candidate in candidates:
        values = [row.get(candidate, "") for row in rows]
        if any(value == "" for value in values):
            continue
        if len(set(values)) == len(values):
            return candidate
    return ""


def foreign_key_candidates(directory: Path) -> list[dict[str, str]]:
    """Columns that *look* like foreign keys, reported rather than acted on.

    Deliberately not returned as foreign keys: relation semantics (ADR-0012) rest on
    declared structure, and a relation whose cardinality came from a naming coincidence
    would be unexplainable. Surfacing candidates lets a modeller declare the real ones.
    """
    files = _table_files(directory)
    table_names = {path.stem for path in files}
    candidates: list[dict[str, str]] = []
    for path in files:
        header, _, _ = _read_rows(path)
        for column in header:
            if not column.lower().endswith("_id"):
                continue
            stem = column[:-3]
            for target in (stem, f"{stem}s", stem.rstrip("s")):
                if target in table_names and target != path.stem:
                    candidates.append(
                        {"sourceTable": path.stem, "column": column, "targetTable": target, "targetColumn": "id"}
                    )
                    break
    return candidates


class CSVRuntime:
    """Runtime reads over CSV files.

    Each call re-reads its file. Deliberately: an extract can be replaced between calls,
    and caching would serve a verdict from data that is no longer what the file says --
    with nothing in the decision record indicating which version was used.
    """

    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, table_name: str) -> Path:
        for suffix in CSV_SUFFIXES:
            candidate = self.directory / f"{table_name}{suffix}"
            if candidate.exists():
                return candidate
        raise FileSourceError(f"文件不存在: {table_name}{CSV_SUFFIXES[0]}（在 {self.directory}）")

    def _typed_rows(self, table_name: str) -> list[dict[str, Any]]:
        path = self._path(table_name)
        header, rows, _ = _read_rows(path)
        types = {column: infer_column_type([row.get(column, "") for row in rows]) for column in header}
        return [{column: coerce_value(row.get(column, ""), types[column]) for column in header} for row in rows]

    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        rows = self._typed_rows(table_name)
        return rows[offset : offset + limit], len(rows)

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]:
        columns = parse_key_columns(primary_key)
        rows = self._typed_rows(table_name)[:limit]
        if len(columns) == 1:
            return [row.get(columns[0]) for row in rows]
        return [InstanceKey.from_row(primary_key, row).token for row in rows]

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> Optional[dict[str, Any]]:
        key = InstanceKey.from_token(primary_key, instance_id)
        for row in self._typed_rows(table_name):
            # Compared as strings because a CSV's `1` and a token's `"1"` are the same
            # instance, and the token has no type information.
            if all(str(row.get(column)) == str(value) for column, value in key.as_mapping().items()):
                return row
        return None

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> Optional[dict[str, Any]]:
        rows = self.fetch_related_many(table_name, column_name, value)
        return rows[0] if rows else None

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        try:
            rows = self._typed_rows(table_name)
        except FileSourceError:
            # A declared relation whose target file is absent yields no rows rather than
            # failing the whole assessment; the rule referencing it then fails closed.
            logger.debug("关联表文件不存在: %s", table_name)
            return []
        return [row for row in rows if str(row.get(column_name)) == str(value)]


class CSVAdapter:
    """A `DatabaseAdapter` over a directory of CSV files."""

    source_type = "csv"

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        try:
            directory = resolve_directory(connection_uri)
        except FileSourceError as error:
            return connection_status(self.source_type, False, "connection_error", str(error))
        files = _table_files(directory)
        if not files:
            return connection_status(
                self.source_type,
                False,
                "connection_error",
                f"目录 {directory} 中没有 CSV／TSV 文件。",
            )
        return connection_status(
            self.source_type,
            True,
            "ok",
            f"目录可读，发现 {len(files)} 个数据文件: {'、'.join(path.name for path in files[:5])}",
        )

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        directory = resolve_directory(connection_uri)
        tables = []
        for path in _table_files(directory):
            header, rows, truncated = _read_rows(path)
            if not header:
                logger.warning("跳过没有表头的文件: %s", path.name)
                continue
            if truncated:
                logger.warning("%s 行数超过上限，统计值为截断后的结果", path.name)
            primary_key = infer_primary_key(path.stem, header, rows)
            columns = []
            for ordinal, column in enumerate(header):
                values = [row.get(column, "") for row in rows]
                data_type = infer_column_type(values)
                present = [value for value in values if value != ""]
                distinct = len(set(present))
                columns.append(
                    SourceColumnInfo(
                        name=column,
                        data_type=data_type,
                        nullable=len(present) < len(values),
                        ordinal=ordinal,
                        is_primary_key=column == primary_key,
                        profile=ColumnProfile(
                            samples=sorted(set(present))[: QUERY_LIMITS.column_profile_samples],
                            null_ratio=0.0 if not values else (len(values) - len(present)) / len(values),
                            distinct_count=distinct,
                            enum_candidate=_is_enum_like(len(rows), distinct),
                        ),
                    )
                )
            tables.append(
                SourceTableInfo(
                    name=path.stem,
                    row_count=len(rows),
                    primary_key=primary_key,
                    columns=columns,
                    # Empty on purpose -- see the module docstring on why foreign keys are
                    # not inferred from column names.
                    foreign_keys=[],
                )
            )
        return tables

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[CSVRuntime]:
        yield CSVRuntime(resolve_directory(connection_uri))


def _is_enum_like(row_count: int, distinct_count: int) -> bool:
    """Same bounds as the SQL scanner, so a column does not change character by source."""
    if row_count <= 0 or distinct_count <= 1:
        return False
    return QUERY_LIMITS.enum_min_distinct <= distinct_count <= QUERY_LIMITS.enum_max_distinct


def describe_file_source(connection_uri: str) -> dict[str, Any]:
    """What the adapter found, including the foreign keys it declined to infer.

    Reported so a modeller can declare the real relations; see the module docstring for
    why they are not created automatically.
    """
    directory = resolve_directory(connection_uri)
    files = _table_files(directory)
    return {
        "directory": str(directory),
        "files": [path.name for path in files],
        "foreignKeyCandidates": foreign_key_candidates(directory),
        "note": "外键候选仅供参考，不会自动建立关系：关系语义要求结构是声明的，而非从命名猜测的。",
    }


# `file` is an alias because that is the scheme people type.
register_adapter("csv", CSVAdapter, aliases=("file",))
