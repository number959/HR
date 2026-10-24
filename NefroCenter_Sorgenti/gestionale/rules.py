"""Regole configurabili per centro e copie storiche dei parametri per mese."""
import calendar, copy, math, re
from datetime import date, datetime, timedelta
from engine import ABSENCE, month_days, simulate_legacy_pay

def defaults():
    slots=[]
    for code,label,start,end,night,color in [('m','Mattina','07:00','13:00',False,'#cda648'),('p','Pomeriggio','13:00','19:00',False,'#d98c53'),('s','Serale','19:00','23:00',False,'#6a8ab5'),('n','Notte','21:00','07:00',True,'#8673b5')]:
        slots.append(dict(id=code,label=label,start=start,end=end,overnight=night,pause=0,color=color,active=True))
    codes=[dict(id=s['id'],label=s['label'],kind='work',credit_minutes=0,color=s['color'],active=True,allowed_slots=[s['id']]) for s in slots]
    codes += [dict(id=k,label=v,kind='rest' if k=='R' else 'absence',credit_minutes=0,color='#4d9a80',active=True,allowed_slots=[]) for k,v in ABSENCE.items()]
    return dict(slots=slots,codes=codes,roles=['INF','MED','DS','OSS','AMM','ALTRO'],weekdays=[0,1,2,3,4,5],holidays=[],
        sites=[],min_rest_hours=11,require_times_on_close=False,operator_edit_times=False,operator_choose_site=False,
        operator_mark_holiday=False,operator_delete=True,operator_export=True,operator_planned=True,
        nurse_roles=['INF'],doctor_roles=['MED','DS'],nurse_reference=5,doctor_reference=20,isolation_weight=5,
        weekday_rate=50,holiday_rate=70,fixed_deduction=100,ccnl_rate=70,pay_mode='surplus',
        csv_separator=';',note='Valori iniziali da verificare. Orari proposti, non ricavati dall’Excel.')

def clock(value):
    return isinstance(value,str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value) is not None

def number(v,lo,hi,integer=False):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (integer and int(v)!=v):
        raise ValueError('Valore numerico fuori intervallo.')
    return v

def validate_config(raw):
    if set(raw)!=set(defaults()):raise ValueError('Configurazione incompleta o con campi non previsti.')
    c=copy.deepcopy(raw)
    for key,limit in [('slots',16),('codes',80)]:
        if not isinstance(c[key],list) or not 1<=len(c[key])<=limit:raise ValueError('Numero di fasce o causali non valido.')
        ids=set()
        for row in c[key]:
            if not isinstance(row,dict) or not re.fullmatch('[A-Za-z0-9_]{1,12}',str(row.get('id',''))):raise ValueError('Codici: usare lettere, numeri o underscore, massimo 12 caratteri.')
            if row['id'].casefold() in ids:raise ValueError('Codice duplicato: '+row['id'])
            ids.add(row['id'].casefold())
            if not str(row.get('label','')).strip() or len(str(row['label']))>100:raise ValueError('Etichetta obbligatoria, massimo 100 caratteri.')
            if not re.fullmatch('#[a-fA-F0-9]{6}',str(row.get('color',''))):raise ValueError('Colore non valido.')
            if type(row.get('active'))!=bool:raise ValueError('Stato causale non valido.')
            if key=='slots':
                if not clock(row.get('start')) or not clock(row.get('end')) or type(row.get('overnight'))!=bool:raise ValueError('Orari di fascia non validi.')
                number(row.get('pause'),0,1439,True)
                a=datetime.fromisoformat('2026-01-01T'+row['start']);b=datetime.fromisoformat('2026-01-01T'+row['end'])+timedelta(days=int(row['overnight']))
                if not row['pause']<(b-a).total_seconds()/60<=1440:raise ValueError('Durata o pausa della fascia non valida.')
            else:
                if row.get('kind') not in ('work','absence','rest'):raise ValueError('Tipo causale non valido.')
                number(row.get('credit_minutes'),0,1440,True)
                if row['kind']!='absence' and row['credit_minutes']!=0:raise ValueError('Il credito minuti è riservato alle assenze.')
    for code in c['codes']:
        allowed=code.get('allowed_slots')
        if not isinstance(allowed,list) or any(s not in {v['id'] for v in c['slots']} for s in allowed):raise ValueError('Fasce autorizzate della causale non valide.')
    if not any(s['active'] for s in c['slots']) or not any(s['active'] for s in c['codes']):raise ValueError('Mantenere almeno una fascia e una causale attiva.')
    for key,limit in [('roles',50),('sites',100),('nurse_roles',50),('doctor_roles',50)]:
        if not isinstance(c[key],list) or len(c[key])>limit or any(not isinstance(x,str) or not x.strip() or len(x)>120 for x in c[key]):raise ValueError('Elenco '+key+' non valido.')
        c[key]=list(dict.fromkeys(x.strip() for x in c[key]))
    if not c['roles']:raise ValueError('Definire almeno un ruolo.')
    if any(r not in c['roles'] for r in c['nurse_roles']+c['doctor_roles']):raise ValueError('Ruolo di carico non presente nell’elenco dei ruoli.')
    if set(c['nurse_roles'])&set(c['doctor_roles']):raise ValueError('Un ruolo non può essere sia infermiere sia medico per il carico.')
    if not isinstance(c['weekdays'],list) or not c['weekdays'] or any(type(v)!=int or v not in range(7) for v in c['weekdays']):raise ValueError('Calendario settimanale non valido.')
    c['weekdays']=sorted(set(c['weekdays']))
    if not isinstance(c['holidays'],list) or len(c['holidays'])>2000:raise ValueError('Elenco festività non valido.')
    for d in c['holidays']:date.fromisoformat(d)
    c['holidays']=sorted(set(c['holidays']))
    for k in ('require_times_on_close','operator_edit_times','operator_choose_site','operator_mark_holiday','operator_delete','operator_export','operator_planned'):
        if type(c[k])!=bool:raise ValueError('Opzione non valida: '+k)
    number(c['min_rest_hours'],0,48)
    for k in ('nurse_reference','doctor_reference','isolation_weight'):number(c[k],.01,1000)
    for k in ('weekday_rate','holiday_rate','fixed_deduction','ccnl_rate'):number(c[k],0,100000)
    if c['pay_mode'] not in ('surplus','all'):raise ValueError('Modalità economica non valida.')
    if c['csv_separator'] not in (';',',','\t'):raise ValueError('Separatore non valido.')
    c['note']=str(c['note'])[:4000]
    return c

def span(e):
    if e['kind']!='work' or not e['start'] or not e['end']:return None
    a=datetime.fromisoformat(e['day']+'T'+e['start']);b=datetime.fromisoformat(e['day']+'T'+e['end'])+timedelta(days=int(e['overnight']))
    return a,b

def duration(e):
    s=span(e)
    return None if s is None else int((s[1]-s[0]).total_seconds()/60)-e['pause']

def make_entry(raw,config,person,center_name,role,existing,old=None):
    day=str(raw.get('day',''));date.fromisoformat(day)
    slot=next((s for s in config['slots'] if s['id']==raw.get('slot')),None)
    code=next((s for s in config['codes'] if s['id']==raw.get('code')),None)
    if not slot or not code or not slot['active'] or not code['active']:raise ValueError('Fascia o causale non autorizzata.')
    if code['allowed_slots'] and slot['id'] not in code['allowed_slots']:raise ValueError('Causale non autorizzata per questa fascia.')
    layer=raw.get('layer')
    if layer not in ('actual','planned'):raise ValueError('Registro non valido.')
    if role!='admin' and layer=='planned' and not config['operator_planned']:raise PermissionError('Pianificazione riservata all’amministratore.')
    e=dict(id=raw.get('id',''),person_id=person['id'],day=day,slot=slot['id'],code=code['id'],kind=code['kind'],code_label=code['label'],
        layer=layer,start='',end='',pause=0,overnight=False,work_site=center_name,holiday=day in config['holidays'],note=str(raw.get('note',''))[:2000],credit_minutes=code['credit_minutes'])
    if code['kind']=='work':
        expected={k:slot[k] for k in ('start','end','pause','overnight')}
        if role!='admin' and not config['operator_edit_times']:
            if old and old['kind']=='work':expected={k:old[k] for k in expected}
            for k,v in expected.items():
                if k in raw and raw[k]!=v:raise PermissionError('Gli orari e le pause sono bloccati dall’amministratore.')
            e.update(expected)
        else:e.update({k:raw.get(k,v) for k,v in expected.items()})
        if type(e['overnight'])!=bool:raise ValueError('Giorno successivo non valido.')
        if bool(e['start'])!=bool(e['end']) or any(t and not clock(t) for t in (e['start'],e['end'])):raise ValueError('Indicare entrambi gli orari nel formato HH:MM.')
        number(e['pause'],0,1439,True)
        if not e['start'] and e['pause']:raise ValueError('Pausa senza orari.')
        s=span(e)
        if s and not e['pause']<(s[1]-s[0]).total_seconds()/60<=1440:raise ValueError('Durata o pausa non valida.')
    site=str(raw.get('work_site',old['work_site'] if old else center_name)).strip()
    expected_site=old['work_site'] if old else center_name
    if role!='admin' and not config['operator_choose_site']:
        if site!=expected_site:raise PermissionError('La sede effettiva è bloccata.')
        site=expected_site
    if site not in [center_name]+config['sites']:raise ValueError('Sede non inclusa fra quelle autorizzate.')
    e['work_site']=site
    expected_holiday=old['holiday'] if old else e['holiday']
    holiday=raw.get('holiday',expected_holiday)
    if type(holiday)!=bool:raise ValueError('Festivo non valido.')
    if role!='admin' and not config['operator_mark_holiday'] and holiday!=expected_holiday:raise PermissionError('La classificazione festiva è bloccata.')
    e['holiday']=holiday
    warnings=[]
    s=span(e)
    for other in existing:
        if other['id']==e['id'] or other['person_id']!=e['person_id'] or other['layer']!=e['layer']:continue
        if other['day']==day and other['slot']==e['slot']:raise ValueError('La fascia è già compilata. Aprirla per modificarla.')
        o=span(other)
        if s and o:
            if s[0]<o[1] and o[0]<s[1]:raise ValueError('Sovrapposizione con il '+other['day'])
            gap=min(abs((s[0]-o[1]).total_seconds()),abs((o[0]-s[1]).total_seconds()))/3600
            if gap<config['min_rest_hours']:warnings.append('Intervallo inferiore a '+str(config['min_rest_hours'])+' ore.')
    return e,list(dict.fromkeys(warnings))

def totals(people,entries,month):
    rows=[]
    for p in people:
        actual=[e for e in entries if e['person_id']==p['id'] and e['day'].startswith(month) and e['layer']=='actual']
        work=[e for e in actual if e['kind']=='work'];absence=[e for e in actual if e['kind']=='absence'];known=[duration(e) for e in work if duration(e) is not None]
        planned=[e for e in entries if e['person_id']==p['id'] and e['day'].startswith(month) and e['layer']=='planned']
        rows.append({**p,'shifts':len(work),'days':len({e['day'] for e in work}),'minutes':sum(known),'missing':len(work)-len(known),
            'external':sum(e['work_site']!=p['home_site'] for e in work),'festive':sum(e['holiday'] for e in work),
            'absence_slots':len(absence),'credit_minutes':sum(e['credit_minutes'] for e in absence),
            'pending':sum(not any(a['day']==e['day'] and a['slot']==e['slot'] for a in actual) for e in planned),
            'causes':{c:sum(e['code']==c for e in actual) for c in sorted({e['code'] for e in actual})}})
    return rows
