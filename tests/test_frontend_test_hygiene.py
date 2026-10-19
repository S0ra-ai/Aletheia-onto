"""A test file that mocks the same module twice is not mocking it twice.

`TableColumns.test.tsx` grew in two rounds -- first the mapping and rule queues, then every other
screen -- and each round added its own `vi.mock('../api')`. Two factories for one module path is
not "both apply": which one wins is undefined, and it moved with the module graph.

In CI the **first** won. That factory provides only `ontologyApi`, so `dataSourceApi`,
`permissionApi`, `backupApi`, `tenancyApi`, `governanceApi`, `workflowApi` and `toolApi` fell
through to the real client, every page's fetch rejected, and 23 of 27 tests failed with
「还没有数据行」 and an antd error toast. Locally the **second** won and the suite was green. The
same commit passed one CI run and failed the next.

The tell, which is why this file exists: the four tests that passed were exactly the ones whose
page needs only `ontologyApi` -- the intersection of the two factories. A suite whose failures
line up with which mock block won is reporting the duplicate, not the screens.

Checked per file and only for literal paths: a mock whose path is a variable cannot be counted,
and pretending otherwise would be a check that reports on its own parser.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"

MOCK = re.compile(r"vi\.mock\(\s*['\"]([^'\"]+)['\"]")


def _test_files() -> list[Path]:
    return sorted(FRONTEND_SRC.rglob("*.test.*"))


def _mocked_paths(path: Path) -> list[str]:
    """The module paths a file mocks, ignoring mentions inside comments.

    The comment case is not hypothetical: the fix for this defect explains itself in prose above
    the remaining mock, and a naive scan counts that sentence as a second declaration.
    """
    found: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        found.extend(MOCK.findall(line))
    return found


def test_no_test_file_mocks_the_same_module_twice() -> None:
    files = _test_files()
    assert files, "没有找到任何前端测试文件——路径变了？"

    duplicated: list[str] = []
    for path in files:
        paths = _mocked_paths(path)
        seen: dict[str, int] = {}
        for name in paths:
            seen[name] = seen.get(name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                duplicated.append(f"{path.relative_to(ROOT)} 声明了 {count} 次 vi.mock('{name}')")

    assert not duplicated, (
        "同一个模块被 mock 了两次。两个工厂不是「都生效」，而是哪个生效没有定义——"
        "它会随模块图变化，于是同一份代码一次绿、一次红：\n  " + "\n  ".join(duplicated)
    )
