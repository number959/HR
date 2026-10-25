"""Comunicazioni HR: modelli, liste di destinatari, anteprime, bozze e invio controllato.

Nessun processo invia email da solo. L'invio reale richiede che l'amministratore
abbia configurato il server di posta aziendale (la password resta solo
nell'ambiente del server, variabile WR_SMTP_PASSWORD) e una conferma esplicita
di ogni lotto. «Accettato dal server di posta» non significa consegnato o letto.
Nella demo pubblica l'invio è sempre simulato.
"""
import hashlib
import hmac
import ipaddress
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import formataddr, formatdate

from . import audit, centers, hr, months, structures, users
from .errors import Conflict, Forbidden, Invalid, NotFound, Unauthorized
from .permissions import has, require
from .util import dumps, loads, new_id, stamp
from . import validate as v

PASSWORD_ENV = 'WR_SMTP_PASSWORD'
MAX_RECIPIENTS = 10000
SMTP_TIMEOUT = 15
STALE_SECONDS = 900
STAGES = ['incoming', 'active', 'ended']
VARIABLES = {
    'nome': 'Nome completo (o referente della struttura)', 'nome_battesimo': 'Nome nel fascicolo',
    'cognome': 'Cognome nel fascicolo', 'matricola': 'Matricola', 'ruolo': 'Ruolo', 'data_ingresso': 'Data di ingresso',
    'struttura': 'Nome della struttura', 'codice_struttura': 'Codice della struttura',
    'ragione_sociale': 'Ragione sociale della struttura', 'email_hr': 'Email HR della struttura',
    'email_struttura': 'Email generale della struttura', 'email_amministrazione': 'Email amministrazione della struttura',
    'telefono_struttura': 'Telefono della struttura', 'indirizzo_struttura': 'Indirizzo della struttura',
    'referente_struttura': 'Referente della struttura', 'email_destinatario': 'Email del destinatario',
}
DEFAULT_SETTINGS = dict(enabled=False, host='', port=465, security='ssl', username='', from_email='', from_name='NefroCenter HR',
                        reply_to='', batch_size=20, max_per_hour=100)
STATUS_LABELS = {'pending': 'Da inviare', 'sending': 'In invio', 'accepted': 'Accettato dal server di posta',
                 'failed': 'Non riuscito', 'uncertain': 'Esito incerto', 'simulated': 'Invio simulato (demo)'}
SEED_TEMPLATES = [
    ('benvenuto', 'Benvenuto', 'Benvenuto in {{struttura}}',
     'Gentile {{nome}},\n\nbenvenuto presso {{struttura}}. Ti invitiamo a concordare con il referente le attività di ingresso '
     'e a completare il fascicolo personale.\n\nUfficio HR'),
    ('documenti', 'Documenti da completare', 'Completamento documenti · {{struttura}}',
     'Gentile {{nome}},\n\nti chiediamo di verificare con l’ufficio HR i documenti da completare nel tuo fascicolo. Usa i canali '
     'aziendali previsti per la consegna.\n\nUfficio HR'),
    ('scadenze', 'Promemoria scadenze', 'Verifica scadenze · {{struttura}}',
     'Gentile {{nome}},\n\nti invitiamo a verificare con l’ufficio HR le scadenze relative al tuo rapporto con {{struttura}} e a '
     'concordare gli aggiornamenti necessari.\n\nUfficio HR'),
    ('presenze', 'Verifica presenze', 'Verifica presenze · {{struttura}}',
     'Gentile {{nome}},\n\nti chiediamo di verificare le presenze e di segnalare al referente eventuali correzioni prima della '
     'chiusura del periodo.\n\nUfficio HR'),
    ('sede', 'Comunicazione alla struttura', 'Comunicazione per {{struttura}}',
     'Alla cortese attenzione del referente di {{struttura}},\n\ninserire qui il testo della comunicazione prima di creare la '
     'bozza di invio.\n\nUfficio HR'),
]
PLACEHOLDER = re.compile(r'{{\s*([^{}]+?)\s*}}')
HOST_PART = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')


def seed(db):
    with db.write() as con:
        for key, name, subject, body in SEED_TEMPLATES:
            con.execute('INSERT OR IGNORE INTO mail_templates(id,data,version) VALUES(?,?,1)',
                        ('seed-' + key, dumps(dict(name=name, subject=subject, body=body))))


def _content(subject, body):
    subject = v.text(subject, 'Oggetto', 300, required=True, field='subject')
    body = v.text(body, 'Messaggio', 20000, required=True, multiline=True, field='body')
    for value in (subject, body):
        unknown = set(PLACEHOLDER.findall(value)) - set(VARIABLES)
        rest = PLACEHOLDER.sub('', value)
        if unknown or '{{' in rest or '}}' in rest:
            raise Invalid('Variabile non riconosciuta: usare soltanto quelle elencate.', field='body')
    return subject, body


def _get(con, table, key):
    found = con.execute(f'SELECT * FROM {table} WHERE id=?', (key,)).fetchone()
    if not found:
        raise NotFound('Modello o lista non trovati.')
    return dict(id=found['id'], version=found['version'], **loads(found['data']))


def _save(db, actor, table, action, raw, validate, key=None):
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'comunicazioni.usa')
        before = _get(con, table, key) if key else None
        version = before['version'] if before else 0
        if v.version(raw.get('version')) != version:
            raise Conflict('La versione è cambiata: ricaricare prima di salvare.')
        data = validate(con, actor, raw)
        key = key or new_id()
        con.execute(f'''INSERT INTO {table}(id,data,version) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET
                        data=excluded.data, version=excluded.version''', (key, dumps(data), version + 1))
        audit.record(con, actor, action, entity=table, entity_id=key, after=dict(version=version + 1, name=data['name']))
    return dict(id=key, version=version + 1, **data)


def save_template(db, actor, raw, key=None):
    def validate(con, actor, raw):
        v.keys(raw, {'name', 'subject', 'body', 'version'}, 'Modello', required={'name', 'subject', 'body', 'version'})
        subject, body = _content(raw['subject'], raw['body'])
        return dict(name=v.text(raw['name'], 'Nome del modello', 120, required=True, field='name'), subject=subject, body=body)
    return _save(db, actor, 'mail_templates', 'Modello email salvato', raw, validate, key)


def _choices(raw, key, permitted, maximum=10000):
    values = raw.get(key, [])
    if not isinstance(values, list) or len(values) > maximum or any(not isinstance(x, str) for x in values):
        raise Invalid(f'Filtro {key} non valido.', field=key)
    values = sorted(set(values))
    if permitted is not None and set(values) - set(permitted):
        raise Invalid(f'Filtro {key}: valore inesistente o non autorizzato.', field=key)
    return values


def save_list(db, actor, raw, key=None):
    def validate(con, actor, raw):
        v.keys(raw, {'name', 'cids', 'roles', 'stages', 'email_field', 'exclude_emails', 'recipient_type', 'structure_field',
                     'version'}, 'Lista', required={'name', 'version'})
        visible = centers.visible(con, actor)
        roles = set()
        for c in visible:
            roles.update(centers.config(con, c['id'])['roles'])
        out = dict(name=v.text(raw['name'], 'Nome della lista', 120, required=True, field='name'),
                   cids=_choices(raw, 'cids', [c['id'] for c in visible]), roles=_choices(raw, 'roles', roles, 1000),
                   stages=_choices(raw, 'stages', STAGES, 3),
                   email_field=v.choice(raw.get('email_field', 'company_email'), 'Indirizzo da usare', ('email', 'company_email'),
                                        field='email_field'),
                   recipient_type=v.choice(raw.get('recipient_type', 'employees'), 'Destinatari', ('employees', 'structures'),
                                           field='recipient_type'),
                   structure_field=v.choice(raw.get('structure_field', 'email'), 'Recapito della struttura',
                                            ('email', 'hr_email', 'admin_email'), field='structure_field'))
        if out['recipient_type'] == 'structures' and (out['roles'] or out['stages']):
            raise Invalid('I filtri per ruolo e stato valgono solo per i dipendenti.', field='roles')
        out['exclude_emails'] = sorted({v.email(x, required=True, field='exclude_emails').casefold()
                                        for x in _choices(raw, 'exclude_emails', None)})
        return out
    return _save(db, actor, 'mail_lists', 'Lista email salvata', raw, validate, key)


# --- configurazione del server di posta -------------------------------------------------------

def settings(con):
    found = con.execute('SELECT * FROM mail_settings WHERE id=1').fetchone()
    return dict(version=found['version'] if found else 0, **(loads(found['data']) if found else DEFAULT_SETTINGS))


def configured(cfg):
    return bool(cfg['host'] and cfg['from_email'] and (not cfg['username'] or os.environ.get(PASSWORD_ENV)))


def ready(cfg, simulated=False):
    return simulated or (cfg['enabled'] and configured(cfg))


def public_settings(cfg, user, simulated=False):
    if has(user, 'comunicazioni.configura'):
        return dict(cfg, configured=configured(cfg), password_configured=bool(os.environ.get(PASSWORD_ENV)), simulated=simulated)
    return dict(enabled=cfg['enabled'], configured=configured(cfg), batch_size=cfg['batch_size'], simulated=simulated)


def save_settings(db, actor, raw, simulated=False):
    v.keys(raw, set(DEFAULT_SETTINGS) | {'version'}, 'Configurazione della posta', required=set(DEFAULT_SETTINGS) | {'version'})
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'comunicazioni.configura')
        old = settings(con)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Configurazione cambiata: ricaricare prima di salvare.')
        cfg = {k: raw[k] for k in DEFAULT_SETTINGS}
        cfg['enabled'] = v.boolean(cfg['enabled'], 'Invio abilitato', field='enabled')
        cfg['security'] = v.choice(cfg['security'], 'Sicurezza', ('ssl', 'starttls'), field='security')
        cfg['port'] = v.integer(cfg['port'], 'Porta', 1, 65535, field='port')
        cfg['batch_size'] = v.integer(cfg['batch_size'], 'Messaggi per lotto', 1, 20, field='batch_size')
        cfg['max_per_hour'] = v.integer(cfg['max_per_hour'], 'Massimo all’ora', 1, 2000, field='max_per_hour')
        for key, label in (('host', 'Server di posta'), ('username', 'Utente'), ('from_name', 'Nome del mittente')):
            cfg[key] = v.text(cfg[key], label, 254, field=key)
        if cfg['host']:
            try:
                ipaddress.ip_address(cfg['host'])
            except ValueError:
                if len(cfg['host']) > 253 or not all(HOST_PART.fullmatch(p) for p in cfg['host'].split('.')):
                    raise Invalid('Server di posta non valido: indicare solo il nome, senza indirizzo web né porta.',
                                  field='host') from None
        cfg['from_email'] = v.email(cfg['from_email'], 'Mittente', field='from_email')
        cfg['reply_to'] = v.email(cfg['reply_to'], 'Rispondi a', field='reply_to')
        if cfg['enabled'] and not (cfg['host'] and cfg['from_email']):
            raise Invalid('Prima di abilitare l’invio indicare server di posta e mittente.', field='enabled')
        con.execute('INSERT INTO mail_settings(id,data,version) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, '
                    'version=excluded.version', (dumps(cfg), old['version'] + 1))
        audit.record(con, actor, 'Configurazione della posta salvata', entity='mail_settings', entity_id='1',
                     after=dict(version=old['version'] + 1, enabled=cfg['enabled'], host=cfg['host']))
        return public_settings(settings(con), actor, simulated)


# --- anteprima e bozze ----------------------------------------------------------------------------

def _render(value, variables):
    missing = set()

    def replace(match):
        key = match.group(1).strip()
        item = variables.get(key, '')
        if not item:
            missing.add(key)
        return str(item)

    return PLACEHOLDER.sub(replace, value), missing


def _preview(con, user, raw):
    template = _get(con, 'mail_templates', v.identifier(raw.get('template_id'), 'Modello'))
    target = _get(con, 'mail_lists', v.identifier(raw.get('list_id'), 'Lista'))
    subject, body = _content(raw.get('subject', template['subject']), raw.get('body', template['body']))
    visible = centers.visible(con, user)
    allowed = {c['id'] for c in visible}
    if set(target['cids']) - allowed:
        raise Invalid('La lista contiene una struttura non più disponibile: aggiornarla.')
    chosen = [c for c in visible if c['active'] and (not target['cids'] or c['id'] in target['cids'])]
    recipients, warnings, seen = [], [], set()
    counts = dict(selected=0, valid=0, missing=0, invalid=0, duplicates=0, excluded=0)
    excluded = set(target['exclude_emails'])

    def warn(code, message, severity='warning'):
        warnings.append(dict(code=code, message=message, severity=severity))

    for c in chosen:
        sf = structures.record(con, c['id'])['fields']
        base = dict(struttura=c['name'], codice_struttura=c['code'], ragione_sociale=sf['legal_name'], email_hr=sf['hr_email'],
                    email_struttura=sf['email'], email_amministrazione=sf['admin_email'], telefono_struttura=sf['phone'],
                    indirizzo_struttura=sf['address'], referente_struttura=sf['contact_name'])
        audience = []
        if target['recipient_type'] == 'structures':
            audience.append(dict(center_id=c['id'], person_id='', name=c['name'], email=sf[target['structure_field']],
                                 variables=dict(base, nome=sf['contact_name'] or c['name'])))
        else:
            for p in months.people(con, c['id']):
                prof = hr.profile(con, p['id'])
                f = prof['fields']
                stage = prof['stage'] if prof['version'] else ('active' if p['active'] else 'ended')
                if (target['roles'] and p['role'] not in target['roles']) or (target['stages'] and stage not in target['stages']):
                    continue
                audience.append(dict(center_id=c['id'], person_id=p['id'], name=p['name'], email=f[target['email_field']],
                                     variables=dict(base, nome=p['name'], nome_battesimo=f['first_name'], cognome=f['last_name'],
                                                    matricola=p['registration'], ruolo=p['role'], data_ingresso=f['start_date'])))
        for row in audience:
            counts['selected'] += 1
            if counts['selected'] > MAX_RECIPIENTS:
                raise Invalid('Oltre 10.000 destinatari: restringere i filtri della lista.')
            label = f'{row["name"]} · {c["name"]}'
            if not row['email']:
                counts['missing'] += 1
                warn('missing_email', f'{label}: email mancante, escluso.')
                continue
            try:
                row['email'] = v.email(row['email'], required=True)
            except Invalid:
                counts['invalid'] += 1
                warn('invalid_email', f'{label}: email non valida, escluso.')
                continue
            key = row['email'].casefold()
            if key in excluded:
                counts['excluded'] += 1
                continue
            if key in seen:
                counts['duplicates'] += 1
                warn('duplicate_email', f'{label}: indirizzo già presente, resta il primo destinatario.')
                continue
            seen.add(key)
            variables = row.pop('variables')
            variables['email_destinatario'] = row['email']
            row['subject'], miss_subject = _render(subject, variables)
            row['body'], miss_body = _render(body, variables)
            missing = miss_subject | miss_body
            if missing:
                warn('missing_variable', f'{label}: mancano i valori per {", ".join(sorted(missing))}.', 'error')
            try:
                v.text(row['subject'], 'Oggetto personalizzato', 2000)
                v.text(row['body'], 'Messaggio personalizzato', 60000, multiline=True)
            except Invalid:
                warn('invalid_content', f'{label}: il contenuto personalizzato contiene dati non validi.', 'error')
            recipients.append(row)
    counts['valid'] = len(recipients)
    if not recipients:
        warn('empty_audience', 'Nessun destinatario valido nella lista.', 'error')
    snapshot = dict(template_id=template['id'], template_version=template['version'], list_id=target['id'],
                    list_version=target['version'], subject=subject, body=body, recipients=recipients, warnings=warnings,
                    counts=counts)
    fingerprint = hashlib.sha256(dumps(snapshot).encode()).hexdigest()
    return dict(snapshot, fingerprint=fingerprint, can_create=not any(w['severity'] == 'error' for w in warnings))


def preview(db, user, raw):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'comunicazioni.usa')
        return _preview(con, user, raw)


def create_campaign(db, actor, raw, simulated=False):
    v.keys(raw, {'template_id', 'list_id', 'subject', 'body', 'fingerprint', 'name'}, 'Bozza',
           required={'template_id', 'list_id', 'fingerprint'})
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'comunicazioni.usa')
        view = _preview(con, actor, raw)
        if not isinstance(raw['fingerprint'], str) or not hmac.compare_digest(raw['fingerprint'], view['fingerprint']):
            raise Conflict('Destinatari o contenuti cambiati: ripetere l’anteprima prima di creare la bozza.')
        if not view['can_create']:
            raise Invalid('Correggere gli errori dell’anteprima prima di creare la bozza.')
        cid = new_id()
        data = {k: val for k, val in view.items() if k not in ('recipients', 'can_create', 'counts')}
        data['name'] = v.text(raw.get('name') or view['subject'], 'Nome della bozza', 300, required=True, field='name')
        con.execute("INSERT INTO mail_campaigns(id,source,data,created_at,created_by) VALUES(?,'manual',?,?,?)",
                    (cid, dumps(data), stamp(), actor.username))
        for ordinal, r in enumerate(view['recipients']):
            con.execute('INSERT INTO mail_recipients(id,campaign_id,ordinal,data) VALUES(?,?,?,?)', (new_id(), cid, ordinal, dumps(r)))
        audit.record(con, actor, 'Bozza email creata', entity='mail_campaign', entity_id=cid,
                     after=dict(recipients=len(view['recipients']), fingerprint=view['fingerprint']))
        return campaign_view(con, actor, cid, simulated=simulated)


def campaign_view(con, user, key, detail=True, simulated=False):
    found = con.execute('SELECT * FROM mail_campaigns WHERE id=?', (key,)).fetchone()
    if not found:
        raise NotFound('Bozza non trovata.')
    data = loads(found['data'])
    counts = dict.fromkeys(STATUS_LABELS, 0)
    for r in con.execute('SELECT status, count(*) AS n FROM mail_recipients WHERE campaign_id=? GROUP BY status', (key,)):
        counts[r['status']] = r['n']
    counts['total'] = sum(counts[k] for k in STATUS_LABELS)
    done = counts['accepted'] + counts['failed'] + counts['simulated']
    status = ('sending' if counts['sending'] else 'uncertain' if counts['uncertain'] else
              'partial' if counts['pending'] and done else 'draft' if counts['pending'] else
              'failed' if counts['failed'] and not counts['accepted'] and not counts['simulated'] else
              'simulated' if counts['simulated'] and not counts['accepted'] else 'accepted')
    cfg = settings(con)
    automatic = found['source'] == 'reminders'
    can = ready(cfg, simulated) and not counts['sending'] and not automatic
    rows = [dict(r) for r in con.execute('''SELECT r.id, r.status, (SELECT count(*) FROM mail_attempts a WHERE a.recipient_id=r.id)
                                            AS attempts FROM mail_recipients r WHERE r.campaign_id=? ORDER BY r.ordinal''', (key,))]
    used = con.execute('SELECT count(*) FROM mail_attempts WHERE started_epoch>?', (time.time() - 3600,)).fetchone()[0]
    available = cfg['batch_size'] if simulated else min(cfg['batch_size'], max(0, cfg['max_per_hour'] - used))
    plans = {mode: dict(recipient_ids=[r['id'] for r in rows if r['status'] == state][:available])
             for mode, state in (('send_plan', 'pending'), ('retry_plan', 'failed'))}
    for plan in plans.values():
        plan['count'] = len(plan['recipient_ids'])
    token = hashlib.sha256(dumps(dict(id=key, config=cfg, recipients=rows, plans=plans, simulated=simulated)).encode()).hexdigest()
    out = dict(id=key, name=data['name'], created_at=found['created_at'], created_by=found['created_by'], status=status,
               status_label={'draft': 'Bozza', 'partial': 'Inviata in parte', 'sending': 'In invio', 'uncertain': 'Esito incerto',
                             'failed': 'Non riuscita', 'accepted': 'Accettata dal server di posta',
                             'simulated': 'Invio simulato (demo)'}[status],
               source=found['source'], counts=counts, remaining=counts['pending'], confirmation_token=token,
               send_plan=dict(plans['send_plan'], token=token), retry_plan=dict(plans['retry_plan'], token=token),
               can_send=bool(can and plans['send_plan']['count']), can_retry_failed=bool(can and plans['retry_plan']['count']),
               batch_size=cfg['batch_size'], simulated=simulated,
               can_reconcile=bool(con.execute("SELECT 1 FROM mail_recipients WHERE campaign_id=? AND status='sending' AND claimed_at<?",
                                              (key, time.time() - STALE_SECONDS)).fetchone()),
               **{k: data.get(k, '') for k in ('template_id', 'list_id', 'fingerprint')})
    if detail:
        out.update(subject=data['subject'], body=data['body'], warnings=data.get('warnings', []), recipients=[])
        for r in con.execute('SELECT * FROM mail_recipients WHERE campaign_id=? ORDER BY ordinal', (key,)):
            attempts = [dict(number=a['number'], status=a['status'], started_at=a['started_at'], finished_at=a['finished_at'],
                             error=a['error'], message_id=a['message_id'])
                        for a in con.execute('SELECT * FROM mail_attempts WHERE recipient_id=? ORDER BY number', (r['id'],))]
            out['recipients'].append(dict(id=r['id'], **loads(r['data']), status=r['status'],
                                          status_label=STATUS_LABELS[r['status']], error=r['error'], attempts=attempts))
    return out


def campaign(db, user, key, simulated=False):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'comunicazioni.usa')
        return campaign_view(con, user, v.identifier(key, 'Bozza'), simulated=simulated)


def overview(db, user, simulated=False):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'comunicazioni.usa')
        visible = centers.visible(con, user)
        roles = set()
        for c in visible:
            roles.update(centers.config(con, c['id'])['roles'])
        return dict(templates=[_get(con, 'mail_templates', r[0]) for r in con.execute('SELECT id FROM mail_templates ORDER BY id')],
                    lists=[_get(con, 'mail_lists', r[0]) for r in con.execute('SELECT id FROM mail_lists ORDER BY id')],
                    campaigns=[campaign_view(con, user, r[0], detail=False, simulated=simulated) for r in con.execute(
                        'SELECT id FROM mail_campaigns ORDER BY created_at DESC, id DESC LIMIT 100')],
                    centers=[dict(id=c['id'], name=c['name'], code=c['code']) for c in visible], roles=sorted(roles),
                    stages=[dict(id=s, label=hr.STAGES[s]) for s in STAGES],
                    variables=[dict(id=k, label=label) for k, label in VARIABLES.items()],
                    settings=public_settings(settings(con), user, simulated))


def reconcile(db, actor, key):
    """Classifica gli invii interrotti come «esito incerto», senza reinviare nulla."""
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'comunicazioni.usa')
        campaign_view(con, actor, key, detail=False)
        stale = con.execute("SELECT id FROM mail_recipients WHERE campaign_id=? AND status='sending' AND claimed_at<?",
                            (key, time.time() - STALE_SECONDS)).fetchall()
        if not stale:
            raise Invalid('Nessun invio interrotto da verificare: attendere almeno 15 minuti senza aggiornamenti del lotto.')
        reason = 'Invio interrotto: verificare lo storico del server di posta. Nessun reinvio automatico.'
        for r in stale:
            mark_uncertain(con, r['id'], reason)
        audit.record(con, actor, 'Invii interrotti verificati', entity='mail_campaign', entity_id=key, after=dict(uncertain=len(stale)))
        return campaign_view(con, actor, key)


def mark_uncertain(con, recipient_id, reason):
    con.execute("UPDATE mail_recipients SET status='uncertain', error=?, batch_id='' WHERE id=?", (reason, recipient_id))
    con.execute("UPDATE mail_attempts SET status='uncertain', finished_at=?, error=? WHERE recipient_id=? AND status='sending'",
                (stamp(), reason, recipient_id))


# --- trasporto --------------------------------------------------------------------------------------

def smtp_send(cfg, recipient, message_id):
    """Invio reale. Restituisce solo categorie sicure, mai il testo degli errori del server."""
    client, data_started = None, False
    message = EmailMessage()
    message['From'] = formataddr((cfg['from_name'], cfg['from_email']))
    message['To'] = recipient['email']
    message['Subject'] = recipient['subject']
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = message_id
    if cfg['reply_to']:
        message['Reply-To'] = cfg['reply_to']
    message.set_content(recipient['body'])
    try:
        context = ssl.create_default_context()
        if cfg['security'] == 'ssl':
            client = smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=SMTP_TIMEOUT, context=context)
            client.ehlo()
        else:
            client = smtplib.SMTP(cfg['host'], cfg['port'], timeout=SMTP_TIMEOUT)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        if cfg['username']:
            client.login(cfg['username'], os.environ.get(PASSWORD_ENV, ''))
        code, _ = client.mail(cfg['from_email'])
        if code != 250:
            return 'failed', 'Il server di posta ha rifiutato il mittente.'
        code, _ = client.rcpt(recipient['email'])
        if code not in (250, 251):
            return 'failed', 'Il server di posta ha rifiutato il destinatario.'
        data_started = True
        code, _ = client.data(message.as_bytes(policy=SMTP_POLICY))
        if code != 250:
            return 'failed', 'Il server di posta ha rifiutato il messaggio.'
        return 'accepted', ''
    except smtplib.SMTPAuthenticationError:
        return 'failed', 'Autenticazione sul server di posta non riuscita: verificare la configurazione.'
    except smtplib.SMTPResponseException:
        return 'failed', 'Il server di posta ha rifiutato la richiesta.'
    except (OSError, smtplib.SMTPException, ValueError):
        if data_started:
            return 'uncertain', 'Esito incerto: verificare i registri del server di posta prima di un nuovo invio.'
        return 'failed', 'Connessione al server di posta non riuscita: verificare server, TLS e credenziali.'
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def simulated_send(cfg, recipient, message_id):
    return 'simulated', ''


def send(db, actor, key, raw, transport=None, simulated=False):
    v.keys(raw, {'confirm', 'retry_failed', 'confirmation_token'}, 'Invio', required={'confirm', 'confirmation_token'})
    if raw['confirm'] is not True:
        raise Invalid('Confermare esplicitamente destinatari e contenuto prima di inviare.', field='confirm')
    retry = v.boolean(raw.get('retry_failed', False), 'Ritenta i non riusciti')
    transport = simulated_send if simulated else (transport or smtp_send)
    batch, now = new_id(), time.time()
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'comunicazioni.usa')
        view = campaign_view(con, actor, v.identifier(key, 'Bozza'), detail=False, simulated=simulated)
        if view['source'] == 'reminders':
            raise Forbidden('I promemoria automatici non si inviano a mano: controllare lo storico nella pagina Promemoria.')
        cfg = settings(con)
        if not ready(cfg, simulated):
            raise Invalid('Invio disattivato o server di posta non configurato: la bozza resta disponibile.')
        if not isinstance(raw['confirmation_token'], str) or not hmac.compare_digest(raw['confirmation_token'],
                                                                                     view['confirmation_token']):
            raise Conflict('Lotto o configurazione cambiati: riaprire la bozza e confermare di nuovo.')
        if con.execute("SELECT 1 FROM mail_recipients WHERE campaign_id=? AND status='sending'", (key,)).fetchone():
            raise Invalid('Un lotto è già in corso: attendere il completamento.')
        plan = view['retry_plan' if retry else 'send_plan']
        if not plan['count']:
            raise Invalid('Limite orario raggiunto o nessun destinatario disponibile (gli esiti incerti non vengono reinviati).')
        domain = (cfg['from_email'] or 'demo.invalid').rsplit('@', 1)[1]
        claimed = []
        for rid in plan['recipient_ids']:
            aid = new_id()
            number = con.execute('SELECT coalesce(max(number),0)+1 FROM mail_attempts WHERE recipient_id=?', (rid,)).fetchone()[0]
            message_id = f'<{aid}@{domain}>'
            con.execute("UPDATE mail_recipients SET status='sending', error='', claimed_at=?, batch_id=? WHERE id=?", (now, batch, rid))
            con.execute("INSERT INTO mail_attempts(id,recipient_id,number,status,started_at,started_epoch,message_id) "
                        "VALUES(?,?,?,'sending',?,?,?)", (aid, rid, number, stamp(), now, message_id))
            data = loads(con.execute('SELECT data FROM mail_recipients WHERE id=?', (rid,)).fetchone()[0])
            claimed.append((rid, aid, message_id, data))
        audit.record(con, actor, 'Lotto email confermato' + (' (simulato)' if simulated else ''), entity='mail_campaign',
                     entity_id=key, after=dict(batch=batch, recipients=len(claimed), retry_failed=retry))
    for rid, aid, message_id, recipient in claimed:
        allowed = False
        with db.write() as con:
            con.execute("UPDATE mail_recipients SET claimed_at=? WHERE batch_id=? AND status='sending'", (time.time(), batch))
            try:
                current_user = users.reload(con, actor)
                require(current_user, 'comunicazioni.usa')
                current = settings(con)
                claim = con.execute("SELECT 1 FROM mail_recipients WHERE id=? AND batch_id=? AND status='sending'",
                                    (rid, batch)).fetchone()
                allowed = bool(claim) and current['version'] == cfg['version'] and ready(current, simulated)
            except (Forbidden, Unauthorized):
                allowed = False
        if allowed:
            status, error = transport(cfg, recipient, message_id)
        else:
            status, error = 'failed', 'Lotto interrotto per cambio di autorizzazioni o configurazione: nessun invio eseguito.'
        with db.write() as con:
            con.execute('UPDATE mail_attempts SET status=?, finished_at=?, error=? WHERE id=?', (status, stamp(), error, aid))
            con.execute("UPDATE mail_recipients SET status=?, error=?, batch_id='' WHERE id=? AND batch_id=?",
                        (status, error, rid, batch))
    with db.write() as con:
        actor = users.reload(con, actor)
        audit.record(con, actor, 'Lotto email terminato', entity='mail_campaign', entity_id=key, after=dict(batch=batch))
        return campaign_view(con, actor, key, simulated=simulated)


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


def _sim(ctx):
    return bool(ctx.app.demo)


@route('GET', '/api/mail', cap='comunicazioni.usa')
def api_overview(ctx):
    return overview(ctx.db, ctx.user, _sim(ctx))


@route('POST', '/api/mail/templates', cap='comunicazioni.usa')
def api_template_create(ctx):
    return save_template(ctx.db, ctx.user, ctx.body)


@route('PUT', '/api/mail/templates/<key>', cap='comunicazioni.usa')
def api_template_update(ctx):
    return save_template(ctx.db, ctx.user, ctx.body, ctx.params['key'])


@route('POST', '/api/mail/lists', cap='comunicazioni.usa')
def api_list_create(ctx):
    return save_list(ctx.db, ctx.user, ctx.body)


@route('PUT', '/api/mail/lists/<key>', cap='comunicazioni.usa')
def api_list_update(ctx):
    return save_list(ctx.db, ctx.user, ctx.body, ctx.params['key'])


@route('POST', '/api/mail/preview', cap='comunicazioni.usa')
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.body)


@route('POST', '/api/mail/campaigns', cap='comunicazioni.usa')
def api_campaign_create(ctx):
    return create_campaign(ctx.db, ctx.user, ctx.body, _sim(ctx))


@route('GET', '/api/mail/campaigns/<key>', cap='comunicazioni.usa')
def api_campaign(ctx):
    return campaign(ctx.db, ctx.user, ctx.params['key'], _sim(ctx))


@route('POST', '/api/mail/campaigns/<key>/send', cap='comunicazioni.usa', step_up=True)
def api_send(ctx):
    return send(ctx.db, ctx.user, ctx.params['key'], ctx.body, ctx.app.services.get('mail_transport'), _sim(ctx))


@route('POST', '/api/mail/campaigns/<key>/reconcile', cap='comunicazioni.usa')
def api_reconcile(ctx):
    return reconcile(ctx.db, ctx.user, ctx.params['key'])


@route('PUT', '/api/mail/settings', cap='comunicazioni.configura', step_up=True)
def api_settings(ctx):
    return save_settings(ctx.db, ctx.user, ctx.body, _sim(ctx))
