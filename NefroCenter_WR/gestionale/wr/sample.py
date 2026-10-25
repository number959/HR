"""Archivio dimostrativo con dati interamente fittizi (demo pubblica, schermate, prove).

Tutti i nomi, gli indirizzi e i documenti sono inventati; i recapiti usano il
dominio riservato example.invalid. I dati passano dalle stesse funzioni del
portale, quindi rispettano le stesse regole dell'applicazione aziendale.
Non usare mai questo modulo su un archivio aziendale.
"""
import random
from datetime import date, timedelta
from pathlib import Path

from . import (agreements, approvals, attendance, centers, departures, hr, mail, months, people, rules, staffing,
               structures, users, workforce)
from .auth import Auth
from .db import Database
from .permissions import User
from .errors import WRError
from .util import month_days, new_id, previous_month, set_today, stamp

DEMO_TODAY = '2026-10-25'
CENTERS = [('Capodichino · Demo', 'DEMO-CAP', 'Napoli', ['Ospedale del Mare · ambulatorio']),
           ('Pozzuoli · Demo', 'DEMO-POZ', 'Pozzuoli', []),
           ('Vomero · Demo', 'DEMO-VOM', 'Napoli', [])]
PEOPLE = {
    'DEMO-CAP': [('Anna Rossi', 'INF', 'DEMO001'), ('Marco Bianchi', 'MED', 'DEMO002'), ('Elena Costa', 'OSS', 'DEMO003'),
                 ('Paolo Greco', 'INF', 'DEMO004')],
    'DEMO-POZ': [('Chiara Ferri', 'INF', 'DEMO101'), ('Anna Rossi', 'INF', 'DEMO102'), ('Luca Moretti', 'OSS', 'DEMO103'),
                 ('Giulia Serra', 'MED', 'DEMO104')],
    'DEMO-VOM': [('Sara Conti', 'OSS', 'DEMO201'), ('Andrea Riva', 'MED', 'DEMO202'), ('Lucia Verdi', 'INF', 'DEMO203'),
                 ('Matteo Villa', 'INF', 'DEMO204')],
}
ACCOUNTS = [('demo.admin', 'Amministrazione · demo', 'admin', []), ('demo.hr', 'Ufficio HR · demo', 'hr', []),
            ('demo.manager', 'Responsabile · demo', 'manager', ['DEMO-CAP', 'DEMO-POZ']),
            ('demo.operator', 'Compilatore · demo', 'operator', ['DEMO-CAP']),
            ('demo.viewer', 'Direzione · demo', 'viewer', ['DEMO-CAP', 'DEMO-POZ', 'DEMO-VOM'])]
# Turni ricorrenti per posizione nella struttura: (fasce del lunedì..sabato)
ROLES = {(code, name): role for code, rows in PEOPLE.items() for name, role, _ in rows}
QUALIFICATIONS = {'INF': 'Infermiere', 'MED': 'Medico nefrologo', 'OSS': 'Operatore socio sanitario'}
WITH_DOCUMENTS = {('DEMO-CAP', 'Anna Rossi'), ('DEMO-CAP', 'Marco Bianchi'), ('DEMO-POZ', 'Chiara Ferri'),
                  ('DEMO-POZ', 'Giulia Serra')}
SKIPPED = []  # registrazioni scartate dalle regole (per esempio riposo o sovrapposizioni): devono restare poche
PATTERNS = [['m', 'm', 'p', 'm', 'p', 'm'], ['p', 'm', 'm', 'p', 'm', ''], ['m', 'p', '', 'm', 'm', 'p'],
            ['p', 'p', 'm', '', 'p', 'm']]


def tiny_pdf(title):
    """PDF minimo valido con un testo: un documento d'esempio, non un documento reale."""
    text = title.replace('\\', '').replace('(', '').replace(')', '')[:60]
    stream = f'BT /F1 14 Tf 60 760 Td (Documento fittizio - {text}) Tj ET'.encode('latin-1', 'replace')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
               b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = bytearray(b'%PDF-1.4\n'), []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode()
    out += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets)
    out += f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(out)


def _accounts(db, auth, demo):
    """Account dimostrativi. Nella demo l'accesso avviene senza password (Auth in modalità demo)."""
    codes = {}
    with db.write() as con:
        now = stamp()
        for username, name, role, codes_of_centers in ACCOUNTS:
            uid = new_id()
            con.execute('INSERT INTO users(id,username,name,role,active,password,version,created_at,updated_at) '
                        "VALUES(?,?,?,?,1,'!',1,?,?)", (uid, username, name, role, now, now))
            con.execute('INSERT INTO user_security(user_id) VALUES(?)', (uid,))
            if not demo:
                codes[username] = auth.issue_activation(con, uid, User(id='', username='console', name='Console', role='admin'),
                                                        'Account di prova (dati fittizi)')
    return codes


def _load(db, username):
    with db.read() as con:
        uid = con.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()[0]
        return users.load(con, uid)


def _assign(db, ids):
    with db.write() as con:
        for username, _, _, codes in ACCOUNTS:
            uid = con.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()[0]
            for code in codes:
                con.execute('INSERT INTO user_centers(user_id,center_id) VALUES(?,?)', (uid, ids[code]))


def build(data_dir=None, key_file=None, *, today=DEMO_TODAY, demo=False, path=None):
    """Crea l'archivio dimostrativo. Restituisce (Database, codici di attivazione)."""
    target = Path(path) if path else Path(data_dir) / 'wr.sqlite3'
    if target.exists():
        raise RuntimeError('Esiste già un archivio in questa cartella: i dati di prova si creano solo in una cartella nuova.')
    set_today(today)
    db = Database(target)
    db.migrate()
    mail.seed(db)
    auth = None
    if not demo:
        if key_file is None:
            raise RuntimeError('Indicare la chiave del server.')
        if not Path(key_file).exists():
            Auth.create_key(key_file)
        auth = Auth(db, key_file)
    codes = _accounts(db, auth, demo)
    admin = _load(db, 'demo.admin')
    ids = {}
    for name, code, city, sites in CENTERS:
        cid = centers.create(db, admin, dict(name=name, code=code))['id']
        ids[code] = cid
        current = centers.read_config(db, admin, cid)
        cfg = dict(current['config'])
        year = int(today[:4])
        cfg['holidays'] = sorted({d for y in (year - 1, year, year + 1) for d, _ in rules.italian_holidays(y)})
        cfg['sites'] = sites
        cfg['note'] = 'Parametri dimostrativi (dati fittizi).'
        if code == 'DEMO-VOM':
            cfg['operator_edit_times'] = True
        centers.save_config(db, admin, cid, dict(config=cfg, version=current['version'], note='Parametri dimostrativi'))
        n = len(ids)
        fields = dict(legal_name=f'{name.split(" ·")[0]} Demo S.r.l. — dati fittizi', address=f'Via Dimostrativa {n}', city=city,
                      postal_code='00000', province='NA', phone=f'000-DEMO-00{n}', email=f'sede{n}@example.invalid',
                      hr_email=f'hr.sede{n}@example.invalid', admin_email=f'amministrazione.sede{n}@example.invalid',
                      pec=f'pec.sede{n}@example.invalid', contact_name='Referente dimostrativo',
                      director='Direttore dimostrativo', website='https://example.invalid',
                      notes='Rubrica fittizia per provare le comunicazioni. Nessun recapito reale.')
        structures.save(db, admin, cid, dict(fields={**{k: '' for k in structures.KEYS}, **fields}, version=0))
    _assign(db, ids)
    hr_user, manager, operator = _load(db, 'demo.hr'), _load(db, 'demo.manager'), _load(db, 'demo.operator')
    persons = {}
    for code, rows in PEOPLE.items():
        for i, (name, role, registration) in enumerate(rows):
            pid = people.create(db, admin, ids[code], dict(name=name, role=role, registration=registration,
                                                           contract='Tempo indeterminato'))['id']
            persons[(code, name)] = pid
    # Anna Rossi lavora in due strutture: le schede sono collegate in Personale di gruppo.
    with db.read() as con:
        target_identity = people.get(con, ids['DEMO-CAP'], persons[('DEMO-CAP', 'Anna Rossi')])['identity_id']
        version = con.execute('SELECT version FROM identities WHERE id=?', (target_identity,)).fetchone()[0]
        twin = people.get(con, ids['DEMO-POZ'], persons[('DEMO-POZ', 'Anna Rossi')])
    workforce.link(db, hr_user, ids['DEMO-POZ'], twin['id'], dict(identity_id=target_identity, identity_version=version,
                                                                   version=twin['version'],
                                                                   reason='Stessa persona: verificato con il fascicolo (demo)'))
    _profiles(db, hr_user, ids, persons, today)
    _attendance(db, admin, manager, operator, hr_user, ids, persons, today)
    _processes(db, admin, hr_user, manager, ids, persons, today)
    set_today(None if not demo else today)
    return db, codes


def _profiles(db, hr_user, ids, persons, today):
    rnd = random.Random(7)
    on = date.fromisoformat(today)
    for n, ((code, name), pid) in enumerate(sorted(persons.items())):
        cid = ids[code]
        first, last = name.split(' ', 1)
        start = (on - timedelta(days=400 + 37 * n)).isoformat()
        incoming = name == 'Giulia Serra'
        if incoming:
            start = (on + timedelta(days=8)).isoformat()
        fields = {k: '' for k in hr.KEYS}
        fields.update(first_name=first, last_name=last, email=f'persona{n + 1}@example.invalid',
                      company_email=f'demo{n + 1}@example.invalid', department='Dialisi', contract_type='Tempo indeterminato',
                      ccnl='CCNL di esempio', level='D', qualification=QUALIFICATIONS[ROLES[code, name]],
                      start_date=start, weekly_hours='36', part_time_percent='100', identity_type='Facsimile',
                      identity_number=f'DEMO-{n + 1:03d}', nationality='Italiana', city='Napoli',
                      identity_expiry=(on + timedelta(days=rnd.choice([16, 45, 120, 400]))).isoformat(),
                      tutor='Tutor dimostrativo' if incoming else '')
        if name == 'Marco Bianchi':
            fields['registration_expiry'] = (on + timedelta(days=12)).isoformat()
        if name == 'Luca Moretti':
            fields.update(contract_type='Tempo determinato', end_date=(on + timedelta(days=21)).isoformat())
        with db.read() as con:
            person = people.get(con, cid, pid)
        saved = hr.save(db, hr_user, cid, dict(name=name, role=person['role'], registration=person['registration'], active=True,
                                              stage='incoming' if incoming else 'active', fields=fields, version=0), pid)
        if not incoming:
            version = saved['version']
            with db.read() as con:
                tasks = hr.tasks_of(con, pid)
            for t in tasks:
                version = hr.save_task(db, hr_user, cid, pid, t['id'], dict(status='done', version=version,
                                                                             note='Completata (demo)'))['version']
        if (code, name) in WITH_DOCUMENTS:
            doc = hr.add_document(db, hr_user, cid, pid, dict(name=f'documento_identita_{first.lower()}.pdf',
                                                              category='Documento di identità', expiry=fields['identity_expiry']),
                                  tiny_pdf(f'documento di identità {name}'))
            if name == 'Marco Bianchi':
                from . import reviews
                reviews.decide(db, hr_user, cid, doc['id'], dict(status='verified', version=1))
            if name == 'Chiara Ferri':
                from . import reviews
                reviews.decide(db, hr_user, cid, doc['id'], dict(status='needs_correction', version=1,
                                                                 note='Copia illeggibile nella seconda pagina (demo)'))


def _work_day(pattern, day):
    wd = date.fromisoformat(day).weekday()
    return pattern[wd] if wd < 6 else ''


def _attendance(db, admin, manager, operator, hr_user, ids, persons, today):
    rnd = random.Random(2026)
    current = today[:7]
    last = previous_month(current)
    for code in ('DEMO-CAP', 'DEMO-POZ', 'DEMO-VOM'):
        cid = ids[code]
        if code == 'DEMO-CAP':
            approvals.configure(db, admin, cid, dict(enabled=True, reason='Percorso di approvazione dimostrativo', version=0))
        names = [n for n, _, _ in PEOPLE[code]]
        writer = admin
        for month in (last, current):
            for idx, name in enumerate(names):
                pid = persons[(code, name)]
                pattern = PATTERNS[(idx + len(code)) % len(PATTERNS)]
                for day in month_days(month):
                    slot = _work_day(pattern, day)
                    if not slot:
                        continue
                    if (code == 'DEMO-POZ' and name == 'Anna Rossi'):
                        if date.fromisoformat(day).weekday() != 5:
                            continue  # la stessa persona lavora a Pozzuoli solo il sabato pomeriggio
                        slot = 'p'
                    if code == 'DEMO-CAP' and name == 'Anna Rossi' and date.fromisoformat(day).weekday() == 5:
                        continue
                    future = day > today
                    layer = 'planned' if future else 'actual'
                    body = dict(person_id=pid, day=day, slot=slot, code=slot, layer=layer)
                    roll = rnd.random()
                    if not future and roll < 0.05:
                        body['code'] = 'FE'
                    elif not future and roll < 0.07:
                        body['code'] = 'MA'
                    if body['code'] == slot and not future and code == 'DEMO-CAP' and roll > 0.97 and month == current:
                        body.update(start='', end='')  # turni senza orari da completare
                    if body['code'] == slot and code == 'DEMO-CAP' and name == 'Marco Bianchi' and day.endswith('-14'):
                        body['site'] = 'Ospedale del Mare · ambulatorio'
                    try:
                        attendance.save_entry(db, writer, cid, month, body)
                    except WRError:
                        SKIPPED.append((code, name, day))
                # Alcune fasce pianificate già passate e non ancora consuntivate.
                if month == current and code == 'DEMO-CAP' and idx == 2:
                    for day in month_days(month)[18:21]:
                        if date.fromisoformat(day).weekday() < 6 and day <= today:
                            try:
                                attendance.save_entry(db, writer, cid, month, dict(person_id=pid, day=day, slot='s', code='s',
                                                                                   layer='planned'))
                            except WRError:
                                SKIPPED.append((code, name, day))
        # Pazienti per fascia (carico) nel mese corrente.
        for day in month_days(current):
            if day <= today and date.fromisoformat(day).weekday() < 6:
                attendance.save_workload(db, writer, cid, current, dict(day=day, slot='m', ordinary=rnd.randint(14, 22),
                                                                         isolated=rnd.randint(0, 2)))
        # Mese precedente verificato e chiuso (con il percorso di approvazione a Capodichino).
        if code == 'DEMO-CAP':
            _approve(db, operator, manager, hr_user, cid, last)
        else:
            with db.read() as con:
                state = months.get(con, cid, last)
            state = attendance.verify_month(db, admin, cid, last, dict(verified=True, version=state['version']))['state']
            attendance.close_month(db, admin, cid, last, dict(version=state['version']))
    # Accordi confermati per due persone di Capodichino nel mese precedente.
    cid = ids['DEMO-CAP']
    # (salvati prima della chiusura non sarebbe possibile: si mostrano nel mese corrente)
    for name in ('Anna Rossi', 'Elena Costa'):
        pid = persons[('DEMO-CAP', name)]
        with db.read() as con:
            _, cfg, rows = agreements.month_rows(con, cid, current)
        row = next(r for r in rows if r['person_id'] == pid)
        data = dict(row['agreement'], basis='all', confirmed=True)
        agreements.save(db, manager, cid, current, pid, dict(agreement=data, reason='Accordo individuale firmato (demo)',
                                                             version=0))


def _approve(db, operator, manager, hr_user, cid, month):
    def step(actor, action, **extra):
        state = approvals.read(db, actor, cid, month)
        approvals.transition(db, actor, cid, month, dict(action=action, version=state['workflow']['version'],
                                                         fingerprint=state['fingerprint'], **extra))
    # Il mese precedente va consuntivato per intero prima dell'invio.
    with db.read() as con:
        pending = [e for e in months.entries(con, cid, month) if e['layer'] == 'planned']
    for e in pending:
        attendance.save_entry(db, manager, cid, month, dict(person_id=e['person_id'], day=e['day'], slot=e['slot'],
                                                           code=e['code'], layer='actual'))
    step(operator, 'submit')
    step(manager, 'manager_approve', calendar_checked=True)
    step(hr_user, 'hr_approve')


def _processes(db, admin, hr_user, manager, ids, persons, today):
    cap = ids['DEMO-CAP']
    current = today[:7]
    on = date.fromisoformat(today)
    # Fabbisogni: due infermieri e un medico al mattino, un OSS al pomeriggio.
    weekly = []
    for wd in range(6):
        weekly += [dict(weekday=wd, slot='m', role='INF', minimum=2), dict(weekday=wd, slot='m', role='MED', minimum=1),
                   dict(weekday=wd, slot='p', role='OSS', minimum=1)]
    staffing.save_requirements(db, manager, cap, dict(version=0, weekly=weekly))
    elena = persons[('DEMO-CAP', 'Elena Costa')]
    future = [d for d in month_days(current) if d > today and date.fromisoformat(d).weekday() < 6]
    if future:
        staffing.save_availability(db, hr_user, cap, elena, dict(version=0, start=future[0], end=future[0],
                                                                 status='unavailable', note='Formazione esterna (demo)'))
    # Sostituzione proposta: Anna Rossi da Pozzuoli verso Capodichino, in attesa del responsabile.
    anna_cap, anna_poz = persons[('DEMO-CAP', 'Anna Rossi')], persons[('DEMO-POZ', 'Anna Rossi')]
    for day in future[1:]:
        try:
            staffing.propose(db, hr_user, cap, dict(person_id=anna_cap, origin_center_id=ids['DEMO-POZ'], origin_person_id=anna_poz,
                                                    day=day, slot='s', code='s', note='Copertura turno serale (demo)'))
            break
        except WRError:
            continue
    # Contratti con decorrenza per due persone.
    for name in ('Anna Rossi', 'Paolo Greco'):
        pid = persons[('DEMO-CAP', name)]
        workforce.save_interval(db, hr_user, cap, pid, 'contract', dict(
            version=0, valid_from=f'{on.year}-01-01', data=dict(role='INF', contract_type='Tempo indeterminato', ccnl='CCNL di esempio',
                                                                level='D', weekly_hours=36, part_time_percent=100),
            reason='Contratto registrato in Personale di gruppo (demo)'))
    # Uscita in corso con badge da restituire.
    paolo = persons[('DEMO-CAP', 'Paolo Greco')]
    case = departures.save_case(db, hr_user, cap, dict(person_id=paolo, kind='termination', reason='Dimissioni volontarie (demo)',
                                                       effective_date=(on + timedelta(days=20)).isoformat(),
                                                       responsible='Ufficio HR · demo', version=0))
    departures.save_task(db, hr_user, cap, case['id'], 'documents', dict(status='done', version=case['version']))
    departures.save_asset(db, hr_user, cap, dict(person_id=paolo, kind='badge', inventory_code='BADGE-DEMO-004',
                                                 label='Badge di accesso (demo)', delivery_date=f'{on.year}-01-10', version=0))
    # Lista email dimostrativa: le bozze si creano dalla pagina Comunicazioni.
    mail.save_list(db, hr_user, dict(name='Personale di Capodichino (demo)', cids=[cap], roles=[], stages=['active'],
                                     version=0))
