"""Generic business-object browsing service.

This is the read-side counterpart to ontology modelling: a business object can be
consumed through one stable API without callers knowing which legacy table or
resolver backs it.  Authorization is deliberately performed before a record is
returned, including row-level filters.
"""

from __future__ import annotations

import json
from typing import Any

from .adapters import get_adapter
from .config import clamp_page_size
from .context import PlatformDb
from .database import connect
from .instance_resolver import ResolverSpec, build_resolver
from .workflow_permission import check_permission


class ObjectAccessError(ValueError):
    """The caller cannot read the requested business object or instance."""


def _json_value(value: Any) -> Any:
    """Normalize adapter values into JSON-safe values without losing information."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _load_target(platform_db: PlatformDb, ontology_id: int, object_code: str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        ontology = conn.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")
        row = conn.execute(
            """
            select bo.*, st.table_name, st.primary_key, st.data_source_id,
                   ds.name as data_source_name, ds.source_type, ds.connection_uri
            from business_object bo
            left join source_table st on st.id = bo.source_table_id
            left join data_source ds on ds.id = st.data_source_id
            where bo.ontology_id = ? and bo.code = ?
            """,
            (ontology_id, object_code),
        ).fetchone()
        if row is None:
            raise ValueError(f"业务对象不存在: {object_code}")
        target = dict(row)
        attributes = conn.execute(
            """
            select ba.code, ba.name, ba.data_type, ba.required, sc.column_name,
                   sc.data_type as source_data_type
            from business_attribute ba
            left join source_column sc on sc.id = ba.source_column_id
            where ba.object_id = ?
            order by ba.id
            """,
            (int(row["id"]),),
        ).fetchall()
    target["ontology"] = dict(ontology)
    target["attributes"] = [dict(attribute) for attribute in attributes]
    return target


def _resolver(target: dict[str, Any]) -> Any:
    spec = ResolverSpec.from_json(
        target.get("resolver_spec") or "",
        table=target.get("table_name") or "",
        primary_key=target.get("primary_key") or "id",
    )
    return build_resolver(spec)


def _authorize(
    platform_db: PlatformDb,
    role_code: str,
    object_code: str,
    ontology_id: int,
    instance_id: str = "",
) -> dict[str, Any]:
    decision = check_permission(
        platform_db,
        role_code,
        object_code,
        "read",
        ontology_id=ontology_id,
        instance_id=instance_id,
    )
    if not decision.get("allowed"):
        raise ObjectAccessError(decision.get("reason") or "无权读取该业务对象")
    return decision


def _item(instance_id: str, record: dict[str, Any], tables: tuple[str, ...]) -> dict[str, Any]:
    return {
        "instanceId": str(instance_id),
        "record": _json_value(record),
        "tables": list(tables),
    }


def list_object_instances(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    *,
    role_code: str,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """List readable instances of an ontology business object."""
    target = _load_target(platform_db, ontology_id, object_code)
    _authorize(platform_db, role_code, object_code, ontology_id)
    resolved_limit = clamp_page_size(limit)
    resolved_offset = max(0, int(offset or 0))
    resolver = _resolver(target)
    if not target.get("source_type") or not target.get("connection_uri"):
        raise ValueError(f"业务对象未绑定可用数据源: {object_code}")

    # Resolver APIs intentionally expose opaque ids rather than SQL offsets.  Fetch a
    # bounded but generous id set, then apply row-level authorization before slicing.
    # This keeps joined/discriminated/custom resolvers on the same security path.
    with get_adapter(target["source_type"]).runtime(target["connection_uri"]) as runtime:
        ids = resolver.list_ids(runtime, limit=max(resolved_offset + resolved_limit, 100000))
        readable: list[dict[str, Any]] = []
        for raw_id in ids:
            instance_id = str(raw_id)
            try:
                _authorize(platform_db, role_code, object_code, ontology_id, instance_id)
            except ObjectAccessError:
                continue
            record = resolver.fetch(runtime, instance_id)
            if record is not None:
                readable.append(_item(instance_id, record, resolver.tables()))

    page_items = readable[resolved_offset : resolved_offset + resolved_limit]
    total = len(readable)
    return {
        "ontology": {
            "id": target["ontology"]["id"],
            "name": target["ontology"]["name"],
            "domain": target["ontology"]["domain"],
            "version": target["ontology"]["version"],
            "status": target["ontology"]["status"],
        },
        "object": {
            "id": target["id"],
            "code": target["code"],
            "name": target["name"],
            "description": target["description"],
            "sourceTable": target.get("table_name") or "",
            "sourceType": target.get("source_type") or "",
            "dataSourceId": target.get("data_source_id"),
            "resolver": resolver.describe(),
        },
        "attributes": [
            {
                "code": attr["code"],
                "name": attr["name"],
                "dataType": attr.get("data_type") or attr.get("source_data_type") or "",
                "required": bool(attr.get("required")),
                "sourceColumn": attr.get("column_name") or "",
            }
            for attr in target["attributes"]
        ],
        "items": page_items,
        "pagination": {
            "limit": resolved_limit,
            "offset": resolved_offset,
            "total": total,
            "hasMore": resolved_offset + resolved_limit < total,
        },
    }


def get_object_instance(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    *,
    role_code: str,
) -> dict[str, Any]:
    """Fetch one readable business-object instance."""
    target = _load_target(platform_db, ontology_id, object_code)
    _authorize(platform_db, role_code, object_code, ontology_id)
    resolver = _resolver(target)
    if not target.get("source_type") or not target.get("connection_uri"):
        raise ValueError(f"业务对象未绑定可用数据源: {object_code}")
    with get_adapter(target["source_type"]).runtime(target["connection_uri"]) as runtime:
        _authorize(platform_db, role_code, object_code, ontology_id, str(instance_id))
        record = resolver.fetch(runtime, str(instance_id))
    if record is None:
        raise ValueError(f"实例不存在: {object_code}/{instance_id}")
    return {
        "ontology": {
            "id": target["ontology"]["id"],
            "name": target["ontology"]["name"],
            "version": target["ontology"]["version"],
            "status": target["ontology"]["status"],
        },
        "object": {
            "code": target["code"],
            "name": target["name"],
            "sourceTable": target.get("table_name") or "",
            "resolver": resolver.describe(),
        },
        **_item(str(instance_id), record, resolver.tables()),
    }
