import json
import uuid
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponseRedirect
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
    QuickExpenseForm,
    ReimbursementForm,
    RevenueForm,
    TransactionForm,
    VRMovementForm,
)
from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Goal, Investment, Person, SalarySnapshot, Transaction, VRMovement
from .importers import import_preview_rows, preview_csv
from .services import add_months, monthly_summary, money_sum, split_installment_values, third_party_by_person, to_decimal


def selected_period(request):
    today = date.today()
    try:
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
        if month not in range(1, 13):
            raise ValueError
    except (TypeError, ValueError):
        month, year = today.month, today.year
    return year, month


def period_context(year, month):
    month_names = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro',
    }
    return {
        'month': month,
        'year': year,
        'month_name': month_names[month],
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
    count = int(data.get('total_installments') or data.get('installment_total') or 1)
    values = split_installment_values(total, count)
    series = uuid.uuid4()
    first_date = data['date']
    last_date = add_months(first_date, count - 1)
    person = data.get('person') or person_from_responsibility(data)
    created = []
    for number, value in enumerate(values, start=1):
        created.append(CreditCardExpense.objects.create(
            date=add_months(first_date, number - 1),
            purchase_date=first_date,
            invoice_month=add_months(first_date, number - 1).replace(day=1),
            description=data['description'],
            category=data['category'],
            amount=value,
            total_amount=total,
            person=person,
            current_installment=number,
            total_installments=count,
            first_installment=first_date,
            last_installment=last_date,
            reimbursable=data.get('reimbursable', False),
            received=data.get('received', False),
            paid=data.get('paid', False),
            notes=data.get('notes', ''),
            series_id=series,
        ))
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
            pass
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
            'category': item.category, 'payment': item.get_payment_method_display(),
            'person': item.person, 'kind': 'transaction', 'type': item.get_type_display(),
            'paid': item.paid, 'pk': item.pk,
        })
    for item in card_qs.distinct():
        movements.append({
            'date': item.date, 'description': item.description, 'amount': item.amount,
            'category': item.category, 'payment': 'Cartão', 'person': item.person,
            'kind': 'card', 'type': 'Compra', 'paid': item.paid, 'paid_at': item.paid_at,
            'pk': item.pk, 'installment': f'{item.current_installment}/{item.total_installments}',
            'reimbursable': item.reimbursable, 'reimbursement_pending': item.reimbursement_pending,
        })
    movements.sort(key=lambda item: item['date'], reverse=True)
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
        'purchase_form': QuickExpenseForm(initial={'date': date.today(), 'installment_total': 1, 'vr_amount': 0}),
        'revenue_form': RevenueForm(initial={'date': date.today(), 'paid': True, 'payment_method': Transaction.PaymentMethod.PIX}),
        'investment_form': InvestmentForm(initial={'date': date.today()}),
        'bill': CreditCardBill.objects.filter(invoice_month=date(year, month, 1)).first(),
        'bill_payment_form': CardBillPaymentForm(initial={'amount': summary['card_invoice'], 'paid_at': date.today()}),
        'csv_form': CsvImportForm(initial={'invoice_month': date(year, month, 1)}),
        'chart_data': json.dumps({
            'revenues': float(summary['revenues']),
            'expenses': float(summary['expenses']),
            'category_labels': summary['category_labels'],
            'category_values': summary['category_values'],
        }),
    })
    return render(request, 'finance/dashboard.html', context)


def settings_page(request):
    profile = FinancialProfile.current()
    form = FinancialProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        target = date.today().replace(day=1)
        updated = form.save()
        SalarySnapshot.objects.update_or_create(
            month=target,
            defaults={
                'salary_gross': updated.salary_gross,
                'salary_net': updated.salary_net,
                'vr_monthly_credit': updated.vr_monthly_credit,
            },
        )
        messages.success(request, 'Dados financeiros atualizados.')
        return redirect('finance:settings')
    return render(request, 'finance/settings.html', {
        'form': form,
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
def csv_import_preview(request):
    form = CsvImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Selecione um CSV e informe o mês da fatura.')
        return redirect('finance:dashboard')
    try:
        rows = preview_csv(form.cleaned_data['csv_file'], form.cleaned_data['invoice_month'])
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
    created, skipped = import_preview_rows(rows, date.fromisoformat(month_value))
    request.session.pop('csv_preview_rows', None)
    request.session.pop('csv_preview_month', None)
    messages.success(request, f'CSV importado: {created} novos registros, {skipped} duplicados ignorados.')
    return redirect(f"{reverse('finance:dashboard')}?year={date.fromisoformat(month_value).year}&month={date.fromisoformat(month_value).month}")


def transaction_list(request):
    year, month = selected_period(request)
    qs = Transaction.objects.select_related('category', 'person').filter(date__year=year, date__month=month)
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
            VRMovement.objects.create(
                date=d['date'],
                description=d['description'],
                movement_type=VRMovement.Type.DEBIT,
                amount=d['amount'],
                transaction=tx,
                notes=d.get('notes', ''),
            )
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
        form.save()
        messages.success(request, 'Lançamento atualizado.')
        return redirect('finance:transaction_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar lançamento'})


def transaction_delete(request, pk):
    return delete_object(request, get_object_or_404(Transaction, pk=pk), 'finance:transaction_list', 'lançamento')


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
            create_card_installments({**d, 'person': person, 'amount': remaining, 'total_installments': d.get('installment_total') or 1})
        elif remaining > 0:
            tx = Transaction.objects.create(
                date=d['date'],
                description=d['description'],
                category=d['category'],
                type=Transaction.Type.EXPENSE,
                payment_method=d['payment_method'],
                amount=remaining,
                paid=d['paid'],
                person=person,
                reimbursable=d['reimbursable'],
                received=d['received'],
                installment_total=1,
                notes=f'Compra total R$ {total}. VR R$ {vr_amount}. {notes}'.strip(),
            )
        if vr_amount > 0:
            VRMovement.objects.create(
                date=d['date'],
                description=d['description'],
                movement_type=VRMovement.Type.DEBIT,
                amount=vr_amount,
                transaction=tx,
                notes=f'Pagamento dividido. Total R$ {total}. {notes}'.strip(),
            )
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
    context.update({'items': items.distinct(), 'summary': summary, 'next_commitment': next_commitment, 'person_filter': person_filter, 'search': search})
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
    form = CreditCardExpenseForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Parcela atualizada.')
        return redirect('finance:card_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar parcela do cartão'})


def card_delete(request, pk):
    return delete_object(request, get_object_or_404(CreditCardExpense, pk=pk), 'finance:card_list', 'parcela')


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


def investment_list(request):
    year, month = selected_period(request)
    items = Investment.objects.filter(date__year=year, date__month=month)
    context = period_context(year, month)
    context.update({
        'items': items,
        'month_total': money_sum(items, 'amount'),
        'balance_total': Investment.objects.aggregate(total=Sum('current_balance'))['total'] or 0,
        'applied_total': money_sum(Investment.objects.all(), 'amount'),
    })
    return render(request, 'finance/investment_list.html', context)


def investment_create(request):
    return model_form_create(request, InvestmentForm, 'Novo investimento', 'finance:investment_list', {'date': date.today()})


def investment_edit(request, pk):
    return model_form_edit(request, Investment, InvestmentForm, pk, 'Editar investimento', 'finance:investment_list')


def investment_delete(request, pk):
    return delete_object(request, get_object_or_404(Investment, pk=pk), 'finance:investment_list', 'investimento')


def monthly_report(request):
    year, month = selected_period(request)
    context = period_context(year, month)
    context['summary'] = monthly_summary(year, month)
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
