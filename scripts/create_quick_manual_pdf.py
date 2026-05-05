from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "docs" / "manual-rapido-equipe.md"
OUTPUT = ROOT / "output" / "pdf" / "sannygold-manual-rapido-equipe.pdf"


def clean_markdown_line(line: str) -> str:
    line = re.sub(r"`([^`]+)`", r"\1", line.strip())
    if line.startswith("# "):
        return line[2:].upper()
    if line.startswith("## "):
        return f"\n{line[3:].upper()}"
    if line.startswith("- "):
        return f"  - {line[2:]}"
    return line


def build_manual_lines() -> list[str]:
    lines = [
        "SannyGold - Manual rapido da equipe",
        "Use este material para treinar a rotina diaria do sistema.",
        "",
    ]
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        cleaned = clean_markdown_line(raw)
        if cleaned:
            lines.append(cleaned)
        else:
            lines.append("")
    return lines


def build_pdf() -> Path:
    from app.main import build_simple_text_pdf

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(build_simple_text_pdf("SannyGold - Manual rapido da equipe", build_manual_lines()))
    return OUTPUT


if __name__ == "__main__":
    print(build_pdf())
