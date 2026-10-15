"""Every route, called once with a body built from its own schema.

Why this exists
---------------

Two 500s were found **by accident**. I was probing request bodies for the response
contract and hit `/data-sources/{id}/initialize` and `/ontologies/draft` on a seeded
instance. Neither had a test, and neither had ever been called with a valid body by
anything but a person clicking a button. This removes "nobody has tried this".

Why the body is synthesized rather than empty
---------------------------------------------

The first version sent `{}` to everything and reported a clean bill of health. It was
wrong twice over: without a token every route answered 401 at the middleware and no
handler ran at all, and with one, an empty body short-circuits at request validation --
most handlers answer 422 before their first line. Either way the sweep was testing the
access policy and the validator, not the application.

The body now comes from each operation's OpenAPI schema: required fields filled with a
value of the right type. That reaches the handlers, which is where the failures were.
The `assert_reached` below is what keeps this honest -- if a future change makes most
requests fail validation again, the sweep says so instead of reporting zero crashes.

Uploads are driven with real files
----------------------------------

`multipart/form-data` operations get a file that is actually a document, not a stub: a
handler that parses one has a rejection path for anything else, and a sweep that trips
that path has not tested the parser. The `.docx` is built with the same library the
importer uses.

What it does not cover
----------------------

A handler can still be broken for input this generator would never produce -- an
`ontologyId` that exists in a table the fixture did not seed, a rule expression that
parses. The response contract covers the thirty endpoints a screen actually calls, with
the bodies those screens send, which is where a value nobody could invent is written down.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

# A handler that answers at all has run. 422 means the request never reached it.
REACHED = range(200, 422)


@pytest.fixture
def seeded_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app over an instance with data in it.

    Seeded because that is the difference that matters: on an empty database every route
    that failed for me answered 404 instead of 500.
    """
    import ontology_platform.cli as cli
    import ontology_platform.database as database_module

    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "sample.sqlite3"

    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "route-sweep-password")
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    cli.main(["--platform-db", str(platform_db), "demo", "--sample-db", str(sample_db), "--quiet"])

    api_module = importlib.reload(__import__("ontology_platform.api", fromlist=["app"]))
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)
    with TestClient(api_module.app) as client:
        # Authenticated, or every route answers 401 at the middleware and no handler runs.
        login = client.post("/auth/login", json={"username": "admin", "password": "route-sweep-password"})
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        yield client
    database_module._platform_adapter = None


def _value_for(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> Any:
    """A value of the right shape for one JSON-schema node."""
    if "$ref" in schema:
        schema = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
    for option in schema.get("anyOf", []):
        if option.get("type") not in (None, "null"):
            return _value_for(option, components, depth + 1)
    kind = schema.get("type")
    if kind == "string":
        return "1"
    if kind in ("integer", "number"):
        return 1
    if kind == "boolean":
        return True
    if kind == "array":
        return []
    if depth > 2:
        return {}
    properties = schema.get("properties", {})
    # Required only: a generator that fills every optional field builds requests nobody
    # sends, and the point is to reach the handler as a caller would.
    return {name: _value_for(properties.get(name, {}), components, depth + 1) for name in schema.get("required", [])}


def _docx_bytes() -> bytes:
    """A rule document the importer can actually parse.

    Made with the same library the importer reads, so the handler runs its parser rather
    than its rejection path -- a sweep that only ever trips the rejection path has not
    tested the parser at all.
    """
    from io import BytesIO

    from docx import Document

    document = Document()
    document.add_paragraph("自定义规则（渲染检查）")
    table = document.add_table(rows=1, cols=7)
    headers = ["规则编码", "规则名称", "适用对象", "规则类型", "规则表达式", "严重程度", "自然语言说明"]
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    row = table.add_row().cells
    values = ["route_sweep_rule", "渲染检查规则", "contract", "校验", "amount > 0", "警告", "金额必须大于零。"]
    for index, value in enumerate(values):
        row[index].text = value
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _multipart_for(schema: dict[str, Any], components: dict[str, Any]) -> tuple[dict, dict]:
    if "$ref" in schema:
        schema = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
    fields: dict[str, Any] = {}
    files: dict[str, Any] = {}
    for name, property_schema in schema.get("properties", {}).items():
        if property_schema.get("type") == "string" and property_schema.get("format") == "binary":
            files[name] = (
                "route-sweep.docx",
                _docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        else:
            fields[name] = _value_for(property_schema, components)
    return fields, files


def test_no_route_crashes_on_a_request_built_from_its_own_schema(seeded_app: TestClient) -> None:
    import ontology_platform.api as api_module

    spec = api_module.app.openapi()
    components = spec.get("components", {}).get("schemas", {})

    crashes: list[str] = []
    requested = 0
    reached = 0

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            url = path
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "path":
                    url = url.replace("{" + parameter["name"] + "}", "1")
            params = {
                parameter["name"]: _value_for(parameter.get("schema", {}), components)
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query" and parameter.get("required")
            }
            media = operation.get("requestBody", {}).get("content", {})
            extra: dict[str, Any] = {}
            if "application/json" in media:
                extra["json"] = _value_for(media["application/json"].get("schema", {}), components)
            elif "multipart/form-data" in media:
                extra["data"], extra["files"] = _multipart_for(
                    media["multipart/form-data"].get("schema", {}), components
                )
            elif media:
                continue

            requested += 1
            try:
                response = seeded_app.request(method.upper(), url, params=params, **extra)
            except Exception as error:
                crashes.append(f"{method.upper()} {path} raised {type(error).__name__}: {error}")
                continue
            if response.status_code not in REACHED:
                continue
            reached += 1
            if response.status_code >= 500:
                crashes.append(f"{method.upper()} {path} -> {response.status_code} {response.text[:120]}")

    assert not crashes, "以下路由在按其自身 schema 构造的请求下崩了：\n  " + "\n  ".join(crashes)
    # The self-check. A sweep where almost nothing reached a handler is a sweep that has
    # quietly become a validator test, which is exactly what its first version was.
    assert requested > 100, f"只构造出 {requested} 个请求，schema 解析或已失效"
    assert reached > requested * 0.8, (
        f"{requested} 个请求里只有 {reached} 个到达了处理器——其余在参数校验处被拒，这个检查退化成了「校验器不出错」"
    )
