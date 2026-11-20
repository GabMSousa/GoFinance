import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.db import transaction

from .models import Category, CreditCardExpense, Person, Transaction
from .services import invoice_month_for_purchase, sync_card_vr

csv.field_size_limit(1024 * 1024)


ALIASES = {
    'date': {'date', 'data', 'transactiondate', 'purchasedate', 'datamovimento', 'datadolancamento'},
    'description': {'description', 'descricao', 'descrição', 'title', 'titulo', 'merchant', 'name', 'historico', 'histórico', 'lancamento', 'movimento'},
    'detail': {'detail', 'detalhe', 'complemento', 'memo', 'observacao', 'observação'},
    'amount': {'amount', 'valor', 'value', 'total', 'transactionamount', 'valorlancamento', 'debit', 'debito', 'credit', 'credito'},
    'balance': {'balance', 'saldo', 'runningbalance', 'saldofinal'},
    'vr_amount': {'vr', 'vramount', 'valerefeicao', 'voucher'},
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


def parse_signed_amount(value):
    raw = str(value or '').strip().replace('R$', '').replace(' ', '')
    negative = raw.startswith('-') or raw.startswith('(') or raw.upper().endswith(('D', 'DR'))
    raw = raw.strip('()').rstrip('DdRr')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    amount = Decimal(raw).quantize(Decimal('0.01'))
    return -abs(amount) if negative else abs(amount)


def parse_date(value):
    raw = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d', '%d-%m-%Y'):
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


def import_hash(purchase_date, description, amount, current, total, invoice_month, occurrence=1):
    raw = f'{purchase_date.isoformat()}|{normalize(description)}|{amount:.2f}|{current}/{total}|{invoice_month.isoformat()}'
    if occurrence > 1:
        raw += f'|occurrence:{occurrence}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _field_map(fieldnames):
    result = {}
    for field in fieldnames or []:
        key = normalize(field)
        for target, aliases in ALIASES.items():
            if key in {normalize(item) for item in aliases}:
                result[target] = field
    return result


def _decode_csv(content):
    if isinstance(content, bytes):
        for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode('utf-8-sig', errors='replace')
    return str(content)


def _csv_rows_with_header(content):
    """Read CSVs with preambles, BOMs and common bank delimiters."""
    text = _decode_csv(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError('O arquivo CSV está vazio.')
    candidates = []
    for delimiter in (';', '\t', ','):
        for index, line in enumerate(lines):
            fields = next(csv.reader([line], delimiter=delimiter), [])
            mapped = _field_map(fields)
            if {'date', 'description', 'amount'} <= set(mapped):
                candidates.append((index, delimiter))
                break
    if not candidates:
        raise ValueError('Não encontrei um cabeçalho com colunas de data, descrição e valor no CSV.')
    header_index, delimiter = min(candidates, key=lambda item: item[0])
    reader = csv.DictReader(io.StringIO('\n'.join(lines[header_index:])), delimiter=delimiter)
    return reader, _field_map(reader.fieldnames)


def _bank_description(raw, fields):
    description = (raw.get(fields['description']) or '').strip()
    detail = (raw.get(fields.get('detail', '')) or '').strip() if fields.get('detail') else ''
    if detail and normalize(detail) != normalize(description):
        description = f'{description} - {detail}'
    return description[:180]


def _payment_method_for_bank(description):
    normalized = normalize(description)
    if 'pix' in normalized:
        return Transaction.PaymentMethod.PIX
    return Transaction.PaymentMethod.DEBIT


def _revenue_type_for_bank(description):
    """Classify salary deposits so they replace, rather than add to, the fallback salary."""
    normalized = normalize(description)
    salary_terms = (
        'salario', 'folha', 'provento', 'ordenado',
        'adiantamentosalarial', 'pagamentosalarial',
    )
    if any(term in normalized for term in salary_terms):
        return Transaction.RevenueType.SALARY
    return Transaction.RevenueType.OTHER


def preview_csv(content, invoice_month=None):
    if hasattr(content, 'read'):
        content = content.read()
    reader, fields = _csv_rows_with_header(content)
    bank_statement = 'balance' in fields or 'detail' in fields
    rows = []
    occurrences = {}
    for row_number, raw in enumerate(reader, start=2):
        if row_number > 10000:
            raise ValueError('O arquivo CSV excede o limite de 10.000 linhas.')
        description = _bank_description(raw, fields)
        if not description:
            continue
        normalized_description = normalize(description)
        if bank_statement and any(word in normalized_description for word in ('abertura', 'saldoinicial', 'saldoanterior', 'encerramento')):
            continue
        try:
            purchase_date = parse_date(raw.get(fields['date']))
            signed_amount = parse_signed_amount(raw.get(fields['amount']))
            amount = abs(signed_amount)
            if not amount:
                continue
            vr_amount = parse_amount(raw.get(fields['vr_amount'])) if fields.get('vr_amount') else Decimal('0.00')
            if vr_amount > amount:
                raise ValueError('O valor de VR não pode ser maior que o total da compra.')
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f'Linha inválida para {description}: {exc}') from exc
        if bank_statement:
            fingerprint = hashlib.sha256(f'bank|{purchase_date.isoformat()}|{normalized_description}|{signed_amount:.2f}'.encode('utf-8')).hexdigest()
            transaction_type = Transaction.Type.REVENUE if signed_amount > 0 else Transaction.Type.EXPENSE
            existing = Transaction.objects.filter(date=purchase_date, amount=amount, type=transaction_type)
            duplicate = any(normalize(item.description) == normalized_description for item in existing)
            rows.append({
                'record_type': 'transaction', 'purchase_date': purchase_date.isoformat(),
                'description': description, 'amount': str(amount), 'signed_amount': str(signed_amount),
                'type': transaction_type, 'payment_method': _payment_method_for_bank(description),
                'category': category_for(description), 'duplicate': duplicate, 'duplicate_reason': '',
                'import_hash': fingerprint, 'occurrence': 1,
            })
            continue
        if any(word in normalized_description for word in ('pagamentorecebido', 'pagamentodefatura', 'estorno')):
            continue
        current, total = installment_for(description, raw.get(fields.get('installment', ''), ''))
        # A data do CSV pertence à fatura importada; parcelas novas avançam no cadastro manual.
        row_invoice_month = invoice_month_for_purchase(purchase_date)
        card_amount = (amount - vr_amount).quantize(Decimal('0.01'))
        occurrence_key = (purchase_date, normalized_description, card_amount, current, total, row_invoice_month)
        occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
        occurrence = occurrences[occurrence_key]
        fingerprint = import_hash(purchase_date, description, amount, current, total, row_invoice_month, occurrence)
        existing = [
            item for item in CreditCardExpense.objects.filter(
                Q(purchase_date=purchase_date) | Q(date=purchase_date),
                total_installments=total,
                current_installment=current,
            )
            if normalize(item.description) == normalized_description
            and item.amount == card_amount
        ]
        duplicate = bool(
            len(existing) >= occurrence
            or CreditCardExpense.objects.filter(import_hash=fingerprint).exists()
        )
        rows.append({
            'purchase_date': purchase_date.isoformat(), 'description': description,
            'amount': str(amount), 'vr_amount': str(vr_amount), 'current_installment': current, 'total_installments': total,
            'invoice_month': row_invoice_month.isoformat(), 'category': category_for(description),
            'duplicate': duplicate, 'duplicate_reason': '',
            'import_hash': fingerprint, 'occurrence': occurrence,
        })
    return rows


def _preview_bank_lines(lines):
    """Convert text lines from a bank statement PDF into transaction rows."""
    money_pattern = re.compile(r'(?P<value>[-(]?\s*(?:R\$\s*)?\d{1,3}(?:(?:\.\d{3})|(?:,\d{3}))*[.,]\d{2}\s*\)?)')
    date_pattern = re.compile(r'(?P<date>\d{2}/\d{2}/(?:\d{4}|\d{2}))')
    rows = []
    for line in lines:
        line = re.sub(r'\s+', ' ', line or '').strip()
        date_match = date_pattern.search(line)
        if not date_match:
            continue
        try:
            movement_date = parse_date(date_match.group('date'))
        except ValueError:
            continue
        rest = line[date_match.end():].strip(' -|')
        money_match = money_pattern.search(rest)
        if not money_match:
            continue
        description = rest[:money_match.start()].strip(' -|')[:180]
        if not description:
            continue
        normalized_description = normalize(description)
        if any(word in normalized_description for word in ('abertura', 'saldoinicial', 'saldoanterior', 'encerramento')):
            continue
        try:
            signed_amount = parse_signed_amount(money_match.group('value'))
        except (ValueError, InvalidOperation):
            continue
        if not signed_amount:
            continue
        amount = abs(signed_amount)
        transaction_type = Transaction.Type.REVENUE if signed_amount > 0 else Transaction.Type.EXPENSE
        existing = Transaction.objects.filter(date=movement_date, amount=amount, type=transaction_type)
        duplicate = any(normalize(item.description) == normalized_description for item in existing)
        fingerprint = hashlib.sha256(f'bank-pdf|{movement_date.isoformat()}|{normalized_description}|{signed_amount:.2f}'.encode('utf-8')).hexdigest()
        rows.append({
            'record_type': 'transaction', 'purchase_date': movement_date.isoformat(),
            'description': description, 'amount': str(amount), 'signed_amount': str(signed_amount),
            'type': transaction_type, 'payment_method': _payment_method_for_bank(description),
            'category': category_for(description), 'duplicate': duplicate, 'duplicate_reason': '',
            'import_hash': fingerprint, 'occurrence': 1,
        })
    return rows


def preview_pdf(content):
    """Extract text-based bank statement PDFs; scanned PDFs need OCR first."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('A importação de PDF precisa da dependência pypdf instalada.') from exc
    if hasattr(content, 'read'):
        content = content.read()
    try:
        reader = PdfReader(io.BytesIO(content))
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except Exception as exc:
        raise ValueError(f'Não foi possível ler o PDF do extrato: {exc}') from exc
    rows = _preview_bank_lines(text.splitlines())
    if not rows:
        raise ValueError('O PDF não contém texto de movimentações reconhecível. Use um PDF pesquisável ou exporte o extrato em CSV.')
    return rows


def preview_statement(content, filename=''):
    """Dispatch CSV/PDF import while preserving the existing CSV card flow."""
    if str(filename or '').lower().endswith('.pdf'):
        return preview_pdf(content)
    return preview_csv(content)


@transaction.atomic
def import_preview_rows(rows, invoice_month=None, source_name='CSV'):
    category_map = {item.name: item for item in Category.objects.all()}
    for name in {row['category'] for row in rows}:
        category_map.setdefault(name, Category.objects.get_or_create(name=name, defaults={'active': True})[0])
    person, _ = Person.objects.get_or_create(name='Eu', defaults={'active': True})
    created = skipped = 0
    for row in rows:
        if row.get('record_type') == 'transaction':
            purchase_date = date.fromisoformat(row['purchase_date'])
            amount = Decimal(row['amount'])
            matching = Transaction.objects.filter(date=purchase_date, amount=amount, type=row['type'], payment_method=row['payment_method'])
            if row.get('duplicate') or any(normalize(item.description) == normalize(row['description']) for item in matching):
                skipped += 1
                continue
            person = Person.objects.get_or_create(name='Eu', defaults={'active': True})[0]
            Transaction.objects.create(
                date=purchase_date, description=row['description'], category=category_map.get(row['category']),
                type=row['type'], payment_method=row['payment_method'], amount=amount,
                paid=row['type'] == Transaction.Type.EXPENSE, received=row['type'] == Transaction.Type.REVENUE,
                person=person,
                revenue_type=_revenue_type_for_bank(row['description']) if row['type'] == Transaction.Type.REVENUE else '',
                notes=f'{source_name}; importado automaticamente do extrato CSV.',
            )
            created += 1
            continue
        import_hash = row['import_hash']
        purchase_date = date.fromisoformat(row['purchase_date'])
        current, total = int(row['current_installment']), int(row['total_installments'])
        occurrence = int(row.get('occurrence') or 1)
        row_invoice_month = date.fromisoformat(row['invoice_month']) if row.get('invoice_month') else invoice_month_for_purchase(purchase_date)
        vr_amount = Decimal(row.get('vr_amount') or '0.00')
        card_amount = (Decimal(row['amount']) - vr_amount).quantize(Decimal('0.01'))
        matching = list(CreditCardExpense.objects.filter(
            purchase_date=purchase_date,
            description=row['description'],
            amount=card_amount,
            current_installment=current,
            total_installments=total,
        ).order_by('id'))
        if (
            row.get('duplicate')
            or CreditCardExpense.objects.filter(import_hash=import_hash).exists()
        ):
            keeper = matching[occurrence - 1] if len(matching) >= occurrence else (matching[0] if matching else None)
            if keeper:
                # A CSV row represents the statement being imported. Keep its
                # competence even when an older import put the installment in
                # a future month, and remove duplicate copies of that row.
                CreditCardExpense.objects.filter(pk=keeper.pk).update(invoice_month=row_invoice_month)
            skipped += 1
            continue
        expense = CreditCardExpense.objects.create(
            date=purchase_date, purchase_date=purchase_date, invoice_month=row_invoice_month,
            description=row['description'], amount=card_amount,
            category=category_map.get(row['category']) or category_map.get('Outros'), person=person,
            current_installment=current, total_installments=total,
            total_amount=(Decimal(row['amount']) * total).quantize(Decimal('0.01')),
            reimbursable=False, notes=f'{source_name}; importado via prévia CSV.',
            vr_amount=vr_amount,
            import_hash=row['import_hash'],
        )
        # CreditCardExpense.save() applies the manual-installment rule. CSV
        # imports must retain the statement competence calculated above.
        CreditCardExpense.objects.filter(pk=expense.pk).update(invoice_month=row_invoice_month)
        sync_card_vr(expense)
        created += 1
    return created, skipped
