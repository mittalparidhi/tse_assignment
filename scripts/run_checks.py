"""Run every check and keep a timestamped log of it.

Continues the first implementation's convention (``legacy/audit/test_logs/``):
each run writes ``audit/test_logs/check_run_<timestamp>.txt`` with the commit,
the interpreter and the full output of every command, and appends one row to
``audit/test_logs/check_log_index.csv``.

    python scripts/run_checks.py            # tests, claims, the three table checks
    python scripts/run_checks.py --replay   # also replay the LLM sweep offline (~25 min)

Exit code 0 only if every command passed.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "audit" / "test_logs"
INDEX = LOG_DIR / "check_log_index.csv"

CHECKS = [
    ("pytest", [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"]),
    ("verify_claims", [sys.executable, "scripts/verify_claims.py"]),
    ("table_v2_deterministic", [sys.executable, "scripts/headline_table.py", "--v2", "--check"]),
    ("table_v2_llm", [sys.executable, "scripts/headline_table.py", "--v2", "--tag", "v2_llm", "--check"]),
    ("table_pre_v2", [sys.executable, "scripts/headline_table.py", "--check"]),
]
REPLAY = ("replay_llm_sweep", [sys.executable, "scripts/replay_llm_sweep.py"])


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return out.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replay", action="store_true",
                        help="also replay the committed LLM sweep from the reply cache")
    args = parser.parse_args()

    checks = CHECKS + ([REPLAY] if args.replay else [])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"check_run_{stamp}.txt"
    commit = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain"))

    results = []
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        log.write(f"check run {stamp}\ncommit {commit}{' (uncommitted changes)' if dirty else ''}\n"
                  f"python {sys.version.split()[0]}\n")
        for name, cmd in checks:
            started = time.perf_counter()
            run = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                                 encoding="utf-8", errors="replace",
                                 env={**__import__("os").environ, "PYTHONUTF8": "1"})
            seconds = time.perf_counter() - started
            status = "PASS" if run.returncode == 0 else "FAIL"
            results.append((name, status, run.returncode, seconds))
            log.write(f"\n{'=' * 78}\n{name}: {status} (exit {run.returncode}, {seconds:.1f}s)\n"
                      f"$ {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}\n"
                      f"{'=' * 78}\n{run.stdout}{run.stderr}")
            print(f"{name:<26}{status}  ({seconds:.1f}s)", flush=True)
        overall = "PASS" if all(s == "PASS" for _, s, _, _ in results) else "FAIL"
        log.write(f"\n{'=' * 78}\nOVERALL {overall}\n")

    new_index = not INDEX.exists()
    with INDEX.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        if new_index:
            writer.writerow(["log_file", "timestamp", "commit", "uncommitted_changes",
                             *[name for name, _ in CHECKS], REPLAY[0], "overall"])
        by_name = {name: status for name, status, _, _ in results}
        writer.writerow([log_path.name, stamp, commit, dirty,
                         *[by_name.get(name, "") for name, _ in CHECKS],
                         by_name.get(REPLAY[0], "not run"), overall])
    print(f"OVERALL {overall} -> {log_path.relative_to(ROOT)}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
