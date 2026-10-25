"""Fascicoli del personale, inserimento dei nuovi assunti, documenti e scadenze.

Il fascicolo appartiene alla scheda della persona nella sua struttura. Gli allegati
sono conservati nell'archivio (non in cartelle condivise), con impronta SHA-256,
e si aprono solo dopo un nuovo controllo dei permessi. Ogni salvataggio crea una
versione nello storico del fascicolo.
"""
import hashlib
import re
from datetime import date, timedelta

from . import approvals, audit, centers, months, people, reviews, structures, users
from .errors import Conflict, Invalid, NotFound, TooLarge
from .permissions import has, require
from .util import dumps, loads, new_id, stamp, today
from . import validate as v
from .web import DOCUMENT_CSP, Reply

MAX_DOCUMENT = 6 * 1024 * 1024
MAX_DOCUMENTS_PER_PERSON = 200
STAGES = {'incoming': 'In ingresso', 'active': 'In servizio', 'ended': 'Cessato'}
TASK_STATES = {'todo': 'Da fare', 'doing': 'In corso', 'done': 'Completata', 'na': 'Non applicabile'}
SECTIONS = {'anagrafica': 'Anagrafica', 'recapiti': 'Recapiti', 'contratto': 'Contratto',
            'amministrazione': 'Amministrazione', 'qualifiche': 'Qualifiche e scadenze'}
DOCUMENT_TYPES = {'pdf': ('application/pdf', b'%PDF-'), 'png': ('image/png', b'\x89PNG\r\n\x1a\n'),
                  'jpg': ('image/jpeg', b'\xff\xd8\xff'), 'jpeg': ('image/jpeg', b'\xff\xd8\xff')}
CATEGORIES = ['Documento di identità', 'Contratto', 'Titolo di studio', 'Abilitazione professionale', 'Permesso di soggiorno',
              'Idoneità sanitaria', 'Formazione sicurezza', 'Privacy', 'Documento amministrativo', 'Altro']

# chiave, etichetta, sezione, lunghezza massima, tipo
FIELDS = [
    ('first_name', 'Nome', 'anagrafica', 80, 'text'), ('last_name', 'Cognome', 'anagrafica', 80, 'text'),
    ('tax_code', 'Codice fiscale', 'anagrafica', 16, 'text'), ('birth_date', 'Data di nascita', 'anagrafica', 10, 'date'),
    ('birth_place', 'Luogo di nascita', 'anagrafica', 150, 'text'), ('birth_province', 'Provincia di nascita', 'anagrafica', 60, 'text'),
    ('nationality', 'Cittadinanza', 'anagrafica', 80, 'text'),
    ('identity_type', 'Tipo di documento di identità', 'anagrafica', 80, 'text'),
    ('identity_number', 'Numero del documento', 'anagrafica', 80, 'text'),
    ('identity_issuer', 'Ente di rilascio', 'anagrafica', 150, 'text'),
    ('identity_issued_date', 'Data di rilascio', 'anagrafica', 10, 'date'),
    ('identity_expiry', 'Scadenza del documento', 'anagrafica', 10, 'date'),
    ('address', 'Indirizzo di residenza', 'recapiti', 250, 'text'), ('postal_code', 'CAP', 'recapiti', 20, 'text'),
    ('city', 'Comune', 'recapiti', 100, 'text'), ('province', 'Provincia', 'recapiti', 60, 'text'),
    ('country', 'Paese', 'recapiti', 80, 'text'), ('domicile', 'Domicilio, se diverso', 'recapiti', 300, 'text'),
    ('email', 'Email personale', 'recapiti', 200, 'email'), ('phone', 'Telefono', 'recapiti', 60, 'tel'),
    ('pec', 'PEC, se pertinente', 'recapiti', 200, 'email'), ('company_email', 'Email aziendale', 'recapiti', 200, 'email'),
    ('emergency_name', 'Contatto di emergenza (facoltativo)', 'recapiti', 150, 'text'),
    ('emergency_phone', 'Telefono di emergenza (facoltativo)', 'recapiti', 60, 'tel'),
    ('employer', 'Società datrice di lavoro', 'contratto', 200, 'text'),
    ('department', 'Reparto o servizio', 'contratto', 150, 'text'), ('manager', 'Responsabile diretto', 'contratto', 150, 'text'),
    ('contract_type', 'Tipologia di contratto', 'contratto', 100, 'text'), ('ccnl', 'CCNL applicato', 'contratto', 150, 'text'),
    ('level', 'Livello di inquadramento', 'contratto', 80, 'text'), ('qualification', 'Mansione o qualifica', 'contratto', 150, 'text'),
    ('contract_number', 'Riferimento del contratto', 'contratto', 80, 'text'),
    ('start_date', 'Data di ingresso', 'contratto', 10, 'date'), ('end_date', 'Scadenza del contratto', 'contratto', 10, 'date'),
    ('probation_end', 'Fine del periodo di prova', 'contratto', 10, 'date'),
    ('weekly_hours', 'Ore settimanali', 'contratto', 10, 'decimal'),
    ('part_time_percent', 'Percentuale di part-time', 'contratto', 10, 'decimal'),
    ('cost_center', 'Centro di costo', 'contratto', 100, 'text'),
    ('workplace', 'Sede di lavoro contrattuale', 'contratto', 150, 'text'),
    ('badge_number', 'Numero badge', 'contratto', 80, 'text'), ('tutor', 'Tutor di inserimento', 'contratto', 150, 'text'),
    ('iban', 'IBAN (se serve per il pagamento)', 'amministrazione', 34, 'iban'),
    ('account_holder', 'Intestatario del conto', 'amministrazione', 150, 'text'),
    ('bank_name', 'Banca', 'amministrazione', 150, 'text'),
    ('payment_method', 'Modalità di pagamento', 'amministrazione', 80, 'text'),
    ('vat_number', 'Partita IVA, se pertinente', 'amministrazione', 30, 'text'),
    ('payroll_contact', 'Referente paghe', 'amministrazione', 200, 'text'),
    ('professional_register', 'Ordine o albo professionale', 'qualifiche', 200, 'text'),
    ('register_number', 'Numero di iscrizione', 'qualifiche', 100, 'text'),
    ('registration_expiry', 'Scadenza dell’abilitazione, se prevista', 'qualifiche', 10, 'date'),
    ('work_permit_expiry', 'Scadenza del titolo di soggiorno o lavoro', 'qualifiche', 10, 'date'),
    ('next_review', 'Prossima verifica amministrativa', 'qualifiche', 10, 'date'),
    ('notes', 'Note amministrative', 'qualifiche', 2000, 'textarea'),
]
KEYS = [f[0] for f in FIELDS]
TYPES = {f[0]: f[4] for f in FIELDS}
DEADLINE_FIELDS = [('identity_expiry', 'Documento di identità', 'anagrafica'), ('end_date', 'Fine del contratto', 'contratto'),
                   ('probation_end', 'Fine del periodo di prova', 'contratto'),
                   ('registration_expiry', 'Iscrizione o abilitazione', 'qualifiche'),
                   ('work_permit_expiry', 'Titolo di soggiorno o lavoro', 'qualifiche'),
                   ('next_review', 'Verifica amministrativa', 'qualifiche')]

# codice, fase, attività, referente, giorni rispetto all'ingresso
DEFAULT_TASKS = [
    ('identita', 'Prima dell’ingresso', 'Verifica dati anagrafici e documento', 'Amministrazione', -7),
    ('contratto', 'Prima dell’ingresso', 'Contratto e informazioni sul rapporto consegnati', 'Consulente del lavoro', -1),
    ('co', 'Prima dell’ingresso', 'Verifica comunicazione obbligatoria e ricevuta, se dovuta', 'Consulente del lavoro', -1),
    ('paghe', 'Prima dell’ingresso', 'Dati paghe, modalità di pagamento e modulistica fiscale/TFR', 'Amministrazione', -1),
    ('titoli', 'Prima dell’ingresso', 'Verifica titoli, abilitazioni e iscrizione all’albo, se pertinenti', 'Responsabile della struttura', -1),
    ('permesso', 'Prima dell’ingresso', 'Verifica titolo di soggiorno/lavoro, se necessario', 'Amministrazione', -1),
    ('medico', 'Prima dell’ingresso', 'Verifica adempimenti con il medico competente, se applicabili', 'Responsabile sicurezza', -1),
    ('sicurezza', 'Primo giorno', 'Verifica formazione, informazione e addestramento previsti per la mansione', 'Responsabile sicurezza', 0),
    ('privacy', 'Primo giorno', 'Informativa dipendenti e istruzioni sul trattamento dei dati', 'Amministrazione', 0),
    ('accessi', 'Primo giorno', 'Account nominativi, permessi e istruzioni di sicurezza', 'IT', 0),
    ('badge', 'Primo giorno', 'Consegna badge, chiavi, dotazioni e DPI previsti', 'Responsabile della struttura', 0),
    ('turni', 'Primo giorno', 'Orari, sede, tutor e modalità di registrazione presenze', 'Responsabile della struttura', 0),
    ('procedure', 'Inserimento', 'Affiancamento e procedure della struttura', 'Tutor', 7),
    ('feedback', 'Inserimento', 'Colloquio di inserimento e verifica attività aperte', 'Responsabile della struttura', 30),
]
CUSTOM_TYPES = ('text', 'date', 'number', 'boolean')
CODE = re.compile(r'[A-Za-z0-9_-]{1,40}')


def field_definitions():
    return [dict(key=k, label=l, section=s, max_length=n, type=t) for k, l, s, n, t in FIELDS]


# --- Modello di inserimento ------------------------------------------------------------------

def template(con, center_id):
    found = con.execute('SELECT * FROM onboarding_templates WHERE center_id=?', (center_id,)).fetchone()
    if not found:
        return dict(version=0, tasks=[dict(id=i, phase=p, label=l, owner=o, offset=d) for i, p, l, o, d in DEFAULT_TASKS],
                    fields=[])
    return dict(version=found['version'], tasks=loads(found['tasks']), fields=loads(found['fields']),
                updated_at=found['updated_at'], updated_by=found['updated_by'])


def validate_template(raw):
    v.keys(raw, {'tasks', 'fields', 'version'}, 'Modello di inserimento', required={'tasks', 'fields', 'version'})
    tasks, fields = raw['tasks'], raw['fields']
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 80:
        raise Invalid('Modello: da 1 a 80 attività.', field='tasks')
    if not isinstance(fields, list) or len(fields) > 40:
        raise Invalid('Modello: al massimo 40 campi aggiuntivi.', field='fields')
    out_tasks, out_fields = [], []
    for t in tasks:
        v.keys(t, {'id', 'phase', 'label', 'owner', 'offset'}, 'Attività del modello', required={'id', 'label', 'phase'})
        if not isinstance(t['id'], str) or not CODE.fullmatch(t['id']):
            raise Invalid('Attività: codice di 1–40 lettere, numeri, trattino o trattino basso.', field='tasks')
        out_tasks.append(dict(id=t['id'], phase=v.text(t['phase'], 'Fase', 80, required=True, field='tasks'),
                              label=v.text(t['label'], 'Attività', 200, required=True, field='tasks'),
                              owner=v.text(t.get('owner', ''), 'Referente', 150, field='tasks'),
                              offset=v.integer(t.get('offset', 0), 'Giorni rispetto all’ingresso', -365, 730, field='tasks')))
    for f in fields:
        v.keys(f, {'id', 'label', 'type', 'required'}, 'Campo aggiuntivo', required={'id', 'label', 'type'})
        if not isinstance(f['id'], str) or not CODE.fullmatch(f['id']):
            raise Invalid('Campo aggiuntivo: codice di 1–40 lettere, numeri, trattino o trattino basso.', field='fields')
        out_fields.append(dict(id=f['id'], label=v.text(f['label'], 'Etichetta', 100, required=True, field='fields'),
                               type=v.choice(f['type'], 'Tipo di campo', CUSTOM_TYPES, field='fields'),
                               required=v.boolean(f.get('required', False), 'Obbligatorio', field='fields')))
    if len({t['id'] for t in out_tasks}) != len(out_tasks) or len({f['id'] for f in out_fields}) != len(out_fields):
        raise Invalid('Codici ripetuti nel modello.')
    return out_tasks, out_fields


def save_template(db, actor, center_id, raw):
    tasks, fields = validate_template(raw)
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.modello')
        old = template(con, center_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Modello modificato da un’altra sessione: ricaricare.')
        con.execute('''INSERT INTO onboarding_templates(center_id,tasks,fields,version,updated_at,updated_by) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(center_id) DO UPDATE SET tasks=excluded.tasks, fields=excluded.fields,
                       version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (center_id, dumps(tasks), dumps(fields), old['version'] + 1, stamp(), actor.username))
        audit.record(con, actor, 'Modello di inserimento aggiornato', center_id, entity='template', entity_id=center_id,
                     after=dict(version=old['version'] + 1, tasks=len(tasks), fields=len(fields)))
    return dict(version=old['version'] + 1)


# --- Fascicolo ---------------------------------------------------------------------------------

def profile(con, person_id):
    found = con.execute('SELECT * FROM profiles WHERE person_id=?', (person_id,)).fetchone()
    fields = {k: '' for k in KEYS}
    if not found:
        return dict(version=0, stage='incoming', fields=fields, custom={}, updated_at='', updated_by='')
    fields.update(loads(found['fields']))
    return dict(version=found['version'], stage=found['stage'], fields=fields, custom=loads(found['custom']),
                updated_at=found['updated_at'], updated_by=found['updated_by'])


def tasks_of(con, person_id):
    return [dict(id=r['task_id'], phase=r['phase'], label=r['label'], owner=r['owner'], due=r['due'], status=r['status'],
                 status_label=TASK_STATES[r['status']], note=r['note'], done_at=r['done_at'], done_by=r['done_by'])
            for r in con.execute('SELECT * FROM onboarding_tasks WHERE person_id=? ORDER BY position', (person_id,))]


def progress(tasks, on=None):
    on = on or today().isoformat()
    return dict(done=sum(t['status'] in ('done', 'na') for t in tasks), total=len(tasks),
                overdue=sum(t['status'] not in ('done', 'na') and bool(t['due']) and t['due'] < on for t in tasks))


def documents_meta(con, person_id):
    rows = []
    for r in con.execute('''SELECT id,center_id,person_id,name,category,expiry,mime,size,sha256,uploaded_at,uploaded_by
                            FROM documents WHERE person_id=? ORDER BY uploaded_at DESC, id''', (person_id,)):
        doc = dict(r)
        doc['review'] = reviews.current(con, doc)
        rows.append(doc)
    return rows


def deadlines(person, prof, tasks, documents, on=None):
    on = on or today().isoformat()
    out = []

    def add(label, when, section, kind):
        if when:
            out.append(dict(person_id=person['id'], name=person['name'], label=label, date=when, late=when < on,
                            section=section, kind=kind))

    for key, label, section in DEADLINE_FIELDS:
        add(label, prof['fields'].get(key, ''), section, 'fascicolo')
    for t in tasks:
        if t['status'] not in ('done', 'na'):
            add(t['label'], t['due'], 'onboarding', 'attività')
    for d in documents:
        add(f'{d["category"]} · {d["name"]}', d['expiry'], 'documenti', 'documento')
    return sorted(out, key=lambda d: d['date'])


def _decimal(value, label, maximum, field):
    if value and (not re.fullmatch(r'\d+(?:[.,]\d{1,2})?', value) or not 0 < float(value.replace(',', '.')) <= maximum):
        raise Invalid(f'{label}: valore non valido.', field=field)


def iban_ok(value):
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', value):
        return False
    digits = ''.join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in value[4:] + value[:4])
    return int(digits) % 97 == 1


def validate_fields(raw):
    v.keys(raw, set(KEYS), 'Fascicolo')
    out = {}
    for key, label, _, limit, kind in FIELDS:
        value = v.text(raw.get(key, ''), label, limit, multiline=kind == 'textarea', field=key)
        if kind == 'date':
            value = v.day(value, label, required=False, field=key)
        elif kind == 'email' and value and not v.is_email(value):
            raise Invalid(f'{label}: indirizzo email non valido.', field=key)
        out[key] = value
    today_iso = today().isoformat()
    if out['birth_date'] and out['birth_date'] >= today_iso:
        raise Invalid('Data di nascita non valida.', field='birth_date')
    if out['end_date'] and out['start_date'] and out['end_date'] < out['start_date']:
        raise Invalid('La scadenza del contratto precede la data di ingresso.', field='end_date')
    if out['probation_end'] and out['start_date'] and out['probation_end'] < out['start_date']:
        raise Invalid('La fine del periodo di prova precede la data di ingresso.', field='probation_end')
    if out['identity_expiry'] and out['identity_issued_date'] and out['identity_expiry'] < out['identity_issued_date']:
        raise Invalid('La scadenza del documento precede la data di rilascio.', field='identity_expiry')
    _decimal(out['weekly_hours'], 'Ore settimanali', 168, 'weekly_hours')
    _decimal(out['part_time_percent'], 'Percentuale di part-time', 100, 'part_time_percent')
    out['tax_code'] = out['tax_code'].upper().replace(' ', '')
    if out['tax_code'] and not (re.fullmatch(r'[A-Z0-9]{16}', out['tax_code']) or re.fullmatch(r'\d{11}', out['tax_code'])):
        raise Invalid('Formato del codice fiscale non valido (la verifica anagrafica resta manuale).', field='tax_code')
    out['iban'] = re.sub(r'\s', '', out['iban']).upper()
    if out['iban'] and not iban_ok(out['iban']):
        raise Invalid('IBAN non valido: controllare le cifre.', field='iban')
    return out


def validate_custom(raw, definitions, previous):
    if not isinstance(raw, dict) or len(raw) > 80:
        raise Invalid('Campi aggiuntivi non validi.', field='custom')
    values = dict(previous)  # i valori di campi ritirati restano nel fascicolo
    for d in definitions:
        value = v.text(raw.get(d['id'], ''), d['label'], 500, field='custom_' + d['id'])
        if d['type'] == 'date':
            value = v.day(value, d['label'], required=False, field='custom_' + d['id'])
        elif d['type'] == 'number' and value and not re.fullmatch(r'-?\d+(?:[.,]\d{1,3})?', value):
            raise Invalid(f'{d["label"]}: numero non valido.', field='custom_' + d['id'])
        elif d['type'] == 'boolean' and value not in ('', 'si', 'no'):
            raise Invalid(f'{d["label"]}: scegliere sì o no.', field='custom_' + d['id'])
        values[d['id']] = value
    return values


def missing_required(prof, definitions):
    return [d['label'] for d in definitions if d['required'] and not prof['custom'].get(d['id'])]


def listing(db, user, center_id):
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'hr.fascicoli')
        tpl = template(con, center_id)
        on = today().isoformat()
        soon = (today() + timedelta(days=30)).isoformat()
        rows, upcoming = [], []
        for p in months.people(con, center_id):
            prof = profile(con, p['id'])
            tasks = tasks_of(con, p['id'])
            docs = documents_meta(con, p['id'])
            rows.append(dict(id=p['id'], name=p['name'], role=p['role'], registration=p['registration'], active=p['active'],
                             stage=prof['stage'], stage_label=STAGES[prof['stage']], department=prof['fields']['department'],
                             start=prof['fields']['start_date'], version=prof['version'], documents=len(docs),
                             to_review=sum(d['review']['status'] != 'verified' for d in docs), **progress(tasks, on)))
            if p['active'] and prof['stage'] != 'ended':
                upcoming.extend(d for d in deadlines(p, prof, tasks, docs, on) if d['date'] <= soon)
    return dict(center=dict(id=center['id'], name=center['name']), employees=rows,
                deadlines=sorted(upcoming, key=lambda d: d['date']), template=tpl, stages=STAGES)


def read(db, user, center_id, person_id):
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'hr.fascicoli')
        person = people.get(con, center_id, person_id)
        prof = profile(con, person_id)
        if not prof['version'] and not prof['fields']['contract_type']:
            prof['fields']['contract_type'] = person['contract']
        tasks = tasks_of(con, person_id)
        docs = documents_meta(con, person_id)
        tpl = template(con, center_id)
        history = [dict(version=r['version'], at=r['at'], actor=r['actor']) for r in con.execute(
            'SELECT version,at,actor FROM profile_history WHERE person_id=? ORDER BY version DESC LIMIT 50', (person_id,))]
        roles = centers.config(con, center_id)['roles']
        return dict(center=dict(id=center['id'], name=center['name']), person=people.public(person, user), profile=prof,
                    tasks=tasks, progress=progress(tasks), documents=docs, deadlines=deadlines(person, prof, tasks, docs),
                    template=tpl, missing=missing_required(prof, tpl['fields']), history=history, roles=roles,
                    structure=structures.record(con, center_id), categories=CATEGORIES,
                    can_review=has(user, 'documenti.verifica'))


def save(db, actor, center_id, raw, person_id=None):
    v.keys(raw, {'name', 'role', 'registration', 'active', 'stage', 'fields', 'custom', 'version', 'person_version'},
           'Fascicolo', required={'name', 'role', 'fields', 'version'})
    fields = validate_fields(raw['fields'])
    name = v.text(raw['name'], 'Nome e cognome', 150, required=True, field='name')
    registration = v.text(raw.get('registration', ''), 'Matricola', 80, field='registration')
    active = v.boolean(raw.get('active', True), 'Abilitato alle presenze', field='active')
    stage = v.choice(raw.get('stage', 'incoming'), 'Stato', STAGES, field='stage')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        cfg = centers.config(con, center_id)
        role = v.choice(raw['role'], 'Ruolo', cfg['roles'], field='role')
        tpl = template(con, center_id)
        old_person = people.get(con, center_id, person_id) if person_id else None
        before = profile(con, person_id) if person_id else profile(con, '')
        if v.version(raw['version']) != before['version']:
            raise Conflict('Fascicolo aggiornato da un’altra sessione: ricaricare.')
        if old_person and raw.get('person_version') is not None and v.version(raw['person_version']) != old_person['version']:
            raise Conflict('Scheda della persona modificata da un’altra sessione: ricaricare.')
        if fields['tax_code']:
            for r in con.execute('SELECT pr.person_id, pr.fields FROM profiles pr JOIN people p ON p.id=pr.person_id '
                                 'WHERE p.center_id=? AND pr.person_id<>?', (center_id, person_id or '')):
                if loads(r['fields']).get('tax_code') == fields['tax_code']:
                    raise Invalid('Codice fiscale già presente in un altro fascicolo della struttura.', field='tax_code')
        people.unique_registration(con, center_id, registration, person_id)
        register = dict(name=name, role=role, registration=registration, active=active, contract=fields['contract_type'])
        if old_person is None:
            approvals.guard_reference_change(con, center_id)
            person_id = people.insert(con, actor, center_id, register)
        else:
            changed = {k: val for k, val in register.items() if old_person[k] != val}
            if changed:
                approvals.guard_reference_change(con, center_id)
                people.write(con, person_id, changed)
        custom = validate_custom(raw.get('custom', {}), tpl['fields'], before['custom'])
        version = before['version'] + 1
        con.execute('''INSERT INTO profiles(person_id,stage,fields,custom,version,updated_at,updated_by) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(person_id) DO UPDATE SET stage=excluded.stage, fields=excluded.fields, custom=excluded.custom,
                       version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (person_id, stage, dumps(fields), dumps(custom), version, stamp(), actor.username))
        if before['version'] == 0 and not con.execute('SELECT 1 FROM onboarding_tasks WHERE person_id=?', (person_id,)).fetchone():
            start = fields['start_date']
            for position, t in enumerate(tpl['tasks']):
                due = (date.fromisoformat(start) + timedelta(days=t['offset'])).isoformat() if start else ''
                con.execute('''INSERT INTO onboarding_tasks(person_id,task_id,position,phase,label,owner,due,status)
                               VALUES(?,?,?,?,?,?,?,'todo')''', (person_id, t['id'], position, t['phase'], t['label'], t['owner'], due))
        _history(con, actor, person_id, version)
        changed_fields = [k for k in KEYS if before['fields'].get(k, '') != fields[k]]
        audit.record(con, actor, 'Fascicolo salvato', center_id, entity='profile', entity_id=person_id,
                     after=dict(version=version, stage=stage, fields_changed=changed_fields))
    return dict(person_id=person_id, version=version)


def _history(con, actor, person_id, version):
    snapshot = profile(con, person_id)
    snapshot['tasks'] = tasks_of(con, person_id)
    con.execute('INSERT INTO profile_history(person_id,version,at,actor,data) VALUES(?,?,?,?,?)',
                (person_id, version, stamp(), actor.username, dumps(snapshot)))


def save_task(db, actor, center_id, person_id, task_id, raw):
    v.keys(raw, {'status', 'due', 'owner', 'note', 'version'}, 'Attività', required={'status', 'version'})
    status = v.choice(raw['status'], 'Stato', TASK_STATES, field='status')
    note = v.text(raw.get('note', ''), 'Nota', 1000, multiline=True, field='note')
    if status == 'na' and not note:
        raise Invalid('Indicare perché l’attività non è applicabile.', field='note')
    due = v.day(raw.get('due', ''), 'Scadenza', required=False, field='due')
    owner = v.text(raw.get('owner', ''), 'Referente', 150, field='owner')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        people.get(con, center_id, person_id)
        prof = profile(con, person_id)
        if not prof['version'] or v.version(raw['version']) != prof['version']:
            raise Conflict('Fascicolo cambiato o non ancora salvato: ricaricare.')
        task = con.execute('SELECT * FROM onboarding_tasks WHERE person_id=? AND task_id=?', (person_id, task_id)).fetchone()
        if not task:
            raise NotFound('Attività non trovata.')
        closing = status in ('done', 'na')
        done_at, done_by = task['done_at'], task['done_by']
        if task['status'] != status:
            done_at, done_by = (stamp(), actor.username) if closing else ('', '')
        con.execute('UPDATE onboarding_tasks SET status=?, due=?, owner=?, note=?, done_at=?, done_by=? WHERE person_id=? AND task_id=?',
                    (status, due, owner, note, done_at, done_by, person_id, task_id))
        version = prof['version'] + 1
        con.execute('UPDATE profiles SET version=?, updated_at=?, updated_by=? WHERE person_id=?',
                    (version, stamp(), actor.username, person_id))
        _history(con, actor, person_id, version)
        audit.record(con, actor, 'Attività di inserimento aggiornata', center_id, entity='task', entity_id=f'{person_id}|{task_id}',
                     before=dict(status=task['status']), after=dict(status=status))
    return dict(version=version)


# --- Documenti -----------------------------------------------------------------------------------

def _safe_name(name):
    name = v.text(name, 'Nome del file', 180, required=True, field='name')
    if '/' in name or '\\' in name or name in ('.', '..') or name.startswith('.'):
        raise Invalid('Nome del file non valido.', field='name')
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in DOCUMENT_TYPES:
        raise Invalid('Caricare file PDF, PNG o JPEG (massimo 6 MiB).', field='name')
    return name, ext


def check_content(data, ext):
    mime, magic = DOCUMENT_TYPES[ext]
    if not data:
        raise Invalid('File vuoto.')
    if len(data) > MAX_DOCUMENT:
        raise TooLarge('Documento troppo grande: massimo 6 MiB.')
    if not data.startswith(magic):
        raise Invalid('Il contenuto del file non corrisponde al formato dichiarato.')
    return mime


def add_document(db, actor, center_id, person_id, meta, data):
    name, ext = _safe_name(meta.get('name'))
    category = v.text(meta.get('category') or 'Documento amministrativo', 'Categoria', 100, required=True, field='category')
    expiry = v.day(meta.get('expiry', ''), 'Scadenza', required=False, field='expiry')
    with db.read() as con:  # permesso verificato prima di esaminare il contenuto
        centers.scoped(con, actor, center_id, 'hr.fascicoli')
    mime = check_content(data, ext)
    sha = hashlib.sha256(data).hexdigest()
    doc_id = new_id()
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        people.get(con, center_id, person_id)
        if not profile(con, person_id)['version']:
            raise Invalid('Salvare il fascicolo prima di allegare documenti.')
        if con.execute('SELECT count(*) FROM documents WHERE person_id=?', (person_id,)).fetchone()[0] >= MAX_DOCUMENTS_PER_PERSON:
            raise Invalid('Raggiunto il limite di 200 documenti per persona.')
        con.execute('''INSERT INTO documents(id,center_id,person_id,name,category,expiry,mime,size,sha256,content,uploaded_at,uploaded_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (doc_id, center_id, person_id, name, category, expiry, mime, len(data), sha, data, stamp(), actor.username))
        reviews.registered(con, actor, doc_id)
        audit.record(con, actor, 'Documento allegato', center_id, entity='document', entity_id=doc_id,
                     after=dict(person_id=person_id, name=name, category=category, sha256=sha))
    return dict(id=doc_id, sha256=sha)


def _document(con, center_id, doc_id):
    found = con.execute('SELECT * FROM documents WHERE id=? AND center_id=?', (v.identifier(doc_id, 'Documento'), center_id)).fetchone()
    if not found:
        raise NotFound('Documento non trovato.')
    return found


def open_document(db, actor, center_id, doc_id, inline):
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        doc = _document(con, center_id, doc_id)
        data = bytes(doc['content'])
        if hashlib.sha256(data).hexdigest() != doc['sha256']:
            raise Invalid('Il documento non corrisponde all’impronta registrata: avvisare l’amministratore.')
        audit.record(con, actor, 'Documento visualizzato' if inline else 'Documento scaricato', center_id, entity='document',
                     entity_id=doc['id'], after=dict(person_id=doc['person_id'], sha256=doc['sha256']))
    headers = [('Content-Security-Policy', DOCUMENT_CSP)] if inline else []
    return Reply(data, content_type=doc['mime'], filename=doc['name'], inline=inline, headers=headers)


def delete_document(db, actor, center_id, doc_id, raw):
    v.keys(raw, {'reason'}, 'Rimozione', required={'reason'})
    reason = v.reason(raw['reason'], 'Motivo della rimozione')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        doc = _document(con, center_id, doc_id)
        con.execute('DELETE FROM documents WHERE id=?', (doc['id'],))
        audit.record(con, actor, 'Documento rimosso', center_id, entity='document', entity_id=doc['id'],
                     before=dict(person_id=doc['person_id'], name=doc['name'], sha256=doc['sha256']), after=dict(reason=reason))
    return dict(ok=True)


def archive(db, user, center_id='all', person='', category='', expiry='all', review='all'):
    """Archivio centrale dei documenti nelle strutture autorizzate, con filtri."""
    person = v.text(person, 'Persona', 150).casefold()
    category = v.text(category, 'Categoria', 100)
    expiry = v.choice(expiry, 'Filtro scadenza', ('all', 'expired', 'soon', 'dated', 'none'))
    review = v.choice(review, 'Filtro verifica', ('all', 'received', 'needs_correction', 'verified', 'expired'))
    on = today().isoformat()
    soon = (today() + timedelta(days=30)).isoformat()
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'hr.fascicoli')
        visible = centers.visible(con, user)
        if center_id != 'all':
            centers.scoped(con, user, center_id, 'hr.fascicoli')
            visible = [c for c in visible if c['id'] == center_id]
        rows, found_categories = [], set()
        for c in visible:
            names = {p['id']: p for p in months.people(con, c['id'])}
            for r in con.execute('''SELECT id,center_id,person_id,name,category,expiry,mime,size,sha256,uploaded_at,uploaded_by
                                    FROM documents WHERE center_id=? ORDER BY uploaded_at DESC, id''', (c['id'],)):
                doc = dict(r)
                doc['review'] = reviews.current(con, doc, on)
                found_categories.add(doc['category'])
                p = names.get(doc['person_id'])
                if not p:
                    continue
                if review == 'expired' and not doc['review']['expired']:
                    continue
                if review not in ('all', 'expired') and doc['review']['status'] != review:
                    continue
                if person and person not in f'{p["name"]} {p["registration"]}'.casefold():
                    continue
                if category and doc['category'] != category:
                    continue
                due = doc['expiry']
                if ((expiry == 'expired' and (not due or due >= on)) or (expiry == 'soon' and (not due or not on <= due <= soon))
                        or (expiry == 'dated' and not due) or (expiry == 'none' and due)):
                    continue
                doc.update(center=c['name'], center_code=c['code'], person=p['name'], registration=p['registration'],
                           late=bool(due and due < on))
                rows.append(doc)
    rows.sort(key=lambda d: (d['uploaded_at'], d['id']), reverse=True)
    return dict(centers=[dict(id=c['id'], name=c['name']) for c in visible] if center_id == 'all' else None,
                categories=sorted(found_categories | set(CATEGORIES), key=str.casefold), documents=rows, total=len(rows),
                can_review=has(user, 'documenti.verifica'))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/hr-fields', cap='hr.fascicoli')
def api_fields(ctx):
    return dict(fields=field_definitions(), sections=SECTIONS, categories=CATEGORIES, stages=STAGES)


@route('GET', '/api/hr/<cid>', cap='hr.fascicoli')
def api_listing(ctx):
    return listing(ctx.db, ctx.user, ctx.params['cid'])


@route('POST', '/api/hr/<cid>', cap='hr.fascicoli')
def api_create(ctx):
    return save(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('PUT', '/api/hr/<cid>/template', cap='hr.modello', step_up=True)
def api_template(ctx):
    return save_template(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/hr/<cid>/<pid>', cap='hr.fascicoli')
def api_read(ctx):
    return read(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'])


@route('PUT', '/api/hr/<cid>/<pid>', cap='hr.fascicoli')
def api_save(ctx):
    return save(ctx.db, ctx.user, ctx.params['cid'], ctx.body, ctx.params['pid'])


@route('PUT', '/api/hr/<cid>/<pid>/tasks/<task_id>', cap='hr.fascicoli')
def api_task(ctx):
    return save_task(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], ctx.params['task_id'], ctx.body)


@route('POST', '/api/hr/<cid>/<pid>/documents', cap='hr.fascicoli')
def api_upload(ctx):
    meta = dict(name=ctx.q('name'), category=ctx.q('category'), expiry=ctx.q('expiry'))
    return add_document(ctx.db, ctx.user, ctx.params['cid'], ctx.params['pid'], meta, ctx.req.raw(MAX_DOCUMENT))


@route('GET', '/api/documents', cap='hr.fascicoli')
def api_archive(ctx):
    return archive(ctx.db, ctx.user, ctx.q('cid', 'all') or 'all', ctx.q('person'), ctx.q('category'),
                   ctx.q('expiry', 'all') or 'all', ctx.q('review', 'all') or 'all')


@route('GET', '/api/documents/<cid>/<doc_id>/content', cap='hr.fascicoli')
def api_content(ctx):
    return open_document(ctx.db, ctx.user, ctx.params['cid'], ctx.params['doc_id'], ctx.q('download') != '1')


@route('DELETE', '/api/documents/<cid>/<doc_id>', cap='hr.fascicoli')
def api_delete(ctx):
    return delete_document(ctx.db, ctx.user, ctx.params['cid'], ctx.params['doc_id'], ctx.body)
