"""Uscite, trasferimenti e restituzione delle dotazioni, senza modifiche implicite ai fascicoli."""
import json
from datetime import date

KINDS = {'termination': 'Cessazione', 'transfer': 'Trasferimento'}
ASSET_KINDS = {'badge': 'Badge', 'keys': 'Chiavi', 'device': 'Dispositivo', 'other': 'Altra dotazione'}
TASKS = [('badge', 'Restituzione badge'), ('keys', 'Restituzione chiavi'),
         ('devices', 'Restituzione dispositivi e altre dotazioni'),
         ('documents', 'Consegna e verifica dei documenti'),
         ('access', 'Conferma con IT della gestione degli accessi')]
ACTIVE = ('open', 'in_progress')
NOTICE = ('La chiusura del percorso non cambia automaticamente il rapporto, la sede o lo stato del dipendente '
          'e non disattiva account esterni. Aggiornare il fascicolo e gli accessi nelle rispettive procedure autorizzate.')


def init(app):
    with app.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS departure_cases(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,
            status TEXT NOT NULL,data TEXT NOT NULL,
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE UNIQUE INDEX IF NOT EXISTS departure_case_active ON departure_cases(cid,pid)
            WHERE status IN ('open','in_progress');
        CREATE TABLE IF NOT EXISTS equipment_assignments(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,version INTEGER NOT NULL,
            asset_key TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE UNIQUE INDEX IF NOT EXISTS equipment_active ON equipment_assignments(cid,asset_key)
            WHERE status='assigned';
        CREATE TABLE IF NOT EXISTS departure_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT NOT NULL,kind TEXT NOT NULL,object_id TEXT NOT NULL,
            version INTEGER NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS departure_history_object ON departure_history(kind,object_id,id);
        ''');c.commit()


def _text(value, label, maximum=200, required=False):
    if not isinstance(value, str) or len(value) > maximum or any(ord(x)<32 and x not in '\n\t' for x in value) or '\x7f' in value:
        raise ValueError(f'{label}: usare un testo valido di massimo {maximum} caratteri.')
    value=value.strip()
    if required and not value:raise ValueError(f'{label}: campo obbligatorio.')
    return value


def _day(value, label, optional=False):
    value=_text(value,label,10,not optional)
    if not value and optional:return ''
    try:
        d=date.fromisoformat(value)
        if d.isoformat()!=value or not 1900<=d.year<=2200:raise ValueError()
    except ValueError:raise ValueError(f'{label}: indicare una data valida (AAAA-MM-GG).')
    return value


def _today():return date.today().isoformat()


def _body(body):
    if not isinstance(body,dict):raise ValueError('Richiesta non valida.')


def _access(app,c,user,cid=None):
    if cid is not None:cid=_text(cid,'Struttura',128,True)
    user=app.fresh_user(c,user)
    if user['role'] not in ('admin','hr','manager'):
        raise PermissionError('Uscite e dotazioni riservate a HR e responsabili autorizzati.')
    if cid is not None:
        app.require_hr(user,cid);app.center(c,cid)
    return user


def _person(app,c,cid,pid):
    pid=_text(pid,'Dipendente',128,True)
    row=c.execute('SELECT data FROM people WHERE cid=? AND id=?',(cid,pid)).fetchone()
    if not row:raise ValueError('Dipendente non presente nella struttura selezionata.')
    return json.loads(row['data'])


def _version(body,record):
    value=body.get('version')
    if type(value) is not int or value!=(record['version'] if record else 0):
        raise ValueError('Dati aggiornati da un’altra sessione. Riaprire la scheda prima di salvare.')


def _record(c,table,cid,oid,required=True):
    cid=_text(cid,'Struttura',128,True);oid=_text(oid,'Scheda',128,True)
    row=c.execute(f'SELECT * FROM {table} WHERE cid=? AND id=?',(cid,oid)).fetchone()
    if not row:
        if required:raise ValueError('Scheda non trovata nella struttura selezionata.')
        return None
    return {**json.loads(row['data']),**{k:row[k] for k in ('id','cid','pid','version','status')}}


def _history(app,c,user,kind,item,action,before=None):
    c.execute('INSERT INTO departure_history(cid,kind,object_id,version,stamp,actor,action,data) VALUES(?,?,?,?,?,?,?,?)',
              (item['cid'],kind,item['id'],item['version'],app.now(),user['username'],action,app.dump(item)))
    app.audit(c,user,action,item['cid'],before=before,after=item)


def _store_case(app,c,item):
    c.execute('''INSERT INTO departure_cases VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        version=excluded.version,status=excluded.status,data=excluded.data''',
        (item['id'],item['cid'],item['pid'],item['version'],item['status'],app.dump(item)))


def _case_detail(app,c,item):
    result=dict(item)
    result['person_name']=_person(app,c,item['cid'],item['pid'])['name']
    result['outstanding_assets']=[_record(c,'equipment_assignments',item['cid'],r['id'])
        for r in c.execute("SELECT id FROM equipment_assignments WHERE cid=? AND pid=? AND status='assigned' ORDER BY id",(item['cid'],item['pid']))]
    result['blockers']=[t['label'] for t in item['tasks'] if t['required'] and t['status'] not in ('done','na')]
    if result['outstanding_assets']:result['blockers'].append('Dotazioni ancora da restituire: '+str(len(result['outstanding_assets'])))
    result['history']=[dict(r) for r in c.execute('''SELECT version,stamp,actor,action FROM departure_history
        WHERE kind='case' AND object_id=? ORDER BY id DESC LIMIT 100''',(item['id'],))]
    result['can_complete']=item['status'] in ACTIVE and not result['blockers']
    result['notice']=NOTICE
    return result


def overview(app,user,cid='all'):
    cid=_text(cid,'Struttura',128,True)
    with app.connect() as c:
        user=_access(app,c,user,None if cid=='all' else cid)
        centers=app.centers_for(c,user)
        if cid!='all':centers=[ct for ct in centers if ct['id']==cid]
        people=[];cases=[];assets=[]
        for center in centers:
            for person in app.objects(c,'people',center['id']):
                people.append(dict(cid=center['id'],id=person['id'],name=person['name'],registration=person.get('registration',''),active=person.get('active',True)))
            for row in c.execute('SELECT id FROM departure_cases WHERE cid=? ORDER BY rowid DESC',(center['id'],)):
                item=_record(c,'departure_cases',center['id'],row['id'])
                item['person_name']=_person(app,c,item['cid'],item['pid'])['name'];cases.append(item)
            for row in c.execute('SELECT id FROM equipment_assignments WHERE cid=? ORDER BY rowid DESC',(center['id'],)):
                item=_record(c,'equipment_assignments',center['id'],row['id'])
                item['person_name']=_person(app,c,item['cid'],item['pid'])['name']
                item['overdue']=item['status']=='assigned' and bool(item['due_date']) and item['due_date']<_today()
                item['history']=[dict(r) for r in c.execute("SELECT version,stamp,actor,action FROM departure_history WHERE kind='asset' AND object_id=? ORDER BY id DESC LIMIT 50",(item['id'],))]
                assets.append(item)
        return dict(centers=[{k:ct[k] for k in ('id','name','code')} for ct in centers],people=people,
                    cases=cases,assets=assets,kinds=KINDS,asset_kinds=ASSET_KINDS,notice=NOTICE,today=_today())


def case_read(app,user,cid,oid):
    with app.connect() as c:
        _access(app,c,user,cid)
        return _case_detail(app,c,_record(c,'departure_cases',cid,oid))


def case_save(app,user,body):
    _body(body)
    cid=_text(body.get('cid'),'Struttura',128,True);oid=_text(body.get('id',''),'Percorso',128)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,cid)
        old=_record(c,'departure_cases',cid,oid) if oid else None;_version(body,old)
        if old and old['status'] not in ACTIVE:raise ValueError('Il percorso è già chiuso: lo storico non può essere riscritto.')
        person=_person(app,c,cid,body.get('pid'));pid=person['id']
        if old and pid!=old['pid']:raise ValueError('Il dipendente del percorso non può essere cambiato.')
        kind=body.get('kind')
        if not isinstance(kind,str) or kind not in KINDS:raise ValueError('Tipo di percorso non valido.')
        destination=_text(body.get('destination_cid',''),'Struttura di destinazione',128)
        if kind=='transfer':
            if not destination or destination==cid:raise ValueError('Indicare una struttura di destinazione diversa.')
            _access(app,c,user,destination)
        elif destination:raise ValueError('Una cessazione non prevede una struttura di destinazione.')
        reason=_text(body.get('reason',''),'Motivazione',1000,True)
        if len(reason)<8:raise ValueError('Spiegare la motivazione con almeno 8 caratteri.')
        effective=_day(body.get('effective_date'),'Data prevista')
        responsible=_text(body.get('responsible',''),'Responsabile del percorso',150,True)
        duplicate=c.execute("SELECT id FROM departure_cases WHERE cid=? AND pid=? AND status IN ('open','in_progress') AND id<>?",(cid,pid,oid)).fetchone()
        if duplicate:raise ValueError('Esiste già un percorso aperto per questa persona nella struttura.')
        if not oid:oid=app.uid()
        tasks=old['tasks'] if old else [dict(id=k,label=label,required=True,status='todo',owner=responsible,due=effective,note='') for k,label in TASKS]
        item=dict(id=oid,cid=cid,pid=pid,version=(old['version'] if old else 0)+1,status=old['status'] if old else 'open',
                  kind=kind,destination_cid=destination,effective_date=effective,reason=reason,responsible=responsible,
                  tasks=tasks,created_at=old['created_at'] if old else app.now(),updated_at=app.now(),closure_note='')
        _store_case(app,c,item);_history(app,c,user,'case',item,'Percorso uscita aggiornato' if old else 'Percorso uscita creato',old)
        c.commit();return _case_detail(app,c,item)


def task_save(app,user,body):
    _body(body)
    cid=_text(body.get('cid'),'Struttura',128,True)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,cid)
        old=_record(c,'departure_cases',cid,body.get('id'));_version(body,old)
        if old['status'] not in ACTIVE:raise ValueError('Il percorso è già chiuso.')
        item=json.loads(app.dump(old));task=next((t for t in item['tasks'] if t['id']==body.get('task_id')),None)
        if not task:raise ValueError('Attività non trovata.')
        status=body.get('status')
        if status not in ('todo','doing','done','na'):raise ValueError('Stato attività non valido.')
        note=_text(body.get('note',''),'Nota attività',1000)
        if status=='na' and len(note)<8:raise ValueError('Motivare la non applicabilità con almeno 8 caratteri.')
        owner=_text(body.get('owner',task['owner']),'Responsabile attività',150,True)
        due=_day(body.get('due',task['due']),'Scadenza attività')
        task.update(status=status,note=note,owner=owner,due=due,updated_at=app.now(),updated_by=user['username'])
        item.update(status='in_progress',version=old['version']+1,updated_at=app.now())
        _store_case(app,c,item);_history(app,c,user,'case',item,'Attività uscita aggiornata',old);c.commit()
        return _case_detail(app,c,item)


def case_transition(app,user,body):
    _body(body)
    cid=_text(body.get('cid'),'Struttura',128,True)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,cid)
        old=_record(c,'departure_cases',cid,body.get('id'));_version(body,old)
        if old['status'] not in ACTIVE:raise ValueError('Il percorso è già chiuso.')
        target=body.get('status')
        if target not in ('completed','cancelled'):raise ValueError('Transizione non valida.')
        note=_text(body.get('note',''),'Nota di chiusura',1000,True)
        if len(note)<8:raise ValueError('Indicare una nota di almeno 8 caratteri.')
        if target=='completed':
            if body.get('confirm') is not True:raise ValueError('Confermare la chiusura del percorso.')
            detail=_case_detail(app,c,old)
            if detail['blockers']:raise ValueError('Completare le attività obbligatorie e restituire tutte le dotazioni prima della chiusura.')
        item={**old,'status':target,'version':old['version']+1,'updated_at':app.now(),'closed_at':app.now(),'closed_by':user['username'],'closure_note':note}
        _store_case(app,c,item);_history(app,c,user,'case',item,'Percorso uscita completato' if target=='completed' else 'Percorso uscita annullato',old)
        c.commit();return _case_detail(app,c,item)


def equipment_save(app,user,body):
    _body(body)
    cid=_text(body.get('cid'),'Struttura',128,True);oid=_text(body.get('id',''),'Dotazione',128)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,cid)
        old=_record(c,'equipment_assignments',cid,oid) if oid else None;_version(body,old)
        person=_person(app,c,cid,body.get('pid'));kind=body.get('kind')
        if not isinstance(kind,str) or kind not in ASSET_KINDS:raise ValueError('Tipo di dotazione non valido.')
        code=_text(body.get('inventory_code'),'Codice inventario',80,True)
        key=' '.join(code.split()).casefold()
        label=_text(body.get('label',''),'Descrizione dotazione',200,True)
        delivered=_day(body.get('delivery_date'),'Data consegna');due=_day(body.get('due_date',''),'Restituzione prevista',True)
        note=_text(body.get('note',''),'Nota dotazione',1000)
        if delivered>_today():raise ValueError('La consegna non può essere registrata nel futuro.')
        if due and due<delivered:raise ValueError('La restituzione prevista non può precedere la consegna.')
        if old:
            if old['status']!='assigned':raise ValueError('La dotazione è già restituita: lo storico non può essere modificato.')
            if any(old[k]!=v for k,v in [('pid',person['id']),('kind',kind),('inventory_code',code),('delivery_date',delivered)]):
                raise ValueError('Persona, codice, tipo e data della consegna non possono essere riscritti. Registrare prima la restituzione.')
        duplicate=c.execute("SELECT id FROM equipment_assignments WHERE cid=? AND asset_key=? AND status='assigned' AND id<>?",(cid,key,oid)).fetchone()
        if duplicate:raise ValueError('Questa dotazione risulta già assegnata nella struttura.')
        item=dict(id=oid or app.uid(),cid=cid,pid=person['id'],version=(old['version'] if old else 0)+1,status='assigned',
                  kind=kind,inventory_code=code,label=label,delivery_date=delivered,due_date=due,note=note,
                  return_date='',return_condition='',return_note='',created_at=old['created_at'] if old else app.now(),updated_at=app.now())
        c.execute('''INSERT INTO equipment_assignments VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            version=excluded.version,data=excluded.data''',(item['id'],cid,item['pid'],item['version'],key,item['status'],app.dump(item)))
        _history(app,c,user,'asset',item,'Consegna dotazione aggiornata' if old else 'Dotazione consegnata',old);c.commit();return {'ok':True,'asset':item}


def equipment_return(app,user,body):
    _body(body)
    cid=_text(body.get('cid'),'Struttura',128,True)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');user=_access(app,c,user,cid)
        old=_record(c,'equipment_assignments',cid,body.get('id'));_version(body,old)
        if old['status']!='assigned':raise ValueError('Questa dotazione è già stata restituita.')
        day=_day(body.get('return_date'),'Data restituzione')
        if day<old['delivery_date'] or day>_today():raise ValueError('La restituzione deve essere tra la consegna e oggi.')
        condition=body.get('condition')
        if condition not in ('good','damaged','unusable'):raise ValueError('Indicare le condizioni della dotazione restituita.')
        note=_text(body.get('note',''),'Nota restituzione',1000)
        if condition!='good' and len(note)<8:raise ValueError('Descrivere danni o problemi con almeno 8 caratteri.')
        item={**old,'version':old['version']+1,'status':'returned','return_date':day,'return_condition':condition,'return_note':note,'returned_by':user['username'],'updated_at':app.now()}
        c.execute('UPDATE equipment_assignments SET version=?,status=?,data=? WHERE id=?',(item['version'],item['status'],app.dump(item),item['id']))
        _history(app,c,user,'asset',item,'Dotazione restituita',old);c.commit();return {'ok':True,'asset':item}
