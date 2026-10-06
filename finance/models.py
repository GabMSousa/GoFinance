from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField('Nome', max_length=100, unique=True)
    active = models.BooleanField('Ativa?', default=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return self.name


class Person(models.Model):
    name = models.CharField('Nome', max_length=100, unique=True)
    active = models.BooleanField('Ativo?', default=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Responsável'
        verbose_name_plural = 'Responsáveis'

    def __str__(self):
        return self.name

    @property
    def is_self(self):
        return self.name.strip().lower() == 'eu'


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
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='Categoria',
        null=True,
        blank=True,
    )
    type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    payment_method = models.CharField('Forma de pagamento', max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(
        'Valor',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    paid = models.BooleanField('Pago?', default=False)
    fixed_expense = models.BooleanField('É gasto fixo?', default=False)
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='Responsável',
        null=True,
        blank=True,
    )
    reimbursable = models.BooleanField('Reembolsável?', default=False)
    received = models.BooleanField('Recebido?', default=False)
    installment_current = models.PositiveSmallIntegerField('Parcela atual', null=True, blank=True)
    installment_total = models.PositiveSmallIntegerField('Total de parcelas', default=1)
    notes = models.TextField('Observações', blank=True)
    revenue_type = models.CharField(
        'Tipo de receita',
        max_length=20,
        choices=RevenueType.choices,
        blank=True,
        default='',
    )
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def __str__(self):
        return f'{self.date} - {self.description}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.installment_total is not None and self.installment_total < 1:
            raise ValidationError({'installment_total': 'O total de parcelas deve ser no mínimo 1.'})
        if (
            self.installment_current
            and self.installment_total
            and self.installment_current > self.installment_total
        ):
            raise ValidationError({'installment_current': 'A parcela atual não pode ser maior que o total.'})
        if self.type == self.Type.EXPENSE and not self.category_id:
            raise ValidationError({'category': 'Categoria é obrigatória para despesas.'})
        if self.reimbursable and not self.person_id:
            raise ValidationError({'person': 'Responsável é obrigatório para gastos de terceiros.'})


class FixedExpense(models.Model):
    class Recurrence(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Mensal'
        YEARLY = 'YEARLY', 'Anual'

    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='fixed_expenses',
        verbose_name='Categoria',
    )
    amount = models.DecimalField(
        'Valor',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    due_day = models.PositiveSmallIntegerField('Dia do vencimento', null=True, blank=True)
    payment_method = models.CharField(
        'Forma de pagamento',
        max_length=20,
        choices=Transaction.PaymentMethod.choices,
        blank=True,
        default='',
    )
    active = models.BooleanField('Ativo?', default=True)
    paid = models.BooleanField('Pago?', default=False)
    recurrence = models.CharField('Recorrência', max_length=10, choices=Recurrence.choices, default=Recurrence.MONTHLY)
    is_subscription = models.BooleanField('É assinatura?', default=False)
    included_in_credit_card = models.BooleanField('Incluído no cartão?', default=False)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['due_day', 'description']
        verbose_name = 'Gasto fixo'
        verbose_name_plural = 'Gastos fixos'

    def __str__(self):
        return self.description

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.due_day is not None and not 1 <= self.due_day <= 31:
            raise ValidationError({'due_day': 'Dia de vencimento deve estar entre 1 e 31.'})


class Goal(models.Model):
    name = models.CharField('Nome', max_length=160)
    target_amount = models.DecimalField('Valor objetivo', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    current_amount = models.DecimalField('Valor acumulado', max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    deadline = models.DateField('Prazo', null=True, blank=True)
    active = models.BooleanField('Ativa?', default=True)
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['active', 'deadline', 'name']
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'

    def __str__(self):
        return self.name

    @property
    def progress_percent(self):
        if not self.target_amount:
            return 0
        return min(float(self.current_amount / self.target_amount * 100), 100)


class FinancialProfile(models.Model):
    salary_gross = models.DecimalField('Salário bruto', max_digits=12, decimal_places=2, default=3000)
    salary_net = models.DecimalField('Salário líquido', max_digits=12, decimal_places=2, default=2751.20)
    previous_net_salary = models.DecimalField('Salário líquido anterior', max_digits=12, decimal_places=2, default=2299)
    vr_monthly_credit = models.DecimalField('Crédito mensal de VR', max_digits=12, decimal_places=2, default=500)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Perfil financeiro'
        verbose_name_plural = 'Perfil financeiro'

    def __str__(self):
        return 'Dados financeiros'

    @classmethod
    def current(cls):
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile


class SalarySnapshot(models.Model):
    month = models.DateField('Mês', unique=True)
    salary_gross = models.DecimalField('Salário bruto', max_digits=12, decimal_places=2, default=3000)
    salary_net = models.DecimalField('Salário líquido', max_digits=12, decimal_places=2, default=2751.20)
    vr_monthly_credit = models.DecimalField('VR mensal', max_digits=12, decimal_places=2, default=500)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-month']


class CreditCardBill(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        PAID = 'PAID', 'Pago'

    invoice_month = models.DateField('Mês da fatura', unique=True)
    amount = models.DecimalField('Valor', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    paid_at = models.DateField('Pago em', null=True, blank=True)
    status = models.CharField('Status', max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['-invoice_month']

    @property
    def is_paid(self):
        return self.status == self.Status.PAID


class CreditCardExpense(models.Model):
    date = models.DateField('Data da parcela')
    purchase_date = models.DateField('Data da compra', null=True, blank=True)
    invoice_month = models.DateField('Mês da fatura', null=True, blank=True, db_index=True)
    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='card_expenses',
        verbose_name='Categoria',
    )
    amount = models.DecimalField(
        'Valor da parcela',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='card_expenses',
        verbose_name='Responsável',
    )
    current_installment = models.PositiveSmallIntegerField('Parcela atual', default=1)
    total_installments = models.PositiveSmallIntegerField('Total de parcelas', default=1)
    reimbursable = models.BooleanField('Reembolsável?', default=False)
    received = models.BooleanField('Recebido?', default=False)
    paid = models.BooleanField('Parcela paga?', default=False)
    paid_at = models.DateField('Data do pagamento', null=True, blank=True)
    reimbursed_amount = models.DecimalField(
        'Valor reembolsado',
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    reimbursed_at = models.DateField('Data do reembolso', null=True, blank=True)
    vr_amount = models.DecimalField('Valor pago com VR', max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    notes = models.TextField('Observações', blank=True)
    total_amount = models.DecimalField(
        'Valor total da compra',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    first_installment = models.DateField('Primeira parcela', null=True, blank=True)
    last_installment = models.DateField('Última parcela', null=True, blank=True)
    series_id = models.UUIDField('Série', null=True, blank=True, db_index=True)
    import_hash = models.CharField('Identificador da importação', max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Gasto no cartão'
        verbose_name_plural = 'Gastos no cartão'

    def __str__(self):
        return f'{self.description} ({self.current_installment}/{self.total_installments})'

    @property
    def remaining_installments(self):
        return max(int(self.total_installments or 1) - int(self.current_installment or 1), 0)

    @property
    def reimbursement_pending(self):
        if not self.reimbursable:
            return Decimal('0.00')
        if self.received and not self.reimbursed_amount:
            return Decimal('0.00')
        return max(self.amount - (self.reimbursed_amount or Decimal('0.00')), Decimal('0.00'))

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.total_installments is not None and self.total_installments < 1:
            raise ValidationError({'total_installments': 'O total de parcelas deve ser no mínimo 1.'})
        if self.current_installment and self.total_installments and self.current_installment > self.total_installments:
            raise ValidationError({'current_installment': 'A parcela atual não pode ser maior que o total.'})
        if self.reimbursed_amount is not None and self.reimbursed_amount > self.amount:
            raise ValidationError({'reimbursed_amount': 'O valor reembolsado não pode ser maior que o valor da parcela.'})
        if self.received and self.reimbursable and self.reimbursed_amount == 0:
            self.reimbursed_amount = self.amount


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
    type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    amount = models.DecimalField(
        'Valor aplicado',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    current_balance = models.DecimalField('Saldo atual', max_digits=12, decimal_places=2, default=0)
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'

    def __str__(self):
        return self.description

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})


class VRMovement(models.Model):
    class Type(models.TextChoices):
        CREDIT = 'CREDIT', 'Crédito'
        DEBIT = 'DEBIT', 'Gasto'
        ADJUSTMENT = 'ADJUSTMENT', 'Ajuste'

    date = models.DateField('Data')
    description = models.CharField('Descrição', max_length=180)
    movement_type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    amount = models.DecimalField(
        'Valor',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        related_name='vr_movements',
        verbose_name='Lançamento',
        null=True,
        blank=True,
    )
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Movimento de VR'
        verbose_name_plural = 'Movimentos de VR'

    def __str__(self):
        return f'{self.date} - {self.description}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
