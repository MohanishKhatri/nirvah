"""Render the markdown policy documents in seed/policies/ to PDFs.

    python seed/make_pdfs.py

The PDFs are what an admin uploads through the UI, and what pdfplumber ingests.
Requires fpdf2 (``pip install fpdf2``).
"""

from __future__ import annotations

import os
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fpdf import FPDF  # noqa: E402

POLICY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies")

# Core PDF fonts are Latin-1 only; these characters are spelled out instead.
REPLACEMENTS = {"₹": "Rs ", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"'}


def _latin1(text: str) -> str:
    for src, dst in REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def render(md_path: str, pdf_path: str) -> None:
    with open(md_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(3)
            continue

        if stripped.startswith("## "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, _latin1(stripped[3:]))
            pdf.ln(1)
        elif stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 10, _latin1(stripped[2:]))
            pdf.ln(4)
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, _latin1(stripped))
            pdf.ln(1)

    pdf.output(pdf_path)


def main() -> None:
    made = 0
    for filename in sorted(os.listdir(POLICY_DIR)):
        if not filename.endswith(".md"):
            continue
        md_path = os.path.join(POLICY_DIR, filename)
        pdf_path = md_path[:-3] + ".pdf"
        render(md_path, pdf_path)
        print(f"  {os.path.basename(pdf_path)}")
        made += 1
    print(f"{made} PDFs written to {POLICY_DIR}")


if __name__ == "__main__":
    main()
