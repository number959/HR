"""Identità di gruppo e decorrenze, senza fusioni o ricalcoli retroattivi impliciti.

Le anagrafiche, i fascicoli e gli allegati restano nelle rispettive sedi. Gli
intervalli sono inclusivi. Nessun dato contrattuale storico viene dedotto dalla
scheda corrente: l'ufficio HR deve inserirne e verificare le decorrenze.
"""
import copy
import json
import math
import re
import uuid
from datetime import date
from decimal import Decimal
import agreements
import hr
from rules import month_days


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def init(app):
    with app.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS group_people(
            id TEXT PRIMARY KEY,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS workforce_assignments(
            cid TEXT NOT NULL,pid TEXT NOT NULL,global_id TEXT NOT NULL REFERENCES group_people(id),
            version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(cid,pid),
            UNIQUE(global_id,cid),FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE INDEX IF NOT EXISTS workforce_global ON workforce_assignments(global_id);
        CREATE TABLE IF NOT EXISTS workforce_contracts(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,
            effective_from TEXT NOT NULL,effective_to TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL,data TEXT NOT NULL,
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE INDEX IF NOT EXISTS workforce_contract_dates ON workforce_contracts(cid,pid,effective_from);
        CREATE TABLE IF NOT EXISTS workforce_economics(
            id TEXT PRIMARY KEY,cid TEXT NOT NULL,pid TEXT NOT NULL,
            effective_from TEXT NOT NULL,effective_to TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL,data TEXT NOT NULL,
            FOREIGN KEY(cid,pid) REFERENCES people(cid,id));
        CREATE INDEX IF NOT EXISTS workforce_economic_dates ON workforce_economics(cid,pid,effective_from);
        CREATE TABLE IF NOT EXISTS workforce_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,cid TEXT NOT NULL,pid TEXT NOT NULL,
            kind TEXT NOT NULL,record_id TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,
            reason TEXT NOT NULL,before_data TEXT NOT NULL,after_data TEXT NOT NULL);
        ''')
        # Every existing assignment receives a distinct identity, even when names,
        # registration numbers or tax codes match. Repeated startup preserves IDs.
        for row in c.execute('SELECT cid,id FROM people').fetchall():
            ensure_person(c, row['cid'], row['id'])
        c.commit()


def ensure_person(c, cid, pid):
    row = c.execute('SELECT * FROM workforce_assignments WHERE cid=? AND pid=?', (cid, pid)).fetchone()
    if row:
        return dict(row)
    if not c.execute('SELECT 1 FROM people WHERE cid=? AND id=?', (cid, pid)).fetchone():
        raise ValueError('Persona non trovata nel centro.')
    gid = uuid.uuid4().hex
    c.execute('INSERT INTO group_people(id) VALUES(?)', (gid,))
    c.execute('INSERT INTO workforce_assignments(cid,pid,global_id) VALUES(?,?,?)', (cid, pid, gid))
    return dict(cid=cid, pid=pid, global_id=gid, version=1)


def _day(value, optional=False):
    if optional and value == '':
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Indicare una data valida nel formato AAAA-MM-GG.')
    date.fromisoformat(value)
    return value


def _access(app, c, user, cid=None):
    user = app.fresh_user(c, user)
    if user['role'] not in ('admin', 'hr', 'manager'):
        raise PermissionError('Personale di gruppo riservato a HR e responsabili autorizzati.')
    if cid:
        if user['role'] == 'manager':
            app.require_manager(user, cid)
        app.center(c, cid)
    return user


def _allowed(user, cid):
    return user['role'] in ('admin', 'hr') or cid in user['centers']


def _assignment(c, cid, pid):
    row = c.execute('SELECT * FROM workforce_assignments WHERE cid=? AND pid=?', (cid, pid)).fetchone()
    if not row:
        raise ValueError('Assegnazione non trovata. Ricaricare i dati.')
    return dict(row)


def _records(c, table, cid, pid):
    if table not in ('workforce_contracts', 'workforce_economics'):
        raise ValueError('Archivio non valido.')
    return [{**dict(r), 'data': json.loads(r['data'])} for r in c.execute(
        'SELECT * FROM '+table+' WHERE cid=? AND pid=? ORDER BY effective_from DESC', (cid, pid))]


def effective_person(c, cid, pid, day):
    """Read only: a complete assignment with the contract valid on this day."""
    _day(day)
    row = c.execute('SELECT data FROM people WHERE cid=? AND id=?', (cid, pid)).fetchone()
    if not row:
        raise ValueError('Persona non trovata nel centro.')
    person = json.loads(row['data'])
    assignment = _assignment(c, cid, pid)
    person['global_id'] = assignment['global_id']
    contract = c.execute('''SELECT * FROM workforce_contracts WHERE cid=? AND pid=?
        AND effective_from<=? AND (effective_to='' OR effective_to>=?)''', (cid, pid, day, day)).fetchone()
    if contract:
        person.update(json.loads(contract['data']))
        person['contract'] = person['contract_type']
        person['effective_contract'] = {k: contract[k] for k in ('id', 'version', 'effective_from', 'effective_to')}
    else:
        person['effective_contract'] = None
    return person


def read(app, user, gid=None, on=None):
    on = _day(on or date.today().isoformat())
    with app.connect() as c:
        user = _access(app, c, user)
        rows = c.execute('''SELECT a.*,p.data,ct.name AS center_name,g.version AS global_version
            FROM workforce_assignments a JOIN people p ON p.cid=a.cid AND p.id=a.pid
            JOIN centers ct ON ct.id=a.cid JOIN group_people g ON g.id=a.global_id
            ORDER BY ct.name,a.pid''').fetchall()
        visible = [r for r in rows if _allowed(user, r['cid']) and (not gid or r['global_id'] == gid)]
        if gid and not visible:
            raise PermissionError('Persona non disponibile nei centri autorizzati.')
        groups = {}
        for row in visible:
            person = effective_person(c, row['cid'], row['pid'], on)
            g = groups.setdefault(row['global_id'], dict(global_id=row['global_id'], version=row['global_version'], assignments=[]))
            assignment = {k: row[k] for k in ('cid', 'pid', 'version', 'center_name')}
            assignment.update(person={k: person.get(k) for k in ('id','name','registration','role','active','contract','contract_type','weekly_hours','part_time_percent','effective_contract')})
            if gid:
                assignment.update(contracts=_records(c,'workforce_contracts',row['cid'],row['pid']),
                    economics=_records(c,'workforce_economics',row['cid'],row['pid']),
                    documents=hr.docs(c,row['cid'],row['pid']),
                    history=[dict(r) for r in c.execute('''SELECT kind,record_id,stamp,actor,reason,before_data,after_data
                        FROM workforce_history WHERE cid=? AND pid=? ORDER BY id DESC LIMIT 100''', (row['cid'],row['pid']))],
                    roles=app.center(c,row['cid'])['config']['roles'],
                    economic_proposal=agreements.proposal(app.center(c,row['cid'])['config'],person))
            g['assignments'].append(assignment)
        return dict(on=on, groups=list(groups.values()), scope='Tutti i centri' if user['role'] in ('admin','hr') else 'Centri assegnati')


def _reason(body):
    value = body.get('reason')
    if not isinstance(value,str) or not 8 <= len(value.strip()) <= 1000:
        raise ValueError('Motivazione obbligatoria, da 8 a 1000 caratteri.')
    return value.strip()


def _history(app,c,user,cid,pid,kind,record_id,reason,before,after):
    c.execute('''INSERT INTO workforce_history(cid,pid,kind,record_id,stamp,actor,reason,before_data,after_data)
        VALUES(?,?,?,?,?,?,?,?,?)''',(cid,pid,kind,record_id,app.now(),user['username'],reason,_dump(before),_dump(after)))
    app.audit(c,user,'Personale di gruppo: '+kind,cid,before=before,after={'reason':reason,'record':after})


def _validate_contract(raw,cfg):
    keys={'role','contract_type','ccnl','level','weekly_hours','part_time_percent','note'}
    if not isinstance(raw,dict) or set(raw)-keys:
        raise ValueError('Campi contratto non validi.')
    if raw.get('role') not in cfg['roles']:
        raise ValueError('Ruolo non valido per il centro.')
    out={'role':raw['role']}
    for key in ('contract_type','ccnl','level','note'):
        value=raw.get(key,'')
        if not isinstance(value,str) or len(value)>(2000 if key=='note' else 150):
            raise ValueError('Testo contratto non valido: '+key)
        out[key]=value.strip()
    for key,maximum in (('weekly_hours',168),('part_time_percent',100)):
        value=raw.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=maximum:
            raise ValueError('Valore non valido: '+key)
        out[key]=value
    return out


def _save_interval(app,c,user,body,assignment,economic=False):
    cid,pid=assignment['cid'],assignment['pid'];table='workforce_economics' if economic else 'workforce_contracts'
    start=_day(body.get('effective_from'));end=_day(body.get('effective_to',''),True)
    if end and end<start:
        raise ValueError('La fine validità precede la decorrenza.')
    reason=_reason(body);cfg=app.center(c,cid)['config']
    data=agreements.validate(body.get('data'),cfg) if economic else _validate_contract(body.get('data'),cfg)
    rid=body.get('id') or app.uid()
    old=c.execute('SELECT * FROM '+table+' WHERE id=? AND cid=? AND pid=?',(rid,cid,pid)).fetchone()
    if body.get('id') and not old:
        raise ValueError('Versione contrattuale non trovata.')
    if body.get('version',0)!=(old['version'] if old else 0):
        raise ValueError('Decorrenza modificata da un’altra sessione. Ricaricare.')
    if c.execute('SELECT 1 FROM '+table+''' WHERE cid=? AND pid=? AND id<>?
        AND effective_from<=? AND (effective_to='' OR effective_to>=?)''',(cid,pid,rid,end or '9999-12-31',start)).fetchone():
        raise ValueError('Intervalli sovrapposti. Chiudere prima la validità precedente al giorno prima della nuova decorrenza.')
    # Stored agreements for closed months are immutable. Contract corrections are
    # versioned here but are never silently copied over a monthly calculation.
    before={**dict(old),'data':json.loads(old['data'])} if old else None
    after=dict(id=rid,cid=cid,pid=pid,effective_from=start,effective_to=end,version=(old['version'] if old else 0)+1,data=data)
    c.execute('INSERT INTO '+table+''' VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        effective_from=excluded.effective_from,effective_to=excluded.effective_to,version=excluded.version,data=excluded.data''',
        (rid,cid,pid,start,end,after['version'],_dump(data)))
    _history(app,c,user,cid,pid,'economia' if economic else 'contratto',rid,reason,before,after)
    return after


def mutate(app,user,action,body):
    if action not in ('workforce_link','workforce_contract','workforce_economic','workforce_apply'):
        raise ValueError('Operazione personale non valida.')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE');cid=body.get('cid','');pid=body.get('pid','')
        user=_access(app,c,user,cid);assignment=_assignment(c,cid,pid)
        if body.get('assignment_version')!=assignment['version']:
            raise ValueError('Assegnazione modificata da un’altra sessione. Ricaricare.')
        if action=='workforce_link':
            reason=_reason(body);target=body.get('global_id','')
            source_members=c.execute('SELECT cid FROM workforce_assignments WHERE global_id=?',(assignment['global_id'],)).fetchall()
            if any(not _allowed(user,r['cid']) for r in source_members):
                raise PermissionError('Il collegamento coinvolge centri non autorizzati. Rivolgersi a HR centrale.')
            if target:
                target_members=c.execute('SELECT cid FROM workforce_assignments WHERE global_id=?',(target,)).fetchall()
                if not target_members or any(not _allowed(user,r['cid']) for r in target_members):
                    raise PermissionError('Identità di destinazione non disponibile nei centri autorizzati.')
                version=c.execute('SELECT version FROM group_people WHERE id=?',(target,)).fetchone()['version']
                if body.get('target_version')!=version:
                    raise ValueError('Identità di destinazione modificata. Ricaricare.')
                if any(r['cid']==cid for r in target_members):
                    raise ValueError('La persona ha già un’anagrafica in questo centro.')
            else:
                target=app.uid();c.execute('INSERT INTO group_people(id) VALUES(?)',(target,))
            c.execute('UPDATE workforce_assignments SET global_id=? WHERE cid=? AND pid=?',(target,cid,pid))
            c.execute('UPDATE group_people SET version=version+1 WHERE id IN (?,?)',(target,assignment['global_id']))
            after={**assignment,'global_id':target,'version':assignment['version']+1}
            _history(app,c,user,cid,pid,'collegamento',target,reason,assignment,after)
        elif action=='workforce_apply':
            after=_apply(app,c,user,body,assignment)
        else:
            after=_save_interval(app,c,user,body,assignment,action=='workforce_economic')
        c.execute('UPDATE workforce_assignments SET version=version+1 WHERE cid=? AND pid=?',(cid,pid))
        c.execute('UPDATE centers SET revision=revision+1 WHERE id=?',(cid,))
        c.commit()
    return dict(ok=True,record=after,global_id=after['global_id'] if action=='workforce_link' else assignment['global_id'])


def _month_segments(c,cid,pid,month):
    days=month_days(month);start,end=days[0],days[-1]
    return [{**r,'effective_from':max(r['effective_from'],start),'effective_to':min(r['effective_to'] or end,end)}
        for r in reversed(_records(c,'workforce_economics',cid,pid))
        if r['effective_from']<=end and (not r['effective_to'] or r['effective_to']>=start)]


def _schedule_reason(segments,month):
    days=month_days(month)
    if not segments or any(sum(s['effective_from']<=d<=s['effective_to'] for s in segments)!=1 for d in days):
        return 'Le condizioni economiche devono coprire ogni giorno del mese senza vuoti o sovrapposizioni.'
    if any(not s['data']['confirmed'] for s in segments):
        return 'Confermare ogni condizione economica prima di applicarla al mese.'
    if len(segments)==1:
        return ''
    if len({s['data']['model'] for s in segments})!=1:
        return 'Modelli differenti nello stesso mese: accordo mensile manuale necessario.'
    if any(s['data']['model']=='fixed' or s['data']['basis']!='all' or any(s['data'][k]!=0 for k in
        ('fixed_amount','fixed_deduction','adjustment','ccnl_count')) for s in segments):
        return 'Cambio infra-mese con quota fissa, detrazioni, teorico o conguagli: concordare e salvare un accordo mensile manuale. Nessun pro-rata automatico.'
    return ''


def calculate_scheduled(person,entries,month,center_name,cfg,agreement):
    """Called by agreements.calculate only when workforce_segments is present.

    Each component is an ordinary validated agreement without this extension,
    so the existing calculation stays the single source of numerical rules.
    """
    segments=agreement.get('workforce_segments',[])
    reason=_schedule_reason(segments,month)
    if reason:
        base=agreements.calculate(person,entries,month,center_name,cfg,{k:v for k,v in agreement.items() if k!='workforce_segments'})
        base.update(amount=None,status='gestione_manuale',warnings=[reason]);return base
    results=[]
    for segment in segments:
        selected=[e for e in entries if segment['effective_from']<=e['day']<=segment['effective_to']]
        results.append(agreements.calculate(person,selected,month,center_name,cfg,segment['data']))
    if len(results)==1:
        return {**results[0],'agreement':agreement,'effective_segments':segments}
    out=copy.deepcopy(results[0]);out['agreement']=agreement;out['effective_segments']=segments
    for key in ('shifts','external','work_minutes','missing_hours','units','base_units','ordinary_units','festive_units'):
        out[key]=sum(r[key] for r in results)
    out['theoretical']=None  # Basis "all" only: no artificial monthly pro-rata.
    out['absences']={key:sum(r['absences'].get(key,0) for r in results) for key in out['absences']}
    out['warnings']=list(dict.fromkeys(w for r in results for w in r['warnings']))
    blocking=next((r for r in results if r['status'] not in ('calcolato','da_verificare','nessun_dato')),None)
    if blocking:
        out.update(amount=None,status=blocking['status']);return out
    if all(r['amount'] is None for r in results):
        out.update(amount=None,status='nessun_dato');return out
    for key in ('amount','ordinary_amount','festive_amount'):
        out[key]=agreements.money(sum((Decimal(str(r.get(key) or 0)) for r in results),Decimal(0)))
    out['status']='da_verificare' if out['warnings'] else 'calcolato'
    return out


def _preview(app,c,cid,pid,month):
    ct=app.center(c,cid);period=app.period(c,ct,month);segments=_month_segments(c,cid,pid,month)
    reason=_schedule_reason(segments,month);result=None
    if not reason:
        proposal={**segments[0]['data'],'workforce_segments':segments}
        result=calculate_scheduled(effective_person(c,cid,pid,month_days(month)[-1]),app.objects(c,'entries',cid),month,ct['name'],app.effective_rules(ct,period),proposal)
    return dict(cid=cid,pid=pid,month=month,segments=segments,manual_required=bool(reason),message=reason,result=result,
        closed=period['closed'],revision=ct['revision'],current_agreement=period.get('agreements',{}).get(pid))


def preview(app,user,cid,pid,month):
    with app.connect() as c:
        _access(app,c,user,cid)
        return _preview(app,c,cid,pid,month)


def _apply(app,c,user,body,assignment):
    cid,pid=assignment['cid'],assignment['pid'];reason=_reason(body);month=body.get('month','')
    current=_preview(app,c,cid,pid,month)
    if current['closed']:
        raise ValueError('Mese chiuso: riaprirlo prima di cambiare accordo.')
    if current['revision']!=body.get('revision'):
        raise ValueError('Dati del centro cambiati. Ricaricare l’anteprima.')
    if current['manual_required']:
        raise ValueError(current['message'])
    ct=app.center(c,cid);period=app.period(c,ct,month);agreements.freeze(period,app.objects(c,'people',cid))
    before=copy.deepcopy(period['agreements'][pid]);segments=current['segments']
    after={**segments[0]['data'], 'version':before.get('version',0)+1, 'source':reason,
        'updated_by':user['username'],'updated_at':app.now(), 'workforce_segments':segments}
    period['agreements'][pid]=after;period['verified']=False
    app.put_period(c,cid,month,period)
    _history(app,c,user,cid,pid,'applicazione al mese',month,reason,before,after)
    return after
