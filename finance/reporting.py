from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.db.models import Sum
from django.utils.timezone import localtime, now
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from .models import CreditCardBill, CreditCardExpense, FixedExpense, Investment
from .services import month_bounds, monthly_summary


INK = colors.HexColor('#171a1f')
MUTED = colors.HexColor('#68707a')
RULE = colors.HexColor('#d7dce2')
FIELD = colors.HexColor('#f4f6f8')
ACCENT = colors.HexColor('#1d6b55')
WARNING = colors.HexColor('#9b6500')


def brl(value):
    value = Decimal(str(value or 0))
    sign = '-' if value < 0 else ''
    return f'{sign}R$ {abs(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def dmy(value):
    return value.strftime('%d/%m/%Y') if value else '-'


def _month_steps(start, end):
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while current <= last:
        yield current.year, current.month
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)


def _range_summary(start, end):
    summaries = [monthly_summary(year, month) for year, month in _month_steps(start, end)]
    if not summaries:
        return monthly_summary(start.year, start.month)
    first = summaries[0]
    last = summaries[-1]
    result = dict(last)
    for key in ('revenues', 'expenses', 'investment_month', 'reimbursements', 'bank_outflow'):
        result[key] = sum((item[key] for item in summaries), Decimal('0.00'))
    result['opening_balance'] = first['opening_balance']
    result['final_balance'] = result['opening_balance'] + result['revenues'] + result['reimbursements'] - result['bank_outflow']
    result['card_invoice'] = sum((item['card_invoice'] for item in summaries), Decimal('0.00'))
    result['third_party_pending'] = last['third_party_pending']
    result['fixed_pending'] = last['fixed_pending']
    result['investment_total'] = last['investment_total']
    return result


class FinancialReportDocTemplate(BaseDocTemplate):
    def __init__(self, stream, **kwargs):
        super().__init__(stream, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=17 * mm, bottomMargin=17 * mm, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        self.addPageTemplates([PageTemplate(id='report', frames=frame, onPage=self._draw_footer)])

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(.5)
        canvas.line(self.leftMargin, 11 * mm, A4[0] - self.rightMargin, 11 * mm)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(self.leftMargin, 7 * mm, 'GoFinance - Relatório financeiro informativo')
        canvas.drawRightString(A4[0] - self.rightMargin, 7 * mm, f'Página {doc.page}')
        canvas.restoreState()


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('report-title', parent=base['Title'], fontName='Helvetica-Bold', fontSize=17, leading=20, textColor=INK, spaceAfter=3),
        'subtitle': ParagraphStyle('report-subtitle', parent=base['Normal'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=MUTED),
        'section': ParagraphStyle('report-section', parent=base['Heading2'], fontName='Helvetica-Bold', fontSize=10.5, leading=13, textColor=INK, spaceBefore=11, spaceAfter=6),
        'body': ParagraphStyle('report-body', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=INK),
        'small': ParagraphStyle('report-small', parent=base['Normal'], fontName='Helvetica', fontSize=7, leading=8.5, textColor=MUTED),
        'right': ParagraphStyle('report-right', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=INK, alignment=TA_RIGHT),
        'right_bold': ParagraphStyle('report-right-bold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=INK, alignment=TA_RIGHT),
        'header': ParagraphStyle('report-header', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white),
    }


def _table(data, widths, header=True, repeat_rows=1, compact=False):
    table = Table(data, colWidths=widths, repeatRows=repeat_rows if header else 0, hAlign='LEFT')
    commands = [
        ('GRID', (0, 0), (-1, -1), .35, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6 if not compact else 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6 if not compact else 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5 if not compact else 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 if not compact else 3),
    ]
    if header:
        commands.extend([('BACKGROUND', (0, 0), (-1, 0), FIELD), ('TEXTCOLOR', (0, 0), (-1, 0), MUTED), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 7.2)])
    table.setStyle(TableStyle(commands))
    return table


def build_financial_pdf(*, user, start, end, report_type, category_id='', payment=''):
    styles = _styles()
    summary = _range_summary(start, end)
    rows = __import__('finance.views', fromlist=['report_rows']).report_rows(start, end, category_id, report_type, payment)
    generated = localtime(now())
    holder = getattr(getattr(user, 'security_profile', None), 'display_name', '') or user.get_username()
    report_id = f'GF-{start:%Y%m%d}-{end:%Y%m%d}'
    output = BytesIO()
    doc = FinancialReportDocTemplate(output, title='GoFinance - Relatório financeiro', author='GoFinance')
    story = []

    story.append(Paragraph('GOFINANCE - RELATÓRIO FINANCEIRO', styles['title']))
    story.append(Paragraph(f'Titular: <b>{holder}</b> &nbsp;&nbsp; Período: <b>{dmy(start)} a {dmy(end)}</b>', styles['subtitle']))
    story.append(Paragraph(f'Emitido em: {generated:%d/%m/%Y %H:%M} &nbsp;&nbsp; ID: {report_id} &nbsp;&nbsp; Tipo: {"Fatura de cartão" if report_type == "bills" else "Extrato financeiro"}', styles['subtitle']))
    story.append(Spacer(1, 5 * mm))

    summary_data = [
        [Paragraph('RESUMO FINANCEIRO', styles['header']), '', '', ''],
        [Paragraph('Saldo inicial', styles['body']), Paragraph(brl(summary['opening_balance']), styles['right']), Paragraph('Receitas no período', styles['body']), Paragraph(brl(summary['revenues']), styles['right'])],
        [Paragraph('Despesas no período', styles['body']), Paragraph(brl(summary['expenses']), styles['right']), Paragraph('Saldo final', styles['body']), Paragraph(brl(summary['final_balance']), styles['right_bold'])],
        [Paragraph('Contas fixas pendentes', styles['body']), Paragraph(brl(summary['fixed_pending']), styles['right']), Paragraph('Fatura do cartão', styles['body']), Paragraph(brl(summary['card_invoice']), styles['right'])],
        [Paragraph('Valores a receber', styles['body']), Paragraph(brl(summary['third_party_pending']), styles['right']), Paragraph('Investimentos no período', styles['body']), Paragraph(brl(summary['investment_month']), styles['right'])],
    ]
    summary_table = Table(summary_data, colWidths=[38 * mm, 34 * mm, 42 * mm, 34 * mm], repeatRows=1)
    summary_table.setStyle(TableStyle([('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), INK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), .35, RULE), ('BACKGROUND', (0, 1), (-1, -1), colors.white), ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story.append(summary_table)

    story.append(Paragraph('MOVIMENTAÇÕES DO PERÍODO', styles['section']))
    movement_data = [[Paragraph(x, styles['small']) for x in ['Data', 'Descrição', 'Categoria', 'Conta / forma', 'Tipo', 'Status', 'Valor']]]
    for row in rows:
        amount = row[4] if row[3] in ('Receita', 'Reembolso') else -abs(row[4])
        movement_data.append([Paragraph(dmy(row[0]), styles['small']), Paragraph(str(row[1]), styles['body']), Paragraph(str(row[2] or '-'), styles['small']), Paragraph(str(row[5] or '-'), styles['small']), Paragraph(str(row[3] or '-'), styles['small']), Paragraph(str(row[10] or '-'), styles['small']), Paragraph(brl(amount), styles['right'])])
    if len(movement_data) == 1:
        movement_data.append([Paragraph('Nenhuma movimentação no período.', styles['small']), '', '', '', '', '', ''])
    story.append(_table(movement_data, [18 * mm, 46 * mm, 27 * mm, 26 * mm, 22 * mm, 19 * mm, 25 * mm], compact=True))

    card_rows = [row for row in rows if row[5] == 'Cartão']
    if report_type == 'bills' or card_rows:
        story.append(Paragraph('SEÇÃO DO CARTÃO DE CRÉDITO', styles['section']))
        bill = CreditCardBill.objects.filter(invoice_month__range=(start.replace(day=1), end.replace(day=1))).order_by('-invoice_month').first()
        bill_status = 'Pago' if bill and bill.is_paid else 'Pendente'
        card_info = [[Paragraph('Período da fatura', styles['body']), Paragraph(f'{dmy(start)} a {dmy(end)}', styles['body']), Paragraph('Valor total', styles['body']), Paragraph(brl(summary['card_invoice']), styles['right_bold'])], [Paragraph('Status', styles['body']), Paragraph(bill_status, styles['body']), Paragraph('Valor pago', styles['body']), Paragraph(brl(summary['card_invoice'] if bill and bill.is_paid else 0), styles['right'])]]
        story.append(_table(card_info, [32 * mm, 45 * mm, 28 * mm, 34 * mm], header=False, compact=True))
        installment_data = [[Paragraph(x, styles['small']) for x in ['Data', 'Compra', 'Categoria', 'Parcela', 'Status', 'Valor']]]
        for row in card_rows:
            installment_data.append([Paragraph(dmy(row[0]), styles['small']), Paragraph(str(row[1]), styles['body']), Paragraph(str(row[2] or '-'), styles['small']), Paragraph(str(row[11] or '-'), styles['small']), Paragraph(str(row[10] or '-'), styles['small']), Paragraph(brl(row[4]), styles['right'])])
        story.append(_table(installment_data, [18 * mm, 52 * mm, 28 * mm, 20 * mm, 22 * mm, 25 * mm], compact=True))

    fixed_items = FixedExpense.objects.select_related('category').filter(active=True).order_by('due_day', 'description')
    if fixed_items.exists():
        story.append(Paragraph('CONTAS FIXAS ATIVAS', styles['section']))
        fixed_data = [[Paragraph(x, styles['small']) for x in ['Conta', 'Categoria', 'Vencimento', 'Valor', 'Status']]]
        for item in fixed_items:
            status = 'Em fatura' if item.included_in_credit_card else ('Pago' if item.paid else 'Pendente')
            fixed_data.append([Paragraph(item.description, styles['body']), Paragraph(str(item.category or '-'), styles['small']), Paragraph(str(item.due_day or '-'), styles['right']), Paragraph(brl(item.amount), styles['right']), Paragraph(status, styles['small'])])
        story.append(_table(fixed_data, [49 * mm, 35 * mm, 24 * mm, 28 * mm, 28 * mm], compact=True))

    categories = list(zip(summary['category_labels'], summary['category_values']))
    if categories:
        story.append(Paragraph('GASTOS POR CATEGORIA', styles['section']))
        total_categories = sum(Decimal(str(value)) for _, value in categories) or Decimal('1')
        category_data = [[Paragraph('Categoria', styles['small']), Paragraph('Valor total', styles['small']), Paragraph('Participação', styles['small'])]]
        for label, value in categories:
            amount = Decimal(str(value))
            category_data.append([Paragraph(label, styles['body']), Paragraph(brl(amount), styles['right']), Paragraph(f'{(amount / total_categories * 100):.1f}%', styles['right'])])
        story.append(_table(category_data, [85 * mm, 38 * mm, 41 * mm], compact=True))

    investments = Investment.objects.filter(date__range=(start, end)).order_by('-date', '-id')
    story.append(Paragraph('INVESTIMENTOS', styles['section']))
    investment_total = investments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    active_recurring = Investment.objects.filter(active=True).exclude(recurrence=Investment.Recurrence.ONE_TIME).count()
    story.append(_table([[Paragraph('Saldo aplicado', styles['body']), Paragraph(brl(summary['investment_total']), styles['right']), Paragraph('Aportes no período', styles['body']), Paragraph(brl(investment_total), styles['right']), Paragraph('Recorrentes ativos', styles['body']), Paragraph(str(active_recurring), styles['right'])]], [32 * mm, 28 * mm, 34 * mm, 28 * mm, 34 * mm, 19 * mm], header=False, compact=True))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('Documento informativo gerado a partir dos registros existentes no GoFinance. Não representa boleto ou instrução de pagamento.', styles['small']))
    doc.build(story)
    return output.getvalue()
