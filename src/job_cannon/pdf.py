"""Render a plain-text letter to PDF.

Fonts are vendored Noto TTFs (the built-in PDF fonts only cover Latin-1). There
is no hyphenation, so text is set ragged-right rather than justified.
"""

import re
from datetime import date
from importlib import resources
from urllib.parse import urlsplit

from fpdf import FPDF

from job_cannon.repo.cover_letters import DEFAULT_ACCENT, long_date

FONTS = resources.files("job_cannon") / "fonts"
INK = (34, 34, 34)
MUTED = (110, 110, 110)
DATE_RE = re.compile(r"\d{1,2} [A-Z][a-z]+ \d{4}")
PARAGRAPH_RE = re.compile(r"\n[ \t]*\n\s*")


def smarten(text: str) -> str:
    """Typographic quotes and dashes: I'm -> I’m, "x" -> “x”, -- -> –."""
    text = text.replace("---", "—").replace("--", "–").replace(" - ", " – ")
    text = re.sub(r"(?<=\w)'", "’", text)           # I’m, Toggl’s, teams’
    text = re.sub(r"'(?=\w)", "‘", text)            # opening single quote
    text = text.replace("'", "’")
    text = re.sub(r'(^|(?<=[\s(\[—–]))"', "“", text)  # opening double quote
    return text.replace('"', "”")


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _contact_items(lh: dict) -> list[tuple[str, str]]:
    """(label, link) pairs for the contact line; link is '' when not clickable."""
    items = []
    if lh.get("location"):
        items.append((lh["location"], ""))
    if lh.get("email"):
        items.append((lh["email"], f"mailto:{lh['email']}"))
    if lh.get("phone"):
        items.append((lh["phone"], ""))
    if site := lh.get("website"):
        scheme = urlsplit(site).scheme
        if scheme in ("http", "https"):
            items.append((site.split("://", 1)[1].rstrip("/"), site))
        elif not scheme:
            items.append((site.rstrip("/"), f"https://{site}"))
        else:
            items.append((site, ""))
    return items


def _letterhead(pdf: FPDF, lh: dict, accent: tuple[int, int, int]) -> None:
    pdf.set_font("Sans", "B", 20)
    pdf.set_text_color(*accent)
    pdf.cell(0, 9, lh["name"], new_x="LMARGIN", new_y="NEXT")
    items = _contact_items(lh)
    if items:
        pdf.set_font("Sans", "", 9)
        pdf.set_text_color(*MUTED)
        for i, (label, link) in enumerate(items):
            if i:
                pdf.cell(pdf.get_string_width("   ·   "), 5, "   ·   ")
            pdf.cell(pdf.get_string_width(label), 5, label, link=link)
        pdf.ln(5)
    pdf.ln(3)
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(10)


def render_letter(text: str, letterhead: dict | None = None, today: date | None = None) -> bytes:
    """A4 letter: optional letterhead, date on the right, then the paragraphs.

    Blank lines separate paragraphs and other line breaks are kept. If the
    letter already starts with a date line (from ``{{date}}``), that date is
    used instead of today's.
    """
    lh = letterhead or {}
    accent = _hex_rgb(lh.get("accent") or DEFAULT_ACCENT)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(24, 22, 24)
    pdf.set_auto_page_break(True, margin=22)
    with resources.as_file(FONTS) as fonts:
        pdf.add_font("Serif", "", str(fonts / "NotoSerif-Regular.ttf"))
        pdf.add_font("Sans", "", str(fonts / "NotoSans-Regular.ttf"))
        pdf.add_font("Sans", "B", str(fonts / "NotoSans-Bold.ttf"))
    pdf.add_page()
    if lh.get("name"):
        _letterhead(pdf, lh, accent)

    paragraphs = PARAGRAPH_RE.split(smarten(text.replace("\r\n", "\n").strip()))
    if paragraphs and DATE_RE.fullmatch(paragraphs[0].strip()):
        dated = paragraphs.pop(0).strip()
    else:
        dated = long_date(today or date.today())

    pdf.set_font("Serif", "", 10.5)
    pdf.set_text_color(*INK)
    pdf.cell(0, 5, dated, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    line_height = 5.6
    for i, para in enumerate(p for p in paragraphs if p.strip()):
        if i:
            pdf.ln(3.2)
        pdf.multi_cell(0, line_height, para.strip("\n"), align="L", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
