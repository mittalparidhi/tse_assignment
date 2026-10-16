# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
import json
import subprocess
import sys
from pathlib import Path


def test_public_filtered_cli_rejects_request_under_contract_v1(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    request_path = root / "examples" / "filtered_request.json"
    output_path = tmp_path / "filtered_runtime_state.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_filtered_analysis",
            "--request-file",
            str(request_path),
            "--output",
            str(output_path),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + "\n" + result.stderr

    response = json.loads(result.stdout)
    assert response["status"] == "error"
    assert response["error_code"] == "unsupported_filter"
    assert response["contract_version"] == "1.0.0-draft"
    assert not output_path.exists()