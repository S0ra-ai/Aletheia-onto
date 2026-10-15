#!/usr/bin/env python3
"""Assert that the render check's allowance covers exactly the columns that are empty.

`ui_smoke.py` lets columns that are empty because the *data* has nothing in them be listed in
`KNOWN_SPARSE`. An allowance suppresses a finding, so a stale entry suppresses the very thing
the check exists to find: a column that was sparse yesterday and is blank today for a
field-name mismatch is never reported.

So the sweep runs once more with the allowance switched off, and what it reports has to be
exactly what the list contains -- more or fewer, either way this fails. The comparison goes
through the script's own route normalisation: re-implementing it here would let this check
disagree with the thing it checks.

Usage (the CI job does this against a running instance):

    python scripts/check_smoke_allowance.py --base-url http://127.0.0.1:8077 \
        --username admin --password '...'
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def login(base_url: str, username: str, password: str) -> dict:
    request = urllib.request.Request(
        f"{base_url}/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8077")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    import ui_smoke

    session = login(args.base_url, args.username, args.password)
    sweep = subprocess.run(
        [
            sys.executable,
            str(Path(ui_smoke.__file__)),
            "--base-url",
            args.base_url,
            "--token",
            session["token"],
            "--user",
            json.dumps(session["user"]),
            "--allow",
            "",
        ],
        capture_output=True,
        text=True,
    )
    print(sweep.stdout, sweep.stderr)

    found = set()
    for route, reported in re.findall(r"^(/\S+)\s+\d+ table\(s\).*?EMPTY: (.*)$", sweep.stdout, re.M):
        for item in reported.split(","):
            found.add((ui_smoke._normalise_route(route), item.split(":", 1)[-1].strip()))

    expected = set(ui_smoke.KNOWN_SPARSE)
    if sweep.returncode == 0:
        print(
            "关掉豁免之后仍然报「没有整列为空的列」——豁免清单已经过期，或者那几列已经有数据了：请删掉对应条目。",
            file=sys.stderr,
        )
        return 1
    if found != expected:
        print(
            f"豁免清单与实际空列不一致：\n  清单 {sorted(expected)}\n  实际 {sorted(found)}\n"
            "清单里多出来的条目会长期掩盖一个真实发现；少掉的条目意味着该列的空白是新出现的。",
            file=sys.stderr,
        )
        return 1
    print("豁免清单正好覆盖：", sorted(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
