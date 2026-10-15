from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app" / "filtered_execution.py"
PATCHED = ROOT / "issue4_patch_source" / "filtered_execution.py"
BACKUP = TARGET.with_name(TARGET.name + ".issue4.bak")


def main() -> int:
    if not TARGET.is_file() or not PATCHED.is_file():
        print("ERROR: expected app/filtered_execution.py patch file is missing")
        return 2
    current = TARGET.read_text(encoding="utf-8-sig")
    patched = PATCHED.read_text(encoding="utf-8")
    marker = "def _aggregate_selected("
    if marker not in current or "def _coverage_validator(" not in current:
        print("ERROR: expected aggregation function markers not found; file was not changed")
        return 2
    if "posting_month" in current[current.index(marker):current.index("def _coverage_validator(") ] and "duplicate_source_row_id" in current:
        print("Issue 4 aggregation behavior appears already installed; no change made")
    else:
        if BACKUP.exists():
            print(f"ERROR: backup already exists; inspect it before retrying: {BACKUP}")
            return 2
        shutil.copy2(TARGET, BACKUP)
        new_block = patched[patched.index(marker):patched.index("def _coverage_validator(")].rstrip()
        start = current.index(marker)
        end = current.index("def _coverage_validator(", start)
        updated = current[:start] + new_block + "\n\n" + current[end:]
        # Only the named aggregation function is replaced.
        TARGET.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Updated {TARGET}; backup: {BACKUP}")

    # Install tests as a new file; refuse to overwrite an existing custom test.
    source_test = Path(__file__).resolve().parent.parent / "tests" / "test_reporting_month_identity.py"
    dest_test = ROOT / "tests" / "test_reporting_month_identity.py"
    if not source_test.is_file():
        print("ERROR: test patch file missing")
        return 2
    if dest_test.exists():
        if dest_test.read_bytes() != source_test.read_bytes():
            print(f"ERROR: destination test already exists with different contents: {dest_test}")
            return 2
    else:
        shutil.copy2(source_test, dest_test)
    print("Issue 4 applied. Run: python -m pytest -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
