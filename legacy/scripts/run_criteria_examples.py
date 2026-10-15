"""Run and print all example Criteria Agent requests as normalized JSON."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.criteria_agent import CriteriaAgent, SourceCatalog  # noqa: E402


def main() -> None:
    examples = json.loads((ROOT / "examples" / "criteria_requests.json").read_text(encoding="utf-8"))
    agent = CriteriaAgent(catalog=SourceCatalog.from_csv(ROOT / "data" / "raw" / "hyderabad.csv"))
    results = []
    for item in examples:
        result = agent.run(item["request"])
        results.append({"id": item["id"], "status": "ok", **result.to_dict()})
    output = {"example_count": len(results), "valid_count": len(results), "results": results}
    print(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
