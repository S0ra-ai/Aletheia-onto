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
import urllib.request
from pathlib import Path
from urllib.parse import quote

# Routes worth checking: every page that renders a table.
#
# Tab-qualified where a page keeps its tables behind one. `--dump-dom` loads a route and
# reads the DOM; it cannot click, so before pages put the active tab in the URL
# (`hooks/useTabParam.ts`) everything below the first tab was outside this check's reach.
# The audit report and the release gate live there, and the bugs that prompted this script
# -- columns rendering empty for every row -- are exactly the kind that hide behind a tab.
ROUTES = (
    "/admin/workbench",
    "/admin/datasource",
    "/admin/ontology",
    "/admin/mapping",
    "/admin/rules",
    "/admin/semantic",
    "/admin/semantic?tab=assess",
    "/admin/semantic?tab=preflight",
    "/admin/governance",
    "/admin/governance?tab=decisions",
    "/admin/governance?tab=audit",
    "/admin/governance?tab=invocations",
    "/admin/governance?tab=report",
    "/admin/knowledge",
    "/admin/feedback",
    "/admin/permission",
    "/admin/permission?tab=policies",
    "/admin/permission?tab=tools",
    "/admin/permission?tab=sso",
    "/admin/permission?tab=reviews",
    "/admin/workflow",
    # `/admin/backup` was in this list and is not a route the application serves: the backup
    # screen is `/admin/data-backup`, and `/admin/backup` is the *API* namespace, so a browser
    # navigation to it is answered by the auth middleware with `{"detail":"缺少访问令牌"}`.
    # The line it printed -- `0 table(s), 0 row(s)` -- read like a page with nothing to show,
    # and the backup table, four columns of it, was never examined at all.
    "/admin/data-backup",
    "/admin/demo",
    "/admin/model",
    "/admin/graph",
    "/admin/chat",
    "/admin/objects",
    "/admin/tenancy",
)

# Routes whose path needs an id. Filled in from the instance when a token is given, because
# a fixed list cannot know one and skipping them leaves the detail pages -- where the
# release gate, the attribute table, the coverage panel and the review queue live -- outside
# the sweep entirely.
ID_ROUTES = (
    "/admin/ontology/{ontology}?tab=objects",
    "/admin/ontology/{ontology}?tab=attributes",
    "/admin/ontology/{ontology}?tab=relations",
    "/admin/ontology/{ontology}?tab=mappings",
    "/admin/ontology/{ontology}?tab=rules",
    "/admin/ontology/{ontology}?tab=release",
    "/admin/ontology/{ontology}?tab=extensions",
    "/admin/datasource/{source}?tab=tables",
    "/admin/datasource/{source}?tab=apis",
    "/admin/datasource/{source}?tab=coverage",
    # The two semantic tabs whose tables appear only after a request. The page reads the
    # query from the URL, so the request is made by arriving -- which is also what makes an
    # explanation something you can paste into a ticket.
    "/admin/semantic?tab=explain&object={object}&instance={instance}&ontology={ontology}",
    "/admin/semantic?tab=consistency&object={object}&ontology={ontology}&instance={instance}",
    # Same reason, one screen further: the knowledge base names the ontology it is showing,
    # so a link opens the documents of the system it was sent about.
    "/admin/knowledge?ontology={ontology}",
)

# Where the seed page is written: the build the running instance serves, unless it was
# started with `ALETHEIA_FRONTEND_DIST` pointing somewhere else -- which the guard below
# detects, because the symptom is otherwise "every page renders nothing".
SEED_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "assets"

CHROME_CANDIDATES = (
    "chromium-cli",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # The absolute paths the GitHub runner image installs, so the CI job does not depend on
    # Chrome happening to be on PATH there.
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
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


# Columns that are empty because the *data* has nothing in them, not because the field name
# is wrong. Listed rather than inferred: the script cannot tell the two apart, and a checker
# that guesses would either miss real defects or fail on real data. Printed on every run, so
# an allowance cannot quietly outlive the reason for it.
KNOWN_SPARSE = (
    # The seeded instance writes a description on the one policy it creates, so that column
    # is populated now -- this entry was removed the first time the CI assertion below ran,
    # which is what the assertion is for: an allowance outlives its reason and then suppresses
    # the finding it was never meant to cover.
    ("/admin/ontology/{id}?tab=attributes", "描述"),
)

# Routes that render no table in the seeded instance, and why. Every other route must render
# at least one, because a route that renders none is a route this check examined *nothing* on
# -- and until this list existed that was indistinguishable from a clean result. It is how
# `/admin/backup` spent its whole life printing `0 table(s), 0 row(s)`: a path the app does
# not serve, standing in for the backup screen that was never visited.
#
# Each entry is a claim, so each is a reason rather than a waiver: a table that needs an
# action this tool cannot take, or a page that has no table by design. A route whose table
# stops rendering without landing here fails, and a route listed here that starts rendering
# one also fails -- the list is checked in both directions.
NO_TABLE_ROUTES = {
    # Two of the five semantic tabs do have tables. Those two are swept through a URL that
    # names the object and the instance (see `ID_ROUTES`), because the page only answers after
    # a submit; the other three render prose or a description list and have no table at all.
    # Stated per tab rather than as one sentence covering all five, because a reason that is
    # approximately right is the kind of entry that stops being read.
    "/admin/semantic": "自然语言交互：答案是正文，没有表格",
    "/admin/semantic?tab=assess": "风险研判：结论以描述列表呈现，没有表格",
    "/admin/semantic?tab=preflight": "操作预检：结果以描述列表呈现，没有表格",
    "/admin/permission?tab=sso": "SSO 是配置表单，没有表格",
    "/admin/graph": "本体图是画布，没有表格",
    "/admin/chat": "对话界面没有表格",
    "/admin/demo": "演示中心是引导与步骤表单，没有表格",
    "/admin/model": "模型配置是表单，没有表格",
}


def _normalise_route(route: str) -> str:
    """Ids to `{id}`, so an allowance survives whichever ontology the instance happens to
    have. A route with a hardcoded id in it would stop matching the day the first ontology
    is not number one -- and then the job fails for a reason that is not a defect."""
    return re.sub(r"/\d+(?=/|\?|$)", "/{id}", route)


def _id_routes(base_url: str, token: str) -> tuple[list[str], list[str]]:
    """The detail routes, filled with what the instance actually has; plus the ones it could not fill.

    Read from the instance rather than written down: a literal `contract` or `1` works on the
    demo and stops working the moment anything else is seeded first, and the job then fails
    for a reason that is not a defect. The second half of the return value is the point: a
    route that cannot be filled is *reported* rather than dropped, because a silently skipped
    route is a coverage loss that reads exactly like a route that was swept and was clean.
    """
    import urllib.request

    def first(endpoint: str, key: str, field: str = "id") -> str:
        request = urllib.request.Request(f"{base_url}{endpoint}", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return ""
        for candidate in (payload.get(key), payload.get("items"), payload.get("dataSources")):
            if isinstance(candidate, list) and candidate:
                return str(candidate[0].get(field, ""))
        return ""

    ontology = first("/ontologies", "ontologies")
    source = first("/data-sources", "dataSources")
    # The object and the instance come from the ontology the sweep is already pointed at, so
    # the semantic routes answer for a real row: the explanation of an instance that does not
    # exist renders the same table with nothing in it, which is the state this check cannot
    # tell from a defect.
    object_code = first(f"/ontologies/{ontology}", "objects", field="code") if ontology else ""
    instance = (
        first(
            f"/semantic/objects/{object_code}/instances?ontologyId={ontology}",
            "items",
            field="instanceId",
        )
        if object_code
        else ""
    )
    filled = []
    unfilled = []
    for template in ID_ROUTES:
        values = {"ontology": ontology, "source": source, "object": object_code, "instance": instance}
        missing = [name for name in values if "{" + name + "}" in template and not values[name]]
        if missing:
            unfilled.append(f"{template}（缺少 {'、'.join(missing)}）")
            continue
        filled.append(template.format(**values))
    return filled, unfilled


def dump_dom(browser: str, url: str) -> str:
    return subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=15000", "--dump-dom", url],
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout


# An icon carries meaning without carrying text: a tick and a cross are the whole content of
# a permission cell. Stripping tags and reading what is left reports every icon-only column as
# "empty in every row", and a diagnostic that reports a standing false positive is teaching
# its reader to skim past the real ones.
_ICON = re.compile(r'<span[^>]*class="[^"]*anticon[^"]*"')


def _cell_text(cell: str) -> str:
    if _ICON.search(cell):
        return "\u2713"
    return re.sub(r"<[^>]+>", "", cell).strip()


def tables(html: str) -> list[tuple[list[str], list[list[str]]]]:
    found = []
    for block in re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL):
        headers = [
            re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<th[^>]*>(.*?)</th>", block, re.DOTALL)
        ]
        rows = []
        for row in re.findall(r'<tr[^>]*class="[^"]*ant-table-row[^"]*"[^>]*>(.*?)</tr>', block, re.DOTALL):
            rows.append([_cell_text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)])

        # antd's expandable rows prepend a column holding nothing but the expand icon. Its
        # header is empty and so is every cell, so it is reported as a finding on every
        # expandable table -- a permanent false positive, which is how a diagnostic teaches
        # its reader to skim past its output. Detected by the icon rather than by "first
        # header is blank": a genuinely blank first header is worth reporting.
        if "ant-table-row-expand-icon" in block:
            headers = headers[1:]
            rows = [row[1:] for row in rows]

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


# What the application renders when a screen did not load. Asserted for *every* route, because
# a crashed page and a page with no table by design produce the same line in this report:
# `/admin/graph` has no table on purpose, and a `/admin/graph` that throws in render has no
# table either. Without this, the second case is an entry in `NO_TABLE_ROUTES` that quietly
# becomes true.
FAILURE_MARKERS = ("页面加载失败", "页面不存在")


def seeded_url(entry: str, route: str) -> str:
    """The seed page's URL for one route, with the route encoded.

    `to` is a single query parameter, so a route carrying more than one of its own --
    `?tab=explain&object=contract&instance=1` -- arrives at the page cut in half at the first
    `&`, and the browser then loads a different screen than the one asked for. That failure
    looks exactly like the page having nothing to show, which is this script's recurring
    shape of mistake.
    """
    return f"{entry}?to={quote(route, safe='')}"


def failure_marker(html: str) -> str:
    """The failure text a dumped page contains, if any.

    Read from the rendered text rather than from a marker element: the error boundary renders
    either a full-page `Result` or an inline `Alert` depending on where it caught the error,
    and the two have no common attribute.
    """
    text = re.sub(r"<[^>]+>", " ", html)
    for marker in FAILURE_MARKERS:
        if marker in text:
            return marker
    return ""


def seed_is_the_build_just_written(entry: str) -> str:
    """Empty when the instance serves the file we just wrote, a reason otherwise.

    A server started with `ALETHEIA_FRONTEND_DIST` elsewhere serves its own copy, so every
    page fails to seed and the report reads "0 tables, 0 rows" sixteen times -- which looks
    like an application where nothing renders, and is really this script looking in the wrong
    drawer.
    """
    try:
        with urllib.request.urlopen(entry, timeout=10) as response:
            served = response.read().decode("utf-8", "replace")
    except Exception as error:
        return f"the seed page is not reachable at {entry}: {error}"
    if "seeding" not in served:
        return (
            f"{entry} is not the file just written; the instance is serving a different build.\n"
            f"This script writes into {SEED_DIRECTORY} and can only seed an instance started "
            "without ALETHEIA_FRONTEND_DIST pointing elsewhere."
        )
    return ""


def token_authenticates(base_url: str, token: str) -> str:
    """Empty when the token works; a line to print when it does, and a reason when it does not.

    A token that does not authenticate renders the login page on every route. The sweep then
    reports "0 tables, 0 rows" for all of them and ends with "no wholly-empty columns found"
    -- a clean bill of health for a run that looked at nothing. Checked before sweeping rather
    than inferred from the empty result, which is indistinguishable from a deployment that
    genuinely has no data.
    """
    request = urllib.request.Request(f"{base_url}/auth/me", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            who = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        return f"the token does not authenticate ({error}); nothing would be rendered"
    return f"sweeping as {who.get('username', '?')} ({who.get('roleCode', '?')})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="", help="a bearer token; without one, only public pages are reachable")
    parser.add_argument("--user", default="", help="the JSON user object, as /auth/login returns it")
    parser.add_argument("--routes", default="", help="comma-separated override of the routes to visit")
    parser.add_argument(
        "--allow",
        default=",".join(f"{route}:{column}" for route, column in KNOWN_SPARSE),
        help="comma-separated route:column pairs known to be empty for want of data",
    )
    args = parser.parse_args()

    browser = find_browser()
    if browser is None:
        print("no headless browser found (looked for chromium-cli, Chrome, Chromium)", file=sys.stderr)
        return 2

    user = json.loads(args.user) if args.user else None
    routes = [r.strip() for r in args.routes.split(",") if r.strip()] or list(ROUTES)
    skipped: list[str] = []
    if not args.routes and args.token:
        filled, skipped = _id_routes(args.base_url, args.token)
        routes.extend(filled)
    routes = tuple(routes)

    # Written into the real build output, because that is what the running instance already
    # serves. A temp directory would be tidier and would not work: the server resolves
    # `frontend_dist()` at request time and cannot be pointed at a path it was not started
    # with. The file is removed on the way out, including on failure.
    assets = SEED_DIRECTORY
    if not assets.is_dir():
        print(f"the frontend is not built: {assets} does not exist (run `npm run build`)", file=sys.stderr)
        return 2

    entry = seed_page(args.base_url, args.token, user, assets)
    # Confirm the instance is serving the directory we just wrote into before walking
    # sixteen routes. A server started with `ALETHEIA_FRONTEND_DIST` elsewhere serves its own
    # copy, so every page fails to seed and the report reads "0 tables, 0 rows" for all of
    # them -- which looks like an application where nothing renders, and is really a script
    # looking in the wrong drawer.
    reason = seed_is_the_build_just_written(entry)
    if reason:
        print(reason, file=sys.stderr)
        (assets / "seed.html").unlink(missing_ok=True)
        return 2

    # A token that does not authenticate renders the login page on every route. The sweep
    # then reports "0 tables, 0 rows" 25 times and ends with "no wholly-empty columns found"
    # -- a clean bill of health for a run that looked at nothing.
    if args.token:
        status = token_authenticates(args.base_url, args.token)
        if status.startswith("the token"):
            print(status, file=sys.stderr)
            (assets / "seed.html").unlink(missing_ok=True)
            return 2
        print(status)

    allowed = {pair.strip() for pair in args.allow.split(",") if pair.strip()}
    findings = 0
    rows_seen = 0
    tableless: list[str] = []
    broken_pages: list[str] = []
    if allowed:
        print("已知因数据为空而整列为空的列（不是缺陷）:")
        for pair in sorted(allowed):
            print(f"  {pair}")
    try:
        print(f"seeding from {entry}")
        for route in routes:
            html = dump_dom(browser, seeded_url(entry, route))
            page_tables = tables(html)
            examined = sum(len(rows) for _, rows in page_tables)
            rows_seen += examined
            # A page that failed to render is a finding on its own, and the first thing to
            # report: whatever its table count says is then meaningless.
            broken = failure_marker(html)
            if broken:
                findings += 1
                broken_pages.append(route)
            # A per-route line, because a silent run and a run that found nothing look
            # identical otherwise -- and "no findings" is only meaningful if the pages were
            # actually reached. A route behind a tab that ignored the query would otherwise
            # report clean forever.
            empty_here = []
            for index, (headers, rows) in enumerate(page_tables):
                if not rows:
                    continue
                # Matched with ids normalised, so the allowance does not depend on which
                # ontology id the instance happens to use.
                allowed_here = {_normalise_route(pair.rsplit(":", 1)[0]) for pair in allowed if ":" in pair}
                allowed_columns = {pair.rsplit(":", 1)[1] for pair in allowed if ":" in pair}
                empty = [
                    column
                    for column in empty_columns(headers, rows)
                    if not (_normalise_route(route) in allowed_here and column in allowed_columns)
                ]
                if empty:
                    findings += 1
                    empty_here.append(f"table #{index}: {', '.join(empty)}")
            if not page_tables:
                tableless.append(route)
            detail = f"  EMPTY: {'; '.join(empty_here)}" if empty_here else ""
            if broken:
                detail = f"  PAGE FAILED: {broken}"
            if not page_tables:
                detail = f"  NO TABLE{': ' + NO_TABLE_ROUTES[route] if route in NO_TABLE_ROUTES else ''}"
            print(f"{route:44s} {len(page_tables):2d} table(s), {examined:4d} row(s){detail}")
    finally:
        (assets / "seed.html").unlink(missing_ok=True)

    # Nothing was examined on a route whose table should be there. Checked in both directions:
    # a route that lost its table, and a route that gained one while still being excused here
    # -- the second is how an allowance outlives its reason and starts hiding a defect.
    unexpected = sorted(route for route in tableless if route not in NO_TABLE_ROUTES)
    stale = sorted(route for route in NO_TABLE_ROUTES if route in routes and route not in tableless)
    if skipped:
        # A route that was dropped is not a route that passed. Reported with the same weight
        # as an unexamined screen, because from the outside the two are the same thing.
        print(
            "\n以下详情路由没有填出来，因此这一次没有扫到（缺少的是实例里的哪一项，见括号）：\n  "
            + "\n  ".join(skipped),
            file=sys.stderr,
        )
        return 1
    if unexpected:
        print(
            "\n以下路由一张表都没有渲染，说明这次扫描在它们身上什么都没检查到：\n  "
            + "\n  ".join(unexpected)
            + "\n（若确实没有表格，把它连同理由加进 NO_TABLE_ROUTES；若应该有，那这就是一个发现。）",
            file=sys.stderr,
        )
        return 1
    if stale:
        print(
            "\n以下路由在 NO_TABLE_ROUTES 里，却渲染出了表格——豁免过期了：\n  " + "\n  ".join(stale),
            file=sys.stderr,
        )
        return 1

    if rows_seen == 0:
        # The headline below would otherwise read "no wholly-empty columns found" for a sweep
        # that rendered no data at all -- the same shape of false pass as an unauthenticated
        # run, and the reason the token is checked above.
        print(
            "\n没有任何一行被渲染：这次扫描什么都没检查到。"
            "通常是实例里没有数据（先跑 `aletheia demo`，或用 scripts/seed_smoke_instance.py 填充）。",
            file=sys.stderr,
        )
        return 1
    if findings:
        if broken_pages:
            print(
                "\n以下路由渲染的是失败页（前端错误边界或「页面不存在」），它们上面的表格计数没有意义：\n  "
                + "\n  ".join(broken_pages),
                file=sys.stderr,
            )
        print(f"\n{findings} table(s) with a column that is empty in every row.")
        print("A sparse column is normal; a column empty in *every* row usually means the")
        print("`dataIndex` does not match the field name the endpoint returns.")
        return 1
    checked = len(routes) - len(tableless)
    print(
        f"\nno wholly-empty columns found"
        f"（{checked}/{len(routes)} 条路由渲染了表格；{len(tableless)} 条没有表格，理由见 NO_TABLE_ROUTES）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
