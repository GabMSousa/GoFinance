from datetime import date

from django.db import migrations, models


def next_month(period):
    if period.month == 12:
        return date(period.year + 1, 1, 1)
    return date(period.year, period.month + 1, 1)


def shift_receipts_to_display_month(apps, schema_editor):
    VRMovement = apps.get_model('finance', 'VRMovement')
    used = set()
    receipts = VRMovement.objects.filter(
        movement_type='CREDIT',
        reference_month__isnull=False,
    ).order_by('-reference_month', '-id')
    for movement in receipts.iterator():
        target = next_month(movement.reference_month)
        key = (movement.owner_id, target)
        if key in used:
            continue
        movement.reference_month = target
        movement.save(update_fields=['reference_month'])
        used.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0025_vrmovement_reference_month_and_more'),
    ]

    operations = [
        migrations.RunPython(shift_receipts_to_display_month, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='vrmovement',
            name='reference_month',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='Mês de referência'),
        ),
    ]
