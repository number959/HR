"""Tracciato paghe: modello versionato, controlli e file per il consulente del lavoro.

Una riga corrisponde a una fascia a consuntivo. Le quantità non sono una busta
paga e non si presume alcuna compatibilità con un gestionale: finché il
consulente non ha verificato le specifiche il modello resta in bozza e il
download è bloccato. Il file si scarica solo se coincide con l'anteprima controllata.
"""
import copy
import csv
import hashlib
import hmac
import io
import json
import math
import re
from collections import defaultdict
from datetime import datetime

from . import approvals, audit, centers, months, rules, users, workforce
from .errors import Conflict, Invalid
from .util import csv_safe, dumps, loads, month_days, month_range, stamp
from . import validate as v
from .web import Reply

MIME_CSV = 'text/csv; charset=utf-8'
MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_ROWS = 100_000
PREVIEW_ROWS = 100
SPEC_SCHEMA = 'nefrocenter.payroll-spec.v1'
SPEC_MAX_BYTES = 32768
FIELDS = {
    'template_version': ('Versione modello', 'integer'), 'center_code': ('Codice struttura', 'text'),
    'registration': ('Matricola paghe', 'text'), 'person_name': ('Dipendente', 'text'),
    'global_id': ('Identificativo persona di gruppo', 'text'), 'day': ('Data', 'date'), 'slot': ('Fascia', 'text'),
    'payroll_code': ('Causale paghe', 'text'), 'source_code': ('Causale registro', 'text'),
    'kind': ('Tipo registrazione', 'text'), 'start': ('Ingresso', 'text'), 'end': ('Uscita', 'text'),
    'overnight': ('Giorno successivo', 'integer'), 'pause_minutes': ('Pausa minuti', 'integer'),
    'worked_minutes': ('Minuti lavorati', 'integer'), 'worked_hours': ('Ore lavorate decimali', 'decimal'),
    'work_shifts': ('Turni lavorati', 'integer'), 'absence_slots': ('Fasce assenza', 'integer'),
    'absence_days': ('Giorni assenza per causale', 'integer'), 'credited_minutes': ('Credito assenza minuti', 'integer'),
    'holiday': ('Festivo', 'integer'), 'work_site': ('Sede effettiva', 'text'), 'role': ('Ruolo alla data', 'text'),
    'weekly_hours': ('Ore contrattuali settimanali alla data', 'decimal'),
    'part_time_percent': ('Part-time percentuale alla data', 'decimal'), 'contract_type': ('Contratto alla data', 'text'),
    'ccnl': ('CCNL alla data', 'text'), 'level': ('Livello alla data', 'text'),
    'source_id': ('Identificativo registrazione', 'text'),
}
REQUIRED_FIELDS = {'template_version', 'center_code', 'registration', 'day', 'payroll_code'}
CONSULTANT_REQUIRED = {'registration', 'day', 'payroll_code'}
DEFAULT_FIELDS = ['template_version', 'center_code', 'registration', 'person_name', 'day', 'slot', 'payroll_code',
                  'worked_minutes', 'worked_hours', 'work_shifts', 'absence_slots', 'absence_days', 'credited_minutes',
                  'source_id']
UNKNOWN_PROVIDER = {'unknown', 'non so', 'non definito', 'da definire', 'sconosciuto'}


def default_connector():
    return dict(mode='generic', provider='', format_name='', format_version='', specification_reference='',
                expected_columns=[], date_format='YYYY-MM-DD', encoding='utf-8-sig')


def default_template(cfg):
    return dict(name='Tracciato generico da concordare', status='draft', confirmation_note='', delimiter=';',
                decimal_separator=',', columns=[dict(field=k, label=FIELDS[k][0]) for k in DEFAULT_FIELDS],
                causes={c['id']: '' for c in cfg['codes']}, registrations={}, connector=default_connector())


def current(con, center_id):
    found = con.execute('SELECT * FROM payroll_templates WHERE center_id=? ORDER BY version DESC LIMIT 1', (center_id,)).fetchone()
    if found:
        data = loads(found['data'])
        data.setdefault('connector', default_connector())
        return dict(version=found['version'], config=data, created_at=found['created_at'], created_by=found['created_by'])
    return dict(version=0, config=default_template(centers.config(con, center_id)), created_at='', created_by='')


def _header(value):
    value = v.text(value, 'Intestazione', 120, required=True, field='columns')
    if value.startswith(('=', '+', '-', '@')):
        raise Invalid('Intestazione non valida: non usare formule o prefissi di formula.', field='columns')
    return value


def validate_connector(raw):
    base = default_connector()
    if not isinstance(raw, dict) or set(raw) != set(base):
        raise Invalid('Profilo del consulente incompleto o con campi non previsti.', field='connector')
    out = copy.deepcopy(raw)
    out['mode'] = v.choice(out['mode'], 'Collegamento', ('generic', 'consultant'), field='connector')
    for key, limit in (('provider', 120), ('format_name', 120), ('format_version', 80), ('specification_reference', 500)):
        out[key] = v.text(out[key], key, limit, field='connector')
    out['date_format'] = v.choice(out['date_format'], 'Formato data', ('YYYY-MM-DD', 'DD/MM/YYYY'), field='connector')
    out['encoding'] = v.choice(out['encoding'], 'Codifica', ('utf-8-sig', 'utf-8', 'cp1252'), field='connector')
    cols = out['expected_columns']
    if not isinstance(cols, list) or len(cols) > len(FIELDS):
        raise Invalid('Elenco delle intestazioni del consulente non valido.', field='connector')
    seen = set()
    for col in cols:
        if not isinstance(col, dict) or set(col) != {'header', 'required', 'type', 'max_length'}:
            raise Invalid('Regola di colonna non valida.', field='connector')
        col['header'] = _header(col['header'])
        if col['header'].casefold() in seen:
            raise Invalid('Le intestazioni del consulente non possono ripetersi.', field='connector')
        seen.add(col['header'].casefold())
        v.boolean(col['required'], 'Obbligatoria', field='connector')
        v.choice(col['type'], 'Tipo', ('text', 'integer', 'decimal', 'date'), field='connector')
        if col['max_length'] is not None:
            v.integer(col['max_length'], 'Lunghezza massima', 1, 2000, field='connector')
    return out


def connector_issues(cfg):
    c = cfg['connector']
    if c['mode'] == 'generic':
        return []
    issues = []
    if not c['provider'] or c['provider'].casefold() in UNKNOWN_PROVIDER:
        issues.append(('consultant_unknown', 'Indicare il gestionale del consulente: non è ancora definito.'))
    for key, label in (('format_name', 'il nome del tracciato'), ('format_version', 'la versione delle specifiche'),
                       ('specification_reference', 'il riferimento alle specifiche ricevute')):
        if not c[key]:
            issues.append(('consultant_metadata', f'Completare {label} del consulente.'))
    expected = c['expected_columns']
    if len(expected) < 3:
        issues.append(('consultant_headers', 'Caricare o definire almeno tre intestazioni del consulente.'))
    if [x['header'] for x in expected] != [x['label'] for x in cfg['columns']]:
        issues.append(('consultant_headers', 'Intestazioni e ordine non corrispondono alle specifiche del consulente.'))
    mapped = {x['field'] for x in cfg['columns'] if x['field']}
    if any(not x['field'] for x in cfg['columns']):
        issues.append(('consultant_mapping', 'Associare ogni intestazione del consulente a un dato del registro.'))
    if not CONSULTANT_REQUIRED <= mapped:
        issues.append(('consultant_identity', 'Il tracciato deve identificare matricola, data e causale paghe.'))
    for col, exp in zip(cfg['columns'], expected):
        if not col['field']:
            continue
        source, target = FIELDS[col['field']][1], exp['type']
        if target != 'text' and source != target and not (source == 'integer' and target == 'decimal'):
            issues.append(('consultant_type', f'La colonna {exp["header"]} richiede un dato di tipo {target}.'))
    try:
        for exp in expected:
            exp['header'].encode(c['encoding'])
    except UnicodeEncodeError:
        issues.append(('consultant_encoding', 'Le intestazioni contengono caratteri non rappresentabili nella codifica scelta.'))
    if cfg['status'] != 'confirmed':
        issues.append(('consultant_unconfirmed', 'Collegamento al consulente da concordare: verificare mappatura e formato '
                                                 'prima di confermare.'))
    return issues


def validate_template(raw, person_ids):
    expected = {'name', 'status', 'confirmation_note', 'delimiter', 'decimal_separator', 'columns', 'causes', 'registrations'}
    if not isinstance(raw, dict) or set(raw) - (expected | {'connector'}) or not expected <= set(raw):
        raise Invalid('Modello paghe incompleto o con campi non previsti.')
    cfg = copy.deepcopy(raw)
    cfg['connector'] = validate_connector(cfg.get('connector', default_connector()))
    consultant = cfg['connector']['mode'] == 'consultant'
    cfg['name'] = v.text(cfg['name'], 'Nome del modello', 120, required=True, field='name')
    cfg['confirmation_note'] = v.text(cfg['confirmation_note'], 'Verifica del consulente', 1000, multiline=True,
                                      field='confirmation_note')
    cfg['status'] = v.choice(cfg['status'], 'Stato', ('draft', 'confirmed'), field='status')
    if cfg['status'] == 'confirmed' and len(cfg['confirmation_note']) < 8:
        raise Invalid('Indicare il riferimento alla verifica con il consulente (almeno 8 caratteri).', field='confirmation_note')
    cfg['delimiter'] = v.choice(cfg['delimiter'], 'Separatore', (';', ',', '\t'), field='delimiter')
    cfg['decimal_separator'] = v.choice(cfg['decimal_separator'], 'Separatore decimale', ('.', ','), field='decimal_separator')
    minimum = 3 if consultant else 5
    if not isinstance(cfg['columns'], list) or not minimum <= len(cfg['columns']) <= len(FIELDS):
        raise Invalid(f'Scegliere da {minimum} a {len(FIELDS)} colonne.', field='columns')
    fields, labels = set(), set()
    for col in cfg['columns']:
        if (not isinstance(col, dict) or set(col) != {'field', 'label'} or not isinstance(col['field'], str)
                or (col['field'] not in FIELDS and not (consultant and col['field'] == ''))):
            raise Invalid('Colonna non riconosciuta.', field='columns')
        col['label'] = _header(col['label']) if consultant else v.text(col['label'], 'Intestazione', 120, required=True,
                                                                         field='columns')
        if (col['field'] and col['field'] in fields) or col['label'].casefold() in labels:
            raise Invalid('Colonne e intestazioni non possono ripetersi.', field='columns')
        fields.add(col['field'])
        labels.add(col['label'].casefold())
    if not consultant and not REQUIRED_FIELDS <= fields:
        raise Invalid('Mantenere versione del modello, codice struttura, matricola, data e causale paghe.', field='columns')
    if consultant and cfg['status'] == 'confirmed':
        problems = connector_issues(cfg)
        if problems:
            raise Invalid(problems[0][1], field='connector')
    for key, limit in (('causes', 500), ('registrations', 20000)):
        mapping = cfg[key]
        if not isinstance(mapping, dict) or len(mapping) > limit:
            raise Invalid('Mappatura non valida.', field=key)
        for source, target in mapping.items():
            v.text(source, 'Identificativo di origine', 100, required=True, field=key)
            mapping[source] = v.text(target, 'Codice di destinazione', 100, field=key)
    if set(cfg['registrations']) - set(person_ids):
        raise Invalid('Mappatura delle matricole riferita a persone di un’altra struttura.', field='registrations')
    return cfg


def read(db, user, center_id):
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'paghe.gestisci')
        cur = current(con, center_id)
        persons = months.people(con, center_id)
        cfg = centers.config(con, center_id)
        causes = {c['id']: dict(id=c['id'], label=c['label'], kind=c['kind']) for c in cfg['codes']}
        for r in con.execute('SELECT DISTINCT code, label, kind FROM entries WHERE center_id=?', (center_id,)):
            causes.setdefault(r['code'], dict(id=r['code'], label=r['label'], kind=r['kind']))
        history = []
        for r in con.execute('SELECT * FROM payroll_templates WHERE center_id=? ORDER BY version DESC LIMIT 30', (center_id,)):
            data = loads(r['data'])
            history.append(dict(version=r['version'], created_at=r['created_at'], created_by=r['created_by'], name=data['name'],
                                status=data['status']))
    return dict(cur, center=dict(id=center['id'], name=center['name'], code=center['code']), history=history,
                fields=[dict(id=k, label=f[0], type=f[1], required=k in REQUIRED_FIELDS) for k, f in FIELDS.items()],
                people=[dict(id=p['id'], name=p['name'], registration=p['registration']) for p in persons],
                causes=list(causes.values()))


def save(db, actor, center_id, raw):
    v.keys(raw, {'config', 'version', 'confirm_connector'}, 'Modello paghe', required={'config', 'version'})
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'paghe.gestisci')
        cur = current(con, center_id)
        if v.version(raw['version']) != cur['version']:
            raise Conflict('Il modello è cambiato: ricaricare prima di salvare.')
        cfg = validate_template(raw['config'], [p['id'] for p in months.people(con, center_id)])
        if cfg['connector']['mode'] == 'consultant' and cfg['status'] == 'confirmed' and raw.get('confirm_connector') is not True:
            raise Invalid('Confermare esplicitamente la verifica di questa versione del tracciato con il consulente.',
                          field='confirm_connector')
        version = cur['version'] + 1
        con.execute('INSERT INTO payroll_templates(center_id,version,data,created_at,created_by) VALUES(?,?,?,?,?)',
                    (center_id, version, dumps(cfg), stamp(), actor.username))
        audit.record(con, actor, 'Modello paghe salvato', center_id, entity='payroll', entity_id=str(version),
                     before=dict(version=cur['version']), after=dict(version=version, name=cfg['name'], status=cfg['status']))
    return dict(version=version, status=cfg['status'])


# --- costruzione del tracciato ---------------------------------------------------------------

def _formatted(value, field, cfg):
    if value is None:
        return ''
    kind = FIELDS.get(field, ('', 'text'))[1]
    if kind == 'date' and cfg['connector']['date_format'] == 'DD/MM/YYYY':
        return datetime.fromisoformat(str(value)).strftime('%d/%m/%Y')
    if kind == 'decimal' and isinstance(value, (int, float)):
        return format(value, '.6f').rstrip('0').rstrip('.').replace('.', cfg['decimal_separator'])
    return str(value)


def _value_issue(value, field, expected, cfg):
    if value is None or value == '':
        return 'dato obbligatorio mancante.' if expected['required'] else ''
    if expected['type'] == 'integer' and (isinstance(value, bool) or not re.fullmatch(r'[+-]?\d+', str(value))):
        return 'il consulente richiede un numero intero.'
    if expected['type'] == 'decimal':
        try:
            if not math.isfinite(float(value)):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            return 'il consulente richiede un numero decimale.'
    if expected['type'] == 'date':
        try:
            datetime.strptime(str(value), '%Y-%m-%d')
        except (ValueError, TypeError):
            return 'il consulente richiede una data.'
    text = _formatted(value, field, cfg)
    if expected['max_length'] is not None and len(text) > expected['max_length']:
        return f'supera la lunghezza massima di {expected["max_length"]} caratteri.'
    if isinstance(value, str) and csv_safe(value) != value:
        return 'prefisso di formula non ammesso nel tracciato del consulente: correggere il dato.'
    try:
        text.encode(cfg['connector']['encoding'])
    except UnicodeEncodeError:
        return 'contiene caratteri non rappresentabili nella codifica scelta.'
    return ''


def build(con, user, center_id, first, last):
    v.month(first, 'Dal mese')
    v.month(last, 'Al mese')
    if last < first:
        raise Invalid('Il mese finale precede quello iniziale.')
    periods = month_range(first, last)
    if len(periods) > 24:
        raise Invalid('Selezionare al massimo 24 mesi.')
    user, center = centers.scoped(con, user, center_id, 'paghe.gestisci')
    cur = current(con, center_id)
    cfg = cur['config']
    persons = {p['id']: p for p in months.people(con, center_id)}
    rows_db = con.execute('SELECT * FROM entries WHERE center_id=? AND day BETWEEN ? AND ? ORDER BY day, id LIMIT ?',
                          (center_id, first + '-01', month_days(last)[-1], MAX_ROWS + 1)).fetchall()
    if len(rows_db) > MAX_ROWS:
        raise Invalid('Oltre 100.000 registrazioni: ridurre il periodo.')
    entries = [months.entry_dict(r) for r in rows_db]
    actual = sorted((e for e in entries if e['layer'] == 'actual'),
                    key=lambda e: (e['day'], persons.get(e['person_id'], {}).get('name', ''), e['slot'], e['id']))
    issues = []

    def issue(code, message, entry=None, severity='error'):
        item = dict(code=code, message=message, severity=severity)
        if entry:
            item.update(day=entry['day'], person_id=entry['person_id'], entry_id=entry['id'])
        issues.append(item)

    if cur['version'] == 0 or cfg['status'] != 'confirmed':
        issue('unconfirmed_template', 'Confermare il modello dopo la verifica delle specifiche con il consulente.')
    for code, message in connector_issues(cfg):
        issue(code, message)
    if not actual:
        issue('empty', 'Nessuna registrazione a consuntivo nel periodo selezionato.')
    for m in periods:
        try:
            approvals.require_approved(con, center_id, m)
        except Invalid as exc:
            issue('approval_required', f'{m}: {exc.message}')
    still_open = [m for m in periods if not months.get(con, center_id, m)['closed']]
    if still_open:
        issue('open_months', 'Mesi ancora aperti: ' + ', '.join(still_open) + '. I dati possono cambiare.', severity='warning')
    seen, timed, owners, absence_seen = set(), defaultdict(list), {}, set()
    rows, minutes_known, missing_hours, pending, no_contract = [], [], 0, 0, set()
    selected = {c['field'] for c in cfg['columns']}
    for e in actual:
        p = persons.get(e['person_id'])
        if not p:
            issue('orphan', 'Registrazione senza anagrafica: ripristinare il collegamento.', e)
            continue
        contract = workforce.contract_on(con, p['id'], e['day'])
        key = (p['id'], e['day'], e['slot'])
        if key in seen:
            issue('duplicate', 'La stessa persona ha più consuntivi nella stessa fascia.', e)
        seen.add(key)
        registration = cfg['registrations'].get(p['id'], '') or p['registration']
        if not registration:
            issue('missing_registration', f'{p["name"]}: matricola paghe mancante.', e)
        elif owners.setdefault(registration, p['id']) != p['id']:
            issue('duplicate_registration', f'La matricola paghe {registration} è attribuita a più persone della struttura.', e)
        mapped = cfg['causes'].get(e['code'], '')
        if not mapped:
            issue('unmapped_cause', f'Manca il codice paghe per la causale {e["code"]}.', e)
        minutes = rules.duration(e) if e['kind'] == 'work' else None
        if e['kind'] == 'work':
            if minutes is None:
                missing_hours += 1
                issue('missing_hours', f'{p["name"]}: completare ingresso e uscita.', e)
            elif minutes < 0:
                issue('invalid_hours', 'Durata negativa: correggere orari o pausa.', e)
            else:
                minutes_known.append(minutes)
            interval = rules.span(e)
            if interval:
                timed[p['id']].append((interval[0], interval[1], e))
        absence_key = (p['id'], e['day'], mapped or e['code'])
        absence_day = int(e['kind'] == 'absence' and absence_key not in absence_seen)
        if e['kind'] == 'absence':
            absence_seen.add(absence_key)
        if not contract:
            no_contract.add(p['id'])
        record = dict(template_version=cur['version'], center_code=center['code'], registration=registration,
                      person_name=p['name'], global_id=p['identity_id'], day=e['day'], slot=e['slot'], payroll_code=mapped,
                      source_code=e['code'], kind=e['kind'], start=e['start'], end=e['end'], overnight=int(e['overnight']),
                      pause_minutes=e['pause'] if e['kind'] == 'work' else None, worked_minutes=minutes,
                      worked_hours=round(minutes / 60, 6) if minutes is not None else None,
                      work_shifts=int(e['kind'] == 'work'), absence_slots=int(e['kind'] == 'absence'), absence_days=absence_day,
                      credited_minutes=e['credit'] if e['kind'] == 'absence' else None, holiday=int(e['holiday']),
                      work_site=e['site'] or center['name'], role=contract['role'] if contract else p['role'],
                      source_id=e['id'])
        for field in ('weekly_hours', 'part_time_percent', 'contract_type', 'ccnl', 'level'):
            value = contract.get(field) if contract else None
            record[field] = None if value == '' else value
        if any(record[f] is None for f in selected & {'weekly_hours', 'part_time_percent'}):
            issue('missing_contract_value', f'{p["name"]}: dato contrattuale richiesto dal modello non disponibile alla data.', e)
        values = [record.get(c['field']) for c in cfg['columns']]
        if cfg['connector']['mode'] == 'consultant':
            for col, exp, value in zip(cfg['columns'], cfg['connector']['expected_columns'], values):
                problem = _value_issue(value, col['field'], exp, cfg)
                if problem:
                    issue('consultant_value', f'{p["name"]} · {exp["header"]}: {problem}', e)
        rows.append(values)
    for intervals in timed.values():
        intervals.sort(key=lambda x: (x[0], x[1]))
        latest = None
        for start, end, e in intervals:
            if latest is not None and start < latest:
                issue('overlap', 'Sovrapposizione fra orari della stessa persona nella struttura.', e)
            latest = end if latest is None else max(latest, end)
    for e in entries:
        if e['layer'] == 'planned' and e['kind'] == 'work' and (e['person_id'], e['day'], e['slot']) not in seen:
            pending += 1
            issue('pending_actual', 'Fascia pianificata senza consuntivo.', e)
    if no_contract:
        issue('no_contract_history', f'{len(no_contract)} persone senza contratto registrato alla data: il ruolo usa la scheda '
                                     'attuale; ore e percentuali contrattuali restano vuote.', severity='warning')
    blockers = sum(i['severity'] == 'error' for i in issues)
    summary = dict(rows=len(rows), people=len({e['person_id'] for e in actual if e['person_id'] in persons}),
                   work_shifts=sum(e['kind'] == 'work' for e in actual), absence_slots=sum(e['kind'] == 'absence' for e in actual),
                   absence_days=len({(e['person_id'], e['day']) for e in actual if e['kind'] == 'absence'}),
                   known_minutes=sum(minutes_known) if minutes_known else (0 if actual and not any(e['kind'] == 'work' for e in actual) else None),
                   missing_hours=missing_hours, pending_actual=pending, blocking_issues=blockers, warnings=len(issues) - blockers)
    payload = dict(center_id=center_id, first=first, last=last, version=cur['version'], config=cfg, rows=rows, issues=issues,
                   summary=summary)
    fingerprint = hashlib.sha256(dumps(payload).encode()).hexdigest()
    consultant = cfg['connector']['mode'] == 'consultant'
    return dict(center=center['name'], center_code=center['code'], center_id=center_id, first=first, last=last,
                version=cur['version'], template_name=cfg['name'], status=cfg['status'], connector=copy.deepcopy(cfg['connector']),
                output_format=dict(delimiter=cfg['delimiter'], decimal_separator=cfg['decimal_separator'],
                                   date_format=cfg['connector']['date_format'], encoding=cfg['connector']['encoding']),
                connector_status=(('verified' if cfg['status'] == 'confirmed' and not connector_issues(cfg) else 'draft')
                                  if consultant else 'generic'),
                columns=[dict(field=c['field'], label=c['label'], type=FIELDS.get(c['field'], ('', 'text'))[1]) for c in cfg['columns']],
                rows=rows, summary=summary, issues=issues, can_download=blockers == 0, fingerprint=fingerprint, config=cfg)


def preview(db, user, center_id, first, last):
    with db.read() as con:
        data = build(con, user, center_id, first, last)
    data.pop('config')
    data['shown_rows'] = min(len(data['rows']), PREVIEW_ROWS)
    data['rows'] = data['rows'][:PREVIEW_ROWS]
    data['shown_issues'] = min(len(data['issues']), 200)
    data['issues'] = data['issues'][:200]
    return data


def _csv(data):
    out = io.StringIO(newline='')
    writer = csv.writer(out, delimiter=data['config']['delimiter'])
    writer.writerow([csv_safe(c['label']) for c in data['columns']])
    for row in data['rows']:
        writer.writerow([csv_safe(_formatted(value, col['field'], data['config'])) for value, col in zip(row, data['columns'])])
    return out.getvalue().encode(data['config']['connector']['encoding'])


def _xlsx(data):
    import xlsxwriter
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': 'Tracciato paghe · ' + data['template_name'], 'author': 'NefroCenter WR',
                       'comments': f'Versione {data["version"]}; SHA256 dati {data["fingerprint"]}'})
    header = wb.add_format({'bold': True, 'bg_color': '#0b2440', 'font_color': '#ffffff'})
    date_format = wb.add_format({'num_format': 'dd/mm/yyyy' if data['config']['connector']['date_format'] == 'DD/MM/YYYY'
                                 else 'yyyy-mm-dd'})
    decimal_format = wb.add_format({'num_format': '0.000000'})
    ws = wb.add_worksheet('Paghe')
    for col, spec in enumerate(data['columns']):
        ws.write_string(0, col, spec['label'], header)
        ws.set_column(col, col, min(42, max(15, len(spec['label']))))
    for r, row in enumerate(data['rows'], 1):
        for col, (value, spec) in enumerate(zip(row, data['columns'])):
            if value is None or value == '':
                ws.write_blank(r, col, None)
            elif spec['type'] == 'date':
                ws.write_datetime(r, col, datetime.fromisoformat(value), date_format)
            elif spec['type'] in ('integer', 'decimal'):
                ws.write_number(r, col, float(value), decimal_format if spec['type'] == 'decimal' else None)
            else:
                ws.write_string(r, col, str(value))
    ws.freeze_panes(1, 3)
    ws.autofilter(0, 0, len(data['rows']), len(data['columns']) - 1)
    info = wb.add_worksheet('Informazioni')
    info.set_column(0, 0, 28)
    info.set_column(1, 1, 100)
    consultant = data['config']['connector']['mode'] == 'consultant'
    notes = [('Modello', data['template_name']), ('Versione', str(data['version'])), ('Struttura', data['center']),
             ('Periodo', f'{data["first"]} / {data["last"]}'), ('SHA256 dati', data['fingerprint']), ('Creato il', stamp()),
             ('Verifica consulente', data['config']['confirmation_note']),
             ('Grana', 'Una riga per fascia a consuntivo; turni pianificati esclusi.'),
             ('Giorni di assenza', '1 alla prima fascia della persona/data/causale paghe; non sommare causali diverse per '
                                   'ottenere giornate totali.'),
             ('Ore e crediti', 'Ore lavorate e crediti di assenza separati; vuoto significa non disponibile, 0 è un valore '
                               'registrato.'),
             ('Tracciato', ('Specifiche configurate per il consulente; nessun invio automatico. ' if consultant else
                            'Modello generico da concordare con il consulente. ') + 'Nessun calcolo di netto o contributi.'),
             ('Gestionale destinatario', data['config']['connector']['provider']),
             ('Versione tracciato consulente', data['config']['connector']['format_version']),
             ('Riferimento specifiche', data['config']['connector']['specification_reference'])]
    notes += [('Avvertenza', i['message']) for i in data['issues'] if i['severity'] == 'warning']
    for r, values in enumerate(notes):
        for col, value in enumerate(values):
            info.write_string(r, col, value)
    wb.close()
    return stream.getvalue()


def export(db, actor, center_id, first, last, fmt, fingerprint):
    fmt = v.choice(fmt, 'Formato', ('csv', 'xlsx'))
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise Invalid('Generare e controllare l’anteprima prima di scaricare.')
    with db.write() as con:
        data = build(con, actor, center_id, first, last)
        actor = users.reload(con, actor)
        if not hmac.compare_digest(fingerprint, data['fingerprint']):
            raise Conflict('Dati o modello cambiati: aggiornare e controllare l’anteprima.')
        if not data['can_download']:
            raise Invalid('Risolvere i controlli bloccanti dell’anteprima prima di scaricare.')
        raw = _csv(data) if fmt == 'csv' else _xlsx(data)
        audit.record(con, actor, 'Esportazione paghe', center_id, entity='payroll', entity_id=data['fingerprint'][:16],
                     after=dict(first=first, last=last, version=data['version'], format=fmt, rows=data['summary']['rows'],
                                fingerprint=data['fingerprint'], file_sha256=hashlib.sha256(raw).hexdigest()))
    name = f'paghe_{data["center_code"]}_{first}_{last}.{fmt}'
    return Reply(raw, content_type=MIME_CSV if fmt == 'csv' else MIME_XLSX, filename=name)


# --- specifiche del consulente ------------------------------------------------------------------

def spec_preview(db, user, center_id, raw):
    """Legge solo intestazioni o una specifica JSON: nulla viene salvato, righe di dati rifiutate."""
    v.keys(raw, {'kind', 'text', 'delimiter'}, 'Specifica', required={'kind', 'text'})
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'paghe.gestisci')
    text = raw['text']
    try:
        size = len(text.encode('utf-8')) if isinstance(text, str) else 0
    except UnicodeEncodeError:
        raise Invalid('La specifica contiene caratteri non validi.') from None
    if not isinstance(text, str) or not text.strip() or size > SPEC_MAX_BYTES:
        raise Invalid('Inviare soltanto intestazioni o una specifica JSON, massimo 32 KiB.')
    connector = dict(default_connector(), mode='consultant')
    delimiter = raw.get('delimiter', ';')
    decimal = ','
    columns = []
    if raw['kind'] == 'csv_header':
        delimiter = v.choice(delimiter, 'Separatore', (';', ',', '\t'))
        try:
            parsed = [r for r in csv.reader(io.StringIO(text.lstrip('﻿')), delimiter=delimiter, strict=True) if r]
        except csv.Error:
            raise Invalid('Intestazione CSV non leggibile.') from None
        if len(parsed) != 1:
            raise Invalid('Inviare solo la riga delle intestazioni, senza dati dei dipendenti.')
        if not 3 <= len(parsed[0]) <= len(FIELDS):
            raise Invalid(f'L’intestazione deve avere da 3 a {len(FIELDS)} colonne.')
        for label in parsed[0]:
            label = _header(label)
            field = next((k for k, f in FIELDS.items() if label.casefold() in (k.casefold(), f[0].casefold())), '')
            columns.append(dict(field=field, label=label))
            connector['expected_columns'].append(dict(header=label, required=True, type=FIELDS[field][1] if field else 'text',
                                                      max_length=None))
    elif raw['kind'] == 'json':
        try:
            spec = json.loads(text.lstrip('﻿'))
        except (ValueError, RecursionError):
            raise Invalid('Specifica JSON non leggibile.') from None
        allowed = {'schema', 'provider', 'format_name', 'format_version', 'specification_reference', 'delimiter',
                   'decimal_separator', 'date_format', 'encoding', 'columns'}
        if not isinstance(spec, dict) or set(spec) - allowed or spec.get('schema') != SPEC_SCHEMA:
            raise Invalid(f'Usare una specifica {SPEC_SCHEMA}, senza dati dei dipendenti o campi aggiuntivi.')
        if not isinstance(spec.get('columns'), list) or not 3 <= len(spec['columns']) <= len(FIELDS):
            raise Invalid('Specifica delle colonne non valida.')
        for key in ('provider', 'format_name', 'format_version', 'specification_reference', 'date_format', 'encoding'):
            if key in spec:
                connector[key] = spec[key]
        delimiter = spec.get('delimiter', ';')
        decimal = spec.get('decimal_separator', ',')
        if delimiter not in (';', ',', '\t') or decimal not in ('.', ','):
            raise Invalid('Separatore della specifica non supportato.')
        for col in spec['columns']:
            if not isinstance(col, dict) or set(col) - {'header', 'field', 'required', 'type', 'max_length'}:
                raise Invalid('Colonna della specifica non valida.')
            field = col.get('field', '')
            if not isinstance(field, str) or (field and field not in FIELDS):
                raise Invalid('Campo del registro non riconosciuto.')
            header = _header(col.get('header'))
            columns.append(dict(field=field, label=header))
            connector['expected_columns'].append(dict(header=header, required=col.get('required', True),
                                                      type=col.get('type', FIELDS.get(field, ('', 'text'))[1]),
                                                      max_length=col.get('max_length')))
    else:
        raise Invalid('Scegliere intestazioni CSV o specifica JSON.')
    connector = validate_connector(connector)
    mapped = [c['field'] for c in columns if c['field']]
    if len(mapped) != len(set(mapped)):
        raise Invalid('Uno stesso dato del registro è associato a più colonne.')
    return dict(center_id=center['id'], connector=connector, columns=columns, delimiter=delimiter, decimal_separator=decimal,
                unmapped=sum(not c['field'] for c in columns), stored=False,
                notice='Sono state lette soltanto intestazioni e regole. Associare i dati, completare il gestionale e salvare '
                       'una nuova versione in bozza.')


def specification(db, user, center_id):
    """Contratto di formato portabile, senza righe dei dipendenti né mappature personali."""
    with db.read() as con:
        centers.scoped(con, user, center_id, 'paghe.gestisci')
        cfg = current(con, center_id)['config']
    c = cfg['connector']
    expected = {col['header']: col for col in c['expected_columns']}
    return dict(schema=SPEC_SCHEMA, **{k: c[k] for k in ('provider', 'format_name', 'format_version', 'specification_reference',
                                                          'date_format', 'encoding')},
                delimiter=cfg['delimiter'], decimal_separator=cfg['decimal_separator'],
                columns=[dict(expected.get(col['label'], dict(header=col['label'], required=col['field'] in REQUIRED_FIELDS,
                                                                type=FIELDS.get(col['field'], ('', 'text'))[1], max_length=None)),
                              field=col['field']) for col in cfg['columns']])


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/payroll/<cid>', cap='paghe.gestisci')
def api_read(ctx):
    return read(ctx.db, ctx.user, ctx.params['cid'])


@route('PUT', '/api/payroll/<cid>', cap='paghe.gestisci', step_up=True)
def api_save(ctx):
    return save(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/payroll/<cid>/preview', cap='paghe.gestisci')
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.params['cid'], ctx.q('from'), ctx.q('to'))


@route('GET', '/api/payroll/<cid>/export', cap='paghe.gestisci', step_up=True)
def api_export(ctx):
    return export(ctx.db, ctx.user, ctx.params['cid'], ctx.q('from'), ctx.q('to'), ctx.q('format', 'csv'), ctx.q('fingerprint'))


@route('POST', '/api/payroll/<cid>/spec-preview', cap='paghe.gestisci')
def api_spec_preview(ctx):
    return spec_preview(ctx.db, ctx.user, ctx.params['cid'], ctx.body)


@route('GET', '/api/payroll/<cid>/specification', cap='paghe.gestisci')
def api_specification(ctx):
    return specification(ctx.db, ctx.user, ctx.params['cid'])
