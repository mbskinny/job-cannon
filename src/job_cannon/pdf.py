"""Render a plain-text letter to PDF.

Uses a vendored DejaVu Serif TTF because the built-in PDF fonts only cover
Latin-1 (no €, smart quotes, etc.).
"""

import re
from importlib import resources

from fpdf import FPDF

FONT = resources.files("job_cannon") / "fonts" / "DejaVuSerif.ttf"


def render_letter(text: str) -> bytes:
    """A4, 25 mm margins, 11 pt. Blank lines separate paragraphs; other line breaks are kept."""
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(True, margin=25)
    pdf.add_page()
    with resources.as_file(FONT) as font_path:
        pdf.add_font("DejaVuSerif", "", str(font_path))
    pdf.set_font("DejaVuSerif", size=11)
    line_height = 5.6
    paragraphs = re.split(r"\n[ \t]*\n\s*", text.replace("\r\n", "\n").strip())
    for i, para in enumerate(paragraphs):
        if i:
            pdf.ln(line_height)
        pdf.multi_cell(0, line_height, para.strip("\n"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
