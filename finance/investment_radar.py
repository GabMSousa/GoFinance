"""Resilient public-data integration for the investment radar."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils.timezone import localdate, localtime, now


BCB_BASE = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/{count}?formato=json'
RADAR_CACHE_KEY = 'finance:investment-radar:v1'
SERIES = {'cdi': (12, 252), 'selic': (1178, 1), 'ipca': (433, 12)}


def _fetch_series(spec):
    series_id, count = spec
    if series_id == 12:
        end = localdate()
        start = end - timedelta(days=370)
        url = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados?formato=json&dataInicial={start:%d/%m/%Y}&dataFinal={end:%d/%m/%Y}'
    else:
        url = BCB_BASE.format(series=series_id, count=count)
    request = Request(
        url,
        headers={'Accept': 'application/json', 'User-Agent': 'GoFinance/1.0'},
    )
    for _attempt in range(2):
        try:
            with urlopen(request, timeout=3.5) as response:
                payload = json.loads(response.read().decode('utf-8'))
            if not isinstance(payload, list):
                continue
            rows = []
            for item in payload:
                if not isinstance(item, dict) or not item.get('data') or item.get('valor') in (None, ''):
                    continue
                try:
                    date_value = datetime.strptime(item['data'], '%d/%m/%Y').date()
                    value = Decimal(str(item['valor']).replace(',', '.'))
                except (TypeError, ValueError, InvalidOperation):
                    continue
                if value.is_finite() and -100 < value < 1000:
                    rows.append({'date': date_value.isoformat(), 'value': value})
            if rows:
                return rows
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return []


def _annualize_daily(rows):
    if not rows:
        return None
    rows = rows[-252:]
    factor = Decimal('1')
    for row in rows:
        factor *= Decimal('1') + row['value'] / Decimal('100')
    return ((factor ** (Decimal('252') / Decimal(len(rows)))) - Decimal('1')) * Decimal('100')


def _compound_monthly(rows):
    if not rows:
        return None
    factor = Decimal('1')
    for row in rows:
        factor *= Decimal('1') + row['value'] / Decimal('100')
    return (factor - Decimal('1')) * Decimal('100')


def _indicator(label, value, unit, rows, source, note=''):
    return {
        'label': label,
        'value': float(value) if value is not None else None,
        'formatted': f'{value:.2f}%' if value is not None else 'Indisponível',
        'unit': unit,
        'date': datetime.strptime(rows[-1]['date'], '%Y-%m-%d').strftime('%d/%m/%Y') if rows else None,
        'source': source,
        'note': note,
        'available': value is not None,
    }


def get_investment_radar(force=False):
    if not force:
        cached = cache.get(RADAR_CACHE_KEY)
        if cached:
            return cached
    rows = {key: _fetch_series(spec) for key, spec in SERIES.items()}
    cdi = _annualize_daily(rows['cdi'])
    selic = rows['selic'][-1]['value'] if rows['selic'] else None
    ipca = _compound_monthly(rows['ipca'])
    indicators = [
        _indicator('CDI de referência', cdi, '% a.a.', rows['cdi'], 'BCB SGS série 12', 'Taxa diária anualizada pela janela de 252 dias úteis.'),
        _indicator('Selic efetiva', selic, '% a.a.', rows['selic'], 'BCB SGS série 1178'),
        _indicator('IPCA acumulado em 12 meses', ipca, '%', rows['ipca'], 'BCB SGS série 433', 'Composição dos 12 últimos índices mensais publicados.'),
    ]
    result = {
        'updated_at': localtime(now()).strftime('%d/%m/%Y %H:%M'),
        'sync_state': 'atualizado',
        'available': any(item['available'] for item in indicators),
        'indicators': indicators,
        'offers': [],
        'offer_filters': {
            'institutions': ['Todas', 'Nubank', 'Outras'],
            'types': ['Todos', 'CDB', 'RDB', 'Tesouro Selic', 'Tesouro IPCA+', 'Tesouro Prefixado', 'Fundos', 'Acoes', 'ETFs', 'FIIs', 'Outros'],
            'returns': ['Todas', 'Pos-fixada', 'Prefixada', 'Hibrida', '% do CDI', 'IPCA + taxa'],
            'liquidity': ['Todas', 'Diaria', 'No vencimento', 'Com carencia'],
            'terms': ['Todos', 'Ate 30 dias', 'Ate 90 dias', 'Ate 1 ano', 'Acima de 1 ano', 'Personalizado'],
        },
        'sources': [
            {'label': 'Banco Central do Brasil', 'url': 'https://dadosabertos.bcb.gov.br/'},
            {'label': 'Nubank - investimentos', 'url': 'https://nubank.com.br/nu/investimentos/tesouro-direto'},
        ],
        'offers_message': 'Nenhuma oferta pública foi incluída: não há uma fonte oficial verificável configurada para comparar produtos neste momento.',
        'source_url': 'https://dadosabertos.bcb.gov.br/',
        'base_rate': float(cdi) if cdi is not None else None,
    }
    cache.set(RADAR_CACHE_KEY, result, getattr(settings, 'RADAR_CACHE_TIMEOUT', 21600))
    return result
