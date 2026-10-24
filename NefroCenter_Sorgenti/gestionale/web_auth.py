"""Mandatory password + TOTP authentication. Secrets stay on the server.

Only web_server.py exposes this module over HTTP. Sessions, challenges, replay
counters, recovery codes and rate limits survive process restarts in SQLite.
"""
import base64, hashlib, hmac, io, json, os, re, secrets, time
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
import pyotp
import segno
import core


class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message); self.status = status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Auth:
    def __init__(self, key_file, clock=time.time):
        self.clock = clock
        with core.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS web_security(
              user_id TEXT PRIMARY KEY REFERENCES users(id), secret TEXT NOT NULL DEFAULT '',
              enabled INTEGER NOT NULL DEFAULT 0, last_step INTEGER NOT NULL DEFAULT -1,
              recovery TEXT NOT NULL DEFAULT '[]', activation TEXT NOT NULL DEFAULT '',
              activation_until REAL NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
              last_login TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS web_sessions(
              id TEXT PRIMARY KEY, csrf TEXT NOT NULL, user_id TEXT REFERENCES users(id),
              stage TEXT NOT NULL, version INTEGER NOT NULL, created REAL NOT NULL,
              touched REAL NOT NULL, expires REAL NOT NULL, verified REAL NOT NULL DEFAULT 0,
              pending_secret TEXT NOT NULL DEFAULT '', pending_until REAL NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS web_sessions_user ON web_sessions(user_id);
            CREATE TABLE IF NOT EXISTS web_rate(
              id TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL,
              blocked REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS web_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, stamp TEXT NOT NULL, user_id TEXT,
              actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
            ''')
            c.execute('INSERT OR IGNORE INTO web_security(user_id) SELECT id FROM users')
            c.commit()
        key_file = Path(key_file)
        if not key_file.is_file():
            raise ValueError('Chiave 2FA assente. Inizializzare il servizio oppure ripristinare la chiave originale insieme al database.')
        self.cipher = Fernet(key_file.read_bytes().strip())
        with core.connect() as c:
            for r in c.execute("SELECT secret FROM web_security WHERE secret<>''"):
                try: self.cipher.decrypt(r['secret'].encode())
                except InvalidToken as ex: raise ValueError('Chiave non corrispondente al database 2FA.') from ex

    @staticmethod
    def create_key(path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f: f.write(Fernet.generate_key() + b'\n')

    def event(self, c, user, action, detail=''):
        c.execute('INSERT INTO web_events(stamp,user_id,actor,action,detail) VALUES(?,?,?,?,?)',
                  (core.now(), user.get('id'), user.get('username', ''), action, str(detail)[:500]))

    def security(self, c, uid):
        c.execute('INSERT OR IGNORE INTO web_security(user_id) VALUES(?)', (uid,))
        return c.execute('SELECT * FROM web_security WHERE user_id=?', (uid,)).fetchone()

    def _new(self, c, user_id=None, stage='anonymous', version=0, verified=0):
        now = self.clock(); sid = secrets.token_urlsafe(40); csrf = secrets.token_urlsafe(32)
        c.execute('DELETE FROM web_sessions WHERE expires<? OR touched<?', (now, now - 28800))
        count = c.execute('SELECT count(*) FROM web_sessions').fetchone()[0]
        if count >= 10000: raise AuthError('Servizio occupato. Riprovare più tardi.', 429)
        life = 28800 if stage == 'full' else 300 if user_id else 3600
        c.execute('INSERT INTO web_sessions(id,csrf,user_id,stage,version,created,touched,expires,verified) VALUES(?,?,?,?,?,?,?,?,?)',
                  (digest(sid), csrf, user_id, stage, version, now, now, now + life, verified))
        return sid, c.execute('SELECT * FROM web_sessions WHERE id=?', (digest(sid),)).fetchone()

    def _replace(self, c, session, user_id=None, stage='anonymous', version=0, verified=0):
        c.execute('DELETE FROM web_sessions WHERE id=?', (session['id'],))
        return self._new(c, user_id, stage, version, verified)

    def session(self, raw, full=False, touch=True):
        if not raw or len(raw) > 160: raise AuthError('Sessione scaduta. Accedere di nuovo.')
        with core.connect() as c:
            s = c.execute('SELECT * FROM web_sessions WHERE id=?', (digest(raw),)).fetchone()
            now = self.clock()
            if not s or s['expires'] <= now or (s['stage'] == 'full' and now - s['touched'] > 900):
                if s: c.execute('DELETE FROM web_sessions WHERE id=?', (s['id'],)); c.commit()
                raise AuthError('Sessione scaduta. Accedere di nuovo.')
            if s['user_id']:
                row = c.execute('SELECT u.active,s.version FROM users u JOIN web_security s ON s.user_id=u.id WHERE u.id=?', (s['user_id'],)).fetchone()
                if not row or not row['active'] or row['version'] != s['version']:
                    raise AuthError('Accesso revocato. Accedere di nuovo.')
            if full and s['stage'] != 'full': raise AuthError('Completa la verifica a due fattori.', 403)
            if touch:
                c.execute('UPDATE web_sessions SET touched=? WHERE id=?', (now, s['id'])); c.commit()
            return dict(s)

    def browser(self, raw):
        try: return self.session(raw, touch=False), None
        except AuthError:
            with core.connect() as c:
                sid, s = self._new(c); c.commit(); return dict(s), sid

    def user(self, s):
        if s['stage'] != 'full': raise AuthError('Completa la verifica a due fattori.', 403)
        with core.connect() as c:
            r = c.execute('SELECT * FROM users WHERE id=? AND active=1', (s['user_id'],)).fetchone()
            if not r: raise AuthError('Account non disponibile.')
            return core.public_user(r)

    def state(self, s):
        user = self.user(s) if s['stage'] == 'full' else None
        with core.connect() as c:
            configured = bool(c.execute('SELECT 1 FROM users').fetchone())
            centers = core.centers_for(c, user) if user else []
            sec = c.execute('SELECT * FROM web_security WHERE user_id=?', (s['user_id'],)).fetchone() if user else None
        return dict(user=user, centers=centers, stage=s['stage'], csrf=s['csrf'],
                    configured=configured, needs_setup=False, two_factor=True,
                    recovery_remaining=len(json.loads(sec['recovery'])) if sec else None)

    def rate_check(self, *keys):
        now = self.clock()
        with core.connect() as c:
            for key in keys:
                r = c.execute('SELECT * FROM web_rate WHERE id=?', (digest(key),)).fetchone()
                if r and r['blocked'] > now:
                    raise AuthError('Troppi tentativi. Attendi cinque minuti e riprova.', 429)

    def rate_fail(self, key, limit=5, window=300):
        now = self.clock()
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM web_rate WHERE started<? AND blocked<?', (now - 3600, now))
            r = c.execute('SELECT * FROM web_rate WHERE id=?', (digest(key),)).fetchone()
            count = r['count'] + 1 if r and now - r['started'] < window else 1
            started = r['started'] if r and now - r['started'] < window else now
            c.execute('INSERT OR REPLACE INTO web_rate VALUES(?,?,?,?)',
                      (digest(key), count, started, now + 300 if count >= limit else 0)); c.commit()

    def clear_rate(self, c, key):
        c.execute('DELETE FROM web_rate WHERE id=?', (digest(key),))

    def login(self, s, body, peer):
        username = str(body.get('username', '')).strip().casefold()[:60]
        key = 'password:' + username; ipkey = 'peer:' + peer
        self.rate_check(key, ipkey)
        with core.connect() as c: row = c.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
        if row is None:
            hashlib.pbkdf2_hmac('sha256', b'invalid', b'constant-auth-salt', core.ITERATIONS)
        good = row is not None and core.verify_password(body.get('password', ''), row['credential'])
        if not good:
            self.rate_fail(key); self.rate_fail(ipkey, 30)
            raise AuthError('Nome utente o password non corretti.')
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT * FROM users WHERE id=? AND active=1', (row['id'],)).fetchone()
            if not current or current['credential'] != row['credential']: raise AuthError('Accesso aggiornato. Riprova.')
            sec = self.security(c, row['id'])
            stage = 'mfa' if sec['enabled'] else 'enroll'
            sid, out = self._replace(c, s, row['id'], stage, sec['version'])
            self.clear_rate(c, key); self.event(c, dict(row), 'Password verificata; secondo fattore richiesto'); c.commit()
        return self.state(out), sid

    def _codes(self):
        codes = ['-'.join(secrets.token_hex(8).upper()[i:i+4] for i in range(0, 16, 4)) for _ in range(10)]
        return codes, json.dumps([digest(x.replace('-', '')) for x in codes])

    def activation(self, uid, actor, reason):
        code = secrets.token_urlsafe(24)
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not row: raise ValueError('Utente non trovato.')
            self.security(c, uid)
            c.execute("UPDATE web_security SET secret='',enabled=0,last_step=-1,recovery='[]',activation=?,activation_until=?,version=version+1 WHERE user_id=?",
                      (digest(code), self.clock() + 7*86400, uid))
            c.execute('DELETE FROM web_sessions WHERE user_id=?', (uid,))
            self.event(c, actor, 'Attivazione 2FA richiesta', row['username'] + ': ' + reason); c.commit()
        return code

    def _qr(self, secret, username):
        uri = pyotp.TOTP(secret).provisioning_uri(username, issuer_name='NefroCenter Presenze')
        buf = io.BytesIO(); segno.make(uri, micro=False).save(buf, kind='svg', scale=5, border=4, xmldecl=False)
        return {'secret':secret, 'qr':'data:image/svg+xml;base64,' + base64.b64encode(buf.getvalue()).decode(),
                'issuer':'NefroCenter Presenze', 'account':username}

    def enroll_start(self, s, body):
        if s['stage'] != 'enroll': raise AuthError('Attivazione non disponibile.', 403)
        key = 'activation:' + s['user_id']; self.rate_check(key)
        with core.connect() as c: sec = self.security(c, s['user_id']); c.commit()
        code = str(body.get('activation', '')).strip()
        if not sec['activation'] or self.clock() > sec['activation_until'] or not hmac.compare_digest(digest(code), sec['activation']):
            self.rate_fail(key); raise AuthError('Codice di attivazione non valido o scaduto. Contatta l’amministratore.', 400)
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            sec = self.security(c, s['user_id'])
            if sec['version'] != s['version'] or sec['enabled']: raise AuthError('Attivazione modificata. Accedi di nuovo.')
            row = c.execute('SELECT username FROM users WHERE id=?', (s['user_id'],)).fetchone()
            existing = c.execute('SELECT * FROM web_sessions WHERE id=?', (s['id'],)).fetchone()
            if not existing: raise AuthError('Sessione scaduta.')
            secret = self.cipher.decrypt(existing['pending_secret'].encode()).decode() if existing['pending_secret'] and existing['pending_until'] > self.clock() else pyotp.random_base32()
            c.execute('UPDATE web_sessions SET pending_secret=?,pending_until=? WHERE id=?',
                      (self.cipher.encrypt(secret.encode()).decode(), min(s['expires'], self.clock()+300), s['id']))
            self.clear_rate(c, key); c.commit()
        return self._qr(secret, row['username'])

    def _step(self, secret, code, last=-1):
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code): return None
        step = int(self.clock() // 30); totp = pyotp.TOTP(secret)
        for candidate in (step, step-1, step+1):
            if candidate > last and hmac.compare_digest(totp.at(candidate*30), code): return candidate
        return None

    def enroll_confirm(self, s, body):
        if s['stage'] != 'enroll': raise AuthError('Attivazione non disponibile.', 403)
        key = 'mfa:' + s['user_id']; self.rate_check(key)
        password = body.get('new_password', '')
        credential = core.password_hash(password)
        error = False
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            session = c.execute('SELECT * FROM web_sessions WHERE id=?', (s['id'],)).fetchone()
            sec = self.security(c, s['user_id'])
            if not session or not session['pending_secret'] or session['pending_until'] < self.clock() or sec['version'] != s['version'] or sec['enabled']:
                raise AuthError('Attivazione scaduta. Ricomincia l’accesso.')
            secret = self.cipher.decrypt(session['pending_secret'].encode()).decode()
            step = self._step(secret, body.get('code', ''))
            if step is None: error = True
            else:
                codes, hashes = self._codes()
                c.execute("UPDATE web_security SET secret=?,enabled=1,last_step=?,recovery=?,activation='',activation_until=0,version=version+1,last_login=? WHERE user_id=?",
                          (session['pending_secret'], step, hashes, core.now(), s['user_id']))
                c.execute('UPDATE users SET credential=? WHERE id=?', (credential, s['user_id']))
                c.execute('DELETE FROM web_sessions WHERE user_id=?', (s['user_id'],))
                sid, out = self._new(c, s['user_id'], 'full', sec['version']+1, self.clock())
                row = c.execute('SELECT * FROM users WHERE id=?', (s['user_id'],)).fetchone()
                self.clear_rate(c, key); self.event(c, dict(row), '2FA attivato'); c.commit()
        if error:
            self.rate_fail(key); raise AuthError('Codice non valido. Controlla l’ora del telefono e riprova.', 400)
        return {**self.state(out), 'recovery_codes':codes}, sid

    def _consume(self, c, sec, code, recovery=False):
        if not sec['enabled'] or not sec['secret']: return False
        if recovery:
            normalized = str(code).replace('-', '').replace(' ', '').upper()
            if not re.fullmatch('[0-9A-F]{16}', normalized): return False
            hashes = json.loads(sec['recovery']); value = digest(normalized)
            found = next((x for x in hashes if hmac.compare_digest(x, value)), None)
            if not found: return False
            hashes.remove(found)
            c.execute('UPDATE web_security SET recovery=? WHERE user_id=?', (json.dumps(hashes), sec['user_id']))
        else:
            secret = self.cipher.decrypt(sec['secret'].encode()).decode()
            step = self._step(secret, code, sec['last_step'])
            if step is None: return False
            c.execute('UPDATE web_security SET last_step=? WHERE user_id=?', (step, sec['user_id']))
        return True

    def verify(self, s, body):
        if s['stage'] != 'mfa': raise AuthError('Prima verifica la password.', 403)
        key = 'mfa:' + s['user_id']; self.rate_check(key)
        good = False
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE'); sec = self.security(c, s['user_id'])
            live = c.execute('SELECT 1 FROM web_sessions WHERE id=? AND expires>?', (s['id'], self.clock())).fetchone()
            if not live or sec['version'] != s['version']: raise AuthError('Accesso scaduto. Ricomincia.')
            good = self._consume(c, sec, body.get('code', ''), body.get('recovery') is True)
            if good:
                sid, out = self._replace(c, s, s['user_id'], 'full', sec['version'], self.clock())
                c.execute('UPDATE web_security SET last_login=? WHERE user_id=?', (core.now(), s['user_id']))
                row = c.execute('SELECT * FROM users WHERE id=?', (s['user_id'],)).fetchone()
                self.clear_rate(c, key); self.event(c, dict(row), 'Accesso con codice di recupero' if body.get('recovery') is True else 'Accesso 2FA completato'); c.commit()
        if not good:
            self.rate_fail(key); raise AuthError('Codice non valido o già usato. Attendi il prossimo codice oppure usa un codice di recupero.', 400)
        return self.state(out), sid

    def logout(self, s):
        with core.connect() as c:
            sid, out = self._replace(c, s); c.commit()
        return self.state(out), sid

    def revoke(self, uid):
        with core.connect() as c:
            self.security(c, uid)
            c.execute('UPDATE web_security SET version=version+1 WHERE user_id=?', (uid,))
            c.execute('DELETE FROM web_sessions WHERE user_id=?', (uid,)); c.commit()

    def stepup(self, s, body):
        user = self.user(s); key = 'stepup:' + user['id']; self.rate_check(key)
        with core.connect() as c: row = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        if not core.verify_password(body.get('password', ''), row['credential']):
            self.rate_fail(key); raise AuthError('Verifica di sicurezza non riuscita.', 400)
        good = False
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE'); sec = self.security(c, user['id'])
            if sec['version'] != s['version']: raise AuthError('Sessione revocata.')
            good = self._consume(c, sec, body.get('code', ''), body.get('recovery') is True)
            if good:
                c.execute('UPDATE web_sessions SET verified=? WHERE id=?', (self.clock(), s['id']))
                self.clear_rate(c, key); self.event(c, user, 'Conferma sicurezza'); c.commit()
        if not good:
            self.rate_fail(key); raise AuthError('Verifica non riuscita: codice non valido o già usato.', 400)
        return {'ok':True}

    def require_recent(self, s):
        self.user(s)
        if self.clock() - s['verified'] > 300:
            raise AuthError('Conferma password e secondo fattore per questa operazione.', 428)

    def recovery_new(self, s):
        self.require_recent(s); user = self.user(s); codes, hashes = self._codes()
        with core.connect() as c:
            c.execute('UPDATE web_security SET recovery=? WHERE user_id=?', (hashes, user['id']))
            self.event(c, user, 'Codici di recupero rigenerati'); c.commit()
        return {'recovery_codes':codes}

    def rotate_start(self, s):
        self.require_recent(s); user = self.user(s); secret = pyotp.random_base32()
        with core.connect() as c:
            c.execute('UPDATE web_sessions SET pending_secret=?,pending_until=? WHERE id=?',
                      (self.cipher.encrypt(secret.encode()).decode(), self.clock()+300, s['id'])); c.commit()
        return self._qr(secret, user['username'])

    def rotate_confirm(self, s, body):
        self.require_recent(s); user = self.user(s); key = 'rotation:' + user['id']; self.rate_check(key)
        error = False
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE'); sec = self.security(c, user['id'])
            row = c.execute('SELECT * FROM web_sessions WHERE id=?', (s['id'],)).fetchone()
            if not row or not row['pending_secret'] or row['pending_until'] < self.clock(): raise AuthError('Configurazione scaduta.', 400)
            secret = self.cipher.decrypt(row['pending_secret'].encode()).decode()
            step = self._step(secret, body.get('code', ''))
            if step is None: error = True
            else:
                codes, hashes = self._codes()
                c.execute('UPDATE web_security SET secret=?,last_step=?,recovery=?,version=version+1 WHERE user_id=?', (row['pending_secret'], step, hashes, user['id']))
                c.execute('DELETE FROM web_sessions WHERE user_id=?', (user['id'],))
                sid, out = self._new(c, user['id'], 'full', sec['version']+1, self.clock())
                self.clear_rate(c, key); self.event(c, user, 'App Authenticator sostituita'); c.commit()
        if error:
            self.rate_fail(key); raise AuthError('Codice del nuovo dispositivo non valido.', 400)
        return {**self.state(out), 'recovery_codes':codes}, sid

    def status(self, s):
        user = self.user(s)
        with core.connect() as c:
            sec = self.security(c, user['id'])
            sessions = c.execute("SELECT count(*) FROM web_sessions WHERE user_id=? AND stage='full' AND expires>? AND touched>?", (user['id'], self.clock(), self.clock()-900)).fetchone()[0]
            history = [dict(r) for r in c.execute('SELECT stamp,action FROM web_events WHERE user_id=? ORDER BY id DESC LIMIT 15', (user['id'],))]
            c.commit()
        return {'enabled':bool(sec['enabled']), 'recovery_remaining':len(json.loads(sec['recovery'])), 'sessions':sessions, 'history':history, 'recent':self.clock()-s['verified']<=300}

    def other_sessions(self, s):
        self.require_recent(s)
        with core.connect() as c:
            c.execute('DELETE FROM web_sessions WHERE user_id=? AND id<>?', (s['user_id'], s['id']))
            self.event(c, self.user(s), 'Altre sessioni revocate'); c.commit()
        return {'ok':True}
