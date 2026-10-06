from django.contrib import admin

from .models import Category, CreditCardBill, CreditCardExpense, FinancialProfile, FixedExpense, Goal, Investment, Person, SalarySnapshot, Transaction, VRMovement


@admin.register(FinancialProfile)
class FinancialProfileAdmin(admin.ModelAdmin):
    list_display = ('salary_gross', 'salary_net', 'previous_net_salary', 'vr_monthly_credit', 'updated_at')


@admin.register(SalarySnapshot)
class SalarySnapshotAdmin(admin.ModelAdmin):
    list_display = ('month', 'salary_gross', 'salary_net', 'vr_monthly_credit')
    date_hierarchy = 'month'


@admin.register(CreditCardBill)
class CreditCardBillAdmin(admin.ModelAdmin):
    list_display = ('invoice_month', 'amount', 'status', 'paid_at')
    list_filter = ('status',)
    date_hierarchy = 'invoice_month'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('name',)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'type', 'amount', 'payment_method', 'person', 'paid')
    list_filter = ('type', 'payment_method', 'paid', 'reimbursable', 'received')
    search_fields = ('description', 'notes')
    date_hierarchy = 'date'


@admin.register(FixedExpense)
class FixedExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'category', 'amount', 'due_day', 'recurrence', 'is_subscription', 'paid', 'active')
    list_filter = ('active', 'paid', 'is_subscription', 'recurrence', 'included_in_credit_card', 'payment_method')
    search_fields = ('description',)


@admin.register(CreditCardExpense)
class CreditCardExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'amount', 'person', 'current_installment', 'total_installments', 'paid', 'received')
    list_filter = ('reimbursable', 'paid', 'received', 'person')
    search_fields = ('description', 'notes')
    date_hierarchy = 'date'


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'type', 'amount', 'current_balance')
    list_filter = ('type',)
    search_fields = ('description',)
    date_hierarchy = 'date'


@admin.register(VRMovement)
class VRMovementAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'movement_type', 'amount')
    list_filter = ('movement_type',)
    search_fields = ('description',)
    date_hierarchy = 'date'


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('name', 'target_amount', 'current_amount', 'deadline', 'active')
    list_filter = ('active',)
    search_fields = ('name', 'notes')
