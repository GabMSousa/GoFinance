from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Investment, Person, SalarySnapshot, Transaction, VRMovement
from .importers import preview_csv
from .services import monthly_summary, split_installment_values
from .views import create_card_installments


class BaseFinanceTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='tester', password='test-password')
        self.client.force_login(user)
        self.food = Category.objects.create(name='Alimentação')
        self.moto = Category.objects.create(name='Moto')
        self.subs = Category.objects.create(name='Assinaturas')
        self.me = Person.objects.create(name='Eu')
        self.vitoria = Person.objects.create(name='Vitória')
        self.other = Person.objects.create(name='Outro')
        self.today = date(2026, 9, 10)


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
        self.assertEqual(summary['card_invoice'], Decimal('30.00'))
        self.assertEqual(summary['expenses'], Decimal('30.00'))
        self.assertEqual(summary['final_balance'], Decimal('-30.00'))

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
        self.assertRedirects(response, reverse('finance:dashboard'))
        self.assertEqual(CreditCardExpense.objects.get().amount, Decimal('30.00'))
        self.assertEqual(CreditCardExpense.objects.get().vr_amount, Decimal('50.00'))
        self.assertEqual(VRMovement.objects.get().amount, Decimal('50.00'))

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
        self.assertContains(response, 'vr-highlight')
        self.assertEqual(monthly_summary(2026, 9)['card_invoice'], Decimal('30.00'))


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
        summary = monthly_summary(2026, 9)
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
        )
        summary = monthly_summary(2026, 9)
        expected_out = Decimal('660.06') + Decimal('159.74') + Decimal('40.00') + Decimal('100.00')
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
        response = self.client.post(reverse('finance:settings'), {
            'salary_gross': '3000.00',
            'salary_net': '2450.00',
            'previous_net_salary': '2299.00',
            'vr_monthly_credit': '550.00',
        })
        self.assertRedirects(response, reverse('finance:settings'))
        profile = FinancialProfile.objects.get(pk=1)
        self.assertEqual(profile.salary_net, Decimal('2450.00'))
        self.assertEqual(profile.vr_monthly_credit, Decimal('550.00'))


class FinalRefinementTests(BaseFinanceTest):
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
        self.assertEqual(item.invoice_month, date(2026, 9, 1))
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
        response = self.client.post(reverse('finance:pay_bill') + '?year=2026&month=9', {'amount': '200.00', 'paid_at': '2026-10-05'})
        self.assertEqual(response.status_code, 302)
        bill = CreditCardBill.objects.get(invoice_month=date(2026, 9, 1))
        self.assertEqual(bill.status, CreditCardBill.Status.PAID)
        self.assertEqual(bill.paid_at, date(2026, 10, 5))
        self.assertEqual(CreditCardExpense.objects.filter(paid=True).count(), 0)
        self.assertEqual(CreditCardExpense.objects.count(), 3)
        self.assertEqual(monthly_summary(2026, 9)['expenses'], Decimal('200.00'))

    def test_bill_payment_can_be_undone_and_months_are_independent(self):
        self.client.post(reverse('finance:pay_bill') + '?year=2026&month=9', {'amount': '100.00', 'paid_at': '2026-10-05'})
        self.assertEqual(CreditCardBill.objects.get(invoice_month=date(2026, 9, 1)).status, CreditCardBill.Status.PAID)
        self.assertFalse(CreditCardBill.objects.filter(invoice_month=date(2026, 10, 1)).exists())
        response = self.client.post(reverse('finance:undo_bill_payment') + '?year=2026&month=9')
        self.assertEqual(response.status_code, 302)
        bill = CreditCardBill.objects.get(invoice_month=date(2026, 9, 1))
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


class AuthenticationTests(TestCase):
    def test_finance_requires_login(self):
        response = self.client.get(reverse('finance:dashboard'))
        self.assertRedirects(response, '/login/?next=/')

    def test_login_page_is_available(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
