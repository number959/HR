"""Account e assegnazioni: caricamento dell'utente e gestione da parte dell'amministratore."""
import re

from . import audit, security
from .errors import Conflict, Forbidden, Invalid, NotFound, Unauthorized
from .permissions import ROLES, User, require
from .util import new_id, stamp
from . import validate as v

USERNAME = re.compile(r'[a-z0-9_.-]{3,60}')


def load(con, user_id):
    """Utente attivo con ruolo e strutture correnti. Usato a ogni richiesta e nelle
    transazioni di scrittura, così una revoca ha effetto immediato."""
    row = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not row or not row['active']:
        raise Unauthorized('Account non disponibile. Accedere di nuovo.')
    centers = frozenset(r[0] for r in con.execute('SELECT center_id FROM user_centers WHERE user_id=?', (user_id,)))
    return User(id=row['id'], username=row['username'], name=row['name'], role=row['role'], centers=centers, active=True)


def reload(con, user):
    return load(con, user.id)


def normalize_username(value):
    value = str(value or '').strip().casefold()
    if not USERNAME.fullmatch(value):
        raise Invalid('Nome utente: da 3 a 60 caratteri tra lettere minuscole, numeri, punto, trattino e trattino basso.',
                      field='username')
    return value


def listing(db, actor):
    with db.read() as con:
        actor = reload(con, actor)
        require(actor, 'utenti.gestisci')
        rows = []
        for r in con.execute('''SELECT u.*, s.totp_enabled, s.activation_until, s.last_login FROM users u
                                LEFT JOIN user_security s ON s.user_id=u.id ORDER BY u.name COLLATE NOCASE'''):
            centers = [c[0] for c in con.execute('SELECT center_id FROM user_centers WHERE user_id=?', (r['id'],))]
            rows.append(dict(id=r['id'], username=r['username'], name=r['name'], role=r['role'],
                             role_label=ROLES[r['role']]['label'], active=bool(r['active']), centers=centers,
                             two_factor=bool(r['totp_enabled']), activation_pending=bool(r['activation_until']),
                             last_login=r['last_login'] or '', version=r['version']))
        return dict(users=rows, roles=[dict(id=k, label=v_['label'], scope=v_['scope']) for k, v_ in ROLES.items()])


def _clean(con, raw, *, creating):
    v.keys(raw, {'username', 'name', 'role', 'centers', 'active', 'version'}, 'Account')
    data = dict(name=v.text(raw.get('name'), 'Nome e cognome', 150, required=True, field='name'),
                role=v.choice(raw.get('role'), 'Ruolo', ROLES, field='role'),
                active=v.boolean(raw.get('active', True), 'Account attivo', field='active'))
    if creating:
        data['username'] = normalize_username(raw.get('username'))
    centers = v.str_list(raw.get('centers', []), 'Strutture assegnate', maximum=500, item_max=64, field='centers')
    known = {r[0] for r in con.execute('SELECT id FROM centers')}
    if set(centers) - known:
        raise Invalid('Strutture assegnate non valide.', field='centers')
    if ROLES[data['role']]['scope'] == 'all':
        centers = []
    elif not centers:
        raise Invalid('Assegnare almeno una struttura a questo ruolo.', field='centers')
    data['centers'] = centers
    return data


def _keep_one_admin(con, user_id, role, active):
    row = con.execute('SELECT role, active FROM users WHERE id=?', (user_id,)).fetchone()
    if row and row['role'] == 'admin' and row['active'] and (role != 'admin' or not active):
        others = con.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (user_id,)).fetchone()[0]
        if not others:
            raise Invalid('Deve restare almeno un amministratore attivo.')


def create(db, auth, actor, raw):
    """Crea l'account e restituisce il codice di attivazione (mostrato una sola volta).
    La password personale viene scelta dall'utente al primo accesso."""
    with db.write() as con:
        actor = reload(con, actor)
        require(actor, 'utenti.gestisci')
        data = _clean(con, raw, creating=True)
        if con.execute('SELECT 1 FROM users WHERE username=?', (data['username'],)).fetchone():
            raise Invalid('Nome utente già utilizzato.', field='username')
        uid = new_id(); now = stamp()
        # Password casuale non comunicata: l'accesso avviene solo con il codice di attivazione.
        placeholder = security.hash_password(security.new_totp_secret() + 'Aa1!')
        con.execute('INSERT INTO users(id,username,name,role,active,password,version,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)',
                    (uid, data['username'], data['name'], data['role'], int(data['active']), placeholder, now, now))
        con.executemany('INSERT INTO user_centers VALUES(?,?)', [(uid, c) for c in data['centers']])
        code = auth.issue_activation(con, uid, actor, 'Creazione account')
        audit.record(con, actor, 'Account creato', entity='user', entity_id=uid,
                     after={k: data[k] for k in ('username', 'name', 'role', 'centers', 'active')})
    return dict(id=uid, activation_code=code, activation_days=auth.ACTIVATION_DAYS)


def update(db, auth, actor, user_id, raw):
    with db.write() as con:
        actor = reload(con, actor)
        require(actor, 'utenti.gestisci')
        row = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise NotFound('Account non trovato.')
        if v.version(raw.get('version')) != row['version']:
            raise Conflict('Account modificato da un’altra sessione: ricaricare.')
        data = _clean(con, raw, creating=False)
        _keep_one_admin(con, user_id, data['role'], data['active'])
        before = dict(name=row['name'], role=row['role'], active=bool(row['active']),
                      centers=sorted(c[0] for c in con.execute('SELECT center_id FROM user_centers WHERE user_id=?', (user_id,))))
        con.execute('UPDATE users SET name=?,role=?,active=?,version=version+1,updated_at=? WHERE id=?',
                    (data['name'], data['role'], int(data['active']), stamp(), user_id))
        con.execute('DELETE FROM user_centers WHERE user_id=?', (user_id,))
        con.executemany('INSERT INTO user_centers VALUES(?,?)', [(user_id, c) for c in data['centers']])
        after = dict(name=data['name'], role=data['role'], active=data['active'], centers=sorted(data['centers']))
        if (before['role'], before['active'], before['centers']) != (after['role'], after['active'], after['centers']):
            # Ruolo, stato o strutture cambiati: le sessioni aperte vanno rinnovate.
            auth.revoke_sessions(con, user_id)
        audit.record(con, actor, 'Account aggiornato', entity='user', entity_id=user_id, before=before, after=after)
    return dict(ok=True)


def reset_access(db, auth, actor, user_id, reason):
    """Nuovo codice di attivazione: azzera secondo fattore e sessioni dell'account."""
    reason = v.reason(reason)
    with db.write() as con:
        actor = reload(con, actor)
        require(actor, 'utenti.gestisci')
        if user_id == actor.id:
            raise Forbidden('Per il tuo account usa la pagina Sicurezza (cambio dispositivo).')
        if not con.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
            raise NotFound('Account non trovato.')
        code = auth.issue_activation(con, user_id, actor, reason)
        audit.record(con, actor, 'Accesso ripristinato', entity='user', entity_id=user_id, after={'reason': reason})
    return dict(activation_code=code, activation_days=auth.ACTIVATION_DAYS)


def create_first_admin(db, auth, username, name):
    """Solo da console, su un archivio senza account. Restituisce il codice di attivazione."""
    username = normalize_username(username)
    name = v.text(name, 'Nome del referente', 150, required=True)
    with db.write() as con:
        if con.execute('SELECT 1 FROM users').fetchone():
            raise Forbidden('Archivio già configurato: esiste almeno un account.')
        uid = new_id(); now = stamp()
        placeholder = security.hash_password(security.new_totp_secret() + 'Aa1!')
        con.execute('INSERT INTO users(id,username,name,role,active,password,version,created_at,updated_at) VALUES(?,?,?,?,1,?,1,?,?)',
                    (uid, username, name, 'admin', placeholder, now, now))
        system = User(id='', username='console', name='Console', role='admin')
        code = auth.issue_activation(con, uid, system, 'Primo amministratore')
        audit.record(con, system, 'Primo amministratore creato', entity='user', entity_id=uid, after={'username': username})
    return code


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/users', cap='utenti.gestisci')
def api_list(ctx):
    return listing(ctx.db, ctx.user)


@route('POST', '/api/users', cap='utenti.gestisci', step_up=True)
def api_create(ctx):
    return create(ctx.db, ctx.app.auth, ctx.user, ctx.body)


@route('PUT', '/api/users/<user_id>', cap='utenti.gestisci', step_up=True)
def api_update(ctx):
    return update(ctx.db, ctx.app.auth, ctx.user, ctx.params['user_id'], ctx.body)


@route('POST', '/api/users/<user_id>/activation', cap='utenti.gestisci', step_up=True)
def api_reset(ctx):
    return reset_access(ctx.db, ctx.app.auth, ctx.user, ctx.params['user_id'], ctx.body.get('reason'))
