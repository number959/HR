"""Regole di presenza. Nessuna regola economica e nessuna macro Excel eseguita."""
import calendar, math, re
from collections import Counter
from datetime import date, datetime, timedelta

WORK = {'m': 'Mattina', 'p': 'Pomeriggio', 's': 'Serale', 'n': 'Notte'}
ABSENCE = {'FE': 'Ferie', 'PS': 'Permesso', 'ROL': 'ROL', 'FG': 'FG (da definire)',
           'RC': 'Recupero turno', 'MA': 'Malattia', 'MT': 'Maternità', 'AL': 'Allattamento',
           'IN': 'Infortunio', 'PH': 'Legge 104', 'AG': 'Assenza giustificata',
           'PL': 'Permesso lutto', 'AS': 'Aspettativa non retribuita', 'R': 'Riposo'}

def month_days(month):
    first = date.fromisoformat(month + '-01')
    return [(first + timedelta(days=i)).isoformat() for i in range(calendar.monthrange(first.year, first.month)[1])]

def working_days(month, holidays=(), weekdays=(0, 1, 2, 3, 4, 5)):
    return sum(date.fromisoformat(d).weekday() in weekdays and d not in holidays for d in month_days(month))

def normalized_code(code):
    s = str(code).strip()
    if s.lower() in WORK:
        return s.lower()
    if s.upper() in ABSENCE:
        return s.upper()
    raise ValueError('Causale non riconosciuta: ' + s)

def interval(entry):
    if entry['code'] not in WORK or not entry.get('start') or not entry.get('end'):
        return None
    start = datetime.fromisoformat(entry['day'] + 'T' + entry['start'])
    end = datetime.fromisoformat(entry['day'] + 'T' + entry['end'])
    if entry.get('overnight'):
        end += timedelta(days=1)
    return start, end

def minutes(entry):
    span = interval(entry)
    return None if span is None else round((span[1] - span[0]).total_seconds() / 60) - int(entry.get('break_minutes', 0))

def validate_entry(entry, others):
    date.fromisoformat(entry['day'])
    entry['code'] = normalized_code(entry['code'])
    if entry.get('slot') not in WORK or entry.get('layer') not in ('planned', 'actual'):
        raise ValueError('Fascia o registro non valido.')
    if entry['code'] in WORK and entry['code'] != entry['slot']:
        raise ValueError('Il codice di lavoro deve coincidere con la fascia selezionata.')
    if entry['code'] in WORK and not str(entry.get('work_site', '')).strip():
        raise ValueError('Indicare la sede effettiva di lavoro.')
    start, end = entry.get('start', ''), entry.get('end', '')
    if any(t and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in (start, end)):
        raise ValueError('Gli orari devono essere nel formato HH:MM.')
    if bool(start) != bool(end):
        raise ValueError('Inserire sia ingresso sia uscita, oppure lasciare entrambi vuoti.')
    if entry['code'] not in WORK and (start or end or entry.get('break_minutes') or entry.get('overnight')):
        raise ValueError('Le causali di assenza sono registrate per fascia, senza orari in questa versione.')
    pause = entry.get('break_minutes', 0)
    if isinstance(pause, bool) or not isinstance(pause, int) or pause < 0:
        raise ValueError('La pausa deve essere un numero intero di minuti non negativo.')
    if not start and pause:
        raise ValueError('La pausa richiede ingresso e uscita.')
    span = interval(entry)
    if span:
        raw = (span[1] - span[0]).total_seconds() / 60
        if raw <= 0 or raw > 24 * 60 or pause >= raw:
            raise ValueError('Orari o pausa non validi. Per passare la mezzanotte spuntare Giorno successivo.')
    warnings = []
    if entry['code'] == 'FG': warnings.append('La causale FG compare nei contatori Excel ma non è definita in legenda.')
    if entry['code'] in WORK and not span: warnings.append('Turno contato; ore non calcolabili senza ingresso e uscita.')
    for other in others:
        if other['id'] == entry.get('id') or other['person_id'] != entry['person_id'] or other['layer'] != entry['layer']:
            continue
        if other['day'] == entry['day'] and (other['slot'] == entry['slot']):
            raise ValueError('Esiste già una registrazione in questa fascia. Aprirla per modificarla.')
        if not span: continue
        other_span = interval(other)
        if not other_span: continue
        if span[0] < other_span[1] and other_span[0] < span[1]:
            raise ValueError('Sovrapposizione con il turno del ' + other['day'] + ', anche fra sedi diverse.')
        gap = min(abs((span[0]-other_span[1]).total_seconds()), abs((other_span[0]-span[1]).total_seconds())) / 3600
        if 0 <= gap < 11:
            warnings.append('Intervallo fra turni inferiore a 11 ore: controllare. Soglia dimostrativa ripresa dalla guida Agende.')
    return list(dict.fromkeys(warnings))

def summarize(entries, people, month):
    rows = []
    for person in people:
        actual = [e for e in entries if e['person_id'] == person['id'] and e['layer'] == 'actual' and e['day'].startswith(month)]
        planned = [e for e in entries if e['person_id'] == person['id'] and e['layer'] == 'planned' and e['day'].startswith(month)]
        work = [e for e in actual if e['code'] in WORK]
        absence = [e for e in actual if e['code'] in ABSENCE and e['code'] != 'R']
        known = [minutes(e) for e in work if minutes(e) is not None]
        rows.append({**person, 'shifts': len(work), 'days_worked': len({e['day'] for e in work}),
            'external': sum(e['work_site'].casefold().strip() != person['home_site'].casefold().strip() for e in work),
            'holiday_shifts': sum(bool(e['holiday']) for e in work), 'known_minutes': sum(known),
            'missing_times': len(work)-len(known), 'absence_slots': len(absence),
            'absence_days': len({e['day'] for e in absence}),
            'causes': dict(Counter(e['code'] for e in actual if e['code'] in ABSENCE)),
            'planned_shifts': sum(e['code'] in WORK for e in planned),
            'to_confirm': sum(not any(a['day']==e['day'] and a['slot']==e['slot'] for a in actual) for e in planned)})
    return rows

def workload(patients, isolation, nurses, doctors, nurse_reference=5, doctor_reference=20):
    """Ipotesi ricostruita dalla fascia mattina del file. Non una verifica di adeguatezza clinica."""
    if any(v is None for v in (patients, isolation)):
        return {'nurse_ratio': None, 'doctor_ratio': None, 'nurse_index': None, 'doctor_index': None, 'status': 'Dati pazienti mancanti'}
    if any(v < 0 for v in (patients, isolation, nurses, doctors)) or min(nurse_reference, doctor_reference) <= 0:
        raise ValueError('Parametri non validi.')
    nratio = (patients + isolation * nurse_reference) / nurses if nurses else None
    dratio = (patients + isolation) / doctors if doctors else None
    return {'nurse_ratio': nratio, 'doctor_ratio': dratio,
            'nurse_index': nratio/nurse_reference if nratio is not None else None,
            'doctor_index': dratio/doctor_reference if dratio is not None else None,
            'status': 'Personale assente con pazienti' if patients + isolation > 0 and (not nurses or not doctors) else 'Calcolo disponibile'}

def simulate_legacy_pay(total, theoretical, festive, ccnl_festive=0, weekday_rate=50,
                        holiday_rate=70, fixed_deduction=100, ccnl_rate=70, all_shifts=False):
    """Simulazione delle celle AV:BA. Valori negativi preservati; nessuna busta paga."""
    values=(total,theoretical,festive,ccnl_festive,weekday_rate,holiday_rate,fixed_deduction,ccnl_rate)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('Inserire valori numerici finiti e non negativi.')
    if any(int(v)!=v for v in (total,theoretical,festive,ccnl_festive)):
        raise ValueError('Il modello conta turni interi: inserire conteggi interi.')
    if total == 0 and not all_shifts:
        return {'calculated': False, 'extra': None, 'ordinary': None,
                'ordinary_amount': None, 'holiday_amount': None, 'total': None,
                'reason': 'AT è zero: le formule dei dipendenti lasciano vuoti AV e il risultato finale.'}
    extra = total if all_shifts else total-theoretical
    ordinary = extra-festive
    return {'calculated': True, 'extra': extra, 'ordinary': ordinary, 'ordinary_amount': ordinary*weekday_rate,
            'holiday_amount': festive*holiday_rate,
            'total': ordinary*weekday_rate+festive*holiday_rate-fixed_deduction-ccnl_festive*ccnl_rate}
