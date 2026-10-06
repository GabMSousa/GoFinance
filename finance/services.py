import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db.models import Q, Sum

from .models import CreditCardExpense, FinancialProfile, FixedExpense, Investment, Person, SalarySnapshot, Transaction, VRMovement

ZERO = Decimal('0.00')


def money_sum(queryset, field):
    return queryset.aggregate(total=Sum(field))['total'] or ZERO


def month_bounds(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def to_decimal(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def split_installment_values(total, count):
    total = to_decimal(total)
    count = max(int(count or 1), 1)
    per = (total / count).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    values = []
    distributed = ZERO
    for number in range(1, count + 1):
        value = per if number < count else (total - distributed)
        values.append(value)
        distributed += value
    return values


def is_self_person(person):
    if person is None:
        return True
    return person.is_self


def third_party_q():
    return Q(person__isnull=False) & ~Q(person__name__iexact='Eu')


def card_reimbursed_sum(queryset):
    total = ZERO
    for item in queryset.filter(reimbursable=True):
        total += item.reimbursed_amount if item.reimbursed_amount else (item.amount if item.received else ZERO)
    return total


def card_reimbursement_pending_sum(queryset):
    total = ZERO
    for item in queryset.filter(reimbursable=True):
        if item.received and not item.reimbursed_amount:
            continue
        total += max(item.amount - (item.reimbursed_amount or ZERO), ZERO)
    return total


def monthly_credit_setting():
    profile = FinancialProfile.objects.first()
    return to_decimal(profile.vr_monthly_credit if profile else getattr(settings, 'VR_MONTHLY_CREDIT', 500))


def financial_profile_for_month(year, month):
    target = date(year, month, 1)
    snapshot = SalarySnapshot.objects.filter(month=target).first()
    profile = FinancialProfile.objects.first()
    if snapshot:
        return snapshot
    return profile


def vr_initial_setting():
    return to_decimal(getattr(settings, 'VR_INITIAL_BALANCE', 0))


def vr_balance_before(target_date):
    movements = VRMovement.objects.filter(date__lt=target_date)
    credits = money_sum(movements.filter(movement_type=VRMovement.Type.CREDIT), 'amount')
    adjustments = money_sum(movements.filter(movement_type=VRMovement.Type.ADJUSTMENT), 'amount')
    spent = money_sum(movements.filter(movement_type=VRMovement.Type.DEBIT), 'amount')
    months_from_year_start = target_date.month - 1
    monthly = monthly_credit_setting() * months_from_year_start
    return vr_initial_setting() + monthly + credits + adjustments - spent


def vr_available(year, month, extra_spent=ZERO):
    summary = monthly_summary(year, month)
    return summary['vr_balance'] - to_decimal(extra_spent)


def monthly_summary(year, month):
    start, end = month_bounds(year, month)
    tx = Transaction.objects.filter(date__range=(start, end))
    card = CreditCardExpense.objects.filter(date__range=(start, end))
    investments = Investment.objects.filter(date__range=(start, end))
    vr = VRMovement.objects.filter(date__range=(start, end))

    explicit_revenues = tx.filter(type=Transaction.Type.REVENUE)
    explicit_salary = explicit_revenues.filter(revenue_type=Transaction.RevenueType.SALARY).exists()
    profile = financial_profile_for_month(year, month)
    salary_net = to_decimal(profile.salary_net if profile else 0)
    automatic_salary = ZERO if explicit_salary else salary_net
    revenues = money_sum(explicit_revenues, 'amount') + automatic_salary
    reimbursements_tx = money_sum(
        tx.filter(type=Transaction.Type.REIMBURSEMENT, received=True),
        'amount',
    )

    variable_qs = tx.filter(type=Transaction.Type.EXPENSE).exclude(
        payment_method__in=[Transaction.PaymentMethod.CREDIT_CARD, Transaction.PaymentMethod.VR]
    ).filter(fixed_expense=False)
    variable_non_card = money_sum(variable_qs, 'amount')

    card_from_tx = money_sum(
        tx.filter(type=Transaction.Type.EXPENSE, payment_method=Transaction.PaymentMethod.CREDIT_CARD),
        'amount',
    )

    fixed_all = FixedExpense.objects.filter(active=True)
    fixed_total = money_sum(fixed_all, 'amount')
    subscriptions_total = money_sum(fixed_all.filter(is_subscription=True), 'amount')
    fixed_card = money_sum(fixed_all.filter(included_in_credit_card=True), 'amount')
    fixed_non_card = fixed_total - fixed_card

    card_manual = money_sum(card, 'amount') + card_from_tx
    variable_total = variable_non_card + card_manual
    card_invoice = card_manual + fixed_card

    third_party = card.filter(third_party_q())
    tx_third = tx.filter(type=Transaction.Type.EXPENSE).filter(third_party_q()).exclude(
        payment_method=Transaction.PaymentMethod.VR
    )
    third_party_total = money_sum(third_party, 'amount') + money_sum(tx_third, 'amount')
    third_party_received = card_reimbursed_sum(third_party) + money_sum(tx_third.filter(received=True), 'amount')
    third_party_pending = card_reimbursement_pending_sum(third_party) + money_sum(
        tx_third.filter(reimbursable=True, received=False), 'amount'
    )

    card_mine = money_sum(card.exclude(third_party_q()), 'amount') + fixed_card
    card_personal_economic = max(card_invoice - third_party_total, ZERO)

    vr_credit_movements = money_sum(vr.filter(movement_type=VRMovement.Type.CREDIT), 'amount')
    vr_adjustments = money_sum(vr.filter(movement_type=VRMovement.Type.ADJUSTMENT), 'amount')
    vr_spent = money_sum(vr.filter(movement_type=VRMovement.Type.DEBIT), 'amount')
    vr_initial = vr_initial_setting()
    if vr.filter(movement_type=VRMovement.Type.CREDIT).exists():
        vr_credit = vr_credit_movements
    else:
        vr_credit = to_decimal(profile.vr_monthly_credit if profile else monthly_credit_setting())
    vr_balance = vr_initial + vr_credit + vr_adjustments - vr_spent

    investment_month = money_sum(investments, 'amount')
    investment_total = Investment.objects.aggregate(total=Sum('current_balance'))['total'] or ZERO

    expenses_total = fixed_non_card + variable_non_card + card_invoice
    bank_outflow = expenses_total + investment_month
    inflow = revenues + reimbursements_tx + third_party_received
    final_balance = inflow - bank_outflow

    category_rows = list(
        tx.filter(type=Transaction.Type.EXPENSE)
        .exclude(payment_method=Transaction.PaymentMethod.VR)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    card_categories = list(card.values('category__name').annotate(total=Sum('amount')).order_by('-total'))
    fixed_categories = list(fixed_all.values('category__name').annotate(total=Sum('amount')).order_by('-total'))
    merged = {}
    for row in category_rows + card_categories + fixed_categories:
        name = row['category__name'] or 'Sem categoria'
        merged[name] = merged.get(name, ZERO) + (row['total'] or ZERO)
    category_data = sorted(merged.items(), key=lambda item: item[1], reverse=True)

    return {
        'revenues': revenues,
        'salary_net': salary_net,
        'automatic_salary': automatic_salary,
        'expenses': expenses_total,
        'reimbursements': reimbursements_tx + third_party_received,
        'fixed_total': fixed_total,
        'subscriptions_total': subscriptions_total,
        'fixed_non_card': fixed_non_card,
        'variable_total': variable_total,
        'card_invoice': card_invoice,
        'card_manual': card_manual,
        'card_fixed': fixed_card,
        'card_mine': card_mine,
        'third_party_total': third_party_total,
        'third_party_received': third_party_received,
        'third_party_pending': third_party_pending,
        'card_personal_economic': card_personal_economic,
        'vr_initial': vr_initial,
        'vr_credit': vr_credit,
        'vr_spent': vr_spent,
        'vr_balance': vr_balance,
        'investment_month': investment_month,
        'investment_total': investment_total,
        'bank_outflow': bank_outflow,
        'final_balance': final_balance,
        'monthly_forecast': expenses_total + investment_month,
        'category_labels': [x[0] for x in category_data],
        'category_values': [float(x[1]) for x in category_data],
    }


def third_party_by_person(year, month):
    start, end = month_bounds(year, month)
    rows = []
    for person in Person.objects.filter(active=True).exclude(name__iexact='Eu'):
        card = CreditCardExpense.objects.filter(date__range=(start, end), person=person)
        tx = Transaction.objects.filter(
            date__range=(start, end),
            person=person,
            type=Transaction.Type.EXPENSE,
        ).exclude(payment_method=Transaction.PaymentMethod.VR)
        spent = money_sum(card, 'amount') + money_sum(tx, 'amount')
        received = card_reimbursed_sum(card) + money_sum(tx.filter(received=True), 'amount')
        pending = card_reimbursement_pending_sum(card) + money_sum(
            tx.filter(reimbursable=True, received=False), 'amount'
        )
        rows.append({
            'person': person,
            'spent': spent,
            'received': received,
            'pending': pending,
        })
    return rows
