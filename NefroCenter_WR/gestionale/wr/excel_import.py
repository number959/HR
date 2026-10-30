"""Importazione del modello Excel delle presenze (Sodav): lettura OOXML, senza Excel e senza macro.

Serve per caricare i mesi passati e per la transizione: il lavoro quotidiano si fa nel portale.
L'anteprima non scrive nulla e mostra tutto ciò che verrà importato, ciò che resta fuori e perché.
La conferma crea una nuova struttura oppure aggiunge il mese a una struttura esistente con lo
stesso nome (mese vuoto e aperto). Le proposte economiche riconosciute dalle formule restano da
confermare. Lo stesso file non si importa due volte.

Letto dal file: persone (sezione dipendenti/collaboratori), registrazioni del mese con sede esterna
(sfondo giallo) e festivo (carattere rosso), pazienti per fascia, festività elencate, pazienti di
riferimento per infermiere e medico, formule economiche (anche con i festivi CCNL e le formule condivise),
riepilogo dei compensi del foglio «Collaboratori» (senza IBAN, solo come nota).
Ogni cella che non si può importare viene elencata (non blocca il file); ogni controllo che la conferma
farebbe viene fatto già in anteprima, così la conferma non fallisce dopo il backup.
"""
import calendar
import hashlib
import io
import math
import pickle
import posixpath
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import date, timedelta

from . import agreements, approvals, audit, backups, centers, months, people, rules, users
from .errors import Invalid, NotFound
from .permissions import require
from .util import dumps, new_id, stamp
from .web import route

MAX_FILE = 12_000_000
MAX_UNZIPPED = 40_000_000
MAX_CELLS = 400_000
MAX_RATE = 1_000_000
MAX_PATIENTS = 9_999
MAX_SKIPPED_LISTED = 3_000
PENDING_SECONDS = 900
EXTERNAL_SITE = rules.IMPORT_SITE
REVIEW_SITE = rules.IMPORT_SITE_REVIEW
REVIEW_COLOR = 'Colore della cella non riconosciuto: verificare la sede.'
REVIEW_DUPLICATE = 'Registrazione presente due volte nel file con codici diversi: verificare.'
WORK = {'m': 'Mattina', 'p': 'Pomeriggio', 's': 'Serale', 'n': 'Notte'}
ABSENCE_CODES = [c for c, _ in rules.ABSENCES] + ['R']
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
ADDRESS = re.compile(r'[A-Z]{1,3}[1-9][0-9]{0,6}')
DIGITS = re.compile(r'[0-9]{1,7}')
REF = re.compile(r'(\$?)([A-Z]{1,3})(\$?)([0-9]{1,7})(?![0-9A-Za-z_(])')
# Tavolozza di base di Excel: solo i colori che il modello usa (nero, bianco, rosso, giallo, «automatico»).
INDEXED = {'8': '000000', '9': 'FFFFFF', '10': 'FF0000', '13': 'FFFF00', '64': ''}
# Intestazioni di sezione del modello (colonna A): distinguono dipendenti e collaboratori a prestazione.
CONSULTANT_WORDS = ('prestazion', 'consulent', 'volontar', 'altri centri', 'fattura')
EMPLOYEE_WORDS = ('dipendent',)
IGNORED_HEADERS = ('total', 'note', 'pazienti', 'turno', 'rapporto', 'efficienza', 'centro', 'qualifica', 'legenda')
PATIENT_SLOTS = {'mattina': 'm', 'pomeriggio': 'p', 'serale': 's', 'sera': 's', 'notte': 'n'}
GROUP_LABELS = {'dipendente': 'Personale dipendente', 'consulente': 'Collaboratori a prestazione', '': 'Sezione non indicata'}
EMPLOYMENT = re.compile(r'\b(T\.?\s?I\.?|T\.?\s?D\.?|TEMPO|FULL|PART|P\.?\s?T\.?|INDETERMINATO|DETERMINATO)\b', re.I)
_LOCK = threading.Lock()
PENDING_KEY = re.compile(r'[0-9a-f]{32}')
PENDING_MAX = 6


# --- Anteprime in attesa di conferma ----------------------------------------------------------
# Salvate su disco accanto all'archivio (non in memoria): con più processi di lavoro la conferma può
# arrivare a un processo diverso da quello che ha letto il file. Contenuto prodotto dal server stesso.

def _pending_dir(db):
    folder = db.path.parent / 'import_pending'
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


def _pending_path(db, key):
    if not isinstance(key, str) or not PENDING_KEY.fullmatch(key):
        raise NotFound('Anteprima non valida o scaduta: caricare di nuovo il file.')
    return _pending_dir(db) / f'{key}.pending'


def _pending_put(db, key, item):
    with _LOCK:
        folder = _pending_dir(db)
        now = time.time()
        files = sorted(folder.glob('*.pending'), key=lambda p: p.stat().st_mtime)
        for path in files:
            if now - path.stat().st_mtime > PENDING_SECONDS:
                path.unlink(missing_ok=True)
        files = [p for p in files if p.exists()]
        while len(files) >= PENDING_MAX:
            files.pop(0).unlink(missing_ok=True)
        tmp = folder / f'{key}.tmp'
        tmp.write_bytes(pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(folder / f'{key}.pending')


def _pending_get(db, key):
    path = _pending_path(db, key)
    try:
        item = pickle.loads(path.read_bytes())
    except (FileNotFoundError, pickle.UnpicklingError, EOFError):
        return None
    if time.time() - item['created'] > PENDING_SECONDS:
        path.unlink(missing_ok=True)
        return None
    return item


def _pending_pop(db, key):
    _pending_path(db, key).unlink(missing_ok=True)


# --- Funzioni di servizio ---------------------------------------------------------------------

def normalized_code(value):
    text = str(value).strip()
    if text.lower() in WORK:
        return text.lower()
    if text.upper() in ABSENCE_CODES:
        return text.upper()
    raise ValueError(text)


def excel_date(value):
    return (date(1899, 12, 30) + timedelta(days=int(float(value)))).isoformat()


def safe_excel_date(raw):
    """Data ISO di un seriale Excel plausibile (1990–2100), altrimenti None: niente eccezioni sui valori strani."""
    text = str(raw).strip().replace(',', '.')
    if not is_number(text):
        return None
    try:
        iso = excel_date(text)
    except (ValueError, OverflowError):
        return None
    return iso if 1990 <= int(iso[:4]) <= 2100 else None


def column(i):
    out = ''
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def column_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def split_address(addr):
    letters = addr.rstrip('0123456789')
    return letters, int(addr[len(letters):])


def fold(name):
    """Confronto dei nominativi: spazi doppi, maiuscole e spazi finali non contano."""
    return ' '.join(str(name).split()).casefold()


def is_number(text):
    try:
        return math.isfinite(float(str(text).replace(',', '.')))
    except (ValueError, OverflowError):
        return False


def to_int(raw, lo, hi):
    """Intero entro i limiti, altrimenti None (celle vuote, testo, numeri enormi o non finiti)."""
    text = str(raw).strip()
    if not text or not is_number(text):
        return None
    number = int(round(float(text.replace(',', '.'))))
    return number if lo <= number <= hi else None


def safe_int(text, default=0):
    try:
        number = int(text)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def money(value):
    return f'{value:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def shift_formula(text, master, target):
    """Formula condivisa: i riferimenti relativi della cella principale traslati sulla cella dipendente."""
    master_col, master_row = split_address(master)
    target_col, target_row = split_address(target)
    dc, dr = column_index(target_col) - column_index(master_col), target_row - master_row

    def shift(m):
        col_abs, col, row_abs, row = m.groups()
        if not col_abs:
            col = column(max(1, column_index(col) + dc))
        if not row_abs:
            row = str(max(1, int(row) + dr))
        return f'{col_abs}{col}{row_abs}{row}'

    parts = re.split(r'("[^"]*")', text)
    return ''.join(p if p.startswith('"') else REF.sub(shift, p) for p in parts)


def recognized_agreement(cells, r):
    """Riconosce le combinazioni di formule economiche note del modello (nessun codice eseguito).

    Varianti accettate: base «tutti i turni» (AV=AT) o «eccedenza» (AV=AT-X3), tariffe feriale e festiva,
    detrazione fissa facoltativa e, nei modelli più recenti, i festivi già riconosciuti dal CCNL (-tariffa*BB).
    """
    def f(col, row):
        return re.sub(r'[\s$]', '', cells.get(f'{col}{row}', {}).get('formula_text', ''))[:400].upper()
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
    number = r'([0-9]+(?:\.[0-9]+)?)'
    weekday = re.fullmatch(fr'IF\(AW{end}="","",AW{end}\*{number}\)', ax)
    holiday = re.fullmatch(fr'IF\(AY{end}="","",AY{end}\*{number}\)', az)
    deduction = re.fullmatch(fr'IF\(AX{end}="","",AX{end}\+AZ{end}(?:-{number})?(?:-{number}\*BB{end})?\)', ba)
    if not (weekday and holiday and deduction):
        return None
    values = dict(weekday_rate=float(weekday[1]), holiday_rate=float(holiday[1]), fixed_deduction=float(deduction[1] or 0),
                  ccnl_rate=float(deduction[2] or 0))
    if any(not math.isfinite(x) or x > MAX_RATE for x in values.values()):
        return None
    ccnl_count = 0
    if values['ccnl_rate']:
        # COUNTA(BB{r}:BC{r+1}): i festivi già riconosciuti sono le celle compilate dall'ufficio in quel riquadro.
        ccnl_count = sum(1 for col in ('BB', 'BC') for row in (r, r + 1)
                         if str(cells.get(f'{col}{row}', {}).get('value', '')).strip())
    counted = [c for c, _ in rules.ABSENCES if c != 'RC' or at == expected]
    return dict(basis=basis, ccnl_count=ccnl_count, counted_absences=counted, **values)


def _section_of(text, current):
    """Aggiorna la sezione corrente leggendo un'intestazione della colonna A: una riga di totali la chiude."""
    low = text.casefold()
    if low.startswith('total'):
        return ''
    if any(w in low for w in CONSULTANT_WORDS):
        return 'consulente'
    if any(w in low for w in EMPLOYEE_WORDS):
        return 'dipendente'
    return current


def _group_of(section, contract):
    """Dipendente o collaboratore: decide la riga sotto il nome (tipo di contratto o chi fattura), poi la sezione."""
    if contract and EMPLOYMENT.search(contract):
        return 'dipendente'
    if contract and 'fattura' in contract.casefold():
        return 'consulente'
    return section


def _holiday_dates(cells, value):
    """Date delle festività elencate nel file: sotto l'etichetta «Festività» e nell'intervallo usato da X3."""
    found = []
    anchors = set()
    for addr, c in cells.items():
        if str(c['value']).strip().casefold().startswith('festivit'):
            anchors.add(split_address(addr))
    for letters, row in anchors:
        blanks = 0
        for r in range(row + 1, row + 60):
            raw = str(value(f'{letters}{r}')).strip()
            if raw and is_number(raw):
                found.append(raw)
                blanks = 0
            elif raw:
                break
            else:
                blanks += 1
                if blanks > 2:
                    break
    formula = cells.get('X3', {}).get('formula_text', '')[:2000]
    for m in list(re.finditer(r'([A-Z]{1,2})([0-9]{1,7}):([A-Z]{1,2})([0-9]{1,7})', formula))[:10]:
        c1, r1, c2, r2 = m.groups()
        if c1 == c2 and 0 < int(r2) - int(r1) < 200:
            for r in range(int(r1), int(r2) + 1):
                raw = str(value(f'{c1}{r}')).strip()
                if raw and is_number(raw):
                    found.append(raw)
    return sorted({iso for iso in (safe_excel_date(raw) for raw in found) if iso})


def _patients(cells, value, rows, month, length, warnings):
    """Pazienti per fascia e giorno dalle righe «Pazienti turno …» (le righe «Contumacia» sono gli isolati)."""
    counts = {}
    conflicts, rejected = set(), []
    for r in rows:
        label = str(value(f'A{r}')).strip().casefold()
        m = re.match(r'pazienti\s+turno\s+(\w+)', label)
        if not m or m.group(1) not in PATIENT_SLOTS:
            continue
        slot = PATIENT_SLOTS[m.group(1)]
        field = 'isolated' if 'contumac' in label else 'ordinary'
        for d in range(1, min(31, length) + 1):
            addr = column(d + 3) + str(r)
            raw = str(value(addr)).strip()
            if not raw:
                continue
            number = to_int(raw, 0, MAX_PATIENTS)
            if number is None:
                rejected.append(addr)
                continue
            key = (f'{month}-{d:02d}', slot)
            current = counts.setdefault(key, {})
            if field in current and current[field] != number:
                conflicts.add(key[0])
            current.setdefault(field, number)
    if conflicts:
        warnings.append(f'Pazienti per fascia indicati due volte con valori diversi in {len(conflicts)} giorni: '
                        'viene usata la prima tabella del file.')
    if rejected:
        shown = ', '.join(rejected[:8]) + (', …' if len(rejected) > 8 else '')
        warnings.append(f'Pazienti per fascia non leggibili o fuori misura in {len(rejected)} celle ({shown}): non importati.')
    return [dict(day=day, slot=slot, ordinary=c.get('ordinary', 0), isolated=c.get('isolated', 0))
            for (day, slot), c in sorted(counts.items()) if c.get('ordinary') or c.get('isolated')]


def _collaborators(sheet):
    """Foglio «Collaboratori»: turni feriali/festivi, lordo, ritenuta, cassa e netto per nominativo. L'IBAN non si legge."""
    if not sheet:
        return []

    def value(addr):
        return str(sheet.get(addr, {}).get('value', '')).strip()

    header = None
    for addr, c in sheet.items():
        if str(c['value']).strip().casefold() == 'collaboratore':
            header = split_address(addr)[1]
            break
    if header is None:
        return []
    columns = {}
    for addr, c in sheet.items():
        letters, row = split_address(addr)
        if row != header:
            continue
        text = str(c['value']).casefold()
        for key, words in (('role', ('qualifica',)), ('name', ('collaboratore',)), ('shifts', ('turni',)),
                           ('gross', ('lordo',)), ('withholding', ('ritenuta',)), ('pension', ('enpapi', 'cassa', 'cont.')),
                           ('net', ('netto',)), ('note', ('note',))):
            if any(w in text for w in words) and key not in columns:
                columns[key] = letters
    if 'name' not in columns:
        return []
    shifts = columns.get('shifts')
    out = []
    blanks = 0
    for r in range(header + 1, header + 200):
        name = value(f'{columns["name"]}{r}')
        if not name:
            blanks += 1
            if blanks > 3:
                break
            continue
        blanks = 0
        low = name.casefold()
        if 'totale' in low or 'competenze' in low or value(f'{columns.get("role", "A")}{r}').casefold().startswith('totale'):
            continue

        def number(key, offset=0):
            letters = columns.get(key)
            if not letters:
                return None
            raw = value(f'{column(column_index(letters) + offset)}{r}')
            return float(raw.replace(',', '.')) if raw and is_number(raw) else None

        out.append(dict(name=' '.join(name.split())[:150], role=value(f'{columns.get("role", "A")}{r}')[:120],
                        weekday_shifts=number('shifts'), holiday_shifts=number('shifts', 1) if shifts else None,
                        gross=number('gross'), withholding=number('withholding'), pension=number('pension'),
                        net=number('net'), note=value(f'{columns["note"]}{r}')[:200] if 'note' in columns else '', row=r))
    return out


def collaborator_summary(c):
    parts = []
    if c.get('weekday_shifts') is not None:
        parts.append(f'{c["weekday_shifts"]:g} turni feriali')
    if c.get('holiday_shifts') is not None:
        parts.append(f'{c["holiday_shifts"]:g} festivi')
    for key, label in (('gross', 'lordo'), ('withholding', 'ritenuta'), ('pension', 'cassa'), ('net', 'netto')):
        if c.get(key) is not None:
            parts.append(f'{label} {money(c[key])}')
    if c.get('note'):
        parts.append(f'nota «{c["note"]}»')
    return 'Foglio Collaboratori: ' + ', '.join(parts) if parts else ''


# --- Lettura del file -------------------------------------------------------------------------

def _open(data):
    if len(data) > MAX_FILE:
        raise Invalid('File troppo grande: massimo 12 MB.')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        if sum(e.file_size for e in archive.infolist()) > MAX_UNZIPPED:
            raise Invalid('Il contenuto decompresso supera 40 MB.')
    except zipfile.BadZipFile:
        raise Invalid('Il file non è una cartella di lavoro Excel (.xlsx o .xlsm).') from None
    return archive


def _xml(archive, path):
    """Documento XML del pacchetto: niente DOCTYPE/entità, solo UTF-8, errori di lettura tradotti in Invalid."""
    try:
        raw = archive.read(path)
    except (KeyError, zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError, ValueError):
        raise Invalid('File Excel danneggiato o non leggibile.') from None
    if raw.startswith((b'\xff\xfe', b'\xfe\xff', b'\x00\x00\xfe\xff')) or re.match(rb'\s*<\?xml[^>]*encoding=["\'](?![Uu][Tt][Ff]-8)', raw[:200]):
        raise Invalid('Codifica XML non supportata: il file non proviene da Excel.')
    # Solo UTF-8 arriva fin qui: il controllo sui byte basta a escludere DOCTYPE ed entità (Excel non li scrive mai).
    if re.search(rb'<!(?:DOCTYPE|ENTITY)', raw, re.I):
        raise Invalid('XML con entità non supportato.')
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise Invalid('Struttura del file Excel non riconosciuta.') from None


def _sheets(archive):
    strings = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        strings = [''.join(t.text or '' for t in e.findall('.//s:t', NS)) for e in _xml(archive, 'xl/sharedStrings.xml')]
    rels = {}
    for r in _xml(archive, 'xl/_rels/workbook.xml.rels'):
        rid, target = r.get('Id'), r.get('Target')
        if not rid or not target or r.get('TargetMode') == 'External':
            continue
        rels[rid] = posixpath.normpath(target.lstrip('/')) if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
    book = _xml(archive, 'xl/workbook.xml')
    prop = book.find('s:workbookPr', NS)
    if prop is not None and prop.get('date1904') in ('1', 'true'):
        raise Invalid('Calendario Excel 1904 non supportato.')
    sheets, total = {}, 0
    for sheet in book.findall('s:sheets/s:sheet', NS):
        target = rels.get(sheet.get(REL))
        if not target or target not in archive.namelist():
            continue
        cells, shared = {}, {}
        for c in _xml(archive, target).findall('.//s:sheetData/s:row/s:c', NS):
            addr = c.get('r') or ''
            if not ADDRESS.fullmatch(addr):
                continue
            node = c.find('s:v', NS)
            value = node.text if node is not None else ''
            if c.get('t') == 's':
                value = strings[int(value)] if value and DIGITS.fullmatch(value) and int(value) < len(strings) else ''
            elif c.get('t') == 'inlineStr':
                value = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
            formula = c.find('s:f', NS)
            text = (formula.text or '') if formula is not None else ''
            if formula is not None and formula.get('t') == 'shared':
                si = formula.get('si')
                if text:
                    shared[si] = (addr, text)
                elif si in shared:
                    text = shift_formula(shared[si][1], shared[si][0], addr)
            if not value and formula is None:
                continue
            cells[addr] = dict(value=value or '', style=safe_int(c.get('s')), formula=formula is not None, formula_text=text)
            total += 1
            if total > MAX_CELLS:
                raise Invalid('Il file contiene troppe celle per essere il modello delle presenze.')
        sheets[sheet.get('name')] = cells
    return sheets


def _palette(archive):
    """Stili e tema del file: servono per riconoscere sfondo giallo e carattere rosso."""
    styles = _xml(archive, 'xl/styles.xml')
    xfs, fills, fonts = styles.find('s:cellXfs', NS), styles.find('s:fills', NS), styles.find('s:fonts', NS)
    theme = {}
    if 'xl/theme/theme1.xml' in archive.namelist():
        try:
            ans = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
            scheme = _xml(archive, 'xl/theme/theme1.xml').find('.//a:clrScheme', ans)
        except Invalid:
            scheme = None
        if scheme is not None:
            lookup = {x.tag.split('}')[-1]: next(iter(x), None) for x in scheme}
            for i, key in enumerate(('lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
                                     'hlink', 'folHlink')):
                node = lookup.get(key)
                if node is not None:
                    theme[str(i)] = node.get('lastClr', node.get('val', '')).upper()

    def child(parent, raw_index):
        if parent is None:
            return None
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return None
        return parent[index] if 0 <= index < len(parent) else None

    def colors(cells, addr):
        x = child(xfs, cells.get(addr, {}).get('style', 0))
        if x is None:
            return {}, {}
        fill = child(fills, x.get('fillId', 0))
        font = child(fonts, x.get('fontId', 0))
        fg = fill.find('s:patternFill/s:fgColor', NS) if fill is not None else None
        color = font.find('s:color', NS) if font is not None else None
        return (dict(fg.attrib) if fg is not None else {}), (dict(color.attrib) if color is not None else {})

    def resolve(attrs):
        """Colore come RGB esadecimale: rgb esplicito, tavolozza di base o tema; '' se tinta o colore ignoti."""
        try:
            if float(attrs.get('tint', '0')) != 0:
                return ''
        except ValueError:
            return ''
        if attrs.get('rgb'):
            return attrs['rgb'].upper()[-6:]
        if attrs.get('indexed') is not None:
            return INDEXED.get(attrs['indexed'], '')
        return theme.get(attrs.get('theme', ''), '')

    return colors, resolve


def read_model(data):
    archive = _open(data)
    sheets = _sheets(archive)
    if 'Da Compilare' not in sheets:
        raise Invalid('Manca il foglio «Da Compilare»: è supportato il modello delle presenze fornito.')
    cells = sheets['Da Compilare']

    def value(addr):
        return cells.get(addr, {}).get('value', '')

    month_iso = safe_excel_date(value('O6'))
    if not month_iso or not 2000 <= int(month_iso[:4]) <= 2100:
        raise Invalid('Mese non leggibile nella cella O6: controllare la data del mese (anno tra il 2000 e il 2100).')
    month = month_iso[:7]
    center = ' '.join(str(value('C6')).split())[:150]
    if not center:
        raise Invalid('Nome della struttura mancante nella cella C6.')
    colors, resolve = _palette(archive)
    refs = sheets.get('Foglio1', {})
    yellow = colors(refs, 'I2')[0]
    red_font = colors(refs, 'M2')[1]
    warnings, notes = [], []
    year, mon = int(month[:4]), int(month[5:])
    length = calendar.monthrange(year, mon)[1]
    file_holidays = [safe_excel_date(c['value']) for a, c in sheets.get('Festività', {}).items() if a != 'A1']
    file_holidays = sorted({h for h in file_holidays if h} | set(_holiday_dates(cells, value)))
    national = [d for d, _ in rules.italian_holidays(year)]
    holidays = sorted(set(national) | {h for h in file_holidays if h.startswith(month[:4])})
    other_years = sorted({h[:4] for h in file_holidays if not h.startswith(month[:4])})
    if file_holidays and not any(h.startswith(month[:4]) for h in file_holidays):
        warnings.append(f'Il file elenca festività di altri anni ({", ".join(other_years)}): per il mese vengono usate le festività '
                        f'nazionali del {year}. Il patrono locale va aggiunto nei parametri della struttura.')
    elif not file_holidays:
        notes.append(f'Il file non elenca festività: vengono usate le festività nazionali del {year}. '
                     'Il patrono locale va aggiunto nei parametri della struttura.')
    elif other_years:
        notes.append(f'Oltre alle festività del {year}, il file ne elenca di altri anni ({", ".join(other_years)}): ignorate.')
    notes.append('Il modello contiene conteggi per fascia m/p/s senza orari: le ore restano da inserire.')
    actual_days = sum(date(year, mon, d).weekday() != 6 and f'{month}-{d:02d}' not in holidays for d in range(1, length + 1))
    x3 = str(value('X3')).strip()
    theoretical_note = ''
    if DIGITS.fullmatch(x3) and int(x3) != actual_days:
        theoretical_note = (f'nel file l’eccedenza era calcolata su X3 = {x3} giorni, il portale usa {actual_days}: ogni proposta '
                            f'«oltre il teorico» differisce di {abs(int(x3) - actual_days)}')
        warnings.append(f'Calendario da verificare: X3 contiene {x3} giorni; nel mese reale (lunedì–sabato, festività '
                        f'presenti) risultano {actual_days}. Il portale usa le date reali; {theoretical_note}.')
    broken = sum('#REF!' in c['formula_text'] for s in sheets.values() for c in s.values())
    if broken:
        warnings.append(f'Il file contiene {broken} formule con riferimenti interrotti: i risultati derivati non vengono importati.')
    if any('COUNTIF(E' in c['formula_text'].upper() and ':AI' in c['formula_text'].upper() and '"ROL"' in c['formula_text'].upper()
           for c in cells.values()):
        notes.append('Alcune formule ROL usano E:AI invece della griglia D:AH: i contatori del portale leggono tutte le celle '
                     'del mese.')
    if any('CONTACELLEPERCOLORE' in c['formula_text'].upper() for c in cells.values()):
        notes.append('I conteggi per colore del file dipendono da macro: il portale legge direttamente i colori delle celle '
                     '(giallo = fuori sede, carattere rosso = festivo).')

    parameters = {}
    for addr, key in (('AJ4', 'nurse_reference'), ('AM4', 'doctor_reference')):
        raw = str(value(addr)).strip()
        if raw and is_number(raw) and 0 < float(raw.replace(',', '.')) <= 1000:
            parameters[key] = float(raw.replace(',', '.'))
    for addr, key in (('AD4', 'stations'), ('AG4', 'isolation_stations')):
        number = to_int(value(addr), 0, 10000)
        if number is not None:
            parameters[key] = number

    persons, entries, skipped = [], [], []
    unknown_cells, unknown_fonts, red_absences, unreadable = [], [], [], []
    by_name, seen_slots, covered = {}, {}, set()
    section = ''
    rows = sorted({split_address(a)[1] for a in cells})

    def grid_cells(start, count):
        return [(column(d + 3) + str(start + off), off) for off in range(count) for d in range(1, 32)
                if str(value(column(d + 3) + str(start + off))).strip()]

    def skip(addr, off, who, reason, start):
        raw = str(value(addr)).strip()
        d = column_index(split_address(addr)[0]) - 3
        skipped.append(dict(cell=addr, value=raw[:40], person=who, day=f'{month}-{min(d, length):02d}', slot=('m', 'p', 's')[off],
                            reason=reason))

    for r in rows:
        first = ' '.join(str(value(f'A{r}')).split())
        trio = tuple(str(value(f'C{r + j}')).strip().lower() for j in range(3))
        if trio != ('m', 'p', 's'):
            if r not in covered and trio[0] in ('m', 'p', 's'):
                filled = [(addr, 0) for addr, _ in grid_cells(r, 1)]
                if filled:
                    for addr, off in filled:
                        skip(addr, ('m', 'p', 's').index(trio[0]), f'riga {r} senza blocco riconosciuto', 'riga di un blocco non riconosciuto (colonna C incompleta)', r)
                    warnings.append(f'Blocco non riconosciuto alla riga {r}: controllare le celle C{r}:C{r + 2} (devono essere m, p, s); '
                                    f'{len(filled)} celle non importate.')
            if first and not str(value(f'B{r}')).strip() and (first.casefold().startswith('total')
                                                            or not any(first.casefold().startswith(w) for w in IGNORED_HEADERS)):
                section = _section_of(first, section)
            continue
        covered.update((r, r + 1, r + 2))
        name = ' '.join(str(value(f'B{r}')).split())[:150]
        if not name:
            filled = grid_cells(r, 3)
            for addr, off in filled:
                skip(addr, off, f'blocco senza nominativo (righe {r}-{r + 2})', 'blocco senza nominativo', r)
            below = ' '.join(str(value(f'B{r + 1}')).split())
            if filled:
                warnings.append(f'Blocco alle righe {r}-{r + 2} senza nominativo in B{r}: {len(filled)} celle non importate'
                                + (f' (B{r + 1} contiene «{below[:40]}»: il nome è forse nella riga sbagliata)' if below else '') + '.')
            elif below:
                warnings.append(f'Blocco alle righe {r}-{r + 2} senza nominativo in B{r} ma con «{below[:40]}» in B{r + 1}: nessuna cella compilata, ignorato.')
            continue
        contract = ' '.join(str(value(f'B{r + 1}')).split())[:150]
        role = first[:120]
        extra_roles = [f'{t} (riga {r + j})' for j in (1, 2) for t in [' '.join(str(value(f'A{r + j}')).split())]
                       if t and t.casefold() != role.casefold()]
        agreement_note = ' | '.join(str(value(f'AU{r + j}')).strip() for j in range(3) if str(value(f'AU{r + j}')).strip())
        proposal = recognized_agreement(cells, r)
        key = fold(name)
        person = by_name.get(key)
        if person is None:
            group = _group_of(section, contract)
            person = dict(id=f'row-{r}', name=name, role=role, contract=contract, group=group, rows=[r], source_row=r,
                          agreement_note=agreement_note, proposal=proposal, proposal_row=r if proposal else None,
                          proposal_partial=False, extra_roles=extra_roles, extra_contracts=[], collaborator=None,
                          notes=[f'Sezione del file: {GROUP_LABELS[group]}'] if group else [])
            if group == 'consulente' and contract and not EMPLOYMENT.search(contract):
                person['billing'] = contract  # per i collaboratori la riga sotto il nome indica chi fattura
                person['contract'] = 'Prestazione / consulenza'
            by_name[key] = person
            persons.append(person)
        else:
            person['rows'].append(r)
            if role and role.casefold() != person['role'].casefold():
                person['extra_roles'].append(f'{role} (righe {r}-{r + 2})')
            person['extra_roles'].extend(extra_roles)
            if contract and contract.casefold() != person['contract'].casefold():
                person['extra_contracts'].append(f'{contract} (righe {r}-{r + 2})')
            if agreement_note:
                person['agreement_note'] = ' | '.join(x for x in (person['agreement_note'], agreement_note) if x)
            text = (f'«{name}» compare due volte nel registro (righe {person["source_row"]} e {r}): le registrazioni sono '
                    'state unite in una sola persona')
            if proposal and person['proposal'] is None:
                person['proposal'], person['proposal_row'], person['proposal_partial'] = proposal, r, True
                text += (f'; la proposta economica deriva dalle sole righe {r}-{r + 2}: nel file l’eccedenza era calcolata su quel '
                         'blocco, nel portale su tutte le registrazioni unite')
            elif proposal and person['proposal'] is not None:
                person['proposal_partial'] = True
                text += (f'; la proposta economica deriva dalle righe {person["proposal_row"]}-{person["proposal_row"] + 2}, '
                         f'le formule delle righe {r}-{r + 2} sono ignorate')
            warnings.append(text + '.')
        for off, slot in enumerate(('m', 'p', 's')):
            for d in range(1, 32):
                addr = column(d + 3) + str(r + off)
                raw = str(value(addr)).strip()
                if not raw:
                    continue
                if cells[addr]['formula']:
                    skip(addr, off, name, 'la cella contiene una formula', r)
                    continue
                if d > length:
                    skip(addr, off, name, 'giorno oltre la fine del mese', r)
                    continue
                try:
                    code = normalized_code(raw)
                except ValueError:
                    skip(addr, off, name, 'causale non riconosciuta', r)
                    continue
                if code in WORK and code != slot:
                    skip(addr, off, name, f'codice della fascia «{WORK[code]}» nella riga «{WORK[slot]}»', r)
                    continue
                slot_key = (person['id'], f'{month}-{d:02d}', slot)
                previous = seen_slots.get(slot_key)
                if previous is not None:
                    if previous['code'] != code:
                        previous['review'] = REVIEW_DUPLICATE
                        skip(addr, off, name, f'doppione con codice diverso (già importato da {previous["cell"]})', r)
                    else:
                        skip(addr, off, name, f'doppione dello stesso turno (già importato da {previous["cell"]})', r)
                    continue
                bg, fg = colors(cells, addr)
                fill, ink = resolve(bg), resolve(fg)
                external = bool(yellow and bg == yellow) or fill in ('FFFF00', '00FF00')
                holiday = bool(red_font and fg == red_font) or ink == 'FF0000'
                unknown = bool(bg) and not external and fill not in ('FFFFFF', '000000')
                if unknown:
                    unknown_cells.append(addr)
                if fg and not holiday and ink not in ('', '000000', 'FFFFFF'):
                    unknown_fonts.append(addr)
                if holiday and code not in WORK:
                    red_absences.append(addr)
                entry = dict(person_id=person['id'], day=f'{month}-{d:02d}', slot=slot, code=code, external=external,
                             holiday=holiday, unknown_color=unknown, cell=addr, review='')
                seen_slots[slot_key] = entry
                entries.append(entry)
    for lst, text in ((unknown_cells, 'Sfondo non riconosciuto in {n} celle ({shown}): controllare la sede.'),
                      (unknown_fonts, 'Colore del carattere non riconosciuto in {n} celle ({shown}): controllare i festivi.'),
                      (red_absences, 'Assenze con carattere rosso in {n} celle ({shown}): nel file la macro le conterebbe fra i '
                                     'festivi, nel portale i festivi riguardano solo i turni di lavoro.')):
        if lst:
            shown = ', '.join(lst[:12]) + (', …' if len(lst) > 12 else '')
            warnings.append(text.format(n=len(lst), shown=shown))
    if skipped:
        shown = '; '.join(f'{s["cell"]} «{s["value"]}»' for s in skipped[:8]) + ('; …' if len(skipped) > 8 else '')
        warnings.append(f'{len(skipped)} celle non importate, da completare a mano nel registro: {shown}.')
    if not persons:
        raise Invalid('Nessuna persona riconosciuta nel modello.')
    if not entries:
        warnings.append('Il file è un modello vuoto: contiene persone ma nessuna presenza compilata.')
    workload = _patients(cells, value, rows, month, length, warnings)
    collaborators = _collaborators(sheets.get('Collaboratori'))
    unmatched = []
    for c in collaborators:
        person = by_name.get(fold(c['name']))
        if person is None:
            unmatched.append(c['name'])
            continue
        person['collaborator'] = c
        proposal = person['proposal']
        if proposal and c.get('gross') is not None and c.get('weekday_shifts') is not None:
            expected = (c['weekday_shifts'] * proposal['weekday_rate'] + (c['holiday_shifts'] or 0) * proposal['holiday_rate']
                        - proposal['fixed_deduction'] - proposal['ccnl_count'] * proposal['ccnl_rate'])
            person['proposal_matches_sheet'] = abs(expected - c['gross']) < 0.5
    if collaborators:
        notes.append('Il foglio «Collaboratori» viene letto solo come promemoria (turni, lordo, ritenute, netto) nelle note delle '
                     'persone e degli accordi: gli importi, le trattenute e l’IBAN non diventano regole di calcolo.')
    if unmatched:
        warnings.append('Nel foglio «Collaboratori» compaiono nominativi assenti dal registro: ' + ', '.join(unmatched[:10])
                        + ('…' if len(unmatched) > 10 else '') + '.')
    mismatched = [p['name'] for p in persons if p.get('proposal_matches_sheet') is False]
    if mismatched:
        warnings.append('Per alcuni collaboratori il lordo del foglio «Collaboratori» non coincide con le tariffe generiche delle formule '
                        f'({", ".join(mismatched[:6])}{"…" if len(mismatched) > 6 else ""}): confermare gli accordi con le tariffe reali.')
    notes.append('Le formule economiche riconosciute diventano proposte individuali da confermare negli accordi del mese.')
    return dict(hash=hashlib.sha256(data).hexdigest(), center=center, month=month, people=persons, entries=entries,
                holidays=holidays, file_holidays=file_holidays, warnings=list(dict.fromkeys(warnings)), notes=list(dict.fromkeys(notes)),
                skipped=skipped, workload=workload, parameters=parameters, collaborators=collaborators,
                theoretical_note=theoretical_note)


# --- Testi e controlli -------------------------------------------------------------------------

def person_note(p, cfg_roles=None):
    lines = [f'Importato dal file Excel (riga {p["source_row"]}' + (f', unita con righe {", ".join(str(r) for r in p["rows"][1:])}' if len(p['rows']) > 1 else '') + ')']
    lines += p.get('notes', [])
    if p.get('billing'):
        lines.append(f'Fatturazione / ente indicato nel file: {p["billing"]}')
    if p['extra_roles']:
        lines.append('Altri ruoli nel file: ' + ', '.join(p['extra_roles']))
    if p.get('extra_contracts'):
        lines.append('Contratto o fatturazione negli altri blocchi: ' + ', '.join(p['extra_contracts']))
    if cfg_roles is not None and p['role'] and p['role'] not in cfg_roles:
        lines.append(f'Ruolo indicato nel file: {p["role"]}')
    if p['agreement_note']:
        lines.append(f'Accordi (colonna AU): {p["agreement_note"]}')
    if p.get('collaborator'):
        lines.append(collaborator_summary(p['collaborator']))
    return '\n'.join(lines)[:2000]


def agreement_source(p, model):
    text = f'Proposta dalle formule del file (riga {p.get("proposal_row") or p["source_row"]}): da confermare'
    if p.get('proposal_partial'):
        text += '; deriva da uno solo dei blocchi della persona unita'
    if p['proposal'] and p['proposal']['basis'] == 'surplus' and model.get('theoretical_note'):
        text += '; ' + model['theoretical_note']
    if p.get('collaborator'):
        text += '. ' + collaborator_summary(p['collaborator'])
        if p.get('proposal_matches_sheet') is False:
            text += ' → lordo diverso dalle tariffe delle formule: inserire le tariffe reali'
    return text[:1000]


def _month_note(model):
    text = '\n'.join(model['warnings'])
    if model['skipped']:
        text += '\nCelle non importate: ' + '; '.join(f'{s["cell"]} «{s["value"]}» ({s["person"]}, {s["reason"]})'
                                                     for s in model['skipped'][:40])
    return text[:2000]


def _new_center_config(model):
    """Parametri della nuova struttura; ruoli oltre il limite vengono lasciati fuori (le persone passano a ALTRO)."""
    cfg = rules.defaults()
    cfg['holidays'] = sorted(set(model['holidays']))
    notes = [f'Creati dall’importazione del file Excel ({model["center"]}, {model["month"]}).']
    if model['parameters'].get('stations') is not None:
        notes.append(f'Posti dialisi accreditati indicati nel file: {model["parameters"]["stations"]}'
                     + (f', contumaciali: {model["parameters"]["isolation_stations"]}' if 'isolation_stations' in model['parameters'] else '') + '.')
    cfg['note'] = '\n'.join(notes + model['warnings'])[:4000]
    cfg['roles'] = list(dict.fromkeys(cfg['roles'] + [p['role'] for p in model['people'] if p['role']]))[:50]
    for key in ('nurse_reference', 'doctor_reference'):
        if key in model['parameters']:
            cfg[key] = model['parameters'][key]
    if model['parameters'].get('stations') is not None:
        cfg['dialysis_stations'] = model['parameters']['stations']
    if model['parameters'].get('isolation_stations') is not None:
        cfg['isolation_stations'] = model['parameters']['isolation_stations']
    for slot in cfg['slots']:
        if slot['id'] == 'n':
            slot['active'] = False
    if any(e['external'] for e in model['entries']):
        cfg['sites'] = [EXTERNAL_SITE]
    return rules.validate_config(cfg)


def _proposal_data(p, cfg):
    """Accordo proposto per la persona, limitato alle causali della struttura; None se non valido."""
    allowed = {c['id'] for c in cfg['codes'] if c['kind'] != 'work'}
    prop = dict(p['proposal'])
    prop['counted_absences'] = [c for c in prop['counted_absences'] if c in allowed]
    try:
        return agreements.validate(dict(agreements.proposal(cfg, None), **prop, confirmed=False), cfg)
    except Invalid:
        return None


def _missing(model, cfg):
    """Causali e fasce del file assenti o disattivate nei parametri della struttura."""
    codes = {c['id']: c for c in cfg['codes']}
    slots = {s['id'] for s in cfg['slots'] if s['active']}
    missing_codes = sorted({e['code'] for e in model['entries'] if e['code'] not in codes or not codes[e['code']]['active']})
    missing_slots = sorted({e['slot'] for e in model['entries'] if e['slot'] not in slots})
    return missing_codes, missing_slots


def _check_new(model):
    """Problemi che impedirebbero di creare la nuova struttura: la conferma li rifiuta già in anteprima."""
    problems = []
    try:
        cfg = _new_center_config(model)
    except Invalid as exc:
        return [f'Parametri della nuova struttura non validi: {exc.message}']
    if len(cfg['roles']) >= 50:
        dropped = [p['role'] for p in model['people'] if p['role'] and p['role'] not in cfg['roles']]
        if dropped:
            problems.append(f'Troppi ruoli nel file: {len(set(dropped))} ruoli diventano «ALTRO» (il ruolo originale resta in nota).')
    for p in model['people']:
        if p['proposal'] and _proposal_data(p, cfg) is None:
            problems.append(f'Proposta economica di «{p["name"]}» non valida: non viene importata.')
    return problems


def _target_problem(con, model, cid):
    """Perché il mese non può essere aggiunto alla struttura (stringa vuota se tutto va bene)."""
    row = centers.row(con, cid)
    if fold(row['name']) != fold(model['center']):
        return 'la struttura non ha lo stesso nome del file'
    if not row['active']:
        return 'struttura disattivata'
    state = months.get(con, cid, model['month'])
    if state['closed']:
        return 'mese già chiuso'
    if approvals.workflow(con, cid, model['month'])['status'] in approvals.FROZEN:
        return 'mese inviato in approvazione'
    first, last = months.bounds(model['month'])
    if con.execute('SELECT 1 FROM entries WHERE center_id=? AND day>=? AND day<=? LIMIT 1', (cid, first, last)).fetchone():
        return 'il mese contiene già registrazioni'
    if con.execute('SELECT 1 FROM workload WHERE center_id=? AND day>=? AND day<=? LIMIT 1', (cid, first, last)).fetchone():
        return 'il mese contiene già pazienti per fascia'
    cfg, _ = months.configuration(con, cid, state)
    missing_codes, missing_slots = _missing(model, cfg)
    if missing_codes:
        return f'mancano le causali {", ".join(missing_codes)} nei parametri'
    if missing_slots:
        return f'mancano le fasce {", ".join(missing_slots)} nei parametri'
    if any(e['external'] for e in model['entries']) and EXTERNAL_SITE not in cfg['sites']:
        return f'manca la sede «{EXTERNAL_SITE}» nei parametri'
    existing = {}
    for person in months.people(con, cid):
        existing.setdefault(fold(person['name']), []).append(person)
    inactive = [p['name'] for p in model['people']
                if existing.get(fold(p['name'])) and not any(x['active'] for x in existing[fold(p['name'])])]
    if inactive:
        return 'persone disattivate con lo stesso nome: ' + ', '.join(inactive[:5]) + ('…' if len(inactive) > 5 else '')
    return ''


def _targets(con, model):
    """Strutture esistenti con lo stesso nome del file e stato del mese da importare."""
    out = []
    wanted = fold(model['center'])
    for row in con.execute('SELECT id, name, code FROM centers ORDER BY name COLLATE NOCASE'):
        if fold(row['name']) != wanted:
            continue
        reason = _target_problem(con, model, row['id'])
        out.append(dict(id=row['id'], name=row['name'], code=row['code'], importable=not reason, reason=reason))
    return out


def _already(con, digest):
    found = con.execute('SELECT i.center_id, i.month, i.at, c.name FROM imports i JOIN centers c ON c.id=i.center_id '
                        'WHERE i.hash=? AND c.active=1', (digest,)).fetchone()
    return dict(center_id=found['center_id'], month=found['month'], at=found['at'], center=found['name']) if found else None


def preview(db, actor, data):
    with db.read() as con:
        actor = users.reload(con, actor)
        require(actor, 'import.excel')
    model = read_model(data)
    with db.read() as con:
        targets = _targets(con, model)
        already = _already(con, model['hash'])
    blocking = _check_new(model)
    key = new_id()
    _pending_put(db, key, dict(owner=actor.id, created=time.time(), model=model))
    counts = {}
    for e in model['entries']:
        counts[e['person_id']] = counts.get(e['person_id'], 0) + 1
    return dict(key=key, center=model['center'], month=model['month'], people=len(model['people']),
                entries=len(model['entries']), external=sum(e['external'] for e in model['entries']),
                holiday_entries=sum(e['holiday'] for e in model['entries']),
                warnings=model['warnings'], notes=model['notes'], blocking=blocking, hash=model['hash'],
                proposals=sum(p['proposal'] is not None for p in model['people']),
                skipped=model['skipped'][:MAX_SKIPPED_LISTED], skipped_total=len(model['skipped']),
                skipped_shown=min(len(model['skipped']), MAX_SKIPPED_LISTED),
                workload_days=len({w['day'] for w in model['workload']}), holidays=model['holidays'],
                parameters=model['parameters'], collaborators=len(model['collaborators']),
                groups={g: sum(p['group'] == g for p in model['people']) for g in ('dipendente', 'consulente', '')},
                persons=[dict(name=p['name'], role=p['role'], contract=p['contract'], group=GROUP_LABELS[p['group']],
                              rows=p['rows'], entries=counts.get(p['id'], 0), proposal=p['proposal'] is not None,
                              collaborator=collaborator_summary(p['collaborator']) if p.get('collaborator') else '',
                              billing=p.get('billing', '')) for p in model['people']],
                targets=targets, already_imported=already)


# --- Scrittura -------------------------------------------------------------------------------

def _insert_entries(con, actor, cid, model, ids, cfg, rules_version):
    missing_codes, missing_slots = _missing(model, cfg)
    if missing_codes:
        raise Invalid(f'La struttura non ha le causali {", ".join(missing_codes)}: aggiungerle nei parametri oppure importare in una '
                      'struttura nuova.')
    if missing_slots:
        raise Invalid('La struttura non ha le fasce del modello: importare in una struttura nuova.')
    labels = {c['id']: c for c in cfg['codes']}
    slots = {s['id'] for s in cfg['slots'] if s['active']}
    now = stamp()
    for e in model['entries']:
        code_cfg = labels[e['code']]
        review = e['review'] or (REVIEW_COLOR if e['unknown_color'] else (REVIEW_SITE if e['external'] else ''))
        con.execute('''INSERT INTO entries(id,center_id,person_id,day,slot,layer,code,kind,label,start,end,pause,overnight,site,
                       holiday,credit,note,source,review,rules_version,version,updated_at,updated_by)
                       VALUES(?,?,?,?,?,'actual',?,?,?,'','',0,0,?,?,?,?,?,?,?,1,?,?)''',
                    (new_id(), cid, ids[e['person_id']], e['day'], e['slot'], e['code'], code_cfg['kind'], code_cfg['label'],
                     EXTERNAL_SITE if e['external'] else '', int(e['holiday']),
                     code_cfg['credit_minutes'] if code_cfg['kind'] == 'absence' else 0,
                     f'Importato dalla cella {e["cell"]}', f'excel:{e["cell"]}', review, rules_version, now, actor.username))
    for w in model['workload']:
        if w['slot'] not in slots:
            continue
        con.execute('''INSERT INTO workload(center_id,day,slot,ordinary,isolated,updated_at,updated_by) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(center_id,day,slot) DO UPDATE SET ordinary=excluded.ordinary, isolated=excluded.isolated,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (cid, w['day'], w['slot'], w['ordinary'], w['isolated'], now, actor.username))
    dropped = []
    for p in model['people']:
        if not p['proposal']:
            continue
        exists = con.execute('SELECT 1 FROM agreements WHERE center_id=? AND month=? AND person_id=?',
                             (cid, model['month'], ids[p['id']])).fetchone()
        if exists:
            continue
        data = _proposal_data(p, cfg)
        if data is None:
            dropped.append(p['name'])
            continue
        con.execute('INSERT INTO agreements(center_id,month,person_id,data,source,version,updated_at,updated_by) '
                    'VALUES(?,?,?,?,?,1,?,?)', (cid, model['month'], ids[p['id']], dumps(data), agreement_source(p, model), now,
                                                actor.username))
    return dropped


def _profile_relationship(con, actor, model, ids, only_new):
    """Fascicolo dei collaboratori riconosciuti nel file: tipo di rapporto e chi emette la fattura."""
    from . import hr
    for p in model['people']:
        if p['group'] != 'consulente' or p['id'] not in ids or (only_new is not None and ids[p['id']] not in only_new):
            continue
        current = hr.profile(con, ids[p['id']])
        fields = dict(current['fields'])
        if fields.get('relationship'):
            continue
        billing = p.get('billing', '')
        fields['relationship'] = 'associazione' if billing and billing.casefold().startswith(('ass', 'coop')) else 'professionista'
        if billing and not fields.get('billing_entity'):
            fields['billing_entity'] = billing[:150]
        con.execute('''INSERT INTO profiles(person_id,stage,fields,custom,version,updated_at,updated_by) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(person_id) DO UPDATE SET fields=excluded.fields, version=excluded.version,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (ids[p['id']], current['stage'], dumps(fields), dumps(current['custom']), current['version'] + 1, stamp(),
                     actor.username))


def _create_center(con, actor, model):
    cfg = _new_center_config(model)
    cid = new_id()
    code = 'IMPORT-' + model['hash'][:12].upper()
    con.execute('INSERT INTO centers(id,name,code,active,config_version,version,created_at) VALUES(?,?,?,1,1,1,?)',
                (cid, model['center'], code, stamp()))
    con.execute('INSERT INTO center_configs(center_id,version,data,note,created_at,created_by) VALUES(?,1,?,?,?,?)',
                (cid, dumps(cfg), 'Creati dall’importazione del modello Excel', stamp(), actor.username))
    ids = {}
    for p in model['people']:
        role = p['role'] if p['role'] in cfg['roles'] else 'ALTRO'
        ids[p['id']] = people.insert(con, actor, cid, dict(name=p['name'], role=role, registration='', active=True,
                                                           contract=p['contract'], note=person_note(p, cfg['roles'])))
    con.execute('INSERT INTO months(center_id,month,rules_version,verified,closed,note,version,updated_at,updated_by) '
                'VALUES(?,?,1,0,0,?,1,?,?)', (cid, model['month'], _month_note(model), stamp(), actor.username))
    dropped = _insert_entries(con, actor, cid, model, ids, cfg, 1)
    _profile_relationship(con, actor, model, ids, None)
    return cid, len(ids), 0, dropped


def _add_to_center(con, actor, model, cid):
    problem = _target_problem(con, model, cid)
    if problem:
        raise Invalid(f'Il mese non può essere aggiunto a questa struttura: {problem}. Scegliere un’altra destinazione o creare '
                      'una nuova struttura.')
    state = months.get(con, cid, model['month'])
    cfg, _ = months.configuration(con, cid, state)
    existing = {}
    for person in sorted(months.people(con, cid), key=lambda p: (not p['active'], p['name'].casefold())):
        existing.setdefault(fold(person['name']), person)  # a parità di nome vale la persona attiva, poi la prima in ordine alfabetico
    ids, created, new_ids = {}, 0, set()
    for p in model['people']:
        match = existing.get(fold(p['name']))
        if match:
            ids[p['id']] = match['id']
            continue
        role = p['role'] if p['role'] in cfg['roles'] else 'ALTRO' if 'ALTRO' in cfg['roles'] else cfg['roles'][0]
        ids[p['id']] = people.insert(con, actor, cid, dict(name=p['name'], role=role, registration='', active=True,
                                                           contract=p['contract'], note=person_note(p, cfg['roles'])))
        new_ids.add(ids[p['id']])
        created += 1
    state = months.ensure(con, cid, model['month'], actor)
    note = '\n'.join(x for x in (state['note'], _month_note(model)) if x)[:2000]
    months.update(con, cid, model['month'], actor, note=note)
    dropped = _insert_entries(con, actor, cid, model, ids, cfg, state['rules_version'])
    _profile_relationship(con, actor, model, ids, new_ids)
    return cid, len(ids), created, dropped


def confirm(db, actor, key, target=None):
    pending = _pending_get(db, key)
    if not pending or pending['owner'] != actor.id:
        raise NotFound('Anteprima non valida o scaduta: caricare di nuovo il file.')
    model = pending['model']
    with db.read() as con:
        require(users.reload(con, actor), 'import.excel')
        done = _already(con, model['hash'])
        if done:
            if target and target != done['center_id']:
                raise Invalid(f'File già importato nella struttura «{done["center"]}»: scegliere quella struttura oppure modificare il file.')
            return dict(center_id=done['center_id'], month=done['month'], already_imported=True)
        # Tutti i controlli prima del backup: una conferma rifiutata non deve lasciare copie inutili.
        if target:
            problem = _target_problem(con, model, target)
            if problem:
                raise Invalid(f'Il mese non può essere aggiunto a questa struttura: {problem}.', field='target')
        else:
            problems = [p for p in _check_new(model) if p.startswith('Parametri')]
            if problems:
                raise Invalid(problems[0])
    backups.create(db, 'prima-importazione-excel')
    with db.write() as con:
        actor = users.reload(con, actor)
        require(actor, 'import.excel')
        if _already(con, model['hash']):
            raise Invalid('File già importato.')
        if target:
            cid, total, created, dropped = _add_to_center(con, actor, model, target)
            action = 'Importazione del modello Excel in una struttura esistente'
        else:
            cid, total, created, dropped = _create_center(con, actor, model)
            action = 'Importazione del modello Excel'
        con.execute('INSERT OR REPLACE INTO imports(hash,center_id,month,at) VALUES(?,?,?,?)', (model['hash'], cid, model['month'], stamp()))
        audit.record(con, actor, action, cid, entity='import', entity_id=model['hash'][:16],
                     after=dict(hash=model['hash'], people=total, new_people=created, entries=len(model['entries']),
                                skipped=len(model['skipped']), workload=len(model['workload']), warnings=model['warnings'],
                                dropped_proposals=dropped,
                                skipped_cells=[(s['cell'], s['value'], s['person'], s['reason']) for s in model['skipped'][:500]]))
    _pending_pop(db, key)
    return dict(center_id=cid, month=model['month'], already_imported=False, people=total, new_people=created,
                skipped=len(model['skipped']), dropped_proposals=dropped)


# --- API ------------------------------------------------------------------------------------

@route('POST', '/api/import/preview', cap='import.excel', step_up=True)
def api_preview(ctx):
    return preview(ctx.db, ctx.user, ctx.req.raw(MAX_FILE))


@route('POST', '/api/import/confirm', cap='import.excel', step_up=True)
def api_confirm(ctx):
    target = ctx.body.get('target')
    if target is not None and not isinstance(target, str):
        raise Invalid('Struttura di destinazione non valida.', field='target')
    return confirm(ctx.db, ctx.user, str(ctx.body.get('key') or ''), target or None)
