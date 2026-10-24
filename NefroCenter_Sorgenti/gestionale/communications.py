"""Comunicazioni HR: bozze verificabili, destinatari individuali e SMTP esplicito.

Nessun processo automatico invia email. La password SMTP vive esclusivamente
nell'ambiente del server. L'accettazione SMTP non equivale a consegna o lettura.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import formataddr, formatdate

import hr
import structures

PASSWORD_ENV = 'PRESENZE_SMTP_PASSWORD'
MAX_RECIPIENTS = 10000
SMTP_TIMEOUT = 15
STALE_BATCH_SECONDS = 900
STAGES = ['incoming', 'active', 'ended']
VARIABLES = {
    'nome': 'Nome completo / destinatario struttura',
    'nome_battesimo': 'Nome nel fascicolo', 'cognome': 'Cognome nel fascicolo',
    'matricola': 'Matricola', 'ruolo': 'Ruolo', 'data_ingresso': 'Data ingresso',
    'struttura': 'Nome struttura', 'codice_struttura': 'Codice struttura',
    'ragione_sociale': 'Ragione sociale struttura', 'email_hr': 'Email HR struttura',
    'email_struttura': 'Email generale struttura',
    'email_amministrazione': 'Email amministrazione struttura',
    'telefono_struttura': 'Telefono struttura', 'indirizzo_struttura': 'Indirizzo struttura',
    'referente_struttura': 'Referente struttura', 'email_destinatario': 'Email destinatario',
}
DEFAULT_SETTINGS = dict(enabled=False, host='', port=465, security='ssl', username='',
                        from_email='', from_name='NefroCenter HR', reply_to='',
                        batch_size=20, max_per_hour=100)
SEED_TEMPLATES = [
    ('benvenuto', 'Benvenuto', 'Benvenuto in {{struttura}}',
     'Gentile {{nome}},\n\nbenvenuto presso {{struttura}}. Ti invitiamo a concordare con il referente le attività di ingresso e a completare il fascicolo personale.\n\nUfficio HR'),
    ('documenti', 'Documenti da completare', 'Completamento documenti · {{struttura}}',
     'Gentile {{nome}},\n\nti chiediamo di verificare con l’ufficio HR i documenti da completare nel tuo fascicolo. Utilizza i canali aziendali previsti per la consegna.\n\nUfficio HR'),
    ('scadenze', 'Promemoria scadenze', 'Verifica scadenze · {{struttura}}',
     'Gentile {{nome}},\n\nti invitiamo a verificare con l’ufficio HR le scadenze relative al tuo rapporto con {{struttura}} e a concordare gli aggiornamenti necessari.\n\nUfficio HR'),
    ('presenze', 'Verifica presenze', 'Verifica presenze · {{struttura}}',
     'Gentile {{nome}},\n\nti chiediamo di verificare le presenze e di segnalare al referente eventuali correzioni prima della chiusura del periodo.\n\nUfficio HR'),
    ('sede', 'Comunicazione alla struttura', 'Comunicazione per {{struttura}}',
     'Alla cortese attenzione del referente di {{struttura}},\n\ninserire qui il testo della comunicazione prima di creare la bozza di invio.\n\nUfficio HR'),
]


def init(app):
    with app.connect() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS communication_templates(
                id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS communication_lists(
                id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS communication_settings(
                id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS communication_campaigns(
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
                data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS communication_recipients(
                id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES communication_campaigns(id),
                ordinal INTEGER NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT '', claimed_at REAL, batch_id TEXT NOT NULL DEFAULT '',
                UNIQUE(campaign_id,ordinal));
            CREATE TABLE IF NOT EXISTS communication_attempts(
                id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL REFERENCES communication_recipients(id),
                number INTEGER NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
                started_epoch REAL NOT NULL, finished_at TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '', message_id TEXT NOT NULL,
                UNIQUE(recipient_id,number));
            CREATE INDEX IF NOT EXISTS communication_recipient_campaign ON communication_recipients(campaign_id,status);
            CREATE INDEX IF NOT EXISTS communication_attempt_time ON communication_attempts(started_epoch);
        ''')
        for key, name, subject, body in SEED_TEMPLATES:
            c.execute('INSERT OR IGNORE INTO communication_templates VALUES(?,?,?)',
                      ('seed-' + key, 1, app.dump(dict(name=name, subject=subject, body=body))))
        c.commit()


def _access(app, c, user, admin=False):
    user = app.fresh_user(c, user)
    if user['role'] not in ('admin', 'hr') or (admin and user['role'] != 'admin'):
        raise PermissionError('Comunicazioni riservate all’ufficio HR centrale e all’amministratore.' if not admin
                              else 'Configurazione SMTP riservata all’amministratore.')
    return user


def _text(value, label, maximum, blank=False, multiline=False):
    allowed = '\n\r\t' if multiline else ''
    if (not isinstance(value, str) or len(value) > maximum
            or any((ord(ch) < 32 or ord(ch) == 127) and ch not in allowed for ch in value)):
        raise ValueError(label + ': testo non valido.')
    value = value.strip()
    if not blank and not value:
        raise ValueError(label + ': valore obbligatorio.')
    return value


def _email(value):
    """Validate one bare mailbox, normalize domains and deduplicate case-insensitively."""
    value = _text(value, 'Email', 254)
    if not structures._email(value):
        raise ValueError('Indirizzo email non valido.')
    local, domain = value.rsplit('@', 1)
    result = local + '@' + domain.encode('idna').decode('ascii').lower()
    if len(result) > 254:
        raise ValueError('Indirizzo email troppo lungo.')
    return result


def _content(raw):
    subject = _text(raw.get('subject'), 'Oggetto', 300)
    body = _text(raw.get('body'), 'Messaggio', 20000, multiline=True)
    for value in (subject, body):
        placeholders = re.findall(r'{{\s*([^{}]+?)\s*}}', value)
        unknown = set(placeholders) - set(VARIABLES)
        if unknown or '{{' in re.sub(r'{{\s*([^{}]+?)\s*}}', '', value) or '}}' in re.sub(r'{{\s*([^{}]+?)\s*}}', '', value):
            raise ValueError('Variabile non riconosciuta: usare soltanto quelle elencate nella guida.')
    return subject, body


def _get(c, table, key):
    row = c.execute('SELECT * FROM ' + table + ' WHERE id=?', (key,)).fetchone()
    if not row:
        raise ValueError('Modello o lista non trovato.')
    return dict(id=row['id'], version=row['version'], **json.loads(row['data']))


def _save(app, user, body, table, action, validate):
    if not isinstance(body, dict):
        raise ValueError('Dati non validi.')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user = _access(app, c, user)
        key = body.get('id')
        if key is not None and (not isinstance(key, str) or not key):
            raise ValueError('Identificativo non valido.')
        before = _get(c, table, key) if key else None
        version = before['version'] if before else 0
        if type(body.get('version')) is not int or body['version'] != version:
            raise ValueError('La versione è cambiata. Ricaricare prima di salvare.')
        data = validate(app, c, user, body)
        key = key or app.uid()
        c.execute('INSERT INTO ' + table + ' VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data',
                  (key, version + 1, app.dump(data)))
        app.audit(c, user, action, after={'id': key, 'version': version + 1, 'name': data['name']})
        c.commit()
        return {'id': key, 'version': version + 1, **data}


def save_template(app, user, body):
    def validate(app, c, user, raw):
        if set(raw) - {'id', 'version', 'name', 'subject', 'body'}:
            raise ValueError('Campi del modello non previsti.')
        subject, text = _content(raw)
        return dict(name=_text(raw.get('name'), 'Nome modello', 120), subject=subject, body=text)
    return _save(app, user, body, 'communication_templates', 'Modello email salvato', validate)


def _choices(raw, key, permitted=None, max_size=10000):
    values = raw.get(key, [])
    if not isinstance(values, list) or len(values) > max_size or any(not isinstance(x, str) for x in values):
        raise ValueError('Filtro ' + key + ' non valido.')
    values = sorted(set(values))
    if permitted is not None and set(values) - set(permitted):
        raise ValueError('Filtro ' + key + ': valore inesistente o non autorizzato.')
    return values


def save_list(app, user, body):
    def validate(app, c, user, raw):
        if set(raw) - {'id', 'version', 'name', 'cids', 'roles', 'stages', 'email_field', 'exclude_emails', 'recipient_type', 'structure_field'}:
            raise ValueError('Campi della lista non previsti.')
        centers = app.centers_for(c, user)
        cids = _choices(raw, 'cids', [x['id'] for x in centers])
        roles = set()
        for center in centers:
            roles.update(app.center(c, center['id'])['config']['roles'])
        values = dict(name=_text(raw.get('name'), 'Nome lista', 120), cids=cids,
                      roles=_choices(raw, 'roles', roles, 1000), stages=_choices(raw, 'stages', STAGES, 3),
                      email_field=raw.get('email_field', 'company_email'),
                      recipient_type=raw.get('recipient_type', 'employees'),
                      structure_field=raw.get('structure_field', 'email'))
        if values['email_field'] not in ('email', 'company_email') or values['recipient_type'] not in ('employees', 'structures') or values['structure_field'] not in ('email', 'hr_email', 'admin_email'):
            raise ValueError('Tipo destinatario o campo email non valido.')
        if values['recipient_type'] == 'structures' and (values['roles'] or values['stages']):
            raise ValueError('I filtri ruolo e stato si applicano solo ai dipendenti.')
        values['exclude_emails'] = sorted({_email(x).casefold() for x in _choices(raw, 'exclude_emails')})
        return values
    return _save(app, user, body, 'communication_lists', 'Lista email salvata', validate)


def _configuration(c):
    row = c.execute('SELECT * FROM communication_settings WHERE id=1').fetchone()
    return dict(version=row['version'] if row else 0,
                **(json.loads(row['data']) if row else DEFAULT_SETTINGS))


def _configured(config):
    return bool(config['host'] and config['from_email'] and
                (not config['username'] or os.environ.get(PASSWORD_ENV)))


def _settings(c, user):
    config = _configuration(c)
    if user['role'] == 'admin':
        return dict(**config, configured=_configured(config), password_configured=bool(os.environ.get(PASSWORD_ENV)))
    return dict(enabled=config['enabled'], configured=_configured(config), batch_size=config['batch_size'])


def save_configuration(app, user, body):
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user = _access(app, c, user, admin=True)
        old = _configuration(c)
        if not isinstance(body, dict) or set(body) != set(DEFAULT_SETTINGS) | {'version'}:
            raise ValueError('Configurazione incompleta o con campi non previsti. La password va impostata solo nell’ambiente del server.')
        if type(body['version']) is not int or body['version'] != old['version']:
            raise ValueError('Configurazione cambiata. Ricaricare prima di salvare.')
        cfg = {k: body[k] for k in DEFAULT_SETTINGS}
        if type(cfg['enabled']) is not bool or cfg['security'] not in ('ssl', 'starttls'):
            raise ValueError('Usare SSL/TLS oppure STARTTLS obbligatorio.')
        for key, minimum, maximum in [('port', 1, 65535), ('batch_size', 1, 20), ('max_per_hour', 1, 2000)]:
            if type(cfg[key]) is not int or not minimum <= cfg[key] <= maximum:
                raise ValueError(key + ': valore non valido.')
        for key in ('host', 'username', 'from_email', 'from_name', 'reply_to'):
            cfg[key] = _text(cfg[key], key, 254, blank=True)
        if cfg['host']:
            try:
                ipaddress.ip_address(cfg['host'])
            except ValueError:
                if len(cfg['host']) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p) for p in cfg['host'].split('.')):
                    raise ValueError('Host SMTP non valido: indicare il nome del server senza URL o porta.')
        for key in ('from_email', 'reply_to'):
            if cfg[key]:
                cfg[key] = _email(cfg[key])
        if cfg['enabled'] and not (cfg['host'] and cfg['from_email']):
            raise ValueError('Prima di abilitare SMTP specificare server e mittente.')
        c.execute('INSERT INTO communication_settings VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data',
                  (old['version'] + 1, app.dump(cfg)))
        app.audit(c, user, 'Configurazione email salvata', after={'version': old['version'] + 1, 'enabled': cfg['enabled']})
        c.commit()
        return _settings(c, user)


def _render(value, variables):
    missing = set()
    def replace(match):
        key = match.group(1).strip()
        item = variables.get(key, '')
        if not item:
            missing.add(key)
        return str(item)
    return re.sub(r'{{\s*([^{}]+?)\s*}}', replace, value), missing


def _preview(app, c, user, body):
    if not isinstance(body, dict):
        raise ValueError('Dati anteprima non validi.')
    template = _get(c, 'communication_templates', body.get('template_id'))
    mailing_list = _get(c, 'communication_lists', body.get('list_id'))
    subject, text = _content({'subject': body.get('subject', template['subject']), 'body': body.get('body', template['body'])})
    centers = app.centers_for(c, user)
    authorized = {ct['id'] for ct in centers}
    if set(mailing_list['cids']) - authorized:
        raise ValueError('La lista contiene una struttura non più disponibile: aggiornarla.')
    selected_centers = [ct for ct in centers if not mailing_list['cids'] or ct['id'] in mailing_list['cids']]
    recipients, warnings, seen = [], [], set()
    counts = dict(selected=0, valid=0, missing=0, invalid=0, duplicates=0, excluded=0)
    excluded = set(mailing_list['exclude_emails'])
    def warn(code, message, severity='warning'):
        warnings.append(dict(code=code, message=message, severity=severity))
    for center in selected_centers:
        structure = structures.record(c, center['id']); sf = structure['fields']
        base = dict(struttura=center['name'], codice_struttura=center['code'], ragione_sociale=sf['legal_name'],
                    email_hr=sf['hr_email'], email_struttura=sf['email'], email_amministrazione=sf['admin_email'],
                    telefono_struttura=sf['phone'], indirizzo_struttura=sf['address'], referente_struttura=sf['contact_name'])
        audience = []
        if mailing_list['recipient_type'] == 'structures':
            audience.append(dict(cid=center['id'], pid='', name=center['name'], email=sf[mailing_list['structure_field']],
                                 variables={**base, 'nome': sf['contact_name'] or center['name']}))
        else:
            for person in sorted(app.objects(c, 'people', center['id']), key=lambda x: (x['name'].casefold(), x['id'])):
                p = hr.profile(c, center['id'], person['id']); f = p['fields']
                # Existing people without an HR file use their explicit active flag.
                stage = p['stage'] if p['version'] else ('active' if person.get('active') else 'ended')
                if mailing_list['roles'] and person['role'] not in mailing_list['roles']:
                    continue
                if mailing_list['stages'] and stage not in mailing_list['stages']:
                    continue
                audience.append(dict(cid=center['id'], pid=person['id'], name=person['name'], email=f[mailing_list['email_field']],
                                     variables={**base, 'nome': person['name'], 'nome_battesimo': f['first_name'], 'cognome': f['last_name'],
                                                'matricola': person.get('registration', ''), 'ruolo': person['role'], 'data_ingresso': f['start_date']}))
        for row in audience:
            counts['selected'] += 1
            if counts['selected'] > MAX_RECIPIENTS:
                raise ValueError('Oltre 10.000 destinatari selezionati: restringere i filtri della lista.')
            description = row['name'] + ' · ' + center['name']
            if not row['email']:
                counts['missing'] += 1; warn('missing_email', description + ': email mancante; escluso.'); continue
            try:
                row['email'] = _email(row['email'])
            except ValueError:
                counts['invalid'] += 1; warn('invalid_email', description + ': email non valida; escluso.'); continue
            key = row['email'].casefold()
            if key in excluded:
                counts['excluded'] += 1; continue
            if key in seen:
                counts['duplicates'] += 1; warn('duplicate_email', description + ': indirizzo già presente; resta il primo destinatario mostrato.'); continue
            seen.add(key)
            variables = row.pop('variables'); variables['email_destinatario'] = row['email']
            row['subject'], missing_subject = _render(subject, variables)
            row['body'], missing_body = _render(text, variables)
            missing = missing_subject | missing_body
            if missing:
                warn('missing_variable', description + ': mancano i valori per ' + ', '.join(sorted(missing)) + '.', 'error')
            try:
                _text(row['subject'], 'Oggetto personalizzato', 2000)
                _text(row['body'], 'Messaggio personalizzato', 60000, multiline=True)
            except ValueError:
                warn('invalid_content', description + ': il contenuto personalizzato contiene dati non validi.', 'error')
            recipients.append(row)
    counts['valid'] = len(recipients)
    if not recipients:
        warn('empty_audience', 'Nessun destinatario valido nella lista.', 'error')
    snapshot = dict(template_id=template['id'], template_version=template['version'], list_id=mailing_list['id'],
                    list_version=mailing_list['version'], subject=subject, body=text, recipients=recipients, warnings=warnings,
                    counts=counts)
    fingerprint = hashlib.sha256(app.dump(snapshot).encode()).hexdigest()
    return dict(**snapshot, fingerprint=fingerprint, can_create=not any(w['severity'] == 'error' for w in warnings))


def preview(app, user, body):
    with app.connect() as c:
        c.execute('BEGIN'); user = _access(app, c, user)
        return _preview(app, c, user, body)


def create_campaign(app, user, body):
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user = _access(app, c, user)
        view = _preview(app, c, user, body)
        expected = body.get('fingerprint')
        if not isinstance(expected, str) or not hmac.compare_digest(expected, view['fingerprint']):
            raise ValueError('Destinatari o contenuti cambiati. Ripetere l’anteprima prima di creare la bozza.')
        if not view['can_create']:
            raise ValueError('Correggere gli errori dell’anteprima prima di creare la bozza.')
        campaign_id = app.uid()
        data = {k: v for k, v in view.items() if k not in ('recipients', 'can_create', 'counts')}
        data.update(name=body.get('name') or view['subject'])
        data['name'] = _text(data['name'], 'Nome campagna', 300)
        c.execute('INSERT INTO communication_campaigns VALUES(?,?,?,?)',
                  (campaign_id, app.now(), user['username'], app.dump(data)))
        for ordinal, recipient in enumerate(view['recipients']):
            c.execute('INSERT INTO communication_recipients(id,campaign_id,ordinal,data) VALUES(?,?,?,?)',
                      (app.uid(), campaign_id, ordinal, app.dump(recipient)))
        app.audit(c, user, 'Bozza email creata', after={'id': campaign_id, 'recipients': len(view['recipients']), 'fingerprint': view['fingerprint']})
        c.commit()
        return _campaign(app, c, user, campaign_id)


def _campaign(app, c, user, key, detail=True):
    row = c.execute('SELECT * FROM communication_campaigns WHERE id=?', (key,)).fetchone()
    if not row:
        raise ValueError('Campagna non trovata.')
    data = json.loads(row['data']); counts = dict.fromkeys(('pending', 'sending', 'accepted', 'failed', 'uncertain'), 0)
    for stat in c.execute('SELECT status,count(*) AS n FROM communication_recipients WHERE campaign_id=? GROUP BY status', (key,)):
        counts[stat['status']] = stat['n']
    counts['total'] = sum(counts.values())
    status = ('sending' if counts['sending'] else 'uncertain' if counts['uncertain'] else
              'partial' if counts['pending'] and counts['accepted'] + counts['failed'] else
              'draft' if counts['pending'] else 'failed' if counts['failed'] else 'accepted')
    cfg = _configuration(c); automatic = data.get('source') == 'reminders'
    ready = cfg['enabled'] and _configured(cfg) and not counts['sending'] and not automatic
    result = dict(id=key, name=data['name'], created_at=row['created_at'], created_by=row['created_by'], status=status, source=data.get('source', 'manual'),
                  counts=counts, remaining=counts['pending'], can_send=bool(ready and counts['pending']),
                  can_retry_failed=bool(ready and counts['failed']), **{k: data[k] for k in ('template_id', 'list_id', 'fingerprint')})
    confirmation = {'id': key, 'config': cfg, 'recipients': [dict(r) for r in c.execute(
        'SELECT r.id,r.status,(SELECT count(*) FROM communication_attempts a WHERE a.recipient_id=r.id) AS attempts '
        'FROM communication_recipients r WHERE r.campaign_id=? ORDER BY r.ordinal', (key,))]}
    used = c.execute('SELECT count(*) FROM communication_attempts WHERE started_epoch>?', (time.time() - 3600,)).fetchone()[0]
    available = min(cfg['batch_size'], max(0, cfg['max_per_hour'] - used))
    plans = {}
    for mode, state in [('send_plan', 'pending'), ('retry_plan', 'failed')]:
        ids = [r['id'] for r in confirmation['recipients'] if r['status'] == state][:available]
        plans[mode] = dict(recipient_ids=ids, count=len(ids))
    confirmation['plans'] = plans
    result['confirmation_token'] = hashlib.sha256(app.dump(confirmation).encode()).hexdigest()
    for mode, plan in plans.items():
        result[mode] = {**plan, 'token': result['confirmation_token']}
    result['batch_size'] = cfg['batch_size']
    result['can_reconcile'] = bool(c.execute("SELECT 1 FROM communication_recipients WHERE campaign_id=? AND status='sending' AND claimed_at<?", (key, time.time()-STALE_BATCH_SECONDS)).fetchone())
    result['can_send'] = bool(result['can_send'] and result['send_plan']['count'])
    result['can_retry_failed'] = bool(result['can_retry_failed'] and result['retry_plan']['count'])
    if detail:
        result.update(subject=data['subject'], body=data['body'], warnings=data['warnings'], recipients=[])
        for recipient in c.execute('SELECT * FROM communication_recipients WHERE campaign_id=? ORDER BY ordinal', (key,)):
            attempts = [dict(number=a['number'], status=a['status'], started_at=a['started_at'], finished_at=a['finished_at'],
                             error=a['error'], message_id=a['message_id']) for a in c.execute(
                                 'SELECT * FROM communication_attempts WHERE recipient_id=? ORDER BY number', (recipient['id'],))]
            result['recipients'].append(dict(id=recipient['id'], **json.loads(recipient['data']), status=recipient['status'],
                                             error=recipient['error'], attempts=attempts))
    return result


def campaign(app, user, key):
    with app.connect() as c:
        user = _access(app, c, user)
        return _campaign(app, c, user, key)


def reconcile_campaign(app, user, body):
    """Classify abandoned work without making a network request or retrying it."""
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user = _access(app, c, user)
        key = body.get('id'); _campaign(app, c, user, key, detail=False)
        stale = c.execute("SELECT id FROM communication_recipients WHERE campaign_id=? AND status='sending' AND claimed_at<?",
                          (key,time.time()-STALE_BATCH_SECONDS)).fetchall()
        if not stale:
            raise ValueError('Nessun invio interrotto verificabile. Attendere almeno 15 minuti senza aggiornamenti del lotto e ricaricare lo storico.')
        reason = 'Invio interrotto: verificare lo storico del servizio di posta. Nessun reinvio automatico.'
        for row in stale:
            c.execute("UPDATE communication_recipients SET status='uncertain',error=?,batch_id='' WHERE id=?", (reason,row['id']))
            c.execute("UPDATE communication_attempts SET status='uncertain',finished_at=?,error=? WHERE recipient_id=? AND status='sending'", (app.now(),reason,row['id']))
        app.audit(c,user,'Invii interrotti verificati',after={'id':key,'uncertain':len(stale)})
        c.commit()
        return _campaign(app,c,user,key)


def overview(app, user):
    with app.connect() as c:
        c.execute('BEGIN'); user = _access(app, c, user)
        centers = app.centers_for(c, user); roles = set()
        for center in centers:
            roles.update(app.center(c, center['id'])['config']['roles'])
        return dict(templates=[_get(c, 'communication_templates', r[0]) for r in c.execute('SELECT id FROM communication_templates ORDER BY id')],
                    lists=[_get(c, 'communication_lists', r[0]) for r in c.execute('SELECT id FROM communication_lists ORDER BY id')],
                    campaigns=[_campaign(app, c, user, r[0], detail=False) for r in c.execute('SELECT id FROM communication_campaigns ORDER BY created_at DESC,id DESC LIMIT 100')],
                    centers=[{k: ct[k] for k in ('id', 'name', 'code')} for ct in centers], roles=sorted(roles), stages=STAGES,
                    variables=[dict(id=key, label=label) for key, label in VARIABLES.items()], settings=_settings(c, user))


def _send_one(config, recipient, message_id):
    """Return only durable-safe categories; never expose SMTP exception contents."""
    smtp = None; data_started = False
    message = EmailMessage()
    message['From'] = formataddr((config['from_name'], config['from_email']))
    message['To'] = recipient['email']
    message['Subject'] = recipient['subject']
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = message_id
    if config['reply_to']:
        message['Reply-To'] = config['reply_to']
    message.set_content(recipient['body'])
    try:
        context = ssl.create_default_context()
        if config['security'] == 'ssl':
            smtp = smtplib.SMTP_SSL(config['host'], config['port'], timeout=SMTP_TIMEOUT, context=context)
            smtp.ehlo()
        else:
            smtp = smtplib.SMTP(config['host'], config['port'], timeout=SMTP_TIMEOUT)
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        if config['username']:
            smtp.login(config['username'], os.environ.get(PASSWORD_ENV, ''))
        # sendmail's individual commands let us distinguish pre-DATA failures from
        # a disconnect after DATA, when SMTP may already have accepted the email.
        code, _ = smtp.mail(config['from_email'])
        if code != 250:
            return 'failed', 'SMTP ha rifiutato il mittente.'
        code, _ = smtp.rcpt(recipient['email'])
        if code not in (250, 251):
            return 'failed', 'SMTP ha rifiutato il destinatario.'
        data_started = True
        code, _ = smtp.data(message.as_bytes(policy=SMTP_POLICY))
        if code != 250:
            return 'failed', 'SMTP ha rifiutato il messaggio.'
        return 'accepted', ''
    except smtplib.SMTPAuthenticationError:
        return 'failed', 'Autenticazione SMTP non riuscita. Verificare la configurazione con l’amministratore.'
    except smtplib.SMTPResponseException:
        return 'failed', 'SMTP ha rifiutato la richiesta.'
    except (OSError, smtplib.SMTPException, ValueError):
        return ('uncertain', 'Esito SMTP incerto: verificare i log del servizio prima di un nuovo invio.') if data_started else (
            'failed', 'Connessione SMTP non riuscita. Verificare server, TLS e credenziali.')
    finally:
        if smtp is not None:
            try:
                smtp.close()
            except Exception:
                pass


def send_campaign(app, user, body):
    if not isinstance(body, dict) or body.get('confirm') is not True or type(body.get('retry_failed', False)) is not bool:
        raise ValueError('Confermare esplicitamente i destinatari e il contenuto prima di inviare.')
    campaign_id = body.get('id'); batch_id = app.uid(); now = time.time()
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user = _access(app, c, user)
        view = _campaign(app, c, user, campaign_id, detail=False)
        if view.get('source') == 'reminders':
            raise ValueError('I promemoria automatici non possono essere inviati o ritentati manualmente. Verifica lo storico nella pagina Promemoria.')
        config = _configuration(c)
        if not config['enabled'] or not _configured(config):
            raise ValueError('Invio disabilitato o configurazione SMTP incompleta. La bozza resta disponibile.')
        token = body.get('confirmation_token')
        if not isinstance(token, str) or not hmac.compare_digest(token, view['confirmation_token']):
            raise ValueError('Lotto o configurazione cambiati. Riaprire la bozza e confermare nuovamente i destinatari.')
        if c.execute("SELECT 1 FROM communication_recipients WHERE campaign_id=? AND status='sending'", (campaign_id,)).fetchone():
            raise ValueError('Un lotto è già in corso. Attendere il completamento prima di continuare.')
        used = c.execute('SELECT count(*) FROM communication_attempts WHERE started_epoch>?', (now - 3600,)).fetchone()[0]
        available = min(config['batch_size'], max(0, config['max_per_hour'] - used))
        if not available:
            raise ValueError('Limite orario raggiunto. Riprendere manualmente quando il limite sarà disponibile.')
        target_status = 'failed' if body.get('retry_failed') else 'pending'
        pending = list(c.execute('SELECT * FROM communication_recipients WHERE campaign_id=? AND status=? ORDER BY ordinal LIMIT ?', (campaign_id, target_status, available)))
        if not pending:
            raise ValueError('Nessun destinatario disponibile per questa operazione. Gli esiti incerti non vengono reinviati.')
        claimed = []
        for row in pending:
            attempt_id = app.uid()
            number = c.execute('SELECT coalesce(max(number),0)+1 FROM communication_attempts WHERE recipient_id=?', (row['id'],)).fetchone()[0]
            domain = config['from_email'].rsplit('@', 1)[1]
            message_id = '<' + attempt_id + '@' + domain + '>'
            c.execute("UPDATE communication_recipients SET status='sending',error='',claimed_at=?,batch_id=? WHERE id=?", (now, batch_id, row['id']))
            c.execute('INSERT INTO communication_attempts(id,recipient_id,number,status,started_at,started_epoch,message_id) VALUES(?,?,?,\'sending\',?,?,?)',
                      (attempt_id, row['id'], number, app.now(), now, message_id))
            claimed.append((row['id'], attempt_id, message_id, json.loads(row['data'])))
        app.audit(c, user, 'Lotto email confermato', after={'id': campaign_id, 'batch_id': batch_id, 'recipients': len(claimed), 'retry_failed': body.get('retry_failed', False)})
        c.commit()
    for recipient_id, attempt_id, message_id, recipient in claimed:
        # A revocation or SMTP configuration change cancels the not-yet-attempted
        # portion without making any further network request.
        with app.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # Renew all outstanding claims before each network operation.
            c.execute("UPDATE communication_recipients SET claimed_at=? WHERE batch_id=? AND status='sending'", (time.time(), batch_id))
            allowed = False
            try:
                _access(app, c, user)
                current = _configuration(c)
                claim=c.execute("SELECT 1 FROM communication_recipients WHERE id=? AND batch_id=? AND status='sending'",(recipient_id,batch_id)).fetchone()
                allowed = bool(claim) and current['enabled'] and current['version'] == config['version'] and _configured(current)
            except (PermissionError, app.AuthenticationError):
                pass
            c.commit()
        if allowed:
            status, error = _send_one(config, recipient, message_id)
        else:
            status, error = 'failed', 'Lotto interrotto per cambio autorizzazioni o configurazione; nessun invio eseguito.'
        with app.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('UPDATE communication_attempts SET status=?,finished_at=?,error=? WHERE id=?', (status, app.now(), error, attempt_id))
            c.execute('UPDATE communication_recipients SET status=?,error=?,batch_id=\'\' WHERE id=? AND batch_id=?', (status, error, recipient_id, batch_id))
            c.commit()
    with app.connect() as c:
        user = _access(app, c, user)
        app.audit(c, user, 'Lotto email terminato', after={'id': campaign_id, 'batch_id': batch_id})
        c.commit()
        return _campaign(app, c, user, campaign_id)
