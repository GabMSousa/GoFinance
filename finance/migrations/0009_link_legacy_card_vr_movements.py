from django.db import migrations


def link_legacy_card_vr_movements(apps, schema_editor):
    CreditCardExpense = apps.get_model('finance', 'CreditCardExpense')
    VRMovement = apps.get_model('finance', 'VRMovement')
    for expense in CreditCardExpense.objects.filter(vr_amount__gt=0):
        movement = VRMovement.objects.filter(
            date=expense.purchase_date or expense.date,
            description=expense.description,
            movement_type='DEBIT',
            transaction__isnull=True,
            card_expense__isnull=True,
        ).order_by('-id').first()
        if movement:
            movement.card_expense_id = expense.pk
            movement.save(update_fields=['card_expense'])


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0008_transaction_vr_amount_vrmovement_card_expense_and_more'),
    ]

    operations = [
        migrations.RunPython(link_legacy_card_vr_movements, migrations.RunPython.noop),
    ]
