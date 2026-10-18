"""Reject filtered requests from the public contract-v1 CLI.

Filtered execution is experimental and is not part of the contract-v1
public analysis interface. Use the canonical full-snapshot analysis path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--request-file",
        type=Path,
        default=None,
        help="JSON filter request (rejected under public contract v1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "audit" / "filtered_runtime_state.json",
        help="Legacy argument; no report is written for rejected requests",
    )
    args = parser.parse_args()

    # Validate a supplied file before returning the contract rejection.
    if args.request_file is not None:
        try:
            request = json.loads(
                args.request_file.read_text(encoding="utf-8-sig")
            )
        except OSError as exc:
            print(json.dumps({
                "status": "error",
                "error_code": "request_file_error",
                "message": str(exc),
            }, indent=2))
            return 2
        except json.JSONDecodeError as exc:
            print(json.dumps({
                "status": "error",
                "error_code": "invalid_request_json",
                "message": str(exc),
            }, indent=2))
            return 2

        if not isinstance(request, dict):
            print(json.dumps({
                "status": "error",
                "error_code": "invalid_request_shape",
                "message": "The request must be a JSON object.",
            }, indent=2))
            return 2

    print(json.dumps({
        "status": "error",
        "error_code": "unsupported_filter",
        "contract_version": "1.0.0-draft",
        "message": (
            "Filtered analysis is not supported by the public contract-v1 "
            "interface. Run the canonical full-snapshot analysis instead. "
            "The filtered execution graph remains experimental."
        ),
    }, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())