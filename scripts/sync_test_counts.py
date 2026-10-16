"""Write the test counts into the documents that state them, instead of by hand.

Adding a single test edits six places: two README badges, two README sentences, and two testing
pages. `tests/test_documented_claims.py` fails when any of them is stale, which is correct and
which turned "add a test" into a chore with six chances to stop halfway. That is the shape of
task a script should do, and this repository already has the pattern -- `generate_types.py`
writes `generated.ts` and `--check` refuses to.

What it will **not** do is write prose. A test file with no row in the distribution table is a
failure rather than an insertion: the number is mechanical, the sentence beside it is not, and a
script that invented 「覆盖什么」 would be writing documentation nobody read. So a missing row is
named and left for a person, exactly as `generate_types.py` fails loudly rather than guessing at
an endpoint it could not call.

    python scripts/sync_test_counts.py            # update the documents
    python scripts/sync_test_counts.py --check    # report what is stale, change nothing
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# Every place a total is stated, and the pattern that finds it. `\1` is the group replaced.
#
# Both the badge and the sentence, because they are separate copies: the badge sat correct while
# the prose said `1379`, and a reader who checks one and finds it right has no reason to look at
# the other.
TOTALS = {
    "README.md": (r"tests-(\d+)%20passing", r"(\d{3,5}) tests\b"),
    "README.zh-CN.md": (r"tests-(\d+)%20passing", r"(\d{3,5}) 个测试"),
    "docs/testing.md": (r"\*\*(\d+) tests\*\*",),
    "docs/testing.zh-CN.md": (r"\*\*(\d+) 个测试\*\*",),
}

# The per-file row: `| \`test_x.py\` | 14 | what it covers |`. Only the middle column is touched.
ROW = re.compile(r"^\| `(?P<name>[\w.]+\.py)` \| (?P<count>\d+) \| (?P<covers>.*) \|$")

DISTRIBUTIONS = ("docs/testing.md", "docs/testing.zh-CN.md")


def counts() -> dict[str, int]:
    """Test file name -> collected count, per pytest.

    Collection rather than a passed count: skips depend on which service containers are
    reachable, so a passed count would be right in one environment and wrong in every other.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(TESTS)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return {Path(name).name: int(count) for name, count in re.findall(r"^(tests/\S+\.py): (\d+)$", out, re.MULTILINE)}


def sync(text: str, filename: str, per_file: dict[str, int], total: int) -> tuple[str, list[str]]:
    """The file's text with current numbers, and what could not be filled in.

    Pure, so the test can hold the committed documents to this without running pytest twice and
    without writing anything: the test asserts `sync(current) == current`.
    """
    missing: list[str] = []
    for pattern in TOTALS.get(filename, ()):
        # A replacement function rather than a template, so a pattern that stops matching is
        # visible here rather than silently doing nothing.
        if not re.search(pattern, text):
            missing.append(f"{filename}: 找不到总数声明（{pattern}）")
            continue
        text = re.sub(pattern, lambda match: match.group(0).replace(match.group(1), str(total)), text)

    if filename in DISTRIBUTIONS:
        lines: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            match = ROW.match(line)
            if not match:
                lines.append(line)
                continue
            name = match.group("name")
            seen.add(name)
            if name not in per_file:
                # A row for a file that is gone. Left in place and reported: deleting it is a
                # judgement about the document, not about a number.
                missing.append(f"{filename}: {name} 这一行对应的测试文件不存在了")
                lines.append(line)
                continue
            lines.append(f"| `{name}` | {per_file[name]} | {match.group('covers')} |")
        # And the other direction: a new test file with no row. The number is mechanical, the
        # sentence is not, so this is reported and a person writes it.
        for name in sorted(set(per_file) - seen):
            missing.append(f"{filename}: 缺少 {name} 的行——数量可以自动填，「覆盖什么」要人来写")
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    return text, missing


def documents() -> list[str]:
    """Every document that states a count, each one once.

    `docs/testing*.md` are in both maps -- they carry the total *and* the per-file table -- and
    iterating the two in sequence wrote and reported them twice.
    """
    return list(dict.fromkeys([*TOTALS, *DISTRIBUTIONS]))


def apply(per_file: dict[str, int], *, check: bool) -> int:
    total = sum(per_file.values())
    stale: list[str] = []
    unresolved: list[str] = []

    for filename in documents():
        path = ROOT / filename
        current = path.read_text(encoding="utf-8")
        wanted, missing = sync(current, filename, per_file, total)
        unresolved.extend(missing)
        if wanted == current:
            continue
        if check:
            # Which numbers, not just which file: a diff would be a hundred lines of table rows
            # when the change is one digit in each of them.
            claimed = sorted(
                {int(found) for pattern in TOTALS.get(filename, ()) for found in re.findall(pattern, current)}
            )
            stale.append(f"{filename}: 写着 {claimed}，应为 {total}" if claimed else f"{filename}: 找不到总数声明")
            continue
        path.write_text(wanted, encoding="utf-8")
        print(f"已更新  {filename}")

    for note in unresolved:
        print(f"需要人工处理  {note}", file=sys.stderr)

    if check and stale:
        print("以下文件里的数量与收集到的测试数不符：", file=sys.stderr)
        for note in stale:
            print(f"  {note}", file=sys.stderr)
        print("\n运行 `python scripts/sync_test_counts.py` 更新它们。", file=sys.stderr)

    if not check:
        print(f"共 {total} 个测试，分布在 {len(per_file)} 个文件里。")

    return 1 if (check and stale) or unresolved else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="把收集到的测试数量写进声明了它们的文档里")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只报告哪些文档过期，不做修改（CI 用这个）",
    )
    args = parser.parse_args()
    return apply(counts(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
