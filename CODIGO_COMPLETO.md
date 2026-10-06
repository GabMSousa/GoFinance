# Código completo por arquivo

O projeto real permanece separado em múltiplos arquivos. Este documento é apenas uma cópia consolidada para revisão.

## Arquivo
`.gitignore`

```text
.venv/
__pycache__/
*.pyc
db.sqlite3
staticfiles/
.env
```

## Arquivo
`ETAPAS.md`

```markdown
# Entrega por etapas

## 1. Criar projeto Django
Arquivos: `manage.py`, `finance_control/settings.py`, `finance_control/urls.py`, `finance_control/wsgi.py`, `finance_control/asgi.py`, `finance/apps.py`, `requirements.txt`.

## 2. Criar models
Arquivo: `finance/models.py`.
Models: `Category`, `Person`, `Transaction`, `FixedExpense`, `CreditCardExpense`, `Investment`, `VRMovement`.

## 3. Criar migrations
Arquivo: `finance/migrations/0001_initial.py`.

## 4. Criar admin
Arquivo: `finance/admin.py`.

## 5. Criar telas
Arquivos em `finance/templates/finance/` e `finance/static/finance/css/app.css`.

## 6. Criar formulários
Arquivo: `finance/forms.py`.
Inclui formulários CRUD, compra parcelada e `+ Novo Gasto` com pagamento dividido usando VR.

## 7. Criar dashboard
Arquivos: `finance/views.py`, `finance/services.py`, `finance/templates/finance/dashboard.html`.

## 8. Criar gráficos
Arquivo: `finance/templates/finance/dashboard.html`.
Gráficos Chart.js: receitas x despesas, categoria, evolução mensal, fixos x variáveis e cartão x fora do cartão.

## 9. Criar filtros
Arquivos: `finance/views.py` e `finance/templates/finance/transaction_list.html`.
Filtros: mês, ano, descrição, categoria, pagamento e responsável.

## 10. Criar deploy
Arquivos: `deploy/financeiro.service`, `deploy/nginx.conf`, `README.md`.
Inclui modo simples com `runserver 0.0.0.0:8000` e modelo de Gunicorn + Nginx.

## Dados iniciais
Comando: `python manage.py seed_initial_data`.
Arquivo: `finance/management/commands/seed_initial_data.py`.
```

## Arquivo
`README.md`

```markdown
# Financeiro Pessoal

Sistema web pessoal para controle financeiro, feito com Django + SQLite + Bootstrap 5 + Chart.js.

## Requisitos

- Python 3.10 ou superior
- pip

## Instalação local / servidor interno

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_initial_data
python manage.py runserver 0.0.0.0:8000
```

Acesse `http://IP_DO_SERVIDOR:8000`.

## Dados iniciais

Categorias solicitadas, responsáveis `Eu`, `Vitória`, `Outro` e os seguintes gastos fixos são criados pelo comando `seed_initial_data`:

- Moto: R$ 660,06
- Seguro Connecta: R$ 159,74 — incluído no cartão
- Internet: R$ 99,90
- Faculdade: R$ 216,89
- Spotify: R$ 23,90
- Academia: R$ 70,00

Dias de vencimento e formas de pagamento que não foram informados ficam em branco para serem definidos pela interface.

O Vale Refeição usa crédito mensal padrão de R$ 500,00 em `finance_control/settings.py` (`VR_MONTHLY_CREDIT`).

## Regras principais

- Gasto fixo com `Incluído no cartão = Sim` entra na fatura calculada e não é somado novamente fora do cartão.
- Compra de cartão parcelada gera automaticamente uma linha por parcela, distribuída mês a mês.
- Gasto de terceiro entra na fatura; quando marcado como recebido, o valor é tratado como reembolso no fluxo do mês.
- No botão `+ Novo Gasto`, o campo `Valor pago com VR` permite dividir uma compra entre VR e outro meio. Apenas o restante reduz o saldo financeiro.
- VR não entra como salário/receita bancária.
- Investimentos reduzem o saldo disponível do mês, mas são exibidos separadamente das despesas de consumo.

## Produção com Gunicorn + Nginx

1. Copie o projeto para `/opt/financeiro_pessoal`.
2. Crie o usuário Linux de serviço ou ajuste `deploy/financeiro.service`.
3. Crie o ambiente virtual e instale `requirements.txt`.
4. Execute:

```bash
python manage.py migrate
python manage.py seed_initial_data
python manage.py collectstatic --noinput
```

5. Copie `deploy/financeiro.service` para `/etc/systemd/system/financeiro.service` e ajuste IP/hostname/SECRET_KEY.
6. Copie `deploy/nginx.conf` para `/etc/nginx/sites-available/financeiro` e habilite o site.
7. Valide e reinicie Nginx/Gunicorn.

## Backup

O banco é o arquivo `db.sqlite3`. Com o serviço parado ou usando backup consistente, copie esse arquivo para outro local.
```

## Arquivo
`deploy/financeiro.service`

```ini
[Unit]
Description=Financeiro Pessoal Django
After=network.target

[Service]
User=financeiro
Group=www-data
WorkingDirectory=/opt/financeiro_pessoal
Environment="DJANGO_DEBUG=0"
Environment="DJANGO_ALLOWED_HOSTS=192.168.0.10,financeiro.local"
Environment="DJANGO_SECRET_KEY=ALTERE_PARA_UMA_CHAVE_FORTE"
ExecStart=/opt/financeiro_pessoal/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 finance_control.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

## Arquivo
`deploy/nginx.conf`

```nginx
server {
    listen 80;
    server_name financeiro.local 192.168.0.10;

    location /static/ {
        alias /opt/financeiro_pessoal/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Arquivo
`finance/__init__.py`

```python

```

## Arquivo
`finance/admin.py`

```python
from django.contrib import admin
from .models import Category, CreditCardExpense, FixedExpense, Investment, Person, Transaction, VRMovement

admin.site.register(Category)
admin.site.register(Person)
admin.site.register(Transaction)
admin.site.register(FixedExpense)
admin.site.register(CreditCardExpense)
admin.site.register(Investment)
admin.site.register(VRMovement)
```

## Arquivo
`finance/apps.py`

```python
from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = 'Financeiro'
```

## Arquivo
`finance/forms.py`

```python
from django import forms
from .models import Category, CreditCardExpense, FixedExpense, Investment, Transaction, VRMovement


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = 'form-control' if not isinstance(field.widget, forms.Select) else 'form-select'


class CategoryForm(BootstrapModelForm):
    class Meta:
        model = Category
        fields = ['name', 'active']


class TransactionForm(BootstrapModelForm):
    class Meta:
        model = Transaction
        fields = ['date', 'description', 'category', 'transaction_type', 'revenue_type', 'payment_method', 'value', 'paid', 'is_fixed', 'person', 'reimbursable', 'received', 'installment_current', 'installments_total', 'notes']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 3})}


class FixedExpenseForm(BootstrapModelForm):
    class Meta:
        model = FixedExpense
        fields = ['description', 'category', 'value', 'due_day', 'payment_method', 'active', 'included_in_card']


class CreditCardExpenseForm(BootstrapModelForm):
    class Meta:
        model = CreditCardExpense
        fields = ['date', 'description', 'category', 'value', 'total_purchase_value', 'person', 'installment_current', 'installments_total', 'first_installment', 'last_installment', 'reimbursable', 'received', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'first_installment': forms.DateInput(attrs={'type': 'date'}),
            'last_installment': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class InvestmentForm(BootstrapModelForm):
    class Meta:
        model = Investment
        fields = ['date', 'description', 'investment_type', 'applied_value', 'current_balance', 'notes']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 3})}


class VRMovementForm(BootstrapModelForm):
    class Meta:
        model = VRMovement
        fields = ['date', 'description', 'movement_type', 'amount', 'category', 'notes']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 3})}


class QuickExpenseForm(forms.Form):
    date = forms.DateField(label='Data', widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    description = forms.CharField(label='Descrição', max_length=180, widget=forms.TextInput(attrs={'class': 'form-control'}))
    category = forms.ModelChoiceField(label='Categoria', queryset=Category.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    payment_method = forms.ChoiceField(label='Forma de pagamento do restante', choices=Transaction.PaymentMethod.choices, widget=forms.Select(attrs={'class': 'form-select'}))
    total_value = forms.DecimalField(label='Valor total', min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    vr_amount = forms.DecimalField(label='Valor pago com VR', min_value=0, decimal_places=2, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    person = forms.ModelChoiceField(label='Responsável', queryset=Transaction._meta.get_field('person').remote_field.model.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    paid = forms.BooleanField(label='Pago?', required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    reimbursable = forms.BooleanField(label='Reembolsável?', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    received = forms.BooleanField(label='Recebido?', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    installments_total = forms.IntegerField(label='Total de parcelas', min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    notes = forms.CharField(label='Observações', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Person
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['person'].queryset = Person.objects.filter(active=True)

    def clean(self):
        data = super().clean()
        total = data.get('total_value') or 0
        vr_amount = data.get('vr_amount') or 0
        if vr_amount > total:
            self.add_error('vr_amount', 'O valor pago com VR não pode ser maior que o total da compra.')
        return data


class CardPurchaseForm(forms.Form):
    date = forms.DateField(label='Primeira parcela', widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    description = forms.CharField(label='Descrição', max_length=180, widget=forms.TextInput(attrs={'class': 'form-control'}))
    category = forms.ModelChoiceField(label='Categoria', queryset=Category.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    total_value = forms.DecimalField(label='Valor total da compra', min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    person = forms.ModelChoiceField(label='Responsável', queryset=Transaction._meta.get_field('person').remote_field.model.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    installments_total = forms.IntegerField(label='Quantidade de parcelas', min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    reimbursable = forms.BooleanField(label='Reembolsável?', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    received = forms.BooleanField(label='Recebido?', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    notes = forms.CharField(label='Observações', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Person
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['person'].queryset = Person.objects.filter(active=True)
```

## Arquivo
`finance/management/__init__.py`

```python

```

## Arquivo
`finance/management/commands/__init__.py`

```python

```

## Arquivo
`finance/management/commands/seed_initial_data.py`

```python
from decimal import Decimal
from django.core.management.base import BaseCommand
from finance.models import Category, FixedExpense, Person, Transaction


class Command(BaseCommand):
    help = 'Cria categorias, responsáveis e gastos fixos iniciais.'

    def handle(self, *args, **options):
        categories = [
            'Alimentação', 'Restaurante', 'Mercado', 'Moto', 'Combustível',
            'Transporte', 'Internet', 'Faculdade', 'Academia', 'Assinaturas',
            'Compras', 'Lazer', 'Saúde', 'Investimentos', 'Outros',
        ]
        for name in categories:
            Category.objects.get_or_create(name=name)

        eu, _ = Person.objects.get_or_create(name='Eu', defaults={'is_self': True})
        if not eu.is_self:
            eu.is_self = True
            eu.save(update_fields=['is_self'])
        Person.objects.get_or_create(name='Vitória')
        Person.objects.get_or_create(name='Outro')

        initial_fixed = [
            ('Moto', 'Moto', Decimal('660.06'), False),
            ('Seguro Connecta', 'Assinaturas', Decimal('159.74'), True),
            ('Internet', 'Internet', Decimal('99.90'), False),
            ('Faculdade', 'Faculdade', Decimal('216.89'), False),
            ('Spotify', 'Assinaturas', Decimal('23.90'), False),
            ('Academia', 'Academia', Decimal('70.00'), False),
        ]
        for description, category_name, value, included_in_card in initial_fixed:
            category = Category.objects.get(name=category_name)
            FixedExpense.objects.get_or_create(
                description=description,
                defaults={
                    'category': category,
                    'value': value,
                    'active': True,
                    'included_in_card': included_in_card,
                    'payment_method': Transaction.PaymentMethod.CREDIT_CARD if included_in_card else '',
                },
            )

        self.stdout.write(self.style.SUCCESS('Dados iniciais criados/validados.'))
```

## Arquivo
`finance/migrations/0001_initial.py`

```python
from decimal import Decimal
import uuid
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
            ],
            options={'verbose_name': 'Categoria', 'verbose_name_plural': 'Categorias', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nome')),
                ('is_self', models.BooleanField(default=False, verbose_name='Sou eu?')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo?')),
            ],
            options={'verbose_name': 'Responsável', 'verbose_name_plural': 'Responsáveis', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Investment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('investment_type', models.CharField(choices=[('CDB','CDB'),('TREASURY','Tesouro'),('STOCKS','Ações'),('ETF','ETF'),('FII','FIIs'),('CRYPTO','Cripto'),('SAVINGS','Poupança'),('OTHER','Outros')], max_length=20, verbose_name='Tipo')),
                ('applied_value', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor aplicado')),
                ('current_balance', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Saldo atual')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
            ],
            options={'verbose_name': 'Investimento', 'verbose_name_plural': 'Investimentos', 'ordering': ['-date','-id']},
        ),
        migrations.CreateModel(
            name='FixedExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('value', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('due_day', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Dia do vencimento')),
                ('payment_method', models.CharField(blank=True, choices=[('PIX','Pix'),('CREDIT_CARD','Cartão de crédito'),('DEBIT','Débito'),('CASH','Dinheiro'),('BOLETO','Boleto'),('VR','Vale Refeição')], default='', max_length=20, verbose_name='Forma de pagamento')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo?')),
                ('included_in_card', models.BooleanField(default=False, verbose_name='Incluído no cartão?')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fixed_expenses', to='finance.category', verbose_name='Categoria')),
            ],
            options={'verbose_name': 'Gasto fixo', 'verbose_name_plural': 'Gastos fixos', 'ordering': ['due_day','description']},
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('transaction_type', models.CharField(choices=[('REVENUE','Receita'),('EXPENSE','Despesa'),('INVESTMENT','Investimento'),('REIMBURSEMENT','Reembolso')], max_length=20, verbose_name='Tipo')),
                ('revenue_type', models.CharField(blank=True, choices=[('SALARY','Salário'),('EXTRA','Renda extra'),('SALE','Venda'),('REIMBURSEMENT','Reembolso'),('OTHER','Outros')], default='', max_length=20, verbose_name='Tipo de receita')),
                ('payment_method', models.CharField(choices=[('PIX','Pix'),('CREDIT_CARD','Cartão de crédito'),('DEBIT','Débito'),('CASH','Dinheiro'),('BOLETO','Boleto'),('VR','Vale Refeição')], max_length=20, verbose_name='Forma de pagamento')),
                ('value', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('paid', models.BooleanField(default=False, verbose_name='Pago?')),
                ('is_fixed', models.BooleanField(default=False, verbose_name='É gasto fixo?')),
                ('reimbursable', models.BooleanField(default=False, verbose_name='Reembolsável?')),
                ('received', models.BooleanField(default=False, verbose_name='Recebido?')),
                ('installment_current', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Parcela atual')),
                ('installments_total', models.PositiveSmallIntegerField(default=1, verbose_name='Total de parcelas')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='finance.category', verbose_name='Categoria')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='finance.person', verbose_name='Responsável')),
            ],
            options={'verbose_name': 'Lançamento', 'verbose_name_plural': 'Lançamentos', 'ordering': ['-date','-id']},
        ),
        migrations.CreateModel(
            name='CreditCardExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data da parcela')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('value', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor da parcela')),
                ('total_purchase_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Valor total da compra')),
                ('installment_current', models.PositiveSmallIntegerField(default=1, verbose_name='Parcela atual')),
                ('installments_total', models.PositiveSmallIntegerField(default=1, verbose_name='Total de parcelas')),
                ('first_installment', models.DateField(blank=True, null=True, verbose_name='Primeira parcela')),
                ('last_installment', models.DateField(blank=True, null=True, verbose_name='Última parcela')),
                ('reimbursable', models.BooleanField(default=False, verbose_name='Reembolsável?')),
                ('received', models.BooleanField(default=False, verbose_name='Recebido?')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('series_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='card_expenses', to='finance.category', verbose_name='Categoria')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='card_expenses', to='finance.person', verbose_name='Responsável')),
            ],
            options={'verbose_name': 'Gasto no cartão', 'verbose_name_plural': 'Gastos no cartão', 'ordering': ['-date','-id']},
        ),
        migrations.CreateModel(
            name='VRMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data')),
                ('description', models.CharField(max_length=180, verbose_name='Descrição')),
                ('movement_type', models.CharField(choices=[('CREDIT','Crédito'),('DEBIT','Gasto'),('ADJUSTMENT','Ajuste')], max_length=20, verbose_name='Tipo')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('notes', models.TextField(blank=True, verbose_name='Observações')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='vr_movements', to='finance.category', verbose_name='Categoria')),
            ],
            options={'verbose_name': 'Movimento de VR', 'verbose_name_plural': 'Movimentos de VR', 'ordering': ['-date','-id']},
        ),
    ]
```

## Arquivo
`finance/migrations/__init__.py`

```python

```

## Arquivo
`finance/models.py`

```python
import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField('Nome', max_length=100, unique=True)
    active = models.BooleanField('Ativa?', default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return self.name


class Person(models.Model):
    name = models.CharField('Nome', max_length=100, unique=True)
    is_self = models.BooleanField('Sou eu?', default=False)
    active = models.BooleanField('Ativo?', default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Responsável'
        verbose_name_plural = 'Responsáveis'

    def __str__(self):
        return self.name


class Transaction(models.Model):
    class Type(models.TextChoices):
        REVENUE = 'REVENUE', 'Receita'
        EXPENSE = 'EXPENSE', 'Despesa'
        INVESTMENT = 'INVESTMENT', 'Investimento'
        REIMBURSEMENT = 'REIMBURSEMENT', 'Reembolso'

    class RevenueType(models.TextChoices):
        SALARY = 'SALARY', 'Salário'
        EXTRA = 'EXTRA', 'Renda extra'
        SALE = 'SALE', 'Venda'
        REIMBURSEMENT = 'REIMBURSEMENT', 'Reembolso'
        OTHER = 'OTHER', 'Outros'

    class PaymentMethod(models.TextChoices):
        PIX = 'PIX', 'Pix'
        CREDIT_CARD = 'CREDIT_CARD', 'Cartão de crédito'
        DEBIT = 'DEBIT', 'Débito'
        CASH = 'CASH', 'Dinheiro'
        BOLETO = 'BOLETO', 'Boleto'
        VR = 'VR', 'Vale Refeição'

    date = models.DateField('Data')
    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='transactions', verbose_name='Categoria')
    transaction_type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    revenue_type = models.CharField('Tipo de receita', max_length=20, choices=RevenueType.choices, blank=True, default='')
    payment_method = models.CharField('Forma de pagamento', max_length=20, choices=PaymentMethod.choices)
    value = models.DecimalField('Valor', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    paid = models.BooleanField('Pago?', default=False)
    is_fixed = models.BooleanField('É gasto fixo?', default=False)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='transactions', verbose_name='Responsável')
    reimbursable = models.BooleanField('Reembolsável?', default=False)
    received = models.BooleanField('Recebido?', default=False)
    installment_current = models.PositiveSmallIntegerField('Parcela atual', null=True, blank=True)
    installments_total = models.PositiveSmallIntegerField('Total de parcelas', default=1)
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def __str__(self):
        return f'{self.date} - {self.description}'


class FixedExpense(models.Model):
    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='fixed_expenses', verbose_name='Categoria')
    value = models.DecimalField('Valor', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    due_day = models.PositiveSmallIntegerField('Dia do vencimento', null=True, blank=True)
    payment_method = models.CharField('Forma de pagamento', max_length=20, choices=Transaction.PaymentMethod.choices, blank=True, default='')
    active = models.BooleanField('Ativo?', default=True)
    included_in_card = models.BooleanField('Incluído no cartão?', default=False)

    class Meta:
        ordering = ['due_day', 'description']
        verbose_name = 'Gasto fixo'
        verbose_name_plural = 'Gastos fixos'

    def __str__(self):
        return self.description


class CreditCardExpense(models.Model):
    date = models.DateField('Data da parcela')
    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='card_expenses', verbose_name='Categoria')
    value = models.DecimalField('Valor da parcela', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    total_purchase_value = models.DecimalField('Valor total da compra', max_digits=12, decimal_places=2, null=True, blank=True)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='card_expenses', verbose_name='Responsável')
    installment_current = models.PositiveSmallIntegerField('Parcela atual', default=1)
    installments_total = models.PositiveSmallIntegerField('Total de parcelas', default=1)
    first_installment = models.DateField('Primeira parcela', null=True, blank=True)
    last_installment = models.DateField('Última parcela', null=True, blank=True)
    reimbursable = models.BooleanField('Reembolsável?', default=False)
    received = models.BooleanField('Recebido?', default=False)
    notes = models.TextField('Observações', blank=True)
    series_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Gasto no cartão'
        verbose_name_plural = 'Gastos no cartão'

    @property
    def remaining_installments(self):
        return max(self.installments_total - self.installment_current, 0)

    def __str__(self):
        return f'{self.description} ({self.installment_current}/{self.installments_total})'


class Investment(models.Model):
    class Type(models.TextChoices):
        CDB = 'CDB', 'CDB'
        TREASURY = 'TREASURY', 'Tesouro'
        STOCKS = 'STOCKS', 'Ações'
        ETF = 'ETF', 'ETF'
        FII = 'FII', 'FIIs'
        CRYPTO = 'CRYPTO', 'Cripto'
        SAVINGS = 'SAVINGS', 'Poupança'
        OTHER = 'OTHER', 'Outros'

    date = models.DateField('Data')
    description = models.CharField('Descrição', max_length=180)
    investment_type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    applied_value = models.DecimalField('Valor aplicado', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    current_balance = models.DecimalField('Saldo atual', max_digits=12, decimal_places=2, default=0)
    notes = models.TextField('Observações', blank=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'

    def __str__(self):
        return self.description


class VRMovement(models.Model):
    class Type(models.TextChoices):
        CREDIT = 'CREDIT', 'Crédito'
        DEBIT = 'DEBIT', 'Gasto'
        ADJUSTMENT = 'ADJUSTMENT', 'Ajuste'

    date = models.DateField('Data')
    description = models.CharField('Descrição', max_length=180)
    movement_type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    amount = models.DecimalField('Valor', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='vr_movements', null=True, blank=True, verbose_name='Categoria')
    notes = models.TextField('Observações', blank=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Movimento de VR'
        verbose_name_plural = 'Movimentos de VR'

    def __str__(self):
        return f'{self.date} - {self.description}'
```

## Arquivo
`finance/services.py`

```python
from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.db.models import Sum
from .models import CreditCardExpense, FixedExpense, Investment, Transaction, VRMovement

ZERO = Decimal('0.00')


def money_sum(queryset, field):
    return queryset.aggregate(total=Sum(field))['total'] or ZERO


def month_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def monthly_summary(year, month):
    start, end = month_bounds(year, month)
    tx = Transaction.objects.filter(date__range=(start, end))
    card = CreditCardExpense.objects.filter(date__range=(start, end))
    investments = Investment.objects.filter(date__range=(start, end))
    vr = VRMovement.objects.filter(date__range=(start, end))

    revenues = money_sum(tx.filter(transaction_type=Transaction.Type.REVENUE), 'value')
    reimbursements_general = money_sum(tx.filter(transaction_type=Transaction.Type.REIMBURSEMENT, received=True), 'value')
    variable_non_card = money_sum(tx.filter(transaction_type=Transaction.Type.EXPENSE).exclude(payment_method__in=[Transaction.PaymentMethod.CREDIT_CARD, Transaction.PaymentMethod.VR]), 'value')

    fixed_all = FixedExpense.objects.filter(active=True)
    fixed_total = money_sum(fixed_all, 'value')
    fixed_card = money_sum(fixed_all.filter(included_in_card=True), 'value')
    fixed_non_card = fixed_total - fixed_card

    card_manual = money_sum(card, 'value')
    variable_total = variable_non_card + card_manual
    card_invoice = card_manual + fixed_card
    third_party = card.exclude(person__is_self=True)
    third_party_total = money_sum(third_party, 'value')
    third_party_received = money_sum(third_party.filter(received=True), 'value')
    third_party_pending = money_sum(third_party.filter(reimbursable=True, received=False), 'value')
    card_personal_economic = max(card_invoice - third_party_total, ZERO)

    vr_initial = Decimal(str(settings.VR_INITIAL_BALANCE))
    vr_credit = Decimal(str(settings.VR_MONTHLY_CREDIT)) + money_sum(vr.filter(movement_type=VRMovement.Type.CREDIT), 'amount')
    vr_spent = money_sum(vr.filter(movement_type=VRMovement.Type.DEBIT), 'amount') + money_sum(tx.filter(transaction_type=Transaction.Type.EXPENSE, payment_method=Transaction.PaymentMethod.VR), 'value')
    vr_balance = vr_initial + vr_credit - vr_spent

    investment_month = money_sum(investments, 'applied_value')
    investment_total = Investment.objects.aggregate(total=Sum('current_balance'))['total'] or ZERO

    bank_outflow = fixed_non_card + variable_non_card + card_invoice + investment_month
    inflow = revenues + reimbursements_general + third_party_received
    final_balance = inflow - bank_outflow

    category_rows = list(
        tx.filter(transaction_type=Transaction.Type.EXPENSE)
        .values('category__name')
        .annotate(total=Sum('value'))
        .order_by('-total')
    )
    card_categories = list(card.values('category__name').annotate(total=Sum('value')).order_by('-total'))
    fixed_categories = list(fixed_all.values('category__name').annotate(total=Sum('value')).order_by('-total'))
    vr_categories = list(vr.filter(movement_type=VRMovement.Type.DEBIT, category__isnull=False).values('category__name').annotate(total=Sum('amount')).order_by('-total'))
    merged = {}
    for row in category_rows + card_categories + fixed_categories + vr_categories:
        merged[row['category__name']] = merged.get(row['category__name'], ZERO) + row['total']
    category_data = sorted(merged.items(), key=lambda item: item[1], reverse=True)

    return {
        'revenues': revenues,
        'reimbursements': reimbursements_general + third_party_received,
        'fixed_total': fixed_total,
        'fixed_non_card': fixed_non_card,
        'variable_total': variable_total,
        'card_invoice': card_invoice,
        'card_manual': card_manual,
        'card_fixed': fixed_card,
        'third_party_total': third_party_total,
        'third_party_received': third_party_received,
        'third_party_pending': third_party_pending,
        'card_personal_economic': card_personal_economic,
        'vr_initial': vr_initial,
        'vr_credit': vr_credit,
        'vr_spent': vr_spent,
        'vr_balance': vr_balance,
        'investment_month': investment_month,
        'investment_total': investment_total,
        'bank_outflow': bank_outflow,
        'final_balance': final_balance,
        'category_labels': [x[0] for x in category_data],
        'category_values': [float(x[1]) for x in category_data],
    }
```

## Arquivo
`finance/static/finance/css/app.css`

```css
body{background:#f5f7f9;color:#263238}.sidebar{width:240px;background:#1f2933;color:#fff}.sidebar h5{color:#fff}.sidebar .nav-link{color:#cbd5e1;border-radius:.5rem}.sidebar .nav-link:hover{background:#334155;color:#fff}.card{border:0;box-shadow:0 1px 4px rgba(0,0,0,.08)}.metric small{color:#6b7280}.table{background:#fff}.text-warning{color:#b7791f!important}@media(max-width:767px){h2{font-size:1.4rem}.container-fluid{padding:1rem!important}}
```

## Arquivo
`finance/templates/finance/_period.html`

```html
<form method="get" class="row g-2 align-items-end mb-3">
  <div class="col-6 col-md-2"><label class="form-label">Mês</label><select name="month" class="form-select">
    {% for m in "123456789101112"|make_list %}{% endfor %}
    <option value="1" {% if month == 1 %}selected{% endif %}>Janeiro</option><option value="2" {% if month == 2 %}selected{% endif %}>Fevereiro</option><option value="3" {% if month == 3 %}selected{% endif %}>Março</option><option value="4" {% if month == 4 %}selected{% endif %}>Abril</option><option value="5" {% if month == 5 %}selected{% endif %}>Maio</option><option value="6" {% if month == 6 %}selected{% endif %}>Junho</option><option value="7" {% if month == 7 %}selected{% endif %}>Julho</option><option value="8" {% if month == 8 %}selected{% endif %}>Agosto</option><option value="9" {% if month == 9 %}selected{% endif %}>Setembro</option><option value="10" {% if month == 10 %}selected{% endif %}>Outubro</option><option value="11" {% if month == 11 %}selected{% endif %}>Novembro</option><option value="12" {% if month == 12 %}selected{% endif %}>Dezembro</option>
  </select></div>
  <div class="col-4 col-md-2"><label class="form-label">Ano</label><input class="form-control" type="number" name="year" value="{{ year }}"></div>
  <div class="col-2 col-md-1"><button class="btn btn-outline-secondary w-100">OK</button></div>
</form>
```

## Arquivo
`finance/templates/finance/base.html`

```html
{% load static %}
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Financeiro Pessoal{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="{% static 'finance/css/app.css' %}">
</head>
<body>
<div class="d-flex min-vh-100">
  <aside class="sidebar p-3 d-none d-lg-block">
    <h5 class="mb-4">Financeiro</h5>
    <nav class="nav flex-column gap-1">
      <a class="nav-link" href="{% url 'finance:dashboard' %}">Dashboard</a>
      <a class="nav-link" href="{% url 'finance:transaction_list' %}">Lançamentos</a>
      <a class="nav-link" href="{% url 'finance:revenue_list' %}">Receitas</a>
      <a class="nav-link" href="{% url 'finance:fixed_list' %}">Gastos Fixos</a>
      <a class="nav-link" href="{% url 'finance:card_list' %}">Cartão</a>
      <a class="nav-link" href="{% url 'finance:category_list' %}">Categorias</a>
      <a class="nav-link" href="{% url 'finance:third_party' %}">Terceiros</a>
      <a class="nav-link" href="{% url 'finance:vr_list' %}">Vale Refeição</a>
      <a class="nav-link" href="{% url 'finance:investment_list' %}">Investimentos</a>
      <a class="nav-link" href="{% url 'finance:monthly_report' %}">Resumo Mensal</a>
    </nav>
    <a class="btn btn-success w-100 mt-4" href="{% url 'finance:quick_expense' %}">+ Novo Gasto</a>
  </aside>
  <main class="flex-grow-1">
    <nav class="navbar navbar-expand-lg bg-white border-bottom d-lg-none px-3">
      <a class="navbar-brand" href="{% url 'finance:dashboard' %}">Financeiro</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mobileMenu"><span class="navbar-toggler-icon"></span></button>
      <div class="collapse navbar-collapse" id="mobileMenu">
        <div class="navbar-nav py-2">
          <a class="nav-link" href="{% url 'finance:transaction_list' %}">Lançamentos</a><a class="nav-link" href="{% url 'finance:fixed_list' %}">Gastos Fixos</a><a class="nav-link" href="{% url 'finance:card_list' %}">Cartão</a><a class="nav-link" href="{% url 'finance:vr_list' %}">Vale Refeição</a><a class="nav-link" href="{% url 'finance:monthly_report' %}">Resumo Mensal</a>
          <a class="btn btn-success mt-2" href="{% url 'finance:quick_expense' %}">+ Novo Gasto</a>
        </div>
      </div>
    </nav>
    <div class="container-fluid p-3 p-md-4">
      {% for message in messages %}<div class="alert alert-{{ message.tags|default:'info' }}">{{ message }}</div>{% endfor %}
      {% block content %}{% endblock %}
    </div>
  </main>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

## Arquivo
`finance/templates/finance/card_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between"><h2>Cartão</h2><a class="btn btn-primary" href="{% url 'finance:card_create' %}">Nova compra</a></div>{% include 'finance/_period.html' %}<div class="row g-3 mb-3"><div class="col-md-3"><div class="card"><div class="card-body"><small>Fatura atual</small><h5>R$ {{ summary.card_invoice|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Gastos de terceiros</small><h5>R$ {{ summary.third_party_total|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Valor efetivamente meu</small><h5>R$ {{ summary.card_personal_economic|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Próximo mês comprometido</small><h5>R$ {{ next_commitment|floatformat:2 }}</h5></div></div></div></div><div class="table-responsive"><table class="table"><thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Responsável</th><th>Parcela</th><th>Restantes</th><th>Valor</th><th>Reembolso</th><th></th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.description }}</td><td>{{ x.category }}</td><td>{{ x.person }}</td><td>{{ x.installment_current }}/{{ x.installments_total }}</td><td>{{ x.remaining_installments }}</td><td>R$ {{ x.value|floatformat:2 }}</td><td>{% if x.reimbursable %}{% if x.received %}<span class="badge text-bg-success">Recebido</span>{% else %}<span class="badge text-bg-danger">Pendente</span>{% endif %}{% else %}-{% endif %}</td><td><a class="btn btn-sm btn-outline-primary" href="{% url 'finance:card_edit' x.id %}">Editar</a> <a class="btn btn-sm btn-outline-danger" href="{% url 'finance:card_delete' x.id %}">Excluir</a></td></tr>{% empty %}<tr><td colspan="9">Nenhuma compra.</td></tr>{% endfor %}</tbody></table></div><small class="text-muted">A fatura inclui automaticamente os gastos fixos configurados como “Incluído no cartão”.</small>{% endblock %}
```

## Arquivo
`finance/templates/finance/category_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between mb-3"><h2>Categorias</h2><a class="btn btn-primary" href="{% url 'finance:category_create' %}">Nova categoria</a></div><div class="table-responsive"><table class="table"><thead><tr><th>Nome</th><th>Status</th><th></th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.name }}</td><td>{% if x.active %}<span class="badge text-bg-success">Ativa</span>{% else %}<span class="badge text-bg-secondary">Inativa</span>{% endif %}</td><td><a class="btn btn-sm btn-outline-primary" href="{% url 'finance:category_edit' x.id %}">Editar</a> <a class="btn btn-sm btn-outline-danger" href="{% url 'finance:category_delete' x.id %}">Excluir</a></td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/confirm_delete.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="card"><div class="card-body"><h4>Excluir {{ label }}</h4><p>Confirma a exclusão de <strong>{{ object }}</strong>?</p><form method="post">{% csrf_token %}<button class="btn btn-danger">Excluir</button><a class="btn btn-outline-secondary" href="javascript:history.back()">Cancelar</a></form></div></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/dashboard.html`

```html
{% extends 'finance/base.html' %}{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3"><h2>Dashboard</h2><a class="btn btn-success" href="{% url 'finance:quick_expense' %}">+ Novo Gasto</a></div>
{% include 'finance/_period.html' %}
<div class="row g-3 mb-4">
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Receitas</small><h4 class="text-success">R$ {{ summary.revenues|floatformat:2 }}</h4></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Despesas / saídas</small><h4 class="text-danger">R$ {{ summary.bank_outflow|floatformat:2 }}</h4></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Fatura do cartão</small><h4>R$ {{ summary.card_invoice|floatformat:2 }}</h4></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Saldo do mês</small><h4 class="{% if summary.final_balance >= 0 %}text-success{% else %}text-danger{% endif %}">R$ {{ summary.final_balance|floatformat:2 }}</h4></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Gastos fixos</small><h5>R$ {{ summary.fixed_total|floatformat:2 }}</h5></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Gastos variáveis</small><h5>R$ {{ summary.variable_total|floatformat:2 }}</h5></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Terceiros pendente</small><h5 class="text-warning">R$ {{ summary.third_party_pending|floatformat:2 }}</h5></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Saldo do VR</small><h5>R$ {{ summary.vr_balance|floatformat:2 }}</h5></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Aportes do mês</small><h5>R$ {{ summary.investment_month|floatformat:2 }}</h5></div></div></div>
  <div class="col-6 col-xl-3"><div class="card metric"><div class="card-body"><small>Total investido atual</small><h5>R$ {{ summary.investment_total|floatformat:2 }}</h5></div></div></div>
</div>
<div class="row g-3">
  <div class="col-lg-6"><div class="card"><div class="card-body"><h6>Receitas x despesas</h6><canvas id="incomeExpense"></canvas></div></div></div>
  <div class="col-lg-6"><div class="card"><div class="card-body"><h6>Gastos por categoria</h6><canvas id="categories"></canvas></div></div></div>
  <div class="col-lg-6"><div class="card"><div class="card-body"><h6>Evolução mensal</h6><canvas id="history"></canvas></div></div></div>
  <div class="col-lg-6"><div class="card"><div class="card-body"><h6>Fixos x variáveis</h6><canvas id="fixedVariable"></canvas></div></div></div>
  <div class="col-lg-6"><div class="card"><div class="card-body"><h6>Cartão x fora do cartão</h6><canvas id="cardOutside"></canvas></div></div></div>
</div>
{% endblock %}
{% block scripts %}<script>
new Chart(document.getElementById('incomeExpense'), {type:'bar',data:{labels:['Receitas','Despesas'],datasets:[{data:[{{ summary.revenues }},{{ summary.bank_outflow }}]}]},options:{plugins:{legend:{display:false}}}});
new Chart(document.getElementById('categories'), {type:'doughnut',data:{labels:{{ summary.category_labels|safe }},datasets:[{data:{{ summary.category_values|safe }}}]}});
new Chart(document.getElementById('history'), {type:'line',data:{labels:{{ summary.history_labels|safe }},datasets:[{label:'Entradas',data:{{ summary.history_income|safe }}},{label:'Saídas',data:{{ summary.history_expense|safe }}}]}});
new Chart(document.getElementById('fixedVariable'), {type:'doughnut',data:{labels:['Fixos','Variáveis'],datasets:[{data:[{{ summary.fixed_total }},{{ summary.variable_total }}]}]}});
new Chart(document.getElementById('cardOutside'), {type:'doughnut',data:{labels:['Cartão','Fora do cartão'],datasets:[{data:[{{ summary.card_invoice }},{{ summary.fixed_non_card|add:summary.variable_total }}]}]}});
</script>{% endblock %}
```

## Arquivo
`finance/templates/finance/fixed_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between mb-3"><div><h2>Gastos Fixos</h2><p class="text-muted">Total ativo: R$ {{ total|floatformat:2 }}</p></div><a class="btn btn-primary align-self-start" href="{% url 'finance:fixed_create' %}">Novo gasto fixo</a></div><div class="table-responsive"><table class="table"><thead><tr><th>Descrição</th><th>Categoria</th><th>Valor</th><th>Venc.</th><th>Pagamento</th><th>Cartão?</th><th>Status</th><th></th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.description }}</td><td>{{ x.category }}</td><td>R$ {{ x.value|floatformat:2 }}</td><td>{% if x.due_day %}Dia {{ x.due_day }}{% else %}—{% endif %}</td><td>{{ x.get_payment_method_display|default:'—' }}</td><td>{% if x.included_in_card %}<span class="badge text-bg-warning">Sim</span>{% else %}Não{% endif %}</td><td>{% if x.active %}<span class="badge text-bg-success">Ativo</span>{% else %}Inativo{% endif %}</td><td><a class="btn btn-sm btn-outline-primary" href="{% url 'finance:fixed_edit' x.id %}">Editar</a> <a class="btn btn-sm btn-outline-danger" href="{% url 'finance:fixed_delete' x.id %}">Excluir</a></td></tr>{% endfor %}</tbody></table></div><div class="alert alert-info">Gastos fixos marcados como “Incluído no cartão” entram na fatura calculada e não são somados novamente fora do cartão.</div>{% endblock %}
```

## Arquivo
`finance/templates/finance/form.html`

```html
{% extends 'finance/base.html' %}{% block content %}<h2 class="mb-3">{{ title }}</h2><div class="card"><div class="card-body"><form method="post">{% csrf_token %}<div class="row g-3">{% for field in form %}<div class="{% if field.field.widget.input_type == 'checkbox' %}col-6 col-md-3{% else %}col-12 col-md-6{% endif %}">{% if field.field.widget.input_type == 'checkbox' %}<div class="form-check mt-4">{{ field }} {{ field.label_tag }}</div>{% else %}{{ field.label_tag }}{{ field }}{% endif %}{% if field.errors %}<div class="text-danger small">{{ field.errors|striptags }}</div>{% endif %}</div>{% endfor %}</div><div class="mt-4"><button class="btn btn-primary">Salvar</button><a href="javascript:history.back()" class="btn btn-outline-secondary">Cancelar</a></div></form></div></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/investment_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between"><h2>Investimentos</h2><a class="btn btn-primary" href="{% url 'finance:investment_create' %}">Novo investimento</a></div>{% include 'finance/_period.html' %}<p>Aportes do mês: <strong>R$ {{ month_total|floatformat:2 }}</strong> | Saldo atual informado: <strong>R$ {{ balance_total|floatformat:2 }}</strong></p><div class="table-responsive"><table class="table"><thead><tr><th>Data</th><th>Descrição</th><th>Tipo</th><th>Aporte</th><th>Saldo atual</th><th></th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.description }}</td><td>{{ x.get_investment_type_display }}</td><td>R$ {{ x.applied_value|floatformat:2 }}</td><td>R$ {{ x.current_balance|floatformat:2 }}</td><td><a class="btn btn-sm btn-outline-primary" href="{% url 'finance:investment_edit' x.id %}">Editar</a> <a class="btn btn-sm btn-outline-danger" href="{% url 'finance:investment_delete' x.id %}">Excluir</a></td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/monthly_report.html`

```html
{% extends 'finance/base.html' %}{% block content %}<h2>Resumo Mensal</h2>{% include 'finance/_period.html' %}<div class="card"><div class="card-body"><table class="table mb-0"><tbody><tr><th>Receitas</th><td class="text-end text-success">R$ {{ summary.revenues|floatformat:2 }}</td></tr><tr><th>Fixos</th><td class="text-end">R$ {{ summary.fixed_total|floatformat:2 }}</td></tr><tr><th>Variáveis</th><td class="text-end">R$ {{ summary.variable_total|floatformat:2 }}</td></tr><tr><th>Cartão</th><td class="text-end">R$ {{ summary.card_invoice|floatformat:2 }}</td></tr><tr><th>Terceiros</th><td class="text-end">R$ {{ summary.third_party_total|floatformat:2 }}</td></tr><tr><th>Reembolsos recebidos</th><td class="text-end text-success">R$ {{ summary.reimbursements|floatformat:2 }}</td></tr><tr><th>VR utilizado</th><td class="text-end">R$ {{ summary.vr_spent|floatformat:2 }}</td></tr><tr><th>Saldo VR</th><td class="text-end">R$ {{ summary.vr_balance|floatformat:2 }}</td></tr><tr><th>Investimentos</th><td class="text-end">R$ {{ summary.investment_month|floatformat:2 }}</td></tr><tr class="table-light"><th>Saldo final</th><td class="text-end fw-bold {% if summary.final_balance >= 0 %}text-success{% else %}text-danger{% endif %}">R$ {{ summary.final_balance|floatformat:2 }}</td></tr></tbody></table></div></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/revenue_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between"><div><h2>Receitas</h2><p>Total: <strong class="text-success">R$ {{ total|floatformat:2 }}</strong></p></div><a class="btn btn-primary align-self-start" href="{% url 'finance:transaction_create' %}">Nova receita</a></div>{% include 'finance/_period.html' %}<div class="table-responsive"><table class="table"><thead><tr><th>Data</th><th>Descrição</th><th>Tipo</th><th>Categoria da receita</th><th>Valor</th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.description }}</td><td>{{ x.get_transaction_type_display }}</td><td>{{ x.get_revenue_type_display|default:'—' }}</td><td>R$ {{ x.value|floatformat:2 }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/third_party.html`

```html
{% extends 'finance/base.html' %}{% block content %}<h2>Terceiros</h2>{% include 'finance/_period.html' %}<div class="row g-3 mb-3"><div class="col-md-4"><div class="card"><div class="card-body"><small>Total gasto por terceiros</small><h5>R$ {{ summary.third_party_total|floatformat:2 }}</h5></div></div></div><div class="col-md-4"><div class="card"><div class="card-body"><small>Total recebido</small><h5 class="text-success">R$ {{ summary.third_party_received|floatformat:2 }}</h5></div></div></div><div class="col-md-4"><div class="card"><div class="card-body"><small>Total pendente</small><h5 class="text-danger">R$ {{ summary.third_party_pending|floatformat:2 }}</h5></div></div></div></div><div class="table-responsive"><table class="table"><thead><tr><th>Data</th><th>Responsável</th><th>Descrição</th><th>Valor</th><th>Status</th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.person }}</td><td>{{ x.description }}</td><td>R$ {{ x.value|floatformat:2 }}</td><td>{% if x.received %}<span class="badge text-bg-success">Recebido</span>{% else %}<span class="badge text-bg-danger">Pendente</span>{% endif %}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/transaction_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between"><h2>Lançamentos</h2><a class="btn btn-primary" href="{% url 'finance:transaction_create' %}">Novo lançamento</a></div>{% include 'finance/_period.html' %}
<form method="get" class="row g-2 mb-3"><input type="hidden" name="month" value="{{ month }}"><input type="hidden" name="year" value="{{ year }}"><div class="col-md-3"><input class="form-control" name="q" value="{{ request.GET.q }}" placeholder="Pesquisar descrição"></div><div class="col-md-2"><select class="form-select" name="category"><option value="">Categoria</option>{% for c in categories %}<option value="{{ c.id }}">{{ c }}</option>{% endfor %}</select></div><div class="col-md-2"><select class="form-select" name="payment"><option value="">Pagamento</option>{% for v,l in payment_choices %}<option value="{{ v }}">{{ l }}</option>{% endfor %}</select></div><div class="col-md-2"><select class="form-select" name="person"><option value="">Responsável</option>{% for p in people %}<option value="{{ p.id }}">{{ p }}</option>{% endfor %}</select></div><div class="col-md-2"><button class="btn btn-outline-secondary">Filtrar</button></div></form>
<div class="table-responsive"><table class="table table-hover align-middle"><thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Tipo</th><th>Pagamento</th><th>Responsável</th><th>Valor</th><th></th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.description }}</td><td>{{ x.category }}</td><td><span class="badge {% if x.transaction_type == 'REVENUE' %}text-bg-success{% else %}text-bg-secondary{% endif %}">{{ x.get_transaction_type_display }}</span></td><td>{{ x.get_payment_method_display }}</td><td>{{ x.person }}</td><td>R$ {{ x.value|floatformat:2 }}</td><td class="text-nowrap"><a class="btn btn-sm btn-outline-primary" href="{% url 'finance:transaction_edit' x.id %}">Editar</a> <a class="btn btn-sm btn-outline-danger" href="{% url 'finance:transaction_delete' x.id %}">Excluir</a></td></tr>{% empty %}<tr><td colspan="8">Nenhum lançamento.</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/templates/finance/vr_list.html`

```html
{% extends 'finance/base.html' %}{% block content %}<div class="d-flex justify-content-between"><h2>Vale Refeição</h2><a class="btn btn-primary" href="{% url 'finance:vr_create' %}">Novo movimento</a></div>{% include 'finance/_period.html' %}<div class="row g-3 mb-3"><div class="col-md-3"><div class="card"><div class="card-body"><small>Saldo inicial</small><h5>R$ {{ summary.vr_initial|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Crédito mensal</small><h5>R$ {{ summary.vr_credit|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Gastos</small><h5>R$ {{ summary.vr_spent|floatformat:2 }}</h5></div></div></div><div class="col-md-3"><div class="card"><div class="card-body"><small>Saldo atual do mês</small><h5>R$ {{ summary.vr_balance|floatformat:2 }}</h5></div></div></div></div><div class="table-responsive"><table class="table"><thead><tr><th>Data</th><th>Descrição</th><th>Tipo</th><th>Valor</th></tr></thead><tbody>{% for x in items %}<tr><td>{{ x.date|date:'d/m/Y' }}</td><td>{{ x.description }}</td><td>{{ x.get_movement_type_display }}</td><td>R$ {{ x.amount|floatformat:2 }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

## Arquivo
`finance/urls.py`

```python
from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('lancamentos/', views.transaction_list, name='transaction_list'),
    path('lancamentos/novo/', views.transaction_create, name='transaction_create'),
    path('novo-gasto/', views.quick_expense, name='quick_expense'),
    path('lancamentos/<int:pk>/editar/', views.transaction_edit, name='transaction_edit'),
    path('lancamentos/<int:pk>/excluir/', views.transaction_delete, name='transaction_delete'),
    path('receitas/', views.revenue_list, name='revenue_list'),
    path('categorias/', views.category_list, name='category_list'),
    path('categorias/nova/', views.category_create, name='category_create'),
    path('categorias/<int:pk>/editar/', views.category_edit, name='category_edit'),
    path('categorias/<int:pk>/excluir/', views.category_delete, name='category_delete'),
    path('gastos-fixos/', views.fixed_list, name='fixed_list'),
    path('gastos-fixos/novo/', views.fixed_create, name='fixed_create'),
    path('gastos-fixos/<int:pk>/editar/', views.fixed_edit, name='fixed_edit'),
    path('gastos-fixos/<int:pk>/excluir/', views.fixed_delete, name='fixed_delete'),
    path('cartao/', views.card_list, name='card_list'),
    path('cartao/novo/', views.card_create, name='card_create'),
    path('cartao/<int:pk>/editar/', views.card_edit, name='card_edit'),
    path('cartao/<int:pk>/excluir/', views.card_delete, name='card_delete'),
    path('terceiros/', views.third_party, name='third_party'),
    path('vale-refeicao/', views.vr_list, name='vr_list'),
    path('vale-refeicao/novo/', views.vr_create, name='vr_create'),
    path('investimentos/', views.investment_list, name='investment_list'),
    path('investimentos/novo/', views.investment_create, name='investment_create'),
    path('investimentos/<int:pk>/editar/', views.investment_edit, name='investment_edit'),
    path('investimentos/<int:pk>/excluir/', views.investment_delete, name='investment_delete'),
    path('resumo-mensal/', views.monthly_report, name='monthly_report'),
]
```

## Arquivo
`finance/views.py`

```python
import calendar
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .forms import CardPurchaseForm, CategoryForm, CreditCardExpenseForm, FixedExpenseForm, InvestmentForm, QuickExpenseForm, TransactionForm, VRMovementForm
from .models import Category, CreditCardExpense, FixedExpense, Investment, Person, Transaction, VRMovement
from .services import monthly_summary, money_sum


def selected_period(request):
    today = date.today()
    try:
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
        if month not in range(1, 13):
            raise ValueError
    except ValueError:
        month, year = today.month, today.year
    return year, month


def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def create_card_installments(data, amount_key='total_value'):
    total = Decimal(data[amount_key])
    count = int(data.get('installments_total') or 1)
    per = (total / count).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    series = uuid.uuid4()
    first_date = data['date']
    last_date = add_months(first_date, count - 1)
    created = []
    distributed = Decimal('0.00')
    for number in range(1, count + 1):
        value = per if number < count else total - distributed
        distributed += value
        created.append(CreditCardExpense.objects.create(
            date=add_months(first_date, number - 1),
            description=data['description'],
            category=data['category'],
            value=value,
            total_purchase_value=total,
            person=data['person'],
            installment_current=number,
            installments_total=count,
            first_installment=first_date,
            last_installment=last_date,
            reimbursable=data.get('reimbursable', False),
            received=data.get('received', False),
            notes=data.get('notes', ''),
            series_id=series,
        ))
    return created


def dashboard(request):
    year, month = selected_period(request)
    summary = monthly_summary(year, month)
    history_labels, history_income, history_expense = [], [], []
    for offset in range(5, -1, -1):
        base = date(year, month, 1)
        target = add_months(base, -offset)
        item = monthly_summary(target.year, target.month)
        history_labels.append(target.strftime('%m/%Y'))
        history_income.append(float(item['revenues'] + item['reimbursements']))
        history_expense.append(float(item['bank_outflow']))
    summary.update({'history_labels': history_labels, 'history_income': history_income, 'history_expense': history_expense})
    return render(request, 'finance/dashboard.html', {'summary': summary, 'month': month, 'year': year})


def transaction_list(request):
    year, month = selected_period(request)
    qs = Transaction.objects.select_related('category', 'person').filter(date__year=year, date__month=month)
    if request.GET.get('q'):
        qs = qs.filter(description__icontains=request.GET['q'])
    if request.GET.get('category'):
        qs = qs.filter(category_id=request.GET['category'])
    if request.GET.get('payment'):
        qs = qs.filter(payment_method=request.GET['payment'])
    if request.GET.get('person'):
        qs = qs.filter(person_id=request.GET['person'])
    return render(request, 'finance/transaction_list.html', {
        'items': qs, 'month': month, 'year': year,
        'categories': Category.objects.filter(active=True), 'people': Person.objects.filter(active=True),
        'payment_choices': Transaction.PaymentMethod.choices,
    })


def transaction_create(request):
    form = TransactionForm(request.POST or None, initial={'date': date.today(), 'installments_total': 1})
    if form.is_valid():
        d = form.cleaned_data
        if d['transaction_type'] == Transaction.Type.EXPENSE and d['payment_method'] == Transaction.PaymentMethod.CREDIT_CARD:
            create_card_installments({**d, 'total_value': d['value']})
            messages.success(request, 'Compra enviada ao cartão e parcelas criadas.')
            return redirect('finance:card_list')
        if d['transaction_type'] == Transaction.Type.EXPENSE and d['payment_method'] == Transaction.PaymentMethod.VR:
            VRMovement.objects.create(date=d['date'], description=d['description'], movement_type=VRMovement.Type.DEBIT, amount=d['value'], category=d['category'], notes=d['notes'])
            messages.success(request, 'Gasto lançado no Vale Refeição.')
            return redirect('finance:vr_list')
        form.save(); messages.success(request, 'Lançamento salvo.'); return redirect('finance:transaction_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Novo lançamento'})


def transaction_edit(request, pk):
    obj = get_object_or_404(Transaction, pk=pk); form = TransactionForm(request.POST or None, instance=obj)
    if form.is_valid(): form.save(); messages.success(request, 'Lançamento atualizado.'); return redirect('finance:transaction_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar lançamento'})


def transaction_delete(request, pk):
    return delete_object(request, get_object_or_404(Transaction, pk=pk), 'finance:transaction_list', 'lançamento')


def revenue_list(request):
    year, month = selected_period(request)
    items = Transaction.objects.filter(date__year=year, date__month=month, transaction_type__in=[Transaction.Type.REVENUE, Transaction.Type.REIMBURSEMENT]).select_related('category', 'person')
    return render(request, 'finance/revenue_list.html', {'items': items, 'month': month, 'year': year, 'total': money_sum(items, 'value')})


def quick_expense(request):
    form = QuickExpenseForm(request.POST or None, initial={'date': date.today(), 'installments_total': 1, 'vr_amount': 0})
    if form.is_valid():
        d = form.cleaned_data; total = d['total_value']; vr_amount = d['vr_amount']; remaining = total - vr_amount
        if vr_amount > 0:
            VRMovement.objects.create(date=d['date'], description=d['description'], movement_type=VRMovement.Type.DEBIT, amount=vr_amount, category=d['category'], notes=f'Compra dividida. Total: R$ {total}. {d["notes"]}')
        if remaining > 0:
            if d['payment_method'] == Transaction.PaymentMethod.CREDIT_CARD:
                card_data = {**d, 'total_value': remaining}
                create_card_installments(card_data)
            elif d['payment_method'] == Transaction.PaymentMethod.VR:
                VRMovement.objects.create(date=d['date'], description=d['description'], movement_type=VRMovement.Type.DEBIT, amount=remaining, category=d['category'], notes=d['notes'])
            else:
                Transaction.objects.create(date=d['date'], description=d['description'], category=d['category'], transaction_type=Transaction.Type.EXPENSE, payment_method=d['payment_method'], value=remaining, paid=d['paid'], person=d['person'], reimbursable=d['reimbursable'], received=d['received'], installments_total=1, notes=f'Compra dividida. Total: R$ {total}; VR: R$ {vr_amount}. {d["notes"]}')
        messages.success(request, 'Gasto salvo.'); return redirect('finance:dashboard')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Novo gasto'})


def category_list(request): return render(request, 'finance/category_list.html', {'items': Category.objects.all()})
def category_create(request): return model_form_create(request, CategoryForm, 'Nova categoria', 'finance:category_list')
def category_edit(request, pk): return model_form_edit(request, Category, CategoryForm, pk, 'Editar categoria', 'finance:category_list')
def category_delete(request, pk): return delete_object(request, get_object_or_404(Category, pk=pk), 'finance:category_list', 'categoria')

def fixed_list(request): return render(request, 'finance/fixed_list.html', {'items': FixedExpense.objects.select_related('category').all(), 'total': money_sum(FixedExpense.objects.filter(active=True), 'value')})
def fixed_create(request): return model_form_create(request, FixedExpenseForm, 'Novo gasto fixo', 'finance:fixed_list')
def fixed_edit(request, pk): return model_form_edit(request, FixedExpense, FixedExpenseForm, pk, 'Editar gasto fixo', 'finance:fixed_list')
def fixed_delete(request, pk): return delete_object(request, get_object_or_404(FixedExpense, pk=pk), 'finance:fixed_list', 'gasto fixo')


def card_list(request):
    year, month = selected_period(request)
    items = CreditCardExpense.objects.filter(date__year=year, date__month=month).select_related('category', 'person')
    summary = monthly_summary(year, month)
    next_commitment = money_sum(CreditCardExpense.objects.filter(date__year=add_months(date(year, month, 1), 1).year, date__month=add_months(date(year, month, 1), 1).month), 'value')
    return render(request, 'finance/card_list.html', {'items': items, 'summary': summary, 'next_commitment': next_commitment, 'month': month, 'year': year})


def card_create(request):
    form = CardPurchaseForm(request.POST or None, initial={'date': date.today(), 'installments_total': 1})
    if form.is_valid():
        create_card_installments(form.cleaned_data); messages.success(request, 'Compra e parcelas criadas.'); return redirect('finance:card_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Nova compra no cartão'})


def card_edit(request, pk):
    obj = get_object_or_404(CreditCardExpense, pk=pk); form = CreditCardExpenseForm(request.POST or None, instance=obj)
    if form.is_valid(): form.save(); messages.success(request, 'Parcela atualizada.'); return redirect('finance:card_list')
    return render(request, 'finance/form.html', {'form': form, 'title': 'Editar parcela do cartão'})


def card_delete(request, pk): return delete_object(request, get_object_or_404(CreditCardExpense, pk=pk), 'finance:card_list', 'parcela')


def third_party(request):
    year, month = selected_period(request); summary = monthly_summary(year, month)
    items = CreditCardExpense.objects.filter(date__year=year, date__month=month).exclude(person__is_self=True).select_related('person', 'category')
    return render(request, 'finance/third_party.html', {'items': items, 'summary': summary, 'month': month, 'year': year})


def vr_list(request):
    year, month = selected_period(request); summary = monthly_summary(year, month)
    items = VRMovement.objects.filter(date__year=year, date__month=month).select_related('category')
    return render(request, 'finance/vr_list.html', {'items': items, 'summary': summary, 'month': month, 'year': year})
def vr_create(request): return model_form_create(request, VRMovementForm, 'Novo movimento de Vale Refeição', 'finance:vr_list', {'date': date.today()})


def investment_list(request):
    year, month = selected_period(request); items = Investment.objects.filter(date__year=year, date__month=month)
    return render(request, 'finance/investment_list.html', {'items': items, 'month': month, 'year': year, 'month_total': money_sum(items, 'applied_value'), 'balance_total': Investment.objects.aggregate(total=Sum('current_balance'))['total'] or 0})
def investment_create(request): return model_form_create(request, InvestmentForm, 'Novo investimento', 'finance:investment_list', {'date': date.today()})
def investment_edit(request, pk): return model_form_edit(request, Investment, InvestmentForm, pk, 'Editar investimento', 'finance:investment_list')
def investment_delete(request, pk): return delete_object(request, get_object_or_404(Investment, pk=pk), 'finance:investment_list', 'investimento')


def monthly_report(request):
    year, month = selected_period(request); return render(request, 'finance/monthly_report.html', {'summary': monthly_summary(year, month), 'month': month, 'year': year})


def model_form_create(request, form_class, title, redirect_name, initial=None):
    form = form_class(request.POST or None, initial=initial)
    if form.is_valid(): form.save(); messages.success(request, 'Registro salvo.'); return redirect(redirect_name)
    return render(request, 'finance/form.html', {'form': form, 'title': title})


def model_form_edit(request, model, form_class, pk, title, redirect_name):
    obj = get_object_or_404(model, pk=pk); form = form_class(request.POST or None, instance=obj)
    if form.is_valid(): form.save(); messages.success(request, 'Registro atualizado.'); return redirect(redirect_name)
    return render(request, 'finance/form.html', {'form': form, 'title': title})


def delete_object(request, obj, redirect_name, label):
    if request.method == 'POST':
        obj.delete(); messages.success(request, f'{label.capitalize()} excluído.'); return redirect(redirect_name)
    return render(request, 'finance/confirm_delete.html', {'object': obj, 'label': label})
```

## Arquivo
`finance_control/__init__.py`

```python

```

## Arquivo
`finance_control/asgi.py`

```python
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_control.settings')
application = get_asgi_application()
```

## Arquivo
`finance_control/settings.py`

```python
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'finance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'finance_control.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'finance_control.wsgi.application'
ASGI_APPLICATION = 'finance_control.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

VR_INITIAL_BALANCE = 0
VR_MONTHLY_CREDIT = 500
REFERENCE_PREVIOUS_NET_SALARY = 2299
REFERENCE_NEW_GROSS_SALARY = 3000
```

## Arquivo
`finance_control/urls.py`

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('finance.urls')),
]
```

## Arquivo
`finance_control/wsgi.py`

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_control.settings')
application = get_wsgi_application()
```

## Arquivo
`manage.py`

```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_control.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
```

## Arquivo
`requirements.txt`

```text
Django>=5.2,<5.3
gunicorn>=23.0,<24.0
```
