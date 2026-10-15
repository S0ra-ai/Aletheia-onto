#!/usr/bin/env python3
"""Report UI columns that render empty for every row.

Why this exists, and why it is not in the test suite
---------------------------------------------------

Three columns of the governance audit table and four of the model-invocation table asked
for field names the API does not send (`targetType` against a `dict(row)` payload of
`target_type`). They rendered **blank**, and nothing reported it: antd draws nothing for a
`dataIndex` that is absent, the linter sees a valid string, mypy sees a valid `string`, and
the component tests render the table without asserting that any particular cell has text.
The only thing that shows it is a browser.

So this script needs a browser and a running instance, which is exactly what the test suite
avoids — a suite that depends on either fails for reasons unrelated to the change. It is a
diagnostic to run by hand after touching a table, not a gate.

Usage
-----

    # 1. start the platform with the built frontend
    aletheia serve

    # 2. log in and point it at that instance
    python scripts/ui_smoke.py --base-url http://127.0.0.1:8000 \\
        --token "$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \\
                   -d '{"username":"admin","password":"..."}' | python -c 'import json,sys;print(json.load(sys.stdin)["token"])')"

Without a token only the public pages are checked. A session is seeded the way the SPA keeps
it (sessionStorage), so this drives the same authenticated application a person sees.

What it checks: every table cell that is empty in **every** data row, reported with the
column title. A column that is legitimately sparse is not a finding; a column that is empty
in every row is almost always a name mismatch, and the two are worth telling apart by eye.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Routes worth checking: every page that renders a table.
ROUTES = (
    "/admin/workbench",
    "/admin/ontology",
    "/admin/mapping",
    "/admin/rules",
    "/admin/semantic",
    "/admin/governance",
    "/admin/knowledge",
    "/admin/feedback",
    "/admin/permission",
    "/admin/workflow",
    "/admin/backup",
    "/admin/graph",
    "/admin/chat",
)

CHROME_CANDIDATES = (
    "chromium-cli",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("chromium") or "",
    shutil.which("google-chrome") or "",
    shutil.which("chromium-browser") or "",
)


def find_browser() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def seed_page(base_url: str, token: str, user: dict | None, directory: Path) -> str:
    """A same-origin page that installs the session and forwards to a route.

    Served from the built assets rather than from `/admin/`: any path under `/admin/` is
    answered by the SPA fallback, so a file placed there is never served and the app
    reports an unknown route instead -- which reads exactly like an application defect.
    """
    page = directory / "seed.html"
    session = "".join(
        f"sessionStorage.setItem({json.dumps(key)}, {json.dumps(value)});\n"
        for key, value in (
            ("ontology.session.token", token),
            ("ontology.session.user", json.dumps(user) if user else ""),
        )
        if value
    )
    page.write_text(
        '<!doctype html><meta charset="utf-8"><script>\n'
        f"{session}"
        "location.replace(new URLSearchParams(location.search).get('to') || '/admin/');\n"
        "</script>seeding",
        encoding="utf-8",
    )
    return f"{base_url}/assets/seed.html"


def dump_dom(browser: str, url: str) -> str:
    return subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=15000", "--dump-dom", url],
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout


def tables(html: str) -> list[tuple[list[str], list[list[str]]]]:
    found = []
    for block in re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL):
        headers = [
            re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<th[^>]*>(.*?)</th>", block, re.DOTALL)
        ]
        rows = []
        for row in re.findall(r'<tr[^>]*class="[^"]*ant-table-row[^"]*"[^>]*>(.*?)</tr>', block, re.DOTALL):
            rows.append(
                [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
            )
        if headers:
            found.append((headers, rows))
    return found


def empty_columns(headers: list[str], rows: list[list[str]]) -> list[str]:
    width = max(len(row) for row in rows)
    empty = []
    for index in range(min(width, len(headers))):
        if all(not (row[index].strip() if index < len(row) else "") for row in rows):
            empty.append(headers[index] or f"column {index}")
    return empty


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="", help="a bearer token; without one, only public pages are reachable")
    parser.add_argument("--user", default="", help="the JSON user object, as /auth/login returns it")
    parser.add_argument("--routes", default="", help="comma-separated override of the routes to visit")
    args = parser.parse_args()

    browser = find_browser()
    if browser is None:
        print("no headless browser found (looked for chromium-cli, Chrome, Chromium)", file=sys.stderr)
        return 2

    user = json.loads(args.user) if args.user else None
    routes = tuple(r.strip() for r in args.routes.split(",") if r.strip()) or ROUTES

    # Written into the real build output, because that is what the running instance already
    # serves. A temp directory would be tidier and would not work: the server resolves
    # `frontend_dist()` at request time and cannot be pointed at a path it was not started
    # with. The file is removed on the way out, including on failure.
    assets = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "assets"
    if not assets.is_dir():
        print(f"the frontend is not built: {assets} does not exist (run `npm run build`)", file=sys.stderr)
        return 2

    entry = seed_page(args.base_url, args.token, user, assets)
    findings = 0
    try:
        print(f"seeding from {entry}")
        for route in routes:
            html = dump_dom(browser, f"{entry}?to={route}")
            for index, (headers, rows) in enumerate(tables(html)):
                if not rows:
                    continue
                empty = empty_columns(headers, rows)
                if empty:
                    findings += 1
                    print(f"{route}  table #{index}  {len(rows)} rows  EMPTY: {', '.join(empty)}")
    finally:
        (assets / "seed.html").unlink(missing_ok=True)

    if findings:
        print(f"\n{findings} table(s) with a column that is empty in every row.")
        print("A sparse column is normal; a column empty in *every* row usually means the")
        print("`dataIndex` does not match the field name the endpoint returns.")
        return 1
    print("\nno wholly-empty columns found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
