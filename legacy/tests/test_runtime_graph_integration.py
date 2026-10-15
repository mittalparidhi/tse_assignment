"""End-to-end smoke test for graph-driven runtime report generation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_runtime_builder_uses_execution_graph_and_emits_real_trace() -> None:
    root = Path(__file__).resolve().parents[1]
    builder = root / "scripts" / "build_runtime_state.py"
    output = root / "audit" / "runtime_state.json"

    result = subprocess.run(
        [sys.executable, str(builder)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "built successfully through execution graph" in result.stdout
    assert output.is_file()

    report = json.loads(output.read_text(encoding="utf-8"))
    months = report.get("monthly_records", report.get("months"))
    assert isinstance(months, list) and len(months) == 12
    assert len(report["trace"]) > 4

    trace = report["trace"]
    assert [event["i"] for event in trace] == list(range(len(trace)))
    agents = {event["agent"] for event in trace}
    assert {"planner", "scanner", "aggregator", "validator", "anomaly", "reporter"} <= agents

    anomaly_count = len(report["anomalies"])
    assert len(report["diagnostics"]) == anomaly_count
    if anomaly_count:
        assert "diagnostic" in agents

    counters = report["loop_counters"]
    assert counters == {"coverage_repair": 0, "critique_revision": 0}
    assert report["execution_graph"]["loop_counters"] == counters
    assert report["execution_graph"]["trace_event_count"] == len(trace)
    metadata = report.get("metadata", report)
    assert metadata["snapshot_sha256"] == (
        "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
    )
