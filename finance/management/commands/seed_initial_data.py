import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from finance.models import Category, Person, UserSecurityProfile
from finance.ownership import get_current_user


class Command(BaseCommand):
    help = 'Cria somente a estrutura neutra de uma instalação nova, sem dados financeiros pessoais.'

    def handle(self, *args, **options):
        password = os.environ.get('DJANGO_ADMIN_PASSWORD', '')
        user_model = get_user_model()
        current_user = get_current_user()
        owner_user = current_user or user_model.objects.order_by('id').first()

        if password:
            admin_user, created = user_model.objects.get_or_create(
                username=os.environ.get('DJANGO_ADMIN_USERNAME', 'admin'),
                defaults={'is_staff': True, 'is_superuser': True, 'email': ''},
            )
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.set_password(password)
            admin_user.save(update_fields=['password', 'is_staff', 'is_superuser'])
            profile, profile_created = UserSecurityProfile.objects.get_or_create(user=admin_user)
            if created or profile_created:
                profile.must_change_password = True
                profile.save(update_fields=['must_change_password', 'updated_at'])
            owner_user = current_user or admin_user
            self.stdout.write(self.style.SUCCESS(f'Usuário administrador {admin_user.username} configurado.'))
        elif owner_user is None:
            raise CommandError(
                'Defina DJANGO_ADMIN_PASSWORD ou crie o primeiro usuário administrador antes de inicializar.'
            )
        else:
            self.stdout.write('DJANGO_ADMIN_PASSWORD não definida; usuário inicial não foi criado/alterado.')

        categories = [
            'Alimentação', 'Restaurante', 'Mercado', 'Combustível', 'Transporte',
            'Assinaturas', 'Compras', 'Lazer', 'Saúde', 'Investimentos', 'Outros',
        ]
        for name in categories:
            Category.objects.get_or_create(
                owner=owner_user,
                name=name,
                defaults={'active': True},
            )

        Person.objects.get_or_create(owner=owner_user, name='Eu', defaults={'active': True})
        self.stdout.write('Nenhuma conta fixa, compra, receita, fatura ou crédito de VR foi criado.')
        self.stdout.write(self.style.SUCCESS('Estrutura inicial criada/validada.'))
