"""Promemoria HR automatici: disattivati finché l'amministratore non li configura.

Ogni promemoria ha una chiave stabile e non viene mai ripetuto: errori ed esiti
incerti non si reinviano da soli. I messaggi contengono solo conteggi per
struttura, senza nomi di dipendenti. L'attivazione richiede l'anteprima dei
destinatari, la conferma esplicita e il server di posta aziendale già attivo.
"""
import hashlib
import hmac
import time
from collections import Counter, defaultdict
from datetime import date, datetime

from . import audit, centers, hr, mail, months, structures, users
from .errors import Conflict, Invalid
from .permissions import User, has, require
from .util import ZONE, dumps, loads, new_id, previous_month, stamp
from . import validate as v

TOPICS = {'contract': 'Contratti e periodo di prova', 'document': 'Documenti', 'qualification': 'Qualifiche e verifiche',
          'onboarding': 'Inserimento in ritardo', 'attendance': 'Presenze del mese precedente da verificare'}
DEFAULTS = dict(enabled=False, centers=[], topics=list(TOPICS), offsets=[30, 15, 7, 0], recipient_mode='structure_hr',
                central_hr_email='', hour=8, max_daily_messages=20, max_overdue_days=30)
SYSTEM = User(id='', username='promemoria-automatici', name='Promemoria automatici', role='admin')
FIELD_TOPICS = [('end_date', 'contract'), ('probation_end', 'contract'), ('identity_expiry', 'document'),
                ('registration_expiry', 'qualification'), ('work_permit_expiry', 'qualification'), ('next_review', 'qualification')]


def clock(now=None):
    if now is None:
        return datetime.now(ZONE)
    if now.tzinfo is None:
        raise ValueError('Il controllo dei promemoria richiede data e fuso orario.')
    return now.astimezone(ZONE)


def settings(con):
    found = con.execute('SELECT * FROM reminder_settings WHERE id=1').fetchone()
    if not found:
        return dict(DEFAULTS, version=0, enabled_by='', approved_routes={})
    return dict(loads(found['data']), version=found['version'], enabled_by=found['enabled_by'])


def validate_config(con, raw):
    v.keys(raw, set(DEFAULTS) | {'version', 'fingerprint', 'confirmed'}, 'Promemoria')
    out = {**DEFAULTS, **{k: raw[k] for k in DEFAULTS if k in raw}}
    out['enabled'] = v.boolean(out['enabled'], 'Attivazione', field='enabled')
    known = {r[0] for r in con.execute('SELECT id FROM centers')}
    out['centers'] = v.str_list(out['centers'], 'Strutture', maximum=1000, item_max=64, allowed=known, field='centers')
    out['topics'] = v.str_list(out['topics'], 'Argomenti', maximum=len(TOPICS), allowed=TOPICS, field='topics')
    if not out['topics']:
        raise Invalid('Selezionare almeno un tipo di promemoria.', field='topics')
    offsets = out['offsets']
    if not isinstance(offsets, list) or not 1 <= len(offsets) <= 8 or any(type(x) is not int or not 0 <= x <= 365 for x in offsets):
        raise Invalid('Indicare da uno a otto anticipi, in giorni da 0 a 365.', field='offsets')
    out['offsets'] = sorted(set(offsets), reverse=True)
    out['hour'] = v.integer(out['hour'], 'Ora di invio', 0, 23, field='hour')
    out['max_daily_messages'] = v.integer(out['max_daily_messages'], 'Messaggi al giorno', 1, 200, field='max_daily_messages')
    out['max_overdue_days'] = v.integer(out['max_overdue_days'], 'Giorni di ritardo considerati', 1, 90, field='max_overdue_days')
    out['recipient_mode'] = v.choice(out['recipient_mode'], 'Destinatari', ('structure_hr', 'central_hr', 'both'),
                                     field='recipient_mode')
    out['central_hr_email'] = v.email(out['central_hr_email'], 'Email HR centrale', field='central_hr_email').casefold()
    if out['recipient_mode'] in ('central_hr', 'both') and not out['central_hr_email']:
        raise Invalid('Indicare l’email dell’ufficio HR centrale.', field='central_hr_email')
    return out


def routes(con, cfg):
    out, warnings = {}, []
    for c in con.execute('SELECT id, name FROM centers WHERE active=1 ORDER BY name, id'):
        if cfg['centers'] and c['id'] not in cfg['centers']:
            continue
        emails = set()
        if cfg['recipient_mode'] in ('structure_hr', 'both'):
            value = structures.record(con, c['id'])['fields']['hr_email']
            if value and v.is_email(value):
                emails.add(v.email(value).casefold())
            else:
                warnings.append(dict(center_id=c['id'], message=f'{c["name"]}: recapito HR della struttura assente o non valido.'))
        if cfg['recipient_mode'] in ('central_hr', 'both'):
            emails.add(cfg['central_hr_email'])
        out[c['id']] = sorted(emails)
    if not out:
        warnings.append(dict(center_id='', message='Nessuna struttura selezionata.'))
    return out, warnings


def _offset(cfg, due, on, overdue_only=False):
    delta = (due - on).days
    if delta < -cfg['max_overdue_days']:
        return None
    if overdue_only:
        return 0 if delta <= 0 else None
    if delta < 0:
        return 0 if 0 in cfg['offsets'] else None
    choices = [n for n in cfg['offsets'] if delta <= n]  # se il servizio era fermo, recupera la soglia più recente una volta
    return min(choices) if choices else None


def candidates(con, cfg, route_map, on):
    rows = []

    def add(center_id, topic, key, due, label):
        if topic not in cfg['topics'] or not due:
            return
        try:
            when = date.fromisoformat(due)
        except (TypeError, ValueError):
            return
        threshold = _offset(cfg, when, on, topic in ('onboarding', 'attendance'))
        if threshold is None:
            return
        for email in route_map.get(center_id, []):
            event = hashlib.sha256(dumps([center_id, key, due, threshold, email]).encode()).hexdigest()
            previous = con.execute('SELECT r.status FROM reminder_events e JOIN mail_recipients r ON r.id=e.recipient_id '
                                   'WHERE e.event_key=?', (event,)).fetchone()
            rows.append(dict(event_key=event, center_id=center_id, source_key=key, due=due, threshold=threshold, email=email,
                             topic=topic, label=label, status=previous['status'] if previous else 'pending'))

    for center_id in route_map:
        for p in months.people(con, center_id):
            prof = hr.profile(con, p['id'])
            if not p['active'] or prof['stage'] == 'ended':
                continue
            for key, topic in FIELD_TOPICS:
                add(center_id, topic, f'profile:{p["id"]}:{key}', prof['fields'].get(key, ''), p['name'])
            for d in con.execute('SELECT id, expiry FROM documents WHERE person_id=?', (p['id'],)):
                add(center_id, 'document', f'document:{d["id"]}', d['expiry'], p['name'])
            for t in hr.tasks_of(con, p['id']):
                if t['status'] not in ('done', 'na'):
                    add(center_id, 'onboarding', f'onboarding:{p["id"]}:{t["id"]}', t['due'], p['name'])
        last = previous_month(on.strftime('%Y-%m'))
        state = months.get(con, center_id, last)
        has_entries = con.execute('SELECT 1 FROM entries WHERE center_id=? AND day>=? AND day<=? LIMIT 1',
                                  (center_id, *months.bounds(last))).fetchone()
        if has_entries and not state['closed'] and not state['verified']:
            add(center_id, 'attendance', f'attendance:{last}', on.replace(day=1).isoformat(), last)
    return sorted(rows, key=lambda x: (x['due'], x['center_id'], x['topic'], x['source_key'], x['email']))


def messages(con, rows):
    grouped = defaultdict(list)
    for r in rows:
        if r['status'] == 'pending':
            grouped[r['center_id'], r['email']].append(r)
    out = []
    for (center_id, email), events in sorted(grouped.items()):
        name = centers.row(con, center_id)['name']
        counts = Counter(e['topic'] for e in events)
        body = (f'Ci sono attività da controllare nel portale NefroCenter WR per {name}.\n\n'
                + '\n'.join(f'{TOPICS[k]}: {n}' for k, n in sorted(counts.items()))
                + '\n\nAccedi al portale aziendale con il tuo account per vedere dettagli e scadenze. Questo messaggio non '
                  'contiene nomi di dipendenti né allegati.\n\nUfficio HR · promemoria automatico')
        out.append(dict(center_id=center_id, email=email, name=f'Ufficio HR · {name}', subject=f'Promemoria HR · {name}',
                        body=body, event_keys=[e['event_key'] for e in events], count=len(events)))
    return out


def _preview(con, raw, now):
    current = settings(con)
    cfg = validate_config(con, raw)
    route_map, warnings = routes(con, cfg)
    rows = candidates(con, cfg, route_map, now.date())
    msgs = messages(con, rows)
    fingerprint = hashlib.sha256(dumps(dict(version=current['version'], config=cfg, routes=route_map, date=now.date().isoformat(),
                                            mail_version=mail.settings(con)['version'])).encode()).hexdigest()
    return dict(config=cfg, routes=route_map, warnings=warnings, candidates=rows[:500], total_events=len(rows),
                pending_events=sum(r['status'] == 'pending' for r in rows), messages=msgs[:100], total_messages=len(msgs),
                fingerprint=fingerprint, can_enable=bool(route_map) and not warnings and all(route_map.values()),
                date=now.date().isoformat(), timezone=str(ZONE))


def preview(db, user, raw=None, now=None):
    now = clock(now)
    with db.read() as con:
        require(users.reload(con, user), 'promemoria.vedi')
        if raw is None:
            current = settings(con)
            raw = {k: current[k] for k in DEFAULTS}
        return _preview(con, raw, now)


def configure(db, actor, raw, now=None):
    now = clock(now)
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'promemoria.configura')
        old = settings(con)
        if v.version(raw.get('version')) != old['version']:
            raise Conflict('Configurazione cambiata: ricaricare prima di salvare.')
        view = _preview(con, raw, now)
        cfg = view['config']
        if cfg['enabled']:
            if (raw.get('confirmed') is not True or not isinstance(raw.get('fingerprint'), str)
                    or not hmac.compare_digest(raw['fingerprint'], view['fingerprint'])):
                raise Invalid('Generare l’anteprima e confermare i destinatari prima di attivare i promemoria.', field='confirmed')
            if not view['can_enable']:
                raise Invalid('Correggere i recapiti HR mancanti o non validi prima di attivare.')
            if not mail.ready(mail.settings(con)):
                raise Invalid('Prima configurare e attivare il server di posta aziendale.')
        cfg['approved_routes'] = view['routes'] if cfg['enabled'] else {}
        con.execute('''INSERT INTO reminder_settings(id,data,version,enabled_by) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET
                       data=excluded.data, version=excluded.version, enabled_by=excluded.enabled_by''',
                    (dumps(cfg), old['version'] + 1, actor.id if cfg['enabled'] else ''))
        audit.record(con, actor, 'Promemoria ' + ('attivati' if cfg['enabled'] else 'configurati (non attivi)'),
                     entity='reminders', entity_id='1', after=dict(enabled=cfg['enabled'], version=old['version'] + 1,
                                                                    recipient_mode=cfg['recipient_mode']))
    return overview(db, actor, now)


def overview(db, user, now=None):
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'promemoria.vedi')
        cfg = settings(con)
        route_map, warnings = routes(con, cfg)
        changed = [c for c in route_map if route_map[c] != cfg.get('approved_routes', {}).get(c)] if cfg['enabled'] else []
        history = []
        for r in con.execute('''SELECT r.id, r.status, r.error, r.data, min(e.created_at) AS created_at, count(e.event_key) AS events
                                FROM reminder_events e JOIN mail_recipients r ON r.id=e.recipient_id
                                GROUP BY r.id ORDER BY created_at DESC, r.id DESC LIMIT 100'''):
            data = loads(r['data'])
            history.append(dict(id=r['id'], status=r['status'], status_label=mail.STATUS_LABELS[r['status']], error=r['error'],
                                email=data['email'], center_id=data['center_id'], name=data['name'], subject=data['subject'],
                                body=data['body'], created_at=r['created_at'], events=r['events']))
        return dict(config={k: cfg[k] for k in ['version', *DEFAULTS]}, can_configure=has(user, 'promemoria.configura'),
                    topics=[dict(id=k, label=label) for k, label in TOPICS.items()],
                    centers=[dict(id=r['id'], name=r['name'], code=r['code']) for r in con.execute(
                        'SELECT id, name, code FROM centers WHERE active=1 ORDER BY name')],
                    smtp_ready=mail.ready(mail.settings(con)), warnings=warnings, changed_routes=changed, history=history,
                    runs=[dict(r) for r in con.execute('SELECT * FROM reminder_runs ORDER BY at DESC, id DESC LIMIT 20')],
                    timezone=str(ZONE))


def after_restore(con):
    """Nella transazione di «after-restore»: disattiva e marca come incerti gli invii in sospeso."""
    cfg = settings(con)
    values = {k: cfg[k] for k in DEFAULTS}
    values.update(enabled=False, approved_routes={})
    con.execute('''INSERT INTO reminder_settings(id,data,version,enabled_by) VALUES(1,?,?,'') ON CONFLICT(id) DO UPDATE SET
                   data=excluded.data, version=excluded.version, enabled_by=''
                ''', (dumps(values), cfg['version'] + 1))
    reason = 'Backup ripristinato: verificare lo storico del server di posta; nessun reinvio automatico.'
    for r in con.execute("SELECT id FROM mail_recipients WHERE id IN (SELECT recipient_id FROM reminder_events) "
                         "AND status IN ('pending','sending')").fetchall():
        mail.mark_uncertain(con, r['id'], reason)


def run(db, now=None, transport=None):
    """Controllo periodico del servizio. Nessun invio se promemoria e posta non sono entrambi attivi."""
    local = clock(now)
    epoch = local.timestamp()
    batch = new_id()
    transport = transport or mail.smtp_send
    claimed, groups = [], []
    with db.write() as con:
        cfg = settings(con)
        smtp = mail.settings(con)
        for r in con.execute('''SELECT DISTINCT r.id FROM reminder_events e JOIN mail_recipients r ON r.id=e.recipient_id
                                WHERE r.status='sending' AND r.claimed_at<?''', (epoch - mail.STALE_SECONDS,)).fetchall():
            mail.mark_uncertain(con, r['id'], 'Promemoria interrotto: esito incerto da verificare con il server di posta.')
        if not cfg['enabled'] or not mail.ready(smtp):
            return dict(state='disabled', messages=0)
        if not con.execute("SELECT 1 FROM users WHERE id=? AND role='admin' AND active=1", (cfg['enabled_by'],)).fetchone():
            return dict(state='authorization_changed', messages=0)
        if local.hour < cfg['hour']:
            return dict(state='waiting', messages=0)
        route_map, _ = routes(con, cfg)
        valid = {c: e for c, e in route_map.items() if e == cfg.get('approved_routes', {}).get(c)}
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        hourly = con.execute('SELECT count(*) FROM mail_attempts WHERE started_epoch>?', (epoch - 3600,)).fetchone()[0]
        daily = con.execute('''SELECT count(DISTINCT a.id) FROM mail_attempts a JOIN reminder_events e ON e.recipient_id=a.recipient_id
                               WHERE a.started_epoch>=?''', (day_start,)).fetchone()[0]
        available = min(smtp['batch_size'], max(0, smtp['max_per_hour'] - hourly), max(0, cfg['max_daily_messages'] - daily))
        if not available:
            return dict(state='rate_limited', messages=0)
        rows = candidates(con, cfg, valid, local.date())
        groups = messages(con, rows)[:available]
        if not groups:
            return dict(state='no_work' if len(valid) == len(route_map) else 'recipients_changed', messages=0)
        campaign_id = new_id()
        data = dict(name=f'Promemoria automatici · {local.date().isoformat()}', subject='Promemoria automatici HR',
                    body='Riepiloghi per struttura; il contenuto di ogni messaggio è nello storico.', warnings=[],
                    template_id='automatic-reminders', list_id='automatic-hr-reminders',
                    fingerprint=hashlib.sha256(dumps(groups).encode()).hexdigest())
        con.execute("INSERT INTO mail_campaigns(id,source,data,created_at,created_by) VALUES(?,'reminders',?,?,?)",
                    (campaign_id, dumps(data), stamp(), SYSTEM.username))
        by_key = {r['event_key']: r for r in rows}
        domain = smtp['from_email'].rsplit('@', 1)[1]
        for ordinal, message in enumerate(groups):
            rid, aid = new_id(), new_id()
            recipient = {k: val for k, val in message.items() if k not in ('event_keys', 'count')}
            con.execute("INSERT INTO mail_recipients(id,campaign_id,ordinal,data,status,claimed_at,batch_id) "
                        "VALUES(?,?,?,?,'sending',?,?)", (rid, campaign_id, ordinal, dumps(recipient), epoch, batch))
            con.execute("INSERT INTO mail_attempts(id,recipient_id,number,status,started_at,started_epoch,message_id) "
                        "VALUES(?,?,1,'sending',?,?,?)", (aid, rid, stamp(), epoch, f'<{aid}@{domain}>'))
            for key in message['event_keys']:
                e = by_key[key]
                con.execute('''INSERT INTO reminder_events(event_key,center_id,source_key,due,threshold,email,topic,created_at,recipient_id)
                               VALUES(?,?,?,?,?,?,?,?,?)''', (key, e['center_id'], e['source_key'], e['due'], e['threshold'],
                                                              e['email'], e['topic'], stamp(), rid))
            claimed.append((rid, aid, f'<{aid}@{domain}>', recipient))
        audit.record(con, SYSTEM, 'Promemoria automatici prenotati', entity='reminders', entity_id=campaign_id,
                     after=dict(messages=len(claimed), events=sum(g['count'] for g in groups)))
    for rid, aid, message_id, recipient in claimed:
        with db.write() as con:
            current, current_smtp = settings(con), mail.settings(con)
            claim = con.execute("SELECT 1 FROM mail_recipients WHERE id=? AND status='sending' AND batch_id=?", (rid, batch)).fetchone()
            route_map, _ = routes(con, current)
            owner = con.execute("SELECT 1 FROM users WHERE id=? AND role='admin' AND active=1", (current['enabled_by'],)).fetchone()
            allowed = bool(claim and owner and current['enabled'] and current['version'] == cfg['version']
                           and current_smtp['version'] == smtp['version'] and mail.ready(current_smtp)
                           and route_map.get(recipient['center_id']) == cfg['approved_routes'].get(recipient['center_id']))
            con.execute("UPDATE mail_recipients SET claimed_at=? WHERE batch_id=? AND status='sending'", (time.time(), batch))
        status, error = (transport(smtp, recipient, message_id) if allowed else
                         ('failed', 'Configurazione o destinatario cambiati: nessun invio eseguito.'))
        with db.write() as con:
            if con.execute("SELECT 1 FROM mail_recipients WHERE id=? AND status='sending' AND batch_id=?", (rid, batch)).fetchone():
                con.execute('UPDATE mail_attempts SET status=?, finished_at=?, error=? WHERE id=?', (status, stamp(), error, aid))
                con.execute("UPDATE mail_recipients SET status=?, error=?, batch_id='' WHERE id=? AND batch_id=?",
                            (status, error, rid, batch))
    with db.write() as con:
        con.execute('INSERT INTO reminder_runs(id,at,state,messages,events,note) VALUES(?,?,?,?,?,?)',
                    (batch, stamp(), 'completed', len(claimed), sum(g['count'] for g in groups),
                     'Accettato dal server di posta non significa consegnato. Nessun nuovo tentativo automatico.'))
    return dict(state='completed', messages=len(claimed))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/reminders', cap='promemoria.vedi')
def api_overview(ctx):
    return overview(ctx.db, ctx.user)


@route('POST', '/api/reminders/preview', cap='promemoria.vedi')
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.body or None)


@route('PUT', '/api/reminders', cap='promemoria.configura', step_up=True)
def api_configure(ctx):
    return configure(ctx.db, ctx.user, ctx.body)
