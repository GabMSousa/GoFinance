from uuid import UUID

from django.db import migrations


def normalize_uuid_values(apps, schema_editor):
    CreditCardExpense = apps.get_model('finance', 'CreditCardExpense')
    InvestmentOperation = apps.get_model('finance', 'InvestmentOperation')

    for model, field_name in (
        (CreditCardExpense, 'series_id'),
        (InvestmentOperation, 'operation_key'),
    ):
        for item in model.objects.exclude(**{f'{field_name}__isnull': True}).iterator():
            value = getattr(item, field_name)
            if not value:
                continue
            try:
                normalized = UUID(str(value)).hex
            except (AttributeError, ValueError):
                continue
            if normalized != value:
                setattr(item, field_name, normalized)
                item.save(update_fields=[field_name])


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0027_alter_financialprofile_previous_net_salary_and_more'),
    ]

    operations = [
        migrations.RunPython(normalize_uuid_values, migrations.RunPython.noop),
    ]
