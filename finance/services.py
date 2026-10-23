import calendar
import re
import unicodedata
from datetime import datetime, time
from difflib import SequenceMatcher
from uuid import UUID
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import CreditCardExpense, FinancialProfile, FixedExpense, Investment, InvestmentOperation, Person, SalarySnapshot, Transaction, VRMovement

ZERO = Decimal('0.00')


def _normalize_match_text(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '', text)


def fixed_card_duplicate(description, amount, fixed_expenses=None):
    """Return a matching active fixed-card expense, if this card row duplicates it."""
    row_words = [_normalize_match_text(word) for word in str(description).split() if _normalize_match_text(word)]
    fixed_expenses = fixed_expenses if fixed_expenses is not None else FixedExpense.objects.filter(
        active=True,
        included_in_credit_card=True,
    )
    for fixed in fixed_expenses:
        if fixed.amount != amount:
            continue
        fixed_words = [_normalize_match_text(word) for word in fixed.description.split() if _normalize_match_text(word)]
        if any(
            word in row_words
            or any(SequenceMatcher(None, word, candidate).ratio() >= 0.8 for candidate in row_words)
            for word in fixed_words
            if len(word) >= 4
        ):
            return fixed
    return None


def money_sum(queryset, field):
    return queryset.aggregate(total=Sum(field))['total'] or ZERO


def month_bounds(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_datetime_bounds(year, month):
    """Return timezone-aware half-open bounds for datetime fields."""
    start_date, _ = month_bounds(year, month)
    next_date = add_months(start_date, 1)
    start = datetime.combine(start_date, time.min)
    next_start = datetime.combine(next_date, time.min)
    if settings.USE_TZ:
        start = timezone.make_aware(start)
        next_start = timezone.make_aware(next_start)
    return start, next_start


def vr_movements_for_display_period(year, month):
    """Show the previous month's VR credit in the following competence."""
    start, end = month_bounds(year, month)
    previous_month = add_months(start, -1)
    previous_start, previous_end = month_bounds(previous_month.year, previous_month.month)
    return VRMovement.objects.filter(
        Q(date__range=(start, end))
        | Q(date__range=(previous_start, previous_end), movement_type=VRMovement.Type.CREDIT)
    )


def transactions_for_display_period(year, month):
    """Show VR purchases in the following competence without changing their dates."""
    start, end = month_bounds(year, month)
    previous_month = add_months(start, -1)
    previous_start, previous_end = month_bounds(previous_month.year, previous_month.month)
    vr_purchase = Q(type=Transaction.Type.EXPENSE) & (
        Q(payment_method=Transaction.PaymentMethod.VR) | Q(vr_amount__gt=0)
    )
    return Transaction.objects.filter(
        (Q(date__range=(start, end)) & ~vr_purchase)
        | (Q(date__range=(previous_start, previous_end)) & vr_purchase)
    )


def invoice_month_for_installment(purchase_date, installment=1):
    """Return the statement month for a real purchase and its installment."""
    return add_months(purchase_date.replace(day=1), int(installment or 1))


def invoice_month_for_purchase(purchase_date):
    return invoice_month_for_installment(purchase_date, 1)


def card_expenses_for_period(year, month):
    period = date(year, month, 1)
    start, end = month_bounds(year, month)
    queryset = CreditCardExpense.objects.filter(
        Q(invoice_month=period)
        | Q(invoice_month__isnull=True, date__range=(start, end))
    )
    fixed_expenses = list(FixedExpense.objects.filter(active=True, included_in_credit_card=True))
    fixed_duplicate_ids = [
        item.pk for item in queryset.only('pk', 'description', 'amount')
        if fixed_card_duplicate(item.description, item.amount, fixed_expenses)
    ]
    return queryset.exclude(pk__in=fixed_duplicate_ids)


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def to_decimal(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def investment_scope(user=None, include_unassigned=False):
    queryset = Investment.objects.all()
    if user is None:
        return queryset
    condition = Q(user=user)
    if include_unassigned:
        condition |= Q(user__isnull=True)
    return queryset.filter(condition)


def apply_investment_operation(*, user, investment_id, operation_type, operation_key, amount=None,
                               new_balance=None, source='', destination='', reason='', notes='', occurred_on=None):
    """Apply one auditable investment operation atomically and idempotently."""
    # MySQL/MariaDB stores Django UUIDField as CHAR(32), while a UUID object
    # can otherwise be sent to the driver in its hyphenated 36-character form.
    # Normalize before both lookup and insert so idempotency works on every DB.
    operation_key = UUID(str(operation_key)).hex
    with db_transaction.atomic():
        existing = InvestmentOperation.objects.filter(operation_key=operation_key).first()
        if existing:
            if existing.user_id != user.id or existing.investment_id != investment_id or existing.operation_type != operation_type:
                raise ValidationError({'operation_key': 'Esta chave já foi usada em outra operação.'})
            return existing

        investment = Investment.objects.select_for_update().get(pk=investment_id)
        if investment.user_id != user.id:
            raise PermissionDenied('Este investimento ainda não está associado ao usuário autenticado.')

        before = to_decimal(investment.current_balance)
        amount = to_decimal(amount)
        new_balance = None if new_balance is None else to_decimal(new_balance)
        reason = (reason or '').strip()
        source = (source or '').strip()
        destination = (destination or '').strip()
        notes = (notes or '').strip()

        if operation_type == InvestmentOperation.OperationType.CONTRIBUTION:
            if amount <= 0:
                raise ValidationError({'amount': 'Informe um valor maior que zero.'})
            if not source:
                raise ValidationError({'source': 'Informe a origem do aporte.'})
            after = before + amount
        elif operation_type == InvestmentOperation.OperationType.WITHDRAWAL:
            if amount <= 0:
                raise ValidationError({'amount': 'Informe um valor maior que zero.'})
            if amount > before:
                raise ValidationError({'amount': 'O resgate não pode ser maior que o saldo atual.'})
            if not reason:
                raise ValidationError({'reason': 'A justificativa é obrigatória para o resgate.'})
            if not destination:
                raise ValidationError({'destination': 'Informe o destino do resgate.'})
            after = before - amount
        elif operation_type == InvestmentOperation.OperationType.ADJUSTMENT:
            if new_balance is None or new_balance < 0:
                raise ValidationError({'new_balance': 'Informe um novo saldo válido.'})
            if not reason:
                raise ValidationError({'reason': 'A justificativa é obrigatória para o ajuste.'})
            if new_balance == before:
                raise ValidationError({'new_balance': 'O novo saldo deve ser diferente do saldo atual.'})
            after = new_balance
            amount = abs(after - before)
        else:
            raise ValidationError({'operation_type': 'Tipo de operação não permitido nesta etapa.'})

        occurred_at = timezone.now()
        if occurred_on:
            occurred_at = timezone.make_aware(datetime.combine(occurred_on, time.min))
        operation = InvestmentOperation(
            operation_key=operation_key,
            investment=investment,
            user=user,
            operation_type=operation_type,
            amount=amount,
            balance_before=before,
            balance_after=after,
            source=source,
            destination=destination,
            reason=reason,
            notes=notes,
            occurred_at=occurred_at,
        )
        operation.full_clean()
        operation.save()
        investment.current_balance = after
        investment.save(update_fields=['current_balance', 'updated_at'])
        return operation


def sync_transaction_vr(transaction):
    """Keep the persisted VR debit for a full-VR transaction idempotent."""
    movements = list(transaction.vr_movements.filter(movement_type=VRMovement.Type.DEBIT).order_by('id'))
    if transaction.vr_amount <= 0:
        VRMovement.objects.filter(pk__in=[movement.pk for movement in movements]).delete()
        return

    movement = movements[0] if movements else VRMovement(transaction=transaction)
    movement.date = transaction.date
    movement.description = transaction.description
    movement.amount = transaction.vr_amount
    movement.notes = transaction.notes
    movement.movement_type = VRMovement.Type.DEBIT
    movement.save()
    VRMovement.objects.filter(pk__in=[item.pk for item in movements[1:]]).delete()


def sync_card_vr(expense, legacy_date=None, legacy_description=None):
    """Synchronize one card installment's VR portion without creating duplicates."""
    movements = list(expense.vr_movements.filter(movement_type=VRMovement.Type.DEBIT).order_by('id'))
    if not movements and legacy_date and legacy_description:
        legacy = VRMovement.objects.filter(
            date=legacy_date,
            description=legacy_description,
            movement_type=VRMovement.Type.DEBIT,
            transaction__isnull=True,
            card_expense__isnull=True,
        ).order_by('-id').first()
        if legacy:
            legacy.card_expense = expense
            legacy.save(update_fields=['card_expense'])
            movements = [legacy]

    if expense.vr_amount <= 0:
        VRMovement.objects.filter(pk__in=[movement.pk for movement in movements]).delete()
        return

    movement = movements[0] if movements else VRMovement(card_expense=expense)
    movement.date = expense.purchase_date or expense.date
    movement.description = expense.description
    movement.movement_type = VRMovement.Type.DEBIT
    movement.amount = expense.vr_amount
    movement.notes = expense.notes
    movement.save()
    VRMovement.objects.filter(pk__in=[item.pk for item in movements[1:]]).delete()


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


def vr_balance_for_date(target_date):
    """Return the VR balance available for a purchase on target_date."""
    start, _ = month_bounds(target_date.year, target_date.month)
    movements = VRMovement.objects.filter(date__range=(start, target_date))
    credits_qs = movements.filter(movement_type=VRMovement.Type.CREDIT)
    profile = financial_profile_for_month(target_date.year, target_date.month)
    if credits_qs.exists():
        credits = money_sum(credits_qs, 'amount')
    else:
        credit_day = int(getattr(profile, 'vr_credit_day', 1) or 1)
        credit_date = date(target_date.year, target_date.month, min(credit_day, month_bounds(target_date.year, target_date.month)[1].day))
        credits = to_decimal(profile.vr_monthly_credit if profile else monthly_credit_setting()) if target_date >= credit_date else ZERO
    adjustments = money_sum(movements.filter(movement_type=VRMovement.Type.ADJUSTMENT), 'amount')
    spent = money_sum(movements.filter(movement_type=VRMovement.Type.DEBIT), 'amount')
    return vr_initial_setting() + credits + adjustments - spent


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
    datetime_start, datetime_next = month_datetime_bounds(year, month)
    tx = Transaction.objects.filter(date__range=(start, end))
    card = card_expenses_for_period(year, month)
    investment_operations = InvestmentOperation.objects.filter(
        occurred_at__gte=datetime_start,
        occurred_at__lt=datetime_next,
        operation_type=InvestmentOperation.OperationType.CONTRIBUTION,
        status=InvestmentOperation.Status.POSTED,
    )
    vr = VRMovement.objects.filter(date__range=(start, end))

    explicit_revenues = tx.filter(type=Transaction.Type.REVENUE)
    explicit_salary = explicit_revenues.filter(revenue_type=Transaction.RevenueType.SALARY).exists()
    profile = financial_profile_for_month(year, month)
    salary_lag = int(getattr(profile, 'salary_competence_lag_months', 0) or 0)
    salary_competence = add_months(date(year, month, 1), -salary_lag)
    salary_profile = financial_profile_for_month(salary_competence.year, salary_competence.month) or profile
    salary_net = to_decimal(salary_profile.salary_net if salary_profile else 0)
    salary_mode = getattr(
        salary_profile,
        'salary_payment_mode',
        FinancialProfile.SalaryPaymentMode.SPLIT_ADVANCE_SETTLEMENT,
    )
    if salary_mode == FinancialProfile.SalaryPaymentMode.FULL_FIRST_BUSINESS_DAY:
        salary_advance = ZERO
        salary_settlement = salary_net
    else:
        salary_advance = min(
            to_decimal(getattr(salary_profile, 'salary_advance_amount', 0) or 0),
            salary_net,
        )
        salary_settlement = max(salary_net - salary_advance, ZERO)
    opening_balance = to_decimal(getattr(profile, 'opening_balance', 0))
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
    fixed_pending = money_sum(fixed_all.filter(paid=False), 'amount')
    fixed_paid = fixed_total - fixed_pending
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

    investment_month = money_sum(investment_operations, 'amount')
    legacy_initial_investments = Investment.objects.filter(
        date__range=(start, end),
        operations__isnull=True,
    )
    investment_chart_month = investment_month + money_sum(legacy_initial_investments, 'amount')
    investment_total = Investment.objects.filter(active=True).aggregate(total=Sum('current_balance'))['total'] or ZERO

    expenses_total = fixed_non_card + variable_non_card + card_invoice
    bank_outflow = expenses_total + investment_month
    inflow = revenues + reimbursements_tx + third_party_received
    final_balance = opening_balance + inflow - bank_outflow

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
        'salary_payment_mode': salary_mode,
        'salary_advance': salary_advance,
        'salary_settlement': salary_settlement,
        'salary_competence_month': salary_competence,
        'opening_balance': opening_balance,
        'automatic_salary': automatic_salary,
        'expenses': expenses_total,
        'reimbursements': reimbursements_tx + third_party_received,
        'fixed_total': fixed_total,
        'fixed_pending': fixed_pending,
        'fixed_paid': fixed_paid,
        'subscriptions_total': subscriptions_total,
        'fixed_non_card': fixed_non_card,
        'variable_total': variable_total,
        'purchase_bank': variable_total,
        'purchase_vr': vr_spent,
        'purchase_total': variable_total + vr_spent,
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
        'investment_chart_month': investment_chart_month,
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
        card = card_expenses_for_period(year, month).filter(person=person)
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
