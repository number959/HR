"""Parametri della struttura e regole del registro presenze.

I parametri sono un documento versionato: ogni salvataggio crea una nuova versione
e ogni mese conserva quella con cui è stato compilato. I permessi del compilatore
(operator_*) valgono invece sempre nella versione più recente, così una revoca ha
effetto immediato anche sui mesi aperti.
"""
import copy
from datetime import date, datetime, timedelta

from .errors import Forbidden, Invalid
from . import validate as v

ABSENCES = [('FE', 'Ferie'), ('PS', 'Permesso'), ('ROL', 'ROL'), ('FG', 'FG (da definire)'), ('RC', 'Recupero turno'),
            ('MA', 'Malattia'), ('MT', 'Maternità'), ('AL', 'Allattamento'), ('IN', 'Infortunio'), ('PH', 'Legge 104'),
            ('AG', 'Assenza giustificata'), ('PL', 'Permesso lutto'), ('AS', 'Aspettativa non retribuita')]
SLOT_DEFAULTS = [('m', 'Mattina', '07:00', '13:00', False, '#c99a2e'), ('p', 'Pomeriggio', '13:00', '19:00', False, '#d4793f'),
                 ('s', 'Serale', '19:00', '23:00', False, '#4f7fbf'), ('n', 'Notte', '21:00', '07:00', True, '#7a62b0')]
# Sede provvisoria delle registrazioni importate da Excel: va sostituita con la sede reale.
IMPORT_SITE = 'Sede esterna da specificare'
IMPORT_SITE_REVIEW = 'Indicare la sede esterna effettiva.'
OPERATOR_FLAGS = ('operator_planned', 'operator_edit_times', 'operator_choose_site', 'operator_mark_holiday',
                  'operator_delete', 'operator_export')

# Descrizione dei parametri: usata per validazione, interfaccia e riferimento impostazioni.
PARAMETERS = {
    'min_rest_hours': ('Riposo minimo tra due turni (ore)', 'number', 0, 48),
    'require_times_on_close': ('Orari obbligatori per chiudere il mese', 'bool'),
    'operator_planned': ('Il compilatore può pianificare i turni', 'bool'),
    'operator_edit_times': ('Il compilatore può modificare orari e pause', 'bool'),
    'operator_choose_site': ('Il compilatore può indicare una sede diversa', 'bool'),
    'operator_mark_holiday': ('Il compilatore può cambiare il festivo', 'bool'),
    'operator_delete': ('Il compilatore può eliminare registrazioni', 'bool'),
    'operator_export': ('Compilatore e consultazione possono scaricare il CSV', 'bool'),
    'nurse_reference': ('Pazienti di riferimento per infermiere', 'number', 0.01, 1000),
    'doctor_reference': ('Pazienti di riferimento per medico', 'number', 0.01, 1000),
    'isolation_weight': ('Peso di un paziente in isolamento', 'number', 0.01, 1000),
    'dialysis_stations': ('Posti dialisi accreditati', 'number', 0, 10000),
    'isolation_stations': ('Posti contumaciali (isolamento)', 'number', 0, 10000),
    'efficiency_threshold': ('Soglia di efficienza considerata adeguata (1 = pari al riferimento)', 'number', 0.01, 5),
    'weekday_rate': ('Tariffa feriale proposta (€ per unità)', 'number', 0, 100000),
    'holiday_rate': ('Tariffa festiva proposta (€ per unità)', 'number', 0, 100000),
    'fixed_deduction': ('Detrazione fissa proposta (€)', 'number', 0, 100000),
    'ccnl_rate': ('Valore festivo CCNL già riconosciuto (€)', 'number', 0, 100000),
    'pay_mode': ('Base proposta per gli accordi', 'choice', ('surplus', 'all')),
    'csv_separator': ('Separatore dei file CSV', 'choice', (';', ',', '\t')),
}


def defaults():
    slots = [dict(id=i, label=l, start=s, end=e, overnight=o, pause=0, color=c, active=True)
             for i, l, s, e, o, c in SLOT_DEFAULTS]
    codes = [dict(id=s['id'], label=s['label'], kind='work', credit_minutes=0, color=s['color'], active=True,
                  allowed_slots=[s['id']]) for s in slots]
    codes += [dict(id=k, label=l, kind='absence', credit_minutes=0, color='#3f8f7a', active=True, allowed_slots=[])
              for k, l in ABSENCES]
    codes.append(dict(id='R', label='Riposo', kind='rest', credit_minutes=0, color='#8a97a8', active=True, allowed_slots=[]))
    return dict(slots=slots, codes=codes, roles=['INF', 'MED', 'DS', 'OSS', 'AMM', 'ALTRO'],
                weekdays=[0, 1, 2, 3, 4, 5], holidays=[], sites=[], min_rest_hours=11, require_times_on_close=False,
                operator_planned=True, operator_edit_times=False, operator_choose_site=False,
                operator_mark_holiday=False, operator_delete=True, operator_export=True,
                nurse_roles=['INF'], doctor_roles=['MED', 'DS'], nurse_reference=5, doctor_reference=20,
                isolation_weight=5, dialysis_stations=0, isolation_stations=0, efficiency_threshold=0.92,
                weekday_rate=50, holiday_rate=70, fixed_deduction=100, ccnl_rate=70,
                pay_mode='surplus', csv_separator=';', note='')


# --- Festività nazionali -------------------------------------------------------------------

def easter(year):
    """Domenica di Pasqua (calendario gregoriano, algoritmo anonimo)."""
    a = year % 19; b, c = divmod(year, 100); d, e = divmod(b, 4)
    f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4); l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def italian_holidays(year):
    """Festività nazionali; il patrono locale va aggiunto dalla struttura."""
    fixed = [(1, 1, 'Capodanno'), (1, 6, 'Epifania'), (4, 25, 'Festa della Liberazione'), (5, 1, 'Festa dei lavoratori'),
             (6, 2, 'Festa della Repubblica'), (8, 15, 'Ferragosto'), (11, 1, 'Ognissanti'),
             (12, 8, 'Immacolata Concezione'), (12, 25, 'Natale'), (12, 26, 'Santo Stefano')]
    out = [(date(year, m, d).isoformat(), name) for m, d, name in fixed]
    out.append(((easter(year) + timedelta(days=1)).isoformat(), 'Lunedì dell’Angelo'))
    return sorted(out)


# --- Validazione dei parametri -------------------------------------------------------------

def validate_config(raw):
    base = defaults()
    v.keys(raw, set(base), 'Parametri', required=set(base))
    c = copy.deepcopy(raw)
    for key, limit, label in (('slots', 16, 'Fasce'), ('codes', 80, 'Causali')):
        rows = c[key]
        if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
            raise Invalid(f'{label}: da 1 a {limit} voci.', field=key)
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise Invalid(f'{label}: voce non valida.', field=key)
            row['id'] = v.code(row.get('id'), f'{label} · codice', field=key)
            if row['id'].casefold() in seen:
                raise Invalid(f'{label}: codice ripetuto ({row["id"]}).', field=key)
            seen.add(row['id'].casefold())
            row['label'] = v.text(row.get('label'), f'{label} · descrizione', 100, required=True, field=key)
            row['color'] = v.color(row.get('color'), f'{label} · colore', field=key)
            row['active'] = v.boolean(row.get('active'), f'{label} · attiva', field=key)
            if key == 'slots':
                v.keys(row, {'id', 'label', 'start', 'end', 'overnight', 'pause', 'color', 'active'}, 'Fascia')
                row['start'] = v.clock(row.get('start'), f'Fascia {row["id"]} · inizio', required=True, field=key)
                row['end'] = v.clock(row.get('end'), f'Fascia {row["id"]} · fine', required=True, field=key)
                row['overnight'] = v.boolean(row.get('overnight'), f'Fascia {row["id"]} · termina il giorno dopo', field=key)
                row['pause'] = v.integer(row.get('pause'), f'Fascia {row["id"]} · pausa', 0, 1439, field=key)
                minutes = span_minutes(row['start'], row['end'], row['overnight'])
                if not row['pause'] < minutes <= 1440:
                    raise Invalid(f'Fascia {row["id"]}: durata o pausa non valida (fine prima dell’inizio? '
                                  'attivare "termina il giorno dopo").', field=key)
            else:
                v.keys(row, {'id', 'label', 'kind', 'credit_minutes', 'color', 'active', 'allowed_slots'}, 'Causale')
                row['kind'] = v.choice(row.get('kind'), f'Causale {row["id"]} · tipo', ('work', 'absence', 'rest'), field=key)
                row['credit_minutes'] = v.integer(row.get('credit_minutes'), f'Causale {row["id"]} · credito minuti', 0, 1440, field=key)
                if row['kind'] != 'absence' and row['credit_minutes']:
                    raise Invalid(f'Causale {row["id"]}: il credito in minuti vale solo per le assenze.', field=key)
    slot_ids = {s['id'] for s in c['slots']}
    for row in c['codes']:
        allowed = row.get('allowed_slots')
        if not isinstance(allowed, list) or any(s not in slot_ids for s in allowed):
            raise Invalid(f'Causale {row["id"]}: fasce autorizzate non valide.', field='codes')
        row['allowed_slots'] = list(dict.fromkeys(allowed))
    if not any(s['active'] for s in c['slots']) or not any(x['active'] for x in c['codes']):
        raise Invalid('Mantenere almeno una fascia e una causale attive.', field='slots')
    c['roles'] = v.str_list(c['roles'], 'Ruoli', maximum=50, field='roles')
    if not c['roles']:
        raise Invalid('Definire almeno un ruolo.', field='roles')
    c['sites'] = v.str_list(c['sites'], 'Sedi esterne', maximum=100, item_max=150, field='sites')
    c['nurse_roles'] = v.str_list(c['nurse_roles'], 'Ruoli infermieristici', maximum=50, allowed=c['roles'], field='nurse_roles')
    c['doctor_roles'] = v.str_list(c['doctor_roles'], 'Ruoli medici', maximum=50, allowed=c['roles'], field='doctor_roles')
    if set(c['nurse_roles']) & set(c['doctor_roles']):
        raise Invalid('Un ruolo non può essere sia infermieristico sia medico nel calcolo del carico.', field='nurse_roles')
    days = c['weekdays']
    if not isinstance(days, list) or not days or any(type(d) is not int or d not in range(7) for d in days):
        raise Invalid('Giorni lavorativi: scegliere almeno un giorno della settimana.', field='weekdays')
    c['weekdays'] = sorted(set(days))
    holidays = c['holidays']
    if not isinstance(holidays, list) or len(holidays) > 2000:
        raise Invalid('Festività: elenco non valido.', field='holidays')
    c['holidays'] = sorted({v.day(d, 'Festività', field='holidays') for d in holidays})
    for key, spec in PARAMETERS.items():
        label, kind = spec[0], spec[1]
        if kind == 'bool':
            c[key] = v.boolean(c[key], label, field=key)
        elif kind == 'number':
            c[key] = v.number(c[key], label, spec[2], spec[3], field=key)
        else:
            c[key] = v.choice(c[key], label, spec[2], field=key)
    c['note'] = v.text(c['note'], 'Note sui parametri', 4000, multiline=True, field='note')
    return c


def effective(month_config, current_config):
    """Parametri del mese con i permessi del compilatore sempre aggiornati."""
    out = dict(month_config)
    out.update({k: current_config[k] for k in OPERATOR_FLAGS})
    return out


# --- Orari e durate -------------------------------------------------------------------------

def span_minutes(start, end, overnight):
    a = datetime.fromisoformat('2000-01-01T' + start)
    b = datetime.fromisoformat('2000-01-01T' + end) + timedelta(days=int(bool(overnight)))
    return int((b - a).total_seconds() // 60)


def span(entry):
    """Intervallo effettivo di un turno di lavoro con orari, altrimenti None."""
    if entry['kind'] != 'work' or not entry['start'] or not entry['end']:
        return None
    a = datetime.fromisoformat(entry['day'] + 'T' + entry['start'])
    b = datetime.fromisoformat(entry['day'] + 'T' + entry['end']) + timedelta(days=int(bool(entry['overnight'])))
    return a, b


def duration(entry):
    """Minuti lavorati (orario di parete, pausa esclusa) oppure None se mancano gli orari."""
    s = span(entry)
    return None if s is None else int((s[1] - s[0]).total_seconds() // 60) - int(entry['pause'] or 0)


def slot_span(day, slot):
    a = datetime.fromisoformat(day + 'T' + slot['start'])
    b = datetime.fromisoformat(day + 'T' + slot['end']) + timedelta(days=int(bool(slot['overnight'])))
    return a, b


# --- Costruzione e verifica di una registrazione -----------------------------------------------

def build_entry(raw, *, config, person, month, can, old=None):
    """Verifica i dati inviati e restituisce la registrazione normalizzata.

    can: funzione che dato un permesso ('presenze.orari', ...) restituisce True/False
    per l'utente su questo centro. old: registrazione esistente (in modifica).
    """
    day = v.day(raw.get('day'), 'Data', field='day')
    if not day.startswith(month + '-'):
        raise Invalid('Data fuori dal mese selezionato.', field='day')
    layer = v.choice(raw.get('layer'), 'Registro', ('actual', 'planned'), field='layer')
    if layer == 'planned' and not can('presenze.pianifica'):
        raise Forbidden('Pianificazione riservata al responsabile del centro e all’amministratore.')
    slot = next((s for s in config['slots'] if s['id'] == raw.get('slot') and s['active']), None)
    code = next((c for c in config['codes'] if c['id'] == raw.get('code') and c['active']), None)
    if not slot:
        raise Invalid('Fascia non disponibile nei parametri del mese.', field='slot')
    if not code:
        raise Invalid('Causale non disponibile nei parametri del mese.', field='code')
    if code['allowed_slots'] and slot['id'] not in code['allowed_slots']:
        raise Invalid(f'La causale {code["id"]} non è prevista nella fascia {slot["label"]}.', field='code')
    if old and any(raw.get(k, old[k]) != old[k] for k in ('day', 'slot', 'layer')):
        raise Invalid('Per spostare una registrazione eliminarla e inserirla di nuovo.', field='day')
    entry = dict(person_id=person['id'], day=day, slot=slot['id'], layer=layer, code=code['id'], kind=code['kind'],
                 label=code['label'], start='', end='', pause=0, overnight=False,
                 credit=code['credit_minutes'] if code['kind'] == 'absence' else 0,
                 note=v.text(raw.get('note', ''), 'Nota', 2000, multiline=True, field='note'))
    if code['kind'] == 'work':
        expected = ({k: old[k] for k in ('start', 'end', 'pause', 'overnight')} if old and old['kind'] == 'work'
                    else {k: slot[k] for k in ('start', 'end', 'pause', 'overnight')})
        expected['overnight'] = bool(expected['overnight'])
        if can('presenze.orari'):
            times = {k: raw.get(k, expected[k]) for k in expected}
        else:
            if any(k in raw and raw[k] != expected[k] for k in expected):
                raise Forbidden('Orari e pause sono bloccati dai parametri del centro: chiedi al responsabile.')
            times = expected
        start = v.clock(times['start'], 'Ingresso', field='start')
        end = v.clock(times['end'], 'Uscita', field='end')
        overnight = v.boolean(times['overnight'], 'Uscita il giorno dopo', field='overnight')
        pause = v.integer(times['pause'], 'Pausa', 0, 1439, field='pause')
        if bool(start) != bool(end):
            raise Invalid('Indicare sia ingresso sia uscita, oppure lasciarli entrambi vuoti.', field='start')
        if pause and not start:
            raise Invalid('La pausa richiede ingresso e uscita.', field='pause')
        if start:
            minutes = span_minutes(start, end, overnight)
            if not 0 < minutes <= 1440 or pause >= minutes:
                raise Invalid('Orari o pausa non validi. Per un turno oltre la mezzanotte attivare "uscita il giorno dopo".',
                              field='end')
        entry.update(start=start, end=end, pause=pause, overnight=overnight)
    sites = config['sites']
    site = raw.get('site', old['site'] if old else '')
    site = '' if site in (None, '') else v.text(site, 'Sede', 150, field='site')
    default_site = old['site'] if old else ''
    if site != default_site and not can('presenze.sede'):
        raise Forbidden('La sede di lavoro è bloccata dai parametri del centro: chiedi al responsabile.')
    if site and site not in sites:
        raise Invalid('Sede non presente tra quelle autorizzate nei parametri.', field='site')
    entry['site'] = site
    default_holiday = bool(old['holiday']) if old else day in config['holidays']
    holiday = raw.get('holiday', default_holiday)
    holiday = v.boolean(holiday, 'Festivo', field='holiday')
    if holiday != default_holiday and not can('presenze.festivo'):
        raise Forbidden('La classificazione festiva è bloccata dai parametri del centro: chiedi al responsabile.')
    entry['holiday'] = holiday
    return entry


def check_conflicts(entry, others, min_rest_hours):
    """others: registrazioni della stessa persona (anche nelle strutture collegate),
    ciascuna con 'center_name'. Errore per fascia doppia o sovrapposizione,
    avviso se il riposo tra due turni è inferiore al minimo."""
    warnings = []
    mine = span(entry)
    for other in others:
        if other.get('id') == entry.get('id') or other['layer'] != entry['layer']:
            continue
        where = f' ({other["center_name"]})' if other.get('center_name') else ''
        if other['day'] == entry['day'] and other['slot'] == entry['slot']:
            raise Invalid(f'La fascia è già compilata{where}: aprirla per modificarla.', field='slot')
        theirs = span(other)
        if mine and theirs:
            if mine[0] < theirs[1] and theirs[0] < mine[1]:
                raise Invalid(f'Sovrapposizione con il turno del {_it(other["day"])}{where}.', field='start')
            gap = min(abs((mine[0] - theirs[1]).total_seconds()), abs((theirs[0] - mine[1]).total_seconds())) / 3600
            if gap < min_rest_hours:
                warnings.append(f'Riposo inferiore a {_hours(min_rest_hours)} ore rispetto al turno del {_it(other["day"])}{where}.')
    return list(dict.fromkeys(warnings))


def _it(day):
    return f'{day[8:10]}/{day[5:7]}/{day[:4]}'


def _hours(value):
    return str(int(value)) if float(value).is_integer() else str(value).replace('.', ',')


# --- Riepilogo del mese -------------------------------------------------------------------------

def summarize(people, entries, until=None):
    """Totali per persona del mese (entries: solo il mese richiesto).

    Con until (data ISO) le fasce pianificate contano come «da consuntivare» solo per i giorni precedenti:
    un turno previsto per oggi o per i prossimi giorni non è ancora un ritardo."""
    by_person = {p['id']: [] for p in people}
    for e in entries:
        by_person.setdefault(e['person_id'], []).append(e)
    rows = []
    for p in people:
        mine = by_person.get(p['id'], [])
        actual = [e for e in mine if e['layer'] == 'actual']
        work = [e for e in actual if e['kind'] == 'work']
        known = [duration(e) for e in work if duration(e) is not None]
        absence = [e for e in actual if e['kind'] == 'absence']
        actual_keys = {(e['day'], e['slot']) for e in actual}
        planned = [e for e in mine if e['layer'] == 'planned']
        causes = {}
        for e in actual:
            causes[e['code']] = causes.get(e['code'], 0) + 1
        rows.append(dict(person_id=p['id'], name=p['name'], role=p['role'], registration=p.get('registration', ''),
                         active=p.get('active', True), shifts=len(work), days=len({e['day'] for e in work}),
                         minutes=sum(known), missing=len(work) - len(known), external=sum(bool(e['site']) for e in work),
                         festive=sum(bool(e['holiday']) for e in work), absences=len(absence),
                         credit=sum(e['credit'] for e in absence),
                         pending=sum((e['day'], e['slot']) not in actual_keys and (until is None or e['day'] < until)
                                     for e in planned),
                         planned=len(planned), causes=dict(sorted(causes.items()))))
    return rows


def working_days(month_days, config):
    return sum(date.fromisoformat(d).weekday() in config['weekdays'] and d not in config['holidays'] for d in month_days)
