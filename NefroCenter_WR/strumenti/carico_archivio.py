"""Prova di carico dell'archivio SQLite di NefroCenter WR con dati fittizi.

Crea un archivio NUOVO in una cartella vuota (mai su un archivio esistente), lo riempie con
migliaia di dipendenti, un anno di presenze (più uno storico pluriennale su alcune strutture),
documenti allegati e giornale delle modifiche, poi misura:

- i tempi di risposta delle pagine più pesanti (registro, riepilogo di gruppo, statistiche, personale di gruppo, archivio documenti, promemoria, esportazioni);
- le scritture concorrenti di più compilatori e le letture durante le scritture;
- il backup (copia coerente) e il controllo di integrità;
- le dimensioni di tabelle e indici.

Uso (dalla cartella NefroCenter_WR):
  python3 strumenti/carico_archivio.py --cartella /tmp/carico --dipendenti 3000 --strutture 60 --mesi 12 --json esito.json

Il motore gira in-process (stesso codice del servizio web, senza rete): i tempi misurati sono quelli
di database e logica, al netto del trasporto HTTP. Lo script non invia email e non tocca servizi esterni.
"""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'gestionale'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from support import Portal  # noqa: E402  (archivio temporaneo, account di prova, client HTTP in-process)
from wr.util import dumps, new_id, stamp, today  # noqa: E402

FIRST_NAMES = ['Anna', 'Luca', 'Giulia', 'Marco', 'Sara', 'Paolo', 'Elena', 'Davide', 'Chiara', 'Andrea', 'Francesca',
               'Matteo', 'Laura', 'Simone', 'Martina', 'Alessandro', 'Valentina', 'Stefano', 'Silvia', 'Roberto',
               'Federica', 'Giorgio', 'Monica', 'Fabio', 'Claudia', 'Nicola', 'Serena', 'Antonio', 'Paola', 'Enrico']
LAST_NAMES = ['Bianchi', 'Rossi', 'Verdi', 'Russo', 'Ferrari', 'Esposito', 'Romano', 'Colombo', 'Ricci', 'Marino',
              'Greco', 'Bruno', 'Gallo', 'Conti', 'De Luca', 'Costa', 'Giordano', 'Mancini', 'Rizzo', 'Lombardi',
              'Moretti', 'Barbieri', 'Fontana', 'Santoro', 'Mariani', 'Rinaldi', 'Caruso', 'Ferrara', 'Galli', 'Martini']
ROLES = ['INF'] * 6 + ['OSS'] * 2 + ['MED', 'AMM']
ABSENCES = ['FE'] * 4 + ['MA'] * 3 + ['PS', 'PS', 'ROL']
WORK_ROTATION = ['m', 'p', 'n']
DOC_CATEGORIES = ['contratto', 'attestato', 'certificato', 'documento']


def month_list(last, count):
    """Gli ultimi `count` mesi fino a `last` ('AAAA-MM'), in ordine crescente."""
    y, m = int(last[:4]), int(last[5:])
    out = []
    for _ in range(count):
        out.append(f'{y:04d}-{m:02d}')
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def first_day(month):
    return date(int(month[:4]), int(month[5:]), 1)


def last_day(month):
    nxt = first_day(month) + timedelta(days=32)
    return date(nxt.year, nxt.month, 1) - timedelta(days=1)


class Loader:
    """Riempie l'archivio con SQL diretto (molto più veloce delle API) rispettando lo schema del portale."""

    def __init__(self, db, cfg, centers, people_per_center, months, history_centers, history_months, seed):
        self.db = db
        self.slots = {s['id']: s for s in cfg['slots']}
        self.codes = {c['id']: c for c in cfg['codes']}
        self.holidays = set(cfg['holidays'])
        self.centers = centers
        self.people_per_center = people_per_center
        self.months = months
        self.history_centers = history_centers
        self.history_months = history_months
        self.rng = random.Random(seed)
        self.today = today()
        self.counts = dict(people=0, entries=0, planned=0, audit=0, months=0, documents=0)
        self.people = {}  # center_id -> [(person_id, role)]

    def run(self, docs_per_person, doc_kb, log):
        con = self.db.connect()
        con.execute('PRAGMA foreign_keys=OFF')       # solo per il caricamento massivo; verificato alla fine
        con.execute('PRAGMA synchronous=OFF')
        try:
            t0 = time.perf_counter()
            self._people(con)
            log(f'  persone: {self.counts["people"]} in {time.perf_counter() - t0:.1f} s')
            t1 = time.perf_counter()
            self._months(con)
            for i, cid in enumerate(self.centers):
                months = self.history_months if i < self.history_centers else self.months
                self._entries(con, cid, months)
            log(f'  registrazioni: {self.counts["entries"]} (di cui pianificate {self.counts["planned"]}) + '
                f'{self.counts["audit"]} righe di giornale in {time.perf_counter() - t1:.1f} s')
            t2 = time.perf_counter()
            self._documents(con, docs_per_person, doc_kb)
            log(f'  documenti: {self.counts["documents"]} da {doc_kb} KB in {time.perf_counter() - t2:.1f} s')
            con.execute('PRAGMA foreign_keys=ON')
            broken = con.execute('PRAGMA foreign_key_check').fetchall()
            if broken:
                raise RuntimeError(f'Riferimenti incoerenti dopo il caricamento: {broken[:5]}')
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            con.close()

    def _people(self, con):
        now = stamp()
        rows_i, rows_p = [], []
        n = 0
        for cid in self.centers:
            members = []
            for k in range(self.people_per_center):
                n += 1
                pid, iid = new_id(), new_id()
                name = f'{FIRST_NAMES[n % len(FIRST_NAMES)]} {LAST_NAMES[(n // len(FIRST_NAMES)) % len(LAST_NAMES)]}'
                role = ROLES[n % len(ROLES)]
                rows_i.append((iid,))
                rows_p.append((pid, cid, iid, name, role, f'M{n:05d}', now, now))
                members.append((pid, role, n))
            self.people[cid] = members
        con.execute('BEGIN')
        con.executemany('INSERT INTO identities(id,version) VALUES(?,1)', rows_i)
        con.executemany('INSERT INTO people(id,center_id,identity_id,name,role,registration,created_at,updated_at) '
                        'VALUES(?,?,?,?,?,?,?,?)', rows_p)
        con.execute('COMMIT')
        self.counts['people'] = len(rows_p)

    def _months(self, con):
        now = stamp()
        rows = []
        open_months = set(self.months[-2:])
        for i, cid in enumerate(self.centers):
            months = self.history_months if i < self.history_centers else self.months
            for m in months:
                closed = 0 if m in open_months else 1
                rows.append((cid, m, 1, closed, closed, now, 'carico'))
        con.execute('BEGIN')
        con.executemany('INSERT INTO months(center_id,month,rules_version,verified,closed,updated_at,updated_by) '
                        'VALUES(?,?,?,?,?,?,?)', rows)
        con.execute('COMMIT')
        self.counts['months'] = len(rows)

    def _entry_row(self, cid, pid, day, slot_id, code_id, layer, actor):
        slot, code = self.slots[slot_id], self.codes[code_id]
        work = code['kind'] == 'work'
        iso = day.isoformat()
        return (new_id(), cid, pid, iso, slot_id, layer, code_id, code['kind'], code['label'],
                slot['start'] if work else '', slot['end'] if work else '', 0, int(bool(slot['overnight'])) if work else 0,
                '', int(iso in self.holidays or day.weekday() == 6), 0, '', '', '', 1, 1, f'{iso}T18:05:00+01:00', actor)

    def _entries(self, con, cid, months):
        rng = self.rng
        start, end = first_day(months[0]), last_day(months[-1])
        current = months[-1]
        actor = 'compilatore'
        rows, audits = [], []
        for pid, role, n in self.people[cid]:
            day = start
            while day <= end:
                if day <= self.today:
                    code = None
                    if day.weekday() == 6:
                        if rng.random() < 0.7:
                            code, slot = 'R', 'm'
                    else:
                        r = rng.random()
                        if r < 0.86:
                            slot = 'm' if role == 'MED' else WORK_ROTATION[(day.isocalendar()[1] + n) % 3]
                            code = slot
                        elif r < 0.93:
                            code, slot = rng.choice(ABSENCES), 'm'
                        elif r < 0.97:
                            code, slot = 'R', 'm'
                    if code:
                        row = self._entry_row(cid, pid, day, slot, code, 'actual', actor)
                        rows.append(row)
                        audits.append((row[21], actor, cid, 'Registrazione presenza', 'entry', row[0], None,
                                       dumps(dict(person_id=pid, day=row[3], slot=slot, code=code, layer='actual'))))
                if day.isoformat()[:7] == current and n % 2 == 0 and day.weekday() != 6:
                    slot = 'm' if role == 'MED' else WORK_ROTATION[(day.isocalendar()[1] + n) % 3]
                    rows.append(self._entry_row(cid, pid, day, slot, slot, 'planned', 'responsabile'))
                    self.counts['planned'] += 1
                day += timedelta(days=1)
        con.execute('BEGIN')
        con.executemany('INSERT INTO entries(id,center_id,person_id,day,slot,layer,code,kind,label,start,end,pause,'
                        'overnight,site,holiday,credit,note,source,review,rules_version,version,updated_at,updated_by) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        con.executemany('INSERT INTO audit(at,actor,center_id,action,entity,entity_id,before,after) VALUES(?,?,?,?,?,?,?,?)',
                        audits)
        con.execute('COMMIT')
        self.counts['entries'] += len(rows)
        self.counts['audit'] += len(audits)

    def _documents(self, con, per_person, kb):
        if not per_person:
            return
        base = os.urandom(kb * 1024)  # contenuto incomprimibile, come un PDF scansionato
        now = stamp()
        k = 0
        for cid in self.centers:
            rows = []
            for pid, role, n in self.people[cid]:
                for j in range(per_person):
                    k += 1
                    content = base[:-8] + k.to_bytes(8, 'big')
                    expiry = (self.today + timedelta(days=(k * 37) % 730)).isoformat() if k % 3 == 0 else ''
                    rows.append((new_id(), cid, pid, f'{DOC_CATEGORIES[j % 4]}_{n:05d}_{j + 1}.pdf', DOC_CATEGORIES[j % 4],
                                 expiry, 'application/pdf', len(content), hashlib.sha256(content).hexdigest(), content,
                                 now, 'hr1'))
            con.execute('BEGIN')
            con.executemany('INSERT INTO documents(id,center_id,person_id,name,category,expiry,mime,size,sha256,content,'
                            'uploaded_at,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', rows)
            con.execute('COMMIT')
            self.counts['documents'] += len(rows)


def ms(values):
    return dict(median_ms=round(statistics.median(values), 1), max_ms=round(max(values), 1), min_ms=round(min(values), 1))


def measure(client, method, path, repeat=3, body=None):
    """Una chiamata di riscaldamento poi `repeat` misurazioni; restituisce stato, dimensione e tempi."""
    client.request(method, path, body)
    times, status, size = [], 0, 0
    for _ in range(repeat):
        t0 = time.perf_counter()
        r = client.request(method, path, body)
        times.append((time.perf_counter() - t0) * 1000)
        status, size = r.status, len(r.body)
    return dict(path=path, status=status, kb=round(size / 1024, 1), **ms(times))


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round((p / 100) * (len(values) - 1))))], 1)


def write_load(portal, writers, seconds, month, log):
    """Ogni compilatore registra turni liberi nella propria struttura per `seconds` secondi."""
    results = dict(ok=0, rejected=0, errors=0, locked=0, latencies_ms=[], samples=[])
    lock = threading.Lock()
    deadline = time.perf_counter() + seconds

    def worker(client, cid, people, taken):
        rng = random.Random(hash(cid) & 0xffff)
        days = [d for d in range(1, min(today().day, last_day(month).day) + 1)]
        local = dict(ok=0, rejected=0, errors=0, locked=0, lat=[], samples=[])
        while time.perf_counter() < deadline:
            pid = rng.choice(people)
            day = f'{month}-{rng.choice(days):02d}'
            slot = rng.choice(('m', 'p', 'n'))
            if (pid, day, slot) in taken:
                continue
            t0 = time.perf_counter()
            try:
                r = client.post(f'/api/attendance/{cid}/{month}/entries',
                                dict(person_id=pid, day=day, slot=slot, layer='actual', code=slot))
            except Exception as exc:  # errori inattesi del motore
                local['errors'] += 1
                local['samples'].append(repr(exc)[:200])
                continue
            dt = (time.perf_counter() - t0) * 1000
            if r.status == 200:
                local['ok'] += 1
                local['lat'].append(dt)
                taken.add((pid, day, slot))
            elif r.status == 400:
                local['rejected'] += 1   # regola del registro (fascia già compilata, sovrapposizione): non è un errore
                taken.add((pid, day, slot))
            else:
                local['errors'] += 1
                text = r.body[:200].decode(errors='replace')
                if 'locked' in text.lower() or 'occupat' in text.lower():
                    local['locked'] += 1
                if len(local['samples']) < 5:
                    local['samples'].append(f'{r.status} {text}')
        with lock:
            for k in ('ok', 'rejected', 'errors', 'locked'):
                results[k] += local[k]
            results['latencies_ms'].extend(local['lat'])
            results['samples'].extend(local['samples'][:3])

    threads = []
    for client, cid, people in writers:
        existing = set()
        with portal.db.read() as con:
            for r in con.execute("SELECT person_id, day, slot FROM entries WHERE center_id=? AND layer='actual' AND day LIKE ?",
                                 (cid, month + '-%')):
                existing.add((r[0], r[1], r[2]))
        threads.append(threading.Thread(target=worker, args=(client, cid, people, existing)))
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0
    lat = results.pop('latencies_ms')
    results.update(seconds=round(elapsed, 1), writers=len(writers), per_second=round(results['ok'] / elapsed, 1),
                   p50_ms=percentile(lat, 50), p95_ms=percentile(lat, 95), max_ms=percentile(lat, 100))
    log(f'  scritture: {results["ok"]} salvate ({results["per_second"]}/s), {results["rejected"]} rifiutate dalle regole, '
        f'{results["errors"]} errori; p50 {results["p50_ms"]} ms, p95 {results["p95_ms"]} ms, max {results["max_ms"]} ms')
    return results


def read_under_writes(portal, writers, readers, seconds, month, log):
    """Lettori che aprono il registro di altre strutture mentre i compilatori scrivono."""
    stop = threading.Event()
    lat, errors = [], []
    lock = threading.Lock()

    def reader(client, cid):
        local, bad = [], []
        while not stop.is_set():
            t0 = time.perf_counter()
            r = client.get(f'/api/attendance/{cid}/{month}')
            local.append((time.perf_counter() - t0) * 1000)
            if r.status != 200:
                bad.append(r.status)
        with lock:
            lat.extend(local)
            errors.extend(bad)

    threads = [threading.Thread(target=reader, args=(client, cid)) for client, cid in readers]
    for t in threads:
        t.start()
    writes = write_load(portal, writers, seconds, month, lambda s: None)
    stop.set()
    for t in threads:
        t.join()
    out = dict(readers=len(readers), reads=len(lat), read_errors=len(errors), read_p50_ms=percentile(lat, 50),
               read_p95_ms=percentile(lat, 95), read_max_ms=percentile(lat, 100), writes=writes)
    log(f'  letture durante le scritture: {len(lat)} aperture del registro, p50 {out["read_p50_ms"]} ms, '
        f'p95 {out["read_p95_ms"]} ms, max {out["read_max_ms"]} ms, errori {len(errors)}; '
        f'scritture {writes["ok"]} ({writes["per_second"]}/s, p95 {writes["p95_ms"]} ms)')
    return out


def sql_probe(db, cid, month):
    """Confronto fra il filtro LIKE 'AAAA-MM-%' usato dal registro e un intervallo BETWEEN sullo stesso indice."""
    out = {}
    with db.read() as con:
        first, last = month + '-01', month + '-31'
        for label, sql, args in (('like', 'SELECT * FROM entries WHERE center_id=? AND day LIKE ? ORDER BY day, slot', (cid, month + '-%')),
                                 ('between', 'SELECT * FROM entries WHERE center_id=? AND day BETWEEN ? AND ? ORDER BY day, slot', (cid, first, last))):
            plan = ' | '.join(r[3] for r in con.execute('EXPLAIN QUERY PLAN ' + sql, args))
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                n = len(con.execute(sql, args).fetchall())
                times.append((time.perf_counter() - t0) * 1000)
            out[label] = dict(plan=plan, rows=n, **ms(times))
        out['center_rows'] = con.execute('SELECT count(*) FROM entries WHERE center_id=?', (cid,)).fetchone()[0]
    return out


def sizes(db):
    con = db.connect()
    try:
        tables = {}
        for name, tbl in con.execute("SELECT name, tbl_name FROM sqlite_master WHERE type IN ('table','index')"):
            tables.setdefault(tbl, []).append(name)
        per_table = {}
        for tbl, names in tables.items():
            marks = ','.join('?' * len(names))
            total = con.execute(f'SELECT coalesce(sum(pgsize),0) FROM dbstat WHERE name IN ({marks})', names).fetchone()[0]
            if total > 1024 * 1024:
                per_table[tbl] = round(total / 1024 / 1024, 1)
        counts = {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('people', 'entries', 'audit', 'documents', 'months', 'centers')}
        page = con.execute('PRAGMA page_size').fetchone()[0]
        pages = con.execute('PRAGMA page_count').fetchone()[0]
    finally:
        con.close()
    wal = db.path.with_name(db.path.name + '-wal')
    return dict(file_mb=round(db.path.stat().st_size / 1024 / 1024, 1), wal_mb=round(wal.stat().st_size / 1024 / 1024, 1) if wal.exists() else 0,
                pages=pages, page_size=page, tables_mb=dict(sorted(per_table.items(), key=lambda kv: -kv[1])), rows=counts)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--cartella', type=Path, required=True, help='cartella NUOVA o vuota dove creare l\'archivio di prova')
    p.add_argument('--dipendenti', type=int, default=3000)
    p.add_argument('--strutture', type=int, default=60)
    p.add_argument('--mesi', type=int, default=12, help='mesi di presenze per ogni struttura')
    p.add_argument('--storico-strutture', type=int, default=3, help='strutture con uno storico più lungo')
    p.add_argument('--storico-mesi', type=int, default=60)
    p.add_argument('--documenti', type=int, default=2, help='documenti allegati per persona')
    p.add_argument('--documento-kb', type=int, default=120)
    p.add_argument('--compilatori', type=int, default=8, help='compilatori che scrivono insieme')
    p.add_argument('--secondi', type=int, default=20, help='durata di ogni prova di scrittura')
    p.add_argument('--seme', type=int, default=2026)
    p.add_argument('--json', type=Path, help='dove salvare l\'esito completo')
    p.add_argument('--conserva', action='store_true', help='non cancellare l\'archivio di prova alla fine')
    a = p.parse_args(argv)

    a.cartella.mkdir(parents=True, exist_ok=True)
    if any(a.cartella.iterdir()):
        sys.exit('La cartella deve essere vuota: non si lavora mai accanto a un archivio esistente.')
    tempfile.tempdir = str(a.cartella)
    log = lambda s: print(s, flush=True)  # noqa: E731
    report = dict(parameters=vars(a) | dict(cartella=str(a.cartella), json=str(a.json) if a.json else None),
                  started=stamp(), sqlite=sqlite3.sqlite_version, python=sys.version.split()[0], cpus=os.cpu_count())

    log('Creo il portale di prova…')
    portal = Portal()
    db = portal.db
    try:
        log(f'Creo {a.strutture} strutture e gli account…')
        centers = [portal.center(f'Centro Dialisi {i + 1:02d}', f'C{i + 1:02d}') for i in range(a.strutture)]
        cfg = portal.admin.ok('GET', f'/api/centers/{centers[0]}/config')['config']
        month = today().isoformat()[:7]
        months = month_list(month, a.mesi)
        history = month_list(month, max(a.storico_mesi, a.mesi))
        per_center = max(1, a.dipendenti // a.strutture)
        report['month'] = month
        report['months'] = [months[0], months[-1]]

        t0 = time.perf_counter()
        log(f'Carico {per_center * a.strutture} dipendenti, {a.mesi} mesi ({a.storico_mesi} su {a.storico_strutture} strutture)…')
        loader = Loader(db, cfg, centers, per_center, months, a.storico_strutture, history, a.seme)
        loader.run(a.documenti, a.documento_kb, log)
        report['load'] = dict(seconds=round(time.perf_counter() - t0, 1), **loader.counts)
        report['sizes'] = sizes(db)
        log(f'  archivio: {report["sizes"]["file_mb"]} MB; tabelle principali (MB): {report["sizes"]["tables_mb"]}')

        hist_cid, normal_cid = centers[0], centers[min(10, len(centers) - 1)]
        mgr_hist = portal.user('resp_storico', 'manager', [hist_cid])
        mgr_norm = portal.user('resp_normale', 'manager', [normal_cid])
        hr_user = portal.user('hr1', 'hr')
        admin = portal.admin

        log('Misuro le letture (3 ripetizioni dopo una di riscaldamento)…')
        first_month = months[0]
        probes = [
            ('registro: struttura normale (responsabile)', mgr_norm, 'GET', f'/api/attendance/{normal_cid}/{month}'),
            ('registro: struttura con 5 anni di storico', mgr_hist, 'GET', f'/api/attendance/{hist_cid}/{month}'),
            ('registro: mese chiuso di un anno fa', mgr_hist, 'GET', f'/api/attendance/{hist_cid}/{first_month}'),
            ('riepilogo di gruppo del mese (tutte le strutture)', admin, 'GET', f'/api/overview/{month}'),
            ('riepilogo di gruppo in Excel', admin, 'GET', f'/api/overview/{month}/export.xlsx'),
            ('cose da fare del mese', admin, 'GET', f'/api/todo/{month}'),
            ('coda approvazioni del mese', admin, 'GET', f'/api/approvals/{month}'),
            ('statistiche: 12 mesi, tutte le strutture', admin, 'GET', f'/api/statistics?from={first_month}&to={month}&cid=all'),
            ('statistiche: 12 mesi, una struttura', admin, 'GET', f'/api/statistics?from={first_month}&to={month}&cid={normal_cid}'),
            ('statistiche: 1 mese, tutte le strutture', admin, 'GET', f'/api/statistics?from={month}&to={month}&cid=all'),
            ('personale di gruppo (tutti i dipendenti)', hr_user, 'GET', '/api/workforce'),
            ('archivio documenti (tutte le strutture)', hr_user, 'GET', '/api/documents'),
            ('archivio documenti: una struttura', hr_user, 'GET', f'/api/documents?cid={normal_cid}'),
            ('fascicoli di una struttura', hr_user, 'GET', f'/api/hr/{normal_cid}'),
            ('promemoria (tutte le strutture)', admin, 'GET', '/api/reminders'),
            ('copertura turni di una struttura', mgr_norm, 'GET', f'/api/staffing/{normal_cid}/{month}'),
            ('collaboratori e compensi di una struttura', mgr_norm, 'GET', f'/api/collaborators/{normal_cid}/{month}'),
            ('foglio mensile Excel di una struttura', mgr_norm, 'GET', f'/api/exports/modello/{normal_cid}/{month}'),
            ('anteprima paghe di una struttura', admin, 'GET', f'/api/payroll/{normal_cid}/preview?from={month}&to={month}'),
            ('uscite (tutte le strutture)', hr_user, 'GET', '/api/departures'),
            ('elenco strutture', admin, 'GET', '/api/centers'),
            ('persone di una struttura', mgr_norm, 'GET', f'/api/centers/{normal_cid}/people'),
        ]
        report['reads'] = []
        for label, client, method, path in probes:
            r = measure(client, method, path)
            r['label'] = label
            report['reads'].append(r)
            flag = '' if r['status'] == 200 else f'  [stato {r["status"]}]'
            log(f'  {r["median_ms"]:8.1f} ms  {r["kb"]:8.1f} KB  {label}{flag}')

        log('Confronto SQL sul registro (LIKE del mese contro intervallo BETWEEN)…')
        report['sql'] = dict(history_center=sql_probe(db, hist_cid, month), normal_center=sql_probe(db, normal_cid, month))
        for key, val in report['sql'].items():
            log(f'  {key}: {val["center_rows"]} righe nella struttura; LIKE {val["like"]["median_ms"]} ms, '
                f'BETWEEN {val["between"]["median_ms"]} ms; piano LIKE: {val["like"]["plan"]}')

        log(f'Scritture concorrenti: {a.compilatori} compilatori per {a.secondi} s…')
        writers = []
        for i in range(a.compilatori):
            cid = centers[(20 + i) % len(centers)]
            client = portal.user(f'op{i}', 'operator', [cid])
            writers.append((client, cid, [pid for pid, _, _ in loader.people[cid]]))
        report['writes'] = write_load(portal, writers, a.secondi, month, log)

        log(f'Letture durante le scritture: {max(1, a.compilatori // 2)} compilatori + {max(1, a.compilatori // 2)} lettori…')
        half = max(1, a.compilatori // 2)
        readers = [(portal.login('admin'), centers[(40 + i) % len(centers)]) for i in range(half)]
        report['mixed'] = read_under_writes(portal, writers[:half], readers, a.secondi, month, log)

        log('Backup (copia coerente con verifica) e controllo di integrità…')
        t0 = time.perf_counter()
        target = db.snapshot(reason='carico', directory=a.cartella / 'backup')
        backup_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        con = db.connect()
        try:
            ok = con.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            con.close()
        report['backup'] = dict(seconds=round(backup_s, 1), mb=round(target.stat().st_size / 1024 / 1024, 1),
                                integrity_seconds=round(time.perf_counter() - t0, 1), integrity=ok)
        target.unlink()
        log(f'  backup: {report["backup"]["mb"]} MB in {report["backup"]["seconds"]} s; integrità "{ok}" in '
            f'{report["backup"]["integrity_seconds"]} s')
        report['sizes_after'] = sizes(db)
        report['finished'] = stamp()
    finally:
        if a.conserva:
            log(f'Archivio di prova conservato in {portal.tmp}')
        else:
            portal.close()
    if a.json:
        a.json.write_text(json.dumps(report, ensure_ascii=False, indent=1))
        log(f'Esito salvato in {a.json}')
    return report


if __name__ == '__main__':
    main()
