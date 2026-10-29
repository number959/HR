"""Importazione del modello Excel delle presenze (Sodav): lettura OOXML, senza Excel e senza macro.

L'anteprima non scrive nulla e mostra tutto ciò che verrà importato e ciò che resta fuori.
La conferma crea una nuova struttura oppure aggiunge il mese a una struttura esistente con lo
stesso nome (il mese deve essere vuoto e aperto). Le proposte economiche riconosciute dalle
formule restano da confermare. Lo stesso file non si importa due volte.

Letto dal file: persone (con sezione dipendenti/collaboratori), registrazioni del mese con sede
esterna (sfondo giallo) e festivo (carattere rosso), pazienti per fascia, festività elencate,
pazienti di riferimento per infermiere e medico, formule economiche (anche con i festivi CCNL),
riepilogo dei compensi del foglio «Collaboratori» (senza IBAN, solo come nota).
Le celle non riconosciute non bloccano l'importazione: vengono elencate e vanno completate a mano.
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

from . import agreements, approvals, audit, backups, centers, months, people, rules, users
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
REVIEW_DUPLICATE = 'Registrazione presente due volte nel file con codici diversi: verificare.'
WORK = {'m': 'Mattina', 'p': 'Pomeriggio', 's': 'Serale', 'n': 'Notte'}
ABSENCE_CODES = [c for c, _ in rules.ABSENCES] + ['R']
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
GRID_FIRST, GRID_LAST = 4, 34  # colonne D..AH: i 31 giorni del mese
# Intestazioni di sezione del modello (colonna A): distinguono dipendenti e collaboratori a prestazione.
CONSULTANT_WORDS = ('prestazion', 'consulent', 'volontar', 'altri centri', 'fattura')
EMPLOYEE_WORDS = ('dipendent',)
IGNORED_HEADERS = ('total', 'note', 'pazienti', 'turno', 'rapporto', 'efficienza', 'centro', 'qualifica', 'legenda')
PATIENT_SLOTS = {'mattina': 'm', 'pomeriggio': 'p', 'serale': 's', 'sera': 's', 'notte': 'n'}
GROUP_LABELS = {'dipendente': 'Personale dipendente', 'consulente': 'Collaboratori a prestazione', '': 'Sezione non indicata'}
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
        float(str(text).replace(',', '.'))
        return True
    except ValueError:
        return False


def money(value):
    return f'{value:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def recognized_agreement(cells, r):
    """Riconosce le combinazioni di formule economiche note del modello (nessun codice eseguito).

    Varianti accettate: base «tutti i turni» (AV=AT) o «eccedenza» (AV=AT-X3), tariffe feriale e festiva,
    detrazione fissa facoltativa e, nei modelli più recenti, i festivi già riconosciuti dal CCNL (-tariffa*BB).
    """
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
    number = r'([0-9]+(?:\.[0-9]+)?)'
    weekday = re.fullmatch(fr'IF\(AW{end}="","",AW{end}\*{number}\)', ax)
    holiday = re.fullmatch(fr'IF\(AY{end}="","",AY{end}\*{number}\)', az)
    deduction = re.fullmatch(fr'IF\(AX{end}="","",AX{end}\+AZ{end}(?:-{number})?(?:-{number}\*BB{end})?\)', ba)
    if not (weekday and holiday and deduction):
        return None
    ccnl_rate = float(deduction[2] or 0)
    ccnl_count = 0
    if ccnl_rate:
        # COUNTA(BB{r}:BC{r+1}): i festivi già riconosciuti sono le celle compilate dall'ufficio in quel riquadro.
        ccnl_count = sum(1 for col in ('BB', 'BC') for row in (r, r + 1)
                         if str(cells.get(f'{col}{row}', {}).get('value', '')).strip())
    counted = [c for c, _ in rules.ABSENCES if c != 'RC' or at == expected]
    return dict(basis=basis, weekday_rate=float(weekday[1]), holiday_rate=float(holiday[1]),
                fixed_deduction=float(deduction[1] or 0), ccnl_rate=ccnl_rate, ccnl_count=ccnl_count,
                counted_absences=counted)


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


EMPLOYMENT = re.compile(r'\b(T\.?\s?I\.?|T\.?\s?D\.?|TEMPO|FULL|PART|P\.?\s?T\.?|INDETERMINATO|DETERMINATO)\b', re.I)


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
    columns = set()
    for addr, c in cells.items():
        if str(c['value']).strip().casefold().startswith('festivit'):
            letters, row = split_address(addr)
            columns.add((letters, row))
    for letters, row in columns:
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
    for m in re.finditer(r'([A-Z]{1,2})(\d+):([A-Z]{1,2})(\d+)', cells.get('X3', {}).get('formula_text', '')):
        c1, r1, c2, r2 = m.groups()
        if c1 == c2 and 0 < int(r2) - int(r1) < 200:
            for r in range(int(r1), int(r2) + 1):
                raw = str(value(f'{c1}{r}')).strip()
                if raw and is_number(raw):
                    found.append(raw)
    out = []
    for raw in found:
        try:
            iso = excel_date(raw)
        except (ValueError, OverflowError):
            continue
        if iso[:4].isdigit() and 1990 <= int(iso[:4]) <= 2100:
            out.append(iso)
    return sorted(set(out))


def _patients(cells, value, rows, month, length, warnings):
    """Pazienti per fascia e giorno dalle righe «Pazienti turno …» (le righe «Contumacia» sono gli isolati)."""
    counts = {}
    conflicts = set()
    for r in rows:
        label = str(value(f'A{r}')).strip().casefold()
        m = re.match(r'pazienti\s+turno\s+(\w+)', label)
        if not m or m.group(1) not in PATIENT_SLOTS:
            continue
        slot = PATIENT_SLOTS[m.group(1)]
        field = 'isolated' if 'contumac' in label else 'ordinary'
        for d in range(1, min(31, length) + 1):
            raw = str(value(column(d + 3) + str(r))).strip()
            if not raw or not is_number(raw):
                continue
            number = int(round(float(raw.replace(',', '.'))))
            if number < 0:
                continue
            key = (f'{month}-{d:02d}', slot)
            current = counts.setdefault(key, {})
            if field in current and current[field] != number:
                conflicts.add(key[0])
            current.setdefault(field, number)
    if conflicts:
        warnings.append(f'Pazienti per fascia indicati due volte con valori diversi in {len(conflicts)} giorni: '
                        'viene usata la prima tabella del file.')
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

        out.append(dict(name=' '.join(name.split()), role=value(f'{columns.get("role", "A")}{r}'),
                        weekday_shifts=number('shifts'), holiday_shifts=number('shifts', 1) if shifts else None,
                        gross=number('gross'), withholding=number('withholding'), pension=number('pension'),
                        net=number('net'), note=value(f'{columns["note"]}{r}') if 'note' in columns else '', row=r))
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
    except (KeyError, ET.ParseError):
        raise Invalid('Struttura del file Excel non riconosciuta.') from None
    prop = book.find('s:workbookPr', NS)
    if prop is not None and prop.get('date1904') in ('1', 'true'):
        raise Invalid('Calendario Excel 1904 non supportato.')
    sheets = {}
    for sheet in book.findall('s:sheets/s:sheet', NS):
        cells = {}
        target = rels.get(sheet.get(REL))
        if not target or target not in archive.namelist():
            continue
        for c in xml(target).findall('.//s:sheetData/s:row/s:c', NS):
            node = c.find('s:v', NS)
            value = node.text if node is not None else ''
            if c.get('t') == 's':
                value = strings[int(value)] if value and value.isdigit() and int(value) < len(strings) else ''
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
    except (TypeError, ValueError, OverflowError):
        raise Invalid('Mese non leggibile nella cella O6.') from None
    center = ' '.join(str(value('C6')).split())
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
        style = sheet.get(addr, {}).get('style', 0)
        x = xfs[style] if xfs is not None and style < len(xfs) else None
        if x is None:
            return {}, {}
        fill = fills[int(x.get('fillId', 0))].find('s:patternFill/s:fgColor', NS)
        font = fonts[int(x.get('fontId', 0))].find('s:color', NS)
        return (dict(fill.attrib) if fill is not None else {}), (dict(font.attrib) if font is not None else {})

    refs = sheets.get('Foglio1', {})
    yellow = colors('I2', refs)[0]
    red_font = colors('M2', refs)[1]
    warnings = []
    year, mon = int(month[:4]), int(month[5:])
    length = calendar.monthrange(year, mon)[1]
    file_holidays = [excel_date(c['value']) for a, c in sheets.get('Festività', {}).items()
                     if a != 'A1' and str(c['value']).replace('.', '', 1).isdigit()]
    file_holidays = sorted(set(file_holidays + _holiday_dates(cells, value)))
    national = [d for d, _ in rules.italian_holidays(year)]
    holidays = sorted(set(national) | {h for h in file_holidays if h.startswith(month[:4])})
    other_years = sorted({h[:4] for h in file_holidays if not h.startswith(month[:4])})
    if file_holidays and not any(h.startswith(month[:4]) for h in file_holidays):
        warnings.append(f'Il file elenca festività di altri anni ({", ".join(other_years)}): per il mese vengono usate le festività '
                        f'nazionali del {year}. Il patrono locale va aggiunto nei parametri della struttura.')
    elif not file_holidays:
        warnings.append(f'Il file non elenca festività: vengono usate le festività nazionali del {year}. '
                        'Il patrono locale va aggiunto nei parametri della struttura.')
    elif other_years:
        warnings.append(f'Oltre alle festività del {year}, il file ne elenca di altri anni ({", ".join(other_years)}): ignorate.')
    warnings.append('Il modello contiene conteggi per fascia m/p/s senza orari: le ore restano da inserire.')
    actual_days = sum(date(year, mon, d).weekday() != 6 and f'{month}-{d:02d}' not in holidays for d in range(1, length + 1))
    if str(value('X3')).strip().isdigit() and int(value('X3')) != actual_days:
        warnings.append(f'Calendario da verificare: X3 contiene {value("X3")} giorni; nel mese reale (lunedì–sabato, festività '
                        f'presenti) risultano {actual_days}. Il portale usa le date reali.')
    broken = sum('#REF!' in c['formula_text'] for s in sheets.values() for c in s.values())
    if broken:
        warnings.append(f'Il file contiene {broken} formule con riferimenti interrotti: i risultati derivati non vengono importati.')
    if any('COUNTIF(E' in c['formula_text'].upper() and ':AI' in c['formula_text'].upper() and '"ROL"' in c['formula_text'].upper()
           for c in cells.values()):
        warnings.append('Alcune formule ROL usano E:AI invece della griglia D:AH: i contatori del portale leggono tutte le celle '
                        'del mese.')
    if any('CONTACELLEPERCOLORE' in c['formula_text'].upper() for c in cells.values()):
        warnings.append('I conteggi per colore del file dipendono da macro: il portale legge direttamente i colori delle celle '
                        '(giallo = fuori sede, carattere rosso = festivo).')

    parameters = {}
    for addr, key in (('AJ4', 'nurse_reference'), ('AM4', 'doctor_reference')):
        raw = str(value(addr)).strip()
        if raw and is_number(raw) and 0 < float(raw.replace(',', '.')) <= 1000:
            parameters[key] = float(raw.replace(',', '.'))
    for addr, key in (('AD4', 'stations'), ('AG4', 'isolation_stations')):
        raw = str(value(addr)).strip()
        if raw and is_number(raw):
            parameters[key] = int(float(raw.replace(',', '.')))

    persons, entries, skipped = [], [], []
    unknown_cells = []
    by_name = {}
    seen_slots = {}
    section = ''
    rows = sorted({split_address(a)[1] for a in cells})
    for r in rows:
        first = str(value(f'A{r}')).strip()
        trio = (str(value(f'C{r}')).strip().lower(), str(value(f'C{r + 1}')).strip().lower(), str(value(f'C{r + 2}')).strip().lower())
        if trio != ('m', 'p', 's'):
            if first and not str(value(f'B{r}')).strip() and (first.casefold().startswith('total')
                                                            or not any(first.casefold().startswith(w) for w in IGNORED_HEADERS)):
                section = _section_of(first, section)
            continue
        name = ' '.join(str(value(f'B{r}')).split())
        if not name:
            continue
        contract = ' '.join(str(value(f'B{r + 1}')).split())
        role = first or ''
        note_lines = []
        key = fold(name)
        person = by_name.get(key)
        if person is None:
            group = _group_of(section, contract)
            person = dict(id=f'row-{r}', name=name, role=role, contract=contract, group=group, rows=[r], source_row=r,
                          agreement_note=' | '.join(str(value(f'AU{r + j}')).strip() for j in range(3) if str(value(f'AU{r + j}')).strip()),
                          proposal=recognized_agreement(cells, r), extra_roles=[], collaborator=None)
            if group == 'consulente' and contract and not EMPLOYMENT.search(contract):
                person['billing'] = contract  # per i collaboratori la riga sotto il nome indica chi fattura
                person['contract'] = 'Prestazione / consulenza'
            by_name[key] = person
            persons.append(person)
        else:
            person['rows'].append(r)
            if role and role != person['role']:
                person['extra_roles'].append(f'{role} (righe {r}-{r + 2})')
            if person['proposal'] is None:
                person['proposal'] = recognized_agreement(cells, r)
            extra_note = ' | '.join(str(value(f'AU{r + j}')).strip() for j in range(3) if str(value(f'AU{r + j}')).strip())
            if extra_note:
                person['agreement_note'] = ' | '.join(x for x in (person['agreement_note'], extra_note) if x)
            warnings.append(f'«{name}» compare due volte nel registro (righe {person["source_row"]} e {r}): le registrazioni sono '
                            'state unite in una sola persona.')
        for offset, slot in enumerate(('m', 'p', 's')):
            for d in range(1, 32):
                addr = column(d + 3) + str(r + offset)
                raw = str(value(addr)).strip()
                if not raw:
                    continue
                skip = dict(cell=addr, value=raw[:40], person=name, day=f'{month}-{min(d, length):02d}', slot=slot)
                if cells[addr]['formula']:
                    skipped.append(dict(skip, reason='la cella contiene una formula'))
                    continue
                if d > length:
                    skipped.append(dict(skip, reason='giorno oltre la fine del mese'))
                    continue
                try:
                    code = normalized_code(raw)
                except ValueError:
                    skipped.append(dict(skip, reason='causale non riconosciuta'))
                    continue
                if code in WORK and code != slot:
                    skipped.append(dict(skip, reason=f'codice della fascia «{WORK[code]}» nella riga «{WORK[slot]}»'))
                    continue
                slot_key = (person['id'], f'{month}-{d:02d}', slot)
                previous = seen_slots.get(slot_key)
                if previous is not None:
                    if previous['code'] != code:
                        previous['review'] = REVIEW_DUPLICATE
                        skipped.append(dict(skip, reason=f'doppione con codice diverso (già importato da {previous["cell"]})'))
                    continue
                bg, fg = colors(addr)
                color = rgb(bg)
                external = bool(yellow and bg == yellow) or color in ('FFFF00', '00FF00')
                holiday = bool(red_font and fg == red_font)
                unknown = bool(bg) and not external and color not in ('FFFFFF', '000000')
                if unknown:
                    unknown_cells.append(addr)
                entry = dict(person_id=person['id'], day=f'{month}-{d:02d}', slot=slot, code=code, external=external,
                             holiday=holiday, unknown_color=unknown, cell=addr, review='')
                seen_slots[slot_key] = entry
                entries.append(entry)
        if person['group']:
            note_lines.append(f'Sezione del file: {GROUP_LABELS[person["group"]]}')
        person.setdefault('notes', note_lines)
    if unknown_cells:
        shown = ', '.join(unknown_cells[:12]) + (', …' if len(unknown_cells) > 12 else '')
        warnings.append(f'Sfondo non riconosciuto in {len(unknown_cells)} celle ({shown}): controllare la sede.')
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
        warnings.append('Il foglio «Collaboratori» viene letto solo come promemoria (turni, lordo, ritenute, netto) nelle note delle '
                        'persone e degli accordi: gli importi, le trattenute e l’IBAN non diventano regole di calcolo.')
    if unmatched:
        warnings.append('Nel foglio «Collaboratori» compaiono nominativi assenti dal registro: ' + ', '.join(unmatched[:10])
                        + ('…' if len(unmatched) > 10 else '') + '.')
    mismatched = [p['name'] for p in persons if p.get('proposal_matches_sheet') is False]
    if mismatched:
        warnings.append('Per alcuni collaboratori il lordo del foglio «Collaboratori» non coincide con le tariffe generiche delle formule '
                        f'({", ".join(mismatched[:6])}{"…" if len(mismatched) > 6 else ""}): confermare gli accordi con le tariffe reali.')
    warnings.append('Le formule economiche riconosciute diventano proposte individuali da confermare negli accordi del mese.')
    return dict(hash=hashlib.sha256(data).hexdigest(), center=center, month=month, people=persons, entries=entries,
                holidays=holidays, file_holidays=file_holidays, warnings=list(dict.fromkeys(warnings)), skipped=skipped,
                workload=workload, parameters=parameters, collaborators=collaborators)


def person_note(p, cfg_roles=None):
    lines = [f'Importato dal file Excel (riga {p["source_row"]}' + (f', unita con righe {", ".join(str(r) for r in p["rows"][1:])}' if len(p['rows']) > 1 else '') + ')']
    lines += p.get('notes', [])
    if p.get('billing'):
        lines.append(f'Fatturazione / ente indicato nel file: {p["billing"]}')
    if p['extra_roles']:
        lines.append('Altri ruoli nel file: ' + ', '.join(p['extra_roles']))
    if cfg_roles is not None and p['role'] and p['role'] not in cfg_roles:
        lines.append(f'Ruolo indicato nel file: {p["role"]}')
    if p['agreement_note']:
        lines.append(f'Accordi (colonna AU): {p["agreement_note"]}')
    if p.get('collaborator'):
        lines.append(collaborator_summary(p['collaborator']))
    return '\n'.join(lines)[:2000]


def agreement_source(p):
    text = f'Proposta dalle formule del file (riga {p["source_row"]}): da confermare'
    if p.get('collaborator'):
        text += '. ' + collaborator_summary(p['collaborator'])
        if p.get('proposal_matches_sheet') is False:
            text += ' → lordo diverso dalle tariffe delle formule: inserire le tariffe reali'
    return text[:1000]


def _targets(con, model):
    """Strutture esistenti con lo stesso nome del file e stato del mese da importare."""
    out = []
    wanted = fold(model['center'])
    for row in con.execute('SELECT id, name, code, active FROM centers ORDER BY name COLLATE NOCASE'):
        if fold(row['name']) != wanted:
            continue
        state = months.get(con, row['id'], model['month'])
        has_entries = con.execute('SELECT 1 FROM entries WHERE center_id=? AND day LIKE ? LIMIT 1',
                                  (row['id'], model['month'] + '-%')).fetchone() is not None
        frozen = approvals.workflow(con, row['id'], model['month'])['status'] in approvals.FROZEN
        if not row['active']:
            reason = 'struttura disattivata'
        elif state['closed']:
            reason = 'mese già chiuso'
        elif frozen:
            reason = 'mese inviato in approvazione'
        elif has_entries:
            reason = 'il mese contiene già registrazioni'
        else:
            reason = ''
        out.append(dict(id=row['id'], name=row['name'], code=row['code'], importable=not reason, reason=reason))
    return out


def preview(db, actor, data):
    with db.read() as con:
        actor = users.reload(con, actor)
        require(actor, 'import.excel')
    model = read_model(data)
    with db.read() as con:
        targets = _targets(con, model)
    key = new_id()
    with _LOCK:
        for k in [k for k, item in _PENDING.items() if time.monotonic() - item['created'] > PENDING_SECONDS]:
            _PENDING.pop(k)
        while len(_PENDING) >= 6:
            _PENDING.pop(next(iter(_PENDING)))
        _PENDING[key] = dict(owner=actor.id, created=time.monotonic(), model=model)
    counts = {}
    for e in model['entries']:
        counts[e['person_id']] = counts.get(e['person_id'], 0) + 1
    return dict(key=key, center=model['center'], month=model['month'], people=len(model['people']),
                entries=len(model['entries']), external=sum(e['external'] for e in model['entries']),
                holiday_entries=sum(e['holiday'] for e in model['entries']),
                warnings=model['warnings'], hash=model['hash'],
                proposals=sum(p['proposal'] is not None for p in model['people']),
                skipped=model['skipped'][:200], skipped_total=len(model['skipped']),
                workload_days=len({w['day'] for w in model['workload']}), holidays=model['holidays'],
                parameters=model['parameters'], collaborators=len(model['collaborators']),
                groups={g: sum(p['group'] == g for p in model['people']) for g in ('dipendente', 'consulente', '')},
                persons=[dict(name=p['name'], role=p['role'], contract=p['contract'], group=GROUP_LABELS[p['group']],
                              rows=p['rows'], entries=counts.get(p['id'], 0), proposal=p['proposal'] is not None,
                              collaborator=collaborator_summary(p['collaborator']) if p.get('collaborator') else '',
                              billing=p.get('billing', '')) for p in model['people']],
                targets=targets)


def _insert_entries(con, actor, cid, model, ids, cfg, rules_version):
    labels = {c['id']: c for c in cfg['codes']}
    slots = {s['id'] for s in cfg['slots']}
    missing = sorted({e['code'] for e in model['entries'] if e['code'] not in labels})
    if missing:
        raise Invalid(f'La struttura non ha le causali {", ".join(missing)}: aggiungerle nei parametri oppure importare in una '
                      'struttura nuova.')
    if any(e['slot'] not in slots for e in model['entries']):
        raise Invalid('La struttura non ha le fasce m/p/s del modello: importare in una struttura nuova.')
    now = stamp()
    for e in model['entries']:
        code_cfg = labels[e['code']]
        review = e['review'] or (REVIEW_COLOR if e['unknown_color'] else (REVIEW_SITE if e['external'] else ''))
        con.execute('''INSERT INTO entries(id,center_id,person_id,day,slot,layer,code,kind,label,start,end,pause,overnight,site,
                       holiday,credit,note,source,review,rules_version,version,updated_at,updated_by)
                       VALUES(?,?,?,?,?,'actual',?,?,?,'','',0,0,?,?,0,?,?,?,?,1,?,?)''',
                    (new_id(), cid, ids[e['person_id']], e['day'], e['slot'], e['code'], code_cfg['kind'], code_cfg['label'],
                     EXTERNAL_SITE if e['external'] else '', int(e['holiday']), f'Importato dalla cella {e["cell"]}',
                     f'excel:{e["cell"]}', review, rules_version, now, actor.username))
    for w in model['workload']:
        if w['slot'] not in slots:
            continue
        con.execute('''INSERT INTO workload(center_id,day,slot,ordinary,isolated,updated_at,updated_by) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(center_id,day,slot) DO UPDATE SET ordinary=excluded.ordinary, isolated=excluded.isolated,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (cid, w['day'], w['slot'], w['ordinary'], w['isolated'], now, actor.username))
    for p in model['people']:
        if not p['proposal']:
            continue
        exists = con.execute('SELECT 1 FROM agreements WHERE center_id=? AND month=? AND person_id=?',
                             (cid, model['month'], ids[p['id']])).fetchone()
        if exists:
            continue
        data = dict(agreements.proposal(cfg, None), **p['proposal'], confirmed=False)
        data = agreements.validate(data, cfg)
        con.execute('INSERT INTO agreements(center_id,month,person_id,data,source,version,updated_at,updated_by) '
                    'VALUES(?,?,?,?,?,1,?,?)', (cid, model['month'], ids[p['id']], dumps(data), agreement_source(p), now,
                                                actor.username))


def _month_note(model):
    text = '\n'.join(model['warnings'])
    if model['skipped']:
        text += '\nCelle non importate: ' + '; '.join(f'{s["cell"]} «{s["value"]}» ({s["person"]}, {s["reason"]})'
                                                     for s in model['skipped'][:40])
    return text[:2000]


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
    cfg = rules.defaults()
    cfg['holidays'] = sorted(set(model['holidays']))
    notes = [f'Creati dall’importazione del file Excel ({model["center"]}, {model["month"]}).']
    if model['parameters'].get('stations') is not None:
        notes.append(f'Posti dialisi accreditati indicati nel file: {model["parameters"]["stations"]}'
                     + (f', contumaciali: {model["parameters"]["isolation_stations"]}' if 'isolation_stations' in model['parameters'] else '') + '.')
    cfg['note'] = '\n'.join(notes + model['warnings'])[:4000]
    cfg['roles'] = list(dict.fromkeys(cfg['roles'] + [p['role'] or 'ALTRO' for p in model['people']]))[:50]
    for key in ('nurse_reference', 'doctor_reference'):
        if key in model['parameters']:
            cfg[key] = model['parameters'][key]
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
        ids[p['id']] = people.insert(con, actor, cid, dict(name=p['name'][:150], role=p['role'] or 'ALTRO', registration='',
                                                           active=True, contract=p['contract'][:150], note=person_note(p)))
    con.execute('INSERT INTO months(center_id,month,rules_version,verified,closed,note,version,updated_at,updated_by) '
                'VALUES(?,?,1,0,0,?,1,?,?)', (cid, model['month'], _month_note(model), stamp(), actor.username))
    _insert_entries(con, actor, cid, model, ids, cfg, 1)
    _profile_relationship(con, actor, model, ids, None)
    return cid, len(ids), 0


def _add_to_center(con, actor, model, cid):
    center = centers.row(con, cid)
    if not center['active']:
        raise Invalid('La struttura scelta è disattivata.')
    state = months.get(con, cid, model['month'])
    months.require_open(state)
    approvals.guard_month(con, actor, cid, model['month'])
    if con.execute('SELECT 1 FROM entries WHERE center_id=? AND day LIKE ? LIMIT 1', (cid, model['month'] + '-%')).fetchone():
        raise Invalid('Il mese contiene già registrazioni in questa struttura: importare in una struttura nuova oppure svuotare il mese.')
    cfg, _ = months.configuration(con, cid, state)
    existing = {}
    for person in months.people(con, cid):
        existing.setdefault(fold(person['name']), person)  # a parità di nome vale la prima (elenco alfabetico)
    ids, created, new_ids = {}, 0, set()
    for p in model['people']:
        match = existing.get(fold(p['name']))
        if match:
            ids[p['id']] = match['id']
            continue
        role = p['role'] if p['role'] in cfg['roles'] else 'ALTRO' if 'ALTRO' in cfg['roles'] else cfg['roles'][0]
        ids[p['id']] = people.insert(con, actor, cid, dict(name=p['name'][:150], role=role, registration='', active=True,
                                                           contract=p['contract'][:150], note=person_note(p, cfg['roles'])))
        new_ids.add(ids[p['id']])
        created += 1
    state = months.ensure(con, cid, model['month'], actor)
    note = '\n'.join(x for x in (state['note'], _month_note(model)) if x)[:2000]
    months.update(con, cid, model['month'], actor, note=note)
    _insert_entries(con, actor, cid, model, ids, cfg, state['rules_version'])
    _profile_relationship(con, actor, model, ids, new_ids)
    return cid, len(ids), created


def confirm(db, actor, key, target=None):
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
        if target:
            cid, total, created = _add_to_center(con, actor, model, target)
            action = 'Importazione del modello Excel in una struttura esistente'
        else:
            cid, total, created = _create_center(con, actor, model)
            action = 'Importazione del modello Excel'
        con.execute('INSERT INTO imports(hash,center_id,month,at) VALUES(?,?,?,?)', (model['hash'], cid, model['month'], stamp()))
        audit.record(con, actor, action, cid, entity='import', entity_id=model['hash'][:16],
                     after=dict(hash=model['hash'], people=total, new_people=created, entries=len(model['entries']),
                                skipped=len(model['skipped']), workload=len(model['workload']), warnings=model['warnings']))
    with _LOCK:
        _PENDING.pop(key, None)
    return dict(center_id=cid, month=model['month'], already_imported=False, people=total, new_people=created,
                skipped=len(model['skipped']))


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
