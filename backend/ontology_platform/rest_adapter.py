"""REST APIs as a read-only data source.

Generality item #12. The systems this exists for are the ones where nobody will give you
database access: a SaaS the business depends on, a vendor system under support contract, a
microservice whose database is deliberately private. In every one of those, the API *is*
the system of record's public surface -- and refusing to model it means the ontology stops
at the boundary of whatever happens to be in a database you can reach.

## Why this is a declaration, not an integration

A REST API has no `information_schema`, so the platform cannot discover its shape. It
could be *guessed* from a sample response, and that is the tempting answer -- but a schema
guessed from one payload changes when the payload changes, and a verdict resting on it
would be unreproducible (ADR-0005, same reasoning as relation classification).

So the endpoint's shape is declared:

```python
register_rest_source(RestSpec(
    source_type="crm",
    resources=(
        RestResource(
            name="customers",
            list_path="/api/customers",
            detail_path="/api/customers/{id}",
            primary_key="id",
            fields=("id", "name", "credit_status"),
        ),
    ),
))
```

If a deployment already has an OpenAPI document, `resources_from_openapi` derives the
declaration from it -- which is a *declared* schema, just one written by the API's owner
rather than by hand.

## Read-only, and that is not a limitation to fix here

No write path. Writing back to a legacy system already has an owner -- `automation.py`,
with preflight, capability checks and audit. A data source that could also write would
create a second, ungoverned way to mutate a business system.

## Bounded, cached within one assessment

An assessment reads related rows repeatedly; without caching, a single verdict could issue
dozens of HTTP calls to the same endpoint. The cache lives for the duration of one runtime
context and no longer: caching across assessments would serve a verdict from data that has
since changed, with nothing in the decision record saying so.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Sequence

from .adapters import (
    ColumnProfile,
    SourceColumnInfo,
    SourceTableInfo,
    connection_status,
    register_adapter,
)
from .config import QUERY_LIMITS
from .instance_key import InstanceKey

logger = logging.getLogger(__name__)

# A single list call must not become an unbounded download.
MAX_REST_ROWS = 1_000
DEFAULT_TIMEOUT_SECONDS = 10


class RestSourceError(ValueError):
    """Raised when a REST declaration or response is unusable."""


@dataclass(frozen=True)
class RestResource:
    """One endpoint, modelled as a table.

    `fields` is declared rather than sampled: a schema inferred from one payload changes
    when the payload changes, and a verdict resting on it would be unreproducible.
    """

    name: str
    list_path: str
    primary_key: str = "id"
    # Optional; when absent, a single instance is found by filtering the list response.
    detail_path: str = ""
    fields: Sequence[str] = ()
    # Where the rows live in the response, e.g. `data.items`. Empty means the body is
    # already a list.
    items_path: str = ""
    # Declared types per field, for the ones that matter to rules. Unlisted fields are
    # text, which is the safe default: calling a field numeric when it is not would make
    # a comparison fail closed on the rows that disagree.
    field_types: dict[str, str] = field(default_factory=dict)

    def validate(self) -> "RestResource":
        if not self.name or not self.name.replace("_", "").isalnum():
            raise RestSourceError(f"资源名必须是字母数字或下划线: {self.name!r}")
        if not self.list_path.startswith("/"):
            raise RestSourceError(f"{self.name} 的 listPath 必须以 / 开头: {self.list_path!r}")
        if not self.fields:
            raise RestSourceError(f"{self.name} 必须声明字段列表：REST 响应没有可供发现的模式")
        if self.primary_key not in self.fields:
            raise RestSourceError(f"{self.name} 的主键 {self.primary_key!r} 不在已声明字段中")
        return self


@dataclass(frozen=True)
class RestSpec:
    """A REST API as a data source type."""

    source_type: str
    resources: Sequence[RestResource] = ()
    # Headers merged into every request. Credentials belong in the data source's stored
    # `api_headers`, not here -- this is for constants like `Accept`.
    headers: dict[str, str] = field(default_factory=lambda: {"Accept": "application/json"})
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def validate(self) -> "RestSpec":
        if not self.source_type or not self.source_type.replace("_", "").isalnum():
            raise RestSourceError(f"数据源类型必须是字母数字或下划线: {self.source_type!r}")
        if not self.resources:
            raise RestSourceError(f"{self.source_type} 未声明任何资源")
        names = [resource.validate().name for resource in self.resources]
        if len(set(names)) != len(names):
            raise RestSourceError(f"{self.source_type} 存在重名资源: {names}")
        return self

    def resource(self, name: str) -> RestResource:
        for resource in self.resources:
            if resource.name == name:
                return resource
        raise RestSourceError(f"未声明的资源: {name}。已声明: {'、'.join(r.name for r in self.resources)}")


def resources_from_openapi(document: dict[str, Any]) -> list[RestResource]:
    """Derive resource declarations from an OpenAPI document.

    Still a declaration -- just one written by the API's owner. Only collection endpoints
    with an array response and an object schema are used; anything whose shape cannot be
    read from the document is skipped rather than guessed, and the skip is logged so a
    modeller knows to declare it by hand.
    """
    resources: list[RestResource] = []
    for path, operations in (document.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        get = operations.get("get")
        if not isinstance(get, dict) or "{" in path:
            continue
        schema = _array_item_schema(get)
        if schema is None:
            logger.debug("跳过 %s：响应不是对象数组，无法据此声明字段", path)
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            logger.debug("跳过 %s：响应模式没有属性声明", path)
            continue
        name = path.strip("/").replace("/", "_").replace("-", "_")
        fields = tuple(str(key) for key in properties)
        primary_key = "id" if "id" in fields else fields[0]
        detail = f"{path.rstrip('/')}/{{id}}"
        resources.append(
            RestResource(
                name=name,
                list_path=path,
                detail_path=detail if isinstance(operations.get("get"), dict) else "",
                primary_key=primary_key,
                fields=fields,
                field_types={
                    str(key): _openapi_type(value) for key, value in properties.items() if isinstance(value, dict)
                },
            )
        )
    return resources


def _array_item_schema(operation: dict[str, Any]) -> Optional[dict[str, Any]]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None
    for status in ("200", 200, "default"):
        response = responses.get(status)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        for media_type, media in content.items():
            if "json" not in str(media_type) or not isinstance(media, dict):
                continue
            schema = media.get("schema")
            if not isinstance(schema, dict):
                continue
            if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
                return schema["items"]
            if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
                # A wrapper like {"items": [...]}; the array is one level down.
                for value in schema["properties"].values():
                    if (
                        isinstance(value, dict)
                        and value.get("type") == "array"
                        and isinstance(value.get("items"), dict)
                    ):
                        return value["items"]
    return None


def _openapi_type(schema: dict[str, Any]) -> str:
    mapping = {"integer": "integer", "number": "number", "boolean": "boolean", "string": "text"}
    declared = str(schema.get("type") or "string")
    if declared == "string" and schema.get("format") in ("date", "date-time"):
        return "date" if schema["format"] == "date" else "timestamp"
    return mapping.get(declared, "text")


def _extract_items(payload: Any, items_path: str) -> list[dict[str, Any]]:
    """Pull the row list out of a response body.

    A response that is not a list of objects raises rather than returning nothing: an
    empty result would read as "this resource has no rows", which is a different and much
    more confusing failure than "the declaration does not match the response".
    """
    current = payload
    for segment in (segment for segment in items_path.split(".") if segment):
        if not isinstance(current, dict) or segment not in current:
            raise RestSourceError(f"响应中找不到 itemsPath 片段 {segment!r}")
        current = current[segment]
    if isinstance(current, dict):
        # A single object is a one-row result, which is what a detail endpoint returns.
        return [current]
    if not isinstance(current, list):
        raise RestSourceError(f"响应不是对象列表: {type(current).__name__}")
    return [row for row in current if isinstance(row, dict)]


class RestRuntime:
    """Runtime reads over a declared REST API.

    Responses are cached for the life of this object -- one assessment -- because an
    assessment reads related rows repeatedly and would otherwise issue dozens of calls to
    the same endpoint. Caching any longer would serve a verdict from data that has since
    changed, with nothing in the decision record saying so.
    """

    def __init__(self, spec: RestSpec, base_url: str, headers: Optional[dict[str, str]] = None):
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.headers = {**spec.headers, **(headers or {})}
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.spec.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            raise RestSourceError(f"请求 {url} 返回 {error.code}: {error.reason}") from error
        except Exception as error:
            raise RestSourceError(f"请求 {url} 失败: {error}") from error
        try:
            return json.loads(body)
        except ValueError as error:
            raise RestSourceError(f"{url} 返回的不是 JSON") from error

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        if table_name in self._cache:
            return self._cache[table_name]
        resource = self.spec.resource(table_name)
        payload = self._get(resource.list_path)
        raw = _extract_items(payload, resource.items_path)
        if len(raw) > MAX_REST_ROWS:
            logger.warning("%s 返回 %s 行，超过 %s 上限，已截断", table_name, len(raw), MAX_REST_ROWS)
            raw = raw[:MAX_REST_ROWS]
        rows = [_project(row, resource) for row in raw]
        self._cache[table_name] = rows
        return rows

    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        rows = self.rows(table_name)
        return rows[offset : offset + limit], len(rows)

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]:
        resource = self.spec.resource(table_name)
        return [row.get(resource.primary_key) for row in self.rows(table_name)[:limit]]

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> Optional[dict[str, Any]]:
        resource = self.spec.resource(table_name)
        if resource.detail_path:
            # A detail endpoint is one call instead of downloading the collection, and it
            # is also the only correct option when the list endpoint is paginated.
            try:
                payload = self._get(resource.detail_path.replace("{id}", str(instance_id)))
                rows = _extract_items(payload, resource.items_path)
                return _project(rows[0], resource) if rows else None
            except RestSourceError as error:
                logger.debug("详情端点不可用，回退到列表过滤: %s", error)
        key = InstanceKey.from_token(primary_key, instance_id)
        for row in self.rows(table_name):
            if all(str(row.get(column)) == str(value) for column, value in key.as_mapping().items()):
                return row
        return None

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> Optional[dict[str, Any]]:
        rows = self.fetch_related_many(table_name, column_name, value)
        return rows[0] if rows else None

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        try:
            rows = self.rows(table_name)
        except RestSourceError as error:
            # A declared relation whose endpoint is unreachable yields no rows rather than
            # failing the assessment; the rule referencing it then fails closed.
            logger.debug("关联资源不可读: %s", error)
            return []
        return [row for row in rows if str(row.get(column_name)) == str(value)]


def _project(row: dict[str, Any], resource: RestResource) -> dict[str, Any]:
    """Keep the declared fields, coerced to their declared types.

    Undeclared fields are dropped: the declaration is the contract, and silently passing
    through whatever the API returned would make a rule's available names depend on the
    payload of the moment.
    """
    projected: dict[str, Any] = {}
    for name in resource.fields:
        value = row.get(name)
        projected[name] = _coerce(value, resource.field_types.get(name, "text"))
    return projected


def _coerce(value: Any, data_type: str) -> Any:
    if value is None:
        return None
    try:
        if data_type == "integer":
            return int(value)
        if data_type == "number":
            return float(value)
        if data_type == "boolean":
            return bool(value) if not isinstance(value, str) else value.strip().lower() in ("true", "1", "yes")
    except (TypeError, ValueError):
        # An unparseable value stays as-is rather than becoming None: a rule comparing it
        # then fails closed with a type error, which is visible, instead of comparing
        # against a fabricated absence.
        return value
    return value


class RestAdapter:
    """A `DatabaseAdapter` over a declared REST API."""

    def __init__(self, spec: RestSpec):
        self.spec = spec.validate()
        self.source_type = spec.source_type

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        runtime = RestRuntime(self.spec, connection_uri)
        first = self.spec.resources[0]
        try:
            runtime.rows(first.name)
        except RestSourceError as error:
            return connection_status(self.source_type, False, "connection_error", str(error))
        return connection_status(self.source_type, True, "ok", f"API 可读，{first.name} 端点返回了有效 JSON。")

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        """Build table metadata from the declaration, profiled against live rows.

        The *shape* comes from the declaration; only the profile (samples, null ratio,
        distinct count) comes from the data. That split is what keeps a rescan from
        changing the model when the payload changes.
        """
        runtime = RestRuntime(self.spec, connection_uri)
        tables = []
        for resource in self.spec.resources:
            try:
                rows = runtime.rows(resource.name)
            except RestSourceError as error:
                logger.warning("资源 %s 不可读，按空表登记: %s", resource.name, error)
                rows = []
            columns = []
            for ordinal, name in enumerate(resource.fields):
                values = [row.get(name) for row in rows]
                present = [value for value in values if value is not None]
                distinct = len({str(value) for value in present})
                columns.append(
                    SourceColumnInfo(
                        name=name,
                        data_type=resource.field_types.get(name, "text"),
                        nullable=len(present) < len(values) if values else True,
                        ordinal=ordinal,
                        is_primary_key=name == resource.primary_key,
                        profile=ColumnProfile(
                            samples=sorted({str(value) for value in present})[: QUERY_LIMITS.column_profile_samples],
                            null_ratio=0.0 if not values else (len(values) - len(present)) / len(values),
                            distinct_count=distinct,
                            enum_candidate=(
                                QUERY_LIMITS.enum_min_distinct <= distinct <= QUERY_LIMITS.enum_max_distinct
                            ),
                        ),
                    )
                )
            tables.append(
                SourceTableInfo(
                    name=resource.name,
                    row_count=len(rows),
                    primary_key=resource.primary_key,
                    columns=columns,
                    # A REST API declares no referential structure, and guessing it from
                    # field names would produce relations resting on a naming coincidence
                    # (same reasoning as the CSV adapter).
                    foreign_keys=[],
                )
            )
        return tables

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[RestRuntime]:
        yield RestRuntime(self.spec, connection_uri)


def register_rest_source(spec: RestSpec, *, replace: bool = False) -> RestSpec:
    """Make a declared REST API available as a data source type."""
    spec.validate()
    register_adapter(spec.source_type, lambda: RestAdapter(spec), replace=replace)
    return spec


def register_openapi_source(
    source_type: str,
    document: dict[str, Any],
    *,
    headers: Optional[dict[str, str]] = None,
    replace: bool = False,
) -> RestSpec:
    """Declare a REST source from an OpenAPI document.

    Fails loudly when nothing usable can be derived: registering an empty source type
    would look like success and then behave as though the API had no data.
    """
    resources = resources_from_openapi(document)
    if not resources:
        raise RestSourceError(
            "OpenAPI 文档中没有可用于声明的集合端点（需要返回对象数组的 GET 端点）。请手工声明 RestResource。"
        )
    spec = RestSpec(
        source_type=source_type,
        resources=tuple(resources),
        headers={"Accept": "application/json", **(headers or {})},
    )
    return register_rest_source(spec, replace=replace)
