from __future__ import annotations

from pathlib import Path
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "sannygold-apresentacao-sistema.pdf"
LOGO = ROOT / "app" / "static" / "sannygold-logo.jpg"

PAGE_W, PAGE_H = landscape(A4)
GOLD = colors.HexColor("#b98121")
GOLD_SOFT = colors.HexColor("#f3d88b")
AQUA = colors.HexColor("#35bfd2")
INK = colors.HexColor("#1d1a17")
MUTED = colors.HexColor("#6a6258")
PANEL = colors.HexColor("#fffaf1")
LINE = colors.HexColor("#ead8b8")
LIGHT = colors.HexColor("#f8f5ef")
DANGER = colors.HexColor("#a33232")
SUCCESS = colors.HexColor("#207a56")


def draw_rounded_rect(c: canvas.Canvas, x: float, y: float, w: float, h: float, fill, stroke=LINE, radius=12):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.roundRect(x, y, w, h, radius, stroke=1, fill=1)


def draw_text(c: canvas.Canvas, text: str, x: float, y: float, size=12, color=INK, bold=False, max_width_chars=80, leading=None):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    leading = leading or size * 1.35
    lines = []
    for paragraph in str(text).split("\n"):
        wrapped = textwrap.wrap(paragraph, width=max_width_chars) or [""]
        lines.extend(wrapped)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_title(c: canvas.Canvas, title: str, subtitle: str, slide_no: int):
    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(LIGHT)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(GOLD_SOFT)
    c.circle(PAGE_W - 80, PAGE_H - 50, 155, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.2, 0.75, 0.82, alpha=0.18))
    c.circle(80, 40, 130, fill=1, stroke=0)
    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), 48, PAGE_H - 104, width=56, height=56, preserveAspectRatio=True, mask="auto")
    draw_text(c, "SANNY GOLD", 116, PAGE_H - 70, size=16, color=GOLD, bold=True, max_width_chars=20)
    draw_text(c, "Banheiros de Luxo", 116, PAGE_H - 91, size=9, color=MUTED, max_width_chars=30)
    draw_text(c, title, 48, PAGE_H - 165, size=31, color=INK, bold=True, max_width_chars=34, leading=35)
    draw_text(c, subtitle, 52, PAGE_H - 230, size=14, color=MUTED, max_width_chars=78, leading=20)
    draw_footer(c, slide_no)


def draw_footer(c: canvas.Canvas, slide_no: int):
    c.setStrokeColor(LINE)
    c.line(48, 34, PAGE_W - 48, 34)
    draw_text(c, "Sistema SannyGold - apresentação operacional", 48, 18, size=8, color=MUTED, max_width_chars=80)
    draw_text(c, f"{slide_no:02d}", PAGE_W - 68, 18, size=8, color=MUTED, bold=True, max_width_chars=4)


def draw_header(c: canvas.Canvas, section: str, title: str, slide_no: int):
    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(LIGHT)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    draw_text(c, section.upper(), 48, PAGE_H - 54, size=8, color=GOLD, bold=True, max_width_chars=40)
    draw_text(c, title, 48, PAGE_H - 88, size=25, color=INK, bold=True, max_width_chars=42, leading=30)
    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), PAGE_W - 94, PAGE_H - 82, width=44, height=44, preserveAspectRatio=True, mask="auto")
    draw_footer(c, slide_no)


def draw_cards(c: canvas.Canvas, cards: list[tuple[str, str]], x=48, y=None, cols=2, card_w=None, card_h=88):
    y = y if y is not None else PAGE_H - 158
    gap = 18
    card_w = card_w or ((PAGE_W - x * 2 - gap * (cols - 1)) / cols)
    for index, (title, body) in enumerate(cards):
        col = index % cols
        row = index // cols
        cx = x + col * (card_w + gap)
        cy = y - row * (card_h + gap)
        draw_rounded_rect(c, cx, cy - card_h, card_w, card_h, PANEL)
        draw_text(c, title, cx + 16, cy - 24, size=12, color=GOLD, bold=True, max_width_chars=36)
        draw_text(c, body, cx + 16, cy - 46, size=9.5, color=MUTED, max_width_chars=52, leading=13)


def bullet_slide(c: canvas.Canvas, section: str, title: str, bullets: list[str], slide_no: int, accent=AQUA):
    draw_header(c, section, title, slide_no)
    y = PAGE_H - 150
    for bullet in bullets:
        c.setFillColor(accent)
        c.circle(60, y + 4, 4, fill=1, stroke=0)
        y = draw_text(c, bullet, 78, y, size=13, color=INK, max_width_chars=88, leading=18) - 10


def flow_slide(c: canvas.Canvas, slide_no: int):
    draw_header(c, "Fluxo diário", "Como a operação acontece no sistema", slide_no)
    steps = [
        ("1", "Cadastrar", "Clientes, eventos, frota, equipamentos e materiais."),
        ("2", "Validar", "Checar pendências antes da rota e evitar erros de campo."),
        ("3", "Operar", "Gerar rota, abrir Maps e confirmar chegada, execução e retorno."),
        ("4", "Fechar", "Registrar histórico, financeiro, backup e fechamento do dia."),
    ]
    x = 58
    y = PAGE_H - 190
    w = 170
    for index, (num, title, body) in enumerate(steps):
        cx = x + index * 192
        draw_rounded_rect(c, cx, y - 130, w, 130, PANEL)
        c.setFillColor(GOLD)
        c.circle(cx + 28, y - 28, 16, fill=1, stroke=0)
        draw_text(c, num, cx + 23, y - 34, size=13, color=colors.white, bold=True, max_width_chars=2)
        draw_text(c, title, cx + 16, y - 64, size=14, color=INK, bold=True, max_width_chars=20)
        draw_text(c, body, cx + 16, y - 88, size=9.7, color=MUTED, max_width_chars=26, leading=13)
        if index < len(steps) - 1:
            c.setStrokeColor(AQUA)
            c.setLineWidth(2)
            c.line(cx + w + 8, y - 64, cx + w + 28, y - 64)
            c.line(cx + w + 28, y - 64, cx + w + 20, y - 58)
            c.line(cx + w + 28, y - 64, cx + w + 20, y - 70)


def finance_slide(c: canvas.Canvas, slide_no: int):
    draw_header(c, "Financeiro", "Controle financeiro com segurança e clareza", slide_no)
    cards = [
        ("Resumo por período", "Visão diária, semanal, mensal, geral e personalizada por datas."),
        ("Contas a receber", "Separação entre vencidas, vencem em breve e pagas."),
        ("Fluxo de caixa", "Entradas, saídas, saldo realizado e saldo previsto."),
        ("Fechamento mensal", "Snapshot travado, PDF do fechamento e permissão específica."),
        ("DRE por evento", "Receita, custo, lucro, margem e alertas de rentabilidade."),
        ("Permissões", "Ver, editar, registrar pagamento, fechar mês e exportar."),
    ]
    draw_cards(c, cards, cols=3, card_h=92)


def metrics_slide(c: canvas.Canvas, slide_no: int):
    draw_header(c, "Valor para a empresa", "O que o sistema ajuda a controlar", slide_no)
    metrics = [
        ("Menos retrabalho", "Validação antes da rota e cadastros com vínculo claro."),
        ("Mais rastreabilidade", "Histórico por cliente, evento, equipamento e usuário."),
        ("Financeiro mais firme", "Recebimentos, inadimplência, fluxo e fechamento mensal."),
        ("Operação móvel", "Modo rápido, busca fixa, botões grandes e acesso ao Maps."),
    ]
    draw_cards(c, metrics, cols=2, card_h=112)
    c.setFillColor(SUCCESS)
    c.rect(62, 90, 250, 8, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(326, 90, 190, 8, fill=1, stroke=0)
    c.setFillColor(AQUA)
    c.rect(530, 90, 220, 8, fill=1, stroke=0)
    draw_text(c, "Operação - Financeiro - Controle interno", 62, 68, size=11, color=MUTED, max_width_chars=80)


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT), pagesize=landscape(A4))
    slide = 1

    draw_title(
        c,
        "Apresentação do Sistema SannyGold",
        "Painel integrado para operação, almoxarifado, frota, eventos, financeiro e controle de acesso.",
        slide,
    )
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Visão geral",
        "Um sistema para a rotina real da empresa",
        [
            "Abre em modo visitante com uma visão pública segura.",
            "Libera módulos internos após login com permissões por função.",
            "Centraliza eventos, clientes, frota, equipamentos, almoxarifado e financeiro.",
            "Prioriza velocidade de operação no celular e clareza no desktop.",
        ],
        slide,
    )
    c.showPage()
    slide += 1

    flow_slide(c, slide)
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Módulos",
        "Clientes, eventos, frota e equipamentos",
        [
            "Clientes com dados operacionais, nota fiscal, valor de serviço e vínculo de equipamento.",
            "Eventos com período, checklist, recorrência, financeiro e vínculos com clientes/veículos.",
            "Frota e equipamentos separados, com status, disponibilidade e manutenção.",
            "Histórico detalhado por cliente com eventos, rotas, confirmações e resultado acumulado.",
        ],
        slide,
    )
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Almoxarifado",
        "Controle interno de materiais",
        [
            "Módulo separado de eventos, rotas, entregas e clientes.",
            "Lista completa de materiais, cadastro por modal e edição rápida.",
            "Reposição, baixa e ajuste manual com histórico de movimentações.",
            "Campos opcionais para link de compra, local onde comprar e foto do item.",
            "Alertas visuais para estoque baixo e zerado, com exportação em PDF.",
        ],
        slide,
        accent=GOLD,
    )
    c.showPage()
    slide += 1

    finance_slide(c, slide)
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Segurança",
        "Autenticação, RBAC e auditoria",
        [
            "Login com email e senha, senha armazenada com hash seguro.",
            "Modo visitante sem acesso a dados sensíveis ou ações críticas.",
            "Roles iniciais: guest, admin, operacional, financeiro e leitura.",
            "Permissões preparadas por módulo e ação, como clients.edit, finance.view e settings.manage.",
            "Auditoria de ações críticas, backup e fechamento diário.",
        ],
        slide,
        accent=DANGER,
    )
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Usabilidade",
        "Mais rápido para operar no dia a dia",
        [
            "Busca global fixa para encontrar registros sem trocar de aba.",
            "Modo operação rápida para celular, com rota, campo, equipamentos e despacho.",
            "Botões '+ Novo' por módulo e filtros com estado salvo no navegador.",
            "Cards compactos com detalhes recolhidos para reduzir rolagem.",
            "Contas financeiras separadas entre vencidas, vencem em breve e pagas.",
        ],
        slide,
    )
    c.showPage()
    slide += 1

    bullet_slide(
        c,
        "Relatórios",
        "Arquivos para conferência e gestão",
        [
            "PDF e Excel por módulo: clientes, eventos, equipamentos, almoxarifado e financeiro.",
            "PDF de rota e fechamento diário para operação.",
            "PDF de fechamento financeiro mensal com dados travados.",
            "Backup completo com dados operacionais, financeiros, usuários e auditoria.",
        ],
        slide,
        accent=GOLD,
    )
    c.showPage()
    slide += 1

    metrics_slide(c, slide)
    c.showPage()
    slide += 1

    draw_title(
        c,
        "Próximos passos sugeridos",
        "Publicar em ambiente seguro, configurar usuários reais, revisar permissões por função e importar dados iniciais da operação.",
        slide,
    )
    draw_cards(
        c,
        [
            ("1. Publicação", "Hospedar com HTTPS, domínio e variáveis de segurança."),
            ("2. Usuários", "Cadastrar equipe com roles admin, operacional, financeiro e leitura."),
            ("3. Dados iniciais", "Importar clientes, equipamentos, frota e materiais."),
            ("4. Rotina", "Definir processo diário: cadastrar, validar, operar e fechar."),
        ],
        y=PAGE_H - 305,
        cols=4,
        card_h=108,
    )
    c.showPage()

    c.save()
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(path)
