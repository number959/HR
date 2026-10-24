"""Tracciato paghe generico, versionato e verificato prima del download.

Una riga corrisponde a una fascia a consuntivo. Le quantità non sono una
liquidazione della busta paga; nessuna compatibilità con gestionali è presunta.
"""
import copy
import csv
import hashlib
import hmac
import io
import json
from collections import defaultdict
from datetime import datetime
import re

import analytics
import xlsxwriter
from rules import duration, month_days, span

MIME_CSV = 'text/csv; charset=utf-8'
MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_ROWS = 100000
PREVIEW_ROWS = 100
FIELDS = {
    'template_version': ('Versione modello', 'integer'),
    'center_code': ('Codice centro', 'text'),
    'registration': ('Matricola paghe', 'text'),
    'person_name': ('Dipendente', 'text'),
    'global_id': ('Identificativo persona di gruppo', 'text'),
    'day': ('Data', 'date'),
    'slot': ('Fascia', 'text'),
    'payroll_code': ('Causale paghe', 'text'),
    'source_code': ('Causale registro', 'text'),
    'kind': ('Tipo registrazione', 'text'),
    'start': ('Ingresso', 'text'),
    'end': ('Uscita', 'text'),
    'overnight': ('Giorno successivo', 'integer'),
    'pause_minutes': ('Pausa minuti', 'integer'),
    'worked_minutes': ('Minuti lavorati', 'integer'),
    'worked_hours': ('Ore lavorate decimali', 'decimal'),
    'work_shifts': ('Turni lavorati', 'integer'),
    'absence_slots': ('Fasce assenza', 'integer'),
    'absence_days': ('Giorni assenza per causale', 'integer'),
    'credited_minutes': ('Credito assenza minuti', 'integer'),
    'holiday': ('Festivo', 'integer'),
    'work_site': ('Sede effettiva', 'text'),
    'role': ('Ruolo alla data', 'text'),
    'weekly_hours': ('Ore contrattuali settimanali alla data', 'decimal'),
    'part_time_percent': ('Part-time percentuale alla data', 'decimal'),
    'contract_type': ('Contratto alla data', 'text'),
    'ccnl': ('CCNL alla data', 'text'),
    'level': ('Livello alla data', 'text'),
    'source_id': ('Identificativo registrazione', 'text'),
}
REQUIRED_FIELDS = {'template_version', 'center_code', 'registration', 'day', 'payroll_code'}
DEFAULT_FIELDS = ['template_version', 'center_code', 'registration', 'person_name', 'day',
                  'slot', 'payroll_code', 'worked_minutes', 'worked_hours', 'work_shifts',
                  'absence_slots', 'absence_days', 'credited_minutes', 'source_id']


def init(core):
    with core.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS payroll_templates(
            cid TEXT NOT NULL REFERENCES centers(id), version INTEGER NOT NULL,
            data TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            PRIMARY KEY(cid,version))''')
        c.commit()


def _access(core, c, user, cid):
    user = core.fresh_user(c, user)
    if user['role'] not in ('admin', 'manager', 'hr'):
        raise PermissionError('Paghe riservate all’ufficio HR e ai responsabili autorizzati.')
    if not isinstance(cid, str) or not cid or cid == 'all':
        raise ValueError('Selezionare un singolo centro.')
    if user['role'] == 'manager':
        core.authorize(user, cid)
    return user, core.center(c, cid)


def _default(center):
    return {'name': 'Tracciato generico da concordare', 'status': 'draft',
            'confirmation_note': '', 'delimiter': ';', 'decimal_separator': ',',
            'columns': [{'field': key, 'label': FIELDS[key][0]} for key in DEFAULT_FIELDS],
            'causes': {v['id']: '' for v in center['config']['codes']}, 'registrations': {},
            'connector': _default_connector()}


def _current(c, center):
    r = c.execute('SELECT * FROM payroll_templates WHERE cid=? ORDER BY version DESC LIMIT 1',
                  (center['id'],)).fetchone()
    if r:
        cfg = json.loads(r['data'])
        cfg.setdefault('connector', _default_connector())
        return {'version': r['version'], 'config': cfg,
                'created_at': r['created_at'], 'created_by': r['created_by']}
    return {'version': 0, 'config': _default(center), 'created_at': '', 'created_by': ''}


def _text(value, name, maximum, blank=True):
    if not isinstance(value, str) or len(value) > maximum or any(ord(ch) < 32 for ch in value):
        raise ValueError(name + ': testo non valido.')
    value = value.strip()
    if not blank and not value:
        raise ValueError(name + ': valore obbligatorio.')
    return value


def validate_config(raw, people):
    expected = {'name', 'status', 'confirmation_note', 'delimiter', 'decimal_separator',
                'columns', 'causes', 'registrations'}
    if not isinstance(raw, dict) or set(raw) - (expected | {'connector'}) or not expected <= set(raw):
        raise ValueError('Modello paghe incompleto o con campi non previsti.')
    cfg = copy.deepcopy(raw)
    cfg['connector'] = _validate_connector(cfg.get('connector', _default_connector()))
    consultant = cfg['connector']['mode'] == 'consultant'
    cfg['name'] = _text(cfg['name'], 'Nome modello', 120, False)
    cfg['confirmation_note'] = _text(cfg['confirmation_note'], 'Verifica consulente', 1000)
    if cfg['status'] not in ('draft', 'confirmed'):
        raise ValueError('Stato modello non valido.')
    if cfg['status'] == 'confirmed' and len(cfg['confirmation_note']) < 8:
        raise ValueError('Indicare il riferimento alla verifica con il consulente (almeno 8 caratteri).')
    if cfg['delimiter'] not in (';', ',', '\t') or cfg['decimal_separator'] not in ('.', ','):
        raise ValueError('Separatore CSV o decimale non valido.')
    minimum = 3 if consultant else 5
    if not isinstance(cfg['columns'], list) or not minimum <= len(cfg['columns']) <= len(FIELDS):
        raise ValueError('Scegliere da %s a %s colonne.' % (minimum, len(FIELDS)))
    fields, labels = set(), set()
    for col in cfg['columns']:
        if not isinstance(col, dict) or set(col) != {'field', 'label'} or not isinstance(col.get('field'), str) or (col.get('field') not in FIELDS and not (consultant and col.get('field') == '')):
            raise ValueError('Colonna non riconosciuta.')
        col['label'] = _text(col['label'], 'Intestazione', 120, False)
        if (col['field'] and col['field'] in fields) or col['label'].casefold() in labels:
            raise ValueError('Le colonne e le intestazioni non possono essere duplicate.')
        if consultant:
            _header(col['label'])
        fields.add(col['field']); labels.add(col['label'].casefold())
    if not consultant and not REQUIRED_FIELDS <= fields:
        raise ValueError('Mantenere versione modello, codice centro, matricola, data e causale paghe.')
    if consultant and cfg['status'] == 'confirmed':
        errors = _connector_issues(cfg)
        if errors:
            raise ValueError(errors[0][1])
    for key in ('causes', 'registrations'):
        mapping = cfg[key]
        if not isinstance(mapping, dict) or len(mapping) > (500 if key == 'causes' else 20000):
            raise ValueError('Mappatura ' + key + ' non valida.')
        for source, target in mapping.items():
            _text(source, 'Identificativo origine', 100, False)
            mapping[source] = _text(target, 'Codice destinazione', 100)
        if key == 'registrations' and set(mapping) - {p['id'] for p in people}:
            raise ValueError('Mappatura matricole riferita a persone di un altro centro o inesistenti.')
    return cfg


def read(core, user, cid):
    with core.connect() as c:
        c.execute('BEGIN')
        user, center = _access(core, c, user, cid)
        current = _current(c, center)
        people = core.objects(c, 'people', cid)
        causes = {v['id']: {'id': v['id'], 'label': v['label'], 'kind': v['kind']}
                  for v in center['config']['codes']}
        for row in c.execute("SELECT DISTINCT json_extract(data,'$.code') AS code, "
                             "json_extract(data,'$.code_label') AS label, "
                             "json_extract(data,'$.kind') AS kind FROM entries WHERE cid=?", (cid,)):
            causes.setdefault(row['code'], {'id': row['code'], 'label': row['label'], 'kind': row['kind']})
        history = [{'version': r['version'], 'created_at': r['created_at'], 'created_by': r['created_by'],
                    'name': json.loads(r['data'])['name'], 'status': json.loads(r['data'])['status']}
                   for r in c.execute('SELECT * FROM payroll_templates WHERE cid=? ORDER BY version DESC LIMIT 30', (cid,))]
        return {**current, 'cid': cid, 'center': center['name'], 'history': history,
                'fields': [{'id': k, 'label': v[0], 'type': v[1], 'required': k in REQUIRED_FIELDS}
                           for k, v in FIELDS.items()],
                'people': [{'id': p['id'], 'name': p['name'], 'registration': p.get('registration', '')}
                           for p in people], 'causes': list(causes.values())}


def save(core, user, body):
    with core.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        cid = body.get('cid', '')
        user, center = _access(core, c, user, cid)
        current = _current(c, center)
        if type(body.get('expected_version')) is not int or body['expected_version'] != current['version']:
            raise ValueError('Il modello è cambiato. Ricaricare la pagina prima di salvare.')
        cfg = validate_config(body.get('config'), core.objects(c, 'people', cid))
        if cfg['connector']['mode'] == 'consultant' and cfg['status'] == 'confirmed' and body.get('confirm_connector') is not True:
            raise ValueError('Confermare esplicitamente la verifica di questa versione del tracciato con il consulente.')
        version = current['version'] + 1
        c.execute('INSERT INTO payroll_templates VALUES(?,?,?,?,?)',
                  (cid, version, core.dump(cfg), core.now(), user['username']))
        core.audit(c, user, 'Modello paghe salvato', cid,
                   before={'version': current['version']},
                   after={'version': version, 'name': cfg['name'], 'status': cfg['status']})
        c.commit()
    return {'ok': True, 'version': version, 'status': cfg['status']}


def _build(core, c, user, cid, first, last):
    import workforce
    months = analytics.months_between(first, last)
    user, center = _access(core, c, user, cid)
    current = _current(c, center); cfg = current['config']
    people = {p['id']: p for p in core.objects(c, 'people', cid)}
    entries = [json.loads(r[0]) for r in c.execute(
        "SELECT data FROM entries WHERE cid=? AND json_extract(data,'$.day')>=? "
        "AND json_extract(data,'$.day')<=? ORDER BY json_extract(data,'$.day'),id LIMIT ?",
        (cid, first + '-01', month_days(last)[-1], MAX_ROWS + 1))]
    if len(entries) > MAX_ROWS:
        raise ValueError('Oltre 100.000 registrazioni: ridurre il periodo.')
    actual = sorted((e for e in entries if e['layer'] == 'actual'),
                    key=lambda e: (e['day'], people.get(e['person_id'], {}).get('name', ''), e['slot'], e['id']))
    issues = []
    def issue(code, message, entry=None, severity='error'):
        item = {'code': code, 'message': message, 'severity': severity}
        if entry:
            item.update(day=entry['day'], person_id=entry['person_id'], entry_id=entry['id'])
        issues.append(item)
    if current['version'] == 0 or cfg['status'] != 'confirmed':
        issue('unconfirmed_template', 'Confermare il modello dopo la verifica delle specifiche con il consulente.')
    for code, message in _connector_issues(cfg):
        issue(code, message)
    if not actual:
        issue('empty', 'Nessuna registrazione a consuntivo nel periodo selezionato.')
    import approvals
    for approval_month in months:
        try:
            approvals.require_approved(core, c, user, cid, approval_month)
        except ValueError as exc:
            issue('approval_required', approval_month + ': ' + str(exc))
    open_months = [m for m in months if not core.period(c, center, m)['closed']]
    if open_months:
        issue('open_months', 'Mesi ancora aperti: ' + ', '.join(open_months) + '. I dati possono cambiare.', severity='warning')
    actual_keys = set(); timed = defaultdict(list); registration_owner = {}; seen_absence = set()
    rows = []; work_minutes = []; missing_hours = 0; unresolved = 0; contract_missing = set()
    selected = {col['field'] for col in cfg['columns']}
    for entry in actual:
        pid = entry['person_id']
        if pid not in people:
            issue('orphan', 'Registrazione senza anagrafica: ripristinare il collegamento.', entry); continue
        person = workforce.effective_person(c, cid, pid, entry['day'])
        key = (pid, entry['day'], entry['slot'])
        if key in actual_keys:
            issue('duplicate', 'La stessa persona ha più consuntivi nella stessa fascia.', entry)
        actual_keys.add(key)
        registration = cfg['registrations'].get(pid, '') or person.get('registration', '')
        if not registration:
            issue('missing_registration', person['name'] + ': matricola paghe mancante.', entry)
        elif registration in registration_owner and registration_owner[registration] != pid:
            issue('duplicate_registration', 'La matricola paghe ' + registration + ' è attribuita a più persone del centro.', entry)
        else:
            registration_owner[registration] = pid
        mapped = cfg['causes'].get(entry['code'], '')
        if not mapped:
            issue('unmapped_cause', 'Manca il codice paghe per la causale ' + entry['code'] + '.', entry)
        minutes = duration(entry) if entry['kind'] == 'work' else None
        if entry['kind'] == 'work':
            if minutes is None:
                missing_hours += 1; issue('missing_hours', person['name'] + ': completare ingresso e uscita.', entry)
            elif minutes < 0:
                issue('invalid_hours', 'Durata negativa: correggere gli orari o la pausa.', entry)
            else:
                work_minutes.append(minutes)
            interval = span(entry)
            if interval:
                timed[pid].append((interval[0], interval[1], entry))
        absence_key = (pid, entry['day'], mapped or entry['code'])
        absence_day = int(entry['kind'] == 'absence' and absence_key not in seen_absence)
        if entry['kind'] == 'absence':
            seen_absence.add(absence_key)
        contract = person.get('effective_contract')
        if not contract:
            contract_missing.add(pid)
        record = {'template_version': current['version'], 'center_code': center['code'],
                  'registration': registration, 'person_name': person['name'],
                  'global_id': person.get('global_id', ''), 'day': entry['day'], 'slot': entry['slot'],
                  'payroll_code': mapped, 'source_code': entry['code'], 'kind': entry['kind'],
                  'start': entry.get('start', ''), 'end': entry.get('end', ''),
                  'overnight': int(bool(entry.get('overnight'))),
                  'pause_minutes': entry.get('pause', 0) if entry['kind'] == 'work' else None,
                  'worked_minutes': minutes, 'worked_hours': round(minutes / 60, 6) if minutes is not None else None,
                  'work_shifts': int(entry['kind'] == 'work'), 'absence_slots': int(entry['kind'] == 'absence'),
                  'absence_days': absence_day,
                  'credited_minutes': entry.get('credit_minutes') if entry['kind'] == 'absence' else None,
                  'holiday': int(bool(entry.get('holiday'))), 'work_site': entry.get('work_site', ''),
                  'role': person.get('role', ''), 'source_id': entry['id']}
        for field in ('weekly_hours', 'part_time_percent', 'contract_type', 'ccnl', 'level'):
            record[field] = person.get(field) if contract else None
            if record[field] == '': record[field] = None
        if any(record.get(field) is None for field in selected & {'weekly_hours', 'part_time_percent'}):
            issue('missing_contract_value', person['name'] + ': dato contrattuale richiesto dal modello non disponibile alla data.', entry)
        values = [record.get(col['field']) for col in cfg['columns']]
        if cfg['connector']['mode'] == 'consultant':
            for col, expected, value in zip(cfg['columns'], cfg['connector']['expected_columns'], values):
                problem = _value_issue(value, col['field'], expected, cfg)
                if problem:
                    issue('consultant_value', person['name'] + ' · ' + expected['header'] + ': ' + problem, entry)
        rows.append(values)
    for intervals in timed.values():
        intervals.sort(key=lambda v: (v[0], v[1]))
        latest_end = None
        for start, end, entry in intervals:
            if latest_end is not None and start < latest_end:
                issue('overlap', 'Sovrapposizione tra orari della stessa persona nel centro.', entry)
            latest_end = max(latest_end, end) if latest_end is not None else end
    for entry in entries:
        if entry['layer'] == 'planned' and entry['kind'] == 'work' and (entry['person_id'], entry['day'], entry['slot']) not in actual_keys:
            unresolved += 1
            issue('pending_actual', 'Fascia pianificata senza consuntivo.', entry)
    if contract_missing:
        issue('no_contract_history', str(len(contract_missing)) + ' persone senza contratto storico alla data. Il ruolo usa l’anagrafica corrente dove manca lo storico; ore e percentuali contrattuali restano vuote.', severity='warning')
    blockers = sum(i['severity'] == 'error' for i in issues)
    summary = {'rows': len(rows), 'people': len({e['person_id'] for e in actual if e['person_id'] in people}),
               'work_shifts': sum(e['kind'] == 'work' for e in actual),
               'absence_slots': sum(e['kind'] == 'absence' for e in actual),
               'absence_days': len({(e['person_id'], e['day']) for e in actual if e['kind'] == 'absence'}),
               'known_minutes': sum(work_minutes) if work_minutes else (0 if actual and not any(e['kind'] == 'work' for e in actual) else None),
               'missing_hours': missing_hours, 'pending_actual': unresolved, 'blocking_issues': blockers,
               'warnings': len(issues) - blockers}
    payload = {'cid': cid, 'first': first, 'last': last, 'version': current['version'],
               'config': cfg, 'rows': rows, 'issues': issues, 'summary': summary}
    fingerprint = hashlib.sha256(core.dump(payload).encode()).hexdigest()
    return {'center': center['name'], 'center_code': center['code'], 'cid': cid, 'first': first, 'last': last,
            'version': current['version'], 'template_name': cfg['name'], 'status': cfg['status'],
            'connector': copy.deepcopy(cfg['connector']),
            'output_format': {'delimiter': cfg['delimiter'], 'decimal_separator': cfg['decimal_separator'],
                              'date_format': cfg['connector']['date_format'], 'encoding': cfg['connector']['encoding']},
            'connector_status': ('verified' if cfg['status'] == 'confirmed' and not _connector_issues(cfg) else 'draft') if cfg['connector']['mode'] == 'consultant' else 'generic',
            'columns': [{'field': x['field'], 'label': x['label'], 'type': FIELDS.get(x['field'], ('', 'text'))[1]} for x in cfg['columns']],
            'rows': rows, 'summary': summary, 'issues': issues, 'can_download': blockers == 0,
            'fingerprint': fingerprint, 'config': cfg}, user


def preview(core, user, cid, first, last):
    with core.connect() as c:
        c.execute('BEGIN')
        data, _ = _build(core, c, user, cid, first, last)
    data.pop('config')
    data['shown_rows'] = min(len(data['rows']), PREVIEW_ROWS)
    data['rows'] = data['rows'][:PREVIEW_ROWS]
    data['shown_issues'] = min(len(data['issues']), 200)
    data['issues'] = data['issues'][:200]
    return data


def _safe_csv(value):
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
        return "'" + value
    return value


def _csv(data):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=data['config']['delimiter'])
    writer.writerow([_safe_csv(col['label']) for col in data['columns']])
    for row in data['rows']:
        values = []
        for value, col in zip(row, data['columns']):
            if value is None:
                value = ''
            elif col['type'] == 'date' and data['config']['connector']['date_format'] == 'DD/MM/YYYY':
                value = datetime.fromisoformat(value).strftime('%d/%m/%Y')
            elif col['type'] == 'decimal' and isinstance(value, (int, float)):
                value = format(value, '.6f').rstrip('0').rstrip('.').replace('.', data['config']['decimal_separator'])
            values.append(_safe_csv(value))
        writer.writerow(values)
    return stream.getvalue().encode(data['config']['connector']['encoding'])


def _xlsx(data):
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': 'Tracciato paghe · ' + data['template_name'], 'author': 'NefroCenter',
                       'comments': 'Versione %s; SHA256 dati %s' % (data['version'], data['fingerprint'])})
    header = wb.add_format({'bold': True, 'bg_color': '#233C61', 'font_color': '#FFFFFF'})
    date_fmt = wb.add_format({'num_format': 'dd/mm/yyyy' if data['config']['connector']['date_format'] == 'DD/MM/YYYY' else 'yyyy-mm-dd'})
    decimal_fmt = wb.add_format({'num_format': '0.000000'})
    ws = wb.add_worksheet('Paghe')
    for col, spec in enumerate(data['columns']):
        ws.write_string(0, col, spec['label'], header)
        ws.set_column(col, col, min(42, max(15, len(spec['label']))))
    for row_number, row in enumerate(data['rows'], 1):
        for col, (value, spec) in enumerate(zip(row, data['columns'])):
            if value is None or value == '':
                ws.write_blank(row_number, col, None)
            elif spec['type'] == 'date':
                ws.write_datetime(row_number, col, datetime.fromisoformat(value), date_fmt)
            elif spec['type'] in ('integer', 'decimal'):
                ws.write_number(row_number, col, float(value), decimal_fmt if spec['type'] == 'decimal' else None)
            else:
                ws.write_string(row_number, col, str(value))
    ws.freeze_panes(1, 3); ws.autofilter(0, 0, len(data['rows']), len(data['columns']) - 1)
    info = wb.add_worksheet('Informazioni'); info.set_column(0, 0, 28); info.set_column(1, 1, 100)
    notes = [('Modello', data['template_name']), ('Versione', str(data['version'])),
             ('Centro', data['center']), ('Periodo', data['first'] + ' / ' + data['last']),
             ('SHA256 dati', data['fingerprint']), ('Creato il', datetime.now().astimezone().isoformat(timespec='seconds')),
             ('Verifica consulente', data['config']['confirmation_note']),
             ('Grana', 'Una riga per fascia a consuntivo; pianificazioni escluse.'),
             ('Giorni assenza', '1 alla prima fascia della persona/data/causale paghe; non sommare causali diverse per ottenere giornate totali.'),
             ('Ore e crediti', 'Ore lavorate e crediti assenza separati; vuoto significa non disponibile, 0 è un valore registrato.'),
             ('Tracciato', 'Specifiche configurate per il consulente; nessun invio automatico al gestionale esterno. Nessun calcolo di netto o contributi.' if data['config']['connector']['mode'] == 'consultant' else 'Modello generico da concordare con il consulente. Nessun calcolo di netto o contributi.'),
             ('Gestionale destinatario', data['config']['connector']['provider']),
             ('Versione tracciato consulente', data['config']['connector']['format_version']),
             ('Riferimento specifiche', data['config']['connector']['specification_reference'])]
    notes += [('Avvertenza', issue['message']) for issue in data['issues'] if issue['severity'] == 'warning']
    for row, values in enumerate(notes):
        for col, value in enumerate(values): info.write_string(row, col, value)
    wb.close()
    return stream.getvalue()


def export(core, user, cid, first, last, format='csv', fingerprint=''):
    if format not in ('csv', 'xlsx'):
        raise ValueError('Formato non valido: scegliere CSV o Excel.')
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError('Generare e controllare l’anteprima prima di scaricare.')
    with core.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        data, user = _build(core, c, user, cid, first, last)
        if not hmac.compare_digest(fingerprint, data['fingerprint']):
            raise ValueError('Dati o modello cambiati: aggiornare e controllare l’anteprima.')
        if not data['can_download']:
            raise ValueError('Risolvere i controlli bloccanti nell’anteprima prima di scaricare.')
        raw = _csv(data) if format == 'csv' else _xlsx(data)
        core.audit(c, user, 'Esportazione paghe', cid, after={
            'dal': first, 'al': last, 'version': data['version'], 'format': format,
            'rows': data['summary']['rows'], 'fingerprint': data['fingerprint'],
            'file_sha256': hashlib.sha256(raw).hexdigest()})
        c.commit()
    return raw


SPEC_SCHEMA = 'nefrocenter.payroll-spec.v1'
CONSULTANT_REQUIRED = {'registration', 'day', 'payroll_code'}
SPEC_MAX_BYTES = 32768


def _default_connector():
    return {'mode': 'generic', 'provider': '', 'format_name': '', 'format_version': '',
            'specification_reference': '', 'expected_columns': [],
            'date_format': 'YYYY-MM-DD', 'encoding': 'utf-8-sig'}


def _header(value):
    value = _text(value, 'Intestazione consulente', 120, False)
    if value.startswith(('=', '+', '-', '@')):
        raise ValueError('Intestazione consulente non valida: non usare formule o prefissi di formula.')
    return value


def _validate_connector(raw):
    default = _default_connector()
    if not isinstance(raw, dict) or set(raw) != set(default):
        raise ValueError('Profilo consulente incompleto o con campi non previsti.')
    cfg = copy.deepcopy(raw)
    if cfg['mode'] not in ('generic', 'consultant'):
        raise ValueError('Tipo di collegamento consulente non valido.')
    for key, maximum in [('provider', 120), ('format_name', 120), ('format_version', 80), ('specification_reference', 500)]:
        cfg[key] = _text(cfg[key], key, maximum)
    if cfg['date_format'] not in ('YYYY-MM-DD', 'DD/MM/YYYY') or cfg['encoding'] not in ('utf-8-sig', 'utf-8', 'cp1252'):
        raise ValueError('Formato data o codifica non supportati.')
    if not isinstance(cfg['expected_columns'], list) or len(cfg['expected_columns']) > len(FIELDS):
        raise ValueError('Elenco intestazioni consulente non valido.')
    seen = set()
    for col in cfg['expected_columns']:
        if not isinstance(col, dict) or set(col) != {'header', 'required', 'type', 'max_length'}:
            raise ValueError('Regola di colonna non valida.')
        col['header'] = _header(col['header'])
        if col['header'].casefold() in seen:
            raise ValueError('Le intestazioni del consulente non possono essere duplicate.')
        seen.add(col['header'].casefold())
        if type(col['required']) is not bool or col['type'] not in ('text', 'integer', 'decimal', 'date'):
            raise ValueError('Obbligatorietà o tipo della colonna non validi.')
        if col['max_length'] is not None and (type(col['max_length']) is not int or not 1 <= col['max_length'] <= 2000):
            raise ValueError('Lunghezza massima della colonna: usare da 1 a 2000 caratteri oppure lasciare vuoto.')
    return cfg


def _connector_issues(cfg):
    connector = cfg['connector']
    if connector['mode'] == 'generic':
        return []
    issues = []
    if not connector['provider'] or connector['provider'].casefold() in {'unknown', 'non so', 'non definito', 'da definire', 'sconosciuto'}:
        issues.append(('consultant_unknown', 'Indicare il gestionale del consulente: non è ancora definito.'))
    for key, label in [('format_name', 'nome del tracciato'), ('format_version', 'versione delle specifiche'), ('specification_reference', 'riferimento alle specifiche ricevute')]:
        if not connector[key]:
            issues.append(('consultant_metadata', 'Completare il ' + label + ' del consulente.'))
    expected = connector['expected_columns']
    if len(expected) < 3:
        issues.append(('consultant_headers', 'Caricare o definire almeno tre intestazioni del consulente.'))
    if [col['header'] for col in expected] != [col['label'] for col in cfg['columns']]:
        issues.append(('consultant_headers', 'Le intestazioni e il loro ordine non corrispondono alle specifiche del consulente.'))
    mapped = {col['field'] for col in cfg['columns'] if col['field']}
    if any(not col['field'] for col in cfg['columns']):
        issues.append(('consultant_mapping', 'Associare ogni intestazione del consulente a un dato del registro.'))
    if not CONSULTANT_REQUIRED <= mapped:
        issues.append(('consultant_identity', 'Il tracciato consulente deve identificare matricola, data e causale paghe.'))
    for col, expected_column in zip(cfg['columns'], expected):
        if not col['field']:
            continue
        source_type = FIELDS[col['field']][1]
        target_type = expected_column['type']
        if target_type != 'text' and source_type != target_type and not (source_type == 'integer' and target_type == 'decimal'):
            issues.append(('consultant_type', 'La colonna ' + expected_column['header'] + ' richiede un dato di tipo ' + target_type + '.'))
    try:
        for col in expected:
            col['header'].encode(connector['encoding'])
    except UnicodeEncodeError:
        issues.append(('consultant_encoding', 'Le intestazioni contengono caratteri non rappresentabili nella codifica scelta.'))
    if cfg['status'] != 'confirmed':
        issues.append(('consultant_unconfirmed', 'Il collegamento al consulente è da concordare: verificare mappatura e formato prima di confermare.'))
    return issues


def _formatted(value, field, cfg):
    if value is None:
        return ''
    if FIELDS.get(field, ('', 'text'))[1] == 'date' and cfg['connector']['date_format'] == 'DD/MM/YYYY':
        return datetime.fromisoformat(str(value)).strftime('%d/%m/%Y')
    if FIELDS.get(field, ('', 'text'))[1] == 'decimal' and isinstance(value, (int, float)):
        return format(value, '.6f').rstrip('0').rstrip('.').replace('.', cfg['decimal_separator'])
    return str(value)


def _value_issue(value, field, expected, cfg):
    if value is None or value == '':
        return 'dato obbligatorio mancante.' if expected['required'] else ''
    if expected['type'] == 'integer' and (isinstance(value, bool) or not re.fullmatch(r'[+-]?[0-9]+', str(value))):
        return 'il consulente richiede un numero intero.'
    if expected['type'] == 'decimal':
        try:
            number = float(value)
            import math
            if not math.isfinite(number):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            return 'il consulente richiede un numero decimale.'
    if expected['type'] == 'date':
        try:
            datetime.strptime(str(value), '%Y-%m-%d')
        except (ValueError, TypeError):
            return 'il consulente richiede una data.'
    text = _formatted(value, field, cfg)
    if expected['max_length'] is not None and len(text) > expected['max_length']:
        return 'supera la lunghezza massima di ' + str(expected['max_length']) + ' caratteri.'
    if isinstance(value, str) and _safe_csv(value) != value:
        return 'prefisso di formula non ammesso nel tracciato consulente: correggere il dato.'
    try:
        text.encode(cfg['connector']['encoding'])
    except UnicodeEncodeError:
        return 'contiene caratteri non rappresentabili nella codifica scelta.'
    return ''


def spec_preview(core, user, body):
    """Parse a header/specification only. Nothing is stored and employee rows are rejected."""
    with core.connect() as c:
        user, center = _access(core, c, user, body.get('cid', ''))
    text = body.get('text')
    try:
        size = len(text.encode('utf-8')) if isinstance(text, str) else 0
    except UnicodeEncodeError:
        raise ValueError('La specifica contiene caratteri Unicode non validi.') from None
    if not isinstance(text, str) or not text.strip() or size > SPEC_MAX_BYTES:
        raise ValueError('Inviare soltanto intestazioni o una specifica JSON, massimo 32 KiB.')
    kind = body.get('kind')
    connector = _default_connector(); connector['mode'] = 'consultant'
    delimiter = body.get('delimiter', ';'); decimal = ','; columns = []
    if kind == 'csv_header':
        if delimiter not in (';', ',', '\t'):
            raise ValueError('Separatore CSV non valido.')
        try:
            parsed = list(csv.reader(io.StringIO(text.lstrip('\ufeff')), delimiter=delimiter, strict=True))
        except csv.Error:
            raise ValueError('Intestazione CSV non leggibile.') from None
        parsed = [row for row in parsed if row]
        if len(parsed) != 1:
            raise ValueError('Inviare solo la riga delle intestazioni, senza dati dei dipendenti.')
        if not 3 <= len(parsed[0]) <= len(FIELDS):
            raise ValueError('L’intestazione deve contenere da 3 a %s colonne.' % len(FIELDS))
        for label in parsed[0]:
            label = _header(label)
            field = next((key for key, value in FIELDS.items() if label.casefold() in (key.casefold(), value[0].casefold())), '')
            columns.append({'field': field, 'label': label})
            connector['expected_columns'].append({'header': label, 'required': True, 'type': FIELDS[field][1] if field else 'text', 'max_length': None})
    elif kind == 'json':
        try:
            raw = json.loads(text.lstrip('\ufeff'))
        except (ValueError, RecursionError):
            raise ValueError('Specifica JSON non leggibile.') from None
        allowed = {'schema', 'provider', 'format_name', 'format_version', 'specification_reference', 'delimiter', 'decimal_separator', 'date_format', 'encoding', 'columns'}
        if not isinstance(raw, dict) or set(raw) - allowed or raw.get('schema') != SPEC_SCHEMA:
            raise ValueError('Usare una specifica ' + SPEC_SCHEMA + ', senza dati dei dipendenti o campi aggiuntivi.')
        if not isinstance(raw.get('columns'), list) or not 3 <= len(raw['columns']) <= len(FIELDS):
            raise ValueError('Specifica colonne non valida.')
        for key in ('provider', 'format_name', 'format_version', 'specification_reference', 'date_format', 'encoding'):
            if key in raw:
                connector[key] = raw[key]
        delimiter = raw.get('delimiter', ';'); decimal = raw.get('decimal_separator', ',')
        if delimiter not in (';', ',', '\t') or decimal not in ('.', ','):
            raise ValueError('Separatore della specifica non supportato.')
        for col in raw['columns']:
            if not isinstance(col, dict) or set(col) - {'header', 'field', 'required', 'type', 'max_length'}:
                raise ValueError('Colonna della specifica non valida.')
            field = col.get('field', '')
            if not isinstance(field, str) or field and field not in FIELDS:
                raise ValueError('Campo del registro non riconosciuto.')
            header = _header(col.get('header'))
            columns.append({'field': field, 'label': header})
            connector['expected_columns'].append({'header': header, 'required': col.get('required', True), 'type': col.get('type', FIELDS.get(field, ('', 'text'))[1]), 'max_length': col.get('max_length')})
    else:
        raise ValueError('Scegliere intestazioni CSV o specifica JSON.')
    connector = _validate_connector(connector)
    if len([col['field'] for col in columns if col['field']]) != len({col['field'] for col in columns if col['field']}):
        raise ValueError('Uno stesso dato del registro è associato a più colonne.')
    return {'cid': center['id'], 'connector': connector, 'columns': columns,
            'delimiter': delimiter, 'decimal_separator': decimal,
            'unmapped': sum(not col['field'] for col in columns), 'stored': False,
            'notice': 'Sono state lette soltanto le intestazioni e le regole. Associa i dati, completa il gestionale e salva una nuova versione in bozza.'}


def specification(core, user, cid):
    """Portable format contract, excluding every employee row and personal mapping."""
    with core.connect() as c:
        user, center = _access(core, c, user, cid)
        current = _current(c, center)
    cfg = current['config']; connector = cfg['connector']
    expected = {col['header']: col for col in connector['expected_columns']}
    return {'schema': SPEC_SCHEMA,
            **{key: connector[key] for key in ('provider', 'format_name', 'format_version', 'specification_reference', 'date_format', 'encoding')},
            'delimiter': cfg['delimiter'], 'decimal_separator': cfg['decimal_separator'],
            'columns': [{**expected.get(col['label'], {'header': col['label'], 'required': col['field'] in REQUIRED_FIELDS, 'type': FIELDS.get(col['field'], ('', 'text'))[1], 'max_length': None}), 'field': col['field']} for col in cfg['columns']]}
