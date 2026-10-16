# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.anomaly_detector import detect_anomalies


def main():
    input_path = ROOT / "audit" / "runtime_state.json"
    output_path = ROOT / "audit" / "anomaly_report.json"

    data = json.loads(input_path.read_text(encoding="utf-8"))
    flags = detect_anomalies(data["records"])

    report = {
        "source_sha256": data["snapshot_sha256"],
        "window_start": data["window_start"],
        "window_end": data["window_end"],
        "rule_thresholds": {
            "AN-01": "absolute price-median change > 0.12",
            "AN-02": "observed count ratio <= 0.50",
            "AN-03": "observed count ratio >= 2.0",
            "AN-04": "final-two-month share >= 0.70",
        },
        "flag_count": len(flags),
        "counts_by_rule": dict(sorted(Counter(
            flag["rule_id"] for flag in flags
        ).items())),
        "flags": flags,
    }

    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Anomaly report: {output_path.relative_to(ROOT)}")
    print(f"Total flags: {len(flags)}")
    for rule_id in ("AN-01", "AN-02", "AN-03", "AN-04"):
        print(
            f"{rule_id}: "
            f"{report['counts_by_rule'].get(rule_id, 0)}"
        )


if __name__ == "__main__":
    main()
