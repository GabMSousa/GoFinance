import calendar
import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    CardPurchaseForm,
    CardBillPaymentForm,
    CategoryForm,
    CreditCardExpenseForm,
    CsvImportForm,
    FixedExpenseForm,
    FinancialProfileForm,
    GoalForm,
    InvestmentForm,
    PaymentDateForm,
    PersonForm,
    QuickExpenseForm,
    ReimbursementForm,
    RevenueForm,
    TransactionForm,
    VRMovementForm,
)
from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Goal, Investment, Person, SalarySnapshot, Transaction, VRMovement
from .importers import import_preview_rows, preview_csv
from .services import add_months, month_bounds, monthly_summary, money_sum, split_installment_values, sync_card_vr, sync_transaction_vr, third_party_by_person, to_decimal


def selected_period(request):
    default_year, default_month = default_open_period()
    try:
        month = int(request.GET.get('month', default_month))
        year = int(request.GET.get('year', default_year))
        if month not in range(1, 13):
            raise ValueError
    except (TypeError, ValueError):
        month, year = default_month, default_year
    return year, month


def default_open_period(today=None):
    """Return the first period that is not closed by a paid invoice."""
    reference = today or date.today()
    candidate = reference.replace(day=1)
    for _ in range(24):
        closed = CreditCardBill.objects.filter(
            invoice_month=candidate,
            status=CreditCardBill.Status.PAID,
        ).exists()
        if not closed:
            return candidate.year, candidate.month
        candidate = add_months(candidate, 1)
    return reference.year, reference.month


def period_context(year, month):
    month_names = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro',
    }
    return {
        'month': month,
        'year': year,
        'month_name': month_names[month],
        'invoice_close_date': add_months(date(year, month, 1), 1),
        'months': [
            (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
            (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
            (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
        ],
    }


def person_from_responsibility(data):
    name = 'Eu' if data.get('responsible', 'SELF') == 'SELF' else (data.get('person_name') or '').strip()
    return Person.objects.get_or_create(name=name, defaults={'active': True})[0]


def create_card_installments(data, amount_key='amount'):
    total = to_decimal(data[amount_key])
    vr_amount = to_decimal(data.get('vr_amount') or 0)
    purchase_total = to_decimal(data.get('purchase_total') or data.get('total_amount') or (total + vr_amount))
    count = int(data.get('total_installments') or data.get('installment_total') or 1)
    values = split_installment_values(total, count)
    series = uuid.uuid4()
    first_date = data['date']
    last_date = add_months(first_date, count - 1)
    person = data.get('person') or person_from_responsibility(data)
    created = []
    for number, value in enumerate(values, start=1):
        expense = CreditCardExpense.objects.create(
            date=add_months(first_date, number - 1),
            purchase_date=first_date,
            invoice_month=add_months(first_date, number - 1).replace(day=1),
            description=data['description'],
            category=data['category'],
            amount=value,
            total_amount=purchase_total,
            person=person,
            current_installment=number,
            total_installments=count,
            first_installment=first_date,
            last_installment=last_date,
            reimbursable=data.get('reimbursable', False),
            received=data.get('received', False),
            paid=data.get('paid', False),
            vr_amount=vr_amount if number == 1 else Decimal('0.00'),
            notes=data.get('notes', ''),
            series_id=series,
        )
        sync_card_vr(expense)
        created.append(expense)
    return created


def dashboard(request):
    year, month = selected_period(request)
    summary = monthly_summary(year, month)
    search = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '')
    payment = request.GET.get('payment', '')
    person_filter = request.GET.get('person', '')
    tx_qs = Transaction.objects.select_related('category', 'person').filter(date__year=year, date__month=month)
    card_qs = CreditCardExpense.objects.select_related('category', 'person').filter(date__year=year, date__month=month)
    if search:
        tx_qs = tx_qs.filter(description__icontains=search)
        card_qs = card_qs.filter(description__icontains=search) | card_qs.filter(person__name__icontains=search)
    if category_id:
        tx_qs = tx_qs.filter(category_id=category_id)
        card_qs = card_qs.filter(category_id=category_id)
    if payment:
        tx_qs = tx_qs.filter(payment_method=payment)
        if payment == Transaction.PaymentMethod.CREDIT_CARD:
            card_qs = card_qs.filter(vr_amount=0)
        elif payment == Transaction.PaymentMethod.VR:
            tx_qs = tx_qs.filter(vr_amount__gt=0)
            card_qs = card_qs.filter(vr_amount__gt=0)
        else:
            card_qs = card_qs.none()
    if person_filter == 'other':
        tx_qs = tx_qs.exclude(person__name__iexact='Eu')
        card_qs = card_qs.exclude(person__name__iexact='Eu')
    elif person_filter == 'self':
        tx_qs = tx_qs.filter(person__name__iexact='Eu')
        card_qs = card_qs.filter(person__name__iexact='Eu')
    movements = []
    for item in tx_qs:
        movements.append({
            'date': item.date, 'description': item.description, 'amount': item.amount,
            'total_amount': item.amount + item.vr_amount, 'vr_amount': item.vr_amount,
            'category': item.category, 'payment': item.get_payment_method_display(),
            'person': item.person, 'kind': 'transaction', 'type': item.get_type_display(),
            'paid': item.paid, 'pk': item.pk,
            'uses_vr': item.vr_movements.exists(),
            'total_amount': item.amount + item.vr_amount,
            'vr_amount': item.vr_amount,
            'card_amount': item.amount if item.payment_method != Transaction.PaymentMethod.VR else Decimal('0.00'),
        })
    for item in card_qs.distinct():
        movements.append({
            'date': item.date, 'description': item.description, 'amount': item.amount,
            'category': item.category, 'payment': 'Cartão', 'person': item.person,
            'total_amount': item.amount + item.vr_amount, 'vr_amount': item.vr_amount,
            'kind': 'card', 'type': 'Compra', 'paid': item.paid, 'paid_at': item.paid_at,
            'pk': item.pk, 'installment': f'{item.current_installment}/{item.total_installments}',
            'reimbursable': item.reimbursable, 'reimbursement_pending': item.reimbursement_pending,
            'uses_vr': item.vr_amount > 0,
            'total_amount': item.movement_total,
            'vr_amount': item.vr_amount,
            'card_amount': item.amount,
        })
    movements.sort(key=lambda item: item['date'], reverse=True)
    vr_movement_indexes = [index for index, item in enumerate(movements) if item.get('uses_vr')]
    balance = summary['opening_balance'] + summary['revenues']
    balance_points = [{'label': '01/' + f'{month:02d}', 'value': float(balance)}]
    all_items = []
    for item in Transaction.objects.filter(date__range=(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))):
        all_items.append((item.date, item.amount, item.type, item.payment_method))
    for item in CreditCardExpense.objects.filter(date__year=year, date__month=month):
        all_items.append((item.date, item.amount, Transaction.Type.EXPENSE, Transaction.PaymentMethod.CREDIT_CARD))
    for item in Investment.objects.filter(date__year=year, date__month=month):
        all_items.append((item.date, item.amount, Transaction.Type.INVESTMENT, None))
    for movement_date, amount, movement_type, payment_method in sorted(all_items, key=lambda row: row[0]):
        if movement_type == Transaction.Type.EXPENSE and payment_method == Transaction.PaymentMethod.VR:
            continue
        if movement_type in (Transaction.Type.EXPENSE, Transaction.Type.INVESTMENT):
            balance -= amount
        elif movement_type == Transaction.Type.REVENUE:
            continue
        elif movement_type == Transaction.Type.REIMBURSEMENT:
            balance += amount
        balance_points.append({'label': movement_date.strftime('%d/%m'), 'value': float(balance)})
    context = period_context(year, month)
    context.update({
        'summary': summary,
        'movements': movements,
        'categories': Category.objects.filter(active=True),
        'payment_choices': Transaction.PaymentMethod.choices,
        'search': search,
        'category_id': category_id,
        'payment': payment,
        'person_filter': person_filter,
        'vr_movement_indexes': vr_movement_indexes,
        'purchase_form': QuickExpenseForm(initial={'date': date.today(), 'installment_total': 1, 'vr_amount': 0}),
        'revenue_form': RevenueForm(initial={'date': date.today(), 'paid': True, 'payment_method': Transaction.PaymentMethod.PIX}),
        'investment_form': InvestmentForm(initial={'date': date.today()}),
        'bill': CreditCardBill.objects.filter(invoice_month=date(year, month, 1)).first(),
        'bill_items': CreditCardExpense.objects.select_related('category', 'person').filter(
            date__year=year, date__month=month
        ),
        'fixed_items': FixedExpense.objects.select_related('category').filter(active=True),
        'investment_items': Investment.objects.select_related('category').filter(date__year=year, date__month=month),
        'active_investments': Investment.objects.filter(active=True),
        'next_investment': Investment.objects.filter(active=True, date__gte=date(year, month, 1)).order_by('date', 'id').first(),
        'bill_payment_form': CardBillPaymentForm(initial={'amount': summary['card_invoice'], 'paid_at': date.today()}),
        'csv_form': CsvImportForm(initial={'invoice_month': date(year, month, 1)}),
        'movement_details': [
            {'total': float(item['total_amount']), 'vr': float(item['vr_amount']), 'card': float(item['card_amount'])}
            for item in movements
        ],
        'chart_data': {
            'revenues': float(summary['revenues']),
            'expenses': float(summary['expenses']),
            'investments': float(summary['investment_month']),
            'category_labels': summary['category_labels'],
            'category_values': summary['category_values'],
            'balance_labels': [point['label'] for point in balance_points],
            'balance_values': [point['value'] for point in balance_points],
        },
    })
    return render(request, 'finance/dashboard.html', context)


def settings_page(request):
    profile = FinancialProfile.current()
    year, month = selected_period(request)
    target = date(year, month, 1)
    snapshot = SalarySnapshot.objects.filter(month=target).first()
    initial = {'opening_balance': snapshot.opening_balance if snapshot else Decimal('0.00')}
    form = FinancialProfileForm(request.POST or None, instance=profile, initial=initial)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        SalarySnapshot.objects.update_or_create(
            month=target,
            defaults={
                'salary_gross': updated.salary_gross,
                'salary_net': updated.salary_net,
                'vr_monthly_credit': updated.vr_monthly_credit,
                'opening_balance': form.cleaned_data.get('opening_balance') or Decimal('0.00'),
            },
        )
        messages.success(request, 'Dados financeiros atualizados.')
        redirect_url = reverse('finance:settings')
        if request.GET.get('year') or request.GET.get('month'):
            redirect_url = f'{redirect_url}?year={year}&month={month}'
        return redirect(redirect_url)
    return render(request, 'finance/settings.html', {
        'form': form,
        **period_context(year, month),
        'fixed_items': FixedExpense.objects.select_related('category').all(),
        'categories': Category.objects.all(),
        'people': Person.objects.all(),
    })


@require_POST
def pay_bill(request):
    year, month = selected_period(request)
    invoice_month = date(year, month, 1)
    form = CardBillPaymentForm(request.POST)
    if form.is_valid():
        bill, _ = CreditCardBill.objects.get_or_create(invoice_month=invoice_month, defaults={'amount': form.cleaned_data['amount']})
        bill.amount = form.cleaned_data['amount']
        bill.paid_at = form.cleaned_data['paid_at']
        bill.status = CreditCardBill.Status.PAID
        bill.save()
        messages.success(request, 'Fatura marcada como paga. A quitação não criou uma nova despesa.')
    else:
        messages.error(request, 'Confira o valor e a data do pagamento.')
    return redirect(f"{reverse('finance:dashboard')}?year={year}&month={month}")


@require_POST
def undo_bill_payment(request):
    year, month = selected_period(request)
    bill = get_object_or_404(CreditCardBill, invoice_month=date(year, month, 1))
    bill.status = CreditCardBill.Status.PENDING
    bill.paid_at = None
    bill.save(update_fields=['status', 'paid_at', 'updated_at'])
    messages.success(request, 'Pagamento desfeito. A fatura voltou para pendente.')
    return redirect(f"{reverse('finance:dashboard')}?year={year}&month={month}")


@require_POST
def csv_import_preview(request):
    form = CsvImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Selecione um CSV e informe o mês da fatura.')
        return redirect('finance:dashboard')
    invoice_month = form.cleaned_data['invoice_month'].replace(day=1)
    bill = CreditCardBill.objects.filter(invoice_month=invoice_month).first()
    if bill and bill.is_paid:
        messages.error(request, 'Esta fatura já foi paga. Para importar novos lançamentos, desfaça o pagamento da fatura primeiro.')
        return redirect(f"{reverse('finance:dashboard')}?year={invoice_month.year}&month={invoice_month.month}")
    try:
        rows = preview_csv(form.cleaned_data['csv_file'], invoice_month)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('finance:dashboard')
    request.session['csv_preview_rows'] = rows
    request.session['csv_preview_month'] = form.cleaned_data['invoice_month'].isoformat()
    context = period_context(form.cleaned_data['invoice_month'].year, form.cleaned_data['invoice_month'].month)
    context.update({'rows': rows, 'new_count': sum(not row['duplicate'] for row in rows), 'duplicate_count': sum(row['duplicate'] for row in rows), 'filename': form.cleaned_data['csv_file'].name})
    return render(request, 'finance/import_preview.html', context)


@require_POST
def csv_import_confirm(request):
    rows = request.session.get('csv_preview_rows', [])
    month_value = request.session.get('csv_preview_month')
    if not rows or not month_value:
        messages.error(request, 'A prévia expirou. Selecione o CSV novamente.')
        return redirect('finance:dashboard')
    invoice_month = date.fromisoformat(month_value)
    bill = CreditCardBill.objects.filter(invoice_month=invoice_month).first()
    if bill and bill.is_paid:
        request.session.pop('csv_preview_rows', None)
        request.session.pop('csv_preview_month', None)
        messages.error(request, 'Esta fatura já foi paga. Para importar novos lançamentos, desfaça o pagamento da fatura primeiro.')
        return redirect(f"{reverse('finance:dashboard')}?year={invoice_month.year}&month={invoice_month.month}")
    created, skipped = import_preview_rows(rows, invoice_month)
    request.session.pop('csv_preview_rows', None)
    request.session.pop('csv_preview_month', None)
    messages.success(request, f'CSV importado: {created} novos registros, {skipped} duplicados ignorados.')
    return redirect(f"{reverse('finance:dashboard')}?year={invoice_month.year}&month={invoice_month.month}")


REPORT_TYPES = {
    'financial': 'Relatório financeiro',
    'bills': 'Relatório de faturas',
    'categories': 'Relatório de categorias',
    'income_expense': 'Receitas e despesas',
    'investments': 'Relatório de investimentos',
    'vr': 'Relatório de VR',
    'third_party': 'Terceiros e reembolsos',
    'visual': 'Relatório visual',
}


def report_period(request):
    year, month = selected_period(request)
    start, end = month_bounds(year, month)
    for field, fallback in (('start', start), ('end', end)):
        value = request.GET.get(field)
        if value:
            try:
                parsed = datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                parsed = fallback
            if field == 'start':
                start = parsed
            else:
                end = parsed
    if start > end:
        start, end = end, start
    return year, month, start, end


def report_rows(start, end, category_id='', report_type='financial'):
    rows = []
    transactions = Transaction.objects.select_related('category', 'person').filter(date__range=(start, end))
    if category_id:
        transactions = transactions.filter(category_id=category_id)
    for item in transactions:
        if report_type not in ('financial', 'categories', 'income_expense', 'third_party', 'visual'):
            continue
        if report_type == 'third_party' and not item.reimbursable:
            continue
        total = item.amount + item.vr_amount
        card_amount = item.amount if item.payment_method != Transaction.PaymentMethod.VR else Decimal('0.00')
        rows.append([item.date, item.description, item.category.name if item.category else '', item.get_type_display(), total, item.get_payment_method_display(), '', item.vr_amount, card_amount, item.person.name if item.person else '', 'Pago' if item.paid else 'Pendente', ''])
    cards = CreditCardExpense.objects.select_related('category', 'person').filter(date__range=(start, end))
    if category_id:
        cards = cards.filter(category_id=category_id)
    for item in cards:
        if report_type not in ('financial', 'bills', 'categories', 'third_party', 'visual'):
            continue
        if report_type == 'third_party' and not item.reimbursable:
            continue
        rows.append([item.date, item.description, item.category.name, 'Despesa', item.amount, 'Cartão', item.invoice_month or item.date, item.vr_amount, item.amount, item.person.name, 'Pago' if item.paid else 'Pendente', f'{item.current_installment}/{item.total_installments}'])
    if report_type in ('financial', 'investments', 'visual'):
        for item in Investment.objects.filter(date__range=(start, end)):
            rows.append([item.date, item.description, '', 'Investimento', item.amount, '', '', '', '', '', '', ''])
    if report_type in ('financial', 'vr', 'visual'):
        for item in VRMovement.objects.filter(date__range=(start, end)):
            if report_type != 'vr' and (item.transaction_id or item.card_expense_id):
                continue
            rows.append([item.date, item.description, '', item.get_movement_type_display(), item.amount, 'VR', '', item.amount, '', '', '', ''])
    for row in rows:
        if len(row) == 12 and row[11]:
            row[4] = row[7] + row[8]
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows


def report_filters(request):
    year, month, start, end = report_period(request)
    category_id = request.GET.get('category', '')
    report_type = request.GET.get('report_type', 'financial')
    if report_type not in REPORT_TYPES:
        report_type = 'financial'
    return year, month, start, end, category_id, report_type


def report_csv(request):
    year, month, start, end, category_id, report_type = report_filters(request)
    summary = monthly_summary(year, month)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="gofinance-{start.isoformat()}-{end.isoformat()}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Forma de pagamento', 'Fatura', 'Valor VR', 'Valor cartão', 'Responsável', 'Status', 'Parcelamento'])
    writer.writerow(['', 'Saldo inicial', '', 'Saldo inicial', summary['opening_balance'], '', '', '', '', '', '', ''])
    writer.writerows(report_rows(start, end, category_id, report_type))
    return response


def report_pdf(request):
    year, month, start, end, category_id, report_type = report_filters(request)
    summary = monthly_summary(year, month)
    lines = [
        f'GoFinance - {REPORT_TYPES[report_type]}',
        f'Periodo: {start.strftime("%d/%m/%Y")} a {end.strftime("%d/%m/%Y")}',
        f'GoFinance - Relatório {month:02d}/{year}',
        f'Saldo inicial: R$ {summary["opening_balance"]:.2f}',
        f'Receitas: R$ {summary["revenues"]:.2f}',
        f'Despesas: R$ {summary["expenses"]:.2f}',
        f'Fatura: R$ {summary["card_invoice"]:.2f}',
        f'Compras: R$ {summary["purchase_total"]:.2f}',
        f'Compras no VR: R$ {summary["purchase_vr"]:.2f}',
        f'Compras no cartão/banco: R$ {summary["purchase_bank"]:.2f}',
        f'Investimentos: R$ {summary["investment_month"]:.2f}',
        f'VR utilizado: R$ {summary["vr_spent"]:.2f}',
        f'Terceiros pendentes: R$ {summary["third_party_pending"]:.2f}',
        f'Saldo: R$ {summary["final_balance"]:.2f}',
        'Categorias:',
        *[f'- {label}: R$ {value:.2f}' for label, value in zip(summary['category_labels'], summary['category_values'])],
        f'Registros: {len(report_rows(start, end, category_id, report_type))}',
    ]
    text = '\n'.join(lines)
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>', None, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    stream = 'BT /F1 12 Tf 50 790 Td ' + ' '.join(f'({line.replace("(", "\\(").replace(")", "\\)")}) Tj 0 -20 Td' for line in lines) + ' ET'
    objects[3] = f'<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream'.encode()
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf)); pdf.extend(f'{number} 0 obj\n'.encode()); pdf.extend(obj); pdf.extend(b'\nendobj\n')
    xref = len(pdf); pdf.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()); pdf.extend(''.join(f'{offset:010d} 00000 n \n' for offset in offsets[1:]).encode()); pdf.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    response = HttpResponse(bytes(pdf), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="gofinance-{start.isoformat()}-{end.isoformat()}.pdf"'
    return response


def transaction_list(request):
    year, month = selected_period(request)
    qs = Transaction.objects.select_related('category', 'person').prefetch_related('vr_movements').filter(date__year=year, date__month=month)
    if request.GET.get('q'):
        qs = qs.filter(description__icontains=request.GET['q'])
    if request.GET.get('category'):
        qs = qs.filter(category_id=request.GET['category'])
    if request.GET.get('payment'):
        qs = qs.filter(payment_method=request.GET['payment'])
    if request.GET.get('person'):
        qs = qs.filter(person_id=request.GET['person'])
    if request.GET.get('type'):
        qs = qs.filter(type=request.GET['type'])
    context = period_context(year, month)
    context.update({
        'items': qs,
        'categories': Category.objects.filter(active=True),
        'people': Person.objects.filter(active=True),
        'payment_choices': Transaction.PaymentMethod.choices,
        'type_choices': Transaction.Type.choices,
        'filters': request.GET,
    })
    return render(request, 'finance/transaction_list.html', context)


def transaction_create(request):
    form = TransactionForm(request.POST or None, initial={'date': date.today(), 'installment_total': 1})
    if form.is_valid():
        d = form.cleaned_data
        if d['type'] == Transaction.Type.EXPENSE and d['payment_method'] == Transaction.PaymentMethod.CREDIT_CARD:
            create_card_installments({**d, 'amount': d['amount'], 'total_installments': d.get('installment_total') or 1})
            messages.success(request, 'Compra enviada ao cartão e parcelas criadas.')
            return redirect('finance:card_list')
        if d['type'] == Transaction.Type.EXPENSE and d['payment_method'] == Transaction.PaymentMethod.VR:
            tx = form.save()
            sync_transaction_vr(tx)
            messages.success(request, 'Gasto lançado no Vale Refeição.')
            return redirect('finance:vr_list')
        form.save()
        messages.success(request, 'Lançamento salvo.')
        return redirect('finance:transaction_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Novo lançamento'})


def transaction_edit(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    form = TransactionForm(request.POST or None, instance=obj)
    if form.is_valid():
        sync_transaction_vr(form.save())
        messages.success(request, 'Lançamento atualizado.')
        return redirect('finance:transaction_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar lançamento'})


def transaction_delete(request, pk):
    item = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        item.vr_movements.all().delete()
    return delete_object(request, item, 'finance:transaction_list', 'lançamento')


@require_POST
def transaction_toggle_paid(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    obj.paid = not obj.paid
    obj.save(update_fields=['paid', 'updated_at'])
    messages.success(request, 'Status de pagamento atualizado.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('finance:transaction_list'))


def revenue_list(request):
    year, month = selected_period(request)
    items = Transaction.objects.filter(
        date__year=year,
        date__month=month,
        type__in=[Transaction.Type.REVENUE, Transaction.Type.REIMBURSEMENT],
    ).select_related('category', 'person')
    context = period_context(year, month)
    context.update({
        'items': items,
        'total': money_sum(items.filter(type=Transaction.Type.REVENUE), 'amount'),
        'previous_net': '2.299,00',
        'new_gross': '3.000,00',
    })
    return render(request, 'finance/revenue_list.html', context)


def revenue_create(request):
    form = RevenueForm(request.POST or None, initial={'date': date.today(), 'paid': True, 'payment_method': Transaction.PaymentMethod.PIX})
    if form.is_valid():
        form.save()
        messages.success(request, 'Receita salva.')
        return redirect('finance:revenue_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Nova receita'})


def revenue_delete(request, pk):
    item = get_object_or_404(Transaction, pk=pk, type__in=[Transaction.Type.REVENUE, Transaction.Type.REIMBURSEMENT])
    return delete_object(request, item, 'finance:revenue_list', 'receita')


def revenue_edit(request, pk):
    obj = get_object_or_404(Transaction, pk=pk, type__in=[Transaction.Type.REVENUE, Transaction.Type.REIMBURSEMENT])
    form = RevenueForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Receita atualizada.')
        return redirect('finance:revenue_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar receita'})


def quick_expense(request):
    form = QuickExpenseForm(request.POST or None, initial={'date': date.today(), 'installment_total': 1, 'vr_amount': 0})
    if form.is_valid():
        d = form.cleaned_data
        total = to_decimal(d['amount'])
        vr_amount = to_decimal(d.get('vr_amount') or 0)
        remaining = total - vr_amount
        notes = d.get('notes') or ''
        person = person_from_responsibility(d)
        tx = None
        if remaining > 0 and d['payment_method'] == Transaction.PaymentMethod.VR:
            vr_amount += remaining
            remaining = Decimal('0.00')
        if remaining > 0 and d['payment_method'] == Transaction.PaymentMethod.CREDIT_CARD:
            create_card_installments({**d, 'person': person, 'amount': remaining, 'purchase_total': total, 'vr_amount': vr_amount, 'total_installments': d.get('installment_total') or 1})
        elif remaining > 0:
            tx = Transaction.objects.create(
                date=d['date'],
                description=d['description'],
                category=d['category'],
                type=Transaction.Type.EXPENSE,
                payment_method=d['payment_method'],
                amount=remaining,
                vr_amount=vr_amount,
                paid=d['paid'],
                person=person,
                reimbursable=d['reimbursable'],
                received=d['received'],
                installment_total=1,
                notes=f'Compra total R$ {total}. VR R$ {vr_amount}. {notes}'.strip(),
            )
        elif vr_amount > 0:
            # Keep a visible ledger entry for purchases made entirely with VR.
            # The linked VR movement remains the source of the debit; this
            # transaction is excluded from bank expenses by monthly_summary.
            tx = Transaction.objects.create(
                date=d['date'],
                description=d['description'],
                category=d['category'],
                type=Transaction.Type.EXPENSE,
                payment_method=Transaction.PaymentMethod.VR,
                amount=vr_amount,
                vr_amount=vr_amount,
                paid=d['paid'],
                person=person,
                reimbursable=d['reimbursable'],
                received=d['received'],
                installment_total=1,
                notes=f'Compra paga integralmente com VR. {notes}'.strip(),
            )
        if tx:
            sync_transaction_vr(tx)
        messages.success(request, 'Gasto salvo.')
        return redirect('finance:dashboard')
    return render(request, 'finance/quick_expense.html', {'form': form, 'title': 'Novo gasto'})


def category_list(request):
    return render(request, 'finance/category_list.html', {'items': Category.objects.all()})


def category_create(request):
    return model_form_create(request, CategoryForm, 'Nova categoria', 'finance:category_list')


def category_edit(request, pk):
    return model_form_edit(request, Category, CategoryForm, pk, 'Editar categoria', 'finance:category_list')


def category_delete(request, pk):
    return delete_object(request, get_object_or_404(Category, pk=pk), 'finance:category_list', 'categoria')


def fixed_list(request):
    items = FixedExpense.objects.select_related('category').all()
    card_items = items.filter(included_in_credit_card=True)
    other_items = items.filter(included_in_credit_card=False)
    return render(request, 'finance/fixed_list.html', {
        'card_items': card_items,
        'other_items': other_items,
        'total': money_sum(items.filter(active=True), 'amount'),
        'total_card': money_sum(card_items.filter(active=True), 'amount'),
        'total_other': money_sum(other_items.filter(active=True), 'amount'),
    })


def fixed_create(request):
    return model_form_create(request, FixedExpenseForm, 'Novo gasto fixo', 'finance:fixed_list')


def fixed_edit(request, pk):
    return model_form_edit(request, FixedExpense, FixedExpenseForm, pk, 'Editar gasto fixo', 'finance:fixed_list')


def fixed_delete(request, pk):
    return delete_object(request, get_object_or_404(FixedExpense, pk=pk), 'finance:fixed_list', 'gasto fixo')


@require_POST
def fixed_toggle_paid(request, pk):
    item = get_object_or_404(FixedExpense, pk=pk)
    item.paid = not item.paid
    item.save(update_fields=['paid', 'updated_at'])
    messages.success(request, 'Status da conta atualizado.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('finance:fixed_list'))


def card_list(request):
    year, month = selected_period(request)
    person_filter = request.GET.get('person', 'all')
    search = request.GET.get('q', '').strip()
    items = CreditCardExpense.objects.select_related('category', 'person')
    if not search and person_filter == 'all':
        items = items.filter(date__year=year, date__month=month)
    if search:
        items = items.filter(description__icontains=search) | items.filter(person__name__icontains=search)
    if person_filter == 'self':
        items = items.filter(person__name__iexact='Eu')
    elif person_filter == 'other':
        items = items.exclude(person__name__iexact='Eu')
    summary = monthly_summary(year, month)
    next_month = add_months(date(year, month, 1), 1)
    next_commitment = money_sum(
        CreditCardExpense.objects.filter(date__year=next_month.year, date__month=next_month.month),
        'amount',
    )
    context = period_context(year, month)
    distinct_items = items.distinct()
    item_list = list(distinct_items)
    context.update({'items': distinct_items, 'vr_card_indexes': [index for index, item in enumerate(item_list) if item.vr_amount > 0], 'vr_card_details': [{'total': str(item.movement_total), 'vr': str(item.vr_amount), 'card': str(item.amount)} for item in item_list], 'summary': summary, 'next_commitment': next_commitment, 'person_filter': person_filter, 'search': search})
    return render(request, 'finance/card_list.html', context)


def card_create(request):
    form = CardPurchaseForm(request.POST or None, initial={'date': date.today(), 'total_installments': 1})
    if form.is_valid():
        create_card_installments({**form.cleaned_data, 'person': person_from_responsibility(form.cleaned_data)})
        messages.success(request, 'Compra e parcelas criadas.')
        return redirect('finance:card_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Nova compra no cartão'})


def card_edit(request, pk):
    obj = get_object_or_404(CreditCardExpense, pk=pk)
    old_vr_date = obj.purchase_date or obj.date
    old_vr_description = obj.description
    form = CreditCardExpenseForm(request.POST or None, instance=obj)
    if form.is_valid():
        updated = form.save()
        sync_card_vr(updated, legacy_date=old_vr_date, legacy_description=old_vr_description)
        messages.success(request, 'Parcela atualizada.')
        return redirect('finance:card_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar parcela do cartão'})


def card_delete(request, pk):
    item = get_object_or_404(CreditCardExpense, pk=pk)
    VRMovement.objects.filter(
        date=item.purchase_date or item.date,
        description=item.description,
        movement_type=VRMovement.Type.DEBIT,
        transaction__isnull=True,
        card_expense__isnull=True,
    ).delete()
    return delete_object(request, item, 'finance:card_list', 'parcela')


@require_POST
def card_mark_paid(request, pk):
    item = get_object_or_404(CreditCardExpense, pk=pk)
    form = PaymentDateForm(request.POST)
    if form.is_valid():
        item.paid = True
        item.paid_at = form.cleaned_data['paid_at']
        item.save(update_fields=['paid', 'paid_at', 'updated_at'])
        messages.success(request, 'Parcela marcada como paga.')
    else:
        messages.error(request, 'Informe uma data de pagamento válida.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('finance:card_list'))


@require_POST
def card_unmark_paid(request, pk):
    item = get_object_or_404(CreditCardExpense, pk=pk)
    item.paid = False
    item.paid_at = None
    item.save(update_fields=['paid', 'paid_at', 'updated_at'])
    messages.success(request, 'Pagamento desfeito.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('finance:card_list'))


@require_POST
def card_reimburse(request, pk):
    item = get_object_or_404(CreditCardExpense, pk=pk)
    form = ReimbursementForm(request.POST, max_amount=item.amount)
    if form.is_valid():
        item.reimbursed_amount = form.cleaned_data['reimbursed_amount']
        item.reimbursed_at = form.cleaned_data['reimbursed_at']
        item.received = item.reimbursed_amount >= item.amount
        item.save(update_fields=['reimbursed_amount', 'reimbursed_at', 'received', 'updated_at'])
        messages.success(request, 'Reembolso registrado.')
    else:
        messages.error(request, 'Informe um valor e uma data de reembolso válidos.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('finance:card_list'))


def third_party(request):
    year, month = selected_period(request)
    summary = monthly_summary(year, month)
    rows = third_party_by_person(year, month)
    items = CreditCardExpense.objects.filter(date__year=year, date__month=month).exclude(
        person__name__iexact='Eu'
    ).select_related('person', 'category')
    context = period_context(year, month)
    context.update({'items': items, 'rows': rows, 'summary': summary})
    return render(request, 'finance/third_party.html', context)


def vr_list(request):
    year, month = selected_period(request)
    summary = monthly_summary(year, month)
    items = VRMovement.objects.filter(date__year=year, date__month=month)
    context = period_context(year, month)
    context.update({'items': items, 'summary': summary})
    return render(request, 'finance/vr_list.html', context)


def vr_create(request):
    return model_form_create(request, VRMovementForm, 'Novo movimento de Vale Refeição', 'finance:vr_list', {'date': date.today()})


def vr_edit(request, pk):
    return model_form_edit(request, VRMovement, VRMovementForm, pk, 'Editar movimento de VR', 'finance:vr_list')


def person_edit(request, pk):
    return model_form_edit(request, Person, PersonForm, pk, 'Editar pessoa', 'finance:settings')


def investment_list(request):
    year, month = selected_period(request)
    items = Investment.objects.select_related('category').filter(date__year=year, date__month=month)
    recurring_items = Investment.objects.filter(active=True).exclude(recurrence=Investment.Recurrence.ONE_TIME)
    next_investment = Investment.objects.filter(active=True, date__gte=date.today()).order_by('date', 'id').first()
    context = period_context(year, month)
    context.update({
        'items': items,
        'month_total': money_sum(items, 'amount'),
        'balance_total': Investment.objects.aggregate(total=Sum('current_balance'))['total'] or 0,
        'applied_total': money_sum(Investment.objects.all(), 'amount'),
        'recurring_items': recurring_items,
        'active_count': Investment.objects.filter(active=True).count(),
        'next_investment': next_investment,
    })
    return render(request, 'finance/investment_list.html', context)


def investment_create(request):
    return model_form_create(request, InvestmentForm, 'Novo investimento', 'finance:investment_list', {'date': date.today()})


def investment_edit(request, pk):
    return model_form_edit(request, Investment, InvestmentForm, pk, 'Editar investimento', 'finance:investment_list')


def investment_delete(request, pk):
    return delete_object(request, get_object_or_404(Investment, pk=pk), 'finance:investment_list', 'investimento')


def monthly_report(request):
    year, month, start, end, category_id, report_type = report_filters(request)
    context = period_context(year, month)
    context['summary'] = monthly_summary(year, month)
    context.update({
        'report_types': REPORT_TYPES.items(),
        'report_type': report_type,
        'report_type_label': REPORT_TYPES[report_type],
        'report_start': start,
        'report_end': end,
        'report_category': category_id,
        'report_categories': Category.objects.filter(active=True),
        'report_chart_data': {
            'labels': context['summary']['category_labels'],
            'values': context['summary']['category_values'],
            'revenues': float(context['summary']['revenues']),
            'expenses': float(context['summary']['expenses']),
            'investments': float(context['summary']['investment_month']),
        },
    })
    return render(request, 'finance/monthly_report.html', context)


def goal_list(request):
    return render(request, 'finance/goal_list.html', {'items': Goal.objects.all()})


def goal_create(request):
    return model_form_create(request, GoalForm, 'Nova meta', 'finance:goal_list')


def goal_edit(request, pk):
    return model_form_edit(request, Goal, GoalForm, pk, 'Editar meta', 'finance:goal_list')


def goal_delete(request, pk):
    return delete_object(request, get_object_or_404(Goal, pk=pk), 'finance:goal_list', 'meta')


def model_form_create(request, form_class, title, redirect_name, initial=None):
    form = form_class(request.POST or None, initial=initial)
    if form.is_valid():
        form.save()
        messages.success(request, 'Registro salvo.')
        return redirect(redirect_name)
    return render(request, 'finance/form.html', {'form': form, 'title': title})


def model_form_edit(request, model, form_class, pk, title, redirect_name):
    obj = get_object_or_404(model, pk=pk)
    form = form_class(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Registro atualizado.')
        return redirect(redirect_name)
    return render(request, 'finance/form.html', {'form': form, 'title': title})


def delete_object(request, obj, redirect_name, label):
    if request.method == 'POST':
        obj.delete()
        messages.success(request, f'{label.capitalize()} excluído.')
        return redirect(redirect_name)
    return render(request, 'finance/confirm_delete.html', {'object': obj, 'label': label})
