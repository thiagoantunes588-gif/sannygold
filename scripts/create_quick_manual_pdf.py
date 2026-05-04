from __future__ import annotations

from pathlib import Path
import re
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "manual-rapido-equipe.md"
OUTPUT = ROOT / "output" / "pdf" / "sannygold-manual-rapido-equipe.pdf"
LOGO = ROOT / "app" / "static" / "sannygold-logo.jpg"

PAGE_W, PAGE_H = A4
MARGIN_X = 54
TOP = PAGE_H - 58
BOTTOM = 54
GOLD = colors.HexColor("#b98121")
INK = colors.HexColor("#1d1a17")
MUTED = colors.HexColor("#6a6258")
LINE = colors.HexColor("#ead8b8")
LIGHT = colors.HexColor("#f8f5ef")
AQUA = colors.HexColor("#1b94aa")


def clean_inline(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"\1", text).strip()


def draw_footer(c: canvas.Canvas, page_number: int):
    c.setStrokeColor(LINE)
    c.line(MARGIN_X, 36, PAGE_W - MARGIN_X, 36)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN_X, 22, "Sistema SannyGold - manual rapido da equipe")
    c.drawRightString(PAGE_W - MARGIN_X, 22, f"{page_number:02d}")


def new_page(c: canvas.Canvas, page_number: int) -> float:
    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(LIGHT)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), MARGIN_X, PAGE_H - 82, width=36, height=36, preserveAspectRatio=True, mask="auto")
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN_X + 46, PAGE_H - 62, "SANNY GOLD")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN_X + 46, PAGE_H - 75, "Banheiros de Luxo")
    draw_footer(c, page_number)
    return TOP - 50


def draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, size: int, color, bold=False, width=82, leading=None) -> float:
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    leading = leading or size * 1.35
    for line in textwrap.wrap(clean_inline(text), width=width) or [""]:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_pdf() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    c = canvas.Canvas(str(OUTPUT), pagesize=A4)
    page = 1
    y = new_page(c, page)

    for raw in lines:
        line = raw.rstrip()
        if y < BOTTOM + 40:
            c.showPage()
            page += 1
            y = new_page(c, page)

        if line.startswith("# "):
            y = draw_wrapped(c, line[2:], MARGIN_X, y, 24, INK, bold=True, width=34, leading=30) - 16
        elif line.startswith("## "):
            y -= 8
            c.setStrokeColor(LINE)
            c.line(MARGIN_X, y + 10, PAGE_W - MARGIN_X, y + 10)
            y = draw_wrapped(c, line[3:], MARGIN_X, y, 16, GOLD, bold=True, width=48, leading=22) - 4
        elif line.startswith("- "):
            c.setFillColor(AQUA)
            c.circle(MARGIN_X + 4, y + 4, 3, fill=1, stroke=0)
            y = draw_wrapped(c, line[2:], MARGIN_X + 16, y, 10, INK, width=82, leading=14) - 2
        elif re.match(r"^\d+\. ", line):
            number, body = line.split(". ", 1)
            c.setFillColor(GOLD)
            c.circle(MARGIN_X + 7, y + 4, 7, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(MARGIN_X + 7, y + 1, number)
            y = draw_wrapped(c, body, MARGIN_X + 22, y, 10, INK, width=80, leading=14) - 2
        elif not line:
            y -= 8
        else:
            y = draw_wrapped(c, line, MARGIN_X, y, 10.5, MUTED, width=88, leading=15) - 2

    c.save()
    return OUTPUT


if __name__ == "__main__":
    print(build_pdf())
