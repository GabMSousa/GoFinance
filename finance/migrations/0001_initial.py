from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nome')),
                ('active', models.BooleanField(default=True, verbose_name='Ativa?')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={'ordering': ['name'], 'verbose_name': 'Categoria', 'verbose_name_plural': 'Categorias'},
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nome')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo?')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={'ordering': ['name'], 'verbose_name': 'Responsável', 'verbose_name_plural': 'Responsáveis'},
        ),
        migrations.CreateModel(
            name='Investment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('type', models.CharField(choices=[('CDB', 'CDB'), ('TREASURY', 'Tesouro'), ('STOCKS', 'Ações'), ('ETF', 'ETF'), ('FII', 'FIIs'), ('CRYPTO', 'Cripto'), ('SAVINGS', 'Poupança'), ('OTHER', 'Outros')], max_length=20, verbose_name='Tipo')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor aplicado')),
                ('current_balance', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Saldo atual')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
            ],
            options={'ordering': ['-date', '-id'], 'verbose_name': 'Investimento', 'verbose_name_plural': 'Investimentos'},
        ),
        migrations.CreateModel(
            name='FixedExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('due_day', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Dia do vencimento')),
                ('payment_method', models.CharField(blank=True, choices=[('PIX', 'Pix'), ('CREDIT_CARD', 'Cartão de crédito'), ('DEBIT', 'Débito'), ('CASH', 'Dinheiro'), ('BOLETO', 'Boleto'), ('VR', 'Vale Refeição')], default='', max_length=20, verbose_name='Forma de pagamento')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo?')),
                ('included_in_credit_card', models.BooleanField(default=False, verbose_name='Incluído no cartão?')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fixed_expenses', to='finance.category', verbose_name='Categoria')),
            ],
            options={'ordering': ['due_day', 'description'], 'verbose_name': 'Gasto fixo', 'verbose_name_plural': 'Gastos fixos'},
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('type', models.CharField(choices=[('REVENUE', 'Receita'), ('EXPENSE', 'Despesa'), ('INVESTMENT', 'Investimento'), ('REIMBURSEMENT', 'Reembolso')], max_length=20, verbose_name='Tipo')),
                ('payment_method', models.CharField(choices=[('PIX', 'Pix'), ('CREDIT_CARD', 'Cartão de crédito'), ('DEBIT', 'Débito'), ('CASH', 'Dinheiro'), ('BOLETO', 'Boleto'), ('VR', 'Vale Refeição')], max_length=20, verbose_name='Forma de pagamento')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('paid', models.BooleanField(default=False, verbose_name='Pago?')),
                ('fixed_expense', models.BooleanField(default=False, verbose_name='É gasto fixo?')),
                ('reimbursable', models.BooleanField(default=False, verbose_name='Reembolsável?')),
                ('received', models.BooleanField(default=False, verbose_name='Recebido?')),
                ('installment_current', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Parcela atual')),
                ('installment_total', models.PositiveSmallIntegerField(default=1, verbose_name='Total de parcelas')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('revenue_type', models.CharField(blank=True, choices=[('SALARY', 'Salário'), ('EXTRA', 'Renda extra'), ('SALE', 'Venda'), ('REIMBURSEMENT', 'Reembolso'), ('OTHER', 'Outros')], default='', max_length=20, verbose_name='Tipo de receita')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='finance.category', verbose_name='Categoria')),
                ('person', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='finance.person', verbose_name='Responsável')),
            ],
            options={'ordering': ['-date', '-id'], 'verbose_name': 'Lançamento', 'verbose_name_plural': 'Lançamentos'},
        ),
        migrations.CreateModel(
            name='CreditCardExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data da parcela')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor da parcela')),
                ('current_installment', models.PositiveSmallIntegerField(default=1, verbose_name='Parcela atual')),
                ('total_installments', models.PositiveSmallIntegerField(default=1, verbose_name='Total de parcelas')),
                ('reimbursable', models.BooleanField(default=False, verbose_name='Reembolsável?')),
                ('received', models.BooleanField(default=False, verbose_name='Recebido?')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('total_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Valor total da compra')),
                ('first_installment', models.DateField(blank=True, null=True, verbose_name='Primeira parcela')),
                ('last_installment', models.DateField(blank=True, null=True, verbose_name='Última parcela')),
                ('series_id', models.UUIDField(blank=True, db_index=True, null=True, verbose_name='Série')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='card_expenses', to='finance.category', verbose_name='Categoria')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='card_expenses', to='finance.person', verbose_name='Responsável')),
            ],
            options={'ordering': ['-date', '-id'], 'verbose_name': 'Gasto no cartão', 'verbose_name_plural': 'Gastos no cartão'},
        ),
        migrations.CreateModel(
            name='VRMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('movement_type', models.CharField(choices=[('CREDIT', 'Crédito'), ('DEBIT', 'Gasto'), ('ADJUSTMENT', 'Ajuste')], max_length=20, verbose_name='Tipo')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('transaction', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vr_movements', to='finance.transaction', verbose_name='Lançamento')),
            ],
            options={'ordering': ['-date', '-id'], 'verbose_name': 'Movimento de VR', 'verbose_name_plural': 'Movimentos de VR'},
        ),
    ]
