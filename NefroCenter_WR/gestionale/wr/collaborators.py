"""Prospetto dei collaboratori a prestazione: il foglio «Collaboratori» del vecchio modello Excel, calcolato dal portale.

Per ogni persona della struttura che non è dipendente (tipo di rapporto nel fascicolo: professionista con fattura,
associazione o cooperativa, volontario, dipendente di un'altra struttura, altro) il prospetto del mese riporta turni
feriali e festivi, compenso lordo dall'accordo del mese, ritenuta d'acconto e contributo cassa con le percentuali del
fascicolo, netto da pagare, chi emette la fattura, IBAN e intestatario. I totali sono per gruppo e complessivi.
Il compenso esiste solo se l'accordo del mese è confermato: non si inventano tariffe.
"""
from decimal import Decimal, ROUND_HALF_UP

from . import agreements, approvals, audit, centers, hr, months, users
from .permissions import has, require
from . import validate as v
from .web import Reply, route

GROUP_ORDER = [code for code, _ in hr.RELATIONSHIPS if code != hr.EMPLOYEE]


def _money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _rate(text):
    if not text:
        return 0.0
    return float(str(text).replace(',', '.'))


def rows_for(con, center_id, month, user):
    """Righe del prospetto del mese. Le coordinate bancarie restano solo a chi gestisce le paghe."""
    state, cfg, results = agreements.month_rows(con, center_id, month)
    bank = has(user, 'paghe.gestisci')
    out = []
    for r in results:
        prof = hr.profile(con, r['person_id'])
        fields = prof['fields']
        relationship = hr.relationship_of(fields)
        if relationship == hr.EMPLOYEE:
            continue
        if not r.get('active', True) and not r['shifts'] and r['amount'] is None:
            continue
        gross = r['amount']
        withholding_rate, fund_rate = _rate(fields.get('withholding_rate')), _rate(fields.get('fund_rate'))
        withholding = fund = net = None
        if gross is not None:
            withholding = _money(Decimal(str(gross)) * Decimal(str(withholding_rate)) / 100)
            fund = _money(Decimal(str(gross)) * Decimal(str(fund_rate)) / 100)
            net = _money(Decimal(str(gross)) + Decimal(str(fund)) - Decimal(str(withholding)))
        notes = [r['source']] if r.get('saved') else []
        if r['agreement'].get('fixed_amount'):
            notes.append(f'quota fissa {r["agreement"]["fixed_amount"]:g} €')
        if r['agreement'].get('adjustment'):
            notes.append(f'conguaglio {r["agreement"]["adjustment"]:g} €')
        out.append(dict(person_id=r['person_id'], name=r['name'], role=r['role'], relationship=relationship,
                        relationship_label=hr.relationship_label(relationship), billing_entity=fields.get('billing_entity', ''),
                        shifts=r['shifts'], external=r['external'], ordinary_units=r['ordinary_units'], festive_units=r['festive_units'],
                        units=r['units'], model=r['agreement']['model'], weekday_rate=r['agreement']['weekday_rate'],
                        holiday_rate=r['agreement']['holiday_rate'], gross=gross, withholding_rate=withholding_rate,
                        withholding=withholding, fund_name=fields.get('fund_name', ''), fund_rate=fund_rate, fund=fund, net=net,
                        iban=fields.get('iban', '') if bank else '', account_holder=fields.get('account_holder', '') if bank else '',
                        payment_method=fields.get('payment_method', ''), status=r['status'], status_label=r['status_label'],
                        warnings=r['warnings'], notes='; '.join(n for n in notes if n), saved=r.get('saved', False)))
    out.sort(key=lambda x: (GROUP_ORDER.index(x['relationship']) if x['relationship'] in GROUP_ORDER else 99, x['name'].casefold()))
    return state, cfg, out


def _totals(rows):
    def total(key):
        values = [Decimal(str(r[key])) for r in rows if r[key] is not None]
        return _money(sum(values, Decimal(0))) if values else None
    return dict(people=len(rows), shifts=sum(r['shifts'] for r in rows), ordinary_units=sum(r['ordinary_units'] for r in rows),
                festive_units=sum(r['festive_units'] for r in rows), gross=total('gross'), withholding=total('withholding'),
                fund=total('fund'), net=total('net'), calculated=sum(r['gross'] is not None for r in rows))


def statement(db, user, center_id, month):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'accordi.vedi')
        state, cfg, rows = rows_for(con, center_id, month, user)
        approval = approvals.metadata(con, user, center_id, month)
    groups = []
    for code in GROUP_ORDER:
        mine = [r for r in rows if r['relationship'] == code]
        if mine:
            groups.append(dict(relationship=code, label=hr.relationship_label(code), rows=mine, totals=_totals(mine)))
    return dict(center=dict(id=center['id'], name=center['name'], code=center['code']), month=month, closed=state['closed'],
                verified=state['verified'], approval=dict(status=approval['status'], label=approval['label'], frozen=approval['frozen']),
                groups=groups, totals=_totals(rows),
                bank_visible=has(user, 'paghe.gestisci'), can_export=has(user, 'paghe.gestisci'),
                relationships=[dict(id=c, label=l) for c, l in hr.RELATIONSHIPS])


def export_xlsx(db, user, center_id, month):
    """Foglio Excel del prospetto: una riga per collaboratore, totali per gruppo, dati bancari inclusi (riservato)."""
    from . import exports
    data = statement(db, user, center_id, month)
    rows = []
    for g in data['groups']:
        for r in g['rows']:
            rows.append([g['label'], r['name'], r['role'], r['billing_entity'], r['shifts'], r['ordinary_units'], r['festive_units'],
                         r['weekday_rate'], r['holiday_rate'], r['gross'], r['withholding_rate'], r['withholding'], r['fund_name'],
                         r['fund_rate'], r['fund'], r['net'], r['payment_method'], r['iban'], r['account_holder'], r['status_label'],
                         r['notes'] + (' · ' if r['notes'] and r['warnings'] else '') + '; '.join(r['warnings'])])
        t = g['totals']
        rows.append([f'Totale {g["label"].lower()}', '', '', '', t['shifts'], t['ordinary_units'], t['festive_units'], None, None,
                     t['gross'], None, t['withholding'], '', None, t['fund'], t['net'], '', '', '', '', ''])
    t = data['totals']
    rows.append(['Totale complessivo', '', '', '', t['shifts'], t['ordinary_units'], t['festive_units'], None, None, t['gross'], None,
                 t['withholding'], '', None, t['fund'], t['net'], '', '', '', '', ''])
    headers = ['Gruppo', 'Collaboratore', 'Qualifica', 'Chi fattura', 'Turni', 'Turni feriali', 'Turni festivi', 'Tariffa feriale',
               'Tariffa festiva', 'Compenso lordo', 'Ritenuta %', 'Ritenuta d’acconto', 'Cassa', 'Cassa %', 'Contributo cassa',
               'Netto da pagare', 'Modalità di pagamento', 'IBAN', 'Intestatario', 'Stato', 'Note']
    types = {4: 'number', 5: 'decimal', 6: 'decimal', 7: 'decimal', 8: 'decimal', 9: 'decimal', 10: 'decimal', 11: 'decimal',
             13: 'decimal', 14: 'decimal', 15: 'decimal'}
    notes = [['Compensi', 'Il lordo viene dall’accordo del mese confermato (turni feriali e festivi per le tariffe, quota fissa, '
                          'detrazioni e conguagli). Senza accordo confermato la cella resta vuota: non è uno zero.'],
             ['Ritenuta e cassa', 'Percentuali indicate nel fascicolo di ciascun collaboratore. Netto = lordo + contributo cassa − ritenuta.'],
             ['Riservatezza', 'Contiene coordinate bancarie: conservare con cura e consegnare solo attraverso i canali aziendali.']]
    scope = f'{data["center"]["name"]} · {month} · mese {"chiuso" if data["closed"] else "aperto"}'
    content = exports.workbook('Prospetto collaboratori', scope, [exports.sheet('Collaboratori', headers, rows, types)], notes)
    with db.write() as con:
        audit.record(con, users.reload(con, user), 'Esportazione Excel: prospetto collaboratori', center_id, entity='export',
                     entity_id='collaboratori', after=dict(month=month, people=t['people']))
    return Reply(content, content_type=exports.MIME, filename=f'collaboratori_{data["center"]["code"]}_{month}.xlsx')


# --- API ------------------------------------------------------------------------------------

@route('GET', '/api/collaborators/<cid>/<month>', cap='accordi.vedi')
def api_statement(ctx):
    return statement(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])


@route('GET', '/api/collaborators/<cid>/<month>/export.xlsx', cap='paghe.gestisci', step_up=True)
def api_export(ctx):
    with ctx.db.read() as con:
        require(users.reload(con, ctx.user), 'paghe.gestisci')
    return export_xlsx(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])
