"""Copertura dei turni: fabbisogni, disponibilità e sostituzioni fra strutture.

I fabbisogni sono riferimenti organizzativi indicati dall'azienda, non soglie
cliniche. Una sostituzione è una proposta: diventa un turno pianificato solo
quando il responsabile della struttura di destinazione la accetta, e solo se
nel frattempo non sono cambiati presenze, disponibilità o dati della persona.
"""
import hashlib
from datetime import date, datetime, timedelta

from . import approvals, audit, centers, months, people, rules, users, workforce
from .errors import Conflict, Invalid, NotFound
from .permissions import has, in_scope, require
from .util import add_days, dumps, loads, month_days, new_id, stamp
from . import validate as v

AVAILABILITY = {'available': 'Disponibile', 'unavailable': 'Non disponibile', 'preferred': 'Disponibilità preferita'}
STATES = {'unconfigured': 'Senza fabbisogno', 'uncovered': 'Scoperto', 'covered': 'Coperto', 'extra': 'Oltre il fabbisogno'}
NOTE = ('Confronto organizzativo sul pianificato: non è una verifica di adeguatezza clinica. I turni notturni '
        'appartengono al giorno di inizio; i conflitti considerano anche il giorno successivo.')


def requirements(con, center_id):
    found = con.execute('SELECT * FROM staffing_requirements WHERE center_id=?', (center_id,)).fetchone()
    if not found:
        return dict(version=0, weekly=[], overrides=[])
    return dict(version=found['version'], weekly=loads(found['weekly']), overrides=loads(found['overrides']),
                updated_at=found['updated_at'], updated_by=found['updated_by'])


def _clean_requirements(rows, kind, cfg):
    if not isinstance(rows, list) or len(rows) > 1000:
        raise Invalid('Massimo 1000 righe di fabbisogno per elenco.', field=kind)
    slots = {s['id'] for s in cfg['slots'] if s['active']}
    seen, out = set(), []
    for row in rows:
        if kind == 'weekly':
            v.keys(row, {'weekday', 'slot', 'role', 'minimum'}, 'Fabbisogno', required={'weekday', 'slot', 'role', 'minimum'})
            when = v.integer(row['weekday'], 'Giorno della settimana', 0, 6, field=kind)
        else:
            v.keys(row, {'day', 'slot', 'role', 'minimum'}, 'Fabbisogno', required={'day', 'slot', 'role', 'minimum'})
            when = v.day(row['day'], field=kind)
        slot = v.choice(row['slot'], 'Fascia', slots, field=kind)
        role = v.choice(row['role'], 'Qualifica', cfg['roles'], field=kind)
        minimum = v.integer(row['minimum'], 'Minimo', 0, 1000, field=kind)
        if (when, slot, role) in seen:
            raise Invalid('Fabbisogno ripetuto per lo stesso giorno, fascia e qualifica.', field=kind)
        seen.add((when, slot, role))
        out.append({('weekday' if kind == 'weekly' else 'day'): when, 'slot': slot, 'role': role, 'minimum': minimum})
    return out


def save_requirements(db, actor, center_id, raw):
    v.keys(raw, {'weekly', 'overrides', 'version'}, 'Fabbisogni', required={'version'})
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'copertura.fabbisogni')
        old = requirements(con, center_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Fabbisogni modificati da un’altra sessione: ricaricare.')
        cfg = centers.config(con, center_id)
        weekly = _clean_requirements(raw.get('weekly', []), 'weekly', cfg)
        overrides = _clean_requirements(raw.get('overrides', []), 'overrides', cfg)
        con.execute('''INSERT INTO staffing_requirements(center_id,weekly,overrides,version,updated_at,updated_by) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(center_id) DO UPDATE SET weekly=excluded.weekly, overrides=excluded.overrides,
                       version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (center_id, dumps(weekly), dumps(overrides), old['version'] + 1, stamp(), actor.username))
        audit.record(con, actor, 'Fabbisogni di copertura aggiornati', center_id, entity='staffing', entity_id=center_id,
                     before=dict(weekly=old['weekly'], overrides=old['overrides']), after=dict(weekly=weekly, overrides=overrides))
    return dict(version=old['version'] + 1)


def save_availability(db, actor, center_id, person_id, raw):
    v.keys(raw, {'id', 'version', 'start', 'end', 'status', 'note', 'active'}, 'Disponibilità',
           required={'version', 'start', 'end', 'status'})
    start = v.day(raw['start'], 'Dal', field='start')
    end = v.day(raw['end'], 'Al', field='end')
    if not 0 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 366:
        raise Invalid('Intervallo non valido o superiore a un anno.', field='end')
    status = v.choice(raw['status'], 'Disponibilità', AVAILABILITY, field='status')
    note = v.text(raw.get('note', ''), 'Nota', 1000, multiline=True, field='note')
    active = v.boolean(raw.get('active', True), 'Attiva', field='active')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'copertura.disponibilita')
        person = people.get(con, center_id, v.identifier(person_id, 'Persona'))
        old = None
        if raw.get('id'):
            old = con.execute('SELECT * FROM availability WHERE id=? AND person_id=?', (v.identifier(raw['id']), person['id'])).fetchone()
            if not old:
                raise NotFound('Disponibilità non trovata.')
        if v.version(raw['version']) != (old['version'] if old else 0):
            raise Conflict('Disponibilità modificata da un’altra sessione: ricaricare.')
        aid = old['id'] if old else new_id()
        if active and con.execute('SELECT 1 FROM availability WHERE person_id=? AND active=1 AND id<>? AND start<=? AND end>=?',
                                  (person['id'], aid, end, start)).fetchone():
            raise Invalid('Intervallo sovrapposto a una disponibilità già registrata: modificare o ritirare quella esistente.',
                          field='start')
        version = (old['version'] if old else 0) + 1
        con.execute('''INSERT INTO availability(id,person_id,start,end,status,note,active,version,updated_at,updated_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET start=excluded.start, end=excluded.end,
                       status=excluded.status, note=excluded.note, active=excluded.active, version=excluded.version,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (aid, person['id'], start, end, status, note, int(active), version, stamp(), actor.username))
        audit.record(con, actor, 'Disponibilità aggiornata', center_id, entity='availability', entity_id=aid,
                     before=dict(old) if old else None, after=dict(person_id=person['id'], start=start, end=end, status=status,
                                                                    active=active))
    return dict(id=aid, version=version)


# --- intervalli e conflitti --------------------------------------------------------------------

def _overlap(a, b):
    return bool(a and b and a[0] < b[1] and b[0] < a[1])


def _slot_of(con, center_id, day, slot_id):
    state = months.get(con, center_id, day[:7])
    cfg, _ = months.configuration(con, center_id, state)
    return next((s for s in cfg['slots'] if s['id'] == slot_id), None)


def _interval(con, entry):
    """Intervallo effettivo; per assenze e turni senza orari si usa la fascia o il giorno intero."""
    found = rules.span(entry)
    if found:
        return found
    slot = _slot_of(con, entry['center_id'], entry['day'], entry['slot'])
    if entry['kind'] != 'work' and slot:
        return rules.slot_span(entry['day'], slot)
    first = datetime.fromisoformat(entry['day'] + 'T00:00:00')
    return first, first + timedelta(days=2 if not slot or slot['overnight'] else 1)


def _identity_entries(con, identity_id, first, last):
    return [dict(months.entry_dict(r), center_id=r['center_id']) for r in con.execute(
        '''SELECT e.* FROM entries e JOIN people p ON p.id=e.person_id WHERE p.identity_id=? AND e.day BETWEEN ? AND ?''',
        (identity_id, first, last))]


def _unavailable(con, identity_id, interval):
    first = interval[0].date().isoformat()
    last = (interval[1] - timedelta(microseconds=1)).date().isoformat()
    return bool(con.execute('''SELECT 1 FROM availability a JOIN people p ON p.id=a.person_id WHERE p.identity_id=? AND a.active=1
                               AND a.status='unavailable' AND a.start<=? AND a.end>=?''', (identity_id, last, first)).fetchone())


def _role_on(con, person, day):
    contract = workforce.contract_on(con, person['id'], day)
    return contract['role'] if contract else person['role']


# --- prospetto di copertura ----------------------------------------------------------------------

def report(db, user, center_id, month):
    v.month(month)
    days = month_days(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'copertura.vedi')
        private = has(user, 'copertura.dettagli')
        state = months.get(con, center_id, month)
        cfg, _ = months.configuration(con, center_id, state)
        req = requirements(con, center_id)
        active = {p['id']: p for p in months.people(con, center_id) if p['active']}
        weekly = {(r['weekday'], r['slot'], r['role']): r['minimum'] for r in req['weekly']}
        overrides = {(r['day'], r['slot'], r['role']): r['minimum'] for r in req['overrides']}
        rows = {}

        def bucket(day, slot, role, minimum=None):
            return rows.setdefault((day, slot, role), dict(day=day, slot=slot, role=role, minimum=minimum, planned=set(),
                                                           actual=set(), excluded=set()))

        for day in days:
            wd = date.fromisoformat(day).weekday()
            keys = {(s, r) for (w, s, r) in weekly if w == wd} | {(s, r) for (d, s, r) in overrides if d == day}
            for slot, role in keys:
                bucket(day, slot, role, overrides.get((day, slot, role), weekly.get((wd, slot, role))))
        problems, cache = [], {}
        for e in months.entries(con, center_id, month):
            person = active.get(e['person_id'])
            if not person or e['kind'] != 'work' or e['site']:
                continue
            e = dict(e, center_id=center_id)
            row = bucket(e['day'], e['slot'], _role_on(con, person, e['day']))
            interval = rules.span(e)
            conflict = interval is None
            if not conflict and e['layer'] == 'planned':
                conflict = _unavailable(con, person['identity_id'], interval)
            if not conflict:
                key = person['identity_id']
                if key not in cache:
                    cache[key] = _identity_entries(con, key, add_days(days[0], -2), add_days(days[-1], 2))
                conflict = any(o['id'] != e['id'] and o['layer'] == e['layer'] and _overlap(interval, _interval(con, o))
                               for o in cache[key])
            if conflict:
                row['excluded'].add(person['id'])
                if private:
                    problems.append(dict(day=e['day'], slot=e['slot'], person=person['name'], layer=e['layer'],
                                         reason='Orari mancanti, indisponibilità o sovrapposizione: verificare il registro '
                                                'prima di considerare coperto il turno.'))
            else:
                row[e['layer']].add(person['id'])
        out = []
        for key in sorted(rows):
            r = rows[key]
            planned, minimum = len(r['planned']), r['minimum']
            status = ('unconfigured' if minimum is None else 'uncovered' if planned < minimum
                      else 'extra' if planned > minimum else 'covered')
            out.append(dict(day=r['day'], slot=r['slot'], role=r['role'], minimum=minimum, planned=planned,
                            actual=len(r['actual']), excluded=len(r['excluded']),
                            gap=max(0, minimum - planned) if minimum is not None else None, state=status,
                            state_label=STATES[status]))
        result = dict(center=dict(id=center['id'], name=center['name']), month=month, closed=state['closed'],
                      requirements=req, rows=out, note=NOTE,
                      slots=[{k: s[k] for k in ('id', 'label', 'start', 'end', 'overnight', 'active')} for s in cfg['slots']],
                      roles=cfg['roles'], codes=[{k: c[k] for k in ('id', 'label', 'kind', 'active', 'allowed_slots')}
                                                 for c in cfg['codes']],
                      summary=dict(configured=sum(r['minimum'] is not None for r in out),
                                   uncovered=sum(r['state'] == 'uncovered' for r in out),
                                   missing=sum(r['gap'] or 0 for r in out)),
                      permissions=dict(configure=has(user, 'copertura.fabbisogni'), availability=has(user, 'copertura.disponibilita'),
                                       propose=has(user, 'copertura.proponi'), decide=has(user, 'copertura.decidi')),
                      availability=[], substitutions=[], candidates=[], problems=problems, people=[])
        if private:
            ids = list(active)
            result['people'] = [dict(id=p['id'], name=p['name'], role=p['role']) for p in active.values()]
            for r in con.execute('''SELECT a.*, p.name FROM availability a JOIN people p ON p.id=a.person_id
                                    WHERE p.center_id=? AND a.start<=? AND a.end>=? ORDER BY a.start, p.name''',
                                 (center_id, days[-1], days[0])):
                result['availability'].append(dict(id=r['id'], person_id=r['person_id'], person=r['name'], start=r['start'],
                                                   end=r['end'], status=r['status'], status_label=AVAILABILITY[r['status']],
                                                   note=r['note'], active=bool(r['active']), version=r['version']))
            for r in con.execute('SELECT * FROM substitutions WHERE center_id=? AND day BETWEEN ? AND ? ORDER BY day, created_at DESC',
                                 (center_id, days[0], days[-1])):
                result['substitutions'].append(_public_substitution(con, user, r))
            for pid in ids:
                person = active[pid]
                for m in con.execute('''SELECT p.id, p.center_id, p.active, c.name FROM people p JOIN centers c ON c.id=p.center_id
                                        WHERE p.identity_id=? AND p.center_id<>?''', (person['identity_id'], center_id)):
                    if m['active'] and in_scope(user, m['center_id']):
                        result['candidates'].append(dict(person_id=pid, name=person['name'], origin_center_id=m['center_id'],
                                                         origin_person_id=m['id'], origin_center=m['name']))
    return result


def _public_substitution(con, user, r):
    out = dict(r)
    out.pop('fingerprint', None)
    out['person'] = con.execute('SELECT name FROM people WHERE id=?', (r['person_id'],)).fetchone()[0]
    if in_scope(user, r['origin_center_id']):
        out['origin_center'] = centers.row(con, r['origin_center_id'])['name']
    else:
        out['origin_center'] = 'Altra struttura del gruppo'
        out.pop('origin_person_id', None)
    return out


# --- sostituzioni -----------------------------------------------------------------------------------

def _state(con, sub):
    """Verifica la proposta e restituisce (impronta, registrazione da creare, avvisi)."""
    person = people.get(con, sub['center_id'], sub['person_id'])
    origin = people.get(con, sub['origin_center_id'], sub['origin_person_id'])
    if not person['active'] or not origin['active']:
        raise Invalid('La persona deve essere attiva in entrambe le strutture.')
    if person['identity_id'] != origin['identity_id'] or sub['center_id'] == sub['origin_center_id']:
        raise Invalid('Per una sostituzione servono due schede della stessa persona collegate in Personale di gruppo.')
    month = sub['day'][:7]
    state = months.get(con, sub['center_id'], month)
    if state['closed']:
        raise Invalid('Il mese della struttura di destinazione è chiuso.')
    cfg, _ = months.configuration(con, sub['center_id'], state)
    role = _role_on(con, person, sub['day'])
    if role not in cfg['roles']:
        raise Invalid('Qualifica non prevista nella struttura di destinazione.')
    raw = dict(person_id=person['id'], day=sub['day'], slot=sub['slot'], code=sub['code'], layer='planned', note=sub['note'])
    entry = rules.build_entry(raw, config=cfg, person=person, month=month, can=lambda cap: True)
    if entry['kind'] != 'work':
        raise Invalid('La sostituzione richiede una causale di lavoro.')
    interval = rules.span(entry)
    if interval is None:
        raise Invalid('La fascia di destinazione deve avere orari definiti per pianificare una sostituzione.')
    linked = _identity_entries(con, person['identity_id'], add_days(sub['day'], -3), add_days(sub['day'], 3))
    names = {c['id']: c['name'] for c in con.execute('SELECT id, name FROM centers')}
    others = [dict(o, center_name=names[o['center_id']] if o['center_id'] != sub['center_id'] else '') for o in linked]
    warnings = rules.check_conflicts(dict(entry, id=''), others, cfg['min_rest_hours'])
    if _unavailable(con, person['identity_id'], interval):
        raise Invalid('La persona risulta non disponibile durante il turno (anche considerando la notte).')
    for o in linked:
        if o['layer'] != 'planned':
            continue
        if o['kind'] == 'work' and rules.span(o) is None and _overlap(interval, _interval(con, o)):
            raise Invalid('Completare gli orari del turno già pianificato prima di proporre una sostituzione.')
        if o['kind'] != 'work' and _overlap(interval, _interval(con, o)):
            raise Invalid('La persona ha già un’assenza o un riposo pianificato durante il turno.')
    availability = [dict(r) for r in con.execute('''SELECT a.* FROM availability a JOIN people p ON p.id=a.person_id
                                                    WHERE p.identity_id=? ORDER BY a.id''', (person['identity_id'],))]
    snapshot = dict(config=cfg, person=person, origin=origin, role=role, entries=sorted(
        [{k: o[k] for k in ('id', 'version', 'day', 'slot', 'layer', 'kind', 'start', 'end', 'overnight')} for o in linked],
        key=lambda o: o['id']), availability=availability, month_version=state['version'])
    return hashlib.sha256(dumps(snapshot).encode()).hexdigest(), entry, warnings


def propose(db, actor, center_id, raw):
    v.keys(raw, {'person_id', 'origin_center_id', 'origin_person_id', 'day', 'slot', 'code', 'note'}, 'Sostituzione',
           required={'person_id', 'origin_center_id', 'origin_person_id', 'day', 'slot', 'code', 'note'})
    day = v.day(raw['day'], field='day')
    note = v.reason(raw['note'], 'Motivazione', field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'copertura.proponi')
        centers.scoped(con, actor, v.identifier(raw['origin_center_id'], 'Struttura di provenienza'), 'copertura.proponi')
        sub = dict(id=new_id(), center_id=center_id, person_id=v.identifier(raw['person_id'], 'Persona'),
                   origin_center_id=raw['origin_center_id'], origin_person_id=v.identifier(raw['origin_person_id'], 'Persona'),
                   day=day, slot=v.code(raw['slot'], 'Fascia', field='slot'), code=v.code(raw['code'], 'Causale', field='code'),
                   note=note)
        if con.execute("SELECT 1 FROM substitutions WHERE person_id=? AND day=? AND slot=? AND status='pending'",
                       (sub['person_id'], day, sub['slot'])).fetchone():
            raise Invalid('Esiste già una proposta aperta per la stessa persona e fascia.')
        fingerprint, _, warnings = _state(con, sub)
        con.execute('''INSERT INTO substitutions(id,center_id,person_id,origin_center_id,origin_person_id,day,slot,code,note,status,
                       fingerprint,version,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,'pending',?,1,?,?)''',
                    (sub['id'], center_id, sub['person_id'], sub['origin_center_id'], sub['origin_person_id'], day, sub['slot'],
                     sub['code'], note, fingerprint, stamp(), actor.username))
        audit.record(con, actor, 'Sostituzione proposta', center_id, entity='substitution', entity_id=sub['id'], after=sub)
    return dict(id=sub['id'], version=1, warnings=warnings)


def decide(db, actor, center_id, substitution_id, raw):
    v.keys(raw, {'decision', 'note', 'version'}, 'Decisione', required={'decision', 'note', 'version'})
    decision = v.choice(raw['decision'], 'Esito', ('accept', 'reject'), field='decision')
    note = v.reason(raw['note'], 'Motivazione', field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'copertura.decidi')
        found = con.execute('SELECT * FROM substitutions WHERE id=? AND center_id=?',
                            (v.identifier(substitution_id, 'Proposta'), center_id)).fetchone()
        if not found:
            raise NotFound('Proposta non trovata.')
        sub = dict(found)
        if v.version(raw['version']) != sub['version'] or sub['status'] != 'pending':
            raise Conflict('La proposta è già stata valutata o modificata: ricaricare.')
        entry_id, warnings = '', []
        if decision == 'accept':
            fingerprint, entry, warnings = _state(con, sub)
            if fingerprint != sub['fingerprint']:
                raise Conflict('Presenze, disponibilità o dati della persona sono cambiati: rifiutare la proposta e prepararne '
                               'una aggiornata.')
            month = sub['day'][:7]
            approvals.guard_month(con, actor, center_id, month)
            state = months.ensure(con, center_id, month, actor)
            entry_id = new_id()
            con.execute('''INSERT INTO entries(id,center_id,person_id,day,slot,layer,code,kind,label,start,end,pause,overnight,site,
                           holiday,credit,note,source,rules_version,version,updated_at,updated_by)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',
                        (entry_id, center_id, entry['person_id'], entry['day'], entry['slot'], 'planned', entry['code'],
                         entry['kind'], entry['label'], entry['start'], entry['end'], entry['pause'], int(entry['overnight']),
                         '', int(entry['holiday']), 0, entry['note'], 'sostituzione', state['rules_version'], stamp(),
                         actor.username))
            audit.record(con, actor, 'Turno pianificato da sostituzione', center_id, entity='entry', entity_id=entry_id,
                         after=dict(person_id=entry['person_id'], day=entry['day'], slot=entry['slot']))
        status = 'accepted' if decision == 'accept' else 'rejected'
        con.execute('''UPDATE substitutions SET status=?, version=version+1, decision_note=?, decided_at=?, decided_by=?, entry_id=?
                       WHERE id=?''', (status, note, stamp(), actor.username, entry_id, sub['id']))
        audit.record(con, actor, 'Sostituzione ' + ('accettata' if status == 'accepted' else 'rifiutata'), center_id,
                     entity='substitution', entity_id=sub['id'], after=dict(status=status, note=note, entry_id=entry_id))
    return dict(id=sub['id'], status=status, version=sub['version'] + 1, entry_id=entry_id, warnings=warnings)


def pending_for(db, user):
    """Sostituzioni in attesa nelle strutture dove l'utente decide (per la pagina iniziale)."""
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'copertura.vedi')
        if not has(user, 'copertura.decidi'):
            return []
        return [dict(id=r['id'], center_id=r['center_id'], day=r['day'], slot=r['slot'])
                for r in con.execute("SELECT * FROM substitutions WHERE status='pending' ORDER BY day")
                if in_scope(user, r['center_id'])]


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/staffing/<cid>/<month>', cap='copertura.vedi')
def api_report(ctx):
    return report(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])


@route('PUT', '/api/staffing/<cid>/requirements', cap='copertura.fabbisogni')
def api_requirements(ctx):
    return save_requirements(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('PUT', '/api/staffing/<cid>/availability/<pid>', cap='copertura.disponibilita')
def api_availability(ctx):
    return save_availability(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.body)


@route('POST', '/api/staffing/<cid>/substitutions', cap='copertura.proponi')
def api_propose(ctx):
    return propose(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('POST', '/api/staffing/<cid>/substitutions/<sid>', cap='copertura.decidi')
def api_decide(ctx):
    return decide(ctx.db, ctx.user, ctx.params['cid'], ctx.params['sid'], ctx.body)
