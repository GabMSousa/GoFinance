from datetime import date

from django.db import migrations


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def normalize_invoice_months(apps, schema_editor):
    CreditCardExpense = apps.get_model('finance', 'CreditCardExpense')
    for expense in CreditCardExpense.objects.all().iterator():
        purchase_date = expense.purchase_date or expense.date
        installment = expense.current_installment or 1
        expected = add_months(purchase_date.replace(day=1), installment)
        if expense.invoice_month != expected:
            CreditCardExpense.objects.filter(pk=expense.pk).update(invoice_month=expected)


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0023_series_id_as_char_field'),
    ]

    operations = [
        migrations.RunPython(normalize_invoice_months, migrations.RunPython.noop),
    ]
