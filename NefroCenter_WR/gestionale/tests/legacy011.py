"""Archivio fittizio nel formato della versione 0.11, per provare la migrazione senza il codice della 0.11.

Le strutture delle tabelle sono quelle di un archivio 0.11.2 reale; i dati sono inventati e coprono
i casi delicati: parametri cambiati dopo un mese chiuso, persona presente in due strutture,
registrazioni importate da Excel, registrazione doppia, accordo salvato e proposta non confermata,
segreto Authenticator cifrato, attivazione in corso, posta e promemoria attivi.
"""
import base64
import hashlib
import json
import sqlite3
from pathlib import Path

from wr import hr, rules, security

DDL = """
CREATE TABLE approval_history( cid TEXT NOT NULL,month TEXT NOT NULL,version INTEGER NOT NULL, action TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL, fingerprint TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL, PRIMARY KEY(cid,month,version));
CREATE TABLE approval_months( cid TEXT NOT NULL,month TEXT NOT NULL,version INTEGER NOT NULL, status TEXT NOT NULL,fingerprint TEXT NOT NULL,note TEXT NOT NULL, updated_at TEXT NOT NULL,updated_by TEXT NOT NULL,PRIMARY KEY(cid,month));
CREATE TABLE approval_policies( cid TEXT PRIMARY KEY,version INTEGER NOT NULL, enabled INTEGER NOT NULL,reason TEXT NOT NULL,updated_at TEXT NOT NULL,updated_by TEXT NOT NULL);
CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT,stamp TEXT,username TEXT,action TEXT,before_data TEXT,after_data TEXT);
CREATE TABLE centers(id TEXT PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,config TEXT NOT NULL,version INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE communication_attempts( id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL, number INTEGER NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, started_epoch REAL NOT NULL, finished_at TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', message_id TEXT NOT NULL, UNIQUE(recipient_id,number));
CREATE TABLE communication_campaigns( id TEXT PRIMARY KEY, created_at TEXT NOT NULL, created_by TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE communication_lists( id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE communication_recipients( id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '', claimed_at REAL, batch_id TEXT NOT NULL DEFAULT '', UNIQUE(campaign_id,ordinal));
CREATE TABLE communication_settings( id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE communication_templates( id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE departure_cases( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL, status TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE departure_history( id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT NOT NULL,kind TEXT NOT NULL,object_id TEXT NOT NULL, version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE entries(cid TEXT,id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
CREATE TABLE equipment_assignments( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL, asset_key TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE group_people( id TEXT PRIMARY KEY,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE hr_document_review_history( document_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL, stamp TEXT NOT NULL, actor TEXT NOT NULL, PRIMARY KEY(document_id,version) );
CREATE TABLE hr_document_reviews( document_id TEXT PRIMARY KEY, version INTEGER NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL );
CREATE TABLE hr_documents(id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,expiry TEXT NOT NULL,uploaded_at TEXT NOT NULL,uploaded_by TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL);
CREATE TABLE hr_history(cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(cid,pid,version));
CREATE TABLE hr_profiles(cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(cid,pid));
CREATE TABLE hr_settings(cid TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL);
CREATE TABLE imports(hash TEXT PRIMARY KEY,cid TEXT,month TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE patients(cid TEXT,id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
CREATE TABLE payroll_templates( cid TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL, PRIMARY KEY(cid,version));
CREATE TABLE people(cid TEXT,id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
CREATE TABLE periods(cid TEXT,month TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,month));
CREATE TABLE reminder_events( event_key TEXT PRIMARY KEY, cid TEXT NOT NULL, source_key TEXT NOT NULL, due TEXT NOT NULL, threshold INTEGER NOT NULL, email TEXT NOT NULL, topic TEXT NOT NULL, created_at TEXT NOT NULL, recipient_id TEXT NOT NULL);
CREATE TABLE reminder_runs( id TEXT PRIMARY KEY, stamp TEXT NOT NULL, state TEXT NOT NULL, messages INTEGER NOT NULL, events INTEGER NOT NULL, note TEXT NOT NULL);
CREATE TABLE reminder_settings( id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, data TEXT NOT NULL, enabled_by TEXT NOT NULL DEFAULT '');
CREATE TABLE staffing_availability( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL, status TEXT NOT NULL,note TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE staffing_proposals( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,origin_cid TEXT NOT NULL,origin_pid TEXT NOT NULL, day TEXT NOT NULL,slot TEXT NOT NULL,code TEXT NOT NULL,note TEXT NOT NULL,status TEXT NOT NULL, version INTEGER NOT NULL,fingerprint TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL, decision_note TEXT NOT NULL DEFAULT '',decided_at TEXT NOT NULL DEFAULT '',decided_by TEXT NOT NULL DEFAULT '', entry_id TEXT NOT NULL DEFAULT '');
CREATE TABLE staffing_requirements( cid TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL);
CREATE TABLE structure_profiles( cid TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version > 0), data TEXT NOT NULL);
CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,centers TEXT NOT NULL,active INTEGER NOT NULL,credential TEXT NOT NULL);
CREATE TABLE web_events( id INTEGER PRIMARY KEY AUTOINCREMENT, stamp TEXT NOT NULL, user_id TEXT, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE TABLE web_rate( id TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL, blocked REAL NOT NULL DEFAULT 0);
CREATE TABLE web_security( user_id TEXT PRIMARY KEY, secret TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0, last_step INTEGER NOT NULL DEFAULT -1, recovery TEXT NOT NULL DEFAULT '[]', activation TEXT NOT NULL DEFAULT '', activation_until REAL NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, last_login TEXT NOT NULL DEFAULT '');
CREATE TABLE web_sessions( id TEXT PRIMARY KEY, csrf TEXT NOT NULL, user_id TEXT, stage TEXT NOT NULL, version INTEGER NOT NULL, created REAL NOT NULL, touched REAL NOT NULL, expires REAL NOT NULL, verified REAL NOT NULL DEFAULT 0, pending_secret TEXT NOT NULL DEFAULT '', pending_until REAL NOT NULL DEFAULT 0);
CREATE TABLE workforce_assignments( cid TEXT NOT NULL,pid TEXT NOT NULL,global_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(cid,pid), UNIQUE(global_id,cid));
CREATE TABLE workforce_contracts( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL, effective_from TEXT NOT NULL,effective_to TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,data TEXT NOT NULL);
CREATE TABLE workforce_economics( id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL, effective_from TEXT NOT NULL,effective_to TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,data TEXT NOT NULL);
CREATE TABLE workforce_history( id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT NOT NULL,pid TEXT NOT NULL, kind TEXT NOT NULL,record_id TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL, reason TEXT NOT NULL,before_data TEXT NOT NULL,after_data TEXT NOT NULL);
"""

PASSWORD = 'Password-della-011'
STAMP = '2026-09-30T18:00:00+00:00'
C1, C2 = 'c' * 31 + '1', 'c' * 31 + '2'
ANNA1, ANNA2, MARCO, LUCA = 'a' * 31 + '1', 'a' * 31 + '2', 'b' * 32, 'd' * 32
GLOBAL_ANNA = 'e' * 32
PDF = b'%PDF-1.4\n% documento dimostrativo\n%%EOF\n'


def j(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def build(path, *, secret='JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP', legacy_key_path=None, activation_code='codice-attivazione-011',
          now=1_800_000_000.0):
    """Crea l'archivio 0.11 di prova. Se legacy_key_path è indicato, cifra il segreto TOTP con quella chiave."""
    con = sqlite3.connect(path)
    for statement in DDL.strip().split(';\n'):
        if statement.strip():
            con.execute(statement)
    con.execute('PRAGMA user_version=8')
    v1 = rules.defaults()
    v2 = dict(rules.defaults(), min_rest_hours=12, note='Riposo aumentato a ottobre')
    con.execute('INSERT INTO centers VALUES(?,?,?,?,?,?)', (C1, 'Centro Uno', 'UNO', j(v2), 2, 40))
    con.execute('INSERT INTO centers VALUES(?,?,?,?,?,?)', (C2, 'Centro Due', 'DUE', j(v1), 1, 10))
    credential = security.hash_password(PASSWORD, 'admin011')
    users = [('u1', 'admin011', 'Amministratore 011', 'admin', []), ('u2', 'hr011', 'HR 011', 'hr', []),
             ('u3', 'resp011', 'Responsabile 011', 'manager', [C1]), ('u4', 'comp011', 'Compilatore 011', 'operator', [C1, C2])]
    for uid, username, name, role, centers in users:
        con.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)', (uid, username, name, role, j(centers), 1, credential))
    # admin con Authenticator (segreto cifrato con la chiave 0.11), comp011 con attivazione in corso
    enc = ''
    if legacy_key_path:
        from cryptography.fernet import Fernet
        enc = Fernet(Path(legacy_key_path).read_bytes().strip()).encrypt(secret.encode()).decode()
    recovery = [hashlib.sha256('ABCD1234ABCD1234'.encode()).hexdigest()]
    con.execute('INSERT INTO web_security VALUES(?,?,?,?,?,?,?,?,?)', ('u1', enc or 'segreto-non-leggibile', 1, -1, j(recovery), '', 0, 3, STAMP))
    con.execute('INSERT INTO web_security VALUES(?,?,?,?,?,?,?,?,?)', ('u2', '', 0, -1, '[]', '', 0, 1, ''))
    con.execute('INSERT INTO web_security VALUES(?,?,?,?,?,?,?,?,?)', ('u4', '', 0, -1, '[]',
                hashlib.sha256(activation_code.encode()).hexdigest(), now + 3 * 86400, 2, ''))
    con.execute('INSERT INTO web_events(stamp,user_id,actor,action,detail) VALUES(?,?,?,?,?)', (STAMP, 'u1', 'admin011', 'Accesso', ''))
    # persone: Anna in entrambe le strutture (stessa identità), Marco e Luca solo nella prima
    people = [(C1, ANNA1, dict(name='Anna Prova', role='INF', registration='M001', contract='Tempo indeterminato')),
              (C2, ANNA2, dict(name='Anna Prova', role='INF', registration='M001', contract='Tempo indeterminato')),
              (C1, MARCO, dict(name='Marco Prova', role='MED', registration='M002', contract='',
                               pay_override=dict(weekday_rate=55, holiday_rate=75, fixed_deduction=0, ccnl_rate=70, pay_mode='all'))),
              (C1, LUCA, dict(name='Luca Prova', role='OSS', registration='', contract='', active=False))]
    for cid, pid, d in people:
        data = dict(id=pid, home_site='Centro Uno' if cid == C1 else 'Centro Due', note='', pay_override=None, active=True)
        data.update(d)
        con.execute('INSERT INTO people VALUES(?,?,?)', (cid, pid, j(data)))
    con.execute('INSERT INTO group_people VALUES(?,?)', (GLOBAL_ANNA, 3))
    con.execute('INSERT INTO workforce_assignments VALUES(?,?,?,?)', (C1, ANNA1, GLOBAL_ANNA, 2))
    con.execute('INSERT INTO workforce_assignments VALUES(?,?,?,?)', (C2, ANNA2, GLOBAL_ANNA, 1))
    con.execute('INSERT INTO group_people VALUES(?,?)', ('f' * 32, 1))
    con.execute('INSERT INTO workforce_assignments VALUES(?,?,?,?)', (C1, MARCO, 'f' * 32, 1))

    def entry(cid, eid, pid, day, slot='m', code='m', layer='actual', **extra):
        kind = 'absence' if code in ('FE', 'MA') else 'work'
        data = dict(id=eid, person_id=pid, day=day, slot=slot, code=code, code_label={'m': 'Mattina', 'p': 'Pomeriggio', 'FE': 'Ferie'}.get(code, code),
                    layer=layer, kind=kind, start='07:00' if kind == 'work' else '', end='13:00' if kind == 'work' else '', pause=0,
                    overnight=False, holiday=False, work_site='Centro Uno' if cid == C1 else 'Centro Due', credit_minutes=0, note='',
                    config_version=1 if day < '2026-10' else 2, updated_by='comp011', updated_at=STAMP)
        data.update(extra)
        con.execute('INSERT INTO entries VALUES(?,?,?)', (cid, eid, j(data)))

    # settembre (mese chiuso, parametri v1) e ottobre (aperto, parametri v2)
    entry(C1, 'e1', ANNA1, '2026-09-01')
    entry(C1, 'e2', ANNA1, '2026-09-02', code='FE')
    entry(C1, 'e3', MARCO, '2026-09-01', slot='p', code='p', work_site='Sede esterna Napoli Est')
    entry(C1, 'e4', ANNA1, '2026-10-01')
    entry(C1, 'e5', ANNA1, '2026-10-02', layer='planned')
    entry(C1, 'e6', MARCO, '2026-10-03', slot='p', code='p', start='', end='', break_minutes=0, pause=None,
          work_site='Sede esterna da specificare', note='Importato da AB12 | Colore sede da verificare')
    entry(C1, 'e7', MARCO, '2026-10-04', updated_at='2026-10-04T08:00:00+00:00')
    entry(C1, 'e8', MARCO, '2026-10-04', start='08:00', end='14:00', updated_at='2026-10-04T09:00:00+00:00')  # doppia: vince questa
    entry(C2, 'e9', ANNA2, '2026-10-05')
    agreement = dict(agreements_fields(), version=2, source='Accordo confermato con la persona', updated_by='resp011', updated_at=STAMP)
    frozen = agreements_fields()
    con.execute('INSERT INTO periods VALUES(?,?,?)', (C1, '2026-09', j(dict(closed=True, verified=True, config=v1, version=1,
                note='Chiuso dopo i controlli', agreements={ANNA1: agreement, MARCO: frozen}))))
    con.execute('INSERT INTO periods VALUES(?,?,?)', (C1, '2026-10', j(dict(closed=False, verified=False, config=v2, version=2, note='',
                agreements={MARCO: dict(agreement, workforce_segments=[dict(id='seg1', cid=C1, pid=MARCO, effective_from='2026-10-01',
                                                                             effective_to='2026-10-31', version=1, data=agreements_fields())])}))))
    con.execute('INSERT INTO periods VALUES(?,?,?)', (C2, '2026-10', j(dict(closed=False, verified=True, config=v1, version=1, note='',
                agreements={}))))
    con.execute('INSERT INTO patients VALUES(?,?,?)', (C1, '2026-10-01|m', j(dict(id='2026-10-01|m', day='2026-10-01', slot='m', ordinary=10, isolated=1))))
    # fascicoli, modello di inserimento, documenti
    fields = {k: '' for k in hr.KEYS}
    fields.update(first_name='Anna', last_name='Prova', start_date='2026-09-01', company_email='anna@example.invalid')
    tasks = [dict(id='identita', phase='Prima dell’ingresso', label='Verifica documento', owner='HR', offset=-7, status='done', due='',
                  note='Fatto', completed_at=STAMP, completed_by='hr011'),
             dict(id='badge', phase='Primo giorno', label='Consegna badge', owner='Responsabile', offset=0, status='todo',
                  due='2026-09-01', note='', completed_at='', completed_by='')]
    con.execute('INSERT INTO hr_profiles VALUES(?,?,?,?)', (C1, ANNA1, 2, j(dict(fields=fields, custom={'badge_extra': 'B-12'},
                stage='active', tasks=tasks, updated_at=STAMP, updated_by='hr011'))))
    con.execute('INSERT INTO hr_history VALUES(?,?,?,?,?,?)', (C1, ANNA1, 1, STAMP, 'hr011', j(dict(fields=fields, tasks=tasks))))
    con.execute('INSERT INTO hr_history VALUES(?,?,?,?,?,?)', (C1, ANNA1, 2, STAMP, 'hr011', j(dict(fields=fields, tasks=tasks))))
    con.execute('INSERT INTO hr_settings VALUES(?,?,?)', (C1, 1, j(dict(tasks=[dict(id='identita', label='Verifica documento',
                phase='Prima dell’ingresso', owner='HR', offset=-7)], fields=[dict(id='badge_extra', label='Badge', type='text', required=False)]))))
    con.execute('INSERT INTO hr_documents VALUES(?,?,?,?,?,?,?,?,?,?)', ('doc1', C1, ANNA1, 'documento.pdf', 'Documento di identità',
                '2027-01-31', STAMP, 'hr011', hashlib.sha256(PDF).hexdigest(), PDF))
    con.execute('INSERT INTO hr_document_reviews VALUES(?,?,?,?,?,?)', ('doc1', 2, 'verified', 'Controllato', STAMP, 'hr011'))
    con.execute('INSERT INTO hr_document_review_history VALUES(?,?,?,?,?,?)', ('doc1', 1, 'received', '', STAMP, 'hr011'))
    con.execute('INSERT INTO hr_document_review_history VALUES(?,?,?,?,?,?)', ('doc1', 2, 'verified', 'Controllato', STAMP, 'hr011'))
    con.execute('INSERT INTO hr_documents VALUES(?,?,?,?,?,?,?,?,?,?)', ('doc2', C1, MARCO, 'foto.png', 'Altro', '', STAMP, 'hr011',
                'impronta-sbagliata', base64.b64encode(b'\x89PNG\r\n\x1a\n000').decode()))
    con.execute('INSERT INTO structure_profiles VALUES(?,?,?)', (C1, 2, j(dict(legal_name='Centro Uno S.r.l. (fittizio)', hr_email='hr@example.invalid'))))
    # personale di gruppo
    con.execute('INSERT INTO workforce_contracts VALUES(?,?,?,?,?,?,?)', ('k1', C1, ANNA1, '2026-09-01', '', 1, j(dict(role='INF',
                contract_type='Tempo indeterminato', ccnl='Esempio', level='C', weekly_hours=36, part_time_percent=100, note=''))))
    con.execute('INSERT INTO workforce_economics VALUES(?,?,?,?,?,?,?)', ('x1', C1, MARCO, '2026-10-01', '', 1, j(agreements_fields())))
    con.execute('INSERT INTO workforce_history(cid,pid,kind,record_id,stamp,actor,reason,before_data,after_data) VALUES(?,?,?,?,?,?,?,?,?)',
                (C1, ANNA1, 'contratto', 'k1', STAMP, 'hr011', 'Contratto registrato', 'null', j(dict(id='k1'))))
    con.execute('INSERT INTO workforce_history(cid,pid,kind,record_id,stamp,actor,reason,before_data,after_data) VALUES(?,?,?,?,?,?,?,?,?)',
                (C1, MARCO, 'applicazione al mese', '2026-10', STAMP, 'hr011', 'Applicato al mese', 'null', j({})))
    # approvazione: settembre approvato da HR nella prima struttura
    con.execute('INSERT INTO approval_policies VALUES(?,?,?,?,?,?)', (C1, 1, 1, 'Processo concordato', STAMP, 'admin011'))
    con.execute('INSERT INTO approval_months VALUES(?,?,?,?,?,?,?,?)', (C1, '2026-09', 3, 'hr_approved', 'impronta-0.11', 'Approvato', STAMP, 'hr011'))
    for version, action, status in ((1, 'submit', 'submitted'), (2, 'manager_approve', 'manager_approved'), (3, 'hr_approve', 'hr_approved')):
        con.execute('INSERT INTO approval_history VALUES(?,?,?,?,?,?,?,?,?)', (C1, '2026-09', version, action, status, '', 'impronta-0.11', STAMP, 'hr011'))
    # copertura, uscite, paghe
    con.execute('INSERT INTO staffing_requirements VALUES(?,?,?)', (C1, 1, j(dict(weekly=[dict(weekday=0, slot='m', role='INF', minimum=1)], overrides=[]))))
    con.execute('INSERT INTO staffing_availability VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('av1', C1, MARCO, '2026-10-20', '2026-10-21', 'unavailable', 'Ferie', 1, 1, STAMP, 'hr011'))
    con.execute('INSERT INTO staffing_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', ('sp1', C2, ANNA2, C1, ANNA1, '2026-10-12', 'p', 'p',
                'Copertura concordata', 'pending', 1, 'impronta-0.11', STAMP, 'hr011', '', '', '', ''))
    case = dict(id='dc1', cid=C1, pid=LUCA, version=1, status='open', kind='termination', destination_cid='', effective_date='2026-11-30',
                reason='Cessazione concordata', responsible='Responsabile', tasks=[dict(id='badge', label='Restituzione badge', required=True,
                status='todo', owner='Responsabile', due='2026-11-30', note='')], created_at=STAMP, updated_at=STAMP, closure_note='')
    con.execute('INSERT INTO departure_cases VALUES(?,?,?,?,?,?)', ('dc1', C1, LUCA, 1, 'open', j(case)))
    asset = dict(id='eq1', kind='keys', inventory_code='CHIAVE 7', label='Chiave armadietto', delivery_date='2026-09-01', due_date='',
                 note='', return_date='', return_condition='', return_note='', created_at=STAMP, updated_at=STAMP)
    con.execute('INSERT INTO equipment_assignments VALUES(?,?,?,?,?,?,?)', ('eq1', C1, LUCA, 1, 'chiave 7', 'assigned', j(asset)))
    con.execute('INSERT INTO departure_history(cid,kind,object_id,version,stamp,actor,action,data) VALUES(?,?,?,?,?,?,?,?)',
                (C1, 'case', 'dc1', 1, STAMP, 'resp011', 'Percorso di uscita aperto', j(case)))
    con.execute('INSERT INTO departure_history(cid,kind,object_id,version,stamp,actor,action,data) VALUES(?,?,?,?,?,?,?,?)',
                (C1, 'asset', 'eq1', 1, STAMP, 'resp011', 'Dotazione consegnata', j(asset)))
    template = dict(name='Tracciato 011', status='draft', confirmation_note='', delimiter=';', decimal_separator=',',
                    columns=[dict(field=f, label=f) for f in ('template_version', 'center_code', 'registration', 'day', 'payroll_code')],
                    causes={'m': 'ORD'}, registrations={MARCO: 'PAGHE-2'}, connector=dict(mode='generic', provider='', format_name='',
                    format_version='', specification_reference='', expected_columns=[], date_format='YYYY-MM-DD', encoding='utf-8-sig'))
    con.execute('INSERT INTO payroll_templates VALUES(?,?,?,?,?)', (C1, 1, j(template), STAMP, 'hr011'))
    # posta e promemoria ATTIVI nella 0.11: devono arrivare spenti
    con.execute('INSERT INTO communication_settings VALUES(?,?,?)', (1, 2, j(dict(enabled=True, host='smtp.example.invalid', port=465,
                security='ssl', username='', from_email='hr@example.invalid', from_name='HR', reply_to='', batch_size=20, max_per_hour=100))))
    con.execute('INSERT INTO communication_templates VALUES(?,?,?)', ('seed-benvenuto', 1, j(dict(name='Benvenuto', subject='Ciao {{nome}}', body='Benvenuto {{nome}}'))))
    con.execute('INSERT INTO communication_lists VALUES(?,?,?)', ('l1', 1, j(dict(name='Tutti', cids=[], roles=[], stages=[], email_field='company_email',
                recipient_type='employees', structure_field='email', exclude_emails=[]))))
    con.execute('INSERT INTO communication_campaigns VALUES(?,?,?,?)', ('cp1', STAMP, 'hr011', j(dict(name='Benvenuto', subject='Ciao', body='Testo',
                template_id='seed-benvenuto', list_id='l1', fingerprint='x', warnings=[]))))
    con.execute('INSERT INTO communication_recipients VALUES(?,?,?,?,?,?,?,?)', ('r1', 'cp1', 0, j(dict(cid=C1, pid=ANNA1, name='Anna Prova',
                email='anna@example.invalid', subject='Ciao', body='Testo')), 'accepted', '', None, ''))
    con.execute('INSERT INTO communication_recipients VALUES(?,?,?,?,?,?,?,?)', ('r2', 'cp1', 1, j(dict(cid=C1, pid=MARCO, name='Marco Prova',
                email='marco@example.invalid', subject='Ciao', body='Testo')), 'sending', '', now - 100, 'lotto'))
    con.execute('INSERT INTO communication_attempts VALUES(?,?,?,?,?,?,?,?,?)', ('t1', 'r1', 1, 'accepted', STAMP, now - 200, STAMP, '', '<t1@example.invalid>'))
    con.execute('INSERT INTO reminder_settings VALUES(?,?,?,?)', (1, 4, j(dict(enabled=True, centers=[], topics=['document'], offsets=[30, 0],
                recipient_mode='structure_hr', central_hr_email='', hour=8, max_daily_messages=20, max_overdue_days=30,
                approved_routes={C1: ['hr@example.invalid']})), 'u1'))
    con.execute('INSERT INTO reminder_runs VALUES(?,?,?,?,?,?)', ('run1', STAMP, 'completato', 0, 0, ''))
    con.execute('INSERT INTO audit(cid,stamp,username,action,before_data,after_data) VALUES(?,?,?,?,?,?)', (C1, STAMP, 'admin011', 'Configurazione iniziale', 'null', j({})))
    con.execute('INSERT INTO imports VALUES(?,?,?)', ('9' * 64, C1, '2026-08'))
    con.commit()
    con.close()


def agreements_fields():
    return dict(model='turns', basis='all', theoretical_mode='calendar', theoretical_units=0, hours_per_day=6, weekday_rate=50,
                holiday_rate=70, fixed_deduction=0, fixed_amount=0, adjustment=0, ccnl_rate=0, ccnl_count=0,
                counted_absences=['FE'], include_external=True, confirmed=True)
