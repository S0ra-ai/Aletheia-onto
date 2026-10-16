#!/usr/bin/env python3
"""Re-capture the screenshots the documentation shows.

The images in `docs/images/` are of a running instance, and every change to the console makes
them stale -- a screenshot that shows a layout the product no longer has is a claim the reader
can check and find false. They were captured by hand, which is why refreshing them was a chore
nobody did: fifteen screens, each needing a login, the right tab and a settled page.

This does it in one command. It pairs each route with the file the docs reference, so the two
cannot drift the way a hand-captured set does -- and `--lang` captures the console in either
language, because the interface is bilingual and the English docs are read by people who would
otherwise be looking at Chinese screens.

Usage
-----

    cd frontend && npm run build && cd ..
    python scripts/seed_smoke_instance.py --platform-db /tmp/platform.sqlite3   # or `aletheia demo`
    aletheia serve &                                   # in another shell
    python scripts/capture_screenshots.py --base-url http://127.0.0.1:8000 \\
        --token "$TOKEN" --user "$USER"

Every route is read from the URL (`?tab=`, `?object=`, `?instance=`), which is what makes a
screenshot reproducible: a state reachable only by clicking is a state this cannot return to.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `(file, route)`: the route that shows the screen the docs caption, and the file the docs
# reference. The order is by filename, which is how they are listed in `docs/images/`.
SCREENS: tuple[tuple[str, str], ...] = (
    # The chat answer, because that is the screen the section describes: the agent's answer with
    # the governing rules named one per bullet, the rule codes, and the evidence tables. The
    # semantic Q&A tab answers the same question in the same shape, but the agent's role -- which
    # is derived at runtime from the onboarded domain -- is only shown here.
    ("01-semantic-qa-with-evidence.png", "/admin/chat?q={question}"),
    ("02-data-source-onboarding.png", "/admin/datasource/{source}?tab=tables"),
    ("03-ontology-objects.png", "/admin/ontology/{ontology}?tab=objects"),
    ("04-governance-release-gate.png", "/admin/ontology/{ontology}?tab=release"),
    ("05-roles-and-permissions.png", "/admin/permission?tab=policies"),
    ("06-workbench.png", "/admin/workbench"),
    ("07-knowledge-graph.png", "/admin/graph"),
    ("08-model-config.png", "/admin/model"),
    ("09-knowledge-base.png", "/admin/knowledge?ontology={ontology}"),
    ("10-feedback-loop.png", "/admin/feedback"),
    ("11-object-browser.png", "/admin/objects?ontology={ontology}&object={object}&instance={instance}"),
    ("12-tenants-and-quotas.png", "/admin/tenancy"),
    ("13-audit-report.png", "/admin/governance?tab=report"),
    (
        "14-instance-explanation.png",
        "/admin/semantic?tab=explain&object={object}&instance={instance}&ontology={ontology}",
    ),
    ("15-modelling-extensions.png", "/admin/ontology/{ontology}?tab=extensions"),
)


def _load_sweep():
    """`scripts/ui_smoke.py`, for the seed page and the browser discovery.

    The session has to be installed the way the SPA keeps it (`sessionStorage`) before the page
    loads, or every screenshot is the login page -- and the two scripts must agree about how a
    route with its own query string survives the seed page.
    """
    spec = importlib.util.spec_from_file_location("ui_smoke_for_capture", ROOT / "scripts" / "ui_smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _first(base_url: str, token: str, path: str, key: str, field: str = "id") -> str:
    """The first id (or code) in a list endpoint's payload, or "" when there is none."""
    request = urllib.request.Request(f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    for candidate in (payload.get(key), payload.get("items"), payload.get("dataSources")):
        if isinstance(candidate, list) and candidate:
            return str(candidate[0].get(field, ""))
    return ""


def instance_values(base_url: str, token: str) -> dict[str, str]:
    """What the screenshots need to point at, read from the instance rather than guessed.

    A literal `contract` or `1` works on the demo and stops working the moment anything else is
    seeded first -- and the failure is a screenshot of an empty page, which reads as a product
    defect. The instance is asked instead, and a missing value is reported before anything is
    captured.
    """
    ontology = _first(base_url, token, "/ontologies", "ontologies")
    object_code = _first(base_url, token, f"/ontologies/{ontology}", "objects", field="code") if ontology else ""
    return {
        "ontology": ontology,
        "source": _first(base_url, token, "/data-sources", "dataSources"),
        "object": object_code,
        "instance": "1",
        # The question the chat screenshot asks. In the instance's own language, because it is
        # *data*: it goes through retrieval and ends up in the answer.
        "question": "合同 1 是否合规？",
    }


def capture(browser: str, url: str, target: Path, *, width: int, height: int, scale: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            # Without this the scrollbar is in every image and the layout is 15px narrower than
            # the one a reader sees.
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale}",
            # The pages fetch on mount; the budget is the same one the render sweep relies on.
            "--virtual-time-budget=15000",
            f"--screenshot={target}",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert target.exists(), f"没有生成 {target.name}：{url}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="", help="a bearer token; without one every image is the login page")
    parser.add_argument("--user", default="", help="the JSON user object, as /auth/login returns it")
    parser.add_argument("--out", default=str(ROOT / "docs" / "images"))
    parser.add_argument("--lang", default="", choices=["", "zh", "en"], help="pin the console's language")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--scale", type=int, default=2, help="device pixel ratio; 2 matches the images in the repo")
    parser.add_argument("--only", default="", help="comma-separated filenames, to re-capture a few")
    args = parser.parse_args()

    sweep = _load_sweep()
    browser = sweep.find_browser()
    if browser is None:
        print("no headless browser found (looked for chromium-cli, Chrome, Chromium)", file=sys.stderr)
        return 2
    if not args.token:
        print("--token is required: without it every screenshot would be the login page", file=sys.stderr)
        return 2

    directory = Path(args.out)
    if not directory.is_dir():
        print(f"the frontend is not built or the path is wrong: {directory} does not exist", file=sys.stderr)
        return 2

    user = json.loads(args.user) if args.user else None
    entry = sweep.seed_page(args.base_url, args.token, user, sweep.SEED_DIRECTORY)
    reason = sweep.seed_is_the_build_just_written(entry)
    if reason:
        print(reason, file=sys.stderr)
        (sweep.SEED_DIRECTORY / "seed.html").unlink(missing_ok=True)
        return 2

    values = instance_values(args.base_url, args.token)
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        print(
            f"实例里没有这些值，截图会指向不存在的记录：{missing}。先跑 `aletheia demo` 或 seed_smoke_instance.py。",
            file=sys.stderr,
        )
        (sweep.SEED_DIRECTORY / "seed.html").unlink(missing_ok=True)
        return 2

    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    captured = 0
    try:
        for filename, route in SCREENS:
            if wanted and filename not in wanted:
                continue
            path = route.format(**values)
            if args.lang:
                path = f"{path}{'&' if '?' in path else '?'}lang={args.lang}"
            capture(
                browser,
                sweep.seeded_url(entry, path),
                directory / filename,
                width=args.width,
                height=args.height,
                scale=args.scale,
            )
            captured += 1
            print(f"  {filename:36s} {route}")
    finally:
        (sweep.SEED_DIRECTORY / "seed.html").unlink(missing_ok=True)

    print(
        f"\n{captured} 张已写入 {directory}（{args.width}×{args.height} @ {args.scale}x，语言 {args.lang or '默认'}）"
    )
    print("图片换了就要看一眼对应的说明文字还对不对：一张截图是一条可以被读到的断言。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
