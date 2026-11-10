from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db import models

from .ownership import UserOwnedManagerMixin, get_current_user


def normalize_uuid_hex(value):
    """Return UUID values in the 32-character format used by MariaDB CHAR(32)."""
    if value in (None, ''):
        return value
    try:
        return UUID(str(value)).hex
    except (AttributeError, ValueError):
        return value


class UserOwnedManager(UserOwnedManagerMixin, models.Manager):
    pass


class UserRelationManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        user = get_current_user()
        return queryset.filter(user=user) if user else queryset

    def create(self, **kwargs):
        user = get_current_user()
        if user and 'user' not in kwargs:
            kwargs['user'] = user
        return super().create(**kwargs)


class UserOwnedModel(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='+',
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Usuário proprietário',
    )
    objects = UserOwnedManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.owner_id is None:
            user = get_current_user()
            if user:
                self.owner = user
            else:
                for relation_name in ('category', 'person', 'transaction', 'card_expense'):
                    related = getattr(self, relation_name, None)
                    related_owner_id = getattr(related, 'owner_id', None)
                    if related_owner_id:
                        self.owner_id = related_owner_id
                        break
        return super().save(*args, **kwargs)


class UserSecurityProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='security_profile')
    display_name = models.CharField('Nome de exibição', max_length=120, blank=True)
    avatar = models.FileField('Foto de perfil', upload_to='profile-avatars/', blank=True)
    must_change_password = models.BooleanField('Deve trocar a senha?', default=False)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    def __str__(self):
        return f'Segurança de {self.user.username}'


class Category(UserOwnedModel):
    name = models.CharField('Nome', max_length=100)
    active = models.BooleanField('Ativa?', default=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return self.name


class Person(UserOwnedModel):
    name = models.CharField('Nome', max_length=100)
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


class Transaction(UserOwnedModel):
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
    vr_amount = models.DecimalField(
        'Valor gasto no VR',
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
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
    objects = UserOwnedManager()

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def __str__(self):
        return f'{self.date} - {self.description}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.vr_amount is not None and self.vr_amount < 0:
            raise ValidationError({'vr_amount': 'O valor de VR não pode ser negativo.'})
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


class FixedExpense(UserOwnedModel):
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


class Goal(UserOwnedModel):
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


class FinancialProfile(UserOwnedModel):
    class SalaryPaymentMode(models.TextChoices):
        FULL_FIRST_BUSINESS_DAY = 'FULL_FIRST_BUSINESS_DAY', 'Salário integral no primeiro dia útil'
        SPLIT_ADVANCE_SETTLEMENT = 'SPLIT_ADVANCE_SETTLEMENT', 'Adiantamento/vale + saldo salarial'

    salary_payment_mode = models.CharField(
        'Padrão de recebimento do salário',
        max_length=30,
        choices=SalaryPaymentMode.choices,
        default=SalaryPaymentMode.SPLIT_ADVANCE_SETTLEMENT,
    )
    salary_payment_day = models.PositiveSmallIntegerField('Dia do pagamento integral', default=5)
    salary_gross = models.DecimalField('Salário bruto', max_digits=12, decimal_places=2, default=0)
    salary_net = models.DecimalField('Salário líquido', max_digits=12, decimal_places=2, default=0)
    previous_net_salary = models.DecimalField('Salário líquido anterior', max_digits=12, decimal_places=2, default=0)
    salary_advance_amount = models.DecimalField('Adiantamento salarial', max_digits=12, decimal_places=2, default=0)
    salary_advance_day = models.PositiveSmallIntegerField('Dia do adiantamento', default=15)
    salary_settlement_day = models.PositiveSmallIntegerField('Dia do saldo salarial', default=31)
    salary_competence_lag_months = models.PositiveSmallIntegerField('Meses entre competência e recebimento', default=1)
    vr_monthly_credit = models.DecimalField('Crédito mensal de VR', max_digits=12, decimal_places=2, default=0)
    vr_credit_day = models.PositiveSmallIntegerField('Dia do crédito de VR', default=1)
    credit_card_due_day = models.PositiveSmallIntegerField('Dia de vencimento do cartão', default=10)
    primary_bank = models.CharField('Banco principal', max_length=120, blank=True, default='')
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Perfil financeiro'
        verbose_name_plural = 'Perfil financeiro'

    def __str__(self):
        return 'Dados financeiros'

    def save(self, *args, **kwargs):
        from .rules import SALARY_COMPETENCE_LAG_MONTHS
        self.salary_competence_lag_months = SALARY_COMPETENCE_LAG_MONTHS
        return super().save(*args, **kwargs)

    @classmethod
    def current(cls, user=None):
        profile = cls.objects.filter(owner=user).first() if user else cls.objects.first()
        if profile:
            return profile
        profile = cls(
            owner=user,
            salary_gross=0,
            salary_net=0,
            previous_net_salary=0,
            salary_advance_amount=0,
            vr_monthly_credit=0,
        )
        profile.save()
        return profile


class SalarySnapshot(UserOwnedModel):
    month = models.DateField('Mês')
    salary_payment_mode = models.CharField(
        'Padrão de recebimento do salário',
        max_length=30,
        choices=FinancialProfile.SalaryPaymentMode.choices,
        default=FinancialProfile.SalaryPaymentMode.SPLIT_ADVANCE_SETTLEMENT,
    )
    salary_payment_day = models.PositiveSmallIntegerField('Dia do pagamento integral', default=5)
    salary_gross = models.DecimalField('Salário bruto', max_digits=12, decimal_places=2, default=0)
    salary_net = models.DecimalField('Salário líquido', max_digits=12, decimal_places=2, default=0)
    salary_advance_amount = models.DecimalField('Adiantamento salarial', max_digits=12, decimal_places=2, default=0)
    salary_advance_day = models.PositiveSmallIntegerField('Dia do adiantamento', default=15)
    salary_settlement_day = models.PositiveSmallIntegerField('Dia do saldo salarial', default=31)
    salary_competence_lag_months = models.PositiveSmallIntegerField('Meses entre competência e recebimento', default=1)
    vr_monthly_credit = models.DecimalField('VR mensal', max_digits=12, decimal_places=2, default=0)
    vr_credit_day = models.PositiveSmallIntegerField('Dia do crédito de VR', default=1)
    credit_card_due_day = models.PositiveSmallIntegerField('Dia de vencimento do cartão', default=10)
    primary_bank = models.CharField('Banco principal', max_length=120, blank=True, default='')
    opening_balance = models.DecimalField('Saldo inicial', max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-month']

    def save(self, *args, **kwargs):
        from .rules import SALARY_COMPETENCE_LAG_MONTHS
        self.salary_competence_lag_months = SALARY_COMPETENCE_LAG_MONTHS
        return super().save(*args, **kwargs)


class CreditCardBill(UserOwnedModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        PAID = 'PAID', 'Pago'

    invoice_month = models.DateField('Mês da fatura')
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


class CreditCardExpense(UserOwnedModel):
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
        validators=[MinValueValidator(Decimal('0.00'))],
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
    vr_amount = models.DecimalField('Valor gasto no VR', max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
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
    # MySQL/MariaDB stores this identifier as CHAR(32), not as a native UUID.
    series_id = models.CharField('Série', max_length=32, null=True, blank=True, db_index=True)
    import_hash = models.CharField('Identificador da importação', max_length=64, null=True, blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Gasto no cartão'
        verbose_name_plural = 'Gastos no cartão'

    def __str__(self):
        return f'{self.description} ({self.current_installment}/{self.total_installments})'

    def save(self, *args, **kwargs):
        from .rules import invoice_month_for_purchase
        self.series_id = normalize_uuid_hex(self.series_id)
        purchase_date = self.purchase_date or self.date
        if purchase_date:
            self.invoice_month = invoice_month_for_purchase(purchase_date, self.current_installment)
        return super().save(*args, **kwargs)

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

    @property
    def movement_total(self):
        """The total represented by this installment, including its VR share."""
        return self.amount + (self.vr_amount or Decimal('0.00'))

    def clean(self):
        if self.amount is not None and self.amount < 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.amount == 0 and not self.vr_amount:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.total_installments is not None and self.total_installments < 1:
            raise ValidationError({'total_installments': 'O total de parcelas deve ser no mínimo 1.'})
        if self.current_installment and self.total_installments and self.current_installment > self.total_installments:
            raise ValidationError({'current_installment': 'A parcela atual não pode ser maior que o total.'})
        if self.reimbursed_amount is not None and self.reimbursed_amount > self.amount:
            raise ValidationError({'reimbursed_amount': 'O valor reembolsado não pode ser maior que o valor da parcela.'})
        if self.received and self.reimbursable and self.reimbursed_amount == 0:
            self.reimbursed_amount = self.amount
        if self.vr_amount is not None and self.vr_amount < 0:
            raise ValidationError({'vr_amount': 'O valor de VR não pode ser negativo.'})
        if self.vr_amount is not None and self.vr_amount > (self.total_amount or self.amount or Decimal('0.00')):
            raise ValidationError({'vr_amount': 'O valor gasto no VR não pode ser maior que o total da compra.'})


class Investment(models.Model):
    class Recurrence(models.TextChoices):
        ONE_TIME = 'ONE_TIME', 'Único'
        MONTHLY = 'MONTHLY', 'Mensal'
        YEARLY = 'YEARLY', 'Anual'

    class Type(models.TextChoices):
        CDB = 'CDB', 'CDB'
        TREASURY = 'TREASURY', 'Tesouro'
        STOCKS = 'STOCKS', 'Ações'
        ETF = 'ETF', 'ETF'
        FII = 'FII', 'FIIs'
        CRYPTO = 'CRYPTO', 'Cripto'
        SAVINGS = 'SAVINGS', 'Poupança'
        CAIXINHA = 'CAIXINHA', 'Caixinha'
        OTHER = 'OTHER', 'Outros'

    date = models.DateField('Data')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='investments',
        verbose_name='Usuário proprietário',
        null=True,
        blank=True,
    )
    description = models.CharField('Descrição', max_length=180)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='investments',
        verbose_name='Categoria',
        null=True,
        blank=True,
    )
    type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    amount = models.DecimalField(
        'Valor aplicado',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    current_balance = models.DecimalField('Saldo atual', max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(
        'Conta utilizada',
        max_length=20,
        choices=Transaction.PaymentMethod.choices,
        default=Transaction.PaymentMethod.PIX,
    )
    recurrence = models.CharField('Periodicidade', max_length=10, choices=Recurrence.choices, default=Recurrence.ONE_TIME)
    due_day = models.PositiveSmallIntegerField('Dia', null=True, blank=True)
    active = models.BooleanField('Ativo?', default=True)
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    objects = UserRelationManager()

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'

    def __str__(self):
        return self.description

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
        if self.due_day is not None and not 1 <= self.due_day <= 31:
            raise ValidationError({'due_day': 'Dia deve estar entre 1 e 31.'})


class InvestmentOperation(models.Model):
    class OperationType(models.TextChoices):
        CONTRIBUTION = 'CONTRIBUTION', 'Aporte'
        WITHDRAWAL = 'WITHDRAWAL', 'Resgate'
        ADJUSTMENT = 'ADJUSTMENT', 'Ajuste de saldo'
        REVERSAL = 'REVERSAL', 'Estorno'

    class Status(models.TextChoices):
        POSTED = 'POSTED', 'Registrada'
        REVERSED = 'REVERSED', 'Estornada'

    # Keep the storage format explicit and portable across SQLite/MySQL/MariaDB.
    # MariaDB's Django backend may treat UUIDField as a native UUID and send
    # 36-character hyphenated values to this CHAR(32) column.
    operation_key = models.CharField('Chave da operação', max_length=32, unique=True)
    investment = models.ForeignKey(
        Investment,
        on_delete=models.PROTECT,
        related_name='operations',
        verbose_name='Investimento',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='investment_operations',
        verbose_name='Responsável',
    )
    operation_type = models.CharField('Operação', max_length=20, choices=OperationType.choices)
    amount = models.DecimalField(
        'Valor da operação',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    balance_before = models.DecimalField('Saldo anterior', max_digits=12, decimal_places=2)
    balance_after = models.DecimalField('Saldo posterior', max_digits=12, decimal_places=2)
    source = models.CharField('Origem', max_length=180, blank=True)
    destination = models.CharField('Destino', max_length=180, blank=True)
    reason = models.TextField('Justificativa', blank=True)
    notes = models.TextField('Observações', blank=True)
    occurred_at = models.DateTimeField('Data e hora', default=timezone.now)
    status = models.CharField('Status', max_length=12, choices=Status.choices, default=Status.POSTED)
    reverses = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        related_name='reversal',
        null=True,
        blank=True,
    )
    objects = UserRelationManager()

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['user', '-occurred_at']),
            models.Index(fields=['investment', '-occurred_at']),
        ]
        verbose_name = 'Operação de investimento'
        verbose_name_plural = 'Operações de investimento'

    def __str__(self):
        return f'{self.get_operation_type_display()} - {self.investment}'

    def save(self, *args, **kwargs):
        self.operation_key = normalize_uuid_hex(self.operation_key)
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'Informe um valor maior que zero.'
        if self.balance_before is not None and self.balance_before < 0:
            errors['balance_before'] = 'O saldo anterior não pode ser negativo.'
        if self.balance_after is not None and self.balance_after < 0:
            errors['balance_after'] = 'O saldo posterior não pode ser negativo.'
        if self.operation_type in {self.OperationType.WITHDRAWAL, self.OperationType.ADJUSTMENT} and not self.reason.strip():
            errors['reason'] = 'A justificativa é obrigatória para esta operação.'
        if errors:
            raise ValidationError(errors)


class VRMovement(UserOwnedModel):
    class Type(models.TextChoices):
        CREDIT = 'CREDIT', 'Crédito'
        DEBIT = 'DEBIT', 'Gasto'
        ADJUSTMENT = 'ADJUSTMENT', 'Ajuste'

    date = models.DateField('Data')
    reference_month = models.DateField('Mês de referência', null=True, blank=True, db_index=True)
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
        on_delete=models.CASCADE,
        related_name='vr_movements',
        verbose_name='Lançamento',
        null=True,
        blank=True,
    )
    card_expense = models.ForeignKey(
        CreditCardExpense,
        on_delete=models.CASCADE,
        related_name='vr_movements',
        verbose_name='Compra no cartão',
        null=True,
        blank=True,
    )
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Movimento de VR'
        verbose_name_plural = 'Movimentos de VR'
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'reference_month', 'movement_type'],
                name='unique_vr_credit_reference_month',
            ),
        ]

    def save(self, *args, **kwargs):
        from .rules import vr_reference_month
        if self.movement_type == self.Type.CREDIT and self.date:
            self.reference_month = vr_reference_month(self.date)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.date} - {self.description}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Informe um valor maior que zero.'})
