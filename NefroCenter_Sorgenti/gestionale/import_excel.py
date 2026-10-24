"""Lettura OOXML del modello fornito; non avvia Excel e non esegue VBA."""
import hashlib, io, calendar, zipfile, posixpath, re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from engine import normalized_code, WORK, ABSENCE

def recognized_agreement(cells,r):
    f=lambda col,row:re.sub(r'[\s$]','',cells.get(col+str(row),{}).get('formula_text','')).upper()
    end=r+2;at=f('AT',r);av=f('AV',end);aw=f('AW',end);ax=f('AX',end);az=f('AZ',end);ba=f('BA',end)
    expected=f'93-COUNTBLANK(D{r}:AH{end})'
    if at not in (expected,expected+f'-AN{r}'):return None
    if av==f'AT{r}':mode='all'
    elif av==f'IF(AT{r}<=0,"",AT{r}-X3)':mode='surplus'
    else:return None
    if aw!=f'IF(AV{end}="","",AV{end}-AY{end})':return None
    wr=re.fullmatch(fr'IF\(AW{end}="","",AW{end}\*([0-9]+(?:\.[0-9]+)?)\)',ax)
    hr=re.fullmatch(fr'IF\(AY{end}="","",AY{end}\*([0-9]+(?:\.[0-9]+)?)\)',az)
    deduction=re.fullmatch(fr'IF\(AX{end}="","",AX{end}\+AZ{end}(?:-([0-9]+(?:\.[0-9]+)?))?\)',ba)
    if not all((wr,hr,deduction)):return None
    return dict(model='turns',basis=mode,weekday_rate=float(wr[1]),holiday_rate=float(hr[1]),
        fixed_deduction=float(deduction[1] or 0),ccnl_rate=0,confirmed=False,
        counted_absences=[k for k in ABSENCE if k!='RC' or at==expected],
        source=f'Proposta da formule Da Compilare!AT{r}:BA{end}; calendario e accordo da confermare')

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

def excel_date(value):
    return (date(1899, 12, 30)+timedelta(days=int(float(value)))).isoformat()

def col(i):
    out = ''
    while i: i, r = divmod(i-1, 26); out = chr(65+r)+out
    return out

def read_model(data):
    if len(data) > 12_000_000: raise ValueError('File troppo grande: massimo 12 MB.')
    z = zipfile.ZipFile(io.BytesIO(data))
    if sum(e.file_size for e in z.infolist()) > 80_000_000: raise ValueError('Il contenuto decompresso supera 80 MB.')
    def xml(path):
        raw = z.read(path)
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('XML con entità non supportato.')
        return ET.fromstring(raw)
    strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        strings = [''.join(t.text or '' for t in e.findall('.//s:t', NS)) for e in xml('xl/sharedStrings.xml')]
    rels = {r.get('Id'): posixpath.normpath(posixpath.join('xl', r.get('Target'))) for r in xml('xl/_rels/workbook.xml.rels')}
    wb = xml('xl/workbook.xml')
    prop = wb.find('s:workbookPr', NS)
    if prop is not None and prop.get('date1904') in ('1','true'): raise ValueError('Calendario Excel 1904 non supportato da questo importatore.')
    sheets = {}
    for sheet in wb.findall('s:sheets/s:sheet', NS):
        cells = {}
        for c in xml(rels[sheet.get(REL)]).findall('.//s:sheetData/s:row/s:c', NS):
            value = c.find('s:v', NS); v = value.text if value is not None else ''
            if c.get('t') == 's': v = strings[int(v)] if v else ''
            elif c.get('t') == 'inlineStr': v = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
            f=c.find('s:f',NS)
            cells[c.get('r')] = {'value': v or '', 'style': int(c.get('s',0)), 'formula': f is not None, 'formula_text': (f.text or '') if f is not None else ''}
        sheets[sheet.get('name')] = cells
    if 'Da Compilare' not in sheets: raise ValueError('Manca il foglio Da Compilare. Supportato il modello allegato alla progettazione.')
    cells = sheets['Da Compilare']
    value = lambda addr: cells.get(addr, {}).get('value', '')
    month = excel_date(value('O6'))[:7]; center = str(value('C6')).strip()
    if not center: raise ValueError('Nome centro mancante in C6.')
    styles = xml('xl/styles.xml'); xfs = styles.find('s:cellXfs',NS); fills = styles.find('s:fills',NS); fonts = styles.find('s:fonts',NS)
    theme_colors={}
    if 'xl/theme/theme1.xml' in z.namelist():
        ans={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        scheme=xml('xl/theme/theme1.xml').find('.//a:clrScheme',ans)
        if scheme is not None:
            lookup={x.tag.split('}')[-1]:next(iter(x),None) for x in scheme}
            for i,key in enumerate(('lt1','dk1','lt2','dk2','accent1','accent2','accent3','accent4','accent5','accent6','hlink','folHlink')):
                node=lookup.get(key)
                if node is not None:theme_colors[str(i)]=node.get('lastClr',node.get('val','')).upper()
    def rgb_color(c):
        if float(c.get('tint','0'))!=0:return ''
        return c.get('rgb','').upper()[-6:] or theme_colors.get(c.get('theme'),'')
    def color(addr, sheet=cells):
        x = xfs[sheet.get(addr,{}).get('style',0)]
        fill = fills[int(x.get('fillId',0))].find('s:patternFill/s:fgColor',NS)
        font = fonts[int(x.get('fontId',0))].find('s:color',NS)
        return (dict(fill.attrib) if fill is not None else {},dict(font.attrib) if font is not None else {})
    refs = sheets.get('Foglio1',{}); yellow = color('I2',refs)[0]; red_font = color('M2',refs)[1]
    holidays = [excel_date(c['value']) for a,c in sheets.get('Festività',{}).items() if a!='A1' and c['value'].replace('.','',1).isdigit()]
    holidays += [excel_date(value('B'+str(r))) for r in range(159,174) if value('B'+str(r)).replace('.','',1).isdigit()]
    holidays=list(dict.fromkeys(holidays))
    warnings = []
    if holidays and any(not h.startswith(month[:4]) for h in holidays):
        warnings.append('Calendario non coerente: mese '+month+' e festività di '+', '.join(sorted({h[:4] for h in holidays}))+'. Nessuna trasposizione automatica.')
    warnings.append('Il modello contiene conteggi per fascia m/p/s, senza orari. Le ore restano da inserire.')
    actual_days=sum(date(int(month[:4]),int(month[5:]),d).weekday()!=6 and month+'-'+str(d).zfill(2) not in holidays for d in range(1,calendar.monthrange(int(month[:4]),int(month[5:]))[1]+1))
    if value('X3').isdigit() and int(value('X3'))!=actual_days:
        warnings.append(f'Calendario da verificare: X3 contiene {value("X3")} giorni; nel mese reale, lunedì–sabato e festività presenti, risultano {actual_days}. Il calendario del software usa le date reali.')
    broken=sum('#REF!' in c['formula_text'] for sheet in sheets.values() for c in sheet.values())
    if broken:warnings.append(f'Il file contiene {broken} formule con riferimenti interrotti. Gli output derivati non vengono importati come risultati validati.')
    if any('COUNTIF(E' in c['formula_text'].upper() and ':AI' in c['formula_text'].upper() and '"ROL"' in c['formula_text'].upper() for c in cells.values()):
        warnings.append('Alcune formule ROL usano E:AI invece della griglia D:AH. I contatori del software leggono tutte le celle presenze del mese.')
    warnings.append('Le formule economiche riconosciute diventano proposte individuali del mese, da confermare; importi manuali, IBAN e trattenute del foglio Collaboratori non vengono trasformati in regole.')
    people, entries = [], []
    rows = sorted({int(a.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')) for a in cells})
    for r in rows:
        if value('C'+str(r)).lower() != 'm' or value('C'+str(r+1)).lower() != 'p' or value('C'+str(r+2)).lower() != 's': continue
        name = value('B'+str(r)).strip()
        if not name: continue
        pid = 'row-'+str(r)
        role = value('A'+str(r)).strip()
        people.append({'id':pid,'name':name,'role':role,'home_site':center,'contract':value('B'+str(r+1)),
                       'source_row':r,'agreement_note':' | '.join(value('AU'+str(r+j)) for j in range(3) if value('AU'+str(r+j))),
                       'agreement_proposal':recognized_agreement(cells,r)})
        for offset, slot in enumerate(('m','p','s')):
            for day in range(1,32):
                addr = col(day+3)+str(r+offset); raw=value(addr).strip()
                if not raw: continue
                if cells[addr]['formula']: raise ValueError('Formula in una cella presenze: '+addr+'. Verificare manualmente.')
                if day > calendar.monthrange(int(month[:4]),int(month[5:]))[1]: raise ValueError('Dato fuori mese nella cella '+addr)
                try: code = normalized_code(raw)
                except ValueError: raise ValueError('Causale non riconosciuta in '+addr+': '+raw)
                if code in WORK and code!=slot: raise ValueError('Codice e fascia non coincidono in '+addr+'. Correggere prima di importare.')
                bg, fg = color(addr)
                rgb = rgb_color(bg)
                external = bool(yellow and bg==yellow) or rgb in ('FFFF00','00FF00')
                holiday = bool(red_font and fg==red_font)
                unknown_fill = bool(bg) and not external and rgb not in ('FFFFFF','000000')
                if unknown_fill: warnings.append('Sfondo non riconosciuto in '+addr+': controllare la sede.')
                entries.append({'person_id':pid,'day':month+'-'+str(day).zfill(2),'slot':slot,'layer':'actual','code':code,
                    'work_site':'Sede esterna da specificare' if external else center,'start':'','end':'','break_minutes':0,
                    'overnight':False,'holiday':holiday,'note':'Importato da '+addr+(' | Colore sede da verificare' if unknown_fill else ''),
                    'source_cell':addr,'source_fill':bg,'source_font':fg})
    if not people: raise ValueError('Non sono state riconosciute anagrafiche nel modello.')
    if not entries: warnings.append('Il file è un modello vuoto: contiene anagrafiche ma nessuna presenza compilata.')
    return {'hash':hashlib.sha256(data).hexdigest(),'center':center,'month':month,'people':people,
            'entries':entries,'holidays':holidays,'warnings':list(dict.fromkeys(warnings))}
