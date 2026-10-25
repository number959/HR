"""Importazione del modello Excel delle presenze (Sodav): lettura OOXML, senza Excel e senza macro.

L'anteprima non scrive nulla. La conferma crea una nuova struttura con persone e
registrazioni del mese; le proposte economiche riconosciute dalle formule
restano da confermare. Lo stesso file non si importa due volte.
"""
import calendar
import hashlib
import io
import posixpath
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

from . import agreements, audit, backups, people, rules, users
from .errors import Invalid, NotFound
from .permissions import require
from .util import dumps, new_id, stamp
from .web import route

MAX_FILE = 12_000_000
MAX_UNZIPPED = 80_000_000
PENDING_SECONDS = 900
EXTERNAL_SITE = rules.IMPORT_SITE
REVIEW_SITE = rules.IMPORT_SITE_REVIEW
REVIEW_COLOR = 'Colore della cella non riconosciuto: verificare la sede.'
WORK = {'m': 'Mattina', 'p': 'Pomeriggio', 's': 'Serale', 'n': 'Notte'}
ABSENCE_CODES = [c for c, _ in rules.ABSENCES] + ['R']
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
_PENDING = {}
_LOCK = threading.Lock()


def normalized_code(value):
    text = str(value).strip()
    if text.lower() in WORK:
        return text.lower()
    if text.upper() in ABSENCE_CODES:
        return text.upper()
    raise ValueError(text)


def excel_date(value):
    return (date(1899, 12, 30) + timedelta(days=int(float(value)))).isoformat()


def column(i):
    out = ''
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def recognized_agreement(cells, r):
    """Riconosce le combinazioni di formule economiche note del modello (nessun codice eseguito)."""
    def f(col, row):
        return re.sub(r'[\s$]', '', cells.get(f'{col}{row}', {}).get('formula_text', '')).upper()
    end = r + 2
    at, av, aw, ax, az, ba = f('AT', r), f('AV', end), f('AW', end), f('AX', end), f('AZ', end), f('BA', end)
    expected = f'93-COUNTBLANK(D{r}:AH{end})'
    if at not in (expected, expected + f'-AN{r}'):
        return None
    if av == f'AT{r}':
        basis = 'all'
    elif av == f'IF(AT{r}<=0,"",AT{r}-X3)':
        basis = 'surplus'
    else:
        return None
    if aw != f'IF(AV{end}="","",AV{end}-AY{end})':
        return None
    weekday = re.fullmatch(fr'IF\(AW{end}="","",AW{end}\*([0-9]+(?:\.[0-9]+)?)\)', ax)
    holiday = re.fullmatch(fr'IF\(AY{end}="","",AY{end}\*([0-9]+(?:\.[0-9]+)?)\)', az)
    deduction = re.fullmatch(fr'IF\(AX{end}="","",AX{end}\+AZ{end}(?:-([0-9]+(?:\.[0-9]+)?))?\)', ba)
    if not (weekday and holiday and deduction):
        return None
    counted = [c for c, _ in rules.ABSENCES if c != 'RC' or at == expected]
    return dict(basis=basis, weekday_rate=float(weekday[1]), holiday_rate=float(holiday[1]),
                fixed_deduction=float(deduction[1] or 0), counted_absences=counted)


def read_model(data):
    if len(data) > MAX_FILE:
        raise Invalid('File troppo grande: massimo 12 MB.')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Invalid('Il file non è una cartella di lavoro Excel (.xlsx o .xlsm).') from None
    if sum(e.file_size for e in archive.infolist()) > MAX_UNZIPPED:
        raise Invalid('Il contenuto decompresso supera 80 MB.')

    def xml(path):
        raw = archive.read(path)
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise Invalid('XML con entità non supportato.')
        return ET.fromstring(raw)

    try:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in e.findall('.//s:t', NS)) for e in xml('xl/sharedStrings.xml')]
        rels = {r.get('Id'): posixpath.normpath(posixpath.join('xl', r.get('Target'))) for r in xml('xl/_rels/workbook.xml.rels')}
        book = xml('xl/workbook.xml')
    except KeyError:
        raise Invalid('Struttura del file Excel non riconosciuta.') from None
    prop = book.find('s:workbookPr', NS)
    if prop is not None and prop.get('date1904') in ('1', 'true'):
        raise Invalid('Calendario Excel 1904 non supportato.')
    sheets = {}
    for sheet in book.findall('s:sheets/s:sheet', NS):
        cells = {}
        for c in xml(rels[sheet.get(REL)]).findall('.//s:sheetData/s:row/s:c', NS):
            node = c.find('s:v', NS)
            value = node.text if node is not None else ''
            if c.get('t') == 's':
                value = strings[int(value)] if value else ''
            elif c.get('t') == 'inlineStr':
                value = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
            formula = c.find('s:f', NS)
            cells[c.get('r')] = dict(value=value or '', style=int(c.get('s', 0)), formula=formula is not None,
                                     formula_text=(formula.text or '') if formula is not None else '')
        sheets[sheet.get('name')] = cells
    if 'Da Compilare' not in sheets:
        raise Invalid('Manca il foglio «Da Compilare»: è supportato il modello delle presenze fornito.')
    cells = sheets['Da Compilare']

    def value(addr):
        return cells.get(addr, {}).get('value', '')

    try:
        month = excel_date(value('O6'))[:7]
    except (TypeError, ValueError):
        raise Invalid('Mese non leggibile nella cella O6.') from None
    center = str(value('C6')).strip()
    if not center:
        raise Invalid('Nome della struttura mancante nella cella C6.')
    styles = xml('xl/styles.xml')
    xfs, fills, fonts = styles.find('s:cellXfs', NS), styles.find('s:fills', NS), styles.find('s:fonts', NS)
    theme = {}
    if 'xl/theme/theme1.xml' in archive.namelist():
        ans = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
        scheme = xml('xl/theme/theme1.xml').find('.//a:clrScheme', ans)
        if scheme is not None:
            lookup = {x.tag.split('}')[-1]: next(iter(x), None) for x in scheme}
            for i, key in enumerate(('lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
                                     'hlink', 'folHlink')):
                node = lookup.get(key)
                if node is not None:
                    theme[str(i)] = node.get('lastClr', node.get('val', '')).upper()

    def rgb(attrs):
        if float(attrs.get('tint', '0')) != 0:
            return ''
        return attrs.get('rgb', '').upper()[-6:] or theme.get(attrs.get('theme'), '')

    def colors(addr, sheet=cells):
        x = xfs[sheet.get(addr, {}).get('style', 0)]
        fill = fills[int(x.get('fillId', 0))].find('s:patternFill/s:fgColor', NS)
        font = fonts[int(x.get('fontId', 0))].find('s:color', NS)
        return (dict(fill.attrib) if fill is not None else {}), (dict(font.attrib) if font is not None else {})

    refs = sheets.get('Foglio1', {})
    yellow = colors('I2', refs)[0]
    red_font = colors('M2', refs)[1]
    holidays = [excel_date(c['value']) for a, c in sheets.get('Festività', {}).items()
                if a != 'A1' and c['value'].replace('.', '', 1).isdigit()]
    holidays += [excel_date(value(f'B{r}')) for r in range(159, 174) if value(f'B{r}').replace('.', '', 1).isdigit()]
    holidays = list(dict.fromkeys(holidays))
    warnings = []
    if holidays and any(not h.startswith(month[:4]) for h in holidays):
        warnings.append(f'Calendario non coerente: mese {month} e festività di {", ".join(sorted({h[:4] for h in holidays}))}. '
                        'Nessuna trasposizione automatica.')
    warnings.append('Il modello contiene conteggi per fascia m/p/s senza orari: le ore restano da inserire.')
    year, mon = int(month[:4]), int(month[5:])
    length = calendar.monthrange(year, mon)[1]
    actual_days = sum(date(year, mon, d).weekday() != 6 and f'{month}-{d:02d}' not in holidays for d in range(1, length + 1))
    if value('X3').isdigit() and int(value('X3')) != actual_days:
        warnings.append(f'Calendario da verificare: X3 contiene {value("X3")} giorni; nel mese reale (lunedì–sabato, festività '
                        f'presenti) risultano {actual_days}. Il portale usa le date reali.')
    broken = sum('#REF!' in c['formula_text'] for s in sheets.values() for c in s.values())
    if broken:
        warnings.append(f'Il file contiene {broken} formule con riferimenti interrotti: i risultati derivati non vengono importati.')
    if any('COUNTIF(E' in c['formula_text'].upper() and ':AI' in c['formula_text'].upper() and '"ROL"' in c['formula_text'].upper()
           for c in cells.values()):
        warnings.append('Alcune formule ROL usano E:AI invece della griglia D:AH: i contatori del portale leggono tutte le celle '
                        'del mese.')
    warnings.append('Le formule economiche riconosciute diventano proposte individuali da confermare; importi manuali, IBAN e '
                    'trattenute del foglio Collaboratori non vengono trasformati in regole.')
    persons, entries = [], []
    rows = sorted({int(a.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')) for a in cells})
    for r in rows:
        if (value(f'C{r}').lower(), value(f'C{r + 1}').lower(), value(f'C{r + 2}').lower()) != ('m', 'p', 's'):
            continue
        name = value(f'B{r}').strip()
        if not name:
            continue
        pid = f'row-{r}'
        persons.append(dict(id=pid, name=name, role=value(f'A{r}').strip(), contract=value(f'B{r + 1}'), source_row=r,
                            agreement_note=' | '.join(value(f'AU{r + j}') for j in range(3) if value(f'AU{r + j}')),
                            proposal=recognized_agreement(cells, r)))
        for offset, slot in enumerate(('m', 'p', 's')):
            for d in range(1, 32):
                addr = column(d + 3) + str(r + offset)
                raw = value(addr).strip()
                if not raw:
                    continue
                if cells[addr]['formula']:
                    raise Invalid(f'Formula in una cella delle presenze ({addr}): verificare a mano.')
                if d > length:
                    raise Invalid(f'Dato fuori dal mese nella cella {addr}.')
                try:
                    code = normalized_code(raw)
                except ValueError:
                    raise Invalid(f'Causale non riconosciuta in {addr}: {raw}.') from None
                if code in WORK and code != slot:
                    raise Invalid(f'Codice e fascia non coincidono in {addr}: correggere prima di importare.')
                bg, fg = colors(addr)
                color = rgb(bg)
                external = bool(yellow and bg == yellow) or color in ('FFFF00', '00FF00')
                holiday = bool(red_font and fg == red_font)
                unknown = bool(bg) and not external and color not in ('FFFFFF', '000000')
                if unknown:
                    warnings.append(f'Sfondo non riconosciuto in {addr}: controllare la sede.')
                entries.append(dict(person_id=pid, day=f'{month}-{d:02d}', slot=slot, code=code, external=external,
                                    holiday=holiday, unknown_color=unknown, cell=addr))
    if not persons:
        raise Invalid('Nessuna persona riconosciuta nel modello.')
    if not entries:
        warnings.append('Il file è un modello vuoto: contiene persone ma nessuna presenza compilata.')
    return dict(hash=hashlib.sha256(data).hexdigest(), center=center, month=month, people=persons, entries=entries,
                holidays=holidays, warnings=list(dict.fromkeys(warnings)))


def preview(db, actor, data):
    with db.read() as con:
        actor = users.reload(con, actor)
        require(actor, 'import.excel')
    model = read_model(data)
    key = new_id()
    with _LOCK:
        for k in [k for k, item in _PENDING.items() if time.monotonic() - item['created'] > PENDING_SECONDS]:
            _PENDING.pop(k)
        while len(_PENDING) >= 6:
            _PENDING.pop(next(iter(_PENDING)))
        _PENDING[key] = dict(owner=actor.id, created=time.monotonic(), model=model)
    return dict(key=key, center=model['center'], month=model['month'], people=len(model['people']),
                entries=len(model['entries']), external=sum(e['external'] for e in model['entries']),
                warnings=model['warnings'], hash=model['hash'],
                proposals=sum(p['proposal'] is not None for p in model['people']))


def confirm(db, actor, key):
    with _LOCK:
        pending = _PENDING.get(key)
    if not pending or pending['owner'] != actor.id or time.monotonic() - pending['created'] > PENDING_SECONDS:
        raise NotFound('Anteprima non valida o scaduta: caricare di nuovo il file.')
    model = pending['model']
    with db.read() as con:
        require(users.reload(con, actor), 'import.excel')
        done = con.execute('SELECT center_id, month FROM imports WHERE hash=?', (model['hash'],)).fetchone()
    if done:
        return dict(center_id=done['center_id'], month=done['month'], already_imported=True)
    backups.create(db, 'prima-importazione-excel')
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'import.excel')
        if con.execute('SELECT 1 FROM imports WHERE hash=?', (model['hash'],)).fetchone():
            raise Invalid('File già importato.')
        cfg = rules.defaults()
        cfg['holidays'] = sorted(set(model['holidays']))
        cfg['note'] = '\n'.join(model['warnings'])[:4000]
        cfg['roles'] = list(dict.fromkeys(cfg['roles'] + [p['role'] or 'ALTRO' for p in model['people']]))[:50]
        for slot in cfg['slots']:
            if slot['id'] == 'n':
                slot['active'] = False
        if any(e['external'] for e in model['entries']):
            cfg['sites'] = [EXTERNAL_SITE]
        cfg = rules.validate_config(cfg)
        cid = new_id()
        code = 'IMPORT-' + model['hash'][:12].upper()
        con.execute('INSERT INTO centers(id,name,code,active,config_version,version,created_at) VALUES(?,?,?,1,1,1,?)',
                    (cid, model['center'][:150], code, stamp()))
        con.execute('INSERT INTO center_configs(center_id,version,data,note,created_at,created_by) VALUES(?,1,?,?,?,?)',
                    (cid, dumps(cfg), 'Creati dall’importazione del modello Excel', stamp(), actor.username))
        ids = {}
        for p in model['people']:
            ids[p['id']] = people.insert(con, actor, cid, dict(
                name=p['name'][:150], role=p['role'] or 'ALTRO', registration='', active=True,
                contract=p['contract'][:150], note=(f'{p["contract"]} | {p["agreement_note"]}').strip(' |')[:2000]))
        month = model['month']
        con.execute('INSERT INTO months(center_id,month,rules_version,verified,closed,note,version,updated_at,updated_by) '
                    'VALUES(?,?,1,0,0,?,1,?,?)', (cid, month, '\n'.join(model['warnings'])[:2000], stamp(), actor.username))
        labels = {c['id']: c for c in cfg['codes']}
        for e in model['entries']:
            code_cfg = labels[e['code']]
            review = REVIEW_COLOR if e['unknown_color'] else (REVIEW_SITE if e['external'] else '')
            con.execute('''INSERT INTO entries(id,center_id,person_id,day,slot,layer,code,kind,label,start,end,pause,overnight,site,
                           holiday,credit,note,source,review,rules_version,version,updated_at,updated_by)
                           VALUES(?,?,?,?,?,'actual',?,?,?,'','',0,0,?,?,0,?,?,?,1,1,?,?)''',
                        (new_id(), cid, ids[e['person_id']], e['day'], e['slot'], e['code'], code_cfg['kind'], code_cfg['label'],
                         EXTERNAL_SITE if e['external'] else '', int(e['holiday']), f'Importato dalla cella {e["cell"]}',
                         f'excel:{e["cell"]}', review, stamp(), actor.username))
        for p in model['people']:
            if p['proposal']:
                data = dict(agreements.proposal(cfg, None), **p['proposal'], confirmed=False)
                data = agreements.validate(data, cfg)
                con.execute('INSERT INTO agreements(center_id,month,person_id,data,source,version,updated_at,updated_by) '
                            'VALUES(?,?,?,?,?,1,?,?)', (cid, month, ids[p['id']], dumps(data),
                                                        f'Proposta dalle formule del file (riga {p["source_row"]}): da confermare',
                                                        stamp(), actor.username))
        con.execute('INSERT INTO imports(hash,center_id,month,at) VALUES(?,?,?,?)', (model['hash'], cid, month, stamp()))
        audit.record(con, actor, 'Importazione del modello Excel', cid, entity='import', entity_id=model['hash'][:16],
                     after=dict(hash=model['hash'], people=len(ids), entries=len(model['entries']), warnings=model['warnings']))
    with _LOCK:
        _PENDING.pop(key, None)
    return dict(center_id=cid, month=month, already_imported=False)


# --- API ------------------------------------------------------------------------------------

@route('POST', '/api/import/preview', cap='import.excel', step_up=True)
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.req.raw(MAX_FILE))


@route('POST', '/api/import/confirm', cap='import.excel', step_up=True)
def api_confirm(ctx):
    return confirm(ctx.db, ctx.user, str(ctx.body.get('key') or ''))
