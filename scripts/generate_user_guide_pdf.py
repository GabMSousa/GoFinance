from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "GUIA_USUARIO_GOFINANCE.pdf"
SCREEN_DIR = ROOT / "tmp" / "pdfs" / "screens"
PAGE = landscape(A4)
W, H = PAGE


def screenshot(path: Path, max_width=W - 24 * mm, max_height=112 * mm):
    reader = ImageReader(str(path))
    width, height = reader.getSize()
    scale = min(max_width / width, max_height / height)
    image = Image(str(path), width=width * scale, height=height * scale)
    image.hAlign = "CENTER"
    return image


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=28, leading=34, textColor=colors.HexColor("#eef1f6"), alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="CoverText", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=12, leading=18, textColor=colors.HexColor("#aab1c2"), alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="SectionTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=18, leading=22, textColor=colors.HexColor("#14213d"), spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Body", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.5, leading=14, textColor=colors.HexColor("#334155"), spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="Caption", parent=styles["BodyText"], fontName="Helvetica-Oblique",
    fontSize=8, leading=11, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER,
    spaceBefore=5, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Small", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"),
))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbe3ee"))
    canvas.line(14 * mm, 12 * mm, W - 14 * mm, 12 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(14 * mm, 7 * mm, "GoFinance - Guia do usuário")
    canvas.drawRightString(W - 14 * mm, 7 * mm, f"Página {doc.page}")
    canvas.restoreState()


def bullets(items):
    return [Paragraph(f"• {item}", styles["Body"]) for item in items]


story = []

# Cover
cover_content = [
    Paragraph("GoFinance", styles["CoverTitle"]),
    Spacer(1, 10 * mm),
    Paragraph("Guia visual de instalação e uso", styles["CoverText"]),
    Spacer(1, 8 * mm),
    Paragraph("Login, painel, compras, VR, cartão, salário, perfil, configurações e administração.", styles["CoverText"]),
]
cover = Table([[cover_content]], colWidths=[W - 56 * mm])
cover.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#101827")),
    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
    ("LEFTPADDING", (0, 0), (-1, -1), 18 * mm),
    ("RIGHTPADDING", (0, 0), (-1, -1), 18 * mm),
    ("TOPPADDING", (0, 0), (-1, -1), 24 * mm),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 24 * mm),
]))
story.extend([Spacer(1, 30 * mm), cover, Spacer(1, 18 * mm), Paragraph("Versão preparada para uso local e corporativo", styles["Caption"]), PageBreak()])


def add_screen(title, text, filename, caption):
    story.append(Paragraph(title, styles["SectionTitle"]))
    story.append(Paragraph(text, styles["Body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(screenshot(SCREEN_DIR / filename))
    story.append(Paragraph(caption, styles["Caption"]))
    story.append(PageBreak())


add_screen(
    "1. Painel inicial",
    "O painel mostra o mês selecionado, o saldo, receitas, despesas, valores a receber e o VR. Use as setas para consultar outros meses. A área de movimentações concentra compras, parcelas e contas do mês.",
    "01-dashboard.png",
    "Figura 1 - Visão geral do painel e dos indicadores financeiros.",
)
add_screen(
    "2. Adicionar uma movimentação",
    "Use + Adicionar para escolher Compra, Receita ou Investimento. Para compras, selecione Pix, débito, dinheiro, boleto, cartão ou Vale Refeição. Em cartão de crédito, informe o total e as parcelas; em VR, informe o valor consumido no benefício.",
    "06-adicionar-modal.png",
    "Figura 2 - Menu de ação rápida para novos lançamentos.",
)
add_screen(
    "3. Investimentos",
    "A tela de investimentos separa aportes, resgates e ajustes das despesas de consumo. O saldo aplicado, as posições e as movimentações são filtrados pelo mês selecionado.",
    "02-investimentos.png",
    "Figura 3 - Área de investimentos e radar de indicadores.",
)
add_screen(
    "4. Configurações pessoais",
    "Configure salário integral ou dividido, dias de recebimento, crédito mensal do VR, dia do crédito, vencimento do cartão, banco principal e saldo inicial. Cada usuário ajusta apenas os próprios dados.",
    "03-configuracoes.png",
    "Figura 4 - Configurações financeiras e aparência.",
)
add_screen(
    "5. Meu perfil",
    "Em Meu perfil, altere nome, e-mail, foto e senha. A troca de senha pelo perfil não exige a senha anterior porque a sessão já está autenticada.",
    "04-perfil.png",
    "Figura 5 - Dados pessoais, regras financeiras e alteração de senha.",
)
add_screen(
    "6. Administração de acessos",
    "A aba Admin é exclusiva para administradores. Cadastre novos usuários, consulte os acessos, ative ou desative contas e use Resetar senha quando necessário. As regras financeiras não são preenchidas pelo administrador.",
    "05-admin.png",
    "Figura 6 - Administração de usuários do GoFinance.",
)

story.append(Paragraph("7. Instalação rápida", styles["SectionTitle"]))
story.append(Paragraph("O banco oficial é MySQL/MariaDB. Para Windows PowerShell:", styles["Body"]))
story.extend(bullets([
    "cd caminho\\para\\GoFinance",
    "py -3 -m venv .venv",
    ".\\.venv\\Scripts\\Activate.ps1",
    "pip install -r requirements.txt",
    "python manage.py migrate",
    "python manage.py seed_initial_data",
    "python manage.py runserver 0.0.0.0:8002",
]))
story.append(Paragraph("Abra http://127.0.0.1:8002/login/. Para Linux/macOS, use python3, source .venv/bin/activate e a porta desejada. Para uso corporativo, use Docker Compose ou Gunicorn + Nginx + HTTPS conforme GUIA_INSTALACAO.md.", styles["Body"]))
story.append(Spacer(1, 5 * mm))
table = Table([
    [Paragraph("Arquivo", styles["Small"]), Paragraph("Finalidade", styles["Small"])],
    [Paragraph("README.md", styles["Small"]), Paragraph("Resumo de instalação, operação e manutenção", styles["Small"])],
    [Paragraph("GUIA_INSTALACAO.md", styles["Small"]), Paragraph("Instalação local, Docker, Linux, Windows Server e operação corporativa", styles["Small"])],
    [Paragraph("MANUAL_USUARIO.md", styles["Small"]), Paragraph("Uso diário e regras funcionais", styles["Small"])],
], colWidths=[55 * mm, 190 * mm])
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
    ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#cbd5e1")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
story.extend([table, Spacer(1, 7 * mm), Paragraph("Faça backup do banco MySQL/MariaDB e da pasta media/ antes de atualizações. Nunca versionar .env, senhas ou dumps com dados reais.", styles["Body"])])

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc = SimpleDocTemplate(str(OUTPUT), pagesize=PAGE, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=18 * mm, title="Guia do usuário GoFinance")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
