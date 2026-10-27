from django.db import migrations


CANONICAL_NAMES = {
    'Combust\u251c\u00a1vel': 'Combust\u00edvel',
    'Sa\u251c\u2551de': 'Sa\u00fade',
}


def normalize_categories(apps, schema_editor):
    Category = apps.get_model('finance', 'Category')
    related_models = [
        apps.get_model('finance', 'Transaction'),
        apps.get_model('finance', 'FixedExpense'),
        apps.get_model('finance', 'CreditCardExpense'),
        apps.get_model('finance', 'Investment'),
    ]

    for category in Category.objects.order_by('id'):
        canonical_name = CANONICAL_NAMES.get(category.name)
        if not canonical_name:
            continue

        keeper = Category.objects.filter(
            owner_id=category.owner_id,
            name=canonical_name,
        ).exclude(pk=category.pk).order_by('id').first()

        if keeper is None:
            category.name = canonical_name
            category.save(update_fields=['name'])
            continue

        for model in related_models:
            model.objects.filter(category_id=category.pk).update(category_id=keeper.pk)
        category.delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0021_alter_investmentoperation_operation_key'),
    ]

    operations = [
        migrations.RunPython(normalize_categories, noop),
    ]
