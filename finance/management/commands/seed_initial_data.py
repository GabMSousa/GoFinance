from datetime import date
from decimal import Decimal
import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from finance.models import Category, FixedExpense, Person, Transaction, VRMovement
from finance.services import monthly_credit_setting


class Command(BaseCommand):
    help = 'Cria categorias, responsáveis, gastos fixos e crédito mensal de VR sem duplicar.'

    def handle(self, *args, **options):
        categories = [
            'Alimentação', 'Restaurante', 'Mercado', 'Moto', 'Combustível',
            'Transporte', 'Internet', 'Faculdade', 'Academia', 'Assinaturas',
            'Compras', 'Lazer', 'Saúde', 'Investimentos', 'Outros',
        ]
        for name in categories:
            Category.objects.get_or_create(name=name, defaults={'active': True})

        Person.objects.get_or_create(name='Eu', defaults={'active': True})

        initial_fixed = [
            ('Moto', 'Moto', Decimal('660.06'), False, '', False),
            ('Seguro Connecta', 'Assinaturas', Decimal('159.74'), True, Transaction.PaymentMethod.CREDIT_CARD, False),
            ('Internet', 'Internet', Decimal('99.90'), False, '', False),
            ('Faculdade', 'Faculdade', Decimal('216.89'), False, '', False),
            ('Spotify', 'Assinaturas', Decimal('23.90'), False, '', True),
            ('Academia', 'Academia', Decimal('70.00'), False, '', False),
        ]
        for description, category_name, amount, included, payment_method, is_subscription in initial_fixed:
            category = Category.objects.get(name=category_name)
            FixedExpense.objects.update_or_create(
                description=description,
                defaults={
                    'category': category,
                    'amount': amount,
                    'active': True,
                    'included_in_credit_card': included,
                    'is_subscription': is_subscription,
                    'payment_method': payment_method,
                },
            )

        today = date.today()
        credit = monthly_credit_setting()
        VRMovement.objects.get_or_create(
            date=date(today.year, today.month, 1),
            description=f'Crédito mensal VR {today.month:02d}/{today.year}',
            movement_type=VRMovement.Type.CREDIT,
            defaults={'amount': credit, 'notes': 'Seed automático do crédito mensal de R$ 500,00.'},
        )

        password = os.environ.get('DJANGO_ADMIN_PASSWORD', '')
        if password:
            user_model = get_user_model()
            user, created = user_model.objects.get_or_create(
                username=os.environ.get('DJANGO_ADMIN_USERNAME', 'gabriel.sousa'),
                defaults={'is_staff': True, 'is_superuser': True, 'email': ''},
            )
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save(update_fields=['password', 'is_staff', 'is_superuser'])
            self.stdout.write(self.style.SUCCESS(f'Usuário administrador {user.username} configurado.'))
        else:
            self.stdout.write('DJANGO_ADMIN_PASSWORD não definida; usuário inicial não foi criado/alterado.')

        self.stdout.write(self.style.SUCCESS('Dados iniciais criados/validados.'))
