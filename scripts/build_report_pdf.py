"""Render REPORT.md to REPORT.pdf (A4) and print its page count.

The brief asks for a 10-12 page report; this renders the Markdown with a
plain academic style through a headless Chromium browser (Edge or Chrome) so
the page count can be checked rather than estimated.

    pip install markdown        # build-time only, not needed to run the app
    python scripts/build_report_pdf.py                         # REPORT.md -> REPORT.pdf
    python scripts/build_report_pdf.py docs/DIAGNOSIS.md       # any other Markdown file
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
# Chrome first: headless Edge exited without writing a PDF on the Windows
# machine this was built on.
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "chromium", "chromium-browser", "google-chrome", "msedge",
]

CSS = """
@page { size: A4; margin: 18mm 17mm; }
body { font-family: "Times New Roman", Georgia, serif; font-size: 10.5pt;
       line-height: 1.32; color: #111; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 14pt 0 4pt; border-bottom: 0.5pt solid #999; }
h3 { font-size: 11pt; margin: 10pt 0 3pt; }
p, li { text-align: justify; margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0; font-size: 8.6pt;
        page-break-inside: auto; }
th, td { border: 0.5pt solid #888; padding: 2pt 4pt; vertical-align: top; }
th { background: #eee; }
tr { page-break-inside: avoid; }
pre { font-size: 7.6pt; line-height: 1.2; background: #f6f6f6; padding: 4pt;
      white-space: pre-wrap; page-break-inside: avoid; }
code { font-family: Consolas, "Courier New", monospace; font-size: 0.92em; }
hr { border: 0; border-top: 0.5pt solid #bbb; }
"""


def _browser() -> str:
    for candidate in BROWSERS:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    sys.exit("no Chromium-based browser found (Edge or Chrome)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", nargs="?", default="REPORT.md",
                        help="Markdown file, relative to the repository (default REPORT.md)")
    args = parser.parse_args()
    src = ROOT / args.source
    source = src.read_text(encoding="utf-8")
    body = markdown.markdown(source, extensions=["tables", "fenced_code"])
    html = ROOT / "results" / "report_build.html"
    html.write_text(f"<!doctype html><html><head><meta charset='utf-8'>"
                    f"<title>Report</title><style>{CSS}</style></head>"
                    f"<body>{body}</body></html>", encoding="utf-8")
    pdf = src.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    # A separate profile, so the call cannot hand off to a browser already open.
    with tempfile.TemporaryDirectory() as profile:
        run = subprocess.run([_browser(), "--headless=new", "--disable-gpu",
                              "--no-pdf-header-footer", f"--user-data-dir={profile}",
                              f"--print-to-pdf={pdf}", html.as_uri()],
                             capture_output=True, text=True, timeout=180)
    html.unlink()
    if not pdf.exists():
        sys.exit(f"the browser wrote no PDF (exit {run.returncode}): {run.stderr[-500:]}")
    from pypdf import PdfReader
    pages = len(PdfReader(str(pdf)).pages)
    print(f"{pdf.relative_to(ROOT)}: {pages} pages (A4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
