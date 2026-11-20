from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0028_normalize_uuid_identifiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='financialprofile',
            name='receives_vr',
            field=models.BooleanField(default=True, verbose_name='Recebe VR'),
        ),
    ]
