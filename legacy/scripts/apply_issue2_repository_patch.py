"""Apply Issue 2: make the verified processed snapshot the app default.

Run from the repository root with:
    python scripts/apply_issue2_repository_patch.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(text: str, old: str, new: str, label: str, marker: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and marker in text:
        return text  # already patched
    raise RuntimeError(f"Could not safely patch {label}: expected one target, found {count}")


def main() -> int:
    paths = {
        "criteria": ROOT / "app" / "criteria_agent.py",
        "retrieval": ROOT / "app" / "retrieval_agent.py",
        "filtered": ROOT / "app" / "filtered_execution.py",
        "repository": ROOT / "app" / "snapshot_repository.py",
        "test": ROOT / "tests" / "test_snapshot_repository.py",
    }
    for key in ("criteria", "retrieval", "filtered", "repository", "test"):
        if not paths[key].is_file():
            raise RuntimeError(f"Required patch/project file is missing: {paths[key]}. Extract the full patch ZIP into the repository root first.")

    changes: dict[Path, str] = {}
    criteria = paths["criteria"].read_text(encoding="utf-8")
    criteria = patch(
        criteria,
        '''from app.schemas import (
    FROZEN_SOURCE_SHA256,
    WINDOW_END,
    WINDOW_START,
    SourcePeriod,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "raw" / "hyderabad.csv"''',
        '''from app.schemas import (
    FROZEN_SOURCE_SHA256,
    WINDOW_END,
    WINDOW_START,
    SourcePeriod,
)
from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"''',
        "criteria imports/default source path",
        "from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot",
    )
    criteria = patch(
        criteria,
        '''        digest = _source_sha256(source_path)
        if digest != FROZEN_SOURCE_SHA256:
            raise CriteriaValidationError(
                "snapshot_integrity_error",
                "The Criteria Agent source hash does not match the frozen Hyderabad snapshot.",
            )''',
        '''        if source_path.resolve() == DEFAULT_SOURCE_PATH.resolve():
            try:
                _, digest = load_processed_snapshot()
            except SnapshotRepositoryError as exc:
                raise CriteriaValidationError(exc.code, exc.message) from exc
        else:
            # Explicit custom paths preserve the original pinned-raw/fixture behavior.
            digest = _source_sha256(source_path)
        if digest != FROZEN_SOURCE_SHA256:
            raise CriteriaValidationError(
                "snapshot_integrity_error",
                "The Criteria Agent source hash does not match the frozen Hyderabad snapshot.",
            )''',
        "criteria source integrity validation",
        "_, digest = load_processed_snapshot()",
    )
    changes[paths["criteria"]] = criteria

    retrieval = paths["retrieval"].read_text(encoding="utf-8")
    retrieval = patch(
        retrieval,
        '''from app.schemas import FROZEN_SOURCE_SHA256, SourcePeriod

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "raw" / "hyderabad.csv"''',
        '''from app.schemas import FROZEN_SOURCE_SHA256, SourcePeriod
from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"''',
        "retrieval imports/default source path",
        "from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot",
    )
    retrieval = patch(
        retrieval,
        '''        if not self.source_path.is_file():
            raise RetrievalError("source_missing", f"Frozen source CSV not found: {self.source_path}")
        digest = _sha256(self.source_path)
        if self.expected_sha256 is not None and digest != self.expected_sha256:
            raise RetrievalError(
                "snapshot_integrity_error",
                "Raw CSV digest differs from the pinned frozen snapshot SHA-256.",
            )

        frame = pd.read_csv(self.source_path, low_memory=False)
        missing = sorted(self.REQUIRED_COLUMNS - set(frame.columns))''',
        '''        is_default_processed = self.source_path.resolve() == DEFAULT_SOURCE_PATH.resolve()
        if is_default_processed:
            try:
                frame, digest = load_processed_snapshot()
            except SnapshotRepositoryError as exc:
                raise RetrievalError(exc.code, exc.message) from exc
        else:
            # Explicit raw paths and temporary fixture paths remain supported.
            if not self.source_path.is_file():
                raise RetrievalError("source_missing", f"Frozen source CSV not found: {self.source_path}")
            digest = _sha256(self.source_path)
            if self.expected_sha256 is not None and digest != self.expected_sha256:
                raise RetrievalError(
                    "snapshot_integrity_error",
                    "Raw CSV digest differs from the pinned frozen snapshot SHA-256.",
                )
            frame = pd.read_csv(self.source_path, low_memory=False)

        if self.expected_sha256 is not None and digest != self.expected_sha256:
            raise RetrievalError(
                "snapshot_integrity_error",
                "Source provenance hash differs from the pinned frozen raw snapshot SHA-256.",
            )

        missing = sorted(self.REQUIRED_COLUMNS - set(frame.columns))''',
        "retrieval data loading/integrity checks",
        "frame, digest = load_processed_snapshot()",
    )
    retrieval = patch(
        retrieval,
        '''        frame = frame.copy()
        frame.insert(0, "source_row_id", np.arange(len(frame), dtype=np.int64))''',
        '''        frame = frame.copy()
        if "source_row_id" not in frame.columns:
            frame.insert(0, "source_row_id", np.arange(len(frame), dtype=np.int64))
        else:
            try:
                frame["source_row_id"] = pd.to_numeric(frame["source_row_id"], errors="raise").astype(np.int64)
            except (TypeError, ValueError, OverflowError) as exc:
                raise RetrievalError("source_schema_error", "source_row_id must contain integer row identities.") from exc''',
        "retrieval source-row identity handling",
        'if "source_row_id" not in frame.columns:',
    )
    changes[paths["retrieval"]] = retrieval

    filtered = paths["filtered"].read_text(encoding="utf-8")
    filtered = patch(
        filtered,
        '''DEFAULT_SOURCE_PATH = ROOT / "data" / "raw" / "hyderabad.csv"''',
        '''DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"''',
        "filtered execution default source path",
        'DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"',
    )
    changes[paths["filtered"]] = filtered

    # Preflight all target strings before modifying the project.
    for path in changes:
        backup = path.with_name(path.name + ".issue2.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
    for path, content in changes.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    print("Issue 2 applied. Backups use the .issue2.bak suffix.")
    print("Next: run python -m pytest -q")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PATCH ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
