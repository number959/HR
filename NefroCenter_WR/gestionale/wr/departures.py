"""Uscite, trasferimenti e dotazioni (badge, chiavi, dispositivi).

Il percorso di uscita è una lista di controllo: chiuderlo non cambia da solo il
rapporto di lavoro, la sede o gli account esterni. Le consegne di dotazioni non
si riscrivono: per correggerle si registra prima la restituzione.
"""
from . import audit, centers, months, people, users
from .errors import Conflict, Invalid, NotFound
from .permissions import in_scope, require
from .util import dumps, loads, new_id, stamp, today_iso
from . import validate as v

KINDS = {'termination': 'Cessazione', 'transfer': 'Trasferimento'}
STATUSES = {'open': 'Aperto', 'in_progress': 'In corso', 'completed': 'Completato', 'cancelled': 'Annullato'}
ASSET_KINDS = {'badge': 'Badge', 'keys': 'Chiavi', 'device': 'Dispositivo', 'other': 'Altra dotazione'}
CONDITIONS = {'good': 'In buono stato', 'damaged': 'Danneggiata', 'unusable': 'Non utilizzabile'}
TASK_STATES = {'todo': 'Da fare', 'doing': 'In corso', 'done': 'Completata', 'na': 'Non applicabile'}
TASKS = [('badge', 'Restituzione badge'), ('keys', 'Restituzione chiavi'),
         ('devices', 'Restituzione dispositivi e altre dotazioni'), ('documents', 'Consegna e verifica dei documenti'),
         ('access', 'Conferma con IT della gestione degli accessi')]
ACTIVE = ('open', 'in_progress')
NOTICE = ('La chiusura del percorso non cambia automaticamente il rapporto, la sede o lo stato del dipendente e non '
          'disattiva account esterni: aggiornare fascicolo e accessi nelle rispettive procedure.')


def _history(con, actor, kind, item, action, before=None):
    con.execute('INSERT INTO process_history(kind,object_id,version,at,actor,action,data) VALUES(?,?,?,?,?,?,?)',
                (kind, item['id'], item['version'], stamp(), actor.username, action, dumps(item)))
    audit.record(con, actor, action, item['center_id'], entity=kind, entity_id=item['id'], before=before, after=item)


def _events(con, kind, object_id, limit=100):
    return [dict(version=r['version'], at=r['at'], actor=r['actor'], action=r['action']) for r in con.execute(
        'SELECT version,at,actor,action FROM process_history WHERE kind=? AND object_id=? ORDER BY id DESC LIMIT ?',
        (kind, object_id, limit))]


def case_dict(r):
    out = dict(r)
    out['tasks'] = loads(r['tasks'])
    out['kind_label'] = KINDS[r['kind']]
    out['status_label'] = STATUSES[r['status']]
    return out


def asset_dict(r):
    out = dict(r)
    out['kind_label'] = ASSET_KINDS[r['kind']]
    out['overdue'] = r['status'] == 'assigned' and bool(r['due_date']) and r['due_date'] < today_iso()
    return out


def _case(con, center_id, case_id):
    found = con.execute('SELECT * FROM departures WHERE id=? AND center_id=?', (v.identifier(case_id, 'Percorso'), center_id)).fetchone()
    if not found:
        raise NotFound('Percorso non trovato nella struttura.')
    return case_dict(found)


def _asset(con, center_id, asset_id):
    found = con.execute('SELECT * FROM equipment WHERE id=? AND center_id=?', (v.identifier(asset_id, 'Dotazione'), center_id)).fetchone()
    if not found:
        raise NotFound('Dotazione non trovata nella struttura.')
    return asset_dict(found)


def detail(con, item):
    out = dict(item)
    out['person'] = people.get(con, item['center_id'], item['person_id'])['name']
    out['outstanding'] = [asset_dict(r) for r in con.execute(
        "SELECT * FROM equipment WHERE center_id=? AND person_id=? AND status='assigned' ORDER BY delivery_date",
        (item['center_id'], item['person_id']))]
    out['blockers'] = [t['label'] for t in item['tasks'] if t['required'] and t['status'] not in ('done', 'na')]
    if out['outstanding']:
        out['blockers'].append(f'Dotazioni ancora da restituire: {len(out["outstanding"])}')
    out['can_complete'] = item['status'] in ACTIVE and not out['blockers']
    out['history'] = _events(con, 'departure', item['id'])
    out['notice'] = NOTICE
    if item['destination_center_id']:
        out['destination'] = centers.row(con, item['destination_center_id'])['name']
    return out


def overview(db, user, center_id='all'):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'uscite.gestisci')
        visible = centers.visible(con, user)
        if center_id != 'all':
            centers.scoped(con, user, center_id, 'uscite.gestisci')
            visible = [c for c in visible if c['id'] == center_id]
        persons, cases, assets = [], [], []
        for c in visible:
            names = {}
            for p in months.people(con, c['id']):
                names[p['id']] = p['name']
                persons.append(dict(center_id=c['id'], id=p['id'], name=p['name'], registration=p['registration'],
                                    active=p['active']))
            for r in con.execute('SELECT * FROM departures WHERE center_id=? ORDER BY created_at DESC', (c['id'],)):
                cases.append(dict(case_dict(r), person=names.get(r['person_id'], ''), center=c['name']))
            for r in con.execute('SELECT * FROM equipment WHERE center_id=? ORDER BY created_at DESC', (c['id'],)):
                assets.append(dict(asset_dict(r), person=names.get(r['person_id'], ''), center=c['name']))
    return dict(centers=[dict(id=c['id'], name=c['name'], code=c['code']) for c in visible], people=persons, cases=cases,
                assets=assets, kinds=KINDS, asset_kinds=ASSET_KINDS, conditions=CONDITIONS, task_states=TASK_STATES,
                notice=NOTICE, today=today_iso(),
                summary=dict(open=sum(c['status'] in ACTIVE for c in cases), assigned=sum(a['status'] == 'assigned' for a in assets),
                             overdue=sum(a['overdue'] for a in assets)))


def read_case(db, user, center_id, case_id):
    with db.read() as con:
        centers.scoped(con, user, center_id, 'uscite.gestisci')
        return detail(con, _case(con, center_id, case_id))


def save_case(db, actor, center_id, raw, case_id=None):
    v.keys(raw, {'person_id', 'kind', 'destination_center_id', 'reason', 'effective_date', 'responsible', 'version'},
           'Percorso di uscita', required={'person_id', 'kind', 'reason', 'effective_date', 'responsible', 'version'})
    kind = v.choice(raw['kind'], 'Tipo di percorso', KINDS, field='kind')
    reason = v.reason(raw['reason'])
    effective = v.day(raw['effective_date'], 'Data prevista', field='effective_date')
    responsible = v.text(raw['responsible'], 'Responsabile del percorso', 150, required=True, field='responsible')
    destination = raw.get('destination_center_id') or ''
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'uscite.gestisci')
        old = _case(con, center_id, case_id) if case_id else None
        if v.version(raw['version']) != (old['version'] if old else 0):
            raise Conflict('Percorso aggiornato da un’altra sessione: riaprirlo prima di salvare.')
        if old and old['status'] not in ACTIVE:
            raise Invalid('Il percorso è già chiuso: lo storico non si riscrive.')
        person = people.get(con, center_id, v.identifier(raw['person_id'], 'Persona'))
        if old and person['id'] != old['person_id']:
            raise Invalid('La persona del percorso non si può cambiare.', field='person_id')
        if kind == 'transfer':
            if not destination or destination == center_id:
                raise Invalid('Indicare una struttura di destinazione diversa.', field='destination_center_id')
            centers.scoped(con, actor, v.identifier(destination, 'Struttura di destinazione'), 'uscite.gestisci')
        elif destination:
            raise Invalid('Una cessazione non prevede una struttura di destinazione.', field='destination_center_id')
        if con.execute("SELECT 1 FROM departures WHERE person_id=? AND status IN ('open','in_progress') AND id<>?",
                       (person['id'], case_id or '')).fetchone():
            raise Invalid('Esiste già un percorso aperto per questa persona.')
        now = stamp()
        tasks = old['tasks'] if old else [dict(id=k, label=label, required=True, status='todo', owner=responsible, due=effective,
                                               note='', updated_at='', updated_by='') for k, label in TASKS]
        item = dict(id=case_id or new_id(), center_id=center_id, person_id=person['id'], kind=kind,
                    destination_center_id=destination, effective_date=effective, reason=reason, responsible=responsible,
                    status=old['status'] if old else 'open', tasks=tasks, closure_note='', version=(old['version'] if old else 0) + 1,
                    created_at=old['created_at'] if old else now, updated_at=now, closed_at='', closed_by='')
        _store(con, item)
        _history(con, actor, 'departure', item, 'Percorso di uscita aggiornato' if old else 'Percorso di uscita aperto', old)
        return detail(con, item)


def _store(con, item):
    con.execute('''INSERT INTO departures(id,center_id,person_id,kind,destination_center_id,effective_date,reason,responsible,status,
                   tasks,closure_note,version,created_at,updated_at,closed_at,closed_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, destination_center_id=excluded.destination_center_id,
                   effective_date=excluded.effective_date, reason=excluded.reason, responsible=excluded.responsible,
                   status=excluded.status, tasks=excluded.tasks, closure_note=excluded.closure_note, version=excluded.version,
                   updated_at=excluded.updated_at, closed_at=excluded.closed_at, closed_by=excluded.closed_by''',
                (item['id'], item['center_id'], item['person_id'], item['kind'], item['destination_center_id'],
                 item['effective_date'], item['reason'], item['responsible'], item['status'], dumps(item['tasks']),
                 item['closure_note'], item['version'], item['created_at'], item['updated_at'], item['closed_at'],
                 item['closed_by']))


def save_task(db, actor, center_id, case_id, task_id, raw):
    v.keys(raw, {'status', 'note', 'owner', 'due', 'version'}, 'Attività', required={'status', 'version'})
    status = v.choice(raw['status'], 'Stato', TASK_STATES, field='status')
    note = v.text(raw.get('note', ''), 'Nota', 1000, multiline=True, field='note')
    if status == 'na' and len(note) < 8:
        raise Invalid('Motivare la non applicabilità con almeno 8 caratteri.', field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'uscite.gestisci')
        old = _case(con, center_id, case_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Percorso aggiornato da un’altra sessione: ricaricare.')
        if old['status'] not in ACTIVE:
            raise Invalid('Il percorso è già chiuso.')
        item = dict(old, tasks=[dict(t) for t in old['tasks']])
        task = next((t for t in item['tasks'] if t['id'] == task_id), None)
        if not task:
            raise NotFound('Attività non trovata.')
        task.update(status=status, note=note,
                    owner=v.text(raw.get('owner', task['owner']), 'Referente', 150, required=True, field='owner'),
                    due=v.day(raw.get('due', task['due']), 'Scadenza', field='due'), updated_at=stamp(), updated_by=actor.username)
        item.update(status='in_progress', version=old['version'] + 1, updated_at=stamp())
        _store(con, item)
        _history(con, actor, 'departure', item, 'Attività di uscita aggiornata', old)
        return detail(con, item)


def transition(db, actor, center_id, case_id, raw):
    v.keys(raw, {'status', 'note', 'confirm', 'version'}, 'Chiusura', required={'status', 'note', 'version'})
    target = v.choice(raw['status'], 'Esito', ('completed', 'cancelled'), field='status')
    note = v.reason(raw['note'], 'Nota di chiusura', field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'uscite.gestisci')
        old = _case(con, center_id, case_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Percorso aggiornato da un’altra sessione: ricaricare.')
        if old['status'] not in ACTIVE:
            raise Invalid('Il percorso è già chiuso.')
        if target == 'completed':
            if raw.get('confirm') is not True:
                raise Invalid('Confermare la chiusura del percorso.', field='confirm')
            if detail(con, old)['blockers']:
                raise Invalid('Completare le attività obbligatorie e far restituire tutte le dotazioni prima della chiusura.')
        item = dict(old, status=target, version=old['version'] + 1, updated_at=stamp(), closed_at=stamp(),
                    closed_by=actor.username, closure_note=note)
        _store(con, item)
        _history(con, actor, 'departure', item, 'Percorso di uscita ' + ('completato' if target == 'completed' else 'annullato'), old)
        return detail(con, item)


def save_asset(db, actor, center_id, raw, asset_id=None):
    v.keys(raw, {'person_id', 'kind', 'inventory_code', 'label', 'delivery_date', 'due_date', 'note', 'version'}, 'Dotazione',
           required={'person_id', 'kind', 'inventory_code', 'label', 'delivery_date', 'version'})
    kind = v.choice(raw['kind'], 'Tipo di dotazione', ASSET_KINDS, field='kind')
    code = v.text(raw['inventory_code'], 'Codice inventario', 80, required=True, field='inventory_code')
    key = ' '.join(code.split()).casefold()
    label = v.text(raw['label'], 'Descrizione', 200, required=True, field='label')
    delivered = v.day(raw['delivery_date'], 'Data di consegna', field='delivery_date')
    due = v.day(raw.get('due_date', ''), 'Restituzione prevista', required=False, field='due_date')
    note = v.text(raw.get('note', ''), 'Nota', 1000, multiline=True, field='note')
    if delivered > today_iso():
        raise Invalid('La consegna non può essere registrata nel futuro.', field='delivery_date')
    if due and due < delivered:
        raise Invalid('La restituzione prevista non può precedere la consegna.', field='due_date')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'uscite.gestisci')
        person = people.get(con, center_id, v.identifier(raw['person_id'], 'Persona'))
        old = _asset(con, center_id, asset_id) if asset_id else None
        if v.version(raw['version']) != (old['version'] if old else 0):
            raise Conflict('Dotazione aggiornata da un’altra sessione: ricaricare.')
        if old:
            if old['status'] != 'assigned':
                raise Invalid('La dotazione è già restituita: lo storico non si modifica.')
            if (old['person_id'], old['kind'], old['inventory_code'], old['delivery_date']) != (person['id'], kind, code, delivered):
                raise Invalid('Persona, tipo, codice e data di consegna non si riscrivono: registrare prima la restituzione.')
        if con.execute("SELECT 1 FROM equipment WHERE center_id=? AND asset_key=? AND status='assigned' AND id<>?",
                       (center_id, key, asset_id or '')).fetchone():
            raise Invalid('Questa dotazione risulta già assegnata nella struttura.', field='inventory_code')
        now = stamp()
        aid = asset_id or new_id()
        version = (old['version'] if old else 0) + 1
        con.execute('''INSERT INTO equipment(id,center_id,person_id,kind,inventory_code,asset_key,label,delivery_date,due_date,note,
                       status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'assigned',?,?,?)
                       ON CONFLICT(id) DO UPDATE SET label=excluded.label, due_date=excluded.due_date, note=excluded.note,
                       version=excluded.version, updated_at=excluded.updated_at''',
                    (aid, center_id, person['id'], kind, code, key, label, delivered, due, note, version,
                     old['created_at'] if old else now, now))
        item = _asset(con, center_id, aid)
        _history(con, actor, 'equipment', item, 'Consegna di dotazione aggiornata' if old else 'Dotazione consegnata', old)
    return dict(asset=item)


def return_asset(db, actor, center_id, asset_id, raw):
    v.keys(raw, {'return_date', 'condition', 'note', 'version'}, 'Restituzione', required={'return_date', 'condition', 'version'})
    day = v.day(raw['return_date'], 'Data di restituzione', field='return_date')
    condition = v.choice(raw['condition'], 'Condizioni', CONDITIONS, field='condition')
    note = v.text(raw.get('note', ''), 'Nota', 1000, multiline=True, field='note')
    if condition != 'good' and len(note) < 8:
        raise Invalid('Descrivere danni o problemi con almeno 8 caratteri.', field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'uscite.gestisci')
        old = _asset(con, center_id, asset_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Dotazione aggiornata da un’altra sessione: ricaricare.')
        if old['status'] != 'assigned':
            raise Invalid('Questa dotazione è già stata restituita.')
        if day < old['delivery_date'] or day > today_iso():
            raise Invalid('La restituzione deve essere fra la consegna e oggi.', field='return_date')
        con.execute('''UPDATE equipment SET status='returned', return_date=?, return_condition=?, return_note=?, returned_by=?,
                       version=version+1, updated_at=? WHERE id=?''', (day, condition, note, actor.username, stamp(), old['id']))
        item = _asset(con, center_id, old['id'])
        _history(con, actor, 'equipment', item, 'Dotazione restituita', old)
    return dict(asset=item)


def asset_history(db, user, center_id, asset_id):
    with db.read() as con:
        centers.scoped(con, user, center_id, 'uscite.gestisci')
        item = _asset(con, center_id, asset_id)
        return dict(asset=item, history=_events(con, 'equipment', item['id'], 50))


def visible_open_cases(con, user):
    """Percorsi aperti nelle strutture visibili (per la lista «Da completare»)."""
    return [case_dict(r) for r in con.execute("SELECT * FROM departures WHERE status IN ('open','in_progress')")
            if in_scope(user, r['center_id'])]


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/departures', cap='uscite.gestisci')
def api_overview(ctx):
    return overview(ctx.db, ctx.user, ctx.q('cid', 'all') or 'all')


@route('POST', '/api/departures/<cid>', cap='uscite.gestisci')
def api_create(ctx):
    return save_case(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/departures/<cid>/<case_id>', cap='uscite.gestisci')
def api_read(ctx):
    return read_case(ctx.db, ctx.user, ctx.params['cid'], ctx.params['case_id'])


@route('PUT', '/api/departures/<cid>/<case_id>', cap='uscite.gestisci')
def api_update(ctx):
    return save_case(ctx.db, ctx.user, ctx.params['cid'], ctx.body, ctx.params['case_id'])


@route('PUT', '/api/departures/<cid>/<case_id>/tasks/<task_id>', cap='uscite.gestisci')
def api_task(ctx):
    return save_task(ctx.db, ctx.user, ctx.params['cid'], ctx.params['case_id'], ctx.params['task_id'], ctx.body)


@route('POST', '/api/departures/<cid>/<case_id>/close', cap='uscite.gestisci')
def api_close(ctx):
    return transition(ctx.db, ctx.user, ctx.params['cid'], ctx.params['case_id'], ctx.body)


@route('POST', '/api/equipment/<cid>', cap='uscite.gestisci')
def api_asset_create(ctx):
    return save_asset(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('PUT', '/api/equipment/<cid>/<asset_id>', cap='uscite.gestisci')
def api_asset_update(ctx):
    return save_asset(ctx.db, ctx.user, ctx.params['cid'], ctx.body, ctx.params['asset_id'])


@route('GET', '/api/equipment/<cid>/<asset_id>', cap='uscite.gestisci')
def api_asset_history(ctx):
    return asset_history(ctx.db, ctx.user, ctx.params['cid'], ctx.params['asset_id'])


@route('POST', '/api/equipment/<cid>/<asset_id>/return', cap='uscite.gestisci')
def api_asset_return(ctx):
    return return_asset(ctx.db, ctx.user, ctx.params['cid'], ctx.params['asset_id'], ctx.body)
