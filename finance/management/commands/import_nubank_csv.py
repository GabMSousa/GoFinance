import csv
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from finance.models import Category, CreditCardExpense, FixedExpense, Person, Transaction
from finance.services import add_months


class Command(BaseCommand):
    help = 'Importa compras de um CSV Nubank para a fatura do cartão sem duplicar fixos ou pagamentos.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)
        parser.add_argument('--invoice-date', default='2026-10-01', help='Mês da fatura no formato YYYY-MM-DD.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['csv_path'])
        if not path.exists():
            raise CommandError(f'CSV não encontrado: {path}')
        try:
            invoice_date = date.fromisoformat(options['invoice_date'])
        except ValueError as exc:
            raise CommandError('--invoice-date deve usar YYYY-MM-DD.') from exc

        categories = {x.name: x for x in Category.objects.all()}
        people = {x.name: x for x in Person.objects.all()}
        required_categories = ['Saúde', 'Mercado', 'Combustível', 'Restaurante', 'Compras', 'Transporte', 'Assinaturas', 'Outros']
        missing = [name for name in required_categories if name not in categories]
        if missing:
            raise CommandError(f'Execute seed_initial_data antes. Categorias ausentes: {", ".join(missing)}')
        if 'Eu' not in people:
            raise CommandError('Execute seed_initial_data antes. Pessoa Eu ausente.')

        source_tag = f'CSV Nubank: {path.name}'
        created = skipped = 0
        total = Decimal('0.00')
        with path.open('r', encoding='utf-8-sig', newline='') as source:
            for row in csv.DictReader(source):
                title = (row.get('title') or '').strip()
                raw_amount = (row.get('amount') or '').strip().replace(' ', '').replace('.', '').replace(',', '.')
                try:
                    amount = Decimal(raw_amount)
                except InvalidOperation as exc:
                    raise CommandError(f'Valor inválido em {title!r}: {row.get("amount")}') from exc
                if amount <= 0 or 'pagamento recebido' in title.lower():
                    skipped += 1
                    continue

                category_name = self.category_for(title)
                person_name = self.person_for(title)
                person = people.get(person_name, people['Eu'])
                current, installments = self.installments_for(title)

                fixed = self.fixed_for(title)
                if fixed:
                    if not options['dry_run'] and fixed.included_in_credit_card is False:
                        fixed.included_in_credit_card = True
                        fixed.payment_method = Transaction.PaymentMethod.CREDIT_CARD
                        fixed.save(update_fields=['included_in_credit_card', 'payment_method', 'updated_at'])
                    skipped += 1
                    total += amount
                    self.stdout.write(f'FIXO mantido no cartão: {title} R$ {amount:.2f}')
                    continue

                if CreditCardExpense.objects.filter(
                    date=invoice_date,
                    description=title,
                    amount=amount,
                    notes__contains=source_tag,
                ).exists():
                    skipped += 1
                    continue

                if not options['dry_run']:
                    first = add_months(invoice_date, -(current - 1))
                    CreditCardExpense.objects.create(
                        date=invoice_date,
                        description=title,
                        category=categories[category_name],
                        amount=amount,
                        total_amount=(amount * installments).quantize(Decimal('0.01')),
                        person=person,
                        current_installment=current,
                        total_installments=installments,
                        first_installment=first,
                        last_installment=add_months(first, installments - 1),
                        reimbursable=person_name != 'Eu',
                        received=False,
                        notes=f'{source_tag}; fatura com vencimento em 01/11/2026.',
                        series_id=uuid.uuid4(),
                    )
                created += 1
                total += amount

        mode = 'simulação' if options['dry_run'] else 'importação'
        self.stdout.write(self.style.SUCCESS(f'{mode.capitalize()} concluída: {created} compras, {skipped} ignorados, total bruto R$ {total:.2f}.'))

    @staticmethod
    def fixed_for(title):
        normalized = title.lower()
        if 'coone[c]?ta' in normalized or 'coonecta' in normalized:
            return FixedExpense.objects.filter(description__iexact='Seguro Connecta').first()
        if 'spotify' in normalized:
            return FixedExpense.objects.filter(description__iexact='Spotify').first()
        return None

    @staticmethod
    def person_for(title):
        normalized = title.lower()
        if 'vitoria' in normalized:
            return 'Vitória'
        if 'maria juraci' in normalized or 'paulo ricardo' in normalized:
            return 'Outro'
        return 'Eu'

    @staticmethod
    def category_for(title):
        normalized = title.lower()
        if 'drogazem' in normalized:
            return 'Saúde'
        if any(word in normalized for word in ['posto', 'combust']):
            return 'Combustível'
        if any(word in normalized for word in ['volpi', 'pelanda', 'festval', 'supermercado']):
            return 'Mercado'
        if any(word in normalized for word in ['bom apetite', 'ifd', 'ifood']):
            return 'Restaurante'
        if 'uber' in normalized:
            return 'Transporte'
        if any(word in normalized for word in ['mercadolivre', 'pichau', 'jim.com', 'universo branco', '45.315.317']):
            return 'Compras'
        if 'spotify' in normalized:
            return 'Assinaturas'
        return 'Outros'

    @staticmethod
    def installments_for(title):
        match = re.search(r'parcela\s+(\d+)\s*/\s*(\d+)', title.lower())
        if not match:
            return 1, 1
        return int(match.group(1)), int(match.group(2))
