"""Knowledge graph projection for visual preview.

An ontology is a graph, but every existing screen shows it as tables. Reviewers
cannot see that `contract` connects to `customer` but nothing points at
`invoice`, which is exactly the kind of modelling gap that tables hide.

This is a read-only projection built from what `summarize_ontology` already
returns -- no new tables, no new scanning. Layout is left to the frontend; the
backend only supplies nodes, edges and the degree/annotation data needed to
decide what deserves emphasis.

Design notes:

- Nodes carry `ruleCount` and `unmapped` so the view can highlight objects that
  produce no verdict or have no confirmed mapping. A graph that only shows shape
  is decorative; these two facts make it diagnostic.
- Every edge names the foreign key it came from. `relation_type` is currently
  always "references" (a known limitation), so the foreign key is what actually
  tells a reviewer why two objects are connected.
"""

from __future__ import annotations

from typing import Any

from .context import PlatformDb
from .database import connect


def build_ontology_graph(platform_db: PlatformDb, ontology_id: int) -> dict[str, Any]:
    """Nodes and edges for one ontology version."""
    with connect(platform_db) as conn:
        ontology = conn.execute(
            "select id, name, domain, version, status from ontology where id = ?", (ontology_id,)
        ).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")

        objects = conn.execute(
            """
            select bo.id, bo.code, bo.name, bo.description, st.table_name,
                   bo.source_table_id
            from business_object bo
            left join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ?
            order by bo.code
            """,
            (ontology_id,),
        ).fetchall()

        relations = conn.execute(
            """
            select br.id, br.code, br.name, br.relation_type,
                   so.code as source_code, tobj.code as target_code,
                   fk.column_name as source_foreign_key
            from business_relation br
            join business_object so on so.id = br.source_object_id
            join business_object tobj on tobj.id = br.target_object_id
            left join source_foreign_key fk on fk.id = br.source_foreign_key_id
            where br.ontology_id = ?
            order by br.id
            """,
            (ontology_id,),
        ).fetchall()

        attribute_counts = {
            row["object_code"]: int(row["count"])
            for row in conn.execute(
                """
                select bo.code as object_code, count(ba.id) as count
                from business_object bo
                left join business_attribute ba on ba.object_id = bo.id
                where bo.ontology_id = ?
                group by bo.code
                """,
                (ontology_id,),
            ).fetchall()
        }

        rule_counts = {
            row["scope_object_code"]: int(row["count"])
            for row in conn.execute(
                """
                select scope_object_code, count(*) as count from business_rule
                where ontology_id = ? group by scope_object_code
                """,
                (ontology_id,),
            ).fetchall()
        }

        confirmed_tables = {
            row["source_ref"]
            for row in conn.execute(
                """
                select source_ref from semantic_mapping
                where ontology_id = ? and mapping_type = 'table_to_object' and status = 'confirmed'
                """,
                (ontology_id,),
            ).fetchall()
        }

    degree: dict[str, int] = {}
    for relation in relations:
        degree[relation["source_code"]] = degree.get(relation["source_code"], 0) + 1
        degree[relation["target_code"]] = degree.get(relation["target_code"], 0) + 1

    nodes = []
    for row in objects:
        code = row["code"]
        table_name = row["table_name"]
        nodes.append(
            {
                "id": code,
                "code": code,
                "name": row["name"],
                "description": row["description"] or "",
                "sourceTable": table_name or "",
                "attributeCount": attribute_counts.get(code, 0),
                "ruleCount": rule_counts.get(code, 0),
                "degree": degree.get(code, 0),
                # Two diagnostics worth seeing at a glance.
                "unbound": row["source_table_id"] is None,
                "unmapped": bool(table_name) and table_name not in confirmed_tables,
            }
        )

    edges = [
        {
            "id": relation["id"],
            "code": relation["code"],
            "name": relation["name"],
            "source": relation["source_code"],
            "target": relation["target_code"],
            "relationType": relation["relation_type"],
            "foreignKey": relation["source_foreign_key"] or "",
        }
        for relation in relations
    ]

    isolated = [node["code"] for node in nodes if node["degree"] == 0]
    return {
        "ontology": {
            "id": ontology["id"],
            "name": ontology["name"],
            "domain": ontology["domain"],
            "version": ontology["version"],
            "status": ontology["status"],
        },
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "isolatedObjects": isolated,
            "objectsWithoutRules": [node["code"] for node in nodes if node["ruleCount"] == 0],
            "unmappedObjects": [node["code"] for node in nodes if node["unmapped"]],
        },
        "notes": {
            "relationTypes": sorted({edge["relationType"] for edge in edges}),
            "limitation": (
                "关系类型目前恒为 references，由外键派生；无基数、无多对多。边上的外键列名是判断关联含义的实际依据。"
            ),
        },
    }
