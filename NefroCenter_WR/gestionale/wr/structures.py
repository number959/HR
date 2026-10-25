"""Rubrica delle strutture: dati societari, sede, recapiti e referenti.

I recapiti appartengono alla struttura e non vengono copiati nei fascicoli.
La rubrica non cambia assegnazioni né parametri delle presenze.
"""
import ipaddress
import re
from urllib.parse import urlsplit

from . import audit, centers, users
from .errors import Conflict, Invalid
from .permissions import require
from .util import dumps, loads, stamp
from . import validate as v

# chiave, etichetta, lunghezza massima, tipo, sezione
FIELDS = [
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
    ('website', 'Sito web', 500, 'url', 'Recapiti'),
    ('contact_name', 'Referente della struttura', 150, 'text', 'Referenti'),
    ('director', 'Direttore', 150, 'text', 'Referenti'),
    ('notes', 'Note organizzative', 2000, 'textarea', 'Note'),
]
KEYS = [f[0] for f in FIELDS]
HOST = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')


def definitions():
    return [dict(key=k, label=l, max_length=n, type=t, section=s) for k, l, n, t, s in FIELDS]


def record(con, center_id):
    center = centers.row(con, center_id)
    found = con.execute('SELECT * FROM structures WHERE center_id=?', (center_id,)).fetchone()
    values = {k: '' for k in KEYS}
    if found:
        values.update(loads(found['data']))
    return dict(center_id=center_id, name=center['name'], code=center['code'], active=bool(center['active']),
                version=found['version'] if found else 0, fields=values,
                updated_at=found['updated_at'] if found else '', updated_by=found['updated_by'] if found else '')


def is_website(value):
    if any(ch.isspace() for ch in value) or '\\' in value:
        return False
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            return False
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        try:
            ipaddress.ip_address(url.hostname)
            return True
        except ValueError:
            host = url.hostname.encode('idna').decode('ascii').rstrip('.')
            return len(host) <= 253 and all(HOST.fullmatch(p) for p in host.split('.'))
    except (ValueError, UnicodeError):
        return False


def validate_fields(raw):
    v.keys(raw, set(KEYS), 'Scheda struttura')
    out = {}
    for key, label, limit, kind, _ in FIELDS:
        value = v.text(raw.get(key, ''), label, limit, multiline=kind == 'textarea', field=key)
        if value and kind == 'email' and not v.is_email(value):
            raise Invalid(f'{label}: indirizzo email non valido.', field=key)
        if value and kind == 'url' and not is_website(value):
            raise Invalid('Sito web: indicare un indirizzo completo http:// o https:// senza credenziali.', field=key)
        out[key] = value
    return out


def listing(db, user):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'strutture.gestisci')
        return dict(structures=[record(con, c['id']) for c in centers.visible(con, user)], fields=definitions())


def read(db, user, center_id):
    with db.read() as con:
        centers.scoped(con, user, center_id, 'strutture.gestisci')
        return dict(structure=record(con, center_id), fields=definitions())


def save(db, actor, center_id, raw):
    v.keys(raw, {'fields', 'version'}, 'Scheda struttura', required={'fields', 'version'})
    values = validate_fields(raw['fields'])
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'strutture.gestisci')
        before = record(con, center_id)
        if v.version(raw['version']) != before['version']:
            raise Conflict('Scheda struttura aggiornata da un’altra sessione: riaprirla prima di salvare.')
        version = before['version'] + 1
        con.execute('''INSERT INTO structures(center_id,data,version,updated_at,updated_by) VALUES(?,?,?,?,?)
                       ON CONFLICT(center_id) DO UPDATE SET data=excluded.data, version=excluded.version,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (center_id, dumps(values), version, stamp(), actor.username))
        changed = [k for k in KEYS if before['fields'][k] != values[k]]
        audit.record(con, actor, 'Scheda struttura salvata', center_id, entity='structure', entity_id=center_id,
                     before={k: before['fields'][k] for k in changed}, after={k: values[k] for k in changed})
        return dict(structure=record(con, center_id))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/structures', cap='strutture.gestisci')
def api_list(ctx):
    return listing(ctx.db, ctx.user)


@route('GET', '/api/structures/<cid>', cap='strutture.gestisci')
def api_read(ctx):
    return read(ctx.db, ctx.user, ctx.params['cid'])


@route('PUT', '/api/structures/<cid>', cap='strutture.gestisci')
def api_save(ctx):
    return save(ctx.db, ctx.user, ctx.params['cid'], ctx.body)
