"""Fascicoli centrali e onboarding con autorizzazione HR, senza dati privati nei pacchetti presenze."""
import base64, copy, hashlib, json, re
from datetime import date, timedelta
import structures
import document_reviews

MAX_DOCUMENT = 6 * 1024 * 1024
FIELDS = {
    'first_name':80,'last_name':80,'tax_code':16,'birth_date':10,'birth_place':150,
    'nationality':80,'address':250,'postal_code':20,'city':100,'province':60,'country':80,
    'domicile':300,'email':200,'phone':60,'emergency_name':150,'emergency_phone':60,
    'employer':200,'department':150,'manager':150,'contract_type':100,'ccnl':150,
    'level':80,'qualification':150,'start_date':10,'end_date':10,'probation_end':10,
    'weekly_hours':10,'part_time_percent':10,'iban':34,'payroll_contact':200,
    'professional_register':200,'register_number':100,'registration_expiry':10,
    'work_permit_expiry':10,'next_review':10,'notes':2000,
    'birth_province':60,'identity_type':80,'identity_number':80,'identity_issuer':150,
    'identity_issued_date':10,'identity_expiry':10,'pec':200,'company_email':200,
    'vat_number':30,'payment_method':80,'account_holder':150,'bank_name':150,
    'contract_number':80,'cost_center':100,'workplace':150,'badge_number':80,'tutor':150,
}
DATES={k for k in FIELDS if k.endswith(('_date','_expiry'))}|{'probation_end','next_review'}
DEFAULT_TASKS=[
 ('identita','Prima dell’ingresso','Verifica dati anagrafici e documento','Amministrazione',-7),
 ('contratto','Prima dell’ingresso','Contratto e informazioni sul rapporto consegnati','Consulente del lavoro',-1),
 ('co','Prima dell’ingresso','Verifica comunicazione obbligatoria e ricevuta, se dovuta','Consulente del lavoro',-1),
 ('paghe','Prima dell’ingresso','Dati paghe, modalità di pagamento e modulistica fiscale/TFR','Amministrazione',-1),
 ('titoli','Prima dell’ingresso','Verifica titoli, abilitazioni e iscrizione all’albo, se pertinenti','Responsabile del centro',-1),
 ('permesso','Prima dell’ingresso','Verifica titolo di soggiorno/lavoro, se necessario','Amministrazione',-1),
 ('medico','Prima dell’ingresso','Verifica adempimenti con il medico competente, se applicabili','Responsabile sicurezza',-1),
 ('sicurezza','Primo giorno','Verifica formazione, informazione e addestramento previsti per la mansione','Responsabile sicurezza',0),
 ('privacy','Primo giorno','Informativa dipendenti e istruzioni sul trattamento dei dati','Amministrazione',0),
 ('accessi','Primo giorno','Account nominativi, permessi e istruzioni di sicurezza','IT',0),
 ('badge','Primo giorno','Consegna badge, chiavi, dotazioni e DPI previsti','Responsabile del centro',0),
 ('turni','Primo giorno','Orari, sede, tutor e modalità di registrazione presenze','Responsabile del centro',0),
 ('procedure','Inserimento','Affiancamento e procedure del centro','Tutor',7),
 ('feedback','Inserimento','Colloquio di inserimento e verifica attività aperte','Responsabile del centro',30),
]

def init(app):
    with app.connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS hr_profiles(cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(cid,pid),FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE TABLE IF NOT EXISTS hr_settings(cid TEXT PRIMARY KEY REFERENCES centers(id),version INTEGER NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hr_documents(id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,expiry TEXT NOT NULL,uploaded_at TEXT NOT NULL,uploaded_by TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL,FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE TABLE IF NOT EXISTS hr_history(cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(cid,pid,version));
        CREATE INDEX IF NOT EXISTS hr_doc_person ON hr_documents(cid,pid);''');c.commit()

def text(v,n=200):
    if not isinstance(v,str) or len(v)>n or '\x00' in v:raise ValueError('Testo non valido o troppo lungo.')
    return v.strip()
def day(v):
    if v:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v):raise ValueError('Usare una data valida.')
        date.fromisoformat(v)
    return v
def access(app,c,user,cid):
    user=app.fresh_user(c,user);app.require_hr(user,cid);app.center(c,cid);return user
def settings(c,cid):
    r=c.execute('SELECT * FROM hr_settings WHERE cid=?',(cid,)).fetchone()
    return {'version':r['version'] if r else 0,**(json.loads(r['data']) if r else {'tasks':[dict(id=i,phase=p,label=l,owner=o,offset=d) for i,p,l,o,d in DEFAULT_TASKS],'fields':[]})}
def task_list(cfg,start):
    return [{**t,'status':'todo','due':(date.fromisoformat(start)+timedelta(days=t['offset'])).isoformat() if start else '', 'note':'','completed_at':'','completed_by':''} for t in cfg['tasks']]
def progress(p):
    tasks=p.get('tasks',[]);done=sum(t['status'] in ('done','na') for t in tasks)
    late=sum(t['status'] not in ('done','na') and bool(t['due']) and t['due']<date.today().isoformat() for t in tasks)
    return {'done':done,'total':len(tasks),'overdue':late}
def docs(c,cid,pid):
    return [document_reviews.attach(c, dict(r)) for r in c.execute('SELECT id,name,category,expiry,uploaded_at,uploaded_by,sha256,length(content) AS size FROM hr_documents WHERE cid=? AND pid=? ORDER BY uploaded_at DESC',(cid,pid))]
def profile(c,cid,pid):
    r=c.execute('SELECT * FROM hr_profiles WHERE cid=? AND pid=?',(cid,pid)).fetchone()
    data=json.loads(r['data']) if r else {'fields':{},'custom':{},'tasks':[],'stage':'incoming'}
    data['fields']={**{k:'' for k in FIELDS},**data.get('fields',{})}
    return {**data,'version':r['version'] if r else 0}

def deadlines(person,p,documents):
    today=date.today().isoformat();out=[]
    def add(label,d,section):
        if d:out.append(dict(pid=person['id'],name=person['name'],label=label,date=d,late=d<today,section=section))
    for key,label,section in [('identity_expiry','Documento di identità','anagrafica'),('end_date','Fine contratto','contratto'),('probation_end','Fine periodo di prova','contratto'),('registration_expiry','Iscrizione/abilitazione','qualifiche'),('work_permit_expiry','Titolo di soggiorno/lavoro','qualifiche'),('next_review','Verifica amministrativa','qualifiche')]:
        add(label,p['fields'].get(key,''),section)
    for t in p['tasks']:
        if t['status'] not in ('done','na'):add(t['label'],t['due'],'onboarding')
    for d in documents:add(d['category']+' · '+d['name'],d['expiry'],'documenti')
    return sorted(out,key=lambda d:d['date'])

def read(app,user,cid,pid=None):
    with app.connect() as c:
        user=access(app,c,user,cid);cfg=settings(c,cid);people=app.objects(c,'people',cid)
        if pid:
            person=next((x for x in people if x['id']==pid),None)
            if not person:raise ValueError('Dipendente non trovato nel centro.')
            p=profile(c,cid,pid);documents=docs(c,cid,pid)
            if not p['version']:p['fields']['contract_type']=person.get('contract','')
            return {'person':{k:person.get(k) for k in ('id','name','role','registration','active')},'profile':p,'history':[dict(r) for r in c.execute('SELECT version,stamp,actor FROM hr_history WHERE cid=? AND pid=? ORDER BY version DESC LIMIT 50',(cid,pid))],'documents':documents,'deadlines':deadlines(person,p,documents),'settings':cfg,'progress':progress(p),'structure':structures.record(c,cid)}
        rows=[];due=[]
        today=date.today().isoformat();soon=(date.today()+timedelta(days=30)).isoformat()
        for person in people:
            p=profile(c,cid,person['id']);f=p['fields'];pr=progress(p)
            rows.append({'id':person['id'],'name':person['name'],'role':person['role'],'registration':person.get('registration',''),'active':person['active'],'stage':p['stage'],'department':f.get('department',''),'start':f.get('start_date',''),'version':p['version'],**pr})
            due.extend(d for d in deadlines(person,p,docs(c,cid,person['id'])) if d['date']<=soon)
        return {'employees':sorted(rows,key=lambda p:p['name'].casefold()),'deadlines':sorted(due,key=lambda d:d['date']),'settings':cfg}

def validate_fields(raw,cfg):
    if not isinstance(raw,dict) or set(raw)-set(FIELDS):raise ValueError('Campi del fascicolo non validi.')
    f={k:text(raw.get(k,''),n) for k,n in FIELDS.items()}
    for k in DATES:day(f[k])
    if f['birth_date'] and f['birth_date']>=date.today().isoformat():raise ValueError('Data di nascita non valida.')
    if f['end_date'] and f['start_date'] and f['end_date']<f['start_date']:raise ValueError('Fine contratto precedente all’ingresso.')
    if f['probation_end'] and f['start_date'] and f['probation_end']<f['start_date']:raise ValueError('Fine prova precedente all’ingresso.')
    if f['identity_expiry'] and f['identity_issued_date'] and f['identity_expiry']<f['identity_issued_date']:raise ValueError('Scadenza del documento precedente al rilascio.')
    for k,maxval in [('weekly_hours',168),('part_time_percent',100)]:
        if f[k] and (not re.fullmatch(r'\d+(?:[.,]\d{1,2})?',f[k]) or not 0<float(f[k].replace(',','.'))<=maxval):raise ValueError('Ore o percentuale non valide.')
    f['tax_code']=f['tax_code'].upper().replace(' ','')
    if f['tax_code'] and not (re.fullmatch('[A-Z0-9]{16}',f['tax_code']) or re.fullmatch('[0-9]{11}',f['tax_code'])):raise ValueError('Formato codice fiscale non valido. La verifica anagrafica resta manuale.')
    f['iban']=re.sub(r'\s','',f['iban']).upper()
    if f['iban']:
        value=f['iban']
        if not re.fullmatch('[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}',value):raise ValueError('Formato IBAN non valido.')
        n=''.join(str(ord(x)-55) if x.isalpha() else x for x in value[4:]+value[:4])
        if int(n)%97!=1:raise ValueError('Controllo IBAN non superato.')
    for key in ('email','pec','company_email'):
        if f[key] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',f[key]):raise ValueError('Indirizzo email non valido: '+key)
    return f

def save(app,user,body):
    cid=body['cid'];pid=body.get('pid') or app.uid()
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=access(app,c,user,cid);ct=app.center(c,cid);cfg=settings(c,cid)
        if body.get('revision')!=ct['revision']:raise ValueError('I dati del centro sono cambiati. Ricaricare prima di salvare.')
        people=app.objects(c,'people',cid);old=next((p for p in people if p['id']==pid),None)
        if body.get('pid') and not old:raise ValueError('Dipendente non trovato.')
        before=profile(c,cid,pid)
        if body.get('version')!=before['version']:raise ValueError('Fascicolo aggiornato da un’altra sessione. Ricaricare.')
        f=validate_fields(body.get('fields',{}),cfg);name=text(body.get('name',''),150)
        if not name:raise ValueError('Nome e cognome obbligatori.')
        role=body.get('role');registration=text(body.get('registration',''),80);active=body.get('active',True);stage=body.get('stage','incoming')
        if role not in ct['config']['roles'] or type(active)!=bool or stage not in ('incoming','active','ended'):raise ValueError('Ruolo o stato non valido.')
        if registration and any(p.get('registration')==registration and p['id']!=pid for p in people):raise ValueError('Matricola già utilizzata nel centro.')
        if f['tax_code']:
            for r in c.execute('SELECT pid,data FROM hr_profiles WHERE cid=? AND pid<>?',(cid,pid)):
                if json.loads(r['data'])['fields'].get('tax_code')==f['tax_code']:raise ValueError('Codice fiscale già presente nel centro.')
        custom=body.get('custom',{})
        if not isinstance(custom,dict) or len(custom)>80:raise ValueError('Campi personalizzati non validi.')
        # Preserve retired field values in the record, while validating active definitions.
        values=dict(before.get('custom',{}))
        for d in cfg['fields']:
            v=text(custom.get(d['id'],''),500)
            if d['type']=='date':day(v)
            if d['type']=='number' and v and not re.fullmatch(r'-?\d+(?:[.,]\d{1,3})?',v):raise ValueError('Numero non valido: '+d['label'])
            if d['type']=='boolean' and v not in ('','si','no'):raise ValueError('Scelta non valida.')
            values[d['id']]=v
        tasks=before['tasks'] if before['version'] else task_list(cfg,f['start_date'])
        p={'fields':f,'custom':values,'tasks':tasks,'stage':stage,'updated_at':app.now(),'updated_by':user['username']}
        person={**(old or {'id':pid,'home_site':ct['name'],'note':'','pay_override':None}), 'name':name,'role':role,'registration':registration,'active':active,'contract':f['contract_type']}
        app.put(c,'people',cid,person)
        c.execute('INSERT INTO hr_profiles VALUES(?,?,?,?) ON CONFLICT(cid,pid) DO UPDATE SET version=excluded.version,data=excluded.data',(cid,pid,before['version']+1,app.dump(p)))
        c.execute('INSERT INTO hr_history VALUES(?,?,?,?,?,?)',(cid,pid,before['version']+1,app.now(),user['username'],app.dump(p)))
        c.execute('UPDATE centers SET revision=revision+1 WHERE id=?',(cid,))
        app.audit(c,user,'Fascicolo dipendente salvato',cid,after={'pid':pid,'version':before['version']+1});c.commit()
    return {'ok':True,'pid':pid}

def task_save(app,user,body):
    cid=body['cid'];pid=body['pid']
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=access(app,c,user,cid);p=profile(c,cid,pid)
        if not p['version'] or body.get('version')!=p['version']:raise ValueError('Fascicolo cambiato o non ancora salvato. Ricaricare.')
        t=next((t for t in p['tasks'] if t['id']==body['task_id']),None)
        if not t:raise ValueError('Attività non trovata.')
        status=body['status'];note=text(body.get('note',''),1000)
        if status not in ('todo','doing','done','na'):raise ValueError('Stato non valido.')
        if status=='na' and not note:raise ValueError('Indicare perché l’attività non è applicabile.')
        changed=t['status']!=status
        t.update(status=status,due=day(text(body.get('due',''),10)),owner=text(body.get('owner',''),150),note=note)
        if changed:t.update(completed_at=app.now() if status in ('done','na') else '',completed_by=user['username'] if status in ('done','na') else '')
        version=p.pop('version')+1;p.update(updated_at=app.now(),updated_by=user['username'])
        c.execute('UPDATE hr_profiles SET version=?,data=? WHERE cid=? AND pid=?',(version,app.dump(p),cid,pid))
        c.execute('INSERT INTO hr_history VALUES(?,?,?,?,?,?)',(cid,pid,version,app.now(),user['username'],app.dump(p)))
        app.audit(c,user,'Attività onboarding aggiornata',cid,after={'pid':pid,'task_id':t['id'],'status':status});c.commit()
    return {'ok':True}

def settings_save(app,user,body):
    cid=body['cid'];raw=body['settings'];tasks=[];fields=[]
    if not isinstance(raw,dict) or not isinstance(raw.get('tasks'),list) or not 1<=len(raw['tasks'])<=80 or not isinstance(raw.get('fields'),list) or len(raw['fields'])>40:raise ValueError('Da 1 a 80 attività e al massimo 40 campi aggiuntivi.')
    for t in raw['tasks']:
        i=text(t['id'],40);label=text(t['label'],200);phase=text(t['phase'],80);owner=text(t.get('owner',''),150);offset=t.get('offset',0)
        if not re.fullmatch('[a-zA-Z0-9_-]{1,40}',i) or not label or type(offset)!=int or not -365<=offset<=730:raise ValueError('Attività modello non valida.')
        tasks.append(dict(id=i,label=label,phase=phase,owner=owner,offset=offset))
    for f in raw['fields']:
        i=text(f['id'],40);label=text(f['label'],100);kind=f['type'];required=f.get('required',False)
        if not re.fullmatch('[a-zA-Z0-9_-]{1,40}',i) or not label or kind not in ('text','date','number','boolean') or type(required)!=bool:raise ValueError('Campo aggiuntivo non valido.')
        fields.append(dict(id=i,label=label,type=kind,required=required))
    if len({t['id'] for t in tasks})!=len(tasks) or len({f['id'] for f in fields})!=len(fields):raise ValueError('Codici ripetuti nel modello.')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=access(app,c,user,cid);old=settings(c,cid)
        if raw.get('version')!=old['version']:raise ValueError('Modello modificato da un’altra sessione. Ricaricare.')
        c.execute('INSERT INTO hr_settings VALUES(?,?,?) ON CONFLICT(cid) DO UPDATE SET version=excluded.version,data=excluded.data',(cid,old['version']+1,app.dump({'tasks':tasks,'fields':fields})))
        app.audit(c,user,'Modello onboarding aggiornato',cid,after={'version':old['version']+1,'tasks':len(tasks),'fields':len(fields)});c.commit()
    return {'ok':True}

def document_add(app,user,body):
    cid=body['cid'];pid=body['pid']
    # Permission check before decoding or accepting sensitive content.
    with app.connect() as c:access(app,c,user,cid)
    name=text(body['name'],180)
    if not name or '/' in name or '\\' in name or name in ('.','..') or any(ord(x)<32 or ord(x)==127 for x in name):raise ValueError('Nome file non valido.')
    ext=name.rsplit('.',1)[-1].lower();category=text(body.get('category','Documento amministrativo'),100)
    if ext not in ('pdf','png','jpg','jpeg'):raise ValueError('Caricare PDF, PNG o JPEG, massimo 6 MiB.')
    encoded=body['content']
    if not isinstance(encoded,str) or len(encoded)>MAX_DOCUMENT*4//3+8:raise ValueError('Documento troppo grande.')
    data=base64.b64decode(encoded,validate=True)
    if not data or len(data)>MAX_DOCUMENT:raise ValueError('Dimensione documento non valida.')
    if not (ext=='pdf' and data.startswith(b'%PDF-') or ext=='png' and data.startswith(b'\x89PNG\r\n\x1a\n') or ext in ('jpg','jpeg') and data.startswith(b'\xff\xd8\xff')):raise ValueError('Il contenuto non corrisponde al formato dichiarato.')
    expiry=day(text(body.get('expiry',''),10));sha=hashlib.sha256(data).hexdigest();docid=app.uid()
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=access(app,c,user,cid)
        if not c.execute('SELECT 1 FROM hr_profiles WHERE cid=? AND pid=?',(cid,pid)).fetchone():raise ValueError('Salvare il fascicolo prima di allegare documenti.')
        if c.execute('SELECT count(*) FROM hr_documents WHERE cid=? AND pid=?',(cid,pid)).fetchone()[0]>=200:raise ValueError('Raggiunto il limite di 200 documenti per dipendente.')
        c.execute('INSERT INTO hr_documents VALUES(?,?,?,?,?,?,?,?,?,?)',(docid,cid,pid,name,category,expiry,app.now(),user['username'],sha,data))
        document_reviews.registered(app,c,user,docid)
        app.audit(c,user,'Documento dipendente aggiunto',cid,after={'pid':pid,'document_id':docid,'sha256':sha});c.commit()
    return {'ok':True,'id':docid}

def document_read(app,user,cid,docid):
    with app.connect() as c:
        user=access(app,c,user,cid);r=c.execute('SELECT * FROM hr_documents WHERE id=? AND cid=?',(docid,cid)).fetchone()
        if not r:raise ValueError('Documento non trovato.')
        app.audit(c,user,'Documento dipendente scaricato',cid,after={'pid':r['pid'],'document_id':docid});c.commit()
        return {'name':r['name'],'content':base64.b64encode(r['content']).decode(),'sha256':r['sha256']}

def document_view(app,user,cid,docid):
    """Return only an authorized database attachment, never a filesystem path."""
    with app.connect() as c:
        user=access(app,c,user,cid)
        r=c.execute('SELECT * FROM hr_documents WHERE id=? AND cid=?',(docid,cid)).fetchone()
        if not r:raise ValueError('Documento non trovato.')
        data=bytes(r['content']);ext=r['name'].rsplit('.',1)[-1].lower()
        mime={'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg'}.get(ext)
        valid=(ext=='pdf' and data.startswith(b'%PDF-') or ext=='png' and data.startswith(b'\x89PNG\r\n\x1a\n') or ext in ('jpg','jpeg') and data.startswith(b'\xff\xd8\xff'))
        if not mime or not valid or hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('Documento non valido per la visualizzazione. Verificare l’allegato originale.')
        app.audit(c,user,'Documento dipendente visualizzato',cid,after={'pid':r['pid'],'document_id':docid,'sha256':r['sha256']});c.commit()
        return data,mime,r['name']

def document_index(app,user,cid='all',person='',category='',expiry='all',review='all'):
    """List document metadata across exactly the caller's authorized HR centers."""
    cid=text(cid,80);person=text(person,150).casefold();category=text(category,100)
    if expiry not in ('all','expired','soon','dated','none'):raise ValueError('Filtro scadenza non valido.')
    if review not in ('all','received','needs_correction','verified','expired'):raise ValueError('Filtro verifica non valido.')
    today=date.today().isoformat();soon=(date.today()+timedelta(days=30)).isoformat()
    with app.connect() as c:
        user=app.fresh_user(c,user)
        if user['role'] not in ('admin','manager','hr'):raise PermissionError('Archivio documenti riservato ai responsabili HR autorizzati.')
        centers=app.centers_for(c,user)
        if cid!='all':
            app.require_hr(user,cid);app.center(c,cid)
            selected=[ct for ct in centers if ct['id']==cid]
        else:selected=centers
        rows=[];categories=set()
        for ct in selected:
            people={p['id']:p for p in app.objects(c,'people',ct['id'])}
            for doc in c.execute('SELECT id,cid,pid,name,category,expiry,uploaded_at,uploaded_by,sha256,length(content) AS size FROM hr_documents WHERE cid=? ORDER BY uploaded_at DESC,id',(ct['id'],)):
                p=people.get(doc['pid'])
                if not p:continue
                d=document_reviews.attach(c,dict(doc),today);categories.add(d['category'])
                if review=='expired' and not d['review']['expired']:continue
                if review not in ('all','expired') and d['review']['status']!=review:continue
                if person and person not in (p['name']+' '+p.get('registration','')).casefold():continue
                if category and d['category']!=category:continue
                due=d['expiry']
                if expiry=='expired' and (not due or due>=today):continue
                if expiry=='soon' and (not due or not today<=due<=soon):continue
                if expiry=='dated' and not due:continue
                if expiry=='none' and due:continue
                d.update(center=ct['name'],center_code=ct['code'],person=p['name'],registration=p.get('registration',''),late=bool(due and due<today))
                rows.append(d)
        rows.sort(key=lambda d:(d['uploaded_at'],d['id']),reverse=True)
        return {'centers':centers,'categories':sorted(categories,key=str.casefold),'documents':rows,'total':len(rows),'generated_at':app.now()}

def document_delete(app,user,body):
    reason=text(body.get('reason',''),300)
    if not reason:raise ValueError('Indicare il motivo della rimozione.')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=access(app,c,user,body['cid'])
        r=c.execute('SELECT pid FROM hr_documents WHERE id=? AND cid=?',(body['id'],body['cid'])).fetchone()
        if not r:raise ValueError('Documento non trovato.')
        c.execute('DELETE FROM hr_documents WHERE id=?',(body['id'],));app.audit(c,user,'Documento dipendente rimosso',body['cid'],after={'document_id':body['id'],'reason':reason});c.commit()
    return {'ok':True}
