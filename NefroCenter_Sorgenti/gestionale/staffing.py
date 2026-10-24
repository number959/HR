"""Copertura pianificata, disponibilità e proposte di sostituzione tra sedi.

I fabbisogni sono riferimenti organizzativi indicati dall'azienda, non soglie
cliniche. Le proposte non cambiano le presenze finché un responsabile autorizzato
non le accetta. L'accettazione registra soltanto il pianificato.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
import agreements
import workforce
from rules import make_entry, month_days, span


def init(app):
    with app.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS staffing_requirements(
            cid TEXT PRIMARY KEY REFERENCES centers(id),version INTEGER NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS staffing_availability(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,
            status TEXT NOT NULL,note TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE INDEX IF NOT EXISTS staffing_availability_dates ON staffing_availability(cid,pid,start,end);
        CREATE TABLE IF NOT EXISTS staffing_proposals(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,origin_cid TEXT NOT NULL,origin_pid TEXT NOT NULL,
            day TEXT NOT NULL,slot TEXT NOT NULL,code TEXT NOT NULL,note TEXT NOT NULL,status TEXT NOT NULL,
            version INTEGER NOT NULL,fingerprint TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,
            decision_note TEXT NOT NULL DEFAULT '',decided_at TEXT NOT NULL DEFAULT '',decided_by TEXT NOT NULL DEFAULT '',
            entry_id TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id),FOREIGN KEY(origin_cid,origin_pid) REFERENCES people(cid,id));
        CREATE UNIQUE INDEX IF NOT EXISTS staffing_pending_unique ON staffing_proposals(cid,pid,day,slot) WHERE status='pending';
        ''')
        c.commit()


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Indicare una data valida nel formato AAAA-MM-GG.')
    date.fromisoformat(value)
    return value


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValueError('Mese non valido.')
    return month_days(value)


def _text(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ValueError('Testo non valido o troppo lungo.')
    value = value.strip()
    if required and len(value) < 8:
        raise ValueError('Indicare una motivazione di almeno 8 caratteri.')
    return value


def _version(value):
    if type(value) != int or value < 0:
        raise ValueError('Versione non valida. Ricaricare la pagina.')
    return value


def _id(value, optional=False):
    if not isinstance(value, str) or len(value) > 128 or '\x00' in value or (not optional and not value):
        raise ValueError('Riferimento non valido. Ricaricare la pagina.')
    return value


def _user(app, c, user, cid, write=False, hr=False):
    _id(cid)
    user = app.fresh_user(c, user)
    app.authorize(user, cid)
    app.center(c, cid)
    if write:
        app.require_manager(user, cid)
    elif hr:
        app.require_hr(user, cid)
    return user


def _allowed(user, cid):
    return user['role'] in ('admin', 'hr') or cid in user['centers']


def _person(c, cid, pid):
    _id(pid)
    row = c.execute('SELECT data FROM people WHERE cid=? AND id=?', (cid, pid)).fetchone()
    if not row:
        raise ValueError('Persona non presente nella struttura.')
    return json.loads(row['data'])


def _requirements(c, cid):
    row = c.execute('SELECT version,data FROM staffing_requirements WHERE cid=?', (cid,)).fetchone()
    return dict(cid=cid, version=row['version'] if row else 0,
                **(json.loads(row['data']) if row else dict(weekly=[], overrides=[])))


def save_requirements(app, user, body):
    cid = body.get('cid', '')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _user(app, c, user, cid, write=True)
        previous = _requirements(c, cid)
        if _version(body.get('version')) != previous['version']:
            raise ValueError('Fabbisogni modificati. Ricaricare prima di salvare.')
        cfg = app.center(c, cid)['config']
        slots = {s['id'] for s in cfg['slots'] if s['active']}
        data = {}
        for key in ('weekly', 'overrides'):
            rows = body.get(key, [])
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError('Massimo 1000 righe di fabbisogno per elenco.')
            unique, clean = set(), []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('Riga di fabbisogno non valida.')
                if not isinstance(row.get('slot'), str) or not isinstance(row.get('role'), str) or row['slot'] not in slots or row['role'] not in cfg['roles']:
                    raise ValueError('Fascia o qualifica non disponibile nel centro.')
                if type(row.get('minimum')) != int or not 0 <= row['minimum'] <= 1000:
                    raise ValueError('Il minimo deve essere un intero tra 0 e 1000.')
                if key == 'weekly':
                    when = row.get('weekday')
                    if type(when) != int or when not in range(7):
                        raise ValueError('Giorno della settimana non valido.')
                    clean_row = dict(weekday=when)
                else:
                    when = _day(row.get('day'))
                    clean_row = dict(day=when)
                identity = (when, row['slot'], row['role'])
                if identity in unique:
                    raise ValueError('Fabbisogno duplicato per giorno, fascia e qualifica.')
                unique.add(identity)
                clean.append({**clean_row, 'slot': row['slot'], 'role': row['role'], 'minimum': row['minimum']})
            data[key] = clean
        current = dict(cid=cid, version=previous['version'] + 1, **data)
        c.execute('INSERT INTO staffing_requirements VALUES(?,?,?) ON CONFLICT(cid) DO UPDATE SET version=excluded.version,data=excluded.data',
                  (cid, current['version'], app.dump(data)))
        app.audit(c, user, 'Fabbisogni di copertura aggiornati', cid, previous, current)
        c.commit()
    return dict(ok=True, requirements=current)


def save_availability(app, user, body):
    cid, pid = body.get('cid', ''), body.get('pid', '')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _user(app, c, user, cid, hr=True)
        _person(c, cid, pid)
        aid = _id(body.get('id', ''), optional=True)
        old = c.execute('SELECT * FROM staffing_availability WHERE id=? AND cid=? AND pid=?',
                        (aid, cid, pid)).fetchone()
        if body.get('id') and not old:
            raise ValueError('Disponibilità non trovata.')
        if _version(body.get('version')) != (old['version'] if old else 0):
            raise ValueError('Disponibilità modificata. Ricaricare prima di salvare.')
        start, end = _day(body.get('from')), _day(body.get('to'))
        if not 0 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 366:
            raise ValueError('Intervallo di disponibilità non valido o superiore a 367 giorni.')
        status = body.get('status')
        if status not in ('available', 'unavailable', 'preferred'):
            raise ValueError('Stato di disponibilità non valido.')
        active = body.get('active', True)
        if type(active) != bool:
            raise ValueError('Stato attivo non valido.')
        note = _text(body.get('note', ''), 1000)
        aid = old['id'] if old else app.uid()
        if active and c.execute('''SELECT 1 FROM staffing_availability WHERE cid=? AND pid=? AND active=1
            AND id<>? AND start<=? AND end>=?''', (cid, pid, aid, end, start)).fetchone():
            raise ValueError('Intervallo sovrapposto a una disponibilità già registrata. Modificare o ritirare quella esistente.')
        current = dict(id=aid, cid=cid, pid=pid, start=start, end=end, status=status, note=note,
                       active=int(active), version=(old['version'] if old else 0) + 1, stamp=app.now(), actor=user['username'])
        c.execute('''INSERT INTO staffing_availability VALUES(:id,:cid,:pid,:start,:end,:status,:note,:active,:version,:stamp,:actor)
            ON CONFLICT(id) DO UPDATE SET start=excluded.start,end=excluded.end,status=excluded.status,note=excluded.note,
            active=excluded.active,version=excluded.version,stamp=excluded.stamp,actor=excluded.actor''', current)
        app.audit(c, user, 'Disponibilità personale aggiornata', cid, dict(old) if old else None, current)
        c.commit()
    return dict(ok=True, availability=current)


def _linked(c, cid, pid):
    assignment = workforce._assignment(c, cid, pid)
    return [dict(r) for r in c.execute('SELECT cid,pid,global_id,version FROM workforce_assignments WHERE global_id=?', (assignment['global_id'],))]


def _span_for(app, c, cid, entry):
    if entry['kind'] == 'work':
        return span(entry)
    ct = app.center(c, cid)
    cfg = app.effective_rules(ct, app.period(c, ct, entry['day'][:7]))
    slot = next((s for s in cfg['slots'] if s['id'] == entry['slot']), None)
    if not slot:
        return None
    first = datetime.fromisoformat(entry['day'] + 'T' + slot['start'])
    last = datetime.fromisoformat(entry['day'] + 'T' + slot['end']) + timedelta(days=int(slot['overnight']))
    return first, last


def _overlap(a, b):
    return bool(a and b and a[0] < b[1] and b[0] < a[1])


def _availability_conflict(c, assignments, interval):
    if not interval:
        return False
    first = interval[0].date().isoformat()
    last = (interval[1] - timedelta(microseconds=1)).date().isoformat()
    for a in assignments:
        if c.execute('''SELECT 1 FROM staffing_availability WHERE cid=? AND pid=? AND active=1 AND status='unavailable'
            AND start<=? AND end>=?''', (a['cid'], a['pid'], last, first)).fetchone():
            return True
    return False


def _global_entries(app, c, assignments):
    result = []
    for a in assignments:
        for entry in app.objects(c, 'entries', a['cid']):
            if entry['person_id'] == a['pid']:
                result.append((a['cid'], entry))
    return result


def _proposal_state(app, c, proposal):
    cid, pid, origin_cid, origin_pid, day = (proposal[k] for k in ('cid', 'pid', 'origin_cid', 'origin_pid', 'day'))
    ct = app.center(c, cid)
    origin = app.center(c, origin_cid)
    person = workforce.effective_person(c, cid, pid, day)
    original = workforce.effective_person(c, origin_cid, origin_pid, day)
    if not person.get('active') or not original.get('active'):
        raise ValueError('La persona deve essere attiva in entrambe le strutture.')
    if person['global_id'] != original['global_id'] or cid == origin_cid:
        raise ValueError('Per una sostituzione tra sedi servono due anagrafiche della stessa persona collegate esplicitamente.')
    period = app.period(c, ct, day[:7])
    if period['closed']:
        raise ValueError('Il mese della struttura di destinazione è chiuso.')
    cfg = app.effective_rules(ct, period)
    if person['role'] not in cfg['roles']:
        raise ValueError('Qualifica non prevista nella struttura di destinazione.')
    raw = dict(person_id=pid, day=day, slot=proposal['slot'], code=proposal['code'], layer='planned', note=proposal['note'])
    links = _linked(c, cid, pid)
    entries = _global_entries(app, c, links)
    comparisons = [{**entry, 'person_id': pid} for _, entry in entries]
    entry, warnings = make_entry(raw, cfg, person, ct['name'], 'admin', comparisons)
    if entry['kind'] != 'work':
        raise ValueError('La sostituzione richiede una causale di lavoro.')
    interval = span(entry)
    if interval is None:
        raise ValueError('La fascia di destinazione deve avere orari definiti per pianificare una sostituzione.')
    if _availability_conflict(c, links, interval):
        raise ValueError('La persona risulta non disponibile durante il turno, anche considerando l’eventuale notte.')
    for source_cid, other in entries:
        if (other['layer'] == 'planned' and other['kind'] == 'work' and span(other) is None
                and _overlap(interval, _span_for_missing(app, c, source_cid, other))):
            raise ValueError('Completare gli orari del pianificato già presente prima di proporre una sostituzione.')
        if other['layer'] == 'planned' and other['kind'] != 'work' and _overlap(interval, _span_for(app, c, source_cid, other)):
            raise ValueError('La persona ha già un’assenza o riposo pianificato durante il turno.')
    availability = [dict(r) for a in links for r in c.execute('SELECT * FROM staffing_availability WHERE cid=? AND pid=? ORDER BY id', (a['cid'], a['pid']))]
    snapshot = dict(target_revision=ct['revision'], origin_revision=origin['revision'], config=cfg,
                    person=person, origin=original, links=links, entries=entries, availability=availability)
    fingerprint = hashlib.sha256(app.dump(snapshot).encode()).hexdigest()
    return fingerprint, entry, warnings, ct, period


def _span_for_missing(app, c, cid, entry):
    # An unknown work interval cannot establish availability. Use its whole
    # starting day, plus the following day for a potentially overnight slot.
    ct = app.center(c, cid)
    cfg = app.effective_rules(ct, app.period(c, ct, entry['day'][:7]))
    slot = next((s for s in cfg['slots'] if s['id'] == entry['slot']), None)
    first = datetime.fromisoformat(entry['day'] + 'T00:00:00')
    return first, first + timedelta(days=2 if not slot or slot['overnight'] else 1)


def propose(app, user, body):
    cid, pid = body.get('cid', ''), body.get('pid', '')
    origin_cid, origin_pid = body.get('origin_cid', ''), body.get('origin_pid', '')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _user(app, c, user, cid, hr=True)
        _id(origin_cid)
        app.require_hr(user, origin_cid)
        _person(c, cid, pid)
        _person(c, origin_cid, origin_pid)
        day = _day(body.get('day'))
        note = _text(body.get('note', ''), 1000, required=True)
        _id(body.get('slot'))
        _id(body.get('code'))
        if c.execute("SELECT 1 FROM staffing_proposals WHERE cid=? AND pid=? AND day=? AND slot=? AND status='pending'", (cid, pid, day, body.get('slot', ''))).fetchone():
            raise ValueError('Esiste già una proposta aperta per la stessa persona e fascia.')
        proposal = dict(id=app.uid(), cid=cid, pid=pid, origin_cid=origin_cid, origin_pid=origin_pid,
                        day=day, slot=body.get('slot', ''), code=body.get('code', ''), note=note, status='pending',
                        version=1, stamp=app.now(), actor=user['username'], decision_note='', decided_at='', decided_by='', entry_id='')
        fingerprint, _, warnings, _, _ = _proposal_state(app, c, proposal)
        proposal['fingerprint'] = fingerprint
        c.execute('''INSERT INTO staffing_proposals(id,cid,pid,origin_cid,origin_pid,day,slot,code,note,status,version,fingerprint,stamp,actor,decision_note,decided_at,decided_by,entry_id)
            VALUES(:id,:cid,:pid,:origin_cid,:origin_pid,:day,:slot,:code,:note,:status,:version,:fingerprint,:stamp,:actor,:decision_note,:decided_at,:decided_by,:entry_id)''', proposal)
        app.audit(c, user, 'Sostituzione proposta', cid, after=proposal)
        c.commit()
    return dict(ok=True, id=proposal['id'], version=1, warnings=warnings)


def decide(app, user, body):
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM staffing_proposals WHERE id=?', (_id(body.get('id', '')),)).fetchone()
        if not row:
            raise ValueError('Proposta non trovata.')
        previous = dict(row)
        user = _user(app, c, user, row['cid'], write=True)
        if _version(body.get('version')) != row['version'] or row['status'] != 'pending':
            raise ValueError('La proposta è già stata valutata o modificata. Ricaricare.')
        decision = body.get('decision')
        if decision not in ('accept', 'reject'):
            raise ValueError('Esito non valido.')
        note = _text(body.get('note', ''), 1000, required=True)
        entry_id, warnings = '', []
        if decision == 'accept':
            fingerprint, entry, warnings, ct, period = _proposal_state(app, c, previous)
            if fingerprint != row['fingerprint']:
                raise ValueError('Presenze, disponibilità o dati della persona sono cambiati. Rifiutare la proposta e prepararne una aggiornata.')
            # Same connection/transaction as the proposal decision: no partial acceptance.
            import approvals
            approvals.guard_mutation(app, c, user, 'entry', {'cid': row['cid'], 'month': row['day'][:7]})
            agreements.freeze(period, app.objects(c, 'people', row['cid']))
            entry_id = app.uid()
            entry.update(id=entry_id, config_version=period['version'], updated_by=user['username'], updated_at=app.now())
            app.put(c, 'entries', row['cid'], entry)
            app.put_period(c, row['cid'], row['day'][:7], period)
            c.execute('UPDATE centers SET revision=revision+1 WHERE id=?', (row['cid'],))
            app.audit(c, user, 'Presenza pianificata da sostituzione', row['cid'], after=entry)
        status = 'accepted' if decision == 'accept' else 'rejected'
        c.execute('''UPDATE staffing_proposals SET status=?,version=version+1,decision_note=?,decided_at=?,decided_by=?,entry_id=? WHERE id=?''',
                  (status, note, app.now(), user['username'], entry_id, row['id']))
        current = dict(c.execute('SELECT * FROM staffing_proposals WHERE id=?', (row['id'],)).fetchone())
        app.audit(c, user, 'Sostituzione valutata', row['cid'], previous, current)
        c.commit()
    return dict(ok=True, id=row['id'], status=status, version=current['version'], entry_id=entry_id, warnings=warnings)


def _public_proposal(app, c, row, user):
    p = dict(row)
    p.pop('fingerprint', None)
    person = _person(c, p['cid'], p['pid'])
    p['person_name'] = person['name']
    p['center_name'] = app.center(c, p['cid'])['name']
    p['origin_name'] = app.center(c, p['origin_cid'])['name'] if _allowed(user, p['origin_cid']) else 'Altra struttura del gruppo'
    if not _allowed(user, p['origin_cid']):
        p.pop('origin_pid', None)
    return p


def report(app, user, cid, month):
    days = _month(month)
    with app.connect() as c:
        user = _user(app, c, user, cid)
        private = user['role'] in ('admin', 'manager', 'hr')
        ct = app.center(c, cid)
        period = app.period(c, ct, month)
        cfg = app.effective_rules(ct, period)
        req = _requirements(c, cid)
        people = {p['id']: p for p in app.objects(c, 'people', cid) if p.get('active')}
        entries = app.objects(c, 'entries', cid)
        weekly = {(r['weekday'], r['slot'], r['role']): r['minimum'] for r in req['weekly']}
        overrides = {(r['day'], r['slot'], r['role']): r['minimum'] for r in req['overrides']}
        rows = {}
        for day in days:
            weekday = date.fromisoformat(day).weekday()
            keys = {(slot, role) for week, slot, role in weekly if week == weekday}
            keys.update((slot, role) for when, slot, role in overrides if when == day)
            for slot, role in keys:
                minimum = overrides.get((day, slot, role), weekly.get((weekday, slot, role)))
                rows[(day, slot, role)] = dict(day=day, slot=slot, role=role, minimum=minimum,
                                             planned=set(), actual=set(), excluded=set())
        assignments, global_entries, effective, problems = {}, {}, {}, []
        for entry in entries:
            pid, day = entry['person_id'], entry['day']
            if pid not in people or not day.startswith(month + '-') or entry['kind'] != 'work' or entry['work_site'] != ct['name']:
                continue
            if (pid, day) not in effective:
                effective[(pid, day)] = workforce.effective_person(c, cid, pid, day)
            role = effective[(pid, day)]['role']
            key = (day, entry['slot'], role)
            bucket = rows.setdefault(key, dict(day=day, slot=entry['slot'], role=role, minimum=None, planned=set(), actual=set(), excluded=set()))
            if pid not in assignments:
                assignments[pid] = _linked(c, cid, pid)
                global_entries[pid] = _global_entries(app, c, assignments[pid])
            interval = span(entry)
            conflict = not interval
            if entry['layer'] == 'planned':
                conflict = conflict or _availability_conflict(c, assignments[pid], interval)
            for other_cid, other in global_entries[pid]:
                if (other_cid == cid and other['id'] == entry['id']) or other['layer'] != entry['layer']:
                    continue
                other_span = _span_for(app, c, other_cid, other)
                if other['kind'] == 'work' and other_span is None:
                    other_span = _span_for_missing(app, c, other_cid, other)
                if _overlap(interval, other_span):
                    conflict = True
                    break
            if conflict:
                bucket['excluded'].add(pid)
                if private:
                    problems.append(dict(day=day, slot=entry['slot'], person_name=people[pid]['name'], layer=entry['layer'],
                                         reason='Orari mancanti, indisponibilità o sovrapposizione: verificare il registro prima di considerare il turno coperto.'))
            else:
                bucket[entry['layer']].add(pid)
        rendered = []
        for key in sorted(rows):
            row = rows[key]
            planned, actual = len(row['planned']), len(row['actual'])
            minimum = row['minimum']
            rendered.append(dict(day=row['day'], slot=row['slot'], role=row['role'], minimum=minimum,
                                 planned=planned, actual=actual, excluded=len(row['excluded']),
                                 gap=max(0, minimum - planned) if minimum is not None else None,
                                 state='unconfigured' if minimum is None else 'uncovered' if planned < minimum else 'extra' if planned > minimum else 'covered'))
        availability = []
        proposals, candidates = [], []
        if private:
            availability = [{**dict(r), 'person_name': _person(c, cid, r['pid'])['name']} for r in c.execute(
                'SELECT * FROM staffing_availability WHERE cid=? AND start<=? AND end>=? ORDER BY start,pid', (cid, days[-1], days[0]))]
            proposals = [_public_proposal(app, c, r, user) for r in c.execute(
                'SELECT * FROM staffing_proposals WHERE cid=? AND day>=? AND day<=? ORDER BY day,stamp DESC', (cid, days[0], days[-1]))]
            for pid, person in people.items():
                for linked in _linked(c, cid, pid):
                    if linked['cid'] == cid or not _allowed(user, linked['cid']):
                        continue
                    original = _person(c, linked['cid'], linked['pid'])
                    if original.get('active'):
                        candidates.append(dict(pid=pid, origin_cid=linked['cid'], origin_pid=linked['pid'], name=person['name'],
                                               origin_name=app.center(c, linked['cid'])['name']))
        return dict(cid=cid, month=month, center_name=ct['name'], closed=period['closed'], requirements=req,
                    slots=[{k: s[k] for k in ('id','label','start','end','overnight','active')} for s in cfg['slots']],
                    roles=cfg['roles'], codes=[{k: code[k] for k in ('id','label','kind','active','allowed_slots')} for code in cfg['codes']],
                    rows=rendered, summary=dict(configured=sum(r['minimum'] is not None for r in rendered),
                    uncovered=sum(r['state'] == 'uncovered' for r in rendered), missing=sum(r['gap'] or 0 for r in rendered)),
                    availability=availability, proposals=proposals, candidates=candidates, problems=problems,
                    people=[dict(id=p['id'], name=p['name']) for p in people.values()] if private else [],
                    permissions=dict(configure=user['role'] in ('admin','manager'), availability=private, propose=private,
                                     decide=user['role'] in ('admin','manager')),
                    note='Confronto organizzativo sul pianificato: non è una verifica di adeguatezza clinica. I turni notturni appartengono al giorno di inizio; i conflitti considerano anche il giorno successivo.')
