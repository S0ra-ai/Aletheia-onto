"""Instance keys: how a business object identifies one of its instances.

The platform used to assume every object is identified by a single column, and
raised outright when it met a composite primary key. That assumption is wrong for
a large share of legacy schemas -- junction tables, versioned records and
partitioned history tables routinely key on two or three columns.

An `InstanceKey` separates three things that were previously conflated:

- the *definition*: which columns identify an instance (from source_table.primary_key)
- the *value*: the concrete values for one instance
- the *token*: the URL-safe string used in APIs and stored in decision records

Token format for composite keys is ``col=value`` pairs joined by ``;``, where
column and value are percent-encoded. Single-column keys keep their bare,
unencoded value as the token, so every existing decision record, audit row and
API caller keeps working unchanged -- that backwards compatibility is the reason
for the asymmetry.

Percent-encoding is used rather than a hand-rolled escape scheme because
``quote``/``unquote`` are exact inverses and already handle the delimiters,
backslashes and non-ASCII values that a business key can legitimately contain.
An earlier hand-written escape pass lost literal backslashes.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import quote, unquote

PAIR_SEPARATOR = ";"
VALUE_SEPARATOR = "="
# Everything outside the unreserved set is encoded, so the delimiters can never
# appear inside an encoded component.
_SAFE_CHARS = ""


class InstanceKeyError(ValueError):
    """Raised when a key definition or token cannot be interpreted."""


def parse_key_columns(primary_key: str | None) -> tuple[str, ...]:
    """Split a stored primary key definition into column names.

    Accepts the comma-separated form that metadata scanning produces for
    composite keys. Falls back to ``id`` because that is what the previous
    single-column code path did when a table reported no key at all.
    """
    raw = (primary_key or "").strip()
    if not raw:
        return ("id",)
    columns = tuple(part.strip() for part in raw.split(",") if part.strip())
    return columns or ("id",)


def is_composite(primary_key: str | None) -> bool:
    return len(parse_key_columns(primary_key)) > 1


def _encode(text: str) -> str:
    return quote(text, safe=_SAFE_CHARS)


def _decode(text: str) -> str:
    return unquote(text)


@dataclass(frozen=True)
class InstanceKey:
    """One instance's identity: ordered column names plus their values."""

    columns: tuple[str, ...]
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if not self.columns:
            raise InstanceKeyError("实例键至少需要一个列")
        if len(self.columns) != len(self.values):
            raise InstanceKeyError(f"实例键列数与值数不匹配: {len(self.columns)} 列 / {len(self.values)} 值")

    @property
    def composite(self) -> bool:
        return len(self.columns) > 1

    @property
    def token(self) -> str:
        """The string form used in URLs, decision records and audit rows."""
        if not self.composite:
            return str(self.values[0])
        return PAIR_SEPARATOR.join(
            f"{_encode(column)}{VALUE_SEPARATOR}{_encode(str(value))}"
            # strict is redundant given __post_init__, and stated anyway: a token is
            # what a decision record stores, so a key silently missing a column would
            # make two different instances share one audit identity.
            for column, value in zip(self.columns, self.values, strict=True)
        )

    def as_mapping(self) -> dict[str, Any]:
        return dict(zip(self.columns, self.values, strict=True))

    def where_clause(self, quote: Any, placeholder: str = "?") -> tuple[str, tuple[Any, ...]]:
        """Build a parameterised WHERE fragment.

        `quote` renders one identifier; values are always bound as parameters so
        a key value can never reach the SQL text.
        """
        conditions = " and ".join(f"{quote(column)} = {placeholder}" for column in self.columns)
        return conditions, tuple(self.values)

    def describe(self) -> str:
        if not self.composite:
            return str(self.values[0])
        return ", ".join(f"{c}={v}" for c, v in zip(self.columns, self.values, strict=True))

    @classmethod
    def from_token(cls, primary_key: str | None, token: str) -> "InstanceKey":
        """Rebuild a key from its token form.

        Single-column keys accept the bare value, which is what every existing
        caller sends. Composite keys accept the ``col=value;col=value`` form and,
        as a convenience for hand-written requests, a bare ordered list joined by
        ``;`` when no ``=`` is present.
        """
        columns = parse_key_columns(primary_key)
        text = "" if token is None else str(token)
        if len(columns) == 1:
            return cls(columns=columns, values=(text,))

        parts = [part for part in text.split(PAIR_SEPARATOR) if part != ""]
        if not parts:
            raise InstanceKeyError(f"复合主键实例需要 {len(columns)} 个键值，收到空标识")

        if all(VALUE_SEPARATOR not in part for part in parts):
            # Positional form: values in the key's declared column order.
            if len(parts) != len(columns):
                raise InstanceKeyError(
                    f"复合主键需要 {len(columns)} 个值（{', '.join(columns)}），收到 {len(parts)} 个"
                )
            return cls(columns=columns, values=tuple(_decode(part) for part in parts))

        mapping: dict[str, str] = {}
        for part in parts:
            # Percent-encoding guarantees no literal '=' survives inside either
            # component, so a single split is unambiguous.
            pieces = part.split(VALUE_SEPARATOR, 1)
            if len(pieces) != 2:
                raise InstanceKeyError(f"实例键片段格式应为 列=值：{part!r}")
            mapping[_decode(pieces[0])] = _decode(pieces[1])

        missing = [column for column in columns if column not in mapping]
        if missing:
            raise InstanceKeyError(f"实例键缺少列: {', '.join(missing)}")
        unexpected = [name for name in mapping if name not in columns]
        if unexpected:
            raise InstanceKeyError(
                f"实例键包含该对象主键之外的列: {', '.join(unexpected)}。主键为 {', '.join(columns)}"
            )
        return cls(columns=columns, values=tuple(mapping[column] for column in columns))

    @classmethod
    def from_row(cls, primary_key: str | None, row: Mapping[str, Any]) -> "InstanceKey":
        """Extract a key from a fetched row."""
        columns = parse_key_columns(primary_key)
        missing = [column for column in columns if column not in row]
        if missing:
            raise InstanceKeyError(f"数据行缺少主键列: {', '.join(missing)}")
        return cls(columns=columns, values=tuple(row[column] for column in columns))

    @classmethod
    def from_values(cls, primary_key: str | None, values: Iterable[Any]) -> "InstanceKey":
        columns = parse_key_columns(primary_key)
        return cls(columns=columns, values=tuple(values))
