"""Funzioni di base: tempo, identificativi, JSON e calendario."""
import calendar
import json
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ZONE = ZoneInfo(os.environ.get('WR_TIMEZONE', 'Europe/Rome'))
except Exception:  # pragma: no cover - solo se manca tzdata
    ZONE = timezone.utc

# Le prove automatiche e la demo possono fissare "oggi" per avere risultati ripetibili.
_FIXED_TODAY = None


def set_today(value):
    """Usata da test e demo: fissa la data corrente (None per tornare all'orologio)."""
    global _FIXED_TODAY
    _FIXED_TODAY = date.fromisoformat(value) if isinstance(value, str) else value


def now():
    return datetime.now(ZONE)


def stamp():
    """Istante corrente in formato ISO con fuso orario, per storici e registri."""
    return now().isoformat(timespec='seconds')


def today():
    return _FIXED_TODAY or now().date()


def today_iso():
    return today().isoformat()


def new_id():
    return uuid.uuid4().hex


def token(nbytes=32):
    return secrets.token_urlsafe(nbytes)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=False)


def loads(text, default=None):
    if text is None or text == '':
        return default
    return json.loads(text)


def month_days(month):
    """Tutti i giorni ISO del mese 'AAAA-MM'."""
    first = date.fromisoformat(month + '-01')
    days = calendar.monthrange(first.year, first.month)[1]
    return [(first + timedelta(days=i)).isoformat() for i in range(days)]


def month_range(first, last):
    """Mesi da first a last inclusi (formato 'AAAA-MM')."""
    a = int(first[:4]) * 12 + int(first[5:]) - 1
    b = int(last[:4]) * 12 + int(last[5:]) - 1
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(a, b + 1)]


def previous_month(month):
    first = date.fromisoformat(month + '-01')
    return (first - timedelta(days=1)).strftime('%Y-%m')


def add_days(day, n):
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def weekday(day):
    """0 = lunedì … 6 = domenica."""
    return date.fromisoformat(day).weekday()


def csv_safe(value):
    """Evita che un foglio di calcolo interpreti il testo come formula."""
    if isinstance(value, str) and (value.lstrip()[:1] in ('=', '+', '-', '@') or value[:1] in ('\t', '\r')):
        return "'" + value
    return value
