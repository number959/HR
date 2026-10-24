"""Rubrica condivisa delle strutture, collegata ai fascicoli tramite il centro.

I recapiti appartengono alla struttura e non vengono copiati nei dipendenti.
La rubrica non cambia le assegnazioni né le impostazioni delle presenze.
"""
import ipaddress
import json
import re
from urllib.parse import urlsplit


FIELD_DEFINITIONS = [
    ('legal_name', 'Ragione sociale', 200, 'text', 'Identità'),
    ('vat_number', 'Partita IVA', 30, 'text', 'Identità'),
    ('tax_code', 'Codice fiscale', 30, 'text', 'Identità'),
    ('address', 'Indirizzo', 250, 'text', 'Sede'),
    ('city', 'Comune', 100, 'text', 'Sede'),
    ('postal_code', 'CAP', 20, 'text', 'Sede'),
    ('province', 'Provincia', 60, 'text', 'Sede'),
    ('phone', 'Telefono', 60, 'tel', 'Recapiti'),
    ('email', 'Email generale', 254, 'email', 'Recapiti'),
    ('hr_email', 'Email ufficio HR', 254, 'email', 'Recapiti'),
    ('admin_email', 'Email amministrazione', 254, 'email', 'Recapiti'),
    ('pec', 'PEC', 254, 'email', 'Recapiti'),
    ('contact_name', 'Referente della struttura', 150, 'text', 'Referenti'),
    ('director', 'Direttore', 150, 'text', 'Referenti'),
    ('website', 'Sito web', 500, 'url', 'Recapiti'),
    ('notes', 'Note organizzative', 2000, 'textarea', 'Note'),
]
FIELDS = {key: limit for key, _, limit, _, _ in FIELD_DEFINITIONS}


def init(app):
    with app.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS structure_profiles(
            cid TEXT PRIMARY KEY REFERENCES centers(id),
            version INTEGER NOT NULL CHECK(version > 0), data TEXT NOT NULL)''')
        c.commit()


def definitions():
    return [dict(key=key, label=label, max_length=limit, type=kind, section=section)
            for key, label, limit, kind, section in FIELD_DEFINITIONS]


def record(c, cid):
    """Read on an existing, authorized connection (also used by hr.read)."""
    center = c.execute('SELECT id,name,code FROM centers WHERE id=?', (cid,)).fetchone()
    if not center:
        raise ValueError('Struttura non trovata.')
    row = c.execute('SELECT version,data FROM structure_profiles WHERE cid=?', (cid,)).fetchone()
    return dict(cid=center['id'], name=center['name'], code=center['code'],
                version=row['version'] if row else 0,
                fields={**{key: '' for key in FIELDS}, **(json.loads(row['data']) if row else {})})


def access(app, c, user, cid=None):
    user = app.fresh_user(c, user)
    if user['role'] not in ('admin', 'hr', 'manager'):
        raise PermissionError('Rubrica strutture riservata a HR e responsabili autorizzati.')
    if cid is not None:
        app.require_hr(user, cid)
        app.center(c, cid)
    return user


def read(app, user, cid=None):
    if cid is not None and (not isinstance(cid, str) or not cid):
        raise ValueError('Indicare una struttura valida.')
    cid = None if cid == 'all' else cid
    with app.connect() as c:
        user = access(app, c, user, cid)
        if cid is not None:
            return {'structure': record(c, cid), 'fields': definitions()}
        return {'structures': [record(c, ct['id']) for ct in app.centers_for(c, user)],
                'fields': definitions()}


def _email(value):
    if value.count('@') != 1 or any(ch.isspace() for ch in value):
        return False
    local, domain = value.rsplit('@', 1)
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}", local):
        return False
    if local.startswith('.') or local.endswith('.') or '..' in local:
        return False
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        return False
    return (len(domain) <= 253 and '.' in domain and
            all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                for part in domain.split('.')))


def _website(value):
    if any(ch.isspace() for ch in value) or '\\' in value:
        return False
    try:
        url = urlsplit(value)
        if (url.scheme not in ('http', 'https') or not url.netloc or not url.hostname
                or url.username is not None or url.password is not None):
            return False
        # Accessing port also checks invalid values and malformed authorities.
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        host = url.hostname
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            host = host.encode('idna').decode('ascii')
            return len(host) <= 253 and all(
                re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                for part in host.rstrip('.').split('.'))
    except (ValueError, UnicodeError):
        return False


def validate_fields(raw):
    if not isinstance(raw, dict) or set(raw) - set(FIELDS):
        raise ValueError('Campi della struttura non validi.')
    values = {}
    for key, label, limit, kind, _ in FIELD_DEFINITIONS:
        value = raw.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'{label}: usare un testo di massimo {limit} caratteri.')
        allowed_controls = '\n\r\t' if kind == 'textarea' else ''
        if any((ord(ch) < 32 or ord(ch) == 127) and ch not in allowed_controls for ch in value):
            raise ValueError(f'{label}: caratteri di controllo non consentiti.')
        value = value.strip()
        if value and kind == 'email' and not _email(value):
            raise ValueError(f'{label}: indirizzo email non valido.')
        if value and kind == 'url' and not _website(value):
            raise ValueError('Sito web: indicare un indirizzo completo http:// o https:// senza credenziali.')
        values[key] = value
    return values


def save(app, user, body):
    if not isinstance(body, dict) or not isinstance(body.get('cid'), str) or not body['cid']:
        raise ValueError('Indicare una struttura valida.')
    cid = body['cid']
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        user = access(app, c, user, cid)
        before = record(c, cid)
        version = body.get('version')
        if type(version) is not int or version != before['version']:
            raise ValueError('Scheda struttura aggiornata da un’altra sessione. Riaprire la scheda prima di salvare.')
        values = validate_fields(body.get('fields'))
        c.execute('''INSERT INTO structure_profiles(cid,version,data) VALUES(?,?,?)
            ON CONFLICT(cid) DO UPDATE SET version=excluded.version,data=excluded.data''',
                  (cid, version + 1, app.dump(values)))
        updated = record(c, cid)
        app.audit(c, user, 'Scheda struttura salvata', cid, before=before, after=updated)
        c.commit()
        return {'ok': True, 'structure': updated}
