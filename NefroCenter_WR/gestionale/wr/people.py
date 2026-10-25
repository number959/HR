"""Persone del registro di una struttura.

Ogni persona appartiene a una struttura ed è collegata a un'identità di gruppo:
la stessa persona in due strutture ha due schede e un'unica identità (vedi workforce).
Note interne e accordo economico personale sono visibili solo all'area HR.
"""
from . import approvals, audit, centers, months
from .errors import Conflict, Invalid, NotFound
from .permissions import has
from .util import dumps, new_id, stamp
from . import validate as v

PAY_KEYS = ('weekday_rate', 'holiday_rate', 'fixed_deduction', 'ccnl_rate', 'pay_mode')


def public(person, user):
    """Scheda visibile all'utente: note e accordo personale solo per l'area HR."""
    out = dict(person)
    if not has(user, 'accordi.vedi'):
        out.pop('note', None)
        out.pop('pay_override', None)
    return out


def get(con, center_id, person_id):
    found = con.execute('SELECT * FROM people WHERE id=? AND center_id=?', (person_id, center_id)).fetchone()
    if not found:
        raise NotFound('Persona non trovata nella struttura.')
    return months.person_dict(found)


def validate_pay(raw):
    if raw is None:
        return None
    v.keys(raw, set(PAY_KEYS), 'Accordo personale', required=set(PAY_KEYS))
    out = {k: v.number(raw[k], label, 0, 100000, field='pay_override')
           for k, label in (('weekday_rate', 'Tariffa feriale'), ('holiday_rate', 'Tariffa festiva'),
                            ('fixed_deduction', 'Detrazione fissa'), ('ccnl_rate', 'Valore festivo CCNL'))}
    out['pay_mode'] = v.choice(raw['pay_mode'], 'Base dell’accordo', ('surplus', 'all'), field='pay_override')
    return out


def clean(raw, cfg, *, partial=False):
    allowed = {'name', 'role', 'registration', 'active', 'note', 'contract', 'pay_override', 'version'}
    v.keys(raw, allowed, 'Persona')
    out = {}
    if not partial or 'name' in raw:
        out['name'] = v.text(raw.get('name'), 'Nome e cognome', 150, required=True, field='name')
    if not partial or 'role' in raw:
        out['role'] = v.choice(raw.get('role'), 'Ruolo', cfg['roles'], field='role')
    if 'registration' in raw or not partial:
        out['registration'] = v.text(raw.get('registration', ''), 'Matricola', 80, field='registration')
    if 'active' in raw or not partial:
        out['active'] = v.boolean(raw.get('active', True), 'Persona attiva', field='active')
    if 'note' in raw or not partial:
        out['note'] = v.text(raw.get('note', ''), 'Note', 2000, multiline=True, field='note')
    if 'contract' in raw or not partial:
        out['contract'] = v.text(raw.get('contract', ''), 'Contratto', 150, field='contract')
    if 'pay_override' in raw or not partial:
        out['pay_override'] = validate_pay(raw.get('pay_override'))
    return out


def unique_registration(con, center_id, registration, person_id):
    if registration and con.execute('SELECT 1 FROM people WHERE center_id=? AND registration=? AND id<>?',
                                    (center_id, registration, person_id or '')).fetchone():
        raise Invalid('Matricola già presente in questa struttura.', field='registration')


def insert(con, actor, center_id, data, identity_id=None):
    """Crea la scheda (e una nuova identità di gruppo se non indicata). Restituisce l'id."""
    pid = new_id(); now = stamp()
    if identity_id is None:
        identity_id = new_id()
        con.execute('INSERT INTO identities(id,version) VALUES(?,1)', (identity_id,))
    con.execute('''INSERT INTO people(id,center_id,identity_id,name,role,registration,active,note,contract,pay_override,
                   version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)''',
                (pid, center_id, identity_id, data['name'], data['role'], data.get('registration', ''),
                 int(data.get('active', True)), data.get('note', ''), data.get('contract', ''),
                 dumps(data['pay_override']) if data.get('pay_override') else '', now, now))
    return pid


def write(con, person_id, data):
    sets, values = [], []
    for key, value in data.items():
        if key == 'pay_override':
            value = dumps(value) if value else ''
        elif key == 'active':
            value = int(value)
        sets.append(f'{key}=?'); values.append(value)
    con.execute(f'UPDATE people SET {", ".join(sets)}, version=version+1, updated_at=? WHERE id=?',
                (*values, stamp(), person_id))


def create(db, actor, center_id, raw):
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'presenze.anagrafica')
        approvals.guard_reference_change(con, center_id)
        data = clean(raw, centers.config(con, center_id))
        unique_registration(con, center_id, data['registration'], None)
        pid = insert(con, actor, center_id, data)
        audit.record(con, actor, 'Persona aggiunta al registro', center_id, entity='person', entity_id=pid,
                     after={k: data[k] for k in ('name', 'role', 'registration', 'active')})
    return dict(id=pid)


def update(db, actor, center_id, person_id, raw):
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'presenze.anagrafica')
        approvals.guard_reference_change(con, center_id)
        before = get(con, center_id, person_id)
        if v.version(raw.get('version')) != before['version']:
            raise Conflict('Scheda modificata da un’altra sessione: ricaricare.')
        data = clean(raw, centers.config(con, center_id), partial=True)
        if 'registration' in data:
            unique_registration(con, center_id, data['registration'], person_id)
        write(con, person_id, data)
        audit.record(con, actor, 'Persona aggiornata', center_id, entity='person', entity_id=person_id,
                     before={k: before[k] for k in data}, after=data)
    return dict(ok=True)


def listing(db, user, center_id):
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'presenze.vedi')
        cfg = centers.config(con, center_id)
        return dict(center=dict(id=center['id'], name=center['name']), roles=cfg['roles'],
                    people=[public(p, user) for p in months.people(con, center_id)],
                    can_edit=has(user, 'presenze.anagrafica'))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/centers/<cid>/people')
def api_list(ctx):
    return listing(ctx.db, ctx.user, ctx.params['cid'])


@route('POST', '/api/centers/<cid>/people', cap='presenze.anagrafica')
def api_create(ctx):
    return create(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('PUT', '/api/centers/<cid>/people/<pid>', cap='presenze.anagrafica')
def api_update(ctx):
    return update(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.body)
