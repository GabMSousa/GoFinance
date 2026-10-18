from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm

from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Goal, Investment, Person, Transaction, VRMovement
from .services import invoice_month_for_purchase, to_decimal, vr_balance_for_date

RESPONSIBLE_CHOICES = (('SELF', 'Eu'), ('OTHER', 'Outro'))


class ProfileForm(forms.Form):
    username = forms.CharField(label='Nome de usuário', max_length=150)
    display_name = forms.CharField(label='Nome de exibição', max_length=120, required=False)
    first_name = forms.CharField(label='Primeiro nome', max_length=150, required=False)
    last_name = forms.CharField(label='Sobrenome', max_length=150, required=False)
    avatar = forms.FileField(label='Foto de perfil', required=False)
    remove_avatar = forms.BooleanField(label='Remover foto atual', required=False)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = getattr(user, 'security_profile', None)
        self.initial.update({
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'display_name': getattr(profile, 'display_name', ''),
        })
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'

    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        if not value:
            raise forms.ValidationError('Informe um nome de usuário.')
        User = get_user_model()
        if User.objects.filter(username__iexact=value).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError('Este nome de usuário já está em uso.')
        return value

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if not avatar:
            return avatar
        if avatar.size > 2 * 1024 * 1024:
            raise forms.ValidationError('A foto deve ter no máximo 2 MB.')
        name = avatar.name.lower()
        if not name.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            raise forms.ValidationError('Use uma foto JPG, PNG ou WEBP.')
        header = avatar.read(12)
        avatar.seek(0)
        valid = header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG\r\n\x1a\n') or (header.startswith(b'RIFF') and header[8:12] == b'WEBP')
        if not valid:
            raise forms.ValidationError('O arquivo enviado não parece ser uma imagem válida.')
        return avatar

    def save(self):
        user = self.user
        user.username = self.cleaned_data['username']
        user.first_name = self.cleaned_data['first_name'].strip()
        user.last_name = self.cleaned_data['last_name'].strip()
        user.save(update_fields=['username', 'first_name', 'last_name'])
        from .models import UserSecurityProfile
        profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
        if self.cleaned_data['remove_avatar'] and profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = ''
        if self.cleaned_data['avatar']:
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = self.cleaned_data['avatar']
        profile.display_name = self.cleaned_data['display_name'].strip()
        profile.save()
        return user


class ProfilePasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(label='Nova senha', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    new_password2 = forms.CharField(label='Confirme a nova senha', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class BootstrapMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs.setdefault('class', 'form-control')


class BootstrapModelForm(BootstrapMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class CategoryForm(BootstrapModelForm):
    class Meta:
        model = Category
        fields = ['name', 'active']


class PersonForm(BootstrapModelForm):
    class Meta:
        model = Person
        fields = ['name', 'active']


class TransactionForm(BootstrapModelForm):
    vr_amount = forms.DecimalField(
        label='Valor gasto no VR',
        min_value=Decimal('0.00'),
        decimal_places=2,
        required=False,
        initial=0,
        help_text='O restante é calculado automaticamente pelo valor da compra.',
    )

    class Meta:
        model = Transaction
        fields = [
            'date',
            'description',
            'category',
            'type',
            'payment_method',
            'amount',
            'vr_amount',
            'paid',
            'fixed_expense',
            'person',
            'reimbursable',
            'received',
            'installment_current',
            'installment_total',
            'notes',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['person'].queryset = Person.objects.filter(active=True)
        self.fields['category'].required = False
        self.fields['person'].required = False
        self.fields['amount'].label = 'Valor total'
        self.fields['amount'].widget.attrs['data-total-with-vr'] = 'true'
        if (
            self.instance
            and self.instance.pk
            and self.instance.type == Transaction.Type.EXPENSE
            and self.instance.vr_amount
            and self.instance.payment_method != Transaction.PaymentMethod.VR
        ):
            self.initial['amount'] = self.instance.amount + self.instance.vr_amount

    def clean(self):
        data = super().clean()
        tx_type = data.get('type')
        category = data.get('category')
        person = data.get('person')
        reimbursable = data.get('reimbursable')
        current = data.get('installment_current')
        total = data.get('installment_total') or 1
        amount = data.get('amount')
        vr_amount = to_decimal(data.get('vr_amount') or 0)
        if amount is not None and amount <= 0:
            self.add_error('amount', 'Informe um valor maior que zero.')
        if amount is not None and vr_amount > amount:
            self.add_error('vr_amount', 'O valor de VR não pode ser maior que o total do lançamento.')
        if vr_amount < 0:
            self.add_error('vr_amount', 'O valor de VR nÃ£o pode ser negativo.')
        if (
            tx_type == Transaction.Type.EXPENSE
            and data.get('payment_method') == Transaction.PaymentMethod.VR
            and amount is not None
            and vr_amount != amount
        ):
            self.add_error('payment_method', 'Use o valor gasto no VR para informar a parte consumida do benefício.')
        if tx_type == Transaction.Type.EXPENSE and not category:
            self.add_error('category', 'Categoria é obrigatória para despesas.')
        if reimbursable and not person:
            self.add_error('person', 'Responsável é obrigatório para gastos de terceiros.')
        if total < 1:
            self.add_error('installment_total', 'O total de parcelas deve ser no mínimo 1.')
        if current and total and current > total:
            self.add_error('installment_current', 'A parcela atual não pode ser maior que o total.')
        if tx_type == Transaction.Type.EXPENSE and data.get('payment_method') == Transaction.PaymentMethod.CREDIT_CARD and amount is not None and vr_amount < amount and data.get('date'):
            invoice_month = invoice_month_for_purchase(data['date'])
            if CreditCardBill.objects.filter(invoice_month=invoice_month, status=CreditCardBill.Status.PAID).exists():
                self.add_error('date', f'A fatura de {invoice_month:%m/%Y} já foi paga. Escolha outra data de compra.')
        if tx_type == Transaction.Type.EXPENSE and vr_amount > 0 and data.get('date'):
            if vr_amount > vr_balance_for_date(data['date']):
                self.add_error('vr_amount', 'Saldo de VR insuficiente. Informe um ajuste de crÃ©dito antes de consumir acima do saldo.')
        if tx_type == Transaction.Type.EXPENSE and amount is not None and vr_amount >= amount:
            data['payment_method'] = Transaction.PaymentMethod.VR
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get('type') == Transaction.Type.EXPENSE:
            total = to_decimal(self.cleaned_data.get('amount') or 0)
            vr_amount = to_decimal(self.cleaned_data.get('vr_amount') or 0)
            remaining = total - vr_amount
            obj.amount = total if remaining <= 0 else remaining
            obj.vr_amount = vr_amount
        if commit:
            obj.save()
        return obj


class RevenueForm(BootstrapModelForm):
    class Meta:
        model = Transaction
        fields = ['date', 'description', 'amount', 'revenue_type', 'payment_method', 'paid', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revenue_type'].required = True
        self.fields['payment_method'].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.type = Transaction.Type.REVENUE
        obj.paid = True if self.cleaned_data.get('paid') else obj.paid
        if commit:
            obj.save()
        return obj


class FixedExpenseForm(BootstrapModelForm):
    class Meta:
        model = FixedExpense
        fields = [
            'description',
            'category',
            'amount',
            'due_day',
            'payment_method',
            'active',
            'paid',
            'recurrence',
            'is_subscription',
            'included_in_credit_card',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(active=True)


class GoalForm(BootstrapModelForm):
    class Meta:
        model = Goal
        fields = ['name', 'target_amount', 'current_amount', 'deadline', 'active', 'notes']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class FinancialProfileForm(BootstrapModelForm):
    opening_balance = forms.DecimalField(
        label='Saldo inicial do mês',
        min_value=Decimal('0.00'),
        decimal_places=2,
        required=False,
    )

    class Meta:
        model = FinancialProfile
        fields = ['salary_gross', 'salary_net', 'previous_net_salary', 'vr_monthly_credit']


class CardBillPaymentForm(BootstrapMixin, forms.Form):
    amount = forms.DecimalField(
        label='Valor efetivamente pago',
        min_value=Decimal('0.00'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'inputmode': 'decimal'}),
    )
    paid_at = forms.DateField(label='Data do pagamento', widget=forms.DateInput(attrs={'type': 'date'}))

    def clean_amount(self):
        return to_decimal(self.cleaned_data['amount'])


class CsvImportForm(BootstrapMixin, forms.Form):
    csv_file = forms.FileField(label='Arquivo CSV')

    def clean_csv_file(self):
        uploaded = self.cleaned_data['csv_file']
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError('O arquivo CSV deve ter no máximo 5 MB.')
        if not uploaded.name.lower().endswith('.csv'):
            raise forms.ValidationError('Envie um arquivo com extensão .csv.')
        allowed_types = {'text/csv', 'application/csv', 'text/plain', ''}
        if uploaded.content_type not in allowed_types:
            raise forms.ValidationError('O arquivo enviado não foi reconhecido como CSV.')
        return uploaded


class CreditCardExpenseForm(BootstrapModelForm):
    responsible = forms.ChoiceField(label='Responsável', choices=RESPONSIBLE_CHOICES, initial='SELF')
    person_name = forms.CharField(label='Nome da pessoa', max_length=100, required=False)

    class Meta:
        model = CreditCardExpense
        fields = [
            'date',
            'description',
            'category',
            'amount',
            'responsible',
            'person_name',
            'current_installment',
            'total_installments',
            'reimbursable',
            'received',
            'paid_at',
            'reimbursed_amount',
            'reimbursed_at',
            'vr_amount',
            'notes',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsible'].required = False
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['vr_amount'].label = 'Valor gasto no VR'
        self.fields['vr_amount'].help_text = 'O restante da compra já está calculado na parcela do cartão.'
        if self.instance and self.instance.pk:
            self.initial['responsible'] = 'SELF' if self.instance.person.is_self else 'OTHER'
            self.initial['person_name'] = '' if self.instance.person.is_self else self.instance.person.name

    def clean(self):
        data = super().clean()
        data['responsible'] = data.get('responsible') or 'SELF'
        current = data.get('current_installment')
        total = data.get('total_installments') or 1
        if total < 1:
            self.add_error('total_installments', 'O total de parcelas deve ser no mínimo 1.')
        if current and total and current > total:
            self.add_error('current_installment', 'A parcela atual não pode ser maior que o total.')
        if data.get('responsible') == 'OTHER' and not (data.get('person_name') or '').strip():
            self.add_error('person_name', 'Informe o nome da pessoa.')
        total = to_decimal(self.instance.total_amount or self.instance.amount or 0)
        if to_decimal(data.get('vr_amount') or 0) > total:
            self.add_error('vr_amount', 'O valor gasto no VR não pode ser maior que o total da compra.')
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        from .models import Person
        if self.cleaned_data.get('responsible') == 'SELF':
            person, _ = Person.objects.get_or_create(name='Eu', defaults={'active': True})
        else:
            person, _ = Person.objects.get_or_create(
                name=self.cleaned_data['person_name'].strip(),
                defaults={'active': True},
            )
        obj.person = person
        obj.received = obj.reimbursable and obj.reimbursed_amount >= obj.amount
        if commit:
            obj.save()
        return obj


class InvestmentForm(BootstrapModelForm):
    class Meta:
        model = Investment
        fields = [
            'date', 'description', 'category', 'type', 'amount', 'current_balance',
            'payment_method', 'recurrence', 'due_day', 'active', 'notes',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(active=True)


class VRMovementForm(BootstrapModelForm):
    class Meta:
        model = VRMovement
        fields = ['date', 'description', 'movement_type', 'amount', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        data = super().clean()
        movement_type = data.get('movement_type')
        amount = data.get('amount')
        movement_date = data.get('date')
        if movement_type == VRMovement.Type.DEBIT and amount and movement_date:
            if amount > vr_balance_for_date(movement_date):
                self.add_error('amount', 'Saldo de VR insuficiente. Informe um ajuste de crédito antes de consumir acima do saldo.')
        return data


class QuickExpenseForm(BootstrapMixin, forms.Form):
    date = forms.DateField(label='Data', widget=forms.DateInput(attrs={'type': 'date'}))
    description = forms.CharField(label='Descrição', max_length=180)
    category = forms.ModelChoiceField(label='Categoria', queryset=Category.objects.none())
    payment_method = forms.ChoiceField(label='Forma de pagamento do restante', choices=Transaction.PaymentMethod.choices)
    amount = forms.DecimalField(label='Valor total', min_value=Decimal('0.01'), decimal_places=2)
    vr_amount = forms.DecimalField(
        label='Valor gasto no VR',
        min_value=Decimal('0.00'),
        decimal_places=2,
        initial=0,
        required=False,
        help_text='Informe quanto desta compra foi consumido do VR. O restante é calculado automaticamente.',
    )
    responsible = forms.ChoiceField(label='Responsável', choices=RESPONSIBLE_CHOICES, initial='SELF')
    person_name = forms.CharField(label='Nome da pessoa', max_length=100, required=False)
    paid = forms.BooleanField(label='Pago?', required=False, initial=True)
    reimbursable = forms.BooleanField(label='Reembolsável?', required=False)
    received = forms.BooleanField(label='Recebido?', required=False)
    installment_total = forms.IntegerField(label='Total de parcelas', min_value=1, initial=1)
    notes = forms.CharField(label='Observações', required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['responsible'].required = False
        self.apply_bootstrap()

    def clean(self):
        data = super().clean()
        data['responsible'] = data.get('responsible') or 'SELF'
        total = to_decimal(data.get('amount') or 0)
        vr_amount = to_decimal(data.get('vr_amount') or 0)
        payment = data.get('payment_method')
        reimbursable = data.get('reimbursable')
        if vr_amount > total:
            self.add_error('vr_amount', 'O valor gasto no VR não pode ser maior que o total da compra.')
        remaining = total - vr_amount
        if payment == Transaction.PaymentMethod.VR and remaining > 0:
            # VR informa apenas o valor consumido. Se a opção antiga "VR"
            # permanecer selecionada em uma compra parcial, o restante cai
            # no cartão sem aumentar a baixa do benefício.
            data['payment_method'] = Transaction.PaymentMethod.CREDIT_CARD
        if remaining > 0 and not payment:
            self.add_error('payment_method', 'Informe a forma de pagamento do restante.')
        if data.get('responsible') == 'OTHER' and not (data.get('person_name') or '').strip():
            self.add_error('person_name', 'Informe o nome da pessoa.')
        movement_date = data.get('date')
        if remaining > 0 and data.get('payment_method') == Transaction.PaymentMethod.CREDIT_CARD and movement_date:
            invoice_month = invoice_month_for_purchase(movement_date)
            if CreditCardBill.objects.filter(invoice_month=invoice_month, status=CreditCardBill.Status.PAID).exists():
                self.add_error('date', f'A fatura de {invoice_month:%m/%Y} já foi paga. Escolha outra data de compra.')
        if vr_amount > 0 and movement_date:
            if vr_amount > vr_balance_for_date(movement_date):
                self.add_error('vr_amount', 'Saldo de VR insuficiente. Informe um ajuste de crédito antes de consumir acima do saldo.')
        installment_total = data.get('installment_total') or 1
        if installment_total < 1:
            self.add_error('installment_total', 'O total de parcelas deve ser no mínimo 1.')
        if remaining <= 0:
            data['payment_method'] = Transaction.PaymentMethod.VR
        return data

class CardPurchaseForm(BootstrapMixin, forms.Form):
    date = forms.DateField(label='Primeira parcela', widget=forms.DateInput(attrs={'type': 'date'}))
    description = forms.CharField(label='Descrição', max_length=180)
    category = forms.ModelChoiceField(label='Categoria', queryset=Category.objects.none())
    amount = forms.DecimalField(label='Valor total da compra', min_value=Decimal('0.01'), decimal_places=2)
    responsible = forms.ChoiceField(label='Responsável', choices=RESPONSIBLE_CHOICES, initial='SELF')
    person_name = forms.CharField(label='Nome da pessoa', max_length=100, required=False)
    total_installments = forms.IntegerField(label='Quantidade de parcelas', min_value=1, initial=1)
    reimbursable = forms.BooleanField(label='Reembolsável?', required=False)
    received = forms.BooleanField(label='Recebido?', required=False)
    notes = forms.CharField(label='Observações', required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(active=True)
        self.fields['responsible'].required = False
        self.apply_bootstrap()

    def clean(self):
        data = super().clean()
        data['responsible'] = data.get('responsible') or 'SELF'
        if data.get('responsible') == 'OTHER' and not (data.get('person_name') or '').strip():
            self.add_error('person_name', 'Informe o nome da pessoa.')
        return data


class PaymentDateForm(BootstrapMixin, forms.Form):
    paid_at = forms.DateField(label='Data do pagamento', widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class ReimbursementForm(BootstrapMixin, forms.Form):
    reimbursed_amount = forms.DecimalField(label='Valor recebido', min_value=Decimal('0.01'), decimal_places=2)
    reimbursed_at = forms.DateField(label='Data do reembolso', widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, max_amount=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_amount = max_amount
        self.apply_bootstrap()

    def clean_reimbursed_amount(self):
        value = self.cleaned_data['reimbursed_amount']
        if self.max_amount is not None and value > self.max_amount:
            raise forms.ValidationError('O valor recebido não pode ser maior que o valor da parcela.')
        return value
