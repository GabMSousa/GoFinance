"""Regras financeiras estruturais do GoFinance.

Estas regras pertencem ao produto e não ao perfil do usuário. Valores,
lançamentos e configurações pessoais podem ser importados; o ciclo financeiro
fundamental da aplicação não pode ser sobrescrito por dados externos.
"""

from datetime import date


CARD_INVOICE_LAG_MONTHS = 1
VR_COMPETENCE_LAG_MONTHS = 1
SALARY_COMPETENCE_LAG_MONTHS = 1


def shift_month_start(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def invoice_month_for_purchase(purchase_date, installment=1):
    installment_number = max(int(installment or 1), 1)
    offset = CARD_INVOICE_LAG_MONTHS + installment_number - 1
    return shift_month_start(purchase_date, offset)


def vr_reference_month(received_date):
    return shift_month_start(received_date, VR_COMPETENCE_LAG_MONTHS)
