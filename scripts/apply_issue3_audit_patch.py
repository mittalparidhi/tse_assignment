#!/usr/bin/env python3
"""Install Issue 3 audit reconciliation safely and idempotently."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_processed_snapshot.py"
FINALIZER = ROOT / "scripts" / "finalize_snapshot_audits.py"
MARKER = "# ISSUE3_FINAL_AUDIT_FINALIZER"
NEEDLE = '''    raw_hash_after = sha256_file(RAW)
    if raw_hash_after != raw_hash_before:
        raise RuntimeError("snapshot_integrity_error: raw CSV changed during processing")
    print(json.dumps({"status": "ok", **actual, "processed_sha256": processed_hash, "output_columns": len(final_columns)}, indent=2))'''
REPLACEMENT = '''    raw_hash_after = sha256_file(RAW)
    if raw_hash_after != raw_hash_before:
        raise RuntimeError("snapshot_integrity_error: raw CSV changed during processing")

    # ISSUE3_FINAL_AUDIT_FINALIZER: synchronize the audit/summary with the final
    # processed artifact after the base cleaner has written its preliminary audit.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "finalize_snapshot_audits.py")], cwd=ROOT, check=True)
    print(json.dumps({"status": "ok", **actual, "processed_sha256": processed_hash, "output_columns": len(final_columns)}, indent=2))'''


def main() -> int:
    for path in (BUILDER, FINALIZER, ROOT / "data/processed/hyderabad_clean.csv", ROOT / "audit/hyderabad_cleaning_audit.json"):
        if not path.is_file():
            raise RuntimeError(f"Required path not found: {path.relative_to(ROOT)}")
    text = BUILDER.read_text(encoding="utf-8")
    if MARKER in text:
        print("Issue 3 builder integration is already installed.")
    else:
        if NEEDLE not in text:
            raise RuntimeError("Expected builder insertion point not found; no files changed.")
        backup = BUILDER.with_suffix(BUILDER.suffix + ".issue3.bak")
        if not backup.exists():
            shutil.copy2(BUILDER, backup)
        BUILDER.write_text(text.replace(NEEDLE, REPLACEMENT), encoding="utf-8", newline="\n")
        print(f"Patched build script; backup: {backup.name}")
    # Preserve original audit artifacts before rewriting for the first time.
    for relative in ("audit/hyderabad_cleaning_audit.json", "audit/hyderabad_cleaning_summary.csv"):
        path = ROOT / relative
        backup = path.with_suffix(path.suffix + ".issue3.bak")
        if path.exists() and not backup.exists():
            shutil.copy2(path, backup)
            print(f"Backed up {relative} -> {backup.name}")
    result = subprocess.run([sys.executable, str(FINALIZER)], cwd=ROOT)
    if result.returncode != 0:
        print("Audit reconciliation failed. Existing backups are retained.", file=sys.stderr)
        return result.returncode
    print("Issue 3 applied: audit JSON and summary now describe the final processed artifact.")
    print("Future builds will regenerate these audit artifacts as part of the build script.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
