"""Portable, user-scoped backup and restore for GoFinance.

The export intentionally contains financial records only. Authentication
credentials, Django sessions, environment variables, uploaded avatars and
secrets never leave the installation.
"""

from datetime import date, datetime
from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Category,
    CreditCardBill,
    CreditCardExpense,
    FinancialProfile,
    FixedExpense,
    Goal,
    Investment,
    InvestmentOperation,
    Person,
    SalarySnapshot,
    Transaction,
    VRMovement,
)
from .rules import SALARY_COMPETENCE_LAG_MONTHS, invoice_month_for_purchase, vr_reference_month


SCHEMA = 'gofinance.portable'
VERSION = 1
MAX_IMPORT_BYTES = 10 * 1024 * 1024

USER_OWNED_MODELS = (
    Category,
    Person,
    Transaction,
    FixedExpense,
    Goal,
    FinancialProfile,
    SalarySnapshot,
    CreditCardBill,
    CreditCardExpense,
    VRMovement,
)


def _dump_value(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _load_value(field, value):
    if value is None:
        return None
    internal_type = field.get_internal_type()
    if internal_type == 'DecimalField':
        return Decimal(str(value))
    if internal_type == 'DateField':
        return date.fromisoformat(value)
    if internal_type == 'DateTimeField':
        parsed = datetime.fromisoformat(value)
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    return value


def _normalize_universal_rules(model, obj):
    """Keep imported records aligned with the system-wide financial rules."""
    if model is FinancialProfile:
        obj.salary_competence_lag_months = SALARY_COMPETENCE_LAG_MONTHS
    elif model is SalarySnapshot:
        obj.salary_competence_lag_months = SALARY_COMPETENCE_LAG_MONTHS
    elif model is CreditCardExpense:
        purchase_date = obj.purchase_date or obj.date
        if purchase_date:
            # A purchase made in November belongs to the December invoice.
            obj.invoice_month = invoice_month_for_purchase(purchase_date, obj.current_installment)
    elif model is VRMovement and obj.movement_type == VRMovement.Type.CREDIT and obj.date:
        # A credit received in November is shown in the December competence.
        obj.reference_month = vr_reference_month(obj.date)


def _record(model, obj):
    fields = {}
    for field in model._meta.concrete_fields:
        if field.primary_key or field.name in {'owner', 'user'}:
            continue
        if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
            continue
        fields[field.attname] = _dump_value(field.value_from_object(obj))
    return {'id': obj.pk, 'fields': fields}


def _records(model, queryset):
    return [_record(model, item) for item in queryset.order_by('pk')]


def build_export(user):
    """Return a JSON-serializable snapshot for one authenticated user."""
    payload = {
        'schema': SCHEMA,
        'version': VERSION,
        'exported_at': timezone.now().isoformat(),
        'data': {},
    }
    for model in USER_OWNED_MODELS:
        payload['data'][model._meta.model_name] = _records(model, model.objects.filter(owner=user))

    payload['data']['investments'] = _records(
        Investment,
        Investment.objects.filter(user=user),
    )
    payload['data']['investment_operations'] = _records(
        InvestmentOperation,
        InvestmentOperation.objects.filter(user=user),
    )
    return payload


def _records_for(payload, name):
    records = payload.get('data', {}).get(name, [])
    if not isinstance(records, list):
        raise ValidationError(f'O bloco {name} do arquivo não é uma lista válida.')
    return records


def _delete_user_data(user):
    # Delete dependants first because several relations use PROTECT/CASCADE.
    VRMovement.objects.filter(owner=user).delete()
    InvestmentOperation.objects.filter(user=user).update(reverses=None)
    InvestmentOperation.objects.filter(user=user).delete()
    CreditCardExpense.objects.filter(owner=user).delete()
    Transaction.objects.filter(owner=user).delete()
    FixedExpense.objects.filter(owner=user).delete()
    Goal.objects.filter(owner=user).delete()
    SalarySnapshot.objects.filter(owner=user).delete()
    CreditCardBill.objects.filter(owner=user).delete()
    FinancialProfile.objects.filter(owner=user).delete()
    Investment.objects.filter(user=user).delete()
    Category.objects.filter(owner=user).delete()
    Person.objects.filter(owner=user).delete()


def _target_for(model, user, source_id):
    if model is Investment:
        return Investment.objects.filter(user=user, pk=source_id).first()
    if model is InvestmentOperation:
        return InvestmentOperation.objects.filter(user=user, pk=source_id).first()
    return model.objects.filter(owner=user, pk=source_id).first()


def _new_object(model, user, source_id):
    # Keep source primary keys where possible. This makes re-imports update
    # the same records while still avoiding collisions with another user.
    if model is Investment:
        collision = Investment.objects.filter(pk=source_id).exclude(user=user).exists()
        return model(pk=None if collision else source_id, user=user)
    if model is InvestmentOperation:
        collision = InvestmentOperation.objects.filter(pk=source_id).exclude(user=user).exists()
        return model(pk=None if collision else source_id, user=user)
    collision = model.objects.filter(pk=source_id).exclude(owner=user).exists()
    return model(pk=None if collision else source_id, owner=user)


def _apply_fields(model, obj, raw_fields, maps):
    for field in model._meta.concrete_fields:
        if field.primary_key or field.name in {'owner', 'user'}:
            continue
        if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
            continue
        if field.attname not in raw_fields:
            continue
        if model is InvestmentOperation and field.name == 'reverses':
            # Reversal links are restored in a second pass after every
            # operation has received its destination primary key.
            continue
        value = raw_fields[field.attname]
        if field.is_relation:
            if value is not None:
                related_map = maps.get(field.remote_field.model, {})
                value = related_map.get(str(value))
                if value is None:
                    raise ValidationError(
                        f'Relação inválida para {model._meta.verbose_name}: {field.name}.'
                    )
            setattr(obj, field.attname, value)
        else:
            setattr(obj, field.name, _load_value(field, value))


def _import_records(model, records, user, maps):
    target_map = {}
    for record in records:
        if not isinstance(record, dict) or 'id' not in record:
            raise ValidationError(f'Registro inválido no bloco {model._meta.model_name}.')
        source_id = str(record['id'])
        obj = _target_for(model, user, record['id'])
        if obj is None and model is VRMovement:
            raw = record.get('fields', {})
            obj = VRMovement.objects.filter(
                owner=user,
                reference_month=_load_value(VRMovement._meta.get_field('reference_month'), raw.get('reference_month')),
                movement_type=raw.get('movement_type'),
            ).first()
        if obj is None:
            obj = _new_object(model, user, record['id'])
        _apply_fields(model, obj, record.get('fields', {}), maps)
        _normalize_universal_rules(model, obj)
        obj.full_clean()
        obj.save()
        target_map[source_id] = obj.pk
    maps[model] = target_map


def _import_investment_operations(records, user, maps):
    target_map = {}
    pending_reverses = []
    for record in records:
        source_id = str(record['id'])
        obj = _target_for(InvestmentOperation, user, record['id'])
        raw_key = record.get('fields', {}).get('operation_key')
        if obj is None and raw_key:
            obj = InvestmentOperation.objects.filter(user=user, operation_key=raw_key).first()
        if obj is None:
            key_taken = raw_key and InvestmentOperation.objects.filter(operation_key=raw_key).exclude(user=user).exists()
            obj = _new_object(InvestmentOperation, user, record['id'])
            if key_taken:
                record = {**record, 'fields': {**record.get('fields', {}), 'operation_key': uuid.uuid4().hex}}
        _apply_fields(InvestmentOperation, obj, record.get('fields', {}), maps)
        obj.investment_id = maps[Investment].get(str(record.get('fields', {}).get('investment_id')))
        if not obj.investment_id:
            raise ValidationError('Operação de investimento sem investimento relacionado.')
        obj.user = user
        obj.reverses_id = None
        obj.full_clean(exclude=['reverses'])
        obj.save()
        target_map[source_id] = obj.pk
        if record.get('fields', {}).get('reverses_id'):
            pending_reverses.append((obj, str(record['fields']['reverses_id'])))
    maps[InvestmentOperation] = target_map
    for obj, source_reverse in pending_reverses:
        obj.reverses_id = target_map.get(source_reverse)
        obj.save(update_fields=['reverses'])


@transaction.atomic
def import_snapshot(payload, user, replace_existing=False):
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA or payload.get('version') != VERSION:
        raise ValidationError('Arquivo incompatível. Exporte os dados pelo GoFinance atualizado.')
    if replace_existing:
        _delete_user_data(user)

    maps = {}
    order = (
        Category,
        Person,
        FinancialProfile,
        SalarySnapshot,
        CreditCardBill,
        Investment,
        Transaction,
        FixedExpense,
        Goal,
        CreditCardExpense,
    )
    for model in order:
        _import_records(model, _records_for(payload, model._meta.model_name), user, maps)
    _import_investment_operations(_records_for(payload, 'investment_operations'), user, maps)
    _import_records(VRMovement, _records_for(payload, 'vrmovement'), user, maps)

    return {
        'categories': len(_records_for(payload, 'category')),
        'transactions': len(_records_for(payload, 'transaction')),
        'fixed_expenses': len(_records_for(payload, 'fixedexpense')),
        'card_expenses': len(_records_for(payload, 'creditcardexpense')),
        'investments': len(_records_for(payload, 'investment')),
        'vr_movements': len(_records_for(payload, 'vrmovement')),
    }
