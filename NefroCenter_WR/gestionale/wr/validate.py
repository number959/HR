"""Controlli comuni sui dati ricevuti, con messaggi chiari in italiano.

Ogni funzione restituisce il valore normalizzato oppure solleva Invalid con
l'indicazione del campo, così l'interfaccia può evidenziarlo.
"""
import math
import re
from datetime import date

from .errors import Invalid

CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
SINGLE_LINE = re.compile(r'[\x00-\x1f\x7f]')
EMAIL_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}")
LABEL = re.compile(r'[A-Za-z0-9 _-]{1,40}')


def text(value, label, maximum=200, *, required=False, multiline=False, field=None, minimum=0):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise Invalid(f'{label}: inserire un testo.', field=field)
    if len(value) > maximum:
        raise Invalid(f'{label}: massimo {maximum} caratteri.', field=field)
    forbidden = CONTROL if multiline else SINGLE_LINE
    if forbidden.search(value):
        raise Invalid(f'{label}: contiene caratteri non ammessi.', field=field)
    value = value.strip()
    if required and not value:
        raise Invalid(f'{label}: campo obbligatorio.', field=field)
    if minimum and value and len(value) < minimum:
        raise Invalid(f'{label}: almeno {minimum} caratteri.', field=field)
    return value


def reason(value, label='Motivazione', field='reason'):
    """Motivazioni richieste per operazioni registrate nello storico: 8–1000 caratteri."""
    value = text(value, label, 1000, required=True, multiline=True, field=field)
    if len(value) < 8:
        raise Invalid(f'{label}: indicare almeno 8 caratteri.', field=field)
    return value


def integer(value, label, lo=None, hi=None, *, field=None):
    if type(value) is not int:
        raise Invalid(f'{label}: inserire un numero intero.', field=field)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise Invalid(f'{label}: valore ammesso da {lo} a {hi}.', field=field)
    return value


def number(value, label, lo=None, hi=None, *, field=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Invalid(f'{label}: inserire un numero.', field=field)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise Invalid(f'{label}: valore ammesso da {lo} a {hi}.', field=field)
    return value


def boolean(value, label, *, field=None):
    if type(value) is not bool:
        raise Invalid(f'{label}: indicare sì o no.', field=field)
    return value


def choice(value, label, options, *, field=None):
    if not isinstance(value, str) or value not in options:
        raise Invalid(f'{label}: valore non previsto.', field=field)
    return value


def day(value, label='Data', *, required=True, field=None):
    if value in (None, '') and not required:
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise Invalid(f'{label}: usare una data valida (AAAA-MM-GG).', field=field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise Invalid(f'{label}: data inesistente.', field=field) from None
    if not 1900 <= parsed.year <= 2200:
        raise Invalid(f'{label}: anno fuori intervallo.', field=field)
    return value


def month(value, label='Mese', *, field=None):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise Invalid(f'{label}: usare il formato AAAA-MM.', field=field)
    if not 1900 <= int(value[:4]) <= 2200:
        raise Invalid(f'{label}: anno fuori intervallo.', field=field)
    return value


def clock(value, label='Orario', *, required=False, field=None):
    if value in (None, '') and not required:
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise Invalid(f'{label}: usare il formato HH:MM.', field=field)
    return value


def email(value, label='Email', *, required=False, field=None):
    value = text(value, label, 254, required=required, field=field)
    if not value:
        return ''
    if not is_email(value):
        raise Invalid(f'{label}: indirizzo email non valido.', field=field)
    local, domain = value.rsplit('@', 1)
    return local + '@' + domain.encode('idna').decode('ascii').lower()


def is_email(value):
    if not isinstance(value, str) or value.count('@') != 1 or any(ch.isspace() for ch in value):
        return False
    local, domain = value.rsplit('@', 1)
    if not EMAIL_LOCAL.fullmatch(local) or local.startswith('.') or local.endswith('.') or '..' in local:
        return False
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        return False
    parts = domain.split('.')
    return (len(domain) <= 253 and len(parts) >= 2 and
            all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p) for p in parts))


def version(value, label='Versione'):
    """Numero di versione inviato dal client per il controllo di concorrenza."""
    if type(value) is not int or value < 0:
        raise Invalid(f'{label} non valida: ricaricare la pagina.', field='version')
    return value


def identifier(value, label='Riferimento', *, required=True, field=None):
    if value in (None, '') and not required:
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise Invalid(f'{label} non valido: ricaricare la pagina.', field=field)
    return value


def code(value, label='Codice', maximum=12, *, field=None):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,%d}' % maximum, value):
        raise Invalid(f'{label}: lettere, numeri o trattino basso, massimo {maximum} caratteri.', field=field)
    return value


def color(value, label='Colore', *, field=None):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise Invalid(f'{label}: usare un colore esadecimale come #2f6db5.', field=field)
    return value.lower()


def str_list(value, label, *, maximum=100, item_max=120, allowed=None, field=None, unique=True):
    if value is None:
        value = []
    if not isinstance(value, list) or len(value) > maximum:
        raise Invalid(f'{label}: elenco non valido (massimo {maximum} voci).', field=field)
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > item_max or CONTROL.search(item):
            raise Invalid(f'{label}: voce non valida.', field=field)
        item = item.strip()
        if allowed is not None and item not in allowed:
            raise Invalid(f'{label}: voce non prevista ({item}).', field=field)
        if not unique or item not in out:
            out.append(item)
    return out


def keys(raw, allowed, label='Dati', *, required=()):
    """Rifiuta campi non previsti e verifica quelli obbligatori."""
    if not isinstance(raw, dict):
        raise Invalid(f'{label}: formato non valido.')
    extra = set(raw) - set(allowed)
    if extra:
        raise Invalid(f'{label}: campi non previsti ({", ".join(sorted(extra))}).')
    missing = [k for k in required if k not in raw]
    if missing:
        raise Invalid(f'{label}: mancano {", ".join(missing)}.')
    return raw
