"""Accordi espliciti per persona/centro/mese. Nessuna formula eseguibile dall'utente."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import copy, math
from rules import duration, month_days

MODELS={'turns','hours','fixed'}

def proposal(cfg, person):
    legacy={**cfg,**(person.get('pay_override') or {})}
    return dict(model='turns',basis=legacy['pay_mode'],theoretical_mode='calendar',theoretical_units=0,
        hours_per_day=6,weekday_rate=legacy['weekday_rate'],holiday_rate=legacy['holiday_rate'],
        fixed_deduction=legacy['fixed_deduction'],fixed_amount=0,adjustment=0,ccnl_rate=0,ccnl_count=0,
        counted_absences=[x['id'] for x in cfg['codes'] if x['kind']=='absence' and x['id']!='RC'],
        include_external=True,confirmed=False,version=0,source='Proposta da verificare')

def validate(raw,cfg):
    base=set(proposal(cfg,{}))-{'version','source'}
    if not isinstance(raw,dict) or not base.issubset(raw):raise ValueError('Accordo incompleto.')
    out={k:copy.deepcopy(raw[k]) for k in base}
    if out['model'] not in MODELS or out['basis'] not in ('surplus','all') or out['theoretical_mode'] not in ('calendar','manual'):
        raise ValueError('Modello di calcolo non valido.')
    for k in ('theoretical_units','hours_per_day','weekday_rate','holiday_rate','fixed_deduction','fixed_amount','adjustment','ccnl_rate','ccnl_count'):
        v=out[k];lo=-1000000 if k=='adjustment' else 0
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=1000000:raise ValueError('Valore non valido: '+k)
    if not 0<out['hours_per_day']<=24:raise ValueError('Ore teoriche giornaliere da 0 escluso a 24.')
    if type(out['confirmed'])!=bool or type(out['include_external'])!=bool:raise ValueError('Conferme non valide.')
    allowed={x['id'] for x in cfg['codes'] if x['kind']!='work'}
    codes=out['counted_absences']
    if not isinstance(codes,list) or any(not isinstance(x,str) or x not in allowed for x in codes):raise ValueError('Causali conteggiabili non valide.')
    out['counted_absences']=list(dict.fromkeys(codes))
    if out['model']=='turns' and out['theoretical_units']%1:raise ValueError('Il teorico a turni deve essere intero.')
    if out['ccnl_count']%1:raise ValueError('Il numero di festivi già riconosciuti deve essere intero.')
    return out

def freeze(period,people):
    """Memorizza la proposta anche per gli accordi ancora da confermare."""
    saved=period.setdefault('agreements',{})
    for person in people:saved.setdefault(person['id'],proposal(period['config'],person))

def money(v):return float(v.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def calculate(person,entries,month,center_name,cfg,agreement):
    if agreement.get('workforce_segments') is not None:
        from workforce import calculate_scheduled
        return calculate_scheduled(person,entries,month,center_name,cfg,agreement)
    a=validate(agreement,cfg)
    es=[e for e in entries if e['person_id']==person['id'] and e['day'].startswith(month+'-') and e['layer']=='actual']
    selected=[e for e in es if a['include_external'] or e['work_site']==center_name]
    work=[e for e in selected if e['kind']=='work']
    absences={x['id']:sum(e['code']==x['id'] for e in es) for x in cfg['codes'] if x['kind']!='work'}
    included=[e for e in selected if e['kind']=='work' or e['code'] in a['counted_absences']]
    calendar_days=sum(date.fromisoformat(d).weekday() in cfg['weekdays'] and d not in cfg['holidays'] for d in month_days(month))
    theoretical=Decimal(str(a['theoretical_units'])) if a['theoretical_mode']=='manual' else Decimal(calendar_days)*(Decimal(str(a['hours_per_day'])) if a['model']=='hours' else 1)
    missing=sum(duration(e) is None for e in work)
    work_minutes=sum(duration(e) or 0 for e in work)
    if a['model']=='hours':
        total=Decimal(sum((duration(e) or 0) if e['kind']=='work' else e.get('credit_minutes',0) for e in included))/60
        festive=Decimal(sum(duration(e) or 0 for e in work if e['holiday']))/60
    else:
        total=Decimal(len(included));festive=Decimal(sum(bool(e['holiday']) for e in work))
    base=total-theoretical if a['basis']=='surplus' else total
    ordinary=base-festive
    out=dict(person_id=person['id'],name=person['name'],role=person['role'],agreement=agreement,
        shifts=len(work),external=sum(e['kind']=='work' and e['work_site']!=center_name for e in es),
        absences=absences,work_minutes=work_minutes,missing_hours=missing,calendar_days=calendar_days,
        units=float(total),theoretical=float(theoretical),base_units=float(base),ordinary_units=float(ordinary),festive_units=float(festive),
        amount=None,status='da_confermare',warnings=[])
    if not a['confirmed']:out['warnings'].append('Accordo del dipendente e calendario da confermare.');return out
    if a['model']=='hours' and missing:out['status']='orari_mancanti';out['warnings'].append('Completare gli orari effettivi prima di calcolare a ore.');return out
    if not included and a['model']!='fixed':out['status']='nessun_dato';return out
    d=lambda k:Decimal(str(a[k]))
    ordinary_amount=ordinary*d('weekday_rate') if a['model']!='fixed' else Decimal(0)
    festive_amount=festive*d('holiday_rate') if a['model']!='fixed' else Decimal(0)
    amount=ordinary_amount+festive_amount+d('fixed_amount')-d('fixed_deduction')+d('adjustment')-d('ccnl_count')*d('ccnl_rate')
    out.update(amount=money(amount),ordinary_amount=money(ordinary_amount),festive_amount=money(festive_amount),status='calcolato')
    if a['model']!='fixed' and ordinary<0:out['warnings'].append('Unità feriali negative: verificare teorico e accordo; nessun azzeramento automatico.')
    if amount<0:out['warnings'].append('Importo negativo da verificare.')
    if any('da specificare' in e['work_site'] for e in selected):out['warnings'].append('Sono presenti sedi effettive da specificare.')
    if out['warnings']:out['status']='da_verificare'
    return out

def report(core,user,cid,month):
    with core.connect() as c:
        user=core.fresh_user(c,user);core.require_hr(user,cid)
        ct=core.center(c,cid);p=core.period(c,ct,month);people=core.objects(c,'people',cid);entries=core.objects(c,'entries',cid)
    cfg=core.effective_rules(ct,p)
    rows=[calculate(person,entries,month,ct['name'],cfg,p.get('agreements',{}).get(person['id'],proposal(p['config'],person))) for person in people]
    return dict(cid=cid,month=month,closed=p['closed'],verified=p['verified'],revision=ct['revision'],rows=rows)
