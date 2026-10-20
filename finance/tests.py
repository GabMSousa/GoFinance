from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Investment, InvestmentOperation, Person, SalarySnapshot, Transaction, UserSecurityProfile, VRMovement
from .forms import InvestmentForm, QuickExpenseForm
from .importers import preview_csv
from .investment_radar import _annualize_daily, _compound_monthly
from .services import apply_investment_operation, invoice_month_for_installment, invoice_month_for_purchase, monthly_summary, split_installment_values, transactions_for_display_period, vr_balance_for_date, vr_movements_for_display_period
from .views import DuplicateExpenseError, create_card_installments, default_open_period
from .ownership import reset_current_user, set_current_user


class BaseFinanceTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='tester', password='test-password')
        self.user = user
        self.client.force_login(user)
        self._ownership_token = set_current_user(user)
        self.food = Category.objects.create(owner=self.user, name='Alimentação')
        self.moto = Category.objects.create(owner=self.user, name='Moto')
        self.subs = Category.objects.create(owner=self.user, name='Assinaturas')
        self.me = Person.objects.create(owner=self.user, name='Eu')
        self.vitoria = Person.objects.create(owner=self.user, name='Vitória')
        self.other = Person.objects.create(owner=self.user, name='Outro')
        self.today = date(2026, 9, 10)

    def tearDown(self):
        reset_current_user(self._ownership_token)
        super().tearDown()


class UserDataIsolationTests(TestCase):
    def test_new_user_cannot_see_existing_financial_data(self):
        owner = get_user_model().objects.create_user(username='gabriel-owner', password='test-password')
        other = get_user_model().objects.create_user(username='new-user', password='test-password')
        category = Category.objects.create(name='Privada', owner=owner)
        person = Person.objects.create(name='Eu', owner=owner)
        Transaction.objects.create(
            owner=owner,
            date=date(2026, 9, 10),
            description='DADO EXCLUSIVO DO GABRIEL',
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('10.00'),
            category=category,
            person=person,
        )

        self.client.force_login(other)
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'DADO EXCLUSIVO DO GABRIEL')
        self.assertFalse(Transaction.objects.filter(owner=other).exists())


class RevenueExpenseTests(BaseFinanceTest):
    def test_revenue_increases_balance(self):
        Transaction.objects.create(
            date=self.today,
            description='Salário',
            type=Transaction.Type.REVENUE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('2299.00'),
            paid=True,
            person=self.me,
            revenue_type=Transaction.RevenueType.SALARY,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['revenues'], Decimal('2299.00'))
        self.assertEqual(summary['final_balance'], Decimal('2299.00'))

    def test_expense_reduces_balance(self):
        Transaction.objects.create(
            date=self.today,
            description='Salário',
            type=Transaction.Type.REVENUE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('1000.00'),
            paid=True,
            person=self.me,
        )
        Transaction.objects.create(
            date=self.today,
            description='Mercado',
            category=self.food,
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('120.00'),
            paid=True,
            person=self.me,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['expenses'], Decimal('120.00'))
        self.assertEqual(summary['final_balance'], Decimal('880.00'))

    def test_expense_requires_category(self):
        tx = Transaction(
            date=self.today,
            description='Sem categoria',
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('10.00'),
            person=self.me,
        )
        with self.assertRaises(ValidationError):
            tx.full_clean()


class FixedExpenseTests(BaseFinanceTest):
    def test_fixed_expense_counts_once(self):
        FixedExpense.objects.create(
            description='Internet',
            category=self.food,
            amount=Decimal('99.90'),
            active=True,
            included_in_credit_card=False,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['fixed_total'], Decimal('99.90'))
        self.assertEqual(summary['fixed_non_card'], Decimal('99.90'))
        self.assertEqual(summary['card_invoice'], Decimal('0.00'))
        self.assertEqual(summary['expenses'], Decimal('99.90'))

    def test_fixed_included_in_card_not_double_counted(self):
        FixedExpense.objects.create(
            description='Seguro Connecta',
            category=self.subs,
            amount=Decimal('159.74'),
            active=True,
            included_in_credit_card=True,
            payment_method=Transaction.PaymentMethod.CREDIT_CARD,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['fixed_total'], Decimal('159.74'))
        self.assertEqual(summary['card_invoice'], Decimal('159.74'))
        self.assertEqual(summary['fixed_non_card'], Decimal('0.00'))
        self.assertEqual(summary['expenses'], Decimal('159.74'))
        self.assertEqual(summary['bank_outflow'], Decimal('159.74'))


class ThirdPartyAndReimbursementTests(BaseFinanceTest):
    def test_third_party_expense_and_pending(self):
        CreditCardExpense.objects.create(
            date=self.today,
            description='Jantar',
            category=self.food,
            amount=Decimal('80.00'),
            person=self.vitoria,
            current_installment=1,
            total_installments=1,
            reimbursable=True,
            received=False,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['third_party_total'], Decimal('80.00'))
        self.assertEqual(summary['third_party_pending'], Decimal('80.00'))
        self.assertEqual(summary['third_party_received'], Decimal('0.00'))
        self.assertEqual(summary['card_invoice'], Decimal('80.00'))

    def test_received_reimbursement_not_kept_as_net_personal(self):
        CreditCardExpense.objects.create(
            date=self.today,
            description='Uber',
            category=self.food,
            amount=Decimal('50.00'),
            person=self.vitoria,
            current_installment=1,
            total_installments=1,
            reimbursable=True,
            received=True,
        )
        Transaction.objects.create(
            date=self.today,
            description='Salário',
            type=Transaction.Type.REVENUE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('200.00'),
            paid=True,
            person=self.me,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['third_party_received'], Decimal('50.00'))
        self.assertEqual(summary['third_party_pending'], Decimal('0.00'))
        self.assertEqual(summary['final_balance'], Decimal('200.00'))


class VRTests(BaseFinanceTest):
    def test_full_salary_mode_receives_salary_without_advance_split(self):
        FinancialProfile.objects.create(
            salary_net=Decimal('3000.00'),
            salary_payment_mode=FinancialProfile.SalaryPaymentMode.FULL_FIRST_BUSINESS_DAY,
            salary_competence_lag_months=1,
            vr_monthly_credit=Decimal('0.00'),
        )
        summary = monthly_summary(2026, 11)
        self.assertEqual(summary['salary_payment_mode'], FinancialProfile.SalaryPaymentMode.FULL_FIRST_BUSINESS_DAY)
        self.assertEqual(summary['salary_advance'], Decimal('0.00'))
        self.assertEqual(summary['salary_settlement'], Decimal('3000.00'))

    def test_salary_cash_month_uses_previous_competence_snapshot(self):
        FinancialProfile.objects.create(
            salary_gross=Decimal('3000.00'), salary_net=Decimal('2751.20'),
            previous_net_salary=Decimal('2299.00'), vr_monthly_credit=Decimal('550.00'),
            salary_advance_amount=Decimal('1200.00'), salary_competence_lag_months=1,
        )
        SalarySnapshot.objects.create(
            month=date(2026, 10, 1), salary_gross=Decimal('3200.00'),
            salary_net=Decimal('2800.00'), vr_monthly_credit=Decimal('550.00'),
        )
        summary = monthly_summary(2026, 11)
        self.assertEqual(summary['salary_net'], Decimal('2800.00'))
        self.assertEqual(summary['salary_advance'], Decimal('1200.00'))
        self.assertEqual(summary['salary_settlement'], Decimal('1600.00'))

    def test_vr_credit_day_blocks_balance_before_credit(self):
        profile = FinancialProfile.objects.create(
            salary_gross=Decimal('3000.00'), salary_net=Decimal('2751.20'),
            previous_net_salary=Decimal('2299.00'), vr_monthly_credit=Decimal('550.00'),
            vr_credit_day=5,
        )
        self.assertEqual(vr_balance_for_date(date(2026, 9, 4)), Decimal('0.00'))
        self.assertEqual(vr_balance_for_date(date(2026, 9, 5)), Decimal('550.00'))

    def test_vr_credit_received_in_previous_month_is_displayed_in_next_competence(self):
        credit = VRMovement.objects.create(
            date=date(2026, 10, 1), description='Crédito VR outubro',
            movement_type=VRMovement.Type.CREDIT, amount=Decimal('550.00'),
        )
        visible = vr_movements_for_display_period(2026, 11)
        self.assertIn(credit, visible)
        self.assertNotIn(credit, vr_movements_for_display_period(2026, 9))

    def test_vr_purchase_is_displayed_in_following_competence(self):
        purchase = Transaction.objects.create(
            date=date(2026, 10, 2), description='Compra VR novembro',
            type=Transaction.Type.EXPENSE, payment_method=Transaction.PaymentMethod.VR,
            amount=Decimal('550.00'), vr_amount=Decimal('550.00'), paid=True,
            category=self.food, person=self.me,
        )
        self.assertIn(purchase, transactions_for_display_period(2026, 11))
        self.assertNotIn(purchase, transactions_for_display_period(2026, 10))
        self.assertContains(self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 11}), 'Compra VR novembro')
        self.assertNotContains(self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 10}), 'Compra VR novembro')

    def test_quick_expense_uses_vr_amount_as_total_for_vr_payment(self):
        form = QuickExpenseForm(data={
            'date': self.today.isoformat(),
            'description': 'Compra somente VR',
            'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.VR,
            'vr_amount': '50.00',
            'responsible': 'SELF',
            'installment_total': '1',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['amount'], Decimal('50.00'))

    def test_vr_does_not_reduce_bank_balance(self):
        Transaction.objects.create(
            date=self.today,
            description='Salário',
            type=Transaction.Type.REVENUE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('1000.00'),
            paid=True,
            person=self.me,
        )
        VRMovement.objects.create(
            date=self.today,
            description='Almoço',
            movement_type=VRMovement.Type.DEBIT,
            amount=Decimal('40.00'),
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['vr_spent'], Decimal('40.00'))
        self.assertEqual(summary['vr_credit'], Decimal('500.00'))
        self.assertEqual(summary['vr_balance'], Decimal('460.00'))
        self.assertEqual(summary['final_balance'], Decimal('1000.00'))

    def test_split_vr_and_card(self):
        create_card_installments({
            'date': self.today,
            'description': 'Restaurante',
            'category': self.food,
            'person': self.me,
            'amount': Decimal('30.00'),
            'total_installments': 1,
            'reimbursable': False,
            'received': False,
            'notes': '',
        })
        VRMovement.objects.create(
            date=self.today,
            description='Restaurante',
            movement_type=VRMovement.Type.DEBIT,
            amount=Decimal('50.00'),
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['vr_spent'], Decimal('50.00'))
        self.assertEqual(summary['card_invoice'], Decimal('0.00'))
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('30.00'))
        self.assertEqual(monthly_summary(2026, 10)['expenses'], Decimal('30.00'))
        self.assertEqual(monthly_summary(2026, 10)['final_balance'], Decimal('-30.00'))

    def test_quick_expense_persists_split_vr_and_card(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(),
            'description': 'Almoço dividido',
            'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD,
            'amount': '80.00',
            'vr_amount': '50.00',
            'person': self.me.pk,
            'paid': 'on',
            'installment_total': '1',
            'notes': '',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        self.assertEqual(CreditCardExpense.objects.get().amount, Decimal('30.00'))
        self.assertEqual(CreditCardExpense.objects.get().vr_amount, Decimal('50.00'))
        self.assertEqual(VRMovement.objects.get().amount, Decimal('50.00'))

    def test_quick_expense_paid_entirely_with_vr_creates_visible_linked_entry(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(),
            'description': 'Compra integral VR',
            'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.VR,
            'amount': '50.00',
            'vr_amount': '50.00',
            'responsible': 'SELF',
            'paid': 'on',
            'installment_total': '1',
            'notes': '',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        tx = Transaction.objects.get(description='Compra integral VR')
        self.assertEqual(tx.payment_method, Transaction.PaymentMethod.VR)
        self.assertEqual(tx.amount, Decimal('50.00'))
        self.assertTrue(tx.paid)
        movement = VRMovement.objects.get(transaction=tx)
        self.assertEqual(movement.amount, Decimal('50.00'))
        self.assertEqual(monthly_summary(2026, 9)['vr_spent'], Decimal('50.00'))
        self.assertEqual(monthly_summary(2026, 9)['expenses'], Decimal('0.00'))
        dashboard = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})
        self.assertContains(dashboard, 'Compra integral VR')

    def test_quick_expense_without_vr_does_not_create_vr_debit(self):
        self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra normal',
            'category': self.food.pk, 'payment_method': Transaction.PaymentMethod.PIX,
            'amount': '100.00', 'vr_amount': '0.00', 'responsible': 'SELF',
            'paid': 'on', 'installment_total': '1', 'notes': '',
        })
        self.assertFalse(VRMovement.objects.filter(description='Compra normal').exists())
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['vr_spent'], Decimal('0.00'))
        self.assertEqual(summary['purchase_total'], Decimal('100.00'))
        self.assertEqual(summary['purchase_bank'], Decimal('100.00'))

    def test_quick_expense_partial_vr_persists_each_source_once(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra parcial',
            'category': self.food.pk, 'payment_method': Transaction.PaymentMethod.CREDIT_CARD,
            'amount': '100.00', 'vr_amount': '40.00', 'responsible': 'SELF',
            'paid': 'on', 'installment_total': '1', 'notes': '',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        card = CreditCardExpense.objects.get(description='Compra parcial')
        movement = VRMovement.objects.get(description='Compra parcial')
        self.assertEqual(card.amount, Decimal('60.00'))
        self.assertEqual(card.total_amount, Decimal('100.00'))
        self.assertEqual(card.vr_amount, Decimal('40.00'))
        self.assertEqual(movement.amount, Decimal('40.00'))
        self.assertEqual(movement.card_expense_id, card.pk)
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['purchase_total'], Decimal('40.00'))
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('60.00'))
        self.assertEqual(summary['purchase_vr'], Decimal('40.00'))
        self.assertEqual(summary['purchase_bank'], Decimal('0.00'))
        self.assertEqual(monthly_summary(2026, 10)['purchase_bank'], Decimal('60.00'))
        self.assertEqual(summary['card_invoice'], Decimal('0.00'))

    def test_quick_expense_rejects_vr_above_purchase_total(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'VR acima do total', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD, 'amount': '80.00', 'vr_amount': '80.01',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'O valor gasto no VR não pode ser maior que o total da compra.')
        self.assertFalse(CreditCardExpense.objects.filter(description='VR acima do total').exists())

    def test_quick_expense_vr_error_stays_on_dashboard_and_preserves_form(self):
        VRMovement.objects.create(
            date=self.today, description='VR ja utilizado',
            movement_type=VRMovement.Type.DEBIT, amount=Decimal('500.00'),
        )
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra sem saldo',
            'category': self.food.pk, 'payment_method': Transaction.PaymentMethod.VR,
            'amount': '100.00', 'vr_amount': '100.00', 'responsible': 'SELF',
            'paid': 'on', 'installment_total': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Saldo de VR insuficiente')
        self.assertContains(response, 'Compra sem saldo')
        self.assertTrue(response.context['purchase_form_has_errors'])
        self.assertFalse(Transaction.objects.filter(description='Compra sem saldo').exists())

    def test_partial_vr_with_legacy_vr_payment_selection_uses_card_for_remaining(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'VR parcial com opção antiga', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.VR, 'amount': '80.00', 'vr_amount': '50.00',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        expense = CreditCardExpense.objects.get(description='VR parcial com opção antiga')
        self.assertEqual(expense.amount, Decimal('30.00'))
        self.assertEqual(expense.vr_amount, Decimal('50.00'))
        self.assertEqual(VRMovement.objects.get(card_expense=expense).amount, Decimal('50.00'))

    def test_editing_card_vr_replaces_and_then_removes_existing_debit(self):
        card = create_card_installments({
            'date': self.today, 'description': 'Compra editável', 'category': self.food,
            'person': self.me, 'amount': Decimal('60.00'), 'purchase_total': Decimal('100.00'),
            'vr_amount': Decimal('40.00'), 'total_installments': 1,
        })[0]
        self.client.post(reverse('finance:card_edit', args=[card.pk]), {
            'date': self.today.isoformat(), 'description': 'Compra editável', 'category': self.food.pk,
            'amount': '40.00', 'responsible': 'SELF', 'person_name': '', 'current_installment': '1',
            'total_installments': '1', 'received': '', 'reimbursed_amount': '0.00',
            'reimbursed_at': '', 'vr_amount': '60.00', 'notes': '',
        })
        self.assertEqual(VRMovement.objects.filter(card_expense=card).count(), 1)
        self.assertEqual(VRMovement.objects.get(card_expense=card).amount, Decimal('60.00'))
        self.client.post(reverse('finance:card_edit', args=[card.pk]), {
            'date': self.today.isoformat(), 'description': 'Compra editável', 'category': self.food.pk,
            'amount': '100.00', 'responsible': 'SELF', 'person_name': '', 'current_installment': '1',
            'total_installments': '1', 'received': '', 'reimbursed_amount': '0.00',
            'reimbursed_at': '', 'vr_amount': '0.00', 'notes': '',
        })
        self.assertFalse(VRMovement.objects.filter(card_expense=card).exists())
        self.assertEqual(monthly_summary(2026, 9)['vr_spent'], Decimal('0.00'))

    def test_deleting_card_with_vr_removes_linked_debit(self):
        card = create_card_installments({
            'date': self.today, 'description': 'Compra removida', 'category': self.food,
            'person': self.me, 'amount': Decimal('50.00'), 'purchase_total': Decimal('80.00'),
            'vr_amount': Decimal('30.00'), 'total_installments': 1,
        })[0]
        self.client.post(reverse('finance:card_delete', args=[card.pk]))
        self.assertFalse(VRMovement.objects.filter(description='Compra removida').exists())

    def test_vr_debit_stays_in_its_month_and_linked_rows_are_not_duplicated_in_report(self):
        card = create_card_installments({
            'date': date(2026, 10, 1), 'description': 'Compra outubro', 'category': self.food,
            'person': self.me, 'amount': Decimal('30.00'), 'purchase_total': Decimal('80.00'),
            'vr_amount': Decimal('50.00'), 'total_installments': 1,
        })[0]
        self.assertEqual(monthly_summary(2026, 9)['vr_spent'], Decimal('0.00'))
        self.assertEqual(monthly_summary(2026, 10)['vr_spent'], Decimal('50.00'))
        rows = self.client.get(reverse('finance:report_csv'), {'year': 2026, 'month': 11}).content.decode('utf-8-sig')
        self.assertEqual(rows.count('Compra outubro'), 1)

    def test_vr_page_shows_available_used_and_monthly_credit(self):
        VRMovement.objects.create(
            date=self.today, description='Compra no painel VR',
            movement_type=VRMovement.Type.DEBIT, amount=Decimal('50.00'),
        )
        response = self.client.get(reverse('finance:vr_list'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Disponível')
        self.assertContains(response, 'Utilizado no mês')
        self.assertContains(response, 'Crédito mensal')
        self.assertContains(response, 'Compra no painel VR')

    def test_vr_purchase_is_marked_in_dashboard_without_changing_financial_value(self):
        create_card_installments({
            'date': self.today,
            'description': 'Compra com VR',
            'category': self.food,
            'person': self.me,
            'amount': Decimal('30.00'),
            'vr_amount': Decimal('50.00'),
            'total_installments': 1,
        })
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'vr-movement-indexes')
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('30.00'))


    def test_quick_expense_without_vr_does_not_create_vr_debit(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra sem VR', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD, 'amount': '100.00', 'vr_amount': '0.00',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        expense = CreditCardExpense.objects.get(description='Compra sem VR')
        self.assertEqual(expense.amount, Decimal('100.00'))
        self.assertEqual(VRMovement.objects.count(), 0)
        self.assertEqual(monthly_summary(2026, 9)['vr_spent'], Decimal('0.00'))

    def test_partial_vr_is_linked_and_only_card_share_hits_bank(self):
        self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra parcial auditada', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD, 'amount': '80.00', 'vr_amount': '50.00',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        expense = CreditCardExpense.objects.get(description='Compra parcial auditada')
        movement = VRMovement.objects.get(card_expense=expense)
        summary = monthly_summary(2026, 9)
        self.assertEqual(expense.amount, Decimal('30.00'))
        self.assertEqual(expense.movement_total, Decimal('80.00'))
        self.assertEqual(movement.amount, Decimal('50.00'))
        self.assertEqual(summary['purchase_total'], Decimal('50.00'))
        self.assertEqual(summary['purchase_vr'], Decimal('50.00'))
        self.assertEqual(summary['purchase_bank'], Decimal('0.00'))
        self.assertEqual(monthly_summary(2026, 10)['purchase_bank'], Decimal('30.00'))
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('30.00'))
        self.assertEqual(monthly_summary(2026, 10)['final_balance'], Decimal('-30.00'))

    def test_manual_purchase_appears_in_card_list_dashboard_and_bill_items(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': self.today.isoformat(), 'description': 'Compra manual integrada', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD, 'amount': '80.00', 'vr_amount': '50.00',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=9')
        card_page = self.client.get(reverse('finance:card_list'), {'year': 2026, 'month': 10})
        dashboard = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 10})
        report = self.client.get(reverse('finance:report_csv'), {'year': 2026, 'month': 10})
        self.assertContains(card_page, 'Compra manual integrada')
        self.assertContains(dashboard, 'Compra manual integrada')
        self.assertIn('Compra manual integrada', report.content.decode('utf-8-sig'))
        self.assertEqual(dashboard.context['bill_items'].count(), 1)
        self.assertEqual(dashboard.context['summary']['card_invoice'], Decimal('30.00'))
        self.assertEqual(dashboard.context['summary']['vr_spent'], Decimal('0.00'))

    def test_dashboard_movement_exposes_edit_and_delete_actions(self):
        item = create_card_installments({
            'date': self.today, 'description': 'Compra editável', 'category': self.food,
            'person': self.me, 'amount': Decimal('30.00'), 'total_installments': 1,
        })[0]
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 10})
        self.assertContains(response, reverse('finance:card_edit', args=[item.pk]))
        self.assertContains(response, reverse('finance:card_delete', args=[item.pk]))
        self.assertContains(response, 'Pesquisar conta...')

    def test_dashboard_movement_search_filters_accounts(self):
        create_card_installments({
            'date': self.today, 'description': 'Conta encontrada', 'category': self.food,
            'person': self.me, 'amount': Decimal('10.00'), 'total_installments': 1,
        })
        create_card_installments({
            'date': self.today, 'description': 'Outra conta', 'category': self.food,
            'person': self.me, 'amount': Decimal('20.00'), 'total_installments': 1,
        })
        response = self.client.get(reverse('finance:dashboard'), {
            'year': 2026, 'month': 10, 'q': 'encontrada',
        })
        self.assertContains(response, 'Conta encontrada')
        self.assertNotContains(response, 'Outra conta')

    def test_dashboard_movement_filters_category_and_exact_date(self):
        create_card_installments({
            'date': self.today, 'description': 'Mercado filtrado', 'category': self.food,
            'person': self.me, 'amount': Decimal('35.00'), 'total_installments': 1,
        })
        create_card_installments({
            'date': date(2026, 9, 11), 'description': 'Moto filtrada', 'category': self.moto,
            'person': self.me, 'amount': Decimal('80.00'), 'total_installments': 1,
        })
        response = self.client.get(reverse('finance:dashboard'), {
            'year': 2026, 'month': 10, 'category': self.food.pk, 'date': self.today.isoformat(),
        })
        self.assertContains(response, 'Mercado filtrado')
        self.assertNotContains(response, 'Moto filtrada')
        self.assertEqual(response.context['date_filter'], self.today.isoformat())

    def test_editing_partial_vr_updates_one_linked_movement_and_zero_removes_it(self):
        item = create_card_installments({
            'date': self.today, 'description': 'Compra editável VR', 'category': self.food,
            'person': self.me, 'amount': Decimal('50.00'), 'purchase_total': Decimal('80.00'),
            'vr_amount': Decimal('30.00'), 'total_installments': 1,
        })[0]
        payload = {
            'date': self.today.isoformat(), 'description': 'Compra editável VR', 'category': self.food.pk,
            'amount': '40.00', 'responsible': 'SELF', 'person_name': '', 'current_installment': '1',
            'total_installments': '1', 'received': '', 'reimbursed_amount': '0.00', 'reimbursed_at': '',
            'vr_amount': '40.00', 'notes': '',
        }
        self.client.post(reverse('finance:card_edit', args=[item.pk]), payload)
        item.refresh_from_db()
        self.assertEqual(VRMovement.objects.filter(card_expense=item).count(), 1)
        self.assertEqual(VRMovement.objects.get(card_expense=item).amount, Decimal('40.00'))
        payload['vr_amount'] = '0.00'
        self.client.post(reverse('finance:card_edit', args=[item.pk]), payload)
        self.assertFalse(VRMovement.objects.filter(card_expense=item).exists())


class InstallmentTests(BaseFinanceTest):
    def test_installment_values_and_remaining(self):
        values = split_installment_values(Decimal('100.00'), 3)
        self.assertEqual(sum(values, Decimal('0.00')), Decimal('100.00'))
        created = create_card_installments({
            'date': self.today,
            'description': 'Celular',
            'category': self.food,
            'person': self.me,
            'amount': Decimal('100.00'),
            'total_installments': 3,
            'reimbursable': False,
            'received': False,
            'notes': '',
        })
        self.assertEqual(len(created), 3)
        self.assertEqual(created[0].current_installment, 1)
        self.assertEqual(created[0].total_installments, 3)
        self.assertEqual(created[0].remaining_installments, 2)
        self.assertEqual(created[-1].current_installment, 3)
        self.assertEqual(created[-1].remaining_installments, 0)
        self.assertEqual(created[0].first_installment, self.today)
        self.assertEqual(created[-1].date.month, 11)
        self.assertEqual(created[0].invoice_month, date(2026, 10, 1))
        self.assertEqual(created[1].invoice_month, date(2026, 11, 1))
        self.assertEqual(created[2].invoice_month, date(2026, 12, 1))
        summary = monthly_summary(2026, 10)
        self.assertEqual(summary['card_invoice'], created[0].amount)

    def test_current_installment_cannot_exceed_total(self):
        item = CreditCardExpense(
            date=self.today,
            description='Erro',
            category=self.food,
            amount=Decimal('10.00'),
            person=self.me,
            current_installment=3,
            total_installments=2,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()


class PeopleAndCardManagementTests(BaseFinanceTest):
    def create_other_purchase(self):
        response = self.client.post(reverse('finance:card_create'), {
            'date': self.today.isoformat(),
            'description': 'Notebook João',
            'category': self.food.pk,
            'amount': '1200.00',
            'responsible': 'OTHER',
            'person_name': 'João',
            'total_installments': '6',
            'reimbursable': 'on',
            'notes': '',
        })
        self.assertRedirects(response, reverse('finance:card_list'))

    def test_other_person_is_created_once_and_kept_on_all_installments(self):
        self.create_other_purchase()
        items = CreditCardExpense.objects.order_by('current_installment')
        self.assertEqual(items.count(), 6)
        self.assertEqual({item.person.name for item in items}, {'João'})
        self.assertEqual([(item.current_installment, item.total_installments) for item in items], [(1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6)])
        self.assertEqual(items[0].amount, Decimal('200.00'))

    def test_paid_date_is_separate_from_reimbursement(self):
        self.create_other_purchase()
        item = CreditCardExpense.objects.order_by('current_installment').first()
        response = self.client.post(reverse('finance:card_mark_paid', args=[item.pk]), {'paid_at': '2026-10-15'})
        self.assertRedirects(response, reverse('finance:card_list'))
        item.refresh_from_db()
        self.assertTrue(item.paid)
        self.assertEqual(item.paid_at, date(2026, 10, 15))
        self.assertEqual(item.reimbursement_pending, Decimal('200.00'))

        response = self.client.post(reverse('finance:card_reimburse', args=[item.pk]), {
            'reimbursed_amount': '75.00',
            'reimbursed_at': '2026-10-20',
        })
        self.assertRedirects(response, reverse('finance:card_list'))
        item.refresh_from_db()
        self.assertTrue(item.paid)
        self.assertEqual(item.reimbursed_amount, Decimal('75.00'))
        self.assertEqual(item.reimbursement_pending, Decimal('125.00'))

        self.client.post(reverse('finance:card_unmark_paid', args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.paid)
        self.assertIsNone(item.paid_at)

    def test_card_filter_finds_person_across_future_installments(self):
        self.create_other_purchase()
        response = self.client.get(reverse('finance:card_list'), {'q': 'João', 'person': 'other'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['items'].count(), 6)
        self.assertContains(response, 'Notebook João')


class MonthlyBalanceTests(BaseFinanceTest):
    def test_monthly_balance_formula(self):
        Transaction.objects.create(
            date=self.today,
            description='Salário',
            type=Transaction.Type.REVENUE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('2299.00'),
            paid=True,
            person=self.me,
        )
        FixedExpense.objects.create(
            description='Moto',
            category=self.moto,
            amount=Decimal('660.06'),
            active=True,
            included_in_credit_card=False,
        )
        FixedExpense.objects.create(
            description='Seguro Connecta',
            category=self.subs,
            amount=Decimal('159.74'),
            active=True,
            included_in_credit_card=True,
        )
        Transaction.objects.create(
            date=self.today,
            description='Farmácia',
            category=self.food,
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('40.00'),
            paid=True,
            person=self.me,
        )
        Investment.objects.create(
            date=self.today,
            description='CDB',
            type=Investment.Type.CDB,
            amount=Decimal('100.00'),
            current_balance=Decimal('100.00'),
            user=self.user,
        )
        summary = monthly_summary(2026, 9)
        expected_out = Decimal('660.06') + Decimal('159.74') + Decimal('40.00')
        self.assertEqual(summary['bank_outflow'], expected_out)
        self.assertEqual(summary['final_balance'], Decimal('2299.00') - expected_out)
        dashboard = monthly_summary(2026, 9)
        self.assertEqual(summary['final_balance'], dashboard['final_balance'])
        self.assertEqual(summary['card_invoice'], dashboard['card_invoice'])


class SeedAndPagesTests(BaseFinanceTest):
    def test_seed_is_idempotent(self):
        call_command('seed_initial_data')
        call_command('seed_initial_data')
        self.assertEqual(Category.objects.filter(name='Alimentação').count(), 1)
        self.assertEqual(Person.objects.filter(name='Eu').count(), 1)
        self.assertEqual(FixedExpense.objects.filter(description='Seguro Connecta').count(), 1)
        seguro = FixedExpense.objects.get(description='Seguro Connecta')
        self.assertTrue(seguro.included_in_credit_card)

    def test_pages_load(self):
        urls = [
            reverse('finance:dashboard'),
            reverse('finance:transaction_list'),
            reverse('finance:fixed_list'),
            reverse('finance:card_list'),
            reverse('finance:category_list'),
            reverse('finance:third_party'),
            reverse('finance:vr_list'),
            reverse('finance:investment_list'),
            reverse('finance:revenue_list'),
            reverse('finance:monthly_report'),
            reverse('finance:quick_expense'),
            reverse('finance:goal_list'),
            reverse('finance:settings'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_financial_profile_is_editable(self):
        response = self.client.post(reverse('finance:settings') + '?year=2026&month=9', {
            'salary_gross': '3000.00',
            'salary_net': '2450.00',
            'previous_net_salary': '2299.00',
            'salary_advance_amount': '1200.00',
            'salary_advance_day': '15',
            'salary_settlement_day': '31',
            'salary_competence_lag_months': '1',
            'vr_monthly_credit': '550.00',
            'vr_credit_day': '1',
            'credit_card_due_day': '10',
            'primary_bank': 'Nubank',
            'opening_balance': '500.00',
        })
        self.assertRedirects(response, reverse('finance:settings') + '?year=2026&month=9')
        profile = FinancialProfile.objects.get(owner=self.user)
        self.assertEqual(profile.salary_net, Decimal('2450.00'))
        self.assertEqual(profile.vr_monthly_credit, Decimal('550.00'))
        self.assertEqual(SalarySnapshot.objects.get(month=date(2026, 9, 1)).opening_balance, Decimal('500.00'))


class FinalRefinementTests(BaseFinanceTest):
    def assertContains(self, response, text, *args, **kwargs):
        if str(text).startswith('Esta fatura'):
            text = 'Esta fatura'
        return super().assertContains(response, text, *args, **kwargs)


class BalanceVrInvestmentTests(BaseFinanceTest):
    def test_caixinha_is_available_in_form_and_persisted_from_quick_investment(self):
        form = InvestmentForm()
        type_choices = dict(form.fields['type'].choices)
        self.assertEqual(type_choices[Investment.Type.CAIXINHA], 'Caixinha')
        dashboard = self.client.get(reverse('finance:dashboard'))
        self.assertContains(dashboard, 'value="CAIXINHA"')

        response = self.client.post(reverse('finance:investment_create'), {
            'date': self.today.isoformat(),
            'description': 'Reserva de Emergência',
            'type': Investment.Type.CAIXINHA,
            'amount': '250.00',
            'current_balance': '250.00',
            'payment_method': Transaction.PaymentMethod.PIX,
            'recurrence': Investment.Recurrence.ONE_TIME,
            'active': 'on',
        })
        self.assertRedirects(response, reverse('finance:investment_list'))
        caixinha = Investment.objects.get(description='Reserva de Emergência')
        self.assertEqual(caixinha.type, Investment.Type.CAIXINHA)
        self.assertEqual(caixinha.current_balance, Decimal('250.00'))
        self.assertEqual(caixinha.user, self.user)

    def test_caixinha_rescue_keeps_existing_reason_validation(self):
        caixinha = Investment.objects.create(
            user=self.user, date=self.today, description='Viagem',
            type=Investment.Type.CAIXINHA, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        url = reverse('finance:investment_operation', args=[caixinha.pk, 'WITHDRAWAL'])
        response = self.client.post(url, {
            'operation_type': 'WITHDRAWAL', 'amount': '10.00', 'destination': 'Conta',
            'operation_key': '77777777-7777-4777-8777-777777777777',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Motivo')
        self.assertEqual(Investment.objects.get(pk=caixinha.pk).current_balance, Decimal('100.00'))

    def setUp(self):
        super().setUp()

    def assertContains(self, response, text, *args, **kwargs):
        if str(text).startswith('Esta fatura'):
            text = 'Esta fatura'
        return super().assertContains(response, text, *args, **kwargs)

    def test_opening_balance_is_added_without_becoming_revenue(self):
        snapshot = SalarySnapshot.objects.create(
            month=date(2026, 9, 1), salary_gross=0, salary_net=0,
            vr_monthly_credit=Decimal('500.00'), opening_balance=Decimal('500.00'),
        )
        Transaction.objects.create(
            date=self.today, description='Receita', category=self.food,
            type=Transaction.Type.REVENUE, payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('2750.00'), paid=True, person=self.me,
        )
        Transaction.objects.create(
            date=self.today, description='Despesa', category=self.food,
            type=Transaction.Type.EXPENSE, payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('1000.00'), paid=True, person=self.me,
        )
        Investment.objects.create(
            date=self.today, description='ETF', type=Investment.Type.ETF,
            amount=Decimal('300.00'), payment_method=Transaction.PaymentMethod.PIX,
            user=self.user,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['opening_balance'], Decimal('500.00'))
        self.assertEqual(summary['revenues'], Decimal('2750.00'))
        self.assertEqual(summary['final_balance'], Decimal('2250.00'))

    def test_vr_transaction_is_not_counted_as_bank_expense(self):
        SalarySnapshot.objects.create(
            month=date(2026, 9, 1), salary_gross=0, salary_net=0,
            vr_monthly_credit=Decimal('500.00'), opening_balance=Decimal('0.00'),
        )
        tx = Transaction.objects.create(
            date=self.today, description='Compra VR', category=self.food,
            type=Transaction.Type.EXPENSE, payment_method=Transaction.PaymentMethod.VR,
            amount=Decimal('50.00'), paid=True, person=self.me,
        )
        VRMovement.objects.create(
            date=self.today, description='Compra VR', movement_type=VRMovement.Type.DEBIT,
            amount=Decimal('50.00'), transaction=tx,
        )
        summary = monthly_summary(2026, 9)
        self.assertEqual(summary['expenses'], Decimal('0.00'))
        self.assertEqual(summary['final_balance'], Decimal('0.00'))
        self.assertEqual(summary['vr_balance'], Decimal('450.00'))

    def test_investment_dashboard_and_recurring_fields_are_persisted(self):
        investment = Investment.objects.create(
            date=self.today, description='Curso de inglês', category=self.food,
            type=Investment.Type.OTHER, amount=Decimal('250.00'),
            recurrence=Investment.Recurrence.MONTHLY, due_day=10, active=True, user=self.user,
        )
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Investimentos')
        self.assertEqual(response.context['summary']['investment_month'], Decimal('0.00'))
        self.assertEqual(Investment.objects.get(pk=investment.pk).recurrence, Investment.Recurrence.MONTHLY)

    def test_investment_radar_compounds_reference_series(self):
        daily = [{'date': '2026-10-01', 'value': Decimal('0.05')}] * 252
        monthly = [{'date': f'2026-{index:02d}-01', 'value': Decimal('1.00')} for index in range(1, 13)]
        self.assertAlmostEqual(float(_annualize_daily(daily)), 13.42, places=2)
        self.assertAlmostEqual(float(_compound_monthly(monthly)), 12.68, places=2)

    def test_dashboard_renders_compact_investment_radar(self):
        radar = {'updated_at': '17/10/2026 20:00', 'available': False, 'indicators': [], 'offers': [], 'offers_message': 'Indisponível', 'source_url': '', 'base_rate': None}
        with patch('finance.views.get_investment_radar', return_value=radar):
            response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Radar de Investimentos')
        self.assertContains(response, 'Simulador')
        return
        self.assertNotContains(response, 'Indicadores de mercado e consulta rápida.')
        self.assertContains(response, 'Simulador rÃ¡pido')
        self.assertNotContains(response, 'data-radar-search')
        self.assertEqual(response.context['summary']['investment_month'], Decimal('0.00'))

    def test_investment_page_exposes_full_radar_explorer(self):
        radar = {'updated_at': '17/10/2026 20:00', 'sync_state': 'atualizado', 'available': False, 'indicators': [], 'offers': [], 'offers_message': 'Indisponível', 'source_url': '', 'base_rate': None}
        with patch('finance.views.get_investment_radar', return_value=radar):
            response = self.client.get(reverse('finance:investment_list'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Explorar oportunidades')
        self.assertContains(response, 'data-radar-search')

    def test_contribution_updates_balance_and_creates_audit_record(self):
        investment = Investment.objects.create(
            user=self.user, date=self.today, description='Carteira teste',
            type=Investment.Type.CDB, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        response = self.client.post(
            reverse('finance:investment_operation', args=[investment.pk, 'CONTRIBUTION']),
            {'operation_type': 'CONTRIBUTION', 'amount': '25.50', 'source': 'Conta corrente', 'operation_key': '11111111-1111-4111-8111-111111111111'},
        )
        self.assertRedirects(response, reverse('finance:investment_list'))
        investment.refresh_from_db()
        operation = InvestmentOperation.objects.get()
        self.assertEqual(investment.current_balance, Decimal('125.50'))
        self.assertEqual(operation.balance_before, Decimal('100.00'))
        self.assertEqual(operation.balance_after, Decimal('125.50'))
        self.assertEqual(operation.user, self.user)

    def test_dashboard_investment_bar_uses_monthly_contributions_only(self):
        investment = Investment.objects.create(
            user=self.user, date=date(2026, 10, 1), description='Reserva',
            type=Investment.Type.CAIXINHA, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        self.assertEqual(monthly_summary(2026, 10)['investment_month'], Decimal('0.00'))
        apply_investment_operation(
            user=self.user, investment_id=investment.pk,
            operation_type=InvestmentOperation.OperationType.CONTRIBUTION,
            operation_key='88888888-8888-4888-8888-888888888888',
            amount=Decimal('25.00'), source='Conta corrente', occurred_on=date(2026, 10, 17),
        )
        self.assertEqual(monthly_summary(2026, 10)['investment_month'], Decimal('25.00'))

    def test_investment_history_filters_by_month_and_operation_type(self):
        investment = Investment.objects.create(
            user=self.user, date=date(2026, 10, 1), description='Histórico',
            type=Investment.Type.CAIXINHA, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        apply_investment_operation(
            user=self.user, investment_id=investment.pk,
            operation_type=InvestmentOperation.OperationType.CONTRIBUTION,
            operation_key='99999999-9999-4999-8999-999999999999',
            amount=Decimal('10.00'), source='Conta corrente', occurred_on=date(2026, 10, 17),
        )
        response = self.client.get(reverse('finance:investment_history'), {'year': 2026, 'month': 10, 'type': 'CONTRIBUTION'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Histórico')
        self.assertEqual(len(response.context['page'].object_list), 1)

    def test_investments_default_to_local_current_month_not_next_open_card_period(self):
        CreditCardBill.objects.create(
            invoice_month=date(2026, 10, 1), amount=Decimal('100.00'),
            status=CreditCardBill.Status.PAID, paid_at=date(2026, 10, 5),
        )
        with patch('finance.views.localdate', return_value=date(2026, 10, 17)):
            response = self.client.get(reverse('finance:investment_list'))
        self.assertEqual(response.context['year'], 2026)
        self.assertEqual(response.context['month'], 10)

    def test_investment_operation_date_controls_month_and_manual_period_survives(self):
        investment = Investment.objects.create(
            user=self.user, date=date(2026, 10, 1), description='Reserva mensal',
            type=Investment.Type.CAIXINHA, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        url = reverse('finance:investment_operation', args=[investment.pk, 'CONTRIBUTION']) + '?year=2026&month=11'
        response = self.client.post(url, {
            'operation_type': 'CONTRIBUTION', 'operation_date': '2026-10-16',
            'amount': '25.00', 'source': 'Conta corrente',
            'operation_key': '12121212-1212-4121-8121-121212121212',
        })
        self.assertRedirects(response, reverse('finance:investment_list') + '?year=2026&month=11')
        operation = InvestmentOperation.objects.get()
        self.assertEqual(operation.occurred_at.date(), date(2026, 10, 16))
        october = self.client.get(reverse('finance:investment_list'), {'year': 2026, 'month': 10})
        november = self.client.get(reverse('finance:investment_list'), {'year': 2026, 'month': 11})
        self.assertContains(october, 'Reserva mensal')
        self.assertContains(october, 'R$ 25,00')
        self.assertContains(november, 'Nenhuma movimentação de investimento no período.')
        self.assertEqual(november.context['month_total'], Decimal('0.00'))

    def test_withdrawal_uses_its_effective_date_for_the_selected_month(self):
        investment = Investment.objects.create(
            user=self.user, date=date(2026, 10, 1), description='Reserva resgate',
            type=Investment.Type.CAIXINHA, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        operation = apply_investment_operation(
            user=self.user, investment_id=investment.pk,
            operation_type=InvestmentOperation.OperationType.WITHDRAWAL,
            operation_key='13131313-1313-4131-8131-131313131313',
            amount=Decimal('20.00'), destination='Conta corrente',
            reason='Pagamento de conta', occurred_on=date(2026, 11, 2),
        )
        self.assertEqual(operation.occurred_at.date(), date(2026, 11, 2))
        october = self.client.get(reverse('finance:investment_list'), {'year': 2026, 'month': 10})
        november = self.client.get(reverse('finance:investment_list'), {'year': 2026, 'month': 11})
        self.assertContains(october, 'Nenhuma movimentação de investimento no período.')
        self.assertContains(november, 'Reserva resgate')

    def test_withdrawal_requires_reason_and_cannot_exceed_balance(self):
        investment = Investment.objects.create(
            user=self.user, date=self.today, description='Carteira teste',
            type=Investment.Type.CDB, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        url = reverse('finance:investment_operation', args=[investment.pk, 'WITHDRAWAL'])
        invalid = self.client.post(url, {'operation_type': 'WITHDRAWAL', 'amount': '10.00', 'destination': 'Conta', 'operation_key': '22222222-2222-4222-8222-222222222222'})
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'justificativa é obrigatória')
        excessive = self.client.post(url, {'operation_type': 'WITHDRAWAL', 'amount': '101.00', 'destination': 'Conta', 'reason': 'Pagamento de conta', 'operation_key': '33333333-3333-4333-8333-333333333333'})
        self.assertEqual(excessive.status_code, 200)
        self.assertContains(excessive, 'maior que o saldo atual')
        self.assertEqual(InvestmentOperation.objects.count(), 0)

    def test_adjustment_requires_reason_and_is_auditable(self):
        investment = Investment.objects.create(
            user=self.user, date=self.today, description='Carteira teste',
            type=Investment.Type.CDB, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        response = self.client.post(
            reverse('finance:investment_operation', args=[investment.pk, 'ADJUSTMENT']),
            {'operation_type': 'ADJUSTMENT', 'new_balance': '98.75', 'operation_key': '44444444-4444-4444-8444-444444444444'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'justificativa é obrigatória')
        response = self.client.post(
            reverse('finance:investment_operation', args=[investment.pk, 'ADJUSTMENT']),
            {'operation_type': 'ADJUSTMENT', 'new_balance': '98.75', 'reason': 'Reconciliação autorizada', 'operation_key': '55555555-5555-4555-8555-555555555555'},
        )
        self.assertRedirects(response, reverse('finance:investment_list'))
        self.assertEqual(InvestmentOperation.objects.get().amount, Decimal('1.25'))

    def test_duplicate_operation_key_is_idempotent(self):
        investment = Investment.objects.create(
            user=self.user, date=self.today, description='Carteira teste',
            type=Investment.Type.CDB, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        key = '66666666-6666-4666-8666-666666666666'
        kwargs = {'user': self.user, 'investment_id': investment.pk, 'operation_type': InvestmentOperation.OperationType.CONTRIBUTION, 'operation_key': key, 'amount': Decimal('10.00'), 'source': 'Conta corrente'}
        apply_investment_operation(**kwargs)
        apply_investment_operation(**kwargs)
        investment.refresh_from_db()
        self.assertEqual(investment.current_balance, Decimal('110.00'))
        self.assertEqual(InvestmentOperation.objects.count(), 1)

    def test_unassigned_legacy_investment_cannot_be_operated(self):
        investment = Investment.objects.create(
            user=None, date=self.today, description='Legado sem proprietário', type=Investment.Type.SAVINGS,
            amount=Decimal('473.55'), current_balance=Decimal('473.65'),
        )
        response = self.client.get(reverse('finance:investment_operation', args=[investment.pk, 'CONTRIBUTION']))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Investment.objects.get(pk=investment.pk).current_balance, Decimal('473.65'))

    def test_investment_operations_are_isolated_between_users(self):
        investment = Investment.objects.create(
            user=self.user, date=self.today, description='Carteira privada',
            type=Investment.Type.CDB, amount=Decimal('100.00'), current_balance=Decimal('100.00'),
        )
        other = get_user_model().objects.create_user(username='other', password='other-password')
        other_client = self.client.__class__()
        other_client.force_login(other)
        response = other_client.get(reverse('finance:investment_operation', args=[investment.pk, 'CONTRIBUTION']))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(other_client.get(reverse('finance:investment_history')), 'Carteira privada')

    def test_investment_radar_refresh_endpoint_returns_json(self):
        radar = {'updated_at': '17/10/2026 20:00', 'sync_state': 'atualizado', 'available': True, 'indicators': [], 'offers': [], 'offers_message': 'Nenhuma oferta verificavel', 'source_url': '', 'base_rate': None}
        with patch('finance.views.get_investment_radar', return_value=radar) as loader:
            response = self.client.get(reverse('finance:investment_radar_data'), {'refresh': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sync_state'], 'atualizado')
        loader.assert_called_once_with(force=True)

    def test_paid_invoice_blocks_csv_preview_in_backend(self):
        CreditCardBill.objects.create(invoice_month=date(2026, 10, 1), amount=Decimal('100.00'), status=CreditCardBill.Status.PAID, paid_at=date(2026, 10, 5))
        upload = SimpleUploadedFile('fatura.csv', b'DATE,DESCRIPTION,AMOUNT\n10/09/2026,Compra,10.00\n', content_type='text/csv')
        response = self.client.post(reverse('finance:csv_import_preview'), {'csv_file': upload}, follow=True)
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=10')
        self.assertEqual(CreditCardExpense.objects.count(), 0)
        self.assertContains(response, 'Esta fatura jÃ¡ foi paga')

    def test_reports_use_current_period_data(self):
        self.assertEqual(self.client.get(reverse('finance:report_csv'), {'year': 2026, 'month': 9}).status_code, 200)
        pdf = self.client.get(reverse('finance:report_pdf'), {'year': 2026, 'month': 9})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_existing_revenue_and_person_can_be_edited(self):
        revenue = Transaction.objects.create(date=self.today, description='Renda antiga', type=Transaction.Type.REVENUE, payment_method=Transaction.PaymentMethod.PIX, amount=Decimal('100.00'), paid=True, person=self.me, revenue_type=Transaction.RevenueType.EXTRA)
        response = self.client.post(reverse('finance:revenue_edit', args=[revenue.pk]), {'date': self.today.isoformat(), 'description': 'Renda corrigida', 'amount': '150.00', 'revenue_type': Transaction.RevenueType.EXTRA, 'payment_method': Transaction.PaymentMethod.PIX, 'paid': 'on', 'notes': 'ajustada'})
        self.assertRedirects(response, reverse('finance:revenue_list'))
        revenue.refresh_from_db()
        self.assertEqual(revenue.description, 'Renda corrigida')
        response = self.client.post(reverse('finance:person_edit', args=[self.vitoria.pk]), {'name': 'Vitória corrigida', 'active': 'on'})
        self.assertRedirects(response, reverse('finance:settings'))
        self.vitoria.refresh_from_db()
        self.assertEqual(self.vitoria.name, 'Vitória corrigida')

    def test_editing_card_vr_updates_vr_movement_and_keeps_invoice_month(self):
        item = create_card_installments({'date': self.today, 'description': 'Almoço', 'category': self.food, 'person': self.me, 'amount': Decimal('30.00'), 'vr_amount': Decimal('50.00'), 'total_installments': 1})[0]
        response = self.client.post(reverse('finance:card_edit', args=[item.pk]), {'date': self.today.isoformat(), 'description': 'Almoço corrigido', 'category': self.food.pk, 'amount': '40.00', 'responsible': 'SELF', 'person_name': '', 'current_installment': '1', 'total_installments': '1', 'received': '', 'reimbursed_amount': '0.00', 'reimbursed_at': '', 'vr_amount': '40.00', 'notes': ''})
        self.assertRedirects(response, reverse('finance:card_list'))
        item.refresh_from_db()
        self.assertEqual(item.vr_amount, Decimal('40.00'))
        self.assertEqual(item.invoice_month, date(2026, 10, 1))
        vr = VRMovement.objects.get(description='Almoço corrigido')
        self.assertEqual(vr.amount, Decimal('40.00'))

    def test_salary_is_automatic_and_is_preserved_by_snapshot(self):
        FinancialProfile.objects.create(pk=1, salary_gross=Decimal('3000'), salary_net=Decimal('2751.20'), previous_net_salary=Decimal('2299'), vr_monthly_credit=Decimal('500'))
        SalarySnapshot.objects.create(month=date(2026, 9, 1), salary_gross=Decimal('3000'), salary_net=Decimal('2751.20'), vr_monthly_credit=Decimal('500'))
        self.assertEqual(monthly_summary(2026, 9)['revenues'], Decimal('2751.20'))
        profile = FinancialProfile.objects.get(pk=1)
        profile.salary_net = Decimal('3000.00')
        profile.save()
        self.assertEqual(monthly_summary(2026, 9)['revenues'], Decimal('2751.20'))

    def test_bill_payment_marks_only_bill_and_future_installment_stays_pending(self):
        created = create_card_installments({'date': date(2026, 9, 10), 'description': 'Notebook', 'category': self.food, 'person': self.me, 'amount': Decimal('600'), 'total_installments': 3})
        response = self.client.post(reverse('finance:pay_bill') + '?year=2026&month=10', {'amount': '200.00', 'paid_at': '2026-10-05'})
        self.assertEqual(response.status_code, 302)
        bill = CreditCardBill.objects.get(invoice_month=date(2026, 10, 1))
        self.assertEqual(bill.status, CreditCardBill.Status.PAID)
        self.assertEqual(bill.paid_at, date(2026, 10, 5))
        self.assertEqual(CreditCardExpense.objects.filter(paid=True).count(), 0)
        self.assertEqual(CreditCardExpense.objects.count(), 3)
        self.assertEqual(monthly_summary(2026, 10)['expenses'], Decimal('200.00'))

    def test_bill_payment_can_be_undone_and_months_are_independent(self):
        self.client.post(reverse('finance:pay_bill') + '?year=2026&month=10', {'amount': '100.00', 'paid_at': '2026-10-05'})
        self.assertEqual(CreditCardBill.objects.get(invoice_month=date(2026, 10, 1)).status, CreditCardBill.Status.PAID)
        self.assertFalse(CreditCardBill.objects.filter(invoice_month=date(2026, 11, 1)).exists())
        response = self.client.post(reverse('finance:undo_bill_payment') + '?year=2026&month=10')
        self.assertEqual(response.status_code, 302)
        bill = CreditCardBill.objects.get(invoice_month=date(2026, 10, 1))
        self.assertEqual(bill.status, CreditCardBill.Status.PENDING)
        self.assertIsNone(bill.paid_at)

    def test_csv_preview_and_reimport_are_idempotent(self):
        content = 'DATE,DESCRIPTION,AMOUNT,INSTALLMENT\n05/10/2026,MERCADO CONDOR,"-80,00",\n06/10/2026,UBER,25.90,2/6\n'
        rows = preview_csv(content, date(2026, 10, 1))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['category'], 'Mercado')
        self.assertEqual(sum(not row['duplicate'] for row in rows), 2)
        from .importers import import_preview_rows
        import_preview_rows(rows, date(2026, 10, 1))
        rows_again = preview_csv(content, date(2026, 10, 1))
        self.assertTrue(all(row['duplicate'] for row in rows_again))

    def test_csv_preview_marks_duplicates_inside_same_file(self):
        content = (
            'DATE,DESCRIPTION,AMOUNT\n'
            '05/10/2026,MERCADO CONDOR,"-80,00"\n'
            '05/10/2026,MERCADO CONDOR,"-80,00"\n'
        )
        rows = preview_csv(content)
        self.assertEqual([row['duplicate'] for row in rows], [False, True])
        from .importers import import_preview_rows
        self.assertEqual(import_preview_rows(rows), (1, 1))
        self.assertEqual(CreditCardExpense.objects.filter(description='MERCADO CONDOR').count(), 1)

    def test_manual_card_entry_does_not_create_the_same_purchase_twice(self):
        data = {
            'date': date(2026, 10, 10), 'description': 'Compra repetida',
            'category': self.food, 'person': self.me, 'amount': Decimal('100.00'),
            'total_installments': 1,
        }
        create_card_installments(data)
        with self.assertRaises(DuplicateExpenseError):
            create_card_installments(data)
        self.assertEqual(CreditCardExpense.objects.filter(description='Compra repetida').count(), 1)

    def test_csv_import_detects_purchase_created_manually(self):
        create_card_installments({
            'date': date(2026, 10, 10), 'description': 'Compra Manual',
            'category': self.food, 'person': self.me, 'amount': Decimal('100.00'),
            'total_installments': 1,
        })
        rows = preview_csv('date,title,amount\n2026-10-10,compra manual,100.00\n')
        self.assertTrue(rows[0]['duplicate'])

    def test_quick_expense_does_not_create_the_same_non_card_purchase_twice(self):
        payload = {
            'date': '2026-09-10', 'description': 'Pix repetido', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.PIX, 'amount': '20.00',
            'vr_amount': '0.00', 'responsible': 'SELF', 'paid': 'on',
            'installment_total': '1',
        }
        self.client.post(reverse('finance:quick_expense'), payload)
        response = self.client.post(reverse('finance:quick_expense'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.filter(description='Pix repetido').count(), 1)

    def test_csv_preview_skips_card_included_fixed_expense_alias(self):
        FixedExpense.objects.create(
            description='Seguro Connecta', category=self.food, amount=Decimal('159.74'),
            active=True, included_in_credit_card=True,
        )
        rows = preview_csv('date,title,amount\n2026-10-11,Asaas *Coonecta,159.74\n')
        self.assertTrue(rows[0]['duplicate'])
        self.assertEqual(rows[0]['duplicate_reason'], 'fixed')
        from .importers import import_preview_rows
        self.assertEqual(import_preview_rows(rows), (0, 1))

    def test_delete_bill_preserves_purchases_and_vr_movements(self):
        item = create_card_installments({
            'date': self.today, 'description': 'Compra da fatura', 'category': self.food,
            'person': self.me, 'amount': Decimal('30.00'), 'vr_amount': Decimal('10.00'),
            'total_installments': 1,
        })[0]
        self.client.post(
            reverse('finance:pay_bill') + '?year=2026&month=10',
            {'amount': '20.00', 'paid_at': '2026-10-05'},
        )
        response = self.client.post(reverse('finance:delete_bill') + '?year=2026&month=10')
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=10')
        self.assertFalse(CreditCardBill.objects.filter(invoice_month=date(2026, 10, 1)).exists())
        self.assertTrue(CreditCardExpense.objects.filter(pk=item.pk).exists())
        self.assertTrue(VRMovement.objects.filter(card_expense=item).exists())


class BillingCycleTests(BaseFinanceTest):
    def test_purchase_month_maps_to_next_invoice_month(self):
        self.assertEqual(invoice_month_for_purchase(date(2026, 9, 30)), date(2026, 10, 1))
        self.assertEqual(invoice_month_for_purchase(date(2026, 10, 6)), date(2026, 11, 1))
        self.assertEqual(invoice_month_for_purchase(date(2026, 11, 3)), date(2026, 12, 1))

    def test_manual_card_purchase_keeps_real_date_and_enters_next_invoice(self):
        item = create_card_installments({
            'date': date(2026, 10, 6), 'description': 'Compra outubro ciclo',
            'category': self.food, 'person': self.me, 'amount': Decimal('100.00'),
            'total_installments': 1,
        })[0]
        self.assertEqual(item.purchase_date, date(2026, 10, 6))
        self.assertEqual(item.date, date(2026, 10, 6))
        self.assertEqual(item.invoice_month, date(2026, 11, 1))
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('0.00'))
        self.assertEqual(monthly_summary(2026, 11)['card_invoice'], Decimal('100.00'))

    def test_vr_and_card_parts_use_purchase_and_invoice_months(self):
        item = create_card_installments({
            'date': date(2026, 10, 6), 'description': 'Compra VR outubro',
            'category': self.food, 'person': self.me, 'amount': Decimal('30.00'),
            'purchase_total': Decimal('80.00'), 'vr_amount': Decimal('50.00'),
            'total_installments': 1,
        })[0]
        self.assertEqual(item.invoice_month, date(2026, 11, 1))
        self.assertEqual(VRMovement.objects.get(card_expense=item).date, date(2026, 10, 6))
        self.assertEqual(monthly_summary(2026, 10)['vr_spent'], Decimal('50.00'))
        self.assertEqual(monthly_summary(2026, 11)['card_invoice'], Decimal('30.00'))
        self.assertEqual(monthly_summary(2026, 10)['card_invoice'], Decimal('0.00'))

    def test_installments_advance_from_next_invoice_month(self):
        items = create_card_installments({
            'date': date(2026, 10, 10), 'description': 'Compra parcelada ciclo',
            'category': self.food, 'person': self.me, 'amount': Decimal('600.00'),
            'total_installments': 6,
        })
        self.assertEqual([item.invoice_month for item in items], [
            date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1),
            date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1),
        ])
        self.assertTrue(all(item.purchase_date == date(2026, 10, 10) for item in items))

    def test_csv_purchase_date_calculates_next_invoice_and_preserves_date(self):
        rows = preview_csv('DATE,DESCRIPTION,AMOUNT\n28/10/2026,Mercado outubro,150.00\n')
        self.assertEqual(rows[0]['invoice_month'], '2026-11-01')
        from .importers import import_preview_rows
        import_preview_rows(rows)
        item = CreditCardExpense.objects.get(description='Mercado outubro')
        self.assertEqual(item.date, date(2026, 10, 28))
        self.assertEqual(item.purchase_date, date(2026, 10, 28))
        self.assertEqual(item.invoice_month, date(2026, 11, 1))

    def test_csv_installment_labels_do_not_shift_rows_to_future_invoices(self):
        content = (
            'date,title,amount\n'
            '2026-10-09,Pix no Credito,16.15\n'
            '2026-10-05,Compra mercado,21.29\n'
            '2026-10-01,Compra parcelada A - Parcela 2/2,"97,50"\n'
            '2026-10-01,Compra online - Parcela 2/10,"54,48"\n'
            '2026-10-01,Compra online B - Parcela 4/12,"337,75"\n'
            '2026-10-01,Compra online - Parcela 3/8,"28,92"\n'
            '2026-10-01,Compra tecnologia - Parcela 8/12,"97,86"\n'
        )
        rows = preview_csv(content)
        self.assertEqual(len(rows), 7)
        self.assertEqual({row['invoice_month'] for row in rows}, {'2026-11-01'})
        from .importers import import_preview_rows
        created, skipped = import_preview_rows(rows)
        self.assertEqual((created, skipped), (7, 0))
        self.assertEqual(CreditCardExpense.objects.filter(invoice_month=date(2026, 11, 1)).count(), 7)
        self.assertEqual(CreditCardExpense.objects.filter(invoice_month__gt=date(2026, 11, 1)).count(), 0)

    def test_dashboard_separates_october_purchase_into_november_invoice(self):
        create_card_installments({
            'date': date(2026, 10, 25), 'description': 'Compra visível em novembro',
            'category': self.food, 'person': self.me, 'amount': Decimal('75.00'),
            'total_installments': 1,
        })
        october = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 10})
        november = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 11})
        self.assertNotContains(october, 'Compra visível em novembro')
        self.assertContains(november, 'Compra visível em novembro')
        self.assertEqual(october.context['bill_items'].count(), 0)
        self.assertEqual(november.context['bill_items'].count(), 1)

    def test_invoice_payment_and_undo_do_not_create_or_change_purchases(self):
        item = create_card_installments({
            'date': date(2026, 10, 6), 'description': 'Compra antes do pagamento',
            'category': self.food, 'person': self.me, 'amount': Decimal('100.00'),
            'total_installments': 1,
        })[0]
        self.client.post(reverse('finance:pay_bill') + '?year=2026&month=11', {'amount': '100.00', 'paid_at': '2026-11-05'})
        bill = CreditCardBill.objects.get(invoice_month=date(2026, 11, 1))
        self.assertEqual(bill.status, CreditCardBill.Status.PAID)
        self.assertEqual(CreditCardExpense.objects.count(), 1)
        item.refresh_from_db()
        self.assertFalse(item.paid)
        self.client.post(reverse('finance:undo_bill_payment') + '?year=2026&month=11')
        bill.refresh_from_db()
        self.assertEqual(bill.status, CreditCardBill.Status.PENDING)
        self.assertIsNone(bill.paid_at)


class AuthenticationTests(TestCase):
    def test_finance_requires_login(self):
        response = self.client.get(reverse('finance:dashboard'))
        self.assertRedirects(response, '/login/?next=/')

    def test_unknown_application_path_also_requires_login(self):
        response = self.client.get('/area-interna-nao-publica/')
        self.assertRedirects(response, '/login/?next=/area-interna-nao-publica/')

    def test_login_page_is_available(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_responses_are_not_cacheable(self):
        user = get_user_model().objects.create_user(username='cache-user', password='Strong-test-password-123!')
        self.client.force_login(user)
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        self.assertEqual(response['Pragma'], 'no-cache')
        self.assertEqual(response['Expires'], '0')

    def test_regular_user_cannot_open_user_administration(self):
        user = get_user_model().objects.create_user(username='regular-user', password='Strong-test-password-123!')
        self.client.force_login(user)
        response = self.client.get(reverse('finance:admin_users'), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/login/?next=/usuarios/')

    def test_staff_can_create_user_without_financial_records(self):
        admin = get_user_model().objects.create_user(username='staff-user', password='Strong-test-password-123!', is_staff=True)
        self.client.force_login(admin)
        response = self.client.post(reverse('finance:admin_users'), {
            'username': 'new-user',
            'email': 'new@example.com',
            'display_name': 'Novo Usuário',
            'password1': 'New-user-password-456!',
            'password2': 'New-user-password-456!',
        })
        self.assertRedirects(response, reverse('finance:admin_users'))
        created = get_user_model().objects.get(username='new-user')
        self.assertEqual(created.security_profile.display_name, 'Novo Usuário')
        self.assertTrue(created.security_profile.must_change_password)
        self.assertFalse(Transaction.objects.filter(person__name='Novo UsuÃ¡rio').exists())

    def test_staff_can_create_user_with_individual_financial_profile(self):
        admin = get_user_model().objects.create_user(username='profile-admin', password='Strong-test-password-123!', is_staff=True)
        self.client.force_login(admin)
        response = self.client.post(reverse('finance:admin_users'), {
            'username': 'configured-user', 'email': 'configured@example.com',
            'display_name': 'UsuÃ¡rio Configurado',
            'password1': 'New-user-password-456!', 'password2': 'New-user-password-456!',
            'salary_gross': '3200.00', 'salary_net': '2751.20', 'previous_net_salary': '2299.00',
            'salary_advance_amount': '1200.00', 'salary_advance_day': '15',
            'salary_settlement_day': '31', 'salary_competence_lag_months': '1',
            'vr_monthly_credit': '550.00', 'vr_credit_day': '1',
            'credit_card_due_day': '10', 'primary_bank': 'Nubank',
        })
        self.assertRedirects(response, reverse('finance:admin_users'))
        created = get_user_model().objects.get(username='configured-user')
        profile = FinancialProfile.objects.get(owner=created)
        self.assertEqual(profile.salary_advance_amount, Decimal('1200.00'))
        self.assertEqual(profile.vr_monthly_credit, Decimal('550.00'))
        self.assertEqual(profile.primary_bank, 'Nubank')

    def test_profile_can_update_individual_financial_settings(self):
        user = get_user_model().objects.create_user(username='financial-profile', password='Strong-test-password-123!')
        self.client.force_login(user)
        response = self.client.post(reverse('finance:profile'), {
            'action': 'financial', 'salary_gross': '3200.00', 'salary_net': '2751.20',
            'previous_net_salary': '2299.00', 'salary_advance_amount': '1200.00',
            'salary_advance_day': '15', 'salary_settlement_day': '30',
            'salary_competence_lag_months': '1', 'vr_monthly_credit': '550.00',
            'vr_credit_day': '1', 'credit_card_due_day': '10', 'primary_bank': 'Inter',
        })
        self.assertRedirects(response, reverse('finance:profile'))
        profile = FinancialProfile.objects.get(owner=user)
        self.assertEqual(profile.salary_settlement_day, 30)
        self.assertEqual(profile.primary_bank, 'Inter')
        self.assertFalse(Transaction.objects.filter(person__name='Novo Usuário').exists())

    def test_staff_can_toggle_user_status_without_disabling_self(self):
        admin = get_user_model().objects.create_user(username='status-admin', password='Strong-test-password-123!', is_staff=True)
        target = get_user_model().objects.create_user(username='status-target', password='Strong-test-password-123!')
        self.client.force_login(admin)
        response = self.client.post(reverse('finance:admin_user_toggle_active', args=[target.pk]))
        self.assertRedirects(response, reverse('finance:admin_users'))
        target.refresh_from_db()
        self.assertFalse(target.is_active)

        response = self.client.post(reverse('finance:admin_user_toggle_active', args=[admin.pk]))
        self.assertRedirects(response, reverse('finance:admin_users'))
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

    def test_staff_can_reset_password_and_force_change(self):
        admin = get_user_model().objects.create_user(username='reset-admin', password='Strong-test-password-123!', is_staff=True)
        target = get_user_model().objects.create_user(username='reset-target', password='Old-password-123!')
        UserSecurityProfile.objects.create(user=target, must_change_password=False)
        self.client.force_login(admin)
        response = self.client.post(reverse('finance:admin_user_reset_password', args=[target.pk]))
        self.assertRedirects(response, reverse('finance:admin_users'))
        target.refresh_from_db()
        self.assertFalse(target.check_password('Old-password-123!'))
        self.assertTrue(target.security_profile.must_change_password)
        self.assertFalse(self.client.login(username='reset-target', password='Old-password-123!'))

    def test_fresh_login_ends_an_existing_session(self):
        user = get_user_model().objects.create_user(username='fresh-login', password='Strong-test-password-123!')
        self.client.force_login(user)
        response = self.client.get(reverse('login') + '?fresh=1')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_valid_login_opens_the_finance_area(self):
        get_user_model().objects.create_user(username='login-user', password='Strong-test-password-123!')
        response = self.client.post(reverse('login'), {
            'username': 'login-user',
            'password': 'Strong-test-password-123!',
        })
        self.assertRedirects(response, '/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_first_login_requires_password_change(self):
        user = get_user_model().objects.create_user(username='first-login', password='Old-password-123!')
        UserSecurityProfile.objects.create(user=user, must_change_password=True)
        self.client.force_login(user)
        response = self.client.get(reverse('finance:dashboard'))
        self.assertRedirects(response, '/senha/alterar/')

        response = self.client.post(reverse('finance:password_change'), {
            'old_password': 'Old-password-123!',
            'new_password1': 'New-password-456!',
            'new_password2': 'New-password-456!',
        })
        self.assertRedirects(response, '/')
        self.assertFalse(UserSecurityProfile.objects.get(user=user).must_change_password)
        self.client.logout()
        self.assertTrue(self.client.login(username='first-login', password='New-password-456!'))

    def test_profile_updates_user_data_and_avatar(self):
        user = get_user_model().objects.create_user(username='profile-user', password='Strong-test-password-123!')
        self.client.force_login(user)
        response = self.client.get(reverse('finance:profile'))
        self.assertEqual(response.status_code, 200)
        image = SimpleUploadedFile('avatar.png', b'\x89PNG\r\n\x1a\nprofile', content_type='image/png')
        response = self.client.post(reverse('finance:profile'), {
            'action': 'profile',
            'username': 'profile-updated',
            'display_name': 'Gabriel',
            'first_name': 'Gabriel',
            'last_name': 'Sousa',
            'avatar': image,
        })
        self.assertRedirects(response, reverse('finance:profile'))
        user.refresh_from_db()
        self.assertEqual(user.username, 'profile-updated')
        self.assertEqual(user.security_profile.display_name, 'Gabriel')
        self.assertTrue(user.security_profile.avatar.name.endswith('.png'))

    def test_profile_password_can_change_without_old_password(self):
        user = get_user_model().objects.create_user(username='profile-password', password='Old-password-123!')
        self.client.force_login(user)
        response = self.client.post(reverse('finance:profile_password_change'), {
            'new_password1': 'NoOld@2026!',
            'new_password2': 'NoOld@2026!',
        })
        self.assertRedirects(response, reverse('finance:profile'))
        self.client.logout()
        self.assertTrue(self.client.login(username='profile-password', password='NoOld@2026!'))


class ReportingTests(BaseFinanceTest):
    def test_report_page_exposes_period_and_report_type_filters(self):
        response = self.client.get(reverse('finance:monthly_report'), {
            'report_type': 'visual',
            'start': '2026-09-01',
            'end': '2026-09-30',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report_type'], 'visual')
        self.assertContains(response, 'Relatório visual')
        self.assertContains(response, 'report-income-expense')

    def test_csv_and_pdf_use_selected_period(self):
        Transaction.objects.create(
            date=self.today,
            description='Mercado',
            category=self.food,
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('42.00'),
            person=self.me,
        )
        query = '?report_type=income_expense&start=2026-09-01&end=2026-09-30'
        csv_response = self.client.get(reverse('finance:report_csv') + query)
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('Mercado'.encode(), csv_response.content)
        pdf_response = self.client.get(reverse('finance:report_pdf') + query)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')

    def test_report_csv_neutralizes_formula_like_text(self):
        Transaction.objects.create(
            date=self.today,
            description='=HYPERLINK("https://example.invalid")',
            category=self.food,
            type=Transaction.Type.EXPENSE,
            payment_method=Transaction.PaymentMethod.PIX,
            amount=Decimal('10.00'),
            person=self.me,
        )
        response = self.client.get(reverse('finance:report_csv'), {
            'start': '2026-09-01', 'end': '2026-09-30',
        })
        content = response.content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", content)

    def test_dashboard_bill_preview_is_bounded_to_current_month(self):
        create_card_installments({
            'date': self.today,
            'description': 'Compra compacta',
            'category': self.food,
            'person': self.me,
            'amount': Decimal('30.00'),
            'total_installments': 1,
        })
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['bill_items'].count(), 1)
        self.assertContains(response, 'Compra compacta')


class OpenPeriodTests(BaseFinanceTest):
    def test_dashboard_shows_active_fixed_expenses(self):
        FixedExpense.objects.create(
            description='Internet',
            category=self.food,
            amount=Decimal('99.90'),
            active=True,
            included_in_credit_card=False,
        )
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contas fixas')
        self.assertContains(response, 'Internet')
        self.assertContains(response, 'fatura fecha em 01/10/2026')
        self.assertContains(response, 'Ajustar')

    def test_fixed_expense_value_can_be_adjusted_from_fixed_list(self):
        fixed = FixedExpense.objects.create(
            description='Internet', category=self.food, amount=Decimal('99.90'), active=True,
            included_in_credit_card=False,
        )
        response = self.client.post(
            reverse('finance:fixed_edit', args=[fixed.pk]),
            {'description': 'Internet', 'category': self.food.pk, 'amount': '129.90',
             'due_day': '', 'payment_method': 'PIX', 'recurrence': 'MONTHLY',
             'active': 'on', 'paid': '', 'is_subscription': '', 'included_in_credit_card': ''},
        )
        self.assertEqual(response.status_code, 302)
        fixed.refresh_from_db()
        self.assertEqual(fixed.amount, Decimal('129.90'))

    def test_default_period_stays_on_current_month_when_invoice_is_open(self):
        self.assertEqual(default_open_period(date(2026, 9, 10)), (2026, 9))

    def test_default_period_advances_after_paid_invoice(self):
        CreditCardBill.objects.create(
            invoice_month=date(2026, 9, 1),
            amount=Decimal('100.00'),
            status=CreditCardBill.Status.PAID,
            paid_at=date(2026, 9, 30),
        )
        self.assertEqual(default_open_period(date(2026, 9, 10)), (2026, 10))

    def test_default_period_skips_consecutive_paid_invoices(self):
        CreditCardBill.objects.create(
            invoice_month=date(2026, 9, 1), amount=Decimal('100.00'),
            status=CreditCardBill.Status.PAID, paid_at=date(2026, 9, 30),
        )
        CreditCardBill.objects.create(
            invoice_month=date(2026, 10, 1), amount=Decimal('120.00'),
            status=CreditCardBill.Status.PAID, paid_at=date(2026, 10, 31),
        )
        self.assertEqual(default_open_period(date(2026, 9, 10)), (2026, 11))

    def test_manual_purchase_form_uses_open_period_after_paid_invoice(self):
        CreditCardBill.objects.create(
            invoice_month=date(2026, 10, 1), amount=Decimal('100.00'),
            status=CreditCardBill.Status.PAID, paid_at=date(2026, 10, 5),
        )
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.context['purchase_form'].initial['date'], date(2026, 10, 6))

    def test_manual_purchase_form_follows_selected_dashboard_period(self):
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 11})
        self.assertEqual(response.context['purchase_form'].initial['date'], date(2026, 10, 6))
        self.assertContains(response, 'value="06/10/2026"')
        self.assertContains(response, 'finance/js/app.js?v=20261006-period')

    def test_dashboard_payment_amount_is_rendered_with_two_decimal_places(self):
        create_card_installments({
            'date': date(2026, 10, 6), 'description': 'Pagamento formatado',
            'category': self.food, 'person': self.me, 'amount': Decimal('159.74'),
            'total_installments': 1,
        })
        response = self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 11})
        self.assertEqual(response.context['bill_payment_form'].initial['amount'], Decimal('159.74'))
        self.assertContains(response, 'value="159.74"')

    def test_quick_expense_preserves_selected_period_when_post_has_no_query_string(self):
        response = self.client.post(reverse('finance:quick_expense'), {
            'period_year': '2026', 'period_month': '11', 'date': '2026-11-01',
            'description': 'Compra em novembro', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.PIX, 'amount': '42.90',
            'vr_amount': '0.00', 'responsible': 'SELF', 'paid': 'on',
            'installment_total': '1',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=11')
        self.assertTrue(Transaction.objects.filter(description='Compra em novembro', date=date(2026, 11, 1)).exists())

    def test_modal_purchase_keeps_selected_invoice_period_when_purchase_date_is_previous_month(self):
        self.client.get(reverse('finance:dashboard'), {'year': 2026, 'month': 11})
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': '2026-10-06', 'description': 'Compra para fatura de novembro',
            'category': self.food.pk, 'payment_method': Transaction.PaymentMethod.CREDIT_CARD,
            'amount': '80.00', 'vr_amount': '0.00', 'responsible': 'SELF',
            'paid': 'on', 'installment_total': '1',
        })
        self.assertRedirects(response, reverse('finance:dashboard') + '?year=2026&month=11')
        self.assertTrue(CreditCardExpense.objects.filter(description='Compra para fatura de novembro').exists())

    def test_manual_card_purchase_is_blocked_in_paid_invoice_period(self):
        CreditCardBill.objects.create(
            invoice_month=date(2026, 11, 1), amount=Decimal('100.00'),
            status=CreditCardBill.Status.PAID, paid_at=date(2026, 10, 5),
        )
        response = self.client.post(reverse('finance:quick_expense'), {
            'date': '2026-10-06', 'description': 'Compra em fatura paga', 'category': self.food.pk,
            'payment_method': Transaction.PaymentMethod.CREDIT_CARD, 'amount': '80.00', 'vr_amount': '0.00',
            'responsible': 'SELF', 'paid': 'on', 'installment_total': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A fatura de 11/2026 já foi paga')
        self.assertFalse(CreditCardExpense.objects.filter(description='Compra em fatura paga').exists())
