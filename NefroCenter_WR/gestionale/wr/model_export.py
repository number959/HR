"""Foglio mensile nel formato del vecchio modello Excel (registro, prospetto per il consulente paghe, collaboratori).

Il file riproduce il modello «Presenze Personale» che gli uffici compilavano a mano ogni mese, ma è generato dai
dati del portale: griglia persone × giorni con una riga per fascia, contatori per causale, spazio riservato
all'ufficio del personale (dagli accordi del mese), indicatori per fascia (persone in turno nella sede, pazienti,
rapporto, efficienza), foglio per il consulente paghe e prospetto dei collaboratori. Contiene solo valori già
calcolati dal portale: nessuna formula, nessuna macro. Contatori e indicatori sono gli stessi numeri della pagina
«Controlli e chiusura» (attendance.counters, workload_rows e workload_summary): il foglio li scrive, non li ricalcola.
Lo scarico segue il permesso «presenze.esporta», quindi per compilatore e direzione il parametro della struttura
«Compilatore e consultazione possono scaricare il CSV», come il CSV e l'Excel del registro. Le parti economiche
compaiono solo per chi può consultare gli accordi; indicatori e pazienti solo per chi può consultare il carico;
l'IBAN solo per chi gestisce le paghe.
"""
import io
from decimal import Decimal

from . import agreements, approvals, attendance, audit, centers, collaborators, exports, hr, months, rules, users
from .errors import Forbidden
from .permissions import has
from .util import month_days, month_label, stamp
from . import validate as v
from .web import Reply, route

# Colori del vecchio modello: sfondo giallo = turno fuori sede, carattere rosso = turno festivo.
YELLOW = '#FFFF00'
RED = '#FF0000'
GREEN = '#D9EAD3'     # efficienza adeguata
ORANGE = '#FCE5CD'    # efficienza sotto la soglia
GREY = '#E7E6E6'      # domeniche e festività nelle colonne dei giorni
NAVY = '#0B2440'
LIGHT = '#DCE6F2'
MODEL_LABELS = {'turns': 'a turni', 'hours': 'a ore', 'fixed': 'quota fissa'}
BASIS_LABELS = {'surplus': 'eccedenza sui giorni lavorativi', 'all': 'tutti i turni'}
KIND_LABELS = {'work': 'turno', 'absence': 'assenza', 'rest': 'riposo'}
# Contatori a destra della griglia, dopo una colonna per ogni causale: (intestazione, nota sotto l'intestazione).
COUNTER_TAIL = [('Totale (modello)', 'senza RC e riposi'), ('Registrazioni', 'tutte, a consuntivo'),
                ('Fuori sede', 'turni in altra sede'), ('Festivi', 'turni festivi')]
COUNTERS_NOTE = ('Contatori: «Totale (modello)» conta le registrazioni a consuntivo senza recuperi turno (RC) e riposi, '
                 'come il vecchio file e la pagina «Controlli e chiusura»; «Registrazioni» le conta tutte.')
EXPORT_DENIED = 'Esportazione del registro non consentita a questo profilo dai parametri della struttura.'
OFFICE_HEADERS = [('Giorni extra', 'turni − teorico'), ('Feriali', 'extra − festivi'), ('Netto feriale', '× tariffa feriale'),
                  ('Festivi', 'turni festivi'), ('Netto festivo', '× tariffa festiva'), ('Totale', 'importo dell’accordo'),
                  ('Festivi CCNL', 'già riconosciuti'), ('Accordo', 'stato e modello')]
CONSULTANT_NOTE = ('L’importo nella colonna Totale è quello da considerare per l’elaborazione dei cedolini; '
                   'la colonna Festivi CCNL indica i festivi da retribuire.')
COLOR_NOTE = 'Sfondo giallo = turno fuori sede (la sede è nel portale); carattere rosso = turno in giorno festivo.'


# --- Raccolta dei dati --------------------------------------------------------------------------

def collect(con, user, center, month):
    """Tutto ciò che serve ai fogli, letto una volta sola e già filtrato dai permessi dell'utente."""
    state = months.get(con, center['id'], month)
    cfg, current = months.configuration(con, center['id'], state)
    everyone = months.people(con, center['id'])
    all_entries = months.entries(con, center['id'], month)
    entries = [e for e in all_entries if e['layer'] == 'actual']
    with_entries = {e['person_id'] for e in entries}
    persons = [p for p in everyone if p['active'] or p['id'] in with_entries]
    slots = [s for s in cfg['slots'] if s['active']]
    known = {s['id'] for s in slots}
    for extra in sorted({e['slot'] for e in entries} - known):
        slots.append(next((s for s in cfg['slots'] if s['id'] == extra), dict(id=extra, label=extra)))
    money = has(user, 'accordi.vedi', current)
    bank = has(user, 'paghe.gestisci', current)
    load = has(user, 'presenze.carico', current)
    relationships = {p['id']: hr.relationship_of(hr.profile(con, p['id'])['fields']) for p in persons}
    pay, collab = {}, []
    if money:
        pay = {r['person_id']: r for r in agreements.month_rows(con, center['id'], month)[2]}
        collab = collaborators.rows_for(con, center['id'], month, user)[2]
    # Contatori per persona e indicatori per fascia: gli stessi numeri della pagina «Controlli e chiusura».
    counts = attendance.counters(cfg, rules.summarize(everyone, all_entries))
    workload, workload_summary = [], None
    if load:
        workload = attendance.workload_rows(con, center['id'], month, cfg, everyone, all_entries)
        workload_summary = attendance.workload_summary(cfg, workload, all_entries, everyone)
    return dict(center=center, month=month, state=state, cfg=cfg, days=months.days_info(month, cfg), persons=persons,
                entries=entries, slots=slots, relationships=relationships, pay=pay, collaborators=collab,
                counter_codes=counts['codes'], counters={r['person_id']: r for r in counts['people']},
                workload=workload, workload_summary=workload_summary,
                approval=approvals.metadata(con, user, center['id'], month), money=money, bank=bank, load=load,
                working_days=rules.working_days(month_days(month), cfg), generated=stamp())


def sections(data):
    """Gruppi del vecchio modello: infermieri dipendenti, infermieri a prestazione, altri ruoli, medici dipendenti, consulenti."""
    cfg = data['cfg']
    nurse, doctor = set(cfg['nurse_roles']), set(cfg['doctor_roles'])
    rel = data['relationships']
    groups = [('nurse', 'Personale dipendente · infermieri', 'infermieri dipendenti',
               lambda p: p['role'] in nurse and rel[p['id']] == hr.EMPLOYEE),
              ('nurse', 'Infermieri a prestazione, volontari e dipendenti di altre strutture', 'infermieri a prestazione',
               lambda p: p['role'] in nurse and rel[p['id']] != hr.EMPLOYEE),
              ('other', 'Altro personale', 'altro personale', lambda p: p['role'] not in nurse and p['role'] not in doctor),
              ('doctor', 'Medici dipendenti', 'medici dipendenti', lambda p: p['role'] in doctor and rel[p['id']] == hr.EMPLOYEE),
              ('doctor', 'Medici consulenti', 'medici consulenti', lambda p: p['role'] in doctor and rel[p['id']] != hr.EMPLOYEE)]
    out = []
    for group, title, short, test in groups:
        members = [p for p in data['persons'] if test(p)]
        if members:
            out.append(dict(group=group, title=title, short=short, persons=members))
    return out


def counters(row, codes):
    """Contatori di una persona dalla riga di attendance.counters: turni, una voce per causale di assenza o riposo,
    totale come nel vecchio modello (senza RC e riposi), registrazioni, fuori sede, festivi. Senza riga: tutti zero."""
    if not row:
        return [0] * (len(codes) + 1 + len(COUNTER_TAIL))
    return ([row['shifts']] + [row['codes'].get(c['id'], 0) for c in codes]
            + [row['total'], row['registrations'], row['external'], row['festive']])


def office_values(row):
    """Spazio riservato ufficio del personale dai calcoli dell'accordo; gli importi mancanti restano vuoti."""
    if not row:
        return [None] * len(OFFICE_HEADERS)
    a = row['agreement']
    status = row['status_label'] + (' · confermato' if a.get('confirmed') else ' · da confermare')
    status += f' · {MODEL_LABELS.get(a.get("model"), a.get("model", ""))} · {BASIS_LABELS.get(a.get("basis"), a.get("basis", ""))}'
    return [row['base_units'], row['ordinary_units'], row['ordinary_amount'], row['festive_units'], row['festive_amount'],
            row['amount'], a.get('ccnl_count', 0) or 0, status]


def month_status(state, approval):
    label = 'chiuso' if state['closed'] else 'aperto'
    if approval['enabled']:
        label += f' · approvazione: {approval["label"]}'
    return label


def _sum(values):
    present = [Decimal(str(x)) for x in values if x is not None]
    return float(sum(present, Decimal(0))) if present else None


def _when(iso):
    """'2026-10-29T14:05:12+01:00' → '29/10/2026 alle 14:05'."""
    return f'{iso[8:10]}/{iso[5:7]}/{iso[:4]} alle {iso[11:16]}'


# --- Scrittura dei fogli ------------------------------------------------------------------------

class Formats:
    """Formati condivisi: una sola istanza per ogni combinazione di proprietà."""

    BASE = dict(font_name='Arial', font_size=9, border=1, border_color='#B7C0CC', valign='vcenter')

    def __init__(self, wb):
        self.wb = wb
        self.cache = {}

    def get(self, **props):
        merged = {**self.BASE, **props}
        key = tuple(sorted(merged.items()))
        if key not in self.cache:
            self.cache[key] = self.wb.add_format(merged)
        return self.cache[key]

    def plain(self, **props):
        merged = {'font_name': 'Arial', 'font_size': 10, 'valign': 'top', **props}
        key = ('plain',) + tuple(sorted(merged.items()))
        if key not in self.cache:
            self.cache[key] = self.wb.add_format(merged)
        return self.cache[key]


class Grid:
    """Scrive la griglia del mese su un foglio: intestazioni, blocchi delle persone, totali, indicatori."""

    ROLE, NAME, SLOT, DAY0 = 0, 1, 2, 3

    def __init__(self, ws, F, data, *, money, indicators):
        self.ws, self.F, self.d = ws, F, data
        self.money = money and data['money']
        self.indicators = indicators and data['load']
        self.days = data['days']
        self.slots = data['slots']
        self.codes = data['counter_codes']
        self.counter_names = ['Turni'] + [c['id'] for c in self.codes] + [name for name, _ in COUNTER_TAIL]
        self.counter_hints = [''] * (1 + len(self.codes)) + [hint for _, hint in COUNTER_TAIL]
        self.C0 = self.DAY0 + len(self.days)
        self.O0 = self.C0 + len(self.counter_names)
        self.last = self.O0 + (len(OFFICE_HEADERS) if self.money else 0) - 1

    # -- celle --------------------------------------------------------------------------------

    def cell(self, r0, c, value, fmt, r1=None):
        r1 = r0 if r1 is None else r1
        if r1 > r0:
            self.ws.merge_range(r0, c, r1, c, value, fmt)
        elif value is None or value == '':
            self.ws.write_blank(r0, c, None, fmt)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.ws.write_number(r0, c, value, fmt)
        else:
            self.ws.write_string(r0, c, str(value), fmt)

    def across(self, r, c0, c1, value, fmt):
        if c1 > c0:
            self.ws.merge_range(r, c0, r, c1, value, fmt)
        else:
            self.cell(r, c0, value, fmt)

    def day_format(self, entry, day, **extra):
        props = dict(align='center', **extra)
        if day['holiday'] or day['weekday'] == 6:
            props['bg_color'] = GREY
        if entry:
            if entry['site']:
                props['bg_color'] = YELLOW
            if entry['holiday']:
                props.update(font_color=RED, bold=True)
        return self.F.get(**props)

    # -- intestazione della griglia -------------------------------------------------------------

    def header(self, top):
        F = self.F
        head = F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF', align='center', text_wrap=True)
        sub = F.get(bg_color=LIGHT, align='center', text_wrap=True, font_size=8, italic=True)
        self.across(top, self.DAY0, self.C0 - 1, 'Giorni del mese', head)
        self.across(top, self.C0, self.O0 - 1, 'Contatori', head)
        if self.money:
            self.across(top, self.O0, self.last, 'Spazio riservato ufficio del personale', head)
        for col, text in ((self.ROLE, 'Ruolo'), (self.NAME, 'Persona · contratto · rapporto'), (self.SLOT, 'Fascia')):
            self.ws.merge_range(top, col, top + 2, col, text, head)
        for i, day in enumerate(self.days):
            props = dict(bold=True, align='center', bg_color=LIGHT)
            if day['holiday'] or day['weekday'] == 6:
                props['bg_color'] = GREY
            if day['holiday']:
                props['font_color'] = RED
            self.cell(top + 1, self.DAY0 + i, int(day['day'][-2:]), F.get(**props))
            self.cell(top + 2, self.DAY0 + i, day['short'], F.get(**dict(props, bold=False, font_size=8)))
        for i, (name, hint) in enumerate(zip(self.counter_names, self.counter_hints)):
            self.cell(top + 1, self.C0 + i, name, head)
            self.cell(top + 2, self.C0 + i, hint, sub)
        if self.money:
            for i, (name, hint) in enumerate(OFFICE_HEADERS):
                self.cell(top + 1, self.O0 + i, name, head)
                self.cell(top + 2, self.O0 + i, hint, sub)
        self.ws.set_row(top + 1, 46)
        self.ws.set_row(top + 2, 22)
        self.ws.freeze_panes(top + 3, self.DAY0)
        self.ws.repeat_rows(top, top + 2)
        return top + 3

    # -- blocchi delle persone -----------------------------------------------------------------

    def person(self, r0, p):
        F, d = self.F, self.d
        mine = [e for e in d['entries'] if e['person_id'] == p['id']]
        cells = {(e['slot'], e['day']): e for e in mine}
        n = len(self.slots)
        r1 = r0 + n - 1
        text = F.get(align='left')
        self.cell(r0, self.ROLE, p['role'], F.get(bold=True, align='center'), r1)
        texts = [p['name'], p['contract'] or '—', hr.relationship_label(d['relationships'][p['id']])]
        lines = texts if n >= 3 else ([texts[0], ' · '.join(texts[1:])] if n == 2 else [' · '.join(texts)])
        for i in range(n):
            value = lines[i] if i < len(lines) else ''
            self.cell(r0 + i, self.NAME, value, F.get(align='left', bold=(i == 0), font_size=9 if i == 0 else 8))
        for i, slot in enumerate(self.slots):
            self.cell(r0 + i, self.SLOT, slot['id'], F.get(align='center', italic=True))
            for j, day in enumerate(self.days):
                e = cells.get((slot['id'], day['day']))
                self.cell(r0 + i, self.DAY0 + j, e['code'] if e else None, self.day_format(e, day))
        values = counters(d['counters'].get(p['id']), self.codes)
        for i, value in enumerate(values):
            self.cell(r0, self.C0 + i, value, F.get(align='center', num_format='0'), r1)
        office = office_values(d['pay'].get(p['id'])) if self.money else []
        for i, value in enumerate(office):
            fmt = text if i == len(office) - 1 else F.get(align='right', num_format='#,##0.00' if i in (2, 4, 5) else 'General')
            self.cell(r0, self.O0 + i, value, fmt, r1)
        return r1 + 1, values, office

    def totals_row(self, r, label, counts, office, *, strong=False):
        F = self.F
        props = dict(bold=True, bg_color=LIGHT if not strong else '#C5D3E6')
        self.across(r, self.ROLE, self.SLOT, label, F.get(align='left', **props))
        for j, day in enumerate(self.days):
            self.cell(r, self.DAY0 + j, None, self.day_format(None, day, **props))
        for i, value in enumerate(counts):
            self.cell(r, self.C0 + i, value, F.get(align='center', num_format='0', **props))
        if self.money:
            for i in range(len(OFFICE_HEADERS)):
                value = office[i] if i < len(OFFICE_HEADERS) - 1 else None
                self.cell(r, self.O0 + i, value, F.get(align='right', num_format='#,##0.00' if i in (2, 4, 5) else 'General', **props))
        return r + 1

    def body(self, r):
        F = self.F
        section_fmt = F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF', align='left')
        width = len(self.counter_names)
        by_group = {}
        overall = dict(counts=[0] * width, office=[[] for _ in OFFICE_HEADERS])
        for section in sections(self.d):
            self.across(r, self.ROLE, self.last, section['title'], section_fmt)
            r += 1
            counts, office = [0] * width, [[] for _ in OFFICE_HEADERS]
            for p in section['persons']:
                r, values, mine_office = self.person(r, p)
                counts = [a + b for a, b in zip(counts, values)]
                for i, value in enumerate(mine_office):
                    office[i].append(value)
            r = self.totals_row(r, f'Totali {section["short"]}', counts, self.office_totals(office))
            bucket = by_group.setdefault(section['group'], dict(counts=[0] * width, office=[[] for _ in OFFICE_HEADERS]))
            for target in (bucket, overall):
                target['counts'] = [a + b for a, b in zip(target['counts'], counts)]
                for i, col in enumerate(office):
                    target['office'][i].extend(col)
        r += 1
        for group, label in (('nurse', 'Totali infermieri'), ('doctor', 'Totali medici')):
            if group in by_group:
                b = by_group[group]
                r = self.totals_row(r, label, b['counts'], self.office_totals(b['office']), strong=True)
        return self.totals_row(r, 'Totali personale', overall['counts'], self.office_totals(overall['office']), strong=True)

    def office_totals(self, columns):
        """Somme delle colonne dell'ufficio del personale; l'ultima (stato dell'accordo) non si somma."""
        if not self.money:
            return []
        return [_sum(col) for col in columns[:-1]] + [None]

    # -- indicatori per fascia -------------------------------------------------------------------

    def indicator_block(self, r, title, group, plural, singular):
        """Blocco di indicatori di un gruppo ('nurse' o 'doctor'): i numeri vengono da attendance.workload_rows (righe
        giornaliere) e attendance.workload_summary (colonna «Totale mese» e righe finali), gli stessi della pagina
        «Controlli e chiusura». Nei giorni senza pazienti registrati il foglio mostra solo le persone in turno."""
        F, d, cfg = self.F, self.d, self.d['cfg']
        threshold = cfg['efficiency_threshold']
        roles = set(cfg[f'{group}_roles'])
        role_of = {p['id']: p['role'] for p in d['persons']}
        rows = {(w['day'], w['slot']): w for w in d['workload']}
        summary = d['workload_summary']
        by_slot = {x['slot']: x for x in summary['slots']}
        head = F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF', align='center')
        label_fmt = F.get(align='left')
        self.across(r, self.ROLE, self.SLOT, title, head)
        for j, day in enumerate(self.days):
            self.cell(r, self.DAY0 + j, int(day['day'][-2:]), head)
        self.cell(r, self.C0, 'Totale mese', F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF', align='center', text_wrap=True))
        self.ws.set_row(r, 26)
        r += 1

        def write_row(label, values, total, fmt_of):
            nonlocal r
            self.across(r, self.ROLE, self.SLOT, label, label_fmt)
            for j, (day, value) in enumerate(zip(self.days, values)):
                self.cell(r, self.DAY0 + j, value, fmt_of(value, day))
            self.cell(r, self.C0, total, fmt_of(total, None, total=True))
            r += 1

        def off_day(day):
            return bool(day) and (day['holiday'] or day['weekday'] == 6)

        def plain(value, day, total=False):
            return self.F.get(align='center', num_format='General', bold=total, **({'bg_color': GREY} if off_day(day) else {}))

        def ratio_fmt(value, day, total=False):
            # Nelle colonne strette dei giorni un decimale basta; la colonna del totale ne mostra due.
            props = dict(align='center', num_format='0.00' if total else '0.0', bold=total)
            if value is None and off_day(day):
                props['bg_color'] = GREY
            return self.F.get(**props)

        def efficiency_fmt(value, day, total=False):
            props = dict(align='center', num_format='0.00', bold=total)
            if value is not None:
                props['bg_color'] = GREEN if value >= threshold else ORANGE
            elif off_day(day):
                props['bg_color'] = GREY
            return self.F.get(**props)

        def rounded(value):
            return None if value is None else round(value, 2)

        def in_site(day, slot):
            # Persone del gruppo in turno nella sede (celle senza sfondo giallo) in un giorno senza pazienti registrati:
            # la stessa regola di attendance.workload_rows, che però produce righe solo per i giorni con pazienti.
            return len({e['person_id'] for e in d['entries'] if e['slot'] == slot and e['day'] == day
                        and e['kind'] == 'work' and not e['site'] and role_of.get(e['person_id']) in roles})

        for slot in self.slots:
            staff, ordinary, isolated, ratios, efficiencies = [], [], [], [], []
            for day in self.days:
                w = rows.get((day['day'], slot['id']))
                staff.append(w[f'{group}s'] if w else in_site(day['day'], slot['id']))
                ordinary.append(w['ordinary'] if w else None)
                isolated.append(w['isolated'] if w else None)
                ratios.append(rounded(w[f'{group}_ratio']) if w else None)
                efficiencies.append(rounded(w[f'{group}_efficiency']) if w else None)
            month = by_slot.get(slot['id'])
            with_data = bool(month and month['days'])
            label = slot.get('label', slot['id'])
            write_row(f'{plural} in turno {label}', staff, month[f'{group}_shifts'] if month else sum(staff), plain)
            write_row(f'Pazienti {label}', ordinary, month['ordinary'] if with_data else None, plain)
            write_row(f'Pazienti {label} in isolamento', isolated, month['isolated'] if with_data else None, plain)
            write_row(f'Rapporto pazienti/{singular} {label}', ratios, rounded(month[f'{group}_ratio']) if month else None, ratio_fmt)
            write_row(f'Efficienza {label}', efficiencies, rounded(month[f'{group}_efficiency']) if month else None, efficiency_fmt)
        strong = F.get(align='left', bold=True, bg_color=LIGHT)
        average = rounded(summary[f'{group}_parameter'])
        for label, value, fmt in (('Totale turni da lavorare', summary[f'{group}_shifts'], plain(None, None, True)),
                                  ('Totale dialisi da effettuare', summary['patients'] if summary['days'] else None, plain(None, None, True)),
                                  ('Media parametro', average, ratio_fmt(None, None, True)),
                                  ('Efficienza media', rounded(summary[f'{group}_efficiency']), None)):
            self.across(r, self.ROLE, self.SLOT, label, strong)
            self.cell(r, self.C0, value, fmt or efficiency_fmt(value, None, True))
            r += 1
        return r + 1

    def indicators_block(self, r):
        r = self.indicator_block(r, 'Indicatori · infermieri', 'nurse', 'Infermieri', 'infermiere')
        r = self.indicator_block(r, 'Indicatori · medici', 'doctor', 'Medici', 'medico')
        return r

    # -- foglio completo -----------------------------------------------------------------------

    def write(self, top):
        r = self.header(top)
        r = self.body(r)
        if self.indicators:
            r += 1
            r = self.indicators_block(r)
        self.ws.set_column(self.ROLE, self.ROLE, 7)
        self.ws.set_column(self.NAME, self.NAME, 30)
        self.ws.set_column(self.SLOT, self.SLOT, 5)
        self.ws.set_column(self.DAY0, self.C0 - 1, 3.6)
        self.ws.set_column(self.C0, self.O0 - 1, 6.5)
        total_col = self.C0 + 1 + len(self.codes)   # «Totale (modello)» e «Registrazioni»: più larghe per non spezzare le parole
        self.ws.set_column(total_col, total_col, 9.5)
        self.ws.set_column(total_col + 1, total_col + 1, 11.5)
        if self.money:
            self.ws.set_column(self.O0, self.last - 1, 9)
            self.ws.set_column(self.last, self.last, 34)
        return r


def _print_setup(ws):
    ws.set_landscape()
    ws.set_paper(9)
    ws.fit_to_pages(1, 0)
    ws.set_margins(0.3, 0.3, 0.5, 0.5)
    ws.set_footer('&LNefroCenter WR · foglio mensile generato dal portale&C&P / &N')
    ws.hide_gridlines(2)
    ws.set_zoom(85)


def _intro(ws, F, data, last, *, note):
    """Prime righe del foglio: titolo, struttura, mese e stato. Restituisce la riga successiva libera."""
    center = data['center']
    ws.merge_range(0, 0, 0, last, f'Presenze Personale · {center["name"]} · {month_label(data["month"])}',
                   F.plain(bold=True, font_size=16, font_color=NAVY))
    ws.set_row(0, 28)
    ws.merge_range(1, 0, 1, last, f'Struttura {center["name"]} ({center["code"]}) · mese {month_label(data["month"])} · '
                   f'stato: {month_status(data["state"], data["approval"])} · parametri versione {data["state"]["rules_version"]} · '
                   f'generato dal portale il {_when(data["generated"])}', F.plain(font_color='#4A5D73'))
    r = 2
    if note:
        ws.merge_range(r, 0, r, last, note, F.plain(bold=True, text_wrap=True, bg_color='#FFF4CC', border=1, border_color='#E0C060'))
        ws.set_row(r, 30)
        r += 1
    return r


def _parameters_and_legend(ws, F, data, last):
    """Riquadro dei parametri del mese (colonne A–C) e legenda delle causali (colonne D in poi)."""
    cfg = data['cfg']
    label = F.get(align='left', bg_color=LIGHT)
    value = F.get(align='right', num_format='General')
    text = F.plain(text_wrap=True, font_size=9, border=1, border_color='#B7C0CC')
    params = [('Giorni lavorativi del mese', data['working_days']), ('Posti dialisi accreditati', cfg['dialysis_stations']),
              ('Posti contumaciali (isolamento)', cfg['isolation_stations']),
              ('Pazienti di riferimento per infermiere', cfg['nurse_reference']),
              ('Pazienti di riferimento per medico', cfg['doctor_reference']),
              ('Peso di un paziente in isolamento', cfg['isolation_weight']),
              ('Soglia di efficienza adeguata', cfg['efficiency_threshold'])]
    top = 3
    for i, (name, number) in enumerate(params):
        ws.merge_range(top + i, 0, top + i, 1, name, label)
        ws.write_number(top + i, 2, number, value)
    work = ' · '.join(f'{c["id"]} = {c["label"]}' for c in cfg['codes'] if c['kind'] == 'work' and c['active'])
    others = ' · '.join(f'{c["id"]} = {c["label"]} ({KIND_LABELS[c["kind"]]})' for c in cfg['codes'] if c['kind'] != 'work' and c['active'])
    c0 = 3
    ws.merge_range(top, c0, top, last, 'Turni (codici in minuscolo): ' + work, text)
    ws.merge_range(top + 1, c0, top + 2, last, 'Assenze e riposi (codici in maiuscolo): ' + others, text)
    ws.merge_range(top + 3, c0, top + 3, last, COLOR_NOTE, F.plain(font_size=9, border=1, border_color='#B7C0CC', bg_color='#FFF4CC'))
    ws.merge_range(top + 4, c0, top + 4, last, 'Gli importi dello spazio riservato all’ufficio del personale esistono solo per gli accordi '
                   'confermati nel portale: una cella vuota non è uno zero.' if data['money'] else
                   'Le parti economiche non sono incluse per questo profilo.', text)
    ws.merge_range(top + 5, c0, top + 5, last, COUNTERS_NOTE, text)
    ws.merge_range(top + 6, c0, top + 8, last, 'Indicatori: persone in turno nella sede (celle senza sfondo giallo), pazienti per fascia '
                   'registrati nel portale, rapporto pazienti/infermiere = (pazienti + isolamento × peso) / infermieri; per i medici '
                   'senza peso. Efficienza = rapporto / pazienti di riferimento: verde se almeno pari alla soglia, arancione sotto. '
                   'Il «Totale mese» di rapporto ed efficienza usa solo i giorni con pazienti registrati, come la pagina «Controlli e chiusura».'
                   if data['load'] else 'Indicatori e pazienti per fascia non sono inclusi per questo profilo.', text)
    return max(top + len(params), top + 9) + 1


def registry_sheet(wb, F, data):
    ws = wb.add_worksheet('Registro')
    grid = Grid(ws, F, data, money=True, indicators=True)
    _intro(ws, F, data, grid.last, note=None)
    top = _parameters_and_legend(ws, F, data, grid.last)
    r = grid.write(top)
    ws.merge_range(r + 1, 0, r + 1, grid.last, 'Note del mese: ' + (data['state']['note'] or '—'),
                   F.plain(text_wrap=True, font_size=9))
    ws.set_row(r + 1, 36)
    _print_setup(ws)


def consultant_sheet(wb, F, data):
    ws = wb.add_worksheet('Per consulente')
    grid = Grid(ws, F, data, money=True, indicators=False)
    r = _intro(ws, F, data, grid.last, note='Nota per il consulente paghe: ' + CONSULTANT_NOTE)
    ws.merge_range(r, 0, r, grid.last, COLOR_NOTE + ' Contatori e spazio ufficio del personale come nel foglio Registro.',
                   F.plain(font_size=9))
    grid.write(r + 2)
    _print_setup(ws)


def collaborators_sheet(wb, F, data):
    ws = wb.add_worksheet('Collaboratori')
    head = F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF', align='center', text_wrap=True)
    text = F.get(align='left')
    euro = F.get(align='right', num_format='#,##0.00 "€"')
    unit = F.get(align='right', num_format='General')
    strong = dict(bold=True, bg_color=LIGHT)
    headers = ['Gruppo', 'Qualifica', 'Collaboratore', 'Chi fattura', 'Turni feriali', 'Turni festivi', 'Tariffa feriale',
               'Tariffa festiva', 'Lordo', 'Ritenuta d’acconto', 'Contributo cassa', 'Netto', 'Note'] + (['IBAN'] if data['bank'] else []) + ['Intestatario']
    last = len(headers) - 1
    r = _intro(ws, F, data, last, note='Collaboratori a prestazione del mese: compensi dagli accordi confermati nel portale, ritenuta e '
               'contributo cassa con le percentuali del fascicolo. Netto = lordo + contributo cassa − ritenuta.')
    r += 1
    ws.write_row(r, 0, headers, head)
    ws.set_row(r, 32)
    ws.freeze_panes(r + 1, 3)
    r += 1

    def money_row(label, rows, props):
        nonlocal r
        ws.merge_range(r, 0, r, 3, label, F.get(align='left', **props))
        values = [sum(x['ordinary_units'] for x in rows), sum(x['festive_units'] for x in rows), None, None,
                  _sum(x['gross'] for x in rows), _sum(x['withholding'] for x in rows), _sum(x['fund'] for x in rows), _sum(x['net'] for x in rows)]
        for i, value in enumerate(values):
            fmt = F.get(align='right', num_format='#,##0.00 "€"' if i >= 2 else 'General', **props)
            if value is None:
                ws.write_blank(r, 4 + i, None, fmt)
            else:
                ws.write_number(r, 4 + i, value, fmt)
        for c in range(12, last + 1):
            ws.write_blank(r, c, None, F.get(**props))
        r += 1

    rows = data['collaborators']
    groups = []
    for row in rows:
        if not groups or groups[-1][0] != row['relationship']:
            groups.append((row['relationship'], row['relationship_label'], []))
        groups[-1][2].append(row)
    for _, label, members in groups:
        for x in members:
            notes = '; '.join(part for part in (x['notes'], x['status_label'] if x['gross'] is None else '') if part)
            values = [label, x['role'], x['name'], x['billing_entity'], x['ordinary_units'], x['festive_units'],
                      x['weekday_rate'] if x['saved'] else None, x['holiday_rate'] if x['saved'] else None, x['gross'],
                      x['withholding'], x['fund'], x['net'], notes] + ([x['iban']] if data['bank'] else []) + [x['account_holder']]
            for c, value in enumerate(values):
                fmt = unit if c in (4, 5) else euro if 6 <= c <= 11 else text
                if value is None or value == '':
                    ws.write_blank(r, c, None, fmt)
                elif isinstance(value, (int, float)):
                    ws.write_number(r, c, value, fmt)
                else:
                    ws.write_string(r, c, str(value), fmt)
            r += 1
        money_row(f'Totale · {label}', members, strong)
    money_row('Totale complessivo', rows, dict(bold=True, bg_color='#C5D3E6'))
    if not rows:
        ws.merge_range(r + 1, 0, r + 1, last, 'Nessun collaboratore a prestazione nel mese: i fascicoli indicano il tipo di rapporto.',
                       F.plain(font_size=9))
    widths = [26, 9, 26, 24, 8, 8, 9, 9, 11, 11, 11, 11, 36] + ([30] if data['bank'] else []) + [24]
    for c, width in enumerate(widths):
        ws.set_column(c, c, width)
    _print_setup(ws)


def info_sheet(wb, F, data):
    ws = wb.add_worksheet('Informazioni')
    center, state = data['center'], data['state']
    rows = [('Generato il', data['generated']), ('Struttura', f'{center["name"]} ({center["code"]})'),
            ('Mese', month_label(data['month'])), ('Stato del mese', month_status(state, data['approval'])),
            ('Versione dei parametri', str(state['rules_version'])),
            ('Legenda dei colori', COLOR_NOTE + ' Colonne grigie = domeniche e festività del calendario. Efficienza: verde se almeno '
             f'pari alla soglia ({data["cfg"]["efficiency_threshold"]}), arancione sotto.'),
            ('Contatori e indicatori', COUNTERS_NOTE + ' Indicatori, rapporti ed efficienza sono quelli della pagina «Controlli e chiusura»: '
             'il rapporto mensile di una fascia usa solo i giorni con pazienti registrati.'),
            ('Fogli inclusi', ', '.join(s.get_name() for s in wb.worksheets())),
            ('Importi', 'Gli importi esistono solo per gli accordi confermati nel portale: una cella vuota non è uno zero. '
                        'Sono una base di verifica per l’ufficio paghe, non un cedolino.'),
            ('Riservatezza', 'Spazio ufficio del personale, foglio per il consulente e collaboratori solo per chi consulta gli accordi; '
                             'IBAN solo per chi gestisce le paghe; indicatori e pazienti solo per chi consulta il carico.'),
            ('Uso del file', 'Copia dei dati al momento dello scarico: le modifiche fatte nel file non tornano nel portale. '
                             'Nessuna formula, nessuna macro.')]
    head = F.get(bold=True, bg_color=NAVY, font_color='#FFFFFF')
    ws.write_row(0, 0, ['Voce', 'Dettaglio'], head)
    for i, (k, val) in enumerate(rows, start=1):
        ws.write_string(i, 0, k, F.get(bold=True, align='left', valign='top'))
        ws.write_string(i, 1, val, F.get(align='left', text_wrap=True, valign='top'))
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 110)
    _print_setup(ws)


def workbook(data):
    import xlsxwriter
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': f'Presenze Personale {data["center"]["code"]} {data["month"]}', 'author': 'NefroCenter WR',
                       'comments': 'Foglio mensile generato dal portale; nessuna formula, nessuna macro.'})
    F = Formats(wb)
    registry_sheet(wb, F, data)
    if data['money']:
        consultant_sheet(wb, F, data)
        collaborators_sheet(wb, F, data)
    info_sheet(wb, F, data)
    wb.close()
    return stream.getvalue()


def export(db, user, center_id, month):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'presenze.vedi')
        # Stesso controllo del CSV e dell'Excel del registro: per compilatore e direzione decide il parametro
        # della struttura «Compilatore e consultazione possono scaricare il CSV».
        if not has(user, 'presenze.esporta', centers.config(con, center_id)):
            raise Forbidden(EXPORT_DENIED)
        data = collect(con, user, center, month)
    content = workbook(data)
    with db.write() as con:
        audit.record(con, users.reload(con, user), 'Esportazione Excel: foglio mensile', center_id, entity='export',
                     entity_id='modello', after=dict(month=month))
    return Reply(content, content_type=exports.MIME, filename=f'Presenze_{center["code"]}_{month}.xlsx')


# --- API ------------------------------------------------------------------------------------

@route('GET', '/api/exports/modello/<cid>/<month>', cap='presenze.vedi')
def api_model(ctx):
    return export(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])
