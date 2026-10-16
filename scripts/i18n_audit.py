#!/usr/bin/env python3
"""What does the English console still show in Chinese?

`scripts/ui_smoke.py` answers "does every screen render its data"; this answers the other
question a bilingual console raises and nothing else checks: **is the English interface
actually English?** The dictionary tests can only read the dictionary -- a screen that keeps
its own copy of a Chinese string compiles, type-checks, and passes every test in the suite.
One did: the sidebar rendered 「本体改造研发平台」 as a literal while `shell.app.name` sat in
the dictionary unused, on every screen, for the whole life of the migration.

## Why this needs a browser and a running instance

The question is about *rendered* text, and no amount of reading source finds it: the string
can come from a constant, from a label map, from the server, or from a table cell. So the
audit walks the same routes the render check does, with `?lang=en` pinned, and reads the DOM.

## Data is not copy, and the difference is the whole design

This instance's content is Chinese -- ontology names, business objects, knowledge clauses, a
reader's display name. Those belong in Chinese on an English screen; translating somebody's
data would be a bug of its own. So the audit asks the API what the instance holds, and treats
a fragment as data when it appears inside something the instance sent back. What is left is
the interface's own words, and those have a translation.

## What it is not

Not a transliteration check and not a proofreader. It reads CJK, so it catches "this sentence
was never translated" and cannot catch "this sentence was translated badly". The other half of
that pair -- no two keys drifting apart, no plural missing -- lives in `tests/test_ui_messages.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read endpoints whose payloads are the *deployment's own* content: the names, codes and text
# somebody typed into this instance. That is what belongs in Chinese on an English screen.
#
# What is deliberately **not** here matters more than what is. Advice, captions and verdict
# explanations -- `nextActions`, `readiness`, `release-readiness`, `semantic-coverage`,
# `reasoning-chain`, `audit-report`, `graph.limitation` -- are the platform's own words, and
# the platform is bilingual only on the console side. Leaving those endpoints in this list
# made the audit subtract its own findings: `/admin/ontology/{id}?tab=release` reported 37
# Chinese fragments before `release-readiness` was added here and 0 afterwards, with nothing
# translated in between. **A data list that includes the thing you are looking for is a check
# that reports a clean screen because it stopped looking.**
#
# The cost is the other direction: a name that the platform generates (a rule the draft
# builder wrote) shows up as a finding until it is either excused or given a code. That is the
# safe way round -- a false positive is visible in the report, a false negative is not.
DATA_ENDPOINTS = (
    "/auth/me",
    "/ontologies",
    "/data-sources",
    "/tenants",
    "/platform/users",
    "/industry-blueprints",
    "/permissions/roles",
    "/permissions/policies",
    "/tools",
    "/agent/roles",
    "/knowledge-bases",
    "/workflows",
    "/feedback",
    "/conversations",
)

# The same for the detail endpoints, which need an id from the instance. Filled from the first
# ontology and the first source, the way the render sweep fills its detail routes.
DETAIL_DATA_ENDPOINTS = (
    "/ontologies/{ontology}",
    "/ontologies/{ontology}/mappings",
    "/ontologies/{ontology}/rules",
    "/ontologies/{ontology}/event-types",
    "/ontologies/{ontology}/knowledge/documents",
    "/ontologies/{ontology}/knowledge/entries",
    "/data-sources/{source}/tables",
    "/data-sources/{source}/readiness",
    "/data-sources/{source}/reasoning-chain",
    "/data-sources/{source}/semantic-coverage",
    "/data-sources/{source}/operation-bindings",
    "/semantic/objects/{object}/instances?ontologyId={ontology}",
)

# Keys whose payload is the platform's own advice rather than the deployment's content. They sit
# inside payloads that are otherwise data -- `readiness` holds a score and a status *and* a list
# of `nextActions` -- so the endpoint is not the unit that can be classified, the key is.
#
# Without this the audit reported a clean `/admin/datasource/1?tab=coverage` while the screen
# was showing 「优先审核待确认语义映射…」: the sentence had been subtracted as data because it
# arrived from an endpoint on the list. Advice is exactly what has to be translated, so
# subtracting it makes the check blind to its own subject.
ADVICE_KEYS = frozenset({"nextActions", "limitation", "remediation", "evidence", "categoryLabel"})

# The instance timeline, which needs an instance key as well. Its payloads are the instance's
# data too -- an event's `reason` is a string a workflow wrote, and the timeline renders the
# payload as JSON, so a payload value with no translation looks exactly like untranslated copy.
# Kept as a named path but **not** harvested: everything it returns that is a *sentence* is the
# platform's wording, and the payloads that are the instance's own content arrive in the drawer
# from the explain endpoint, which is harvested.
# The instance timeline, harvested for the same reason as everything else on the list: an event's
# payload is content somebody's workflow wrote (`{"reason": "进入工作流"}`), and it renders as
# JSON, so a payload value with no translation looks exactly like untranslated copy. The labels
# the endpoint *resolves* -- `categoryLabel` -- are the platform's words and are skipped by key
# below, which is the same rule the rest of this list follows.
TIMELINE = "/ontologies/{ontology}/objects/{object}/instances/{instance}/events?limit=200"

# Chinese the *server* composes and the console prints as-is. Empty, and that is the point:
# every sentence the audit found has been given a code the console can translate, so the list
# has no reason to hold anything. It stays because the mechanism is what keeps a *new* server
# sentence from passing unnoticed -- an entry that matches nothing fails the run, so the list
# cannot quietly become a place where findings are hidden.
KNOWN_BACKEND_PROSE: tuple[tuple[str, str, str], ...] = ()


CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _load_smoke():
    """Import `scripts/ui_smoke.py` by path: it is a script, not a package module.

    Imported rather than copied because the two tools must agree about what a route is, what
    the seed page does, and how a browser is found -- and because the sweep learned those the
    hard way, once per mistake.
    """
    spec = importlib.util.spec_from_file_location("ui_smoke_for_audit", ROOT / "scripts" / "ui_smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _get(base_url: str, token: str, path: str) -> object:
    request = urllib.request.Request(f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _first(base_url: str, token: str, path: str, key: str, field: str = "id") -> str:
    """The first id in a list endpoint's payload, or "" when there is none."""
    payload = _get(base_url, token, path)
    if not isinstance(payload, dict):
        return ""
    for candidate in (payload.get(key), payload.get("items"), payload.get("dataSources")):
        if isinstance(candidate, list) and candidate:
            return str(candidate[0].get(field, ""))
    return ""


def instance_strings(base_url: str, token: str) -> list[str]:
    """Every string the instance holds, from the endpoints that feed the screens."""
    collected: list[str] = []

    def walk(payload: object, key: str = "") -> None:
        if key in ADVICE_KEYS:
            return
        if isinstance(payload, str):
            if payload.strip():
                collected.append(payload.strip())
        elif isinstance(payload, dict):
            for name, value in payload.items():
                walk(value, str(name))
        elif isinstance(payload, list):
            for value in payload:
                walk(value, key)

    for path in DATA_ENDPOINTS:
        walk(_get(base_url, token, path))

    ontology = _first(base_url, token, "/ontologies", "ontologies")
    source = _first(base_url, token, "/data-sources", "dataSources")
    object_code = _first(base_url, token, f"/ontologies/{ontology}", "objects", field="code") if ontology else ""
    # The timeline is read for the first few instance keys rather than discovered: the instance
    # list endpoint filters rows by a row-level policy and can come back empty on an instance
    # whose drawer still renders. A key that does not exist answers 404, which `_get` turns into
    # nothing -- so the cost of trying is one failed request.
    timelines = [
        TIMELINE.format(ontology=ontology, object=object_code, instance=key)
        for key in ("1", "2", "3")
        if ontology and object_code
    ]
    for path in (*DETAIL_DATA_ENDPOINTS, *timelines):
        path = path.format(ontology=ontology, source=source, object=object_code)
        if "//" in path or path.endswith("/") or "/None" in path:
            continue
        walk(_get(base_url, token, path))
    return collected


def rendered_text(html: str) -> list[str]:
    """The visible lines of a dumped page, scripts and styles removed."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    return [line.strip() for line in text.split("\n") if line.strip()]


def _normalize(text: str) -> str:
    """Collapse whitespace and drop the characters the browser inserts.

    The DOM has ` ` and line breaks where the payload had a space, and an audit that
    compares raw text reports the instance's own sentence as untranslated copy because a
    non-breaking space differs from a space.
    """
    return re.sub(r"\s+", " ", text.replace(" ", " ").replace("​", "")).strip()


def chinese_fragments(html: str, data: list[str]) -> list[tuple[str, str]]:
    """The lines that are Chinese and are not the instance's own content, with the remainder.

    Data is removed from the line before the line is judged, rather than the line being
    matched against the data wholesale. Screens put their own words around the content --
    `合同管理本体 v0.1.0` is a name the instance holds in the middle of a version suffix this
    console wrote, and `合同 · 1` is a name and an instance key. Judging those by "is this line
    one of the instance's strings" reports every composed title as untranslated copy.

    So: strip every known data string out, and only what the *console* contributed is left to
    judge. A greeting that wraps server prose around a name still has CJK after the strip --
    which is the answer, because the prose is what needs translating.

    **Longest first**, and that is not an optimisation: this deployment's ontology domain is
    「合同管理」 and its source is named 「合同管理样例系统」. Replacing in collection order strips
    the short one out of the long one and leaves 「样例系统」 behind -- a fragment of the
    instance's own name reported as untranslated copy, which is exactly the false positive
    that would teach a reader to stop reading this report.

    The remainder is returned with the line because that is what the report has to show. A
    line on its own leaves the reader asking why the instance's own name was reported; the
    remainder is the part that has no translation, and printing it makes a false positive
    self-evident -- which matters more here than in most checks, because this one is noisy
    about content that is Chinese on purpose.
    """
    known = sorted((_normalize(value) for value in data if CJK.search(value)), key=len, reverse=True)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in rendered_text(html):
        if not CJK.search(line) or line in seen:
            continue
        normalized = _normalize(line)
        # Contained *in* a data string: the payload holds a paragraph and the DOM split it into
        # lines, so one clause of a two-clause entry is a line that no data string equals. The
        # other direction cannot see this -- replacing a longer string inside a shorter one
        # replaces nothing, and the line comes back reported as untranslated copy.
        if any(normalized in value for value in known):
            continue
        remainder = normalized
        for value in known:
            if value:
                remainder = remainder.replace(value, "")
        if not CJK.search(remainder):
            continue
        seen.add(line)
        found.append((line, remainder.strip()))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="", help="a bearer token; the audit is meaningless without one")
    parser.add_argument("--user", default="", help="the JSON user object, as /auth/login returns it")
    parser.add_argument("--routes", default="", help="comma-separated override of the routes to visit")
    args = parser.parse_args()

    browser = _load_smoke()
    executable = browser.find_browser()
    if executable is None:
        print("no headless browser found (looked for chromium-cli, Chrome, Chromium)", file=sys.stderr)
        return 2
    if not args.token:
        # Without a token every route renders the login page -- which is translated, so the
        # audit would report a clean English interface for a run that never got past the door.
        print("--token is required: an unauthenticated run only ever reads the login page", file=sys.stderr)
        return 2

    assets = browser.SEED_DIRECTORY
    if not assets.is_dir():
        print(f"the frontend is not built: {assets} does not exist (run `npm run build`)", file=sys.stderr)
        return 2

    user = json.loads(args.user) if args.user else None
    routes = [r.strip() for r in args.routes.split(",") if r.strip()] or list(browser.ROUTES)
    if not args.routes:
        filled, _ = browser._id_routes(args.base_url, args.token)
        routes.extend(filled)

    status = browser.token_authenticates(args.base_url, args.token)
    if status.startswith("the token"):
        print(status, file=sys.stderr)
        return 2
    print(status)

    data = instance_strings(args.base_url, args.token)
    print(f"实例里读到 {len(data)} 条数据字符串，出现这些字符串的页面文本按数据对待\n")

    entry = browser.seed_page(args.base_url, args.token, user, assets)
    reason = browser.seed_is_the_build_just_written(entry)
    if reason:
        print(reason, file=sys.stderr)
        (assets / "seed.html").unlink(missing_ok=True)
        return 2

    findings: dict[str, list[tuple[str, str]]] = {}
    excused: dict[str, list[str]] = {}
    matched: set[int] = set()
    try:
        for route in routes:
            separator = "&" if "?" in route else "?"
            url = browser.seeded_url(entry, f"{route}{separator}lang=en")
            found = chinese_fragments(browser.dump_dom(executable, url), data)
            print(f"{route:52s} {len(found):3d} 段中文")
            # Matched on the route *and its tabs*: an entry without a `?` covers every tab of
            # that page, an entry with one covers only that tab. The audit report's sentences
            # live on one tab of a page whose other tabs are clean, so its entry names the tab;
            # the reasoning chain's sentence appears on two different tabs, so its entry names
            # the page. Both are stated where the sentence is, which is the only place that
            # knows how wide the excuse has to be.
            for line, remainder in found:
                for index, (excused_route, pattern, _reason) in enumerate(KNOWN_BACKEND_PROSE):
                    if route.startswith(excused_route) and re.search(pattern, line):
                        matched.add(index)
                        excused.setdefault(route, []).append(line)
                        break
                else:
                    findings.setdefault(route, []).append((line, remainder))
    finally:
        (assets / "seed.html").unlink(missing_ok=True)

    if excused:
        print("\n已知由服务端提供的措辞（每条都写了理由，改前端改不掉）：")
        for route, lines in excused.items():
            for line in lines[:12]:
                reason = next(reason for path, pattern, reason in KNOWN_BACKEND_PROSE if re.search(pattern, line))
                print(f"  {route:46s} {line[:38]:40s} {reason}")

    # An allowance that matched nothing this run is an allowance that has outlived its reason
    # -- the sentence was translated, or the route changed. Reported rather than kept, because
    # the next thing it suppresses is a defect.
    stale = [
        (path, pattern, reason)
        for index, (path, pattern, reason) in enumerate(KNOWN_BACKEND_PROSE)
        if index not in matched
    ]
    if stale:
        print("\n以下豁免这一次一条都没匹配上——句子可能已经翻译了，或者路由变了：", file=sys.stderr)
        for path, pattern, reason in stale:
            print(f"  {path}  /{pattern}/  （理由：{reason}）", file=sys.stderr)
        return 1

    if not findings:
        print(f"\n英文界面上没有未翻译的界面文案；{sum(len(v) for v in excused.values())} 处是已知的服务端措辞。")
        return 0

    print("\n这些页面上出现了没有翻译的界面文案（`←` 后面是剥掉实例数据之后剩下的那部分）：", file=sys.stderr)
    for route, fragments in findings.items():
        print(f"\n  {route}", file=sys.stderr)
        for line, remainder in fragments[:12]:
            print(f"    {line[:80]}  ← {remainder[:60]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
