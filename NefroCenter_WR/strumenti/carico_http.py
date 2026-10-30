"""Prova di carico via HTTP reale (Waitress) su un archivio DI PROVA: confronta il servizio con un
processo solo e con più processi di lavoro (--processes), con lettori e compilatori contemporanei.

Uso (dalla cartella NefroCenter_WR), con l'archivio creato da strumenti/carico_archivio.py --conserva:
  python3 strumenti/carico_http.py --dati CARTELLA/data --chiave CARTELLA/private/server.key --processi 1 4 --lettori 6 --scrittori 2

Lo script crea un nuovo codice di attivazione per l'account indicato (--utente, predefinito admin),
lo attiva via HTTP come farebbe la persona (password nuova e app Authenticator simulata) e poi lancia
processi client separati. Va usato SOLO su archivi di prova con dati fittizi: revoca gli accessi
dell'account e scrive registrazioni nel mese corrente.
"""
import argparse
import http.client
import json
import multiprocessing as mp
import random
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import date
from http.cookies import SimpleCookie
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'gestionale'
sys.path.insert(0, str(ROOT))

from wr import app as factory, security  # noqa: E402
from wr.permissions import User  # noqa: E402

PASSWORD = 'Prova-carico-2026'


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))], 1)


class Session:
    """Client HTTP minimo con cookie di sessione e token anti-falsificazione."""

    def __init__(self, port):
        self.port = port
        self.cookie = ''
        self.csrf = ''
        self.conn = None

    def request(self, method, path, body=None):
        if self.conn is None:
            self.conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=120)
        headers = {'Origin': f'http://127.0.0.1:{self.port}'}
        if self.cookie:
            headers['Cookie'] = self.cookie
        if method != 'GET':
            headers['Content-Type'] = 'application/json'
            if self.csrf:
                headers['X-WR-Token'] = self.csrf
        data = json.dumps(body).encode() if body is not None else None
        try:
            self.conn.request(method, path, body=data, headers=headers)
            r = self.conn.getresponse()
            payload = r.read()
        except (http.client.HTTPException, OSError):
            self.conn.close()
            self.conn = None
            raise
        for value in r.headers.get_all('Set-Cookie') or []:
            jar = SimpleCookie()
            jar.load(value)
            for key, morsel in jar.items():
                self.cookie = f'{key}={morsel.value}'
        if r.headers.get('Content-Type', '').startswith('application/json') and payload:
            parsed = json.loads(payload)
            if isinstance(parsed, dict) and isinstance(parsed.get('csrf'), str):
                self.csrf = parsed['csrf']
            return r.status, parsed, len(payload)
        return r.status, None, len(payload)


def issue_activation(data_dir, key_file, username, origin):
    application = factory.create(data_dir, origin=origin, key_file=key_file, dev=True, migrate=False)
    with application.db.write() as con:
        row = con.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if not row:
            raise SystemExit(f'Account {username} non trovato nell’archivio di prova.')
        code = application.auth.issue_activation(con, row[0], User(id='', username='console', name='Console', role='admin'),
                                                 'Prova di carico HTTP (archivio di prova, dati fittizi)')
    return code


def skip_todays_backup(data_dir):
    """Il servizio fa un backup al giorno appena parte: su un archivio di prova da 1,5 GB falserebbe la misura.
    Una copia fittizia con il nome di oggi gli fa saltare quella di avvio."""
    folder = data_dir / 'backups'
    folder.mkdir(exist_ok=True)
    marker = folder / ('wr_' + date.today().strftime('%Y%m%d') + '_000000_000000.sqlite3')
    if not marker.exists():
        con = sqlite3.connect(marker)
        con.execute('CREATE TABLE prova(x)')
        con.commit()
        con.close()
    return marker


def start_server(data_dir, key_file, port, processes, threads):
    cmd = [sys.executable, '-m', 'wr.server', '--data-dir', str(data_dir), '--key-file', str(key_file),
           '--origin', f'http://127.0.0.1:{port}', '--dev-http', '--port', str(port), '--processes', str(processes),
           '--threads', str(threads)]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            s = Session(port)
            status, _, _ = s.request('GET', '/api/session')
            if status == 200:
                return proc
        except OSError:
            pass
        if proc.poll() is not None:
            raise SystemExit('Il servizio si è fermato subito dopo l’avvio.')
        time.sleep(0.3)
    proc.kill()
    raise SystemExit('Il servizio non risponde sulla porta indicata.')


def login(port, username, code):
    s = Session(port)
    s.request('GET', '/api/session')
    status, state, _ = s.request('POST', '/api/session/activation', dict(username=username, activation=code))
    if status != 200:
        raise SystemExit(f'Attivazione non riuscita: {status} {state}')
    secret = state['setup']['secret']
    totp = security.totp_code(secret, int(time.time() // 30))
    status, done, _ = s.request('POST', '/api/session/enroll', dict(password=PASSWORD, code=totp))
    if status != 200:
        raise SystemExit(f'Registrazione del secondo fattore non riuscita: {status} {done}')
    return s.cookie, s.csrf


def reader(port, cookie, csrf, cid, month, seconds, out):
    s = Session(port)
    s.cookie, s.csrf = cookie, csrf
    lat, bad, kb = [], 0, 0
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        t0 = time.perf_counter()
        try:
            status, _, size = s.request('GET', f'/api/attendance/{cid}/{month}')
        except OSError:
            bad += 1
            continue
        lat.append((time.perf_counter() - t0) * 1000)
        kb = size / 1024
        if status != 200:
            bad += 1
    out.put(('r', lat, bad, kb))


def writer(port, cookie, csrf, db_path, cid, month, seconds, out, seed):
    s = Session(port)
    s.cookie, s.csrf = cookie, csrf
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    people = [r[0] for r in con.execute('SELECT id FROM people WHERE center_id=?', (cid,))]
    taken = {tuple(r) for r in con.execute("SELECT person_id, day, slot FROM entries WHERE center_id=? AND layer='actual' "
                                           'AND day>=? AND day<=?', (cid, month + '-01', month + '-31'))}
    con.close()
    rng = random.Random(seed)
    today = date.today().day if date.today().isoformat()[:7] == month else 28
    lat, rejected, bad, skipped = [], 0, 0, 0
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        key = (rng.choice(people), f'{month}-{rng.randint(1, today):02d}', rng.choice('mpn'))
        if key in taken:
            skipped += 1
            if skipped > 200_000:  # struttura ormai piena: nessuna casella libera da registrare
                break
            continue
        taken.add(key)
        t0 = time.perf_counter()
        try:
            status, _, _ = s.request('POST', f'/api/attendance/{cid}/{month}/entries',
                                     dict(person_id=key[0], day=key[1], slot=key[2], layer='actual', code=key[2]))
        except OSError:
            bad += 1
            continue
        if status == 200:
            lat.append((time.perf_counter() - t0) * 1000)
        elif status == 400:
            rejected += 1
        else:
            bad += 1
    out.put(('w', lat, rejected, bad))


def scenario(port, cookie, csrf, db_path, centers, month, readers, writers, seconds):
    out = mp.Queue()
    procs = [mp.Process(target=reader, args=(port, cookie, csrf, centers[(40 + i) % len(centers)], month, seconds, out))
             for i in range(readers)]
    procs += [mp.Process(target=writer, args=(port, cookie, csrf, db_path, centers[(10 + i) % len(centers)], month, seconds, out, i))
              for i in range(writers)]
    for p in procs:
        p.start()
    r_lat, r_bad, w_lat, w_rej, w_bad, kb = [], 0, [], 0, 0, 0
    for _ in procs:
        item = out.get()
        if item[0] == 'r':
            r_lat.extend(item[1])
            r_bad += item[2]
            kb = item[3]
        else:
            w_lat.extend(item[1])
            w_rej += item[2]
            w_bad += item[3]
    for p in procs:
        p.join()
    return dict(readers=readers, writers=writers, seconds=seconds, reads=len(r_lat), read_errors=r_bad, read_kb=round(kb, 1),
                read_p50_ms=pct(r_lat, 50), read_p95_ms=pct(r_lat, 95), read_max_ms=pct(r_lat, 100),
                reads_per_second=round(len(r_lat) / seconds, 1), writes=len(w_lat), writes_per_second=round(len(w_lat) / seconds, 1),
                write_rejected=w_rej, write_errors=w_bad, write_p50_ms=pct(w_lat, 50), write_p95_ms=pct(w_lat, 95))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--dati', type=Path, required=True, help='cartella data dell’archivio di prova')
    p.add_argument('--chiave', type=Path, required=True, help='chiave del server dell’archivio di prova')
    p.add_argument('--utente', default='admin')
    p.add_argument('--porta', type=int, default=8097)
    p.add_argument('--processi', type=int, nargs='+', default=[1, 4])
    p.add_argument('--thread', type=int, default=8)
    p.add_argument('--lettori', type=int, default=6)
    p.add_argument('--scrittori', type=int, default=2)
    p.add_argument('--secondi', type=int, default=15)
    p.add_argument('--json', type=Path)
    a = p.parse_args(argv)

    db_path = a.dati / factory.DB_NAME
    if not db_path.exists():
        raise SystemExit('Archivio non trovato nella cartella indicata.')
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    centers = [r[0] for r in con.execute('SELECT id FROM centers ORDER BY code')]
    con.close()
    month = date.today().isoformat()[:7]
    origin = f'http://127.0.0.1:{a.porta}'
    skip_todays_backup(a.dati)
    results = []
    for n in a.processi:
        code = issue_activation(a.dati, a.chiave, a.utente, origin)
        print(f'Avvio il servizio con {n} processo/i e {a.thread} thread…', flush=True)
        proc = start_server(a.dati, a.chiave, a.porta, n, a.thread)
        try:
            cookie, csrf = login(a.porta, a.utente, code)
            for readers, writers in ((1, 0), (a.lettori, 0), (a.lettori, 0), (a.lettori, a.scrittori)):  # la seconda ripetizione misura la variabilità
                r = scenario(a.porta, cookie, csrf, db_path, centers, month, readers, writers, a.secondi)
                r['processes'] = n
                results.append(r)
                print(f'  processi {n} · lettori {readers} · compilatori {writers}: registro p50 {r["read_p50_ms"]} ms, '
                      f'p95 {r["read_p95_ms"]} ms, max {r["read_max_ms"]} ms ({r["reads_per_second"]} aperture/s, '
                      f'{r["read_kb"]} KB, errori {r["read_errors"]}); scritture {r["writes"]} ({r["writes_per_second"]}/s, '
                      f'p95 {r["write_p95_ms"]} ms, rifiutate {r["write_rejected"]}, errori {r["write_errors"]})', flush=True)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
    if a.json:
        a.json.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return results


if __name__ == '__main__':
    mp.set_start_method('fork')
    main()
