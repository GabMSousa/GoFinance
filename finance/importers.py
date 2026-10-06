import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .models import Category, CreditCardExpense, Person


ALIASES = {
    'date': {'date', 'data', 'transactiondate', 'purchasedate'},
    'description': {'description', 'descricao', 'descrição', 'title', 'titulo', 'merchant', 'name'},
    'amount': {'amount', 'valor', 'value', 'total'},
    'installment': {'installment', 'parcela', 'parcelas'},
}


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '', text)


def parse_amount(value):
    raw = str(value or '').strip().replace('R$', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    return abs(Decimal(raw).quantize(Decimal('0.01')))


def parse_date(value):
    raw = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f'Data inválida: {raw}')


def category_for(description):
    text = normalize(description)
    rules = {
        'Mercado': ('mercado', 'supermercado', 'condor', 'carrefour', 'festval'),
        'Combustível': ('posto', 'combust', 'shell', 'ipiranga'),
        'Assinaturas': ('spotify', 'netflix', 'amazon prime', 'streaming'),
        'Transporte': ('uber', '99app', 'taxi'),
        'Restaurante': ('ifood', 'restaurante', 'lanchonete'),
        'Saúde': ('farmacia', 'drogazem', 'hospital'),
        'Compras': ('mercadolivre', 'pichau', 'shopping'),
    }
    for name, keywords in rules.items():
        if any(normalize(keyword) in text for keyword in keywords):
            return name
    return 'Outros'


def installment_for(description, raw=''):
    match = re.search(r'(?:parcela\s*)?(\d+)\s*/\s*(\d+)', f'{description} {raw}', re.I)
    return (int(match.group(1)), int(match.group(2))) if match else (1, 1)


def import_hash(purchase_date, description, amount, current, total, invoice_month):
    raw = f'{purchase_date.isoformat()}|{normalize(description)}|{amount:.2f}|{current}/{total}|{invoice_month.isoformat()}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _field_map(fieldnames):
    result = {}
    for field in fieldnames or []:
        key = normalize(field)
        for target, aliases in ALIASES.items():
            if key in {normalize(item) for item in aliases}:
                result[target] = field
    return result


def preview_csv(content, invoice_month):
    if hasattr(content, 'read'):
        content = content.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(content))
    fields = _field_map(reader.fieldnames)
    missing = [name for name in ('date', 'description', 'amount') if name not in fields]
    if missing:
        raise ValueError(f'Colunas obrigatórias ausentes: {", ".join(missing)}')
    rows = []
    for raw in reader:
        description = (raw.get(fields['description']) or '').strip()
        if not description:
            continue
        normalized_description = normalize(description)
        if any(word in normalized_description for word in ('pagamentorecebido', 'pagamentodefatura', 'estorno')):
            continue
        try:
            purchase_date = parse_date(raw.get(fields['date']))
            amount = parse_amount(raw.get(fields['amount']))
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f'Linha inválida para {description}: {exc}') from exc
        current, total = installment_for(description, raw.get(fields.get('installment', ''), ''))
        fingerprint = import_hash(purchase_date, description, amount, current, total, invoice_month)
        legacy_duplicate = CreditCardExpense.objects.filter(
            invoice_month=invoice_month, description=description, amount=amount,
        ).exists() or CreditCardExpense.objects.filter(
            date=invoice_month, description=description, amount=amount,
        ).exists()
        duplicate = bool(CreditCardExpense.objects.filter(import_hash=fingerprint).exists() or legacy_duplicate)
        rows.append({
            'purchase_date': purchase_date.isoformat(), 'description': description,
            'amount': str(amount), 'current_installment': current, 'total_installments': total,
            'category': category_for(description), 'duplicate': duplicate, 'import_hash': fingerprint,
        })
    return rows


def import_preview_rows(rows, invoice_month, source_name='CSV'):
    category_map = {item.name: item for item in Category.objects.all()}
    for name in {row['category'] for row in rows}:
        category_map.setdefault(name, Category.objects.get_or_create(name=name, defaults={'active': True})[0])
    person, _ = Person.objects.get_or_create(name='Eu', defaults={'active': True})
    created = skipped = 0
    for row in rows:
        if row.get('duplicate') or CreditCardExpense.objects.filter(import_hash=row['import_hash']).exists():
            skipped += 1
            continue
        purchase_date = date.fromisoformat(row['purchase_date'])
        current, total = int(row['current_installment']), int(row['total_installments'])
        CreditCardExpense.objects.create(
            date=invoice_month, purchase_date=purchase_date, invoice_month=invoice_month,
            description=row['description'], amount=Decimal(row['amount']),
            category=category_map.get(row['category']) or category_map.get('Outros'), person=person,
            current_installment=current, total_installments=total,
            total_amount=(Decimal(row['amount']) * total).quantize(Decimal('0.01')),
            reimbursable=False, notes=f'{source_name}; importado via prévia CSV.',
            import_hash=row['import_hash'],
        )
        created += 1
    return created, skipped
