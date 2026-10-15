"""Load the built-in contract sample into the default platform database.

Kept as a script because it is convenient in a checkout, but it no longer holds the
scenario: `ontology_platform.demo` does, and this calls it. The three copies of that flow
had already drifted once -- the browser's demo stopped assessing an instance -- and a
fourth copy would drift again.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from ontology_platform.database import DEFAULT_PLATFORM_DB, initialize_platform_db
from ontology_platform.demo import run_contract_demo
from ontology_platform.sample_data import DEFAULT_SAMPLE_DB


def main() -> None:
    initialize_platform_db(DEFAULT_PLATFORM_DB)
    result = run_contract_demo(DEFAULT_PLATFORM_DB, DEFAULT_SAMPLE_DB)
    print("已创建合同管理样例库:", result["samplePath"])
    print("已注册数据源:", result["source"])
    print("元数据扫描结果:", result["scan"])
    print(
        "本体草案:",
        {
            "id": result["ontologyId"],
            "objects": len(result["ontology"]["objects"]),
            "relations": len(result["ontology"]["relations"]),
            "rules": len(result["ontology"]["rules"]),
        },
    )
    print("合同 1 语义研判:", result["decision"])


if __name__ == "__main__":
    main()
