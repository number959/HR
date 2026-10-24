"""Regole e archivio condiviso di Persone e Presenze Web. Nessun listener HTTP."""
import argparse, base64, copy, csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, sys, threading, time, uuid, webbrowser, zipfile
from contextlib import contextmanager
from datetime import date, datetime
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from rules import defaults, validate_config, make_entry, totals, duration, month_days
from engine import simulate_legacy_pay
from import_excel import read_model
import hr
import agreements
import backup_tools
import workforce
import payroll
import structures
import communications
import approvals, document_reviews, reminders, staffing, departures

BASE=Path(__file__).resolve().parent
DB=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PresenzeCentri'/'presenze.sqlite3'
CSRF=secrets.token_urlsafe(32)
SESSIONS={};FAILURES={};PENDING={};LOCK=threading.RLock()
ITERATIONS=600000
class AuthenticationError(Exception):pass
class RateLimitError(Exception):pass

def uid():return uuid.uuid4().hex
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def dump(o):return json.dumps(o,ensure_ascii=False,separators=(',',':'))
@contextmanager
def connect():
    con=sqlite3.connect(DB,timeout=15);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
    try:yield con
    finally:con.close()
def init_db():
    DB.parent.mkdir(parents=True,exist_ok=True)
    if DB.exists():
        with connect() as c:
            upgrade=c.execute('PRAGMA user_version').fetchone()[0]<8
        if upgrade:_backup()
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,centers TEXT NOT NULL,active INTEGER NOT NULL,credential TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS centers(id TEXT PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,config TEXT NOT NULL,version INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS people(cid TEXT REFERENCES centers(id),id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
        CREATE TABLE IF NOT EXISTS entries(cid TEXT REFERENCES centers(id),id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
        CREATE TABLE IF NOT EXISTS patients(cid TEXT REFERENCES centers(id),id TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,id));
        CREATE TABLE IF NOT EXISTS periods(cid TEXT REFERENCES centers(id),month TEXT,data TEXT NOT NULL,PRIMARY KEY(cid,month));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT,stamp TEXT,username TEXT,action TEXT,before_data TEXT,after_data TEXT);
        CREATE TABLE IF NOT EXISTS imports(hash TEXT PRIMARY KEY,cid TEXT,month TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);

        ''');c.commit()
    structures.init(sys.modules[__name__])
    hr.init(sys.modules[__name__])
    document_reviews.init(sys.modules[__name__])
    workforce.init(sys.modules[__name__])
    payroll.init(sys.modules[__name__])
    communications.init(sys.modules[__name__])
    approvals.init(sys.modules[__name__])
    staffing.init(sys.modules[__name__])
    departures.init(sys.modules[__name__])
    reminders.init(sys.modules[__name__])
    with connect() as c:
        c.execute('PRAGMA user_version=8');c.commit()
    daily_backup()

def password_hash(password):
    if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Password da 12 a 256 caratteri.')
    salt=secrets.token_bytes(16);key=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS)
    return dump({'scheme':'pbkdf2-sha256','iterations':ITERATIONS,'salt':salt.hex(),'hash':key.hex()})
def verify_password(password,stored):
    if not isinstance(password,str) or len(password)>256:return False
    v=json.loads(stored);key=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(v['salt']),v['iterations'])
    return hmac.compare_digest(key.hex(),v['hash'])
def public_user(row):
    if not row:return None
    return {k:json.loads(row[k]) if k=='centers' else bool(row[k]) if k=='active' else row[k] for k in ('id','username','name','role','centers','active')}
def fresh_user(c,user):
    row=c.execute('SELECT * FROM users WHERE id=? AND active=1',(user['id'],)).fetchone()
    if not row:raise AuthenticationError('Account disabilitato. Accedere di nuovo.')
    return public_user(row)
def require_admin(user):
    if user['role']!='admin':raise PermissionError('Operazione riservata all’amministratore.')
def require_manager(user,cid):
    authorize(user,cid)
    if user['role'] not in ('admin','manager'):raise PermissionError('Operazione riservata al responsabile del centro.')
def require_hr(user,cid):
    authorize(user,cid)
    if user['role'] not in ('admin','manager','hr'):raise PermissionError('Operazione riservata ai responsabili HR autorizzati.')

def authorize(user,cid,write=False):
    if user['role'] not in ('admin','hr') and cid not in user['centers']:raise PermissionError('Centro non assegnato a questo utente.')
    if write and user['role'] in ('viewer','hr'):raise PermissionError('Il profilo non può modificare presenze e configurazione del centro.')
def center(c,cid):
    r=c.execute('SELECT * FROM centers WHERE id=?',(cid,)).fetchone()
    if not r:raise ValueError('Centro non trovato.')
    return {**dict(r),'config':json.loads(r['config'])}
def objects(c,table,cid):
    if table not in ('people','entries','patients'):raise ValueError('Archivio non valido.')
    return [json.loads(r[0]) for r in c.execute('SELECT data FROM '+table+' WHERE cid=?',(cid,))]
def put(c,table,cid,obj):
    if table not in ('people','entries','patients'):raise ValueError('Archivio non valido.')
    c.execute('INSERT INTO '+table+' VALUES(?,?,?) ON CONFLICT(cid,id) DO UPDATE SET data=excluded.data',(cid,obj['id'],dump(obj)))
    if table=='people':workforce.ensure_person(c,cid,obj['id'])
def audit(c,user,action,cid='',before=None,after=None):
    c.execute('INSERT INTO audit(cid,stamp,username,action,before_data,after_data) VALUES(?,?,?,?,?,?)',(cid,now(),user['username'],action,dump(before),dump(after)))
def period(c,ct,month):
    month_days(month)
    r=c.execute('SELECT data FROM periods WHERE cid=? AND month=?',(ct['id'],month)).fetchone()
    return json.loads(r[0]) if r else dict(closed=False,verified=False,config=ct['config'],version=ct['version'],note='')
def effective_rules(ct,p):
    return {**p['config'],**{k:v for k,v in ct['config'].items() if k.startswith('operator_')}}

def put_period(c,cid,month,p):
    c.execute('INSERT INTO periods VALUES(?,?,?) ON CONFLICT(cid,month) DO UPDATE SET data=excluded.data',(cid,month,dump(p)))
def centers_for(c,user):
    rows=[dict(r) for r in c.execute('SELECT id,name,code,version,revision FROM centers ORDER BY name')]
    return [r for r in rows if user['role'] in ('admin','hr') or r['id'] in user['centers']]
def revoke(user_id):
    with LOCK:
        for k in list(SESSIONS):
            if SESSIONS[k]['id']==user_id:SESSIONS.pop(k,None)

def setup(body):
    username=str(body.get('username','')).strip().casefold();name=str(body.get('name','')).strip();site=str(body.get('center_name','')).strip()
    if not re.fullmatch('[a-z0-9_.-]{3,60}',username) or not name or not site:raise ValueError('Indicare nome, centro e nome utente di 3–60 caratteri.')
    credential=password_hash(body.get('password'));pid=uid();cid=uid()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM users').fetchone():raise PermissionError('Configurazione iniziale già completata.')
        c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',(pid,username,name[:150],'admin','[]',1,credential))
        c.execute('INSERT INTO centers VALUES(?,?,?,?,?,0)',(cid,site[:150],'CENTRO-1',dump(defaults()),1))
        audit(c,{'username':username},'Configurazione iniziale',cid,after={'center':site});c.commit()
    return {'ok':True}

def login(body):
    username=str(body.get('username','')).strip().casefold();key=username[:60]
    with LOCK:
        n,until=FAILURES.get(key,(0,0))
        if until>time.monotonic():raise RateLimitError('Troppi tentativi. Riprovare fra cinque minuti.')
    with connect() as c:row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
    valid=row is not None and verify_password(body.get('password',''),row['credential'])
    if not valid:
        if row is None:hashlib.pbkdf2_hmac('sha256',b'invalid',b'constant-auth-salt',ITERATIONS)
        with LOCK:
            n=n+1 if until==0 else 1
            FAILURES[key]=(n,time.monotonic()+300 if n>=5 else 0)
        raise AuthenticationError('Nome utente o password non corretti.')
    sid=secrets.token_urlsafe(40)
    with LOCK:
        FAILURES.pop(key,None)
        SESSIONS[sid]={'id':row['id'],'last':time.monotonic(),'created':time.monotonic()}
    return sid,public_user(row)

def session(sid):
    with LOCK:
        s=SESSIONS.get(sid)
        if not s or time.monotonic()-s['last']>900 or time.monotonic()-s['created']>28800:
            SESSIONS.pop(sid,None);raise AuthenticationError('Sessione scaduta. Accedere di nuovo.')
        s['last']=time.monotonic();pid=s['id']
    with connect() as c:
        row=c.execute('SELECT * FROM users WHERE id=? AND active=1',(pid,)).fetchone()
    if not row:raise AuthenticationError('Account non disponibile.')
    return public_user(row)

def snapshot(user,cid,month):
    with connect() as c:
        user=fresh_user(c,user);authorize(user,cid);ct=center(c,cid);p=period(c,ct,month)
        people=objects(c,'people',cid);entries=objects(c,'entries',cid);rows=totals(people,entries,month)
        alerts=[]
        if not p['verified']:alerts.append('Calendario e parametri del mese da verificare dall’amministratore.')
        for r in rows:
            if r['missing']:alerts.append(r['name']+': '+str(r['missing'])+' turni senza orari.')
            if r['pending']:alerts.append(r['name']+': '+str(r['pending'])+' fasce pianificate da consuntivare.')
        cfg=effective_rules(ct,p);onmonth=[e for e in entries if e['day'].startswith(month)]
        patients=[v for v in objects(c,'patients',cid) if v['day'].startswith(month)]
        roles={v['id']:v['role'] for v in people};load=[]
        for pat in patients:
            es=[e for e in onmonth if e['day']==pat['day'] and e['slot']==pat['slot'] and e['kind']=='work' and e['layer']=='actual' and e['work_site']==ct['name']]
            nurses=len({e['person_id'] for e in es if roles[e['person_id']] in cfg['nurse_roles']});doctors=len({e['person_id'] for e in es if roles[e['person_id']] in cfg['doctor_roles']})
            load.append({**pat,'nurses':nurses,'doctors':doctors,'nurse_ratio':(pat['ordinary']+pat['isolated']*cfg['isolation_weight'])/nurses if nurses else None,'doctor_ratio':(pat['ordinary']+pat['isolated'])/doctors if doctors else None})
        history=[dict(r) for r in c.execute('SELECT stamp,username,action FROM audit WHERE cid=? ORDER BY id DESC LIMIT 60',(cid,))]
        centers=centers_for(c,user)
        users=[public_user(r) for r in c.execute('SELECT * FROM users ORDER BY username')] if user['role']=='admin' else []
        approval=approvals.metadata(sys.modules[__name__],c,user,ct,month)
    if user['role'] not in ('admin','manager','hr'):
        people=[{k:v for k,v in person.items() if k not in ('pay_override','note')} for person in people]
        rows=[{k:v for k,v in person.items() if k not in ('pay_override','note')} for person in rows]
    visible_period=copy.deepcopy(p)
    if user['role'] not in ('admin','manager','hr'):visible_period.pop('agreements',None)
    return dict(user=user,centers=centers,center=ct,approval=approval,period={**visible_period,'config':effective_rules(ct,p)},people=people,entries=onmonth,summary=rows,alerts=alerts,audit=history,users=users,workload=load,
        working_days=sum(date.fromisoformat(d).weekday() in cfg['weekdays'] and d not in cfg['holidays'] for d in month_days(month)))

def mutate(user,action,body):
    warnings=[];before=None;after=None;cid=body.get('cid','');newid=None;revoke_id=None
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');user=fresh_user(c,user)
        if action in ('center_create','user_save'):require_admin(user)
        if action in ('center_save','person','period_verify','close','reopen','patient','apply_rules','agreement_save'):require_manager(user,cid)
        if action=='user_save':
            raw=body['user'];pid=raw.get('id') or uid();old=c.execute('SELECT * FROM users WHERE id=?',(pid,)).fetchone();before=public_user(old)
            if raw.get('id') and not old:raise ValueError('Utente non trovato.')
            username=str(raw.get('username','')).strip().casefold();name=str(raw.get('name','')).strip();role=raw.get('role');active=raw.get('active',True)
            if not re.fullmatch('[a-z0-9_.-]{3,60}',username) or not name or role not in ('admin','manager','hr','operator','viewer') or type(active)!=bool:raise ValueError('Dati utente non validi.')
            assigned=raw.get('centers',[])
            if not isinstance(assigned,list) or any(not c.execute('SELECT 1 FROM centers WHERE id=?',(x,)).fetchone() for x in assigned):raise ValueError('Centri assegnati non validi.')
            if role not in ('admin','hr') and not assigned:raise ValueError('Assegnare almeno un centro.')
            if role in ('admin','hr'):assigned=[]
            if old and old['role']=='admin' and old['active'] and (role!='admin' or not active) and c.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:raise ValueError('Mantenere almeno un amministratore attivo.')
            credential=password_hash(raw['password']) if raw.get('password') else old['credential'] if old else None
            if not credential:raise ValueError('Impostare una password iniziale.')
            c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,name=excluded.name,role=excluded.role,centers=excluded.centers,active=excluded.active,credential=excluded.credential',(pid,username,name[:150],role,dump(list(set(assigned))),int(active),credential))
            after=public_user(c.execute('SELECT * FROM users WHERE id=?',(pid,)).fetchone());revoke_id=pid;cid=''
        elif action=='password':
            row=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
            if not verify_password(body.get('current',''),row['credential']):raise AuthenticationError('Password attuale non corretta.')
            c.execute('UPDATE users SET credential=? WHERE id=?',(password_hash(body.get('password')),user['id']));revoke_id=user['id'];cid='';after={'password_changed':True}
        elif action=='center_create':
            name=str(body.get('name','')).strip();code=str(body.get('code','')).strip().upper()
            if not name or not re.fullmatch('[A-Z0-9_-]{2,30}',code):raise ValueError('Nome e codice centro obbligatori; codice da 2 a 30 lettere/numeri.')
            cfg=center(c,body['copy_from'])['config'] if body.get('copy_from') else defaults()
            cid=uid();c.execute('INSERT INTO centers VALUES(?,?,?,?,?,0)',(cid,name[:150],code,dump(cfg),1));after={'name':name,'code':code};newid=cid
        else:
            authorize(user,cid,write=True);ct=center(c,cid)
            if body.get('revision')!=ct['revision']:raise ValueError('I dati sono cambiati. Ricaricare prima di salvare.')
            approvals.guard_mutation(sys.modules[__name__],c,user,action,body)
            if action=='center_save':
                cfg=validate_config(body['config']);before={'config':ct['config'],'version':ct['version']};after={'config':cfg,'version':ct['version']+1}
                c.execute('UPDATE centers SET config=?,version=version+1 WHERE id=?',(dump(cfg),cid))
            else:
                month=body['month'];p=period(c,ct,month);cfg=effective_rules(ct,p);entries=objects(c,'entries',cid);people=objects(c,'people',cid)
                if p['closed'] and action!='reopen':raise ValueError('Mese chiuso: solo l’amministratore può riaprirlo.')
                agreements.freeze(p,people)
                if action=='agreement_save':
                    pid=body.get('person_id');person=next((x for x in people if x['id']==pid),None)
                    if not person:raise ValueError('Dipendente non presente nella struttura.')
                    reason=str(body.get('reason','')).strip()
                    if len(reason)<8:raise ValueError('Indicare la motivazione, almeno 8 caratteri.')
                    before=copy.deepcopy(p['agreements'][pid]);ag=agreements.validate(body.get('agreement'),cfg)
                    ag.update(version=before.get('version',0)+1,source=reason,updated_by=user['username'],updated_at=now())
                    p['agreements'][pid]=ag;p['verified']=False;after={'person_id':pid,'month':month,'agreement':ag}
                elif action=='person':
                    raw=body['person'];pid=raw.get('id') or uid();before=next((x for x in people if x['id']==pid),None)
                    if raw.get('id') and not before:raise ValueError('Persona non trovata.')
                    name=str(raw.get('name','')).strip();role=raw.get('role');registration=str(raw.get('registration','')).strip()
                    if not name or role not in ct['config']['roles']:raise ValueError('Nome e ruolo valido obbligatori.')
                    if registration and any(x.get('registration')==registration and x['id']!=pid for x in people):raise ValueError('Matricola già presente in questo centro.')
                    pay=raw.get('pay_override')
                    if pay is not None:
                        keys={'weekday_rate','holiday_rate','fixed_deduction','ccnl_rate','pay_mode'}
                        if not isinstance(pay,dict) or set(pay)!=keys:raise ValueError('Accordo economico incompleto.')
                        validate_config({**ct['config'],**pay})
                    after={**(before or {}),**dict(id=pid,name=name[:150],role=role,registration=registration[:80],home_site=ct['name'],note=str(raw.get('note',''))[:2000],active=bool(raw.get('active',True)),pay_override=pay)}
                    put(c,'people',cid,after)
                elif action=='entry':
                    raw=body['entry'];pid=raw.get('person_id');person=next((x for x in people if x['id']==pid and x['active']),None)
                    if not person:raise ValueError('Persona non presente o non attiva nel centro.')
                    if not str(raw.get('day','')).startswith(month+'-'):raise ValueError('Data fuori dal mese selezionato.')
                    before=next((e for e in entries if e['id']==raw.get('id')),None)
                    if raw.get('id') and not before:raise ValueError('Registrazione da modificare non trovata.')
                    if before and any(raw.get(k)!=before[k] for k in ('day','slot','person_id','layer')):raise ValueError('Per spostare una registrazione eliminarla e reinserirla.')
                    comparisons=list(entries)
                    assignment=workforce.ensure_person(c,cid,pid)
                    for peer in c.execute('SELECT cid,pid FROM workforce_assignments WHERE global_id=? AND cid<>?',(assignment['global_id'],cid)):
                        comparisons += [{**e,'person_id':pid} for e in objects(c,'entries',peer['cid']) if e['person_id']==peer['pid']]
                    after,warnings=make_entry(raw,cfg,person,ct['name'],'admin' if user['role']=='manager' else user['role'],comparisons,before);after['id']=after['id'] or uid();after['config_version']=p['version'];after['updated_by']=user['username'];after['updated_at']=now()
                    put(c,'entries',cid,after)
                elif action=='delete':
                    if user['role'] not in ('admin','manager') and not cfg['operator_delete']:raise PermissionError('Eliminazione riservata all’amministratore.')
                    before=next((e for e in entries if e['id']==body.get('id') and e['day'].startswith(month+'-')),None)
                    if not before:raise ValueError('Registrazione non trovata nel mese.')
                    if before['layer']=='planned' and user['role'] not in ('admin','manager') and not cfg['operator_planned']:raise PermissionError('Pianificazione riservata all’amministratore.')
                    c.execute('DELETE FROM entries WHERE cid=? AND id=?',(cid,before['id']))
                elif action=='period_verify':
                    before=copy.deepcopy(p);p['verified']=bool(body.get('verified'));p['note']=str(body.get('note',''))[:2000];after=p
                elif action=='apply_rules':
                    if not str(body.get('reason','')).strip():raise ValueError('Indicare il motivo del cambio di regole.')
                    if any(e['day'].startswith(month+'-') for e in entries):raise ValueError('Il mese contiene registrazioni. Per preservare lo storico, i nuovi parametri valgono dai mesi non ancora compilati.')
                    before=copy.deepcopy(p);p['config']=ct['config'];p['version']=ct['version'];p['verified']=False;p['note']=str(body['reason'])[:2000];after=p
                elif action=='close':
                    selected=[e for e in entries if e['day'].startswith(month+'-') and e['layer']=='actual']
                    if not p['verified']:raise ValueError('Verificare calendario e parametri prima della chiusura.')
                    if not selected:raise ValueError('Mese senza registrazioni effettive.')
                    if any(r['pending'] for r in totals(people,entries,month)):raise ValueError('Completare le fasce pianificate.')
                    if any('da specificare' in e['work_site'] or 'Colore sede da verificare' in e['note'] for e in selected):raise ValueError('Risolvere le sedi importate non definite.')
                    if cfg['require_times_on_close'] and any(e['kind']=='work' and duration(e) is None for e in selected):raise ValueError('Completare gli orari richiesti per la chiusura.')
                    before=copy.deepcopy(p);p['closed']=True;after=p
                elif action=='reopen':
                    if not str(body.get('reason','')).strip():raise ValueError('Motivazione obbligatoria.')
                    before=copy.deepcopy(p);p['closed']=False;p['note']=str(body['reason'])[:2000];after=p
                elif action=='patient':
                    raw=body['patient'];day=raw.get('day','');date.fromisoformat(day);slot=raw.get('slot')
                    if not day.startswith(month+'-') or slot not in {s['id'] for s in cfg['slots']}:raise ValueError('Data o fascia non valida.')
                    if any(type(raw.get(k))!=int or not 0<=raw[k]<=10000 for k in ('ordinary','isolated')):raise ValueError('Inserire conteggi interi non negativi.')
                    after={'id':day+'|'+slot,'day':day,'slot':slot,'ordinary':raw['ordinary'],'isolated':raw['isolated']};before=next((x for x in objects(c,'patients',cid) if x['id']==after['id']),None);put(c,'patients',cid,after)
                else:raise ValueError('Operazione non riconosciuta.')
                put_period(c,cid,month,p)
            c.execute('UPDATE centers SET revision=revision+1 WHERE id=?',(cid,))
        audit(c,user,action,cid,before,after);c.commit()
    if revoke_id:revoke(revoke_id)
    return {'ok':True,'warnings':warnings,'cid':newid}

def _backup():
    directory=DB.parent/'backups';directory.mkdir(exist_ok=True)
    path=directory/('presenze_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite3')
    pending=path.with_suffix('.sqlite3.partial')
    try:
        with connect() as src:
            dst=sqlite3.connect(pending)
            try:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup non valido.')
            finally:dst.close()
        pending.replace(path)
    finally:
        if pending.exists():pending.unlink()
    return {'filename':path.name}

def backup(user):
    with connect() as c:require_admin(fresh_user(c,user))
    return _backup()

def daily_backup():
    prefix='presenze_'+date.today().strftime('%Y%m%d')+'_'
    if not any(path.name.startswith(prefix) for path in backup_tools.completed_files(DB.parent/'backups')):
        return _backup()

def import_confirm(user,key):
    require_admin(user)
    with LOCK:model=PENDING.get(key)
    if not model or model['owner']!=user['id']:raise ValueError('Anteprima non valida o scaduta.')
    if time.monotonic()-model['created']>900:raise ValueError('Anteprima scaduta.')
    model=model['model'];backup(user)
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');user=fresh_user(c,user);require_admin(user)
        old=c.execute('SELECT cid,month FROM imports WHERE hash=?',(model['hash'],)).fetchone()
        if old:return dict(old)
        cid=uid();cfg=defaults();cfg['holidays']=model['holidays'];cfg['note']='\n'.join(model['warnings'])
        cfg['roles']=list(dict.fromkeys(cfg['roles']+[p['role'] or 'ALTRO' for p in model['people']]))
        for slot in cfg['slots']:
            if slot['id']=='n':slot['active']=False
        cfg['sites']=sorted({e['work_site'] for e in model['entries'] if e['work_site']!=model['center']})
        c.execute('INSERT INTO centers VALUES(?,?,?,?,?,0)',(cid,model['center'],'IMPORT-'+model['hash'][:12].upper(),dump(cfg),1))
        for p in model['people']:put(c,'people',cid,dict(id=p['id'],name=p['name'],role=p['role'] or 'ALTRO',registration='',home_site=model['center'],active=True,contract=p.get('contract',''),note=p.get('contract','')+' | '+p.get('agreement_note','')))
        for entry in model['entries']:
            code=next(x for x in cfg['codes'] if x['id']==entry['code'])
            e={k:entry[k] for k in ('person_id','day','slot','layer','code','work_site','start','end','overnight','holiday','note')}
            e.update(id=uid(),kind=code['kind'],code_label=code['label'],pause=entry['break_minutes'],credit_minutes=0,config_version=1,updated_by=user['username'],updated_at=now(),source_cell=entry['source_cell'])
            put(c,'entries',cid,e)
        imported_period=dict(closed=False,verified=False,config=cfg,version=1,note='\n'.join(model['warnings']))
        imported_people=objects(c,'people',cid);agreements.freeze(imported_period,imported_people)
        for person in model['people']:
            if person.get('agreement_proposal'):
                imported_period['agreements'][person['id']].update(person['agreement_proposal'])
        put_period(c,cid,model['month'],imported_period)
        c.execute('INSERT INTO imports VALUES(?,?,?)',(model['hash'],cid,model['month']));audit(c,user,'importazione Excel',cid,after={'hash':model['hash'],'warnings':model['warnings']});c.commit()
    with LOCK:PENDING.pop(key,None)
    return {'cid':cid,'month':model['month']}

def export_csv(user,cid,month,detail=False):
    s=snapshot(user,cid,month);cfg=s['period']['config'];user=s['user']
    if user['role'] not in ('admin','manager','hr') and not cfg['operator_export']:raise PermissionError('Esportazione riservata ai ruoli autorizzati.')
    out=io.StringIO();w=csv.writer(out,delimiter=cfg['csv_separator']);state='CHIUSO' if s['period']['closed'] else 'BOZZA'
    def safe(v):
        v=str(v);return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
    def row(values):w.writerow([safe(x) for x in values])
    if detail:
        row(['Stato','Centro','Matricola','Persona','Data','Fascia','Causale','Registro','Sede','Ingresso','Uscita','Giorno successivo','Pausa min','Festivo','Versione regole','Operatore','Note'])
        ps={p['id']:p for p in s['people']}
        for e in sorted(s['entries'],key=lambda e:(e['day'],e['person_id'],e['slot'])):
            p=ps[e['person_id']];row([state,s['center']['name'],p.get('registration',''),p['name'],e['day'],e['slot'],e['code'],e['layer'],e['work_site'],e['start'],e['end'],int(e['overnight']),e['pause'],int(e['holiday']),e['config_version'],e.get('updated_by',''),e['note']])
    else:
        causes=sorted({code for p in s['summary'] for code in p['causes']})
        row(['Stato','Centro','Mese','Matricola','Persona','Ruolo','Turni','Giorni','Minuti lavorati con orari','Turni senza orario','Fasce assenza','Credito assenze min','Fuori sede','Festivi','Da consuntivare']+causes)
        for p in s['summary']:row([state,s['center']['name'],month,p.get('registration',''),p['name'],p['role'],p['shifts'],p['days'],p['minutes'],p['missing'],p['absence_slots'],p['credit_minutes'],p['external'],p['festive'],p['pending']]+[p['causes'].get(k,0) for k in causes])
    return ('\ufeff'+out.getvalue()).encode('utf-8')

