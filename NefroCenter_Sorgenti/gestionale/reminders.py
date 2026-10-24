"""Promemoria HR automatici, disattivati fino a configurazione e verifica dei destinatari.

Il worker condivide trasporto SMTP, registro tentativi e limite orario delle
comunicazioni. Ogni evento ha una chiave stabile; errori e risultati incerti non
vengono reinviati automaticamente. Le email contengono solo conteggi per sede.
"""
import hashlib
import hmac
import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import communications as mail
import hr
import structures

ZONE = ZoneInfo('Europe/Rome')
TOPICS = {'contract': 'Contratti e periodo di prova', 'document': 'Documenti',
          'qualification': 'Qualifiche e verifiche', 'onboarding': 'Onboarding in ritardo',
          'attendance': 'Presenze del mese precedente da verificare'}
DEFAULTS = dict(enabled=False, centers=[], topics=list(TOPICS), offsets=[30,15,7,0],
                recipient_mode='structure_hr', central_hr_email='', hour=8,
                max_daily_messages=20, max_overdue_days=30)
SYSTEM = {'username': 'promemoria-automatici'}


def init(app):
    with app.connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS reminder_settings(
            id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL,
            data TEXT NOT NULL, enabled_by TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS reminder_events(
            event_key TEXT PRIMARY KEY, cid TEXT NOT NULL, source_key TEXT NOT NULL,
            due TEXT NOT NULL, threshold INTEGER NOT NULL, email TEXT NOT NULL,
            topic TEXT NOT NULL, created_at TEXT NOT NULL,
            recipient_id TEXT NOT NULL REFERENCES communication_recipients(id));
        CREATE INDEX IF NOT EXISTS reminder_event_recipient ON reminder_events(recipient_id);
        CREATE TABLE IF NOT EXISTS reminder_runs(
            id TEXT PRIMARY KEY, stamp TEXT NOT NULL, state TEXT NOT NULL,
            messages INTEGER NOT NULL, events INTEGER NOT NULL, note TEXT NOT NULL);
        '''); c.commit()


def _clock(now=None):
    if now is None:
        return datetime.now(ZONE)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('Il controllo dei promemoria richiede data e fuso orario.')
    return now.astimezone(ZONE)


def _access(app, c, user, admin=False):
    user=app.fresh_user(c,user)
    if user['role'] not in ('admin','hr') or (admin and user['role']!='admin'):
        raise PermissionError('Promemoria riservati a HR centrale e amministratori; la configurazione è solo dell’amministratore.')
    return user


def _settings(c):
    row=c.execute('SELECT * FROM reminder_settings WHERE id=1').fetchone()
    return dict(version=row['version'] if row else 0, enabled_by=row['enabled_by'] if row else '',
                **(json.loads(row['data']) if row else {**DEFAULTS,'approved_routes':{}}))


def _validate(app,c,raw):
    if not isinstance(raw,dict):raise ValueError('Configurazione promemoria non valida.')
    if set(raw)-set(DEFAULTS)-{'version','fingerprint','confirmed'}:
        raise ValueError('Campi della configurazione non previsti.')
    result={**DEFAULTS,**{k:raw[k] for k in DEFAULTS if k in raw}}
    if type(result['enabled']) is not bool:raise ValueError('Abilitazione non valida.')
    for key,allowed,maximum in [('centers',{r['id'] for r in c.execute('SELECT id FROM centers')},1000),('topics',set(TOPICS),len(TOPICS))]:
        value=result[key]
        if not isinstance(value,list) or len(value)>maximum or any(not isinstance(x,str) for x in value) or set(value)-allowed:
            raise ValueError('Selezione '+key+' non valida.')
        result[key]=sorted(set(value))
    offsets=result['offsets']
    if not isinstance(offsets,list) or not offsets or len(offsets)>8 or any(type(x) is not int or not 0<=x<=365 for x in offsets):
        raise ValueError('Indicare da uno a otto anticipi, in giorni da 0 a 365.')
    result['offsets']=sorted(set(offsets),reverse=True)
    for key,low,high in [('hour',0,23),('max_daily_messages',1,200),('max_overdue_days',1,90)]:
        if type(result[key]) is not int or not low<=result[key]<=high:raise ValueError('Valore non valido: '+key)
    if result['recipient_mode'] not in ('structure_hr','central_hr','both'):raise ValueError('Destinazione non valida.')
    address=result['central_hr_email']
    if not isinstance(address,str):raise ValueError('Email HR centrale non valida.')
    result['central_hr_email']=mail._email(address).casefold() if address.strip() else ''
    if result['recipient_mode'] in ('central_hr','both') and not result['central_hr_email']:
        raise ValueError('Indicare esplicitamente l’email dell’ufficio HR centrale.')
    if not result['topics']:raise ValueError('Selezionare almeno un tipo di promemoria.')
    return result


def _routes(app,c,config):
    routes={};warnings=[]
    for ct in c.execute('SELECT id,name FROM centers ORDER BY name,id'):
        cid=ct['id']
        if config['centers'] and cid not in config['centers']:continue
        emails=set()
        if config['recipient_mode'] in ('structure_hr','both'):
            value=structures.record(c,cid)['fields']['hr_email']
            try:emails.add(mail._email(value).casefold())
            except ValueError:warnings.append({'cid':cid,'message':ct['name']+': recapito HR della struttura assente o non valido.'})
        if config['recipient_mode'] in ('central_hr','both'):emails.add(config['central_hr_email'])
        routes[cid]=sorted(emails)
    if not routes:warnings.append({'cid':'','message':'Nessuna struttura selezionata.'})
    return routes,warnings


def _offset(config,due,today,overdue_only=False):
    delta=(due-today).days
    if delta < -config['max_overdue_days']:return None
    if overdue_only:return 0 if delta<=0 else None
    if delta<0:return 0 if 0 in config['offsets'] else None
    # If the server missed the exact day, recover the latest due threshold once.
    choices=[n for n in config['offsets'] if delta<=n]
    return min(choices) if choices else None


def _candidates(app,c,config,routes,today):
    rows=[]
    def add(cid,topic,key,due,label):
        if topic not in config['topics'] or not due:return
        try:due_date=date.fromisoformat(due)
        except (ValueError,TypeError):return
        threshold=_offset(config,due_date,today,topic in ('onboarding','attendance'))
        if threshold is None:return
        for email in routes.get(cid,[]):
            event_key=hashlib.sha256(app.dump([cid,key,due,threshold,email]).encode()).hexdigest()
            previous=c.execute('SELECT r.status FROM reminder_events e JOIN communication_recipients r ON r.id=e.recipient_id WHERE e.event_key=?',(event_key,)).fetchone()
            rows.append(dict(event_key=event_key,cid=cid,source_key=key,due=due,threshold=threshold,
                             email=email,topic=topic,label=label,status=previous['status'] if previous else 'pending'))
    for cid in routes:
        for person in app.objects(c,'people',cid):
            p=hr.profile(c,cid,person['id'])
            if not person.get('active',True) or p.get('stage')=='ended':continue
            f=p['fields'];pid=person['id']
            for key,topic in [('end_date','contract'),('probation_end','contract'),('identity_expiry','document'),('registration_expiry','qualification'),('work_permit_expiry','qualification'),('next_review','qualification')]:
                add(cid,topic,'profile:'+pid+':'+key,f.get(key,''),person['name'])
            for doc in c.execute('SELECT id,expiry FROM hr_documents WHERE cid=? AND pid=?',(cid,pid)):
                add(cid,'document','document:'+doc['id'],doc['expiry'],person['name'])
            for task in p.get('tasks',[]):
                if task.get('status') not in ('done','na'):
                    add(cid,'onboarding','onboarding:'+pid+':'+str(task['id']),task.get('due',''),person['name'])
        previous=(today.replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
        period=c.execute('SELECT data FROM periods WHERE cid=? AND month=?',(cid,previous)).fetchone()
        data=json.loads(period['data']) if period else {}
        exists=any(str(e.get('day','')).startswith(previous+'-') for e in app.objects(c,'entries',cid))
        if exists and not data.get('closed') and not data.get('verified'):
            add(cid,'attendance','attendance:'+previous,today.replace(day=1).isoformat(),previous)
    return sorted(rows,key=lambda x:(x['due'],x['cid'],x['topic'],x['source_key'],x['email']))


def _messages(app,c,candidates):
    grouped=defaultdict(list)
    for row in candidates:
        if row['status']=='pending':grouped[row['cid'],row['email']].append(row)
    out=[]
    for (cid,email),events in sorted(grouped.items()):
        center=app.center(c,cid);counts=Counter(e['topic'] for e in events)
        subject=mail._text('Promemoria HR · '+center['name'],'Oggetto',300)
        body='Sono presenti attività da controllare nel portale NefroCenter per '+center['name']+'.\n\n'
        body+='\n'.join(TOPICS[k]+': '+str(v) for k,v in sorted(counts.items()))
        body+='\n\nAccedi al portale aziendale con il tuo account autorizzato per vedere dettagli e scadenze. Questo messaggio non contiene nomi di dipendenti o allegati.\n\nUfficio HR · Promemoria automatico'
        out.append(dict(cid=cid,email=email,name='Ufficio HR · '+center['name'],subject=subject,body=body,
                        event_keys=[e['event_key'] for e in events],count=len(events)))
    return out


def _preview(app,c,raw,now):
    current=_settings(c);config=_validate(app,c,raw);routes,warnings=_routes(app,c,config)
    candidates=_candidates(app,c,config,routes,now.date());messages=_messages(app,c,candidates)
    fingerprint=hashlib.sha256(app.dump(dict(version=current['version'],config=config,routes=routes,
                    date=now.date().isoformat(),mail_version=mail._configuration(c)['version'])).encode()).hexdigest()
    return dict(config=config,routes=routes,warnings=warnings,candidates=candidates[:500],
                total_events=len(candidates),pending_events=sum(e['status']=='pending' for e in candidates),
                messages=messages[:100],total_messages=len(messages),fingerprint=fingerprint,
                can_enable=bool(routes) and not warnings and all(routes.values()),date=now.date().isoformat(),timezone='Europe/Rome')


def preview(app,user,body=None,now=None):
    now=_clock(now)
    with app.connect() as c:
        c.execute('BEGIN');_access(app,c,user)
        raw=body if body is not None else {k:_settings(c)[k] for k in DEFAULTS}
        return _preview(app,c,raw,now)


def configure(app,user,body,now=None):
    if not isinstance(body,dict):raise ValueError('Configurazione promemoria non valida.')
    now=_clock(now)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,True);old=_settings(c)
        if type(body.get('version')) is not int or body['version']!=old['version']:raise ValueError('Configurazione cambiata: ricarica prima di salvare.')
        view=_preview(app,c,body,now);config=view['config']
        if config['enabled']:
            if body.get('confirmed') is not True or not isinstance(body.get('fingerprint'),str) or not hmac.compare_digest(body['fingerprint'],view['fingerprint']):
                raise ValueError('Genera l’anteprima e conferma i destinatari prima di abilitare i promemoria.')
            if not view['can_enable']:raise ValueError('Correggere i recapiti HR mancanti o non validi prima di abilitare.')
            smtp=mail._configuration(c)
            if not smtp['enabled'] or not mail._configured(smtp):raise ValueError('Prima configura e abilita il servizio SMTP aziendale.')
        config['approved_routes']=view['routes'] if config['enabled'] else {}
        c.execute('INSERT INTO reminder_settings VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data,enabled_by=excluded.enabled_by',
                  (old['version']+1,app.dump(config),user['id']))
        app.audit(c,user,'Configurazione promemoria salvata',after={'enabled':config['enabled'],'version':old['version']+1,'recipient_mode':config['recipient_mode']})
        c.commit()
    return overview(app,user,now)


def overview(app,user,now=None):
    now=_clock(now)
    with app.connect() as c:
        c.execute('BEGIN');user=_access(app,c,user);config=_settings(c);routes,warnings=_routes(app,c,config)
        changed=[cid for cid in routes if routes[cid]!=config.get('approved_routes',{}).get(cid)] if config['enabled'] else []
        history=[]
        for row in c.execute('''SELECT r.id,r.status,r.error,r.data, min(e.created_at) AS created_at,count(e.event_key) AS event_count
                 FROM reminder_events e JOIN communication_recipients r ON r.id=e.recipient_id
                 GROUP BY r.id ORDER BY created_at DESC,r.id DESC LIMIT 100'''):
            data=json.loads(row['data']);history.append(dict(id=row['id'],status='sent' if row['status']=='accepted' else row['status'],error=row['error'],
                    email=data['email'],cid=data['cid'],name=data['name'],subject=data['subject'],body=data['body'],created_at=row['created_at'],event_count=row['event_count']))
        smtp=mail._configuration(c)
        return dict(config={k:config[k] for k in ['version',*DEFAULTS]},can_configure=user['role']=='admin',
                    topics=[dict(id=k,label=v) for k,v in TOPICS.items()],centers=[dict(r) for r in c.execute('SELECT id,name,code FROM centers ORDER BY name')],
                    smtp_ready=bool(smtp['enabled'] and mail._configured(smtp)),warnings=warnings,changed_routes=changed,
                    history=history,runs=[dict(r) for r in c.execute('SELECT * FROM reminder_runs ORDER BY stamp DESC,id DESC LIMIT 20')],timezone='Europe/Rome')


def after_restore(app,c):
    """Use inside manage.py's existing restore transaction, without committing."""
    config=_settings(c)
    values={k:config[k] for k in DEFAULTS};values.update(enabled=False,approved_routes={})
    c.execute('INSERT INTO reminder_settings VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data,enabled_by=excluded.enabled_by',
              (config['version']+1,app.dump(values),''))
    reason='Backup ripristinato: verificare lo storico SMTP; nessun reinvio automatico.'
    c.execute("UPDATE communication_recipients SET status='uncertain',error=?,batch_id='' WHERE id IN (SELECT recipient_id FROM reminder_events) AND status IN ('pending','sending')",(reason,))
    c.execute("UPDATE communication_attempts SET status='uncertain',finished_at=?,error=? WHERE recipient_id IN (SELECT recipient_id FROM reminder_events) AND status='sending'",(app.now(),reason))


def run(app,now=None):
    """Periodic background tick. No SMTP call unless both services are enabled."""
    local=_clock(now);epoch=local.timestamp();batch=app.uid();claimed=[]
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');config=_settings(c);smtp=mail._configuration(c)
        stale=list(c.execute("SELECT DISTINCT r.id FROM reminder_events e JOIN communication_recipients r ON r.id=e.recipient_id WHERE r.status='sending' AND r.claimed_at<?",(epoch-mail.STALE_BATCH_SECONDS,)))
        for row in stale:
            reason='Promemoria interrotto: esito incerto da verificare con il servizio SMTP.'
            c.execute("UPDATE communication_recipients SET status='uncertain',error=?,batch_id='' WHERE id=?",(reason,row['id']))
            c.execute("UPDATE communication_attempts SET status='uncertain',finished_at=?,error=? WHERE recipient_id=? AND status='sending'",(app.now(),reason,row['id']))
        if not config['enabled'] or not smtp['enabled'] or not mail._configured(smtp):
            c.commit();return {'state':'disabled','messages':0}
        owner=c.execute("SELECT 1 FROM users WHERE id=? AND role='admin' AND active=1",(config['enabled_by'],)).fetchone()
        if not owner:c.commit();return {'state':'authorization_changed','messages':0}
        if local.hour<config['hour']:c.commit();return {'state':'waiting','messages':0}
        routes,warnings=_routes(app,c,config)
        valid_routes={cid:emails for cid,emails in routes.items() if emails==config.get('approved_routes',{}).get(cid)}
        day_start=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        hourly=c.execute('SELECT count(*) FROM communication_attempts WHERE started_epoch>?',(epoch-3600,)).fetchone()[0]
        daily=c.execute('''SELECT count(DISTINCT a.id) FROM communication_attempts a JOIN reminder_events e ON e.recipient_id=a.recipient_id WHERE a.started_epoch>=?''',(day_start,)).fetchone()[0]
        available=min(smtp['batch_size'],max(0,smtp['max_per_hour']-hourly),max(0,config['max_daily_messages']-daily))
        if not available:c.commit();return {'state':'rate_limited','messages':0}
        candidates=_candidates(app,c,config,valid_routes,local.date());groups=_messages(app,c,candidates)[:available]
        if not groups:c.commit();return {'state':'no_work' if len(valid_routes)==len(routes) else 'recipients_changed','messages':0}
        campaign_id=app.uid();fingerprint=hashlib.sha256(app.dump(groups).encode()).hexdigest()
        campaign=dict(name='Promemoria automatici · '+local.date().isoformat(),subject='Promemoria automatici HR',body='Riepiloghi per struttura; contenuto individuale nello storico.',warnings=[],
                      template_id='automatic-reminders',list_id='automatic-hr-reminders',fingerprint=fingerprint,source='reminders')
        c.execute('INSERT INTO communication_campaigns VALUES(?,?,?,?)',(campaign_id,app.now(),SYSTEM['username'],app.dump(campaign)))
        bykey={e['event_key']:e for e in candidates}
        for ordinal,message in enumerate(groups):
            rid=app.uid();aid=app.uid();message_id='<'+aid+'@'+smtp['from_email'].rsplit('@',1)[1]+'>'
            recipient={k:v for k,v in message.items() if k not in ('event_keys','count')}
            c.execute("INSERT INTO communication_recipients(id,campaign_id,ordinal,data,status,claimed_at,batch_id) VALUES(?,?,?,?,'sending',?,?)",(rid,campaign_id,ordinal,app.dump(recipient),epoch,batch))
            c.execute("INSERT INTO communication_attempts(id,recipient_id,number,status,started_at,started_epoch,message_id) VALUES(?,?,1,'sending',?,?,?)",(aid,rid,app.now(),epoch,message_id))
            for key in message['event_keys']:
                e=bykey[key];c.execute('INSERT INTO reminder_events VALUES(?,?,?,?,?,?,?,?,?)',(key,e['cid'],e['source_key'],e['due'],e['threshold'],e['email'],e['topic'],app.now(),rid))
            claimed.append((rid,aid,message_id,recipient))
        app.audit(c,SYSTEM,'Promemoria automatici prenotati',after={'campaign_id':campaign_id,'messages':len(claimed),'events':sum(g['count'] for g in groups)})
        c.commit()
    for rid,aid,message_id,recipient in claimed:
        with app.connect() as c:
            c.execute('BEGIN IMMEDIATE');current=_settings(c);current_smtp=mail._configuration(c)
            claim=c.execute("SELECT 1 FROM communication_recipients WHERE id=? AND status='sending' AND batch_id=?",(rid,batch)).fetchone()
            routes,_=_routes(app,c,current)
            owner=c.execute("SELECT 1 FROM users WHERE id=? AND role='admin' AND active=1",(current['enabled_by'],)).fetchone()
            allowed=bool(claim and owner and current['enabled'] and current['version']==config['version'] and current_smtp['enabled'] and
                         current_smtp['version']==smtp['version'] and mail._configured(current_smtp) and
                         routes.get(recipient['cid'])==config['approved_routes'].get(recipient['cid']))
            c.execute("UPDATE communication_recipients SET claimed_at=? WHERE batch_id=? AND status='sending'",(time.time(),batch));c.commit()
        status,error=mail._send_one(smtp,recipient,message_id) if allowed else ('failed','Configurazione o destinatario cambiato: nessun invio eseguito.')
        with app.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # A restore or reconciliation may have revoked this claim meanwhile.
            active=c.execute("SELECT 1 FROM communication_recipients WHERE id=? AND status='sending' AND batch_id=?",(rid,batch)).fetchone()
            if active:
                c.execute('UPDATE communication_attempts SET status=?,finished_at=?,error=? WHERE id=?',(status,app.now(),error,aid))
                c.execute("UPDATE communication_recipients SET status=?,error=?,batch_id='' WHERE id=? AND batch_id=?",(status,error,rid,batch))
            c.commit()
    with app.connect() as c:
        c.execute('INSERT INTO reminder_runs VALUES(?,?,?,?,?,?)',(batch,app.now(),'completed',len(claimed),sum(g['count'] for g in groups),'Accettazione SMTP non equivale a consegna. Nessun ritentativo automatico.'))
        c.commit()
    return {'state':'completed','messages':len(claimed),'campaign_id':campaign_id}
