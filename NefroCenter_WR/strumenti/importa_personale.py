"""Importazione del «DATABASE PERSONALE» (cartella Excel del gruppo) in un archivio NefroCenter WR.

Legge il solo foglio DATABASE, una riga per persona e rapporto di lavoro, e crea o aggiorna:
- una struttura per ogni SOCIETÀ (codice ricavato dal nome), con i ruoli usati e le sedi esterne (LUOGO DI LAVORO);
- la rubrica della struttura (indirizzo, attività, referente);
- il modello di inserimento con i campi aggiuntivi per idoneità, formazione e scadenze di sicurezza (uguale per tutte);
- una persona per ogni coppia (società, persona) con il fascicolo compilato; le righe ripetute della stessa persona
  nella stessa società diventano contratti storici del personale di gruppo;
- il collegamento di gruppo fra le schede della stessa persona in società diverse (codice fiscale, altrimenti
  nome e data di nascita).

Uso (dalla cartella NefroCenter_WR):
  python3 strumenti/importa_personale.py --dati CARTELLA/data --chiave CARTELLA/private/server.key FILE.xlsx
      [--prova] [--json esito.json] [--limite N] [--utente admin]

L'archivio deve già esistere (manage.py init). Il file Excel non viene copiato né conservato. Il rapporto a video e in
JSON contiene solo conteggi e numeri di riga, mai nomi o codici fiscali. Legge solo le librerie standard di Python.
"""
import argparse
import io
import json
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent / 'gestionale'
sys.path.insert(0, str(ROOT))

from wr import app as factory, centers, hr, structures, users, workforce  # noqa: E402
from wr.errors import WRError  # noqa: E402
from wr.util import today  # noqa: E402

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
SHEET_NAME = 'DATABASE'
MAX_ROWS = 200_000

# Colonne riconosciute per intestazione (confronto senza accenti, apostrofi e maiuscole).
COLUMNS = {
    'societa': ('SOCIETA',), 'regione': ('REGIONE',), 'provincia': ('PROVINCIA',), 'citta': ('CITTA',),
    'indirizzo': ('INDIRIZZO',), 'attivita': ('TIPOLOGIA ATTIVITA',), 'ateco': ('CODICE ATECO',),
    'rischio': ('LIVELLO RISCHIO',), 'referente': ('REFERENTE',), 'ribaltamento': ('SOCIETA DI RIBALTAMENTO',),
    'luogo': ('LUOGO DI LAVORO',), 'nominativo': ('NOMINATIVO',), 'sesso': ('SESSO',), 'nascita': ('DATA DI NASCITA',),
    'luogo_nascita': ('LUOGO DI NASCITA',), 'cf': ('CODICE FISCALE',), 'residenza_citta': ('CITTA DI RESIDENZA',),
    'residenza_prov': ('PROVINCIA DI RESIDENZA',), 'email': ('E-MAIL', 'EMAIL'), 'contratto': ('TIPOLOGIA CONTRATTO',),
    'titolo': ('TITOLO DI STUDIO',), 'part_time': ('% PART TIME', 'PART TIME'), 'ccnl': ('CCNL',),
    'livello': ('LIVELLO CONTRATTUALE',), 'profilo': ('PROFILO',), 'mansione': ('MANSIONE',),
    'ore': ('ORE CONTRATTO H/W', 'ORE CONTRATTO'), 'inizio': ('DATA INIZIO GG/MM/AA', 'DATA INIZIO'),
    'fine': ('DATA FINE GG/MM/AA', 'DATA FINE'), 'stato': ('STATO CONTRATTO',),
    'ore_accreditamento': ('ORE ACCREDITAMENTO H/W', 'ORE ACCREDITAMENTO'), 'progetto': ('PROGETTO/BANDO',),
    'idoneita_visita': ('DATA VISITA IDONEITA SANITARIA',), 'idoneita_anni': ('DURATA IDONEITA SANITARIA (ANNI)',),
    'idoneita_scadenza': ('SCADENZA IDONEITA SANITARIA',), 'idoneita_copia': ('COPIA IDONEITA',),
    'prescrizioni': ('PRESCRIZIONI SANITARIE',), 'medico': ('MEDICO COMPETENTE',), 'medico_coord': ('MEDICO COORDINATO',),
    'fondo': ('FONDO FORMAZIONE',), 'form_generale': ('SCADENZA FORMAZIONE GENERALE',),
    'form_specifica': ('SCADENZA FORMAZIONE SPECIFICA',), 'preposto': ('SCADENZA PREPOSTO',),
    'antincendio': ('SCADENZA ANTINCENDIO',), 'rls': ('SCADENZA RLS',), 'primo_soccorso': ('SCADENZA PRIMO SOCCORSO',),
    'rspp': ('SCADENZA RSPP',), 'blsd': ('SCADENZA BLSD',), 'phtc': ('SCADENZA PHTC',),
    'legale_rapp': ('SCADENZA LEGALE RAPPRESENTANTE',),
}
REQUIRED = ('societa', 'nominativo')
DATE_KEYS = {'nascita', 'inizio', 'fine', 'idoneita_visita', 'idoneita_scadenza', 'form_generale', 'form_specifica', 'preposto',
             'antincendio', 'rls', 'primo_soccorso', 'rspp', 'blsd', 'phtc', 'legale_rapp'}

# Ruolo del registro ricavato dalla mansione: la prima regola che corrisponde vince.
# Le parole chiave sono scritte senza punti; quelle corte (fino a 4 lettere, senza spazi) devono essere parole intere.
ROLE_RULES = [
    ('DS', ('direttore sanitario',)),
    ('TEC', ('tecnico di laboratorio', 'tecn laboratorio', 'tecnico radiolog', 'tecnico rx', 'radiologo', 'neurofisiopat', 'biolog',
             'tecnico controllo', 'tecnico di qualit', 'analista contr', 'tecn di contr', 'capo-tecnico', 'vascolare', 'perfusion')),
    ('INF', ('infermier', 'infer', 'inf', 'caposala', 'capo sala', 'ostetric')),
    ('MED', ('medico', 'med', 'cardiolog', 'neurolog', 'diabetolog', 'nefrolog', 'anestes', 'chirurg')),
    ('OSS', ('oss', 'osa', 'ota', 'operatore sanitario', 'socio sanit', 'ausiliar', 'puericultr', 'assistente di poltrona')),
    ('FIS', ('fisioterap', 'logoped', 'psicolog', 'psicomotric', 'dietist', 'nutrizion', 'educat', 'musicoterap', 'ortottist',
             'assistente sociale', 'animat', 'istruttore', 'terapista')),
    ('FARM', ('farmacist', 'direttore farmacia', 'conf medicinali')),
    ('OPE', ('pulizie', 'operai', 'inscatolat', 'magazzin', 'manuten', 'autista', 'meccanic', 'portiere', 'guardaroba',
             'macchinista', 'generic', 'custode', 'usciere', 'cuoc', 'centralinist', 'ope', 'op spec')),
    ('AMM', ('amministr', 'impiegat', 'imp', 'segretar', 'contabil', 'add', 'addett', 'resp', 'responsabile', 'direttore', 'dir',
             'referente', 'manager', 'informatic', 'infomatic', 'ingegnere', 'sviluppat', 'statistic', 'ricerca', 'legale rappresentante',
             'dpo', 'specialist', 'plant', 'cup', 'quality', 'apprendista', 'appr', 'clinic assistant', 'coll amm', 'accettazione',
             'acc', 'capo serv')),
]
ROLE_LABELS = {'DS': 'Direttore sanitario', 'INF': 'Infermieri e ostetriche', 'MED': 'Medici', 'OSS': 'OSS/OSA/OTA',
               'TEC': 'Tecnici sanitari', 'FIS': 'Riabilitazione e supporto', 'FARM': 'Farmacia', 'OPE': 'Operativi e servizi',
               'AMM': 'Amministrativi e direzione', 'ALTRO': 'Altro o non indicato'}
RELATIONSHIPS = {'DIPENDENTE': 'dipendente', 'APPRENDISTATO': 'dipendente', 'DET. PER SOST.': 'dipendente',
                 'A CHIAMATA': 'dipendente', 'TIROCINIO': 'dipendente', 'CONSULENTE': 'professionista',
                 'COLL. OCC.': 'professionista', 'CO.CO.CO.': 'professionista', 'LEGALE RAPPRESENTANTE': 'altro',
                 'COMP. AMMINISTRATORE': 'altro'}
ENDED_STATES = {'TERMINATO'}
LEGAL_FORMS = ('S.C.A.R.L.', 'SCARL', 'S.R.L.S.', 'SRLS', 'S.R.L.', 'SRL', 'S.P.A.', 'SPA', 'S.A.S.', 'SAS', 'S.N.C.', 'SNC',
               'SOC. CONSORTILE', 'SOC. COOP.', 'SOC.', 'COOP.', 'COOP', 'ONLUS', 'ETS', 'A R.L.', 'ARL')
PARTICLES = {'di', 'de', 'del', 'della', 'dello', 'dei', 'degli', 'delle', 'da', 'dal', 'dalla', 'la', 'lo', 'le', 'li', "d'",
             'van', 'von', 'mc', 'mac', 'san', 'santa', 'lu'}
CF = re.compile(r'[A-Z]{6}[0-9A-Z]{2}[A-Z][0-9A-Z]{2}[A-Z][0-9A-Z]{3}[A-Z]')

# Campi aggiuntivi del fascicolo (al massimo 40): le scadenze di sicurezza e sanitarie del database.
CUSTOM_FIELDS = [
    ('attivita', 'Tipologia di attività della società', 'text'), ('rischio', 'Livello di rischio', 'text'),
    ('ateco', 'Codice ATECO', 'text'), ('ribaltamento', 'Società di ribaltamento', 'text'),
    ('profilo', 'Profilo di rischio della mansione', 'text'), ('sesso', 'Sesso', 'text'),
    ('titolo_studio', 'Titolo di studio', 'text'), ('ore_accreditamento', 'Ore di accreditamento settimanali', 'number'),
    ('progetto', 'Progetto o bando', 'text'),
    ('idoneita_visita', 'Idoneità sanitaria: data della visita', 'date'), ('idoneita_stato', 'Idoneità sanitaria: stato', 'text'),
    ('idoneita_durata_anni', 'Idoneità sanitaria: durata in anni', 'number'), ('idoneita_scadenza', 'Idoneità sanitaria: scadenza', 'date'),
    ('idoneita_copia', 'Copia dell’idoneità in archivio', 'boolean'), ('prescrizioni', 'Prescrizioni sanitarie', 'text'),
    ('medico_competente', 'Medico competente', 'text'), ('medico_coordinato', 'Medico coordinato', 'text'),
    ('fondo_formazione', 'Fondo per la formazione', 'text'),
    ('formazione_generale_scadenza', 'Formazione generale: scadenza', 'date'), ('formazione_generale_stato', 'Formazione generale: stato', 'text'),
    ('formazione_specifica_scadenza', 'Formazione specifica: scadenza', 'date'), ('formazione_specifica_stato', 'Formazione specifica: stato', 'text'),
    ('preposto_scadenza', 'Preposto: scadenza', 'date'), ('preposto_stato', 'Preposto: stato', 'text'),
    ('antincendio_scadenza', 'Antincendio: scadenza', 'date'), ('antincendio_stato', 'Antincendio: stato', 'text'),
    ('rls_scadenza', 'RLS: scadenza', 'date'), ('rls_stato', 'RLS: stato', 'text'),
    ('primo_soccorso_scadenza', 'Primo soccorso: scadenza', 'date'), ('primo_soccorso_stato', 'Primo soccorso: stato', 'text'),
    ('rspp_scadenza', 'RSPP: scadenza', 'date'), ('rspp_stato', 'RSPP: stato', 'text'),
    ('blsd_scadenza', 'BLSD: scadenza', 'date'), ('blsd_stato', 'BLSD: stato', 'text'),
    ('phtc_scadenza', 'PHTC: scadenza', 'date'), ('phtc_stato', 'PHTC: stato', 'text'),
    ('legale_rapp_scadenza', 'Legale rappresentante: scadenza', 'date'), ('legale_rapp_stato', 'Legale rappresentante: stato', 'text'),
]
DEADLINES = [('idoneita_scadenza', 'idoneita'), ('form_generale', 'formazione_generale'), ('form_specifica', 'formazione_specifica'),
             ('preposto', 'preposto'), ('antincendio', 'antincendio'), ('rls', 'rls'), ('primo_soccorso', 'primo_soccorso'),
             ('rspp', 'rspp'), ('blsd', 'blsd'), ('phtc', 'phtc'), ('legale_rapp', 'legale_rapp')]


# --- Lettura del foglio ----------------------------------------------------------------------

def plain(text):
    """Testo senza accenti, apostrofi e spazi ripetuti, in maiuscolo: per confrontare intestazioni e valori."""
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('’', '').replace("'", '').replace('`', '')
    return re.sub(r'\s+', ' ', text).strip().upper()


def clean(value):
    return re.sub(r'\s+', ' ', str(value if value is not None else '')).strip()


def excel_date(serial):
    try:
        iso = (date(1899, 12, 30) + timedelta(days=int(float(serial)))).isoformat()
    except (ValueError, OverflowError):
        return ''
    return iso if 1902 <= int(iso[:4]) <= 2100 else ''


def to_date(value):
    """(data ISO, testo): un numero Excel o una data scritta diventa ISO; un testo come «DA FARE» resta testo."""
    text = clean(value)
    if not text:
        return '', ''
    if re.fullmatch(r'\d+(\.\d+)?', text):
        return excel_date(text), ''
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?', text)
    if m:
        return excel_date_from_parts(m.group(1), m.group(2), m.group(3)), ''
    m = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', text)
    if m:
        year = m.group(3) if len(m.group(3)) == 4 else '20' + m.group(3)
        return excel_date_from_parts(year, m.group(2), m.group(1)), ''
    return '', text


def excel_date_from_parts(y, m, d):
    try:
        iso = date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return ''
    return iso if 1902 <= int(y) <= 2100 else ''


def to_number(value):
    text = clean(value).replace(',', '.').replace('%', '')
    if not re.fullmatch(r'-?\d+(\.\d+)?', text):
        return None
    number = float(text)
    return int(number) if number.is_integer() else round(number, 2)


def read_sheet(path, limit=None):
    """Righe del foglio DATABASE come dizionari {chiave: valore grezzo}, con il numero di riga Excel."""
    archive = zipfile.ZipFile(path)
    strings = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
        strings = [''.join(t.text or '' for t in si.iter(f'{{{NS["s"]}}}t')) for si in root.findall('s:si', NS)]
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
    target = None
    for sheet in ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS):
        if plain(sheet.get('name')) == SHEET_NAME:
            raw = rels.get(sheet.get(REL), '')
            target = raw.lstrip('/') if raw.startswith('/') else 'xl/' + raw
    if not target or target not in archive.namelist():
        raise SystemExit(f'Nel file manca il foglio «{SHEET_NAME}».')
    headers, mapping, rows = None, {}, []
    with archive.open(target) as stream:
        for _, el in ET.iterparse(stream):
            if el.tag != f'{{{NS["s"]}}}row':
                continue
            number = int(el.get('r') or 0)
            values = {}
            for c in el.findall('s:c', NS):
                addr = c.get('r') or ''
                col = re.match(r'[A-Z]+', addr)
                if not col:
                    continue
                kind = c.get('t')
                node = c.find('s:v', NS)
                value = node.text if node is not None else ''
                if kind == 's':
                    value = strings[int(value)] if value and value.isdigit() and int(value) < len(strings) else ''
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.iter(f'{{{NS["s"]}}}t'))
                elif kind == 'e':
                    value = ''
                if value not in (None, ''):
                    values[col.group()] = value
            el.clear()
            if not values:
                continue
            if headers is None:
                headers = {col: plain(val) for col, val in values.items()}
                for key, names in COLUMNS.items():
                    for col, head in headers.items():
                        if head in names:
                            mapping[key] = col
                            break
                missing = [k for k in REQUIRED if k not in mapping]
                if missing:
                    raise SystemExit(f'Intestazioni non trovate nel foglio {SHEET_NAME}: {", ".join(missing)}.')
                continue
            rows.append((number, {key: values.get(col, '') for key, col in mapping.items()}))
            if len(rows) >= (limit or MAX_ROWS):
                break
    return rows, mapping


# --- Interpretazione ----------------------------------------------------------------------------

def cf_block(text, first_name=False):
    letters = [ch for ch in plain(text) if ch.isalpha()]
    consonants = [ch for ch in letters if ch not in 'AEIOU']
    vowels = [ch for ch in letters if ch in 'AEIOU']
    if first_name and len(consonants) >= 4:
        consonants = [consonants[0], consonants[2], consonants[3]]
    return (''.join(consonants + vowels) + 'XXX')[:3]


def split_name(full, cf):
    """Cognome e nome da «COGNOME NOME»: con il codice fiscale si cerca la divisione coerente, altrimenti
    si tiene unita la particella (Di, De, La…)."""
    tokens = full.split()
    if len(tokens) < 2:
        return full, ''
    if cf:
        for i in range(1, len(tokens)):
            surname, name = ' '.join(tokens[:i]), ' '.join(tokens[i:])
            if cf_block(surname) == cf[:3] and cf_block(name, True) == cf[3:6]:
                return surname, name
        for i in range(1, len(tokens)):
            surname, name = ' '.join(tokens[i:]), ' '.join(tokens[:i])  # scritto «NOME COGNOME»
            if cf_block(surname) == cf[:3] and cf_block(name, True) == cf[3:6]:
                return surname, name
    i = 1
    while i < len(tokens) - 1 and tokens[i - 1].lower() in PARTICLES:
        i += 1
    return ' '.join(tokens[:i]), ' '.join(tokens[i:])


def role_of(mansione):
    text = plain(mansione).lower().replace('/', ' ')
    if not text:
        return 'ALTRO'
    words = set()
    for token in text.split():
        words.update(token.replace('.', ' ').split())   # «inf. ped.» → inf, ped
        words.add(token.replace('.', ''))                # «o.s.s.» → oss
    flat = re.sub(r'\s+', ' ', text.replace('.', ' ')).strip()
    for role, needles in ROLE_RULES:
        for needle in needles:
            if len(needle) <= 4 and ' ' not in needle:
                if needle in words:
                    return role
            elif needle in flat or needle in text:
                return role
    return 'ALTRO'


def relationship_of(contract):
    key = plain(contract)
    for prefix, value in RELATIONSHIPS.items():
        if key.startswith(prefix):
            return value
    return 'altro' if key else ''


def center_code(name, taken):
    text = re.sub(r'\([^)]*\)', ' ', plain(name))
    for form in LEGAL_FORMS:
        text = re.sub(r'(?<![A-Z])' + re.escape(form) + r'(?![A-Z])', ' ', text)
    words = re.findall(r'[A-Z0-9]+', text) or re.findall(r'[A-Z0-9]+', plain(name)) or ['STRUTTURA']
    base = '-'.join(words)[:30].strip('-')
    if len(base) < 2:
        base = (base + 'XX')[:2]
    code, n = base, 1
    while code in taken:
        n += 1
        suffix = f'-{n}'
        code = base[:30 - len(suffix)] + suffix
    taken.add(code)
    return code


def decimal(value):
    number = to_number(value)
    return '' if number is None else str(number)


def interpret(number, raw, warnings):
    """Una riga del foglio diventa la descrizione di una persona in una società."""
    name = clean(raw.get('nominativo'))
    company = clean(raw.get('societa'))
    cf = plain(raw.get('cf')).replace(' ', '')
    if cf and not CF.fullmatch(cf):
        warnings.append(dict(row=number, field='codice_fiscale', problem='codice fiscale non valido: ignorato'))
        cf = ''
    birth, _ = to_date(raw.get('nascita'))
    start, start_text = to_date(raw.get('inizio'))
    end, end_text = to_date(raw.get('fine'))
    state = plain(raw.get('stato'))
    ended = state in ENDED_STATES or (not state and end and end < today().isoformat())
    stage = 'ended' if ended else ('incoming' if start and start > today().isoformat() else 'active')
    surname, first = split_name(name, cf)
    part = to_number(raw.get('part_time'))
    if part is not None:
        part = part * 100 if part <= 1 else part
        part = '' if part <= 0 or part > 100 else str(int(part) if float(part).is_integer() else round(part, 2))
    else:
        part = ''
    if not part and re.search(r'\bFT\b', plain(raw.get('contratto'))):
        part = '100'  # tempo pieno: nel file la percentuale è indicata solo per i part-time
    hours = decimal(raw.get('ore'))
    if hours and not 0 < float(hours) <= 168:
        hours = ''  # zero o fuori scala: ore non note
    fields = {k: '' for k in hr.KEYS}
    fields.update(
        first_name=first[:80], last_name=surname[:80], tax_code=cf, birth_date=birth, birth_place=clean(raw.get('luogo_nascita'))[:150],
        city=clean(raw.get('residenza_citta'))[:100], province=clean(raw.get('residenza_prov'))[:60],
        email=clean(raw.get('email'))[:200].lower(), employer=company[:200], department=clean(raw.get('attivita'))[:150],
        manager=clean(raw.get('referente'))[:150], relationship=relationship_of(raw.get('contratto')),
        contract_type=clean(raw.get('contratto'))[:100], ccnl=clean(raw.get('ccnl'))[:150], level=clean(raw.get('livello'))[:80],
        qualification=clean(raw.get('mansione'))[:150], start_date=start, end_date=end, weekly_hours=hours,
        part_time_percent=part, workplace=(clean(raw.get('luogo')) or clean(raw.get('citta')))[:150],
    )
    notes = [f'Importato dal database del personale (riga {number}).']
    if start_text:
        notes.append(f'Data inizio nel file: {start_text}.')
    if end_text:
        notes.append(f'Data fine nel file: {end_text}.')
    if state and not ended:
        notes.append(f'Stato nel file: {clean(raw.get("stato"))}.')
    fields['notes'] = ' '.join(notes)[:2000]
    custom = dict(attivita=clean(raw.get('attivita')), rischio=clean(raw.get('rischio')), ateco=clean(raw.get('ateco')),
                  ribaltamento=clean(raw.get('ribaltamento')), profilo=clean(raw.get('profilo')), sesso=clean(raw.get('sesso')),
                  titolo_studio=clean(raw.get('titolo')), ore_accreditamento=decimal(raw.get('ore_accreditamento')),
                  progetto=clean(raw.get('progetto')), prescrizioni=clean(raw.get('prescrizioni')),
                  medico_competente=clean(raw.get('medico')), medico_coordinato=clean(raw.get('medico_coord')),
                  fondo_formazione=clean(raw.get('fondo')), idoneita_durata_anni=decimal(raw.get('idoneita_anni')))
    visit, visit_text = to_date(raw.get('idoneita_visita'))
    custom['idoneita_visita'] = visit
    copy = plain(raw.get('idoneita_copia'))
    custom['idoneita_copia'] = 'si' if copy in ('SI', 'S', 'X', 'OK') else ('no' if copy == 'NO' else '')
    for key, prefix in DEADLINES:
        when, text = to_date(raw.get(key))
        custom[f'{prefix}_scadenza'] = when
        custom[f'{prefix}_stato'] = text[:60]
    if visit_text and not custom['idoneita_stato']:
        custom['idoneita_stato'] = visit_text[:60]
    custom = {k: val for k, val in custom.items() if val}
    key = cf or (plain(name) + '|' + birth if name else '')
    return dict(row=number, company=company, name=name[:150], key=key, role=role_of(raw.get('mansione')), fields=fields,
                custom=custom, active=not ended, stage=stage, start=start, end=end, city=clean(raw.get('citta')),
                site=clean(raw.get('luogo')), address=dict(address=clean(raw.get('indirizzo'))[:250], city=clean(raw.get('citta'))[:100],
                                                            province=clean(raw.get('provincia'))[:60],
                                                            contact_name=clean(raw.get('referente'))[:150],
                                                            notes=' · '.join(x for x in (clean(raw.get('attivita')),
                                                                                         ('ATECO ' + clean(raw.get('ateco'))) if clean(raw.get('ateco')) else '',
                                                                                         clean(raw.get('regione'))) if x)[:2000]))


def plan(rows, warnings):
    """Raggruppa le righe: società → persone (per chiave) → righe ordinate per data di inizio."""
    companies = {}
    skipped = 0
    for number, raw in rows:
        if not clean(raw.get('nominativo')) or not clean(raw.get('societa')):
            skipped += 1
            continue
        item = interpret(number, raw, warnings)
        company = companies.setdefault(plain(item['company']), dict(name=item['company'], people={}, sites=Counter(), cities=Counter(),
                                                                       address=item['address'], roles=Counter()))
        company['cities'][item['city']] += 1
        if item['site']:
            company['sites'][item['site']] += 1
        company['people'].setdefault(item['key'] or f'riga-{number}', []).append(item)
    for company in companies.values():
        for key, items in company['people'].items():
            items.sort(key=lambda x: (x['start'] or '0000', x['row']))
            company['roles'][items[-1]['role']] += 1
    return companies, skipped


# --- Scrittura nell'archivio --------------------------------------------------------------------

def save_with_retries(db, actor, cid, body, person_id, warnings, number):
    """Salva il fascicolo; se un campo viene rifiutato, lo svuota e riprova (al massimo 4 volte)."""
    for _ in range(4):
        try:
            return hr.save(db, actor, cid, body, person_id)
        except WRError as exc:
            field = getattr(exc, 'field', None)
            if field and field in body['fields'] and body['fields'][field]:
                warnings.append(dict(row=number, field=field, problem=exc.message))
                body['fields'][field] = ''
            elif field and field.startswith('custom_') and body['custom'].get(field[7:]):
                warnings.append(dict(row=number, field=field, problem=exc.message))
                body['custom'].pop(field[7:], None)
            else:
                warnings.append(dict(row=number, field=field or '', problem=exc.message))
                return None
    return None


def run(db, actor, path, *, dry_run=False, limit=None, log=print):
    started = time.perf_counter()
    rows, mapping = read_sheet(path, limit)
    warnings = []
    companies, skipped = plan(rows, warnings)
    missing_columns = [k for k in COLUMNS if k not in mapping]
    report = dict(file=Path(path).name, rows=len(rows), skipped_rows=skipped, companies=len(companies),
                  people={'total': sum(len(c['people']) for c in companies.values()),
                          'rows_merged': sum(len(v) - 1 for c in companies.values() for v in c['people'].values())},
                  columns_missing=missing_columns, roles=dict(Counter(r for c in companies.values() for r in c['roles'].elements())),
                  unmapped_qualifications=dict(Counter(items[-1]['fields']['qualification'] for c in companies.values()
                                                       for items in c['people'].values() if items[-1]['role'] == 'ALTRO').most_common(40)),
                  dry_run=dry_run, centers_created=0, centers_reused=0, people_created=0, people_updated=0, contracts=0,
                  contracts_skipped=0, links=0, warnings=warnings)
    log(f'Righe lette: {len(rows)} (saltate senza nome o società: {skipped}); società: {len(companies)}; '
        f'persone: {report["people"]["total"]} (righe ripetute della stessa persona: {report["people"]["rows_merged"]})')
    if missing_columns:
        log('Colonne non trovate nel foglio (campi lasciati vuoti): ' + ', '.join(missing_columns))
    if dry_run:
        report['seconds'] = round(time.perf_counter() - started, 1)
        return report

    with db.read() as con:
        existing = {plain(r['name']): dict(r) for r in con.execute('SELECT id, name, code, config_version FROM centers')}
        taken = {r['code'] for r in existing.values()}
    template_fields = [dict(id=i, label=l, type=t, required=False) for i, l, t in CUSTOM_FIELDS]
    by_key = defaultdict(list)  # chiave persona → [(center_id, person_id)] per i collegamenti di gruppo
    for n, (ckey, company) in enumerate(sorted(companies.items()), 1):
        if ckey in existing:
            cid = existing[ckey]['id']
            report['centers_reused'] += 1
        else:
            cid = centers.create(db, actor, dict(name=company['name'][:150], code=center_code(company['name'], taken)))['id']
            report['centers_created'] += 1
        # parametri: ruoli usati e sedi esterne (luoghi di lavoro diversi dal comune della società)
        current = centers.read_config(db, actor, cid)
        cfg = dict(current['config'])
        roles = list(cfg['roles'])
        for role in sorted(company['roles']):
            if role not in roles:
                roles.append(role)
        main_city = company['cities'].most_common(1)[0][0] if company['cities'] else ''
        sites = sorted(s for s in company['sites'] if plain(s) != plain(main_city))[:100]
        if roles != cfg['roles'] or sites != cfg['sites']:
            cfg['roles'], cfg['sites'] = roles, sites
            centers.save_config(db, actor, cid, dict(config=cfg, version=current['version'], note='Importazione database personale'))
        # rubrica della struttura
        with db.read() as con:
            structure = structures.record(con, cid)
            tpl = hr.template(con, cid)
        fields = dict(structure['fields'])
        fields.update(legal_name=company['name'][:200], **company['address'])
        if fields != structure['fields']:
            structures.save(db, actor, cid, dict(fields=fields, version=structure['version']))
        if tpl['fields'] != template_fields:
            hr.save_template(db, actor, cid, dict(tasks=tpl['tasks'], fields=template_fields, version=tpl['version']))
        # persone
        with db.read() as con:
            known = {}
            for r in con.execute('SELECT p.id, p.version, pr.fields, pr.version AS pv FROM people p LEFT JOIN profiles pr ON pr.person_id=p.id '
                                 'WHERE p.center_id=?', (cid,)):
                tax = (json.loads(r['fields']).get('tax_code') if r['fields'] else '') or ''
                if tax:
                    known[tax] = dict(id=r['id'], version=r['version'], profile_version=r['pv'] or 0)
        for key, items in company['people'].items():
            current_item = items[-1]
            previous = known.get(current_item['fields']['tax_code']) if current_item['fields']['tax_code'] else None
            body = dict(name=current_item['name'], role=current_item['role'], registration='', active=current_item['active'],
                        stage=current_item['stage'], fields=dict(current_item['fields']), custom=dict(current_item['custom']),
                        version=previous['profile_version'] if previous else 0)
            if previous:
                body['person_version'] = previous['version']
            saved = save_with_retries(db, actor, cid, body, previous['id'] if previous else None, warnings, current_item['row'])
            if not saved:
                continue
            pid = saved['person_id']
            report['people_updated' if previous else 'people_created'] += 1
            by_key[key].append((cid, pid))
            for item in items:
                if not item['start'] or not item['fields']['weekly_hours'] or not item['fields']['part_time_percent']:
                    report['contracts_skipped'] += 1
                    continue
                data = dict(role=item['role'], contract_type=item['fields']['contract_type'], ccnl=item['fields']['ccnl'],
                            level=item['fields']['level'], weekly_hours=float(item['fields']['weekly_hours']),
                            part_time_percent=float(item['fields']['part_time_percent']), note='')
                try:
                    workforce.save_interval(db, actor, cid, pid, 'contract',
                                            dict(version=0, valid_from=item['start'], valid_to=item['end'], data=data,
                                                 reason='Importazione database personale'))
                    report['contracts'] += 1
                except WRError as exc:
                    report['contracts_skipped'] += 1
                    warnings.append(dict(row=item['row'], field='contratto', problem=exc.message))
        log(f'  [{n}/{len(companies)}] struttura pronta: {len(company["people"])} persone')
    # collegamenti di gruppo: stessa persona in società diverse
    for key, members in by_key.items():
        if len(members) < 2 or key.startswith('riga-'):
            continue
        with db.read() as con:
            first = con.execute('SELECT p.identity_id, i.version FROM people p JOIN identities i ON i.id=p.identity_id WHERE p.id=?',
                                (members[0][1],)).fetchone()
        for cid, pid in members[1:]:
            with db.read() as con:
                person = con.execute('SELECT identity_id, version FROM people WHERE id=?', (pid,)).fetchone()
                identity = con.execute('SELECT version FROM identities WHERE id=?', (first['identity_id'],)).fetchone()
            if person['identity_id'] == first['identity_id']:
                continue
            try:
                workforce.link(db, actor, cid, pid, dict(identity_id=first['identity_id'], identity_version=identity['version'],
                                                          version=person['version'],
                                                          reason='Importazione database personale: stessa persona in più società'))
                report['links'] += 1
            except WRError as exc:
                warnings.append(dict(row=0, field='collegamento', problem=exc.message))
    report['seconds'] = round(time.perf_counter() - started, 1)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('file', type=Path, help='cartella Excel «DATABASE PERSONALE» (.xlsx)')
    p.add_argument('--dati', type=Path, required=True, help='cartella data dell’archivio WR (già inizializzato)')
    p.add_argument('--chiave', type=Path, required=True, help='chiave del server')
    p.add_argument('--utente', default='admin', help='account amministratore a nome del quale importare')
    p.add_argument('--prova', action='store_true', help='legge e riepiloga senza scrivere nulla')
    p.add_argument('--limite', type=int, help='solo le prime N righe (per prove)')
    p.add_argument('--json', type=Path, help='dove salvare il rapporto (solo conteggi, nessun dato personale)')
    a = p.parse_args(argv)
    if not (a.dati / factory.DB_NAME).exists():
        raise SystemExit('Archivio non trovato: inizializzarlo prima con «manage.py init».')
    application = factory.create(a.dati, origin='http://127.0.0.1', key_file=a.chiave, dev=True)
    db = application.db
    with db.read() as con:
        row = con.execute('SELECT id FROM users WHERE username=? AND active=1', (a.utente,)).fetchone()
        if not row:
            raise SystemExit(f'Account «{a.utente}» non trovato o non attivo.')
        actor = users.load(con, row['id'])
    report = run(db, actor, a.file, dry_run=a.prova, limit=a.limite)
    summary = {k: v for k, v in report.items() if k != 'warnings'}
    summary['warnings_count'] = len(report['warnings'])
    summary['warnings_by_field'] = dict(Counter(w['field'] for w in report['warnings']))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if a.json:
        a.json.write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f'Rapporto salvato in {a.json}')
    return report


if __name__ == '__main__':
    main()
