"""Personale di gruppo: identità condivise fra strutture e decorrenze di contratto ed economia.

Ogni scheda di struttura resta separata (registro, fascicolo, allegati). L'identità
collega le schede della stessa persona; i collegamenti si fanno solo a mano, con
motivazione, mai per somiglianza di nome o codice fiscale. Gli intervalli di
validità sono inclusivi e non si sovrappongono. Nessuna modifica è retroattiva
sui mesi: un accordo mensile cambia solo con «Applica al mese».
"""
from . import agreements, approvals, audit, centers, months, people, users
from .errors import Conflict, Forbidden, Invalid, NotFound
from .permissions import in_scope, require
from .util import dumps, loads, month_days, new_id, stamp, today_iso
from . import validate as v

CONTRACT_TEXT = (('contract_type', 'Tipo di contratto', 150), ('ccnl', 'CCNL', 150), ('level', 'Livello', 150),
                 ('note', 'Note', 2000))
TABLES = {'contract': 'contracts', 'economic': 'economics'}
KIND_LABELS = {'contract': 'contratto', 'economic': 'condizioni economiche', 'link': 'collegamento',
               'apply': 'applicazione al mese'}


def validate_contract(raw, cfg):
    v.keys(raw, {'role', 'contract_type', 'ccnl', 'level', 'weekly_hours', 'part_time_percent', 'note'}, 'Contratto',
           required={'role', 'weekly_hours', 'part_time_percent'})
    out = dict(role=v.choice(raw['role'], 'Ruolo', cfg['roles'], field='role'))
    for key, label, limit in CONTRACT_TEXT:
        out[key] = v.text(raw.get(key, ''), label, limit, multiline=key == 'note', field=key)
    out['weekly_hours'] = v.number(raw['weekly_hours'], 'Ore settimanali', 0, 168, field='weekly_hours')
    out['part_time_percent'] = v.number(raw['part_time_percent'], 'Percentuale di part-time', 0, 100, field='part_time_percent')
    if not out['weekly_hours'] or not out['part_time_percent']:
        raise Invalid('Ore settimanali e percentuale devono essere maggiori di zero.', field='weekly_hours')
    return out


def records(con, kind, person_id):
    return [dict(id=r['id'], valid_from=r['valid_from'], valid_to=r['valid_to'], data=loads(r['data']), version=r['version'],
                 updated_at=r['updated_at'], updated_by=r['updated_by'])
            for r in con.execute(f'SELECT * FROM {TABLES[kind]} WHERE person_id=? ORDER BY valid_from DESC', (person_id,))]


def contract_on(con, person_id, day):
    r = con.execute("SELECT * FROM contracts WHERE person_id=? AND valid_from<=? AND (valid_to='' OR valid_to>=?)",
                    (person_id, day, day)).fetchone()
    return dict(id=r['id'], valid_from=r['valid_from'], valid_to=r['valid_to'], version=r['version'], **loads(r['data'])) if r else None


def _members(con, identity_id):
    return [dict(r) for r in con.execute('''SELECT p.id, p.center_id, c.name AS center_name FROM people p
                                            JOIN centers c ON c.id=p.center_id WHERE p.identity_id=?''', (identity_id,))]


def _history(con, actor, person, kind, record_id, reason, before, after):
    con.execute('INSERT INTO workforce_history(person_id,kind,record_id,at,actor,reason,before,after) VALUES(?,?,?,?,?,?,?,?)',
                (person['id'], kind, record_id, stamp(), actor.username, reason,
                 None if before is None else dumps(before), None if after is None else dumps(after)))
    audit.record(con, actor, 'Personale di gruppo: ' + KIND_LABELS[kind], person['center_id'], entity='person',
                 entity_id=person['id'], before=before, after=dict(reason=reason, record=after))


def overview(db, user, on=None):
    on = v.day(on or today_iso(), 'Data di riferimento', field='on')
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'gruppo.gestisci')
        groups = {}
        rows = con.execute('''SELECT p.*, c.name AS center_name, c.code AS center_code, i.version AS identity_version
                              FROM people p JOIN centers c ON c.id=p.center_id JOIN identities i ON i.id=p.identity_id
                              ORDER BY p.name COLLATE NOCASE, c.name''')
        for r in rows:
            if not in_scope(user, r['center_id']):
                continue
            group = groups.setdefault(r['identity_id'], dict(identity_id=r['identity_id'], version=r['identity_version'],
                                                             name=r['name'], assignments=[]))
            contract = contract_on(con, r['id'], on)
            group['assignments'].append(dict(person_id=r['id'], center_id=r['center_id'], center=r['center_name'],
                                             center_code=r['center_code'], name=r['name'], role=r['role'],
                                             registration=r['registration'], active=bool(r['active']),
                                             version=r['version'], contract=contract))
        out = list(groups.values())
        for g in out:
            g['linked'] = len(g['assignments']) > 1
            g['missing_contract'] = sum(a['contract'] is None for a in g['assignments'] if a['active'])
    return dict(on=on, groups=out, scope='Tutte le strutture' if user.sees_all else 'Strutture assegnate')


def detail(db, user, identity_id, on=None):
    from . import hr
    on = v.day(on or today_iso(), 'Data di riferimento', field='on')
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'gruppo.gestisci')
        found = con.execute('SELECT * FROM identities WHERE id=?', (v.identifier(identity_id, 'Identità'),)).fetchone()
        members = [m for m in _members(con, identity_id) if in_scope(user, m['center_id'])] if found else []
        if not members:
            raise NotFound('Persona non disponibile nelle strutture autorizzate.')
        assignments = []
        for m in members:
            person = people.get(con, m['center_id'], m['id'])
            cfg = centers.config(con, m['center_id'])
            assignments.append(dict(
                center_id=m['center_id'], center=m['center_name'], person=people.public(person, user),
                contract=contract_on(con, person['id'], on), contracts=records(con, 'contract', person['id']),
                economics=records(con, 'economic', person['id']), documents=hr.documents_meta(con, person['id']),
                roles=cfg['roles'], economic_proposal=agreements.proposal(cfg, person),
                absence_codes=[dict(id=c['id'], label=c['label']) for c in cfg['codes'] if c['kind'] != 'work'],
                history=[dict(kind=r['kind'], label=KIND_LABELS.get(r['kind'], r['kind']), at=r['at'], actor=r['actor'],
                              reason=r['reason'], before=loads(r['before']), after=loads(r['after']))
                         for r in con.execute('SELECT * FROM workforce_history WHERE person_id=? ORDER BY id DESC LIMIT 100',
                                              (person['id'],))]))
        hidden = len(_members(con, identity_id)) - len(members)
    return dict(identity_id=identity_id, version=found['version'], on=on, assignments=assignments, hidden_assignments=hidden)


def _person(con, actor, center_id, person_id):
    actor, _ = centers.scoped(con, actor, center_id, 'gruppo.gestisci')
    return actor, people.get(con, center_id, v.identifier(person_id, 'Persona'))


def link(db, actor, center_id, person_id, raw):
    v.keys(raw, {'identity_id', 'identity_version', 'version', 'reason'}, 'Collegamento', required={'version', 'reason'})
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, person = _person(con, actor, center_id, person_id)
        if v.version(raw['version']) != person['version']:
            raise Conflict('Scheda modificata da un’altra sessione: ricaricare.')
        if any(not in_scope(actor, m['center_id']) for m in _members(con, person['identity_id'])):
            raise Forbidden('Il collegamento coinvolge strutture non autorizzate: rivolgersi a HR centrale.')
        target = raw.get('identity_id') or ''
        if target:
            target = v.identifier(target, 'Identità di destinazione')
            if target == person['identity_id']:
                raise Invalid('La scheda è già collegata a questa persona.')
            found = con.execute('SELECT version FROM identities WHERE id=?', (target,)).fetchone()
            members = _members(con, target)
            if not found or not members or any(not in_scope(actor, m['center_id']) for m in members):
                raise Forbidden('Persona di destinazione non disponibile nelle strutture autorizzate.')
            if v.version(raw.get('identity_version')) != found['version']:
                raise Conflict('Persona di destinazione modificata da un’altra sessione: ricaricare.')
            if any(m['center_id'] == center_id for m in members):
                raise Invalid('Questa persona ha già una scheda in questa struttura.')
        else:
            if len(_members(con, person['identity_id'])) == 1:
                raise Invalid('La scheda non è collegata ad altre strutture.')
            target = new_id()
            con.execute('INSERT INTO identities(id,version) VALUES(?,0)', (target,))
        con.execute('UPDATE people SET identity_id=?, version=version+1, updated_at=? WHERE id=?', (target, stamp(), person['id']))
        con.execute('UPDATE identities SET version=version+1 WHERE id IN (?,?)', (target, person['identity_id']))
        _history(con, actor, person, 'link', target, reason, dict(identity_id=person['identity_id']), dict(identity_id=target))
    return dict(identity_id=target)


def save_interval(db, actor, center_id, person_id, kind, raw):
    v.keys(raw, {'id', 'version', 'valid_from', 'valid_to', 'data', 'reason'}, 'Decorrenza',
           required={'version', 'valid_from', 'data', 'reason'})
    start = v.day(raw['valid_from'], 'Decorrenza', field='valid_from')
    end = v.day(raw.get('valid_to', ''), 'Fine validità', required=False, field='valid_to')
    if end and end < start:
        raise Invalid('La fine validità precede la decorrenza.', field='valid_to')
    reason = v.reason(raw['reason'])
    table = TABLES[kind]
    with db.write() as con:
        actor, person = _person(con, actor, center_id, person_id)
        cfg = centers.config(con, center_id)
        data = agreements.validate(raw['data'], cfg) if kind == 'economic' else validate_contract(raw['data'], cfg)
        rid = raw.get('id') or ''
        old = None
        if rid:
            old = con.execute(f'SELECT * FROM {table} WHERE id=? AND person_id=?', (v.identifier(rid), person['id'])).fetchone()
            if not old:
                raise NotFound('Decorrenza non trovata: ricaricare.')
        if v.version(raw['version']) != (old['version'] if old else 0):
            raise Conflict('Decorrenza modificata da un’altra sessione: ricaricare.')
        rid = rid or new_id()
        clash = con.execute(f'''SELECT valid_from FROM {table} WHERE person_id=? AND id<>? AND valid_from<=?
                                AND (valid_to='' OR valid_to>=?)''', (person['id'], rid, end or '9999-12-31', start)).fetchone()
        if clash:
            raise Invalid('Intervalli sovrapposti: chiudere prima la validità precedente al giorno prima della nuova decorrenza.',
                          field='valid_from')
        version = (old['version'] if old else 0) + 1
        con.execute(f'''INSERT INTO {table}(id,person_id,valid_from,valid_to,data,version,updated_at,updated_by)
                        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET valid_from=excluded.valid_from,
                        valid_to=excluded.valid_to, data=excluded.data, version=excluded.version,
                        updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (rid, person['id'], start, end, dumps(data), version, stamp(), actor.username))
        before = dict(valid_from=old['valid_from'], valid_to=old['valid_to'], data=loads(old['data'])) if old else None
        after = dict(id=rid, valid_from=start, valid_to=end, data=data, version=version)
        _history(con, actor, person, kind, rid, reason, before, after)
        if kind == 'contract' and start <= today_iso() and (not end or end >= today_iso()) and data['role'] != person['role']:
            # Il ruolo del registro segue il contratto in vigore oggi.
            con.execute('UPDATE people SET role=?, contract=?, version=version+1, updated_at=? WHERE id=?',
                        (data['role'], data['contract_type'], stamp(), person['id']))
    return dict(record=after)


def month_segments(con, person_id, month):
    days = month_days(month)
    first, last = days[0], days[-1]
    out = []
    for r in reversed(records(con, 'economic', person_id)):
        if r['valid_from'] <= last and (not r['valid_to'] or r['valid_to'] >= first):
            out.append(dict(id=r['id'], version=r['version'], valid_from=max(r['valid_from'], first),
                            valid_to=min(r['valid_to'] or last, last), data=r['data']))
    return out


def _preview(con, center_id, person, month):
    state = months.get(con, center_id, month)
    cfg, _ = months.configuration(con, center_id, state)
    segments = month_segments(con, person['id'], month)
    problem = agreements.segments_problem(segments, month)
    result = None
    if not problem:
        proposal = {**segments[0]['data'], 'segments': segments}
        result = agreements.calculate(person, months.entries(con, center_id, month), month, cfg, proposal)
    current = agreements.stored(con, center_id, month).get(person['id'])
    return dict(center_id=center_id, person_id=person['id'], month=month, segments=segments, manual_required=bool(problem),
                message=problem, result=result, closed=state['closed'], current=current)


def preview(db, user, center_id, person_id, month):
    v.month(month)
    with db.read() as con:
        _, person = _person(con, user, center_id, person_id)
        return _preview(con, center_id, person, month)


def apply(db, actor, center_id, person_id, raw):
    v.keys(raw, {'month', 'reason', 'agreement_version'}, 'Applicazione al mese', required={'month', 'reason', 'agreement_version'})
    month = v.month(raw['month'])
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, person = _person(con, actor, center_id, person_id)
        months.require_open(months.get(con, center_id, month))
        approvals.guard_month(con, actor, center_id, month)
        current = _preview(con, center_id, person, month)
        if current['manual_required']:
            raise Invalid(current['message'])
        segments = current['segments']
        data = {**segments[0]['data'], 'segments': segments}
        before = current['current']['data'] if current['current'] else None
        version = agreements.write_agreement(con, actor, center_id, month, person['id'], data, reason,
                                             v.version(raw['agreement_version']))
        _history(con, actor, person, 'apply', month, reason, before, data)
    return dict(version=version, result=current['result'])


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/workforce', cap='gruppo.gestisci')
def api_overview(ctx):
    return overview(ctx.db, ctx.user, ctx.q('on') or None)


@route('GET', '/api/workforce/<identity_id>', cap='gruppo.gestisci')
def api_detail(ctx):
    return detail(ctx.db, ctx.user, ctx.params['identity_id'], ctx.q('on') or None)


@route('POST', '/api/workforce/<cid>/<pid>/link', cap='gruppo.gestisci', step_up=True)
def api_link(ctx):
    return link(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.body)


@route('PUT', '/api/workforce/<cid>/<pid>/contracts', cap='gruppo.gestisci', step_up=True)
def api_contract(ctx):
    return save_interval(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], 'contract', ctx.body)


@route('PUT', '/api/workforce/<cid>/<pid>/economics', cap='gruppo.gestisci', step_up=True)
def api_economic(ctx):
    return save_interval(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], 'economic', ctx.body)


@route('GET', '/api/workforce/<cid>/<pid>/preview/<month>', cap='gruppo.gestisci')
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.params['month'])


@route('POST', '/api/workforce/<cid>/<pid>/apply', cap='gruppo.gestisci', step_up=True)
def api_apply(ctx):
    return apply(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.body)
