from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0022_normalize_categories'),
    ]

    operations = [
        migrations.AlterField(
            model_name='creditcardexpense',
            name='series_id',
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True, verbose_name='Série'),
        ),
    ]
