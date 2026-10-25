"""Accordi individuali del mese e calcolo dei compensi variabili.

Nessuna formula è eseguibile dall'utente: tre modelli fissi (a turni, a ore,
quota fissa) con parametri validati. Una proposta viene calcolata dai parametri
del mese e dall'accordo personale; diventa un accordo solo quando il
responsabile la salva con una motivazione. Senza conferma non si calcola alcun
importo. Il risultato è una base di verifica per l'ufficio paghe, non un cedolino.
"""
import copy
import math
from decimal import ROUND_HALF_UP, Decimal

from . import approvals, audit, centers, months, people, rules
from .errors import Conflict, Invalid, NotFound
from .permissions import has
from .util import dumps, loads, month_days, stamp
from . import validate as v

MODELS = ('turns', 'hours', 'fixed')
NUMBERS = ('theoretical_units', 'hours_per_day', 'weekday_rate', 'holiday_rate', 'fixed_deduction', 'fixed_amount',
           'adjustment', 'ccnl_rate', 'ccnl_count')
FIELDS = set(NUMBERS) | {'model', 'basis', 'theoretical_mode', 'counted_absences', 'include_external', 'confirmed'}
STATUS_LABELS = {'calcolato': 'Calcolato', 'da_confermare': 'Accordo da confermare', 'da_verificare': 'Da verificare',
                 'orari_mancanti': 'Orari mancanti', 'nessun_dato': 'Nessun dato', 'gestione_manuale': 'Gestione manuale'}


def proposal(cfg, person):
    base = {**cfg, **((person or {}).get('pay_override') or {})}
    return dict(model='turns', basis=base['pay_mode'], theoretical_mode='calendar', theoretical_units=0, hours_per_day=6,
                weekday_rate=base['weekday_rate'], holiday_rate=base['holiday_rate'], fixed_deduction=base['fixed_deduction'],
                fixed_amount=0, adjustment=0, ccnl_rate=0, ccnl_count=0,
                counted_absences=[c['id'] for c in cfg['codes'] if c['kind'] == 'absence' and c['id'] != 'RC'],
                include_external=True, confirmed=False)


def validate(raw, cfg):
    if not isinstance(raw, dict) or not FIELDS <= set(raw):
        raise Invalid('Accordo incompleto: ricaricare la pagina.', field='agreement')
    out = {k: copy.deepcopy(raw[k]) for k in FIELDS}
    out['model'] = v.choice(out['model'], 'Modello di calcolo', MODELS, field='model')
    out['basis'] = v.choice(out['basis'], 'Base di calcolo', ('surplus', 'all'), field='basis')
    out['theoretical_mode'] = v.choice(out['theoretical_mode'], 'Teorico', ('calendar', 'manual'), field='theoretical_mode')
    for key in NUMBERS:
        lo = -1_000_000 if key == 'adjustment' else 0
        out[key] = v.number(out[key], key.replace('_', ' ').capitalize(), lo, 1_000_000, field=key)
    if not 0 < out['hours_per_day'] <= 24:
        raise Invalid('Ore teoriche giornaliere: da 0 escluso a 24.', field='hours_per_day')
    out['confirmed'] = v.boolean(out['confirmed'], 'Accordo confermato', field='confirmed')
    out['include_external'] = v.boolean(out['include_external'], 'Includere i turni fuori sede', field='include_external')
    allowed = {c['id'] for c in cfg['codes'] if c['kind'] != 'work'}
    out['counted_absences'] = v.str_list(out['counted_absences'], 'Causali conteggiate', maximum=80, allowed=allowed,
                                         field='counted_absences')
    if out['model'] == 'turns' and out['theoretical_units'] % 1:
        raise Invalid('Il teorico a turni deve essere un numero intero.', field='theoretical_units')
    if out['ccnl_count'] % 1:
        raise Invalid('Il numero di festivi già riconosciuti deve essere intero.', field='ccnl_count')
    return out


def money(value):
    return float(Decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def calculate(person, entries, month, cfg, agreement):
    """entries: registrazioni del mese (anche di altre persone); agreement: proposta o accordo salvato."""
    if agreement.get('segments'):
        return calculate_segments(person, entries, month, cfg, agreement)
    a = validate(agreement, cfg)
    mine = [e for e in entries if e['person_id'] == person['id'] and e['day'].startswith(month + '-') and e['layer'] == 'actual']
    selected = [e for e in mine if a['include_external'] or not e['site']]
    work = [e for e in selected if e['kind'] == 'work']
    absences = {c['id']: sum(e['code'] == c['id'] for e in mine) for c in cfg['codes'] if c['kind'] != 'work'}
    included = [e for e in selected if e['kind'] == 'work' or e['code'] in a['counted_absences']]
    calendar_days = rules.working_days(month_days(month), cfg)
    if a['theoretical_mode'] == 'manual':
        theoretical = Decimal(str(a['theoretical_units']))
    else:
        theoretical = Decimal(calendar_days) * (Decimal(str(a['hours_per_day'])) if a['model'] == 'hours' else 1)
    missing = sum(rules.duration(e) is None for e in work)
    work_minutes = sum(rules.duration(e) or 0 for e in work)
    if a['model'] == 'hours':
        total = Decimal(sum((rules.duration(e) or 0) if e['kind'] == 'work' else e['credit'] for e in included)) / 60
        festive = Decimal(sum(rules.duration(e) or 0 for e in work if e['holiday'])) / 60
    else:
        total = Decimal(len(included))
        festive = Decimal(sum(bool(e['holiday']) for e in work))
    base = total - theoretical if a['basis'] == 'surplus' else total
    ordinary = base - festive
    out = dict(person_id=person['id'], name=person['name'], role=person['role'], registration=person.get('registration', ''),
               agreement=agreement, shifts=len(work), external=sum(e['kind'] == 'work' and bool(e['site']) for e in mine),
               absences=absences, work_minutes=work_minutes, missing_hours=missing, calendar_days=calendar_days,
               units=float(total), theoretical=float(theoretical), base_units=float(base), ordinary_units=float(ordinary),
               festive_units=float(festive), amount=None, ordinary_amount=None, festive_amount=None,
               status='da_confermare', warnings=[])
    if not a['confirmed']:
        out['warnings'].append('Accordo e calendario da confermare: nessun importo calcolato.')
        return out
    if a['model'] == 'hours' and missing:
        out['status'] = 'orari_mancanti'
        out['warnings'].append('Completare gli orari effettivi prima del calcolo a ore.')
        return out
    if not included and a['model'] != 'fixed':
        out['status'] = 'nessun_dato'
        return out
    d = lambda k: Decimal(str(a[k]))  # noqa: E731
    ordinary_amount = ordinary * d('weekday_rate') if a['model'] != 'fixed' else Decimal(0)
    festive_amount = festive * d('holiday_rate') if a['model'] != 'fixed' else Decimal(0)
    amount = ordinary_amount + festive_amount + d('fixed_amount') - d('fixed_deduction') + d('adjustment') - d('ccnl_count') * d('ccnl_rate')
    out.update(amount=money(amount), ordinary_amount=money(ordinary_amount), festive_amount=money(festive_amount),
               status='calcolato')
    if a['model'] != 'fixed' and ordinary < 0:
        out['warnings'].append('Unità feriali negative: verificare teorico e accordo (nessun azzeramento automatico).')
    if amount < 0:
        out['warnings'].append('Importo negativo da verificare.')
    if any(e['review'] for e in selected):
        out['warnings'].append('Sono presenti registrazioni importate da verificare.')
    if out['warnings']:
        out['status'] = 'da_verificare'
    return out


# --- Condizioni economiche con decorrenze (personale di gruppo) ---------------------------------

def segments_problem(segments, month):
    days = month_days(month)
    if not segments or any(sum(s['valid_from'] <= d <= s['valid_to'] for s in segments) != 1 for d in days):
        return 'Le condizioni economiche devono coprire ogni giorno del mese senza vuoti né sovrapposizioni.'
    if any(not s['data']['confirmed'] for s in segments):
        return 'Confermare ogni condizione economica prima di applicarla al mese.'
    if len(segments) == 1:
        return ''
    if len({s['data']['model'] for s in segments}) != 1:
        return 'Modelli diversi nello stesso mese: serve un accordo mensile manuale.'
    if any(s['data']['model'] == 'fixed' or s['data']['basis'] != 'all'
           or any(s['data'][k] != 0 for k in ('fixed_amount', 'fixed_deduction', 'adjustment', 'ccnl_count')) for s in segments):
        return ('Cambio a metà mese con quota fissa, detrazioni, teorico o conguagli: concordare e salvare un accordo '
                'mensile manuale. Nessun calcolo proporzionale automatico.')
    return ''


def calculate_segments(person, entries, month, cfg, agreement):
    segments = agreement['segments']
    problem = segments_problem(segments, month)
    plain = {k: val for k, val in agreement.items() if k != 'segments'}
    if problem:
        out = calculate(person, entries, month, cfg, plain)
        out.update(amount=None, ordinary_amount=None, festive_amount=None, status='gestione_manuale', warnings=[problem])
        return out
    results = []
    for s in segments:
        part = [e for e in entries if s['valid_from'] <= e['day'] <= s['valid_to']]
        results.append(calculate(person, part, month, cfg, s['data']))
    if len(results) == 1:
        return {**results[0], 'agreement': agreement, 'segments': segments}
    out = copy.deepcopy(results[0])
    out.update(agreement=agreement, segments=segments, theoretical=None)
    for key in ('shifts', 'external', 'work_minutes', 'missing_hours', 'units', 'base_units', 'ordinary_units', 'festive_units'):
        out[key] = sum(r[key] for r in results)
    out['absences'] = {k: sum(r['absences'].get(k, 0) for r in results) for k in out['absences']}
    out['warnings'] = list(dict.fromkeys(w for r in results for w in r['warnings']))
    blocking = next((r for r in results if r['status'] not in ('calcolato', 'da_verificare', 'nessun_dato')), None)
    if blocking:
        out.update(amount=None, ordinary_amount=None, festive_amount=None, status=blocking['status'])
        return out
    if all(r['amount'] is None for r in results):
        out.update(amount=None, status='nessun_dato')
        return out
    for key in ('amount', 'ordinary_amount', 'festive_amount'):
        out[key] = money(sum((Decimal(str(r.get(key) or 0)) for r in results), Decimal(0)))
    out['status'] = 'da_verificare' if out['warnings'] else 'calcolato'
    return out


# --- Archivio ------------------------------------------------------------------------------------

def stored(con, center_id, month):
    return {r['person_id']: dict(data=loads(r['data']), source=r['source'], version=r['version'], updated_at=r['updated_at'],
                                 updated_by=r['updated_by'])
            for r in con.execute('SELECT * FROM agreements WHERE center_id=? AND month=?', (center_id, month))}


def month_rows(con, center_id, month):
    """Calcolo per tutte le persone del mese (accordo salvato o proposta)."""
    state = months.get(con, center_id, month)
    cfg, _ = months.configuration(con, center_id, state)
    persons = months.people(con, center_id)
    entries = months.entries(con, center_id, month)
    saved = stored(con, center_id, month)
    rows = []
    for p in persons:
        current = saved.get(p['id'])
        agreement = current['data'] if current else proposal(cfg, p)
        result = calculate(p, entries, month, cfg, agreement)
        result.update(saved=bool(current), version=current['version'] if current else 0,
                      source=current['source'] if current else 'Proposta da verificare',
                      updated_by=current['updated_by'] if current else '', updated_at=current['updated_at'] if current else '',
                      status_label=STATUS_LABELS[result['status']], active=p['active'])
        rows.append(result)
    return state, cfg, rows


def report(db, user, center_id, month):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'accordi.vedi')
        state, cfg, rows = month_rows(con, center_id, month)
        approval = approvals.metadata(con, user, center_id, month)
    totals = dict(amount=money(sum((Decimal(str(r['amount'])) for r in rows if r['amount'] is not None), Decimal(0))),
                  calculated=sum(r['amount'] is not None for r in rows), to_confirm=sum(r['status'] == 'da_confermare' for r in rows))
    return dict(center=dict(id=center['id'], name=center['name']), month=month, closed=state['closed'],
                verified=state['verified'], rules_version=state['rules_version'], rows=rows, totals=totals,
                parameters={k: cfg[k] for k in ('weekday_rate', 'holiday_rate', 'fixed_deduction', 'ccnl_rate', 'pay_mode')},
                absence_codes=[dict(id=c['id'], label=c['label']) for c in cfg['codes'] if c['kind'] != 'work'],
                editable=has(user, 'accordi.modifica') and not state['closed'] and not approval['frozen'],
                approval=approval)


def write_agreement(con, actor, center_id, month, person_id, data, reason, expected_version):
    current = stored(con, center_id, month).get(person_id)
    if expected_version != (current['version'] if current else 0):
        raise Conflict('Accordo modificato da un’altra sessione: ricaricare.')
    version = (current['version'] if current else 0) + 1
    con.execute('''INSERT INTO agreements(center_id,month,person_id,data,source,version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(center_id,month,person_id) DO UPDATE SET data=excluded.data,
                   source=excluded.source, version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                (center_id, month, person_id, dumps(data), reason, version, stamp(), actor.username))
    months.update(con, center_id, month, actor, verified=False)
    audit.record(con, actor, 'Accordo del mese salvato', center_id, entity='agreement', entity_id=f'{month}|{person_id}',
                 before=current['data'] if current else None, after=dict(data=data, reason=reason))
    return version


def save(db, actor, center_id, month, person_id, raw):
    v.month(month)
    v.keys(raw, {'agreement', 'reason', 'version'}, 'Accordo', required={'agreement', 'reason', 'version'})
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'accordi.modifica')
        state = months.get(con, center_id, month)
        months.require_open(state)
        approvals.guard_month(con, actor, center_id, month)
        people.get(con, center_id, person_id)
        cfg, _ = months.configuration(con, center_id, state)
        data = validate(raw['agreement'], cfg)
        version = write_agreement(con, actor, center_id, month, person_id, data, reason, v.version(raw['version']))
    return dict(version=version)


def simulate_excel(total, theoretical, festive, ccnl_festive=0, weekday_rate=50, holiday_rate=70, fixed_deduction=100,
                   ccnl_rate=70, all_shifts=False):
    """Riproduce le celle AV:BA del modello Excel di origine. Valori negativi conservati."""
    values = (total, theoretical, festive, ccnl_festive, weekday_rate, holiday_rate, fixed_deduction, ccnl_rate)
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in values):
        raise Invalid('Inserire valori numerici non negativi.')
    if any(int(x) != x for x in (total, theoretical, festive, ccnl_festive)):
        raise Invalid('Il modello conta turni interi: inserire conteggi interi.')
    if total == 0 and not all_shifts:
        return dict(calculated=False, extra=None, ordinary=None, ordinary_amount=None, holiday_amount=None, total=None,
                    reason='Con zero turni il modello Excel lascia vuoti i risultati (cella AT uguale a zero).')
    extra = total if all_shifts else total - theoretical
    ordinary = extra - festive
    return dict(calculated=True, extra=extra, ordinary=ordinary, ordinary_amount=ordinary * weekday_rate,
                holiday_amount=festive * holiday_rate,
                total=ordinary * weekday_rate + festive * holiday_rate - fixed_deduction - ccnl_festive * ccnl_rate)


def simulate(db, user, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'person_id', 'total', 'festive', 'ccnl_festive'}, 'Simulazione', required={'total', 'festive'})
    with db.read() as con:
        user, _ = centers.scoped(con, user, center_id, 'accordi.vedi')
        state = months.get(con, center_id, month)
        cfg, _ = months.configuration(con, center_id, state)
        params = dict(cfg)
        if raw.get('person_id'):
            person = people.get(con, center_id, v.identifier(raw['person_id'], 'Persona'))
            params.update(person['pay_override'] or {})
    theoretical = rules.working_days(month_days(month), cfg)
    out = simulate_excel(raw['total'], theoretical, raw['festive'], raw.get('ccnl_festive', 0), params['weekday_rate'],
                         params['holiday_rate'], params['fixed_deduction'], params['ccnl_rate'], params['pay_mode'] == 'all')
    out['theoretical'] = theoretical
    out['parameters'] = {k: params[k] for k in ('weekday_rate', 'holiday_rate', 'fixed_deduction', 'ccnl_rate', 'pay_mode')}
    return out


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/agreements/<cid>/<month>', cap='accordi.vedi')
def api_report(ctx):
    return report(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])


@route('PUT', '/api/agreements/<cid>/<month>/<pid>', cap='accordi.modifica', step_up=True)
def api_save(ctx):
    return save(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.params['pid'], ctx.body)


@route('POST', '/api/agreements/<cid>/<month>/simulate', cap='accordi.vedi')
def api_simulate(ctx):
    return simulate(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)
