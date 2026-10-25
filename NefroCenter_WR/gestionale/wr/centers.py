"""Strutture del gruppo e parametri versionati delle presenze."""
import re

from . import audit, rules, users
from .errors import Conflict, Invalid, NotFound
from .permissions import has, in_scope, require, require_center
from .util import dumps, loads, new_id, stamp
from . import validate as v

CODE = re.compile(r'[A-Z0-9_-]{2,30}')


def row(con, center_id):
    found = con.execute('SELECT * FROM centers WHERE id=?', (center_id,)).fetchone()
    if not found:
        raise NotFound('Struttura non trovata.')
    return dict(found)


def config(con, center_id, version=None):
    """Parametri della versione indicata (o della corrente)."""
    if version is None:
        version = row(con, center_id)['config_version']
    found = con.execute('SELECT data FROM center_configs WHERE center_id=? AND version=?', (center_id, version)).fetchone()
    if not found:
        raise NotFound('Versione dei parametri non trovata.')
    return loads(found[0])


def scoped(con, user, center_id, cap=None, *, current_config=None):
    """Ricarica l'utente nella transazione, verifica ambito e permesso. Restituisce (utente, struttura)."""
    user = users.reload(con, user)
    center = row(con, center_id)
    require_center(user, center_id)
    if cap:
        require(user, cap, current_config)
    return user, center


def visible(con, user):
    out = []
    for r in con.execute('SELECT * FROM centers ORDER BY name COLLATE NOCASE'):
        if in_scope(user, r['id']) and (r['active'] or user.role == 'admin'):
            out.append(dict(id=r['id'], name=r['name'], code=r['code'], active=bool(r['active']),
                            config_version=r['config_version'], version=r['version']))
    return out


def _insert_config(con, center_id, version, data, note, actor):
    con.execute('INSERT INTO center_configs(center_id,version,data,note,created_at,created_by) VALUES(?,?,?,?,?,?)',
                (center_id, version, dumps(data), note, stamp(), actor.username))


def create(db, actor, raw):
    v.keys(raw, {'name', 'code', 'copy_from'}, 'Struttura')
    name = v.text(raw.get('name'), 'Nome della struttura', 150, required=True, field='name')
    code = str(raw.get('code') or '').strip().upper()
    if not CODE.fullmatch(code):
        raise Invalid('Codice struttura: da 2 a 30 lettere maiuscole, numeri, trattino o trattino basso.', field='code')
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'centri.crea')
        if con.execute('SELECT 1 FROM centers WHERE code=?', (code,)).fetchone():
            raise Invalid('Codice struttura già utilizzato.', field='code')
        source = raw.get('copy_from') or ''
        data = config(con, v.identifier(source, 'Struttura da copiare')) if source else rules.defaults()
        cid = new_id()
        con.execute('INSERT INTO centers(id,name,code,active,config_version,version,created_at) VALUES(?,?,?,1,1,1,?)',
                    (cid, name, code, stamp()))
        _insert_config(con, cid, 1, data, 'Copiati da un’altra struttura' if source else 'Parametri iniziali', actor)
        audit.record(con, actor, 'Struttura creata', cid, entity='center', entity_id=cid,
                     after=dict(name=name, code=code, copy_from=source))
    return dict(id=cid)


def update(db, actor, center_id, raw):
    v.keys(raw, {'name', 'active', 'version'}, 'Struttura', required={'version'})
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'centri.crea')
        current = row(con, center_id)
        if v.version(raw['version']) != current['version']:
            raise Conflict('Struttura modificata da un’altra sessione: ricaricare.')
        name = v.text(raw.get('name', current['name']), 'Nome della struttura', 150, required=True, field='name')
        active = v.boolean(raw.get('active', bool(current['active'])), 'Struttura attiva', field='active')
        con.execute('UPDATE centers SET name=?, active=?, version=version+1 WHERE id=?', (name, int(active), center_id))
        audit.record(con, actor, 'Struttura aggiornata', center_id, entity='center', entity_id=center_id,
                     before=dict(name=current['name'], active=bool(current['active'])), after=dict(name=name, active=active))
    return dict(ok=True)


def read_config(db, user, center_id):
    with db.read() as con:
        user, center = scoped(con, user, center_id, 'presenze.vedi')
        data = config(con, center_id)
        versions = [dict(version=r['version'], note=r['note'], created_at=r['created_at'], created_by=r['created_by'])
                    for r in con.execute('SELECT version,note,created_at,created_by FROM center_configs WHERE center_id=? '
                                         'ORDER BY version DESC LIMIT 50', (center_id,))]
    return dict(center=dict(id=center['id'], name=center['name'], code=center['code']), version=center['config_version'],
                config=data, versions=versions, parameters=parameters_reference(),
                can_edit=has(user, 'centri.parametri'))


def save_config(db, actor, center_id, raw):
    from . import approvals
    v.keys(raw, {'config', 'version', 'note'}, 'Parametri', required={'config', 'version'})
    data = rules.validate_config(raw['config'])
    note = v.text(raw.get('note', ''), 'Motivo della modifica', 500, field='note')
    with db.write() as con:
        actor, center = scoped(con, actor, center_id, 'centri.parametri')
        if v.version(raw['version']) != center['config_version']:
            raise Conflict('Parametri modificati da un’altra sessione: ricaricare prima di salvare.')
        approvals.guard_reference_change(con, center_id)
        before = config(con, center_id)
        version = center['config_version'] + 1
        _insert_config(con, center_id, version, data, note or 'Parametri aggiornati', actor)
        con.execute('UPDATE centers SET config_version=? WHERE id=?', (version, center_id))
        audit.record(con, actor, 'Parametri della struttura aggiornati', center_id, entity='config', entity_id=str(version),
                     before=_changed(before, data, 'before'), after=_changed(before, data, 'after'))
    return dict(version=version)


def _changed(before, after, side):
    """Solo le voci cambiate, per un registro attività leggibile."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    source = before if side == 'before' else after
    return {k: source.get(k) for k in keys}


def parameters_reference():
    """Descrizione dei parametri per l'interfaccia e il riferimento impostazioni."""
    out = []
    for key, spec in rules.PARAMETERS.items():
        item = dict(id=key, label=spec[0], type=spec[1])
        if spec[1] == 'number':
            item.update(minimum=spec[2], maximum=spec[3])
        elif spec[1] == 'choice':
            item.update(options=list(spec[2]))
        out.append(item)
    return out


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/centers')
def api_list(ctx):
    with ctx.db.read() as con:
        return dict(centers=visible(con, users.reload(con, ctx.user)))


@route('POST', '/api/centers', cap='centri.crea', step_up=True)
def api_create(ctx):
    return create(ctx.db, ctx.user, ctx.body)


@route('PUT', '/api/centers/<cid>', cap='centri.crea')
def api_update(ctx):
    return update(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/centers/<cid>/config')
def api_config(ctx):
    return read_config(ctx.db, ctx.user, ctx.params['cid'])


@route('PUT', '/api/centers/<cid>/config', cap='centri.parametri')
def api_save_config(ctx):
    return save_config(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/holidays/<year>')
def api_holidays(ctx):
    year = ctx.params['year']
    if not year.isdigit() or not 1900 <= int(year) <= 2200:
        raise Invalid('Anno non valido.')
    return dict(year=int(year), holidays=[dict(day=d, name=n) for d, n in rules.italian_holidays(int(year))],
                note='Festività nazionali. Aggiungere il santo patrono della struttura.')
