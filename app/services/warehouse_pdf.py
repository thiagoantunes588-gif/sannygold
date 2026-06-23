from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import io
from pathlib import Path
import re
import unicodedata
import urllib.parse
import urllib.request

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#091527")
NAVY_SOFT = colors.HexColor("#16243a")
GOLD = colors.HexColor("#c59a35")
GOLD_SOFT = colors.HexColor("#f7edd1")
TEXT = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#55616f")
LIGHT_BG = colors.HexColor("#f7f9fb")
LINE = colors.HexColor("#d9e1ea")
GREEN = colors.HexColor("#1f7a4d")
GREEN_BG = colors.HexColor("#e6f3ec")
ORANGE = colors.HexColor("#a85f00")
ORANGE_BG = colors.HexColor("#fff2d8")
RED = colors.HexColor("#b3261e")
RED_BG = colors.HexColor("#fde7e4")
GRAY = colors.HexColor("#667085")
GRAY_BG = colors.HexColor("#edf0f3")

EMPTY_VALUES = {"", "n/d", "nd", "none", "null", "undefined", "-", "--", "nan"}
LOWERCASE_CONNECTORS = {"a", "as", "com", "da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos", "o", "os", "para", "por"}
UPPERCASE_TERMS = {"epi", "pdf", "cpf", "cnpj", "id", "qr", "usb"}
STATUS_COLORS = {
    "normal": {"label": "NORMAL", "text": GREEN, "bg": GREEN_BG, "priority": 2},
    "baixo": {"label": "BAIXO", "text": ORANGE, "bg": ORANGE_BG, "priority": 1},
    "zerado": {"label": "ZERADO", "text": RED, "bg": RED_BG, "priority": 0},
    "inativo": {"label": "INATIVO", "text": GRAY, "bg": GRAY_BG, "priority": 3},
}

_FONTS_REGISTERED = False


@dataclass(frozen=True)
class WarehouseStockInfo:
    status: str
    label: str
    priority: int
    text_color: colors.Color
    background_color: colors.Color
    reorder_quantity: float | None
    reorder_label: str


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, footer_text: str = "", generated_label: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.footer_text = footer_text
        self.generated_label = generated_label
        self.draw_page_background()

    def draw_page_background(self) -> None:
        self.saveState()
        width, height = A4
        self.setFillColor(colors.white)
        self.rect(0, 0, width, height, stroke=0, fill=1)
        self.restoreState()

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
        self.draw_page_background()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count: int) -> None:
        self.saveState()
        width, _height = A4
        self.setStrokeColor(LINE)
        self.setLineWidth(0.4)
        self.line(1.4 * cm, 1.28 * cm, width - 1.4 * cm, 1.28 * cm)
        self.setFont("SannySans", 8)
        self.setFillColor(MUTED)
        self.drawString(1.4 * cm, 0.86 * cm, self.footer_text)
        self.drawCentredString(width / 2, 0.86 * cm, self.generated_label)
        self.drawRightString(width - 1.4 * cm, 0.86 * cm, f"Página {self._pageNumber} de {page_count}")
        self.restoreState()


def register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    import reportlab

    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    fonts = {
        "SannySans": font_dir / "Vera.ttf",
        "SannySans-Bold": font_dir / "VeraBd.ttf",
        "SannySans-Italic": font_dir / "VeraIt.ttf",
        "SannySans-BoldItalic": font_dir / "VeraBI.ttf",
    }
    for name, path in fonts.items():
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "SannySans",
        normal="SannySans",
        bold="SannySans-Bold",
        italic="SannySans-Italic",
        boldItalic="SannySans-BoldItalic",
    )
    _FONTS_REGISTERED = True


def is_meaningful(value) -> bool:
    normalized = clean_display_text(value).lower()
    return normalized not in EMPTY_VALUES


def clean_display_text(value, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else fallback


def normalize_sort_text(value) -> str:
    normalized = unicodedata.normalize("NFD", clean_display_text(value).lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def display_capitalized(value, fallback: str = "") -> str:
    text = clean_display_text(value, fallback)
    if not text:
        return fallback
    tokens = []
    for index, token in enumerate(text.split(" ")):
        token_lower = token.lower()
        if index > 0 and token_lower in LOWERCASE_CONNECTORS:
            tokens.append(token_lower)
        elif token_lower in UPPERCASE_TERMS:
            tokens.append(token.upper())
        elif token.isupper() and len(token) <= 5:
            tokens.append(token)
        elif any(ch.isdigit() for ch in token):
            tokens.append(token)
        else:
            tokens.append(token[:1].upper() + token[1:])
    return " ".join(tokens)


def parse_decimal(value, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.strip().replace(".", "").replace(",", ".") if "," in value else value.strip()
        return float(value)
    except (TypeError, ValueError):
        return fallback


def format_number_br(value) -> str:
    number = round(parse_decimal(value), 2)
    if number == int(number):
        return str(int(number))
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_quantity(value, unit: str | None = "") -> str:
    unit_text = clean_display_text(unit)
    number = format_number_br(value)
    return f"{number} {unit_text}".strip()


def format_datetime_br(value: datetime | str | None = None) -> str:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return clean_display_text(value)
    else:
        dt = datetime.now()
    return dt.strftime("%d/%m/%Y às %H:%M")


def format_date_br(value: str | None) -> str:
    if not is_meaningful(value):
        return ""
    text = clean_display_text(value)
    try:
        return datetime.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def warehouse_stock_info(item: dict) -> WarehouseStockInfo:
    item_status = clean_display_text(item.get("status"), "ativo").lower()
    quantity = parse_decimal(item.get("quantity_current"))
    minimum = parse_decimal(item.get("stock_minimum"))
    if item_status == "inativo":
        status = "inativo"
    elif quantity <= 0:
        status = "zerado"
    elif quantity <= minimum:
        status = "baixo"
    else:
        status = "normal"
    status_meta = STATUS_COLORS[status]
    reorder_quantity = None
    reorder_label = ""
    if status in {"zerado", "baixo"}:
        missing = max(minimum - quantity, 0)
        if missing > 0:
            reorder_quantity = round(missing, 2)
            reorder_label = f"Repor {format_number_br(reorder_quantity)}"
        else:
            reorder_label = "Repor acima do mínimo"
    return WarehouseStockInfo(
        status=status,
        label=str(status_meta["label"]),
        priority=int(status_meta["priority"]),
        text_color=status_meta["text"],
        background_color=status_meta["bg"],
        reorder_quantity=reorder_quantity,
        reorder_label=reorder_label,
    )


def sorted_warehouse_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: (warehouse_stock_info(item).priority, normalize_sort_text(item.get("name"))))


def warehouse_pdf_filename(generated_at: datetime | None = None, *, prefix: str = "sannygold-almoxarifado") -> str:
    generated_at = generated_at or datetime.now()
    return f"{prefix}-{generated_at.strftime('%Y-%m-%d_%H-%M')}.pdf"


def styles():
    register_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "SannyTitle",
            parent=base["Title"],
            fontName="SannySans-Bold",
            fontSize=20,
            leading=23,
            textColor=NAVY,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "SannySubtitle",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=10,
            leading=13,
            textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "SannySection",
            parent=base["Heading2"],
            fontName="SannySans-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "SannyBody",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=9,
            leading=12,
            textColor=TEXT,
        ),
        "small": ParagraphStyle(
            "SannySmall",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=7.8,
            leading=10,
            textColor=MUTED,
        ),
        "small_right": ParagraphStyle(
            "SannySmallRight",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
            textColor=MUTED,
        ),
        "table_header": ParagraphStyle(
            "SannyTableHeader",
            parent=base["BodyText"],
            fontName="SannySans-Bold",
            fontSize=7.6,
            leading=9,
            alignment=TA_LEFT,
            textColor=colors.white,
        ),
        "table": ParagraphStyle(
            "SannyTable",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=7.8,
            leading=9.8,
            textColor=TEXT,
            splitLongWords=False,
            wordWrap="CJK",
        ),
        "table_bold": ParagraphStyle(
            "SannyTableBold",
            parent=base["BodyText"],
            fontName="SannySans-Bold",
            fontSize=8.2,
            leading=10,
            textColor=NAVY,
            splitLongWords=False,
            wordWrap="CJK",
        ),
        "badge": ParagraphStyle(
            "SannyBadge",
            parent=base["BodyText"],
            fontName="SannySans-Bold",
            fontSize=7.2,
            leading=9,
            alignment=TA_CENTER,
        ),
        "card_value": ParagraphStyle(
            "SannyCardValue",
            parent=base["BodyText"],
            fontName="SannySans-Bold",
            fontSize=15,
            leading=17,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "card_label": ParagraphStyle(
            "SannyCardLabel",
            parent=base["BodyText"],
            fontName="SannySans",
            fontSize=7.8,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def rich_paragraph(parts: list[str], style) -> Paragraph:
    return Paragraph("<br/>".join(part for part in parts if part), style)


def link_markup(url: str, label: str | None = None) -> str:
    safe_url = escape(url, quote=True)
    safe_label = escape(label or url)
    return f'<a href="{safe_url}" color="#15879b">{safe_label}</a>'


def local_image_path(value: str, uploads_dir: Path | None) -> Path | None:
    text = clean_display_text(value)
    if not text:
        return None
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return None
    if text.startswith("/uploads/assets/") and uploads_dir:
        candidate = uploads_dir / "assets" / Path(text).name
    else:
        candidate = Path(text).expanduser()
    try:
        return candidate if candidate.exists() and candidate.is_file() else None
    except OSError:
        return None


def image_flowable(value: str, uploads_dir: Path | None, *, max_width: float = 28, max_height: float = 28) -> Flowable | None:
    text = clean_display_text(value)
    if not text:
        return None
    try:
        path = local_image_path(text, uploads_dir)
        source = str(path) if path else None
        if source is None and urllib.parse.urlparse(text).scheme in {"http", "https"}:
            with urllib.request.urlopen(text, timeout=2) as response:
                source = io.BytesIO(response.read(512_000))
        if source is None:
            return None
        reader = ImageReader(source)
        width, height = reader.getSize()
        scale = min(max_width / width, max_height / height, 1)
        return Image(source, width=width * scale, height=height * scale)
    except Exception:
        return None


def logo_flowable(logo_path: Path | None) -> Flowable | Paragraph:
    if logo_path and logo_path.exists():
        try:
            reader = ImageReader(str(logo_path))
            width, height = reader.getSize()
            target_width = 38 * mm
            target_height = min(22 * mm, target_width * height / width)
            return Image(str(logo_path), width=target_width, height=target_height)
        except Exception:
            pass
    return Paragraph("<b>SannyGold</b>", ParagraphStyle("LogoText", fontName="SannySans-Bold", fontSize=18, textColor=NAVY))


def build_header(
    *,
    title: str,
    subtitle: str,
    generated_at: datetime,
    user: dict | None,
    logo_path: Path | None,
    report_id: str,
    deposit_label: str,
) -> list[Flowable]:
    st = styles()
    user_name = clean_display_text((user or {}).get("nome") or (user or {}).get("email"))
    meta = [
        f"<b>Gerado:</b> {escape(format_datetime_br(generated_at))}",
        f"<b>Responsável:</b> {escape(user_name)}" if user_name else "",
        f"<b>Unidade/depósito:</b> {escape(deposit_label)}" if deposit_label else "",
        f"<b>ID:</b> {escape(report_id)}" if report_id else "",
    ]
    right = [
        Paragraph(escape(title), st["title"]),
        Paragraph(escape(subtitle), st["subtitle"]),
        Paragraph("<br/>".join(item for item in meta if item), st["small_right"]),
    ]
    table = Table(
        [[logo_flowable(logo_path), right]],
        colWidths=[4.2 * cm, 12.1 * cm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ],
    )
    return [table, HRFlowable(width="100%", color=GOLD, thickness=1.1, spaceBefore=2, spaceAfter=10)]


def summary_counts(items: list[dict]) -> dict[str, int]:
    statuses = [warehouse_stock_info(item).status for item in items]
    return {
        "total": len(items),
        "normal": statuses.count("normal"),
        "low": statuses.count("baixo"),
        "zero": statuses.count("zerado"),
        "inactive": statuses.count("inativo"),
        "consumables": sum(1 for item in items if clean_display_text(item.get("item_kind")).lower() == "consumivel"),
        "accessories": sum(1 for item in items if clean_display_text(item.get("item_kind")).lower() == "acessorio_operacional"),
    }


def build_summary_cards(items: list[dict]) -> Flowable:
    st = styles()
    counts = summary_counts(items)
    cards = [
        ("Total", counts["total"], NAVY, colors.white),
        ("Normal", counts["normal"], GREEN, GREEN_BG),
        ("Baixo", counts["low"], ORANGE, ORANGE_BG),
        ("Zerado", counts["zero"], RED, RED_BG),
        ("Consumíveis", counts["consumables"], NAVY, LIGHT_BG),
        ("Acessórios", counts["accessories"], NAVY, LIGHT_BG),
    ]
    row = []
    for label, value, color, bg in cards:
        value_style = ParagraphStyle(f"CardValue{label}", parent=st["card_value"], textColor=color)
        row.append([Paragraph(str(value), value_style), Paragraph(label, st["card_label"])])
    table = Table(
        [row],
        colWidths=[2.72 * cm] * 6,
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.4, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ],
    )
    for index, (_label, _value, _color, bg) in enumerate(cards):
        table.setStyle(TableStyle([("BACKGROUND", (index, 0), (index, 0), bg)]))
    return table


def attention_items(items: list[dict]) -> list[dict]:
    return [item for item in sorted_warehouse_items(items) if warehouse_stock_info(item).status in {"baixo", "zerado"}]


def item_detail_markup(item: dict, uploads_dir: Path | None = None) -> list[str]:
    details: list[str] = []
    pairs = [
        ("Aplicação", item.get("description") or item.get("sector")),
        ("Observações", item.get("notes")),
        ("Onde comprar", item.get("purchase_location")),
        ("Código", item.get("id")),
        ("Marca", item.get("brand")),
        ("Modelo", item.get("model")),
        ("Última atualização", format_datetime_br(item.get("updated_at")) if is_meaningful(item.get("updated_at")) else ""),
    ]
    for label, value in pairs:
        if is_meaningful(value):
            details.append(f"<b>{escape(label)}:</b> {escape(display_capitalized(value) if label in {'Aplicação', 'Onde comprar'} else clean_display_text(value))}")
    if is_meaningful(item.get("purchase_link")):
        details.append(f"<b>Link:</b> {link_markup(clean_display_text(item.get('purchase_link')), 'abrir compra')}")
    if is_meaningful(item.get("photo_url")) and image_flowable(clean_display_text(item.get("photo_url")), uploads_dir) is None:
        details.append("<b>Foto:</b> não acessível no momento")
    return details


def build_attention_section(items: list[dict], uploads_dir: Path | None) -> list[Flowable]:
    st = styles()
    flowables: list[Flowable] = [Paragraph("Materiais que precisam de atenção", st["section"])]
    critical = attention_items(items)
    if not critical:
        flowables.append(Paragraph("Nenhum material necessita de reposição no momento.", st["body"]))
        flowables.append(Spacer(1, 8))
        return flowables
    for item in critical:
        info = warehouse_stock_info(item)
        parts = [
            f"<b>{escape(clean_display_text(item.get('name'), 'Material sem nome'))}</b>",
            f"{escape(format_quantity(item.get('quantity_current'), item.get('unit')))} atual / mínimo {escape(format_quantity(item.get('stock_minimum'), item.get('unit')))}",
        ]
        if info.reorder_label:
            parts.append(escape(info.reorder_label + (f" {clean_display_text(item.get('unit'))}" if info.reorder_quantity is not None else "")))
        details = []
        for label, value in (
            ("Local", item.get("storage_location")),
            ("Categoria", item.get("category")),
            ("Onde comprar", item.get("purchase_location")),
        ):
            if is_meaningful(value):
                details.append(f"<b>{escape(label)}:</b> {escape(display_capitalized(value))}")
        if is_meaningful(item.get("purchase_link")):
            details.append(f"<b>Compra:</b> {link_markup(clean_display_text(item.get('purchase_link')), 'abrir link')}")
        row = [
            Paragraph(info.label, ParagraphStyle("AttentionBadge", parent=st["badge"], textColor=info.text_color)),
            rich_paragraph(parts, st["table"]),
            rich_paragraph(details, st["small"]),
        ]
        card = Table(
            [row],
            colWidths=[2.2 * cm, 5.8 * cm, 8.3 * cm],
            style=[
                ("BACKGROUND", (0, 0), (0, 0), info.background_color),
                ("BACKGROUND", (1, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ],
        )
        flowables.append(KeepTogether([card, Spacer(1, 5)]))
    flowables.append(Spacer(1, 6))
    return flowables


def material_name_cell(item: dict, uploads_dir: Path | None):
    st = styles()
    title = Paragraph(escape(clean_display_text(item.get("name"), "Material sem nome")), st["table_bold"])
    details = item_detail_markup(item, uploads_dir)
    content: list[Flowable] = [title]
    if details:
        content.append(Paragraph("<br/>".join(details), st["small"]))
    thumb = image_flowable(clean_display_text(item.get("photo_url")), uploads_dir)
    if not thumb:
        return content
    return Table(
        [[thumb, content]],
        colWidths=[1.0 * cm, 4.0 * cm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ],
    )


def build_materials_table(items: list[dict], uploads_dir: Path | None) -> Flowable:
    st = styles()
    headers = ["Material", "Categoria", "Aplicação", "Quantidade", "Mínimo", "Un.", "Status", "Local"]
    rows = [[Paragraph(header, st["table_header"]) for header in headers]]
    row_statuses: list[WarehouseStockInfo] = []
    for item in sorted_warehouse_items(items):
        info = warehouse_stock_info(item)
        row_statuses.append(info)
        status_style = ParagraphStyle(f"Status{info.status}{len(row_statuses)}", parent=st["badge"], textColor=info.text_color)
        rows.append(
            [
                material_name_cell(item, uploads_dir),
                Paragraph(escape(display_capitalized(item.get("category"), "Geral")), st["table"]),
                Paragraph(escape(display_capitalized(item.get("description") or item.get("sector"), "")), st["table"]),
                Paragraph(escape(format_quantity(item.get("quantity_current"))), st["table"]),
                Paragraph(escape(format_quantity(item.get("stock_minimum"))), st["table"]),
                Paragraph(escape(clean_display_text(item.get("unit"), "un")), st["table"]),
                Paragraph(info.label, status_style),
                Paragraph(escape(display_capitalized(item.get("storage_location"), "")), st["table"]),
            ]
        )
    table = LongTable(
        rows,
        repeatRows=1,
        colWidths=[5.2 * cm, 2.2 * cm, 2.4 * cm, 1.55 * cm, 1.35 * cm, 0.85 * cm, 1.55 * cm, 2.0 * cm],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ],
        splitByRow=True,
    )
    for row_index, info in enumerate(row_statuses, start=1):
        table.setStyle(TableStyle([("BACKGROUND", (6, row_index), (6, row_index), info.background_color)]))
        if row_index % 2 == 0:
            table.setStyle(TableStyle([("BACKGROUND", (0, row_index), (5, row_index), LIGHT_BG), ("BACKGROUND", (7, row_index), (7, row_index), LIGHT_BG)]))
    return table


def deposit_label_for_items(items: list[dict]) -> str:
    deposits = sorted({clean_display_text(item.get("deposit")) for item in items if is_meaningful(item.get("deposit"))})
    if len(deposits) == 1:
        return deposits[0]
    if len(deposits) > 1:
        return "Múltiplos depósitos"
    return "SannyGold"


def build_warehouse_pdf_bytes(
    items: list[dict],
    *,
    generated_at: datetime | None = None,
    user: dict | None = None,
    logo_path: Path | None = None,
    uploads_dir: Path | None = None,
    report_id: str | None = None,
    title: str = "Relatório do Almoxarifado",
    subtitle: str = "Controle de materiais e estoque",
    empty_message: str = "Nenhum material encontrado para os filtros selecionados.",
) -> bytes:
    register_fonts()
    generated_at = generated_at or datetime.now()
    report_id = report_id or f"ALM-{generated_at.strftime('%Y%m%d-%H%M')}"
    ordered_items = sorted_warehouse_items(items)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.25 * cm,
        bottomMargin=1.65 * cm,
        title=title,
        author="SannyGold",
        subject=subtitle,
        pageCompression=0,
    )
    st = styles()
    story: list[Flowable] = []
    story.extend(
        build_header(
            title=title,
            subtitle=subtitle,
            generated_at=generated_at,
            user=user,
            logo_path=logo_path,
            report_id=report_id,
            deposit_label=deposit_label_for_items(ordered_items),
        )
    )
    story.append(Paragraph("Resumo executivo", st["section"]))
    story.append(build_summary_cards(ordered_items))
    story.append(Spacer(1, 9))
    story.extend(build_attention_section(ordered_items, uploads_dir))
    story.append(Paragraph("Lista completa de materiais", st["section"]))
    if ordered_items:
        story.append(build_materials_table(ordered_items, uploads_dir))
    else:
        story.append(Paragraph(empty_message, st["body"]))
    footer_generated = f"Gerado em {format_datetime_br(generated_at)}"
    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: NumberedCanvas(
            *args,
            footer_text="SannyGold - Controle de Almoxarifado",
            generated_label=footer_generated,
            **kwargs,
        ),
    )
    return buffer.getvalue()
