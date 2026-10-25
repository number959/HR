"""Accesso con password e secondo fattore obbligatorio, sessioni lato server.

Percorsi:
- primo accesso: nome utente + codice di attivazione → password personale + app
  Authenticator → codici di recupero;
- accesso abituale: nome utente + password → codice a 6 cifre (o codice di recupero);
- operazioni sensibili: conferma recente di password e secondo fattore (5 minuti).

I segreti TOTP sono cifrati con la chiave del server (file separato dal database).
Le sessioni sono salvate come impronta: il cookie da solo non è ricostruibile dal DB.
"""
import hmac
import json
import os
import time
from pathlib import Path

from . import security, users
from .errors import Forbidden, Invalid, RateLimited, StepUpRequired, Unauthorized
from .util import stamp, token


class Auth:
    ANON_LIFE = 3600
    PENDING_LIFE = 300
    IDLE = 900
    FULL_LIFE = 8 * 3600
    STEP_UP_WINDOW = 300
    ACTIVATION_DAYS = 7
    MAX_SESSIONS = 20000

    def __init__(self, db, key_file=None, *, clock=time.time, demo=False):
        self.db = db
        self.clock = clock
        self.demo = demo
        self._cipher = None
        if key_file is not None:
            key_file = Path(key_file)
            if not key_file.is_file():
                raise RuntimeError('Chiave del server assente: inizializzare l’installazione oppure ripristinare '
                                   'la chiave originale insieme al database.')
            from cryptography.fernet import Fernet
            self._cipher = Fernet(key_file.read_bytes().strip())
            self._check_key()

    @staticmethod
    def create_key(path):
        from cryptography.fernet import Fernet
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(Fernet.generate_key() + b'\n')

    def _check_key(self):
        from cryptography.fernet import InvalidToken
        with self.db.read() as con:
            for row in con.execute("SELECT totp_secret FROM user_security WHERE totp_secret<>'' LIMIT 20"):
                try:
                    self._cipher.decrypt(row[0].encode())
                except InvalidToken:
                    raise RuntimeError('La chiave del server non corrisponde a questo archivio.') from None

    def _encrypt(self, text):
        if self._cipher is None:
            raise RuntimeError('Chiave del server non configurata.')
        return self._cipher.encrypt(text.encode()).decode()

    def _decrypt(self, value):
        return self._cipher.decrypt(value.encode()).decode()

    # --- registro eventi di sicurezza --------------------------------------------

    def event(self, con, user_id, actor, action, detail=''):
        con.execute('INSERT INTO security_events(at,user_id,actor,action,detail) VALUES(?,?,?,?,?)',
                    (stamp(), user_id, actor, action, str(detail)[:500]))

    # --- limiti ai tentativi --------------------------------------------------------

    def check_rate(self, *keys):
        now = self.clock()
        with self.db.read() as con:
            for key in keys:
                row = con.execute('SELECT blocked_until FROM rate_limits WHERE key=?', (security.digest(key),)).fetchone()
                if row and row[0] > now:
                    raise RateLimited('Troppi tentativi. Attendere cinque minuti e riprovare.')

    def fail(self, key, limit=5, window=300, block=300):
        """Registra un tentativo fallito in una transazione propria (resta anche se la richiesta fallisce)."""
        now = self.clock(); hashed = security.digest(key)
        with self.db.write() as con:
            con.execute('DELETE FROM rate_limits WHERE started<? AND blocked_until<?', (now - 3600, now))
            row = con.execute('SELECT count, started FROM rate_limits WHERE key=?', (hashed,)).fetchone()
            fresh = row and now - row['started'] < window
            count = row['count'] + 1 if fresh else 1
            started = row['started'] if fresh else now
            con.execute('INSERT OR REPLACE INTO rate_limits(key,count,started,blocked_until) VALUES(?,?,?,?)',
                        (hashed, count, started, now + block if count >= limit else 0))

    def _clear_rate(self, con, key):
        con.execute('DELETE FROM rate_limits WHERE key=?', (security.digest(key),))

    # --- sessioni -------------------------------------------------------------------

    def _new(self, con, user_id=None, stage='anonymous', generation=0, verified=0.0):
        now = self.clock()
        con.execute('DELETE FROM sessions WHERE expires<? OR (stage=? AND touched<?)', (now, 'full', now - self.IDLE))
        if con.execute('SELECT count(*) FROM sessions').fetchone()[0] >= self.MAX_SESSIONS:
            raise RateLimited('Servizio momentaneamente occupato. Riprovare fra qualche minuto.')
        life = self.FULL_LIFE if stage == 'full' else self.PENDING_LIFE if user_id else self.ANON_LIFE
        raw = token(32)
        con.execute('INSERT INTO sessions(id,csrf,user_id,stage,generation,created,touched,expires,verified) VALUES(?,?,?,?,?,?,?,?,?)',
                    (security.digest(raw), token(24), user_id, stage, generation, now, now, now + life, verified))
        return raw, dict(con.execute('SELECT * FROM sessions WHERE id=?', (security.digest(raw),)).fetchone())

    def _replace(self, con, session, **kwargs):
        con.execute('DELETE FROM sessions WHERE id=?', (session['id'],))
        return self._new(con, **kwargs)

    def session(self, raw, *, touch=True):
        if not raw or len(raw) > 200:
            raise Unauthorized('Sessione scaduta. Accedere di nuovo.')
        now = self.clock()
        with self.db.write() as con:
            row = con.execute('SELECT * FROM sessions WHERE id=?', (security.digest(raw),)).fetchone()
            expired = (not row or row['expires'] <= now or (row['stage'] == 'full' and now - row['touched'] > self.IDLE))
            if expired:
                if row:
                    con.execute('DELETE FROM sessions WHERE id=?', (row['id'],))
                raise Unauthorized('Sessione scaduta. Accedere di nuovo.')
            if row['user_id']:
                sec = con.execute('''SELECT u.active, s.generation FROM users u JOIN user_security s ON s.user_id=u.id
                                     WHERE u.id=?''', (row['user_id'],)).fetchone()
                if not sec or not sec['active'] or sec['generation'] != row['generation']:
                    con.execute('DELETE FROM sessions WHERE id=?', (row['id'],))
                    raise Unauthorized('Accesso revocato o aggiornato. Accedere di nuovo.')
            if touch:
                con.execute('UPDATE sessions SET touched=? WHERE id=?', (now, row['id']))
            return dict(row)

    def ensure(self, raw):
        """Sessione esistente oppure una nuova sessione anonima (con token anti-falsificazione)."""
        try:
            return self.session(raw, touch=False), None
        except Unauthorized:
            with self.db.write() as con:
                new_raw, row = self._new(con)
            return row, new_raw

    def user(self, session):
        if session['stage'] != 'full':
            raise Unauthorized('Completare l’accesso con il secondo fattore.')
        with self.db.read() as con:
            return users.load(con, session['user_id'])

    def state(self, session):
        out = dict(stage=session['stage'], csrf=session['csrf'], user=None, recovery_remaining=None,
                   configured=self._configured(), demo=self.demo)
        if session['stage'] == 'full':
            with self.db.read() as con:
                user = users.load(con, session['user_id'])
                sec = con.execute('SELECT recovery FROM user_security WHERE user_id=?', (user.id,)).fetchone()
            out.update(user=user.public(), recovery_remaining=len(json.loads(sec['recovery'])) if sec else 0)
        return out

    def _configured(self):
        with self.db.read() as con:
            return bool(con.execute('SELECT 1 FROM users LIMIT 1').fetchone())

    def _security(self, con, user_id):
        con.execute('INSERT OR IGNORE INTO user_security(user_id) VALUES(?)', (user_id,))
        return con.execute('SELECT * FROM user_security WHERE user_id=?', (user_id,)).fetchone()

    # --- accesso abituale ------------------------------------------------------------

    def login(self, session, username, password, peer=''):
        name = str(username or '').strip().casefold()[:60]
        keys = ('password:' + name, 'peer:' + peer)
        self.check_rate(*keys)
        with self.db.read() as con:
            row = con.execute('SELECT * FROM users WHERE username=? AND active=1', (name,)).fetchone()
        if row is None:
            security.burn_password_time()
        if row is None or not security.verify_password(password, row['password']):
            self.fail(keys[0]); self.fail(keys[1], limit=30)
            raise Unauthorized('Nome utente o password non corretti.')
        with self.db.write() as con:
            current = con.execute('SELECT password, active FROM users WHERE id=?', (row['id'],)).fetchone()
            if not current or not current['active'] or current['password'] != row['password']:
                raise Unauthorized('Accesso aggiornato nel frattempo. Riprovare.')
            sec = self._security(con, row['id'])
            if not sec['totp_enabled']:
                raise Forbidden('Account non ancora attivato: scegliere «Primo accesso» e inserire il codice di attivazione.')
            raw, new = self._replace(con, session, user_id=row['id'], stage='password', generation=sec['generation'])
            self._clear_rate(con, keys[0])
        return self.state(new), raw

    def verify(self, session, code, recovery=False):
        if session['stage'] != 'password':
            raise Forbidden('Prima inserire nome utente e password.')
        key = 'mfa:' + session['user_id']
        self.check_rate(key)
        good = False
        with self.db.write() as con:
            sec = self._security(con, session['user_id'])
            if sec['generation'] != session['generation']:
                raise Unauthorized('Accesso scaduto. Ricominciare.')
            good = self._consume(con, sec, code, recovery is True)
            if good:
                raw, new = self._replace(con, session, user_id=session['user_id'], stage='full',
                                         generation=sec['generation'], verified=self.clock())
                con.execute('UPDATE user_security SET last_login=? WHERE user_id=?', (stamp(), session['user_id']))
                name = con.execute('SELECT username FROM users WHERE id=?', (session['user_id'],)).fetchone()[0]
                self.event(con, session['user_id'], name, 'Accesso con codice di recupero' if recovery is True else 'Accesso completato')
                self._clear_rate(con, key)
        if not good:
            self.fail(key)
            raise Invalid('Codice non valido o già usato. Attendere il codice successivo oppure usare un codice di recupero.',
                          field='code')
        return self.state(new), raw

    def _consume(self, con, sec, code, recovery):
        """Verifica e consuma un codice TOTP o di recupero nella transazione corrente."""
        if not sec['totp_enabled'] or not sec['totp_secret']:
            return False
        if recovery:
            value = security.normalize_recovery(code)
            if not value:
                return False
            hashes = json.loads(sec['recovery'])
            wanted = security.digest(value)
            match = next((h for h in hashes if hmac.compare_digest(h, wanted)), None)
            if not match:
                return False
            hashes.remove(match)
            con.execute('UPDATE user_security SET recovery=? WHERE user_id=?', (json.dumps(hashes), sec['user_id']))
            return True
        step = security.totp_match(self._decrypt(sec['totp_secret']), code, self.clock(), sec['totp_last_step'])
        if step is None:
            return False
        con.execute('UPDATE user_security SET totp_last_step=? WHERE user_id=?', (step, sec['user_id']))
        return True

    def logout(self, session):
        with self.db.write() as con:
            raw, new = self._replace(con, session)
        return self.state(new), raw

    # --- primo accesso -----------------------------------------------------------------

    def activation_start(self, session, username, code, peer=''):
        name = str(username or '').strip().casefold()[:60]
        keys = ('activation:' + name, 'peer:' + peer)
        self.check_rate(*keys)
        code = str(code or '').strip()
        with self.db.write() as con:
            row = con.execute('SELECT * FROM users WHERE username=? AND active=1', (name,)).fetchone()
            sec = self._security(con, row['id']) if row else None
            valid = bool(sec and sec['activation_hash'] and self.clock() <= sec['activation_until']
                         and hmac.compare_digest(security.digest(code), sec['activation_hash']))
            if valid:
                secret = security.new_totp_secret()
                raw, new = self._replace(con, session, user_id=row['id'], stage='enroll', generation=sec['generation'])
                con.execute('UPDATE sessions SET pending_secret=?, pending_until=? WHERE id=?',
                            (self._encrypt(secret), self.clock() + self.PENDING_LIFE, new['id']))
                self._clear_rate(con, keys[0])
        if not valid:
            self.fail(keys[0]); self.fail(keys[1], limit=30)
            raise Invalid('Nome utente o codice di attivazione non validi, oppure codice scaduto. '
                          'Chiedere un nuovo codice all’amministratore.', field='activation')
        state = self.state(new)
        uri = security.provisioning_uri(secret, name)
        state.update(setup=dict(secret=secret, uri=uri, qr=security.qr_svg_data_uri(uri), issuer=security.ISSUER, account=name))
        return state, raw

    def enroll(self, session, password, code):
        if session['stage'] != 'enroll':
            raise Forbidden('Attivazione non disponibile: ricominciare dal primo accesso.')
        key = 'enroll:' + session['user_id']
        self.check_rate(key)
        with self.db.read() as con:
            username = con.execute('SELECT username FROM users WHERE id=?', (session['user_id'],)).fetchone()[0]
        credential = security.hash_password(password, username)
        good = False
        with self.db.write() as con:
            row = con.execute('SELECT * FROM sessions WHERE id=?', (session['id'],)).fetchone()
            sec = self._security(con, session['user_id'])
            if (not row or not row['pending_secret'] or row['pending_until'] < self.clock()
                    or sec['generation'] != session['generation']):
                raise Unauthorized('Attivazione scaduta: ricominciare dal primo accesso.')
            secret = self._decrypt(row['pending_secret'])
            step = security.totp_match(secret, code, self.clock())
            if step is not None:
                good = True
                codes, hashes = security.new_recovery_codes()
                generation = sec['generation'] + 1
                con.execute('''UPDATE user_security SET totp_secret=?, totp_enabled=1, totp_last_step=?, recovery=?,
                               activation_hash='', activation_until=0, generation=?, last_login=? WHERE user_id=?''',
                            (self._encrypt(secret), step, json.dumps(hashes), generation, stamp(), session['user_id']))
                con.execute('UPDATE users SET password=?, updated_at=? WHERE id=?', (credential, stamp(), session['user_id']))
                con.execute('DELETE FROM sessions WHERE user_id=?', (session['user_id'],))
                raw, new = self._new(con, user_id=session['user_id'], stage='full', generation=generation, verified=self.clock())
                self.event(con, session['user_id'], username, 'Account attivato con secondo fattore')
                self._clear_rate(con, key)
        if not good:
            self.fail(key)
            raise Invalid('Codice non valido: controllare che l’ora del telefono sia corretta e riprovare.', field='code')
        state = self.state(new)
        state['recovery_codes'] = codes
        return state, raw

    # --- conferma recente per operazioni sensibili -----------------------------------

    def step_up(self, session, password, code, recovery=False):
        user = self.user(session)
        key = 'stepup:' + user.id
        self.check_rate(key)
        with self.db.read() as con:
            stored = con.execute('SELECT password FROM users WHERE id=?', (user.id,)).fetchone()[0]
        if not security.verify_password(password, stored):
            self.fail(key)
            raise Invalid('Password non corretta.', field='password')
        good = False
        with self.db.write() as con:
            sec = self._security(con, user.id)
            if sec['generation'] != session['generation']:
                raise Unauthorized('Sessione revocata. Accedere di nuovo.')
            good = self._consume(con, sec, code, recovery is True)
            if good:
                con.execute('UPDATE sessions SET verified=? WHERE id=?', (self.clock(), session['id']))
                self.event(con, user.id, user.username, 'Conferma di sicurezza')
                self._clear_rate(con, key)
        if not good:
            self.fail(key)
            raise Invalid('Codice non valido o già usato.', field='code')
        return dict(ok=True, valid_seconds=self.STEP_UP_WINDOW)

    def require_recent(self, session):
        self.user(session)
        if self.clock() - session['verified'] > self.STEP_UP_WINDOW:
            raise StepUpRequired('Per questa operazione confermare password e codice dell’app Authenticator.')

    # --- sicurezza del proprio account ------------------------------------------------

    def status(self, session):
        user = self.user(session)
        now = self.clock()
        with self.db.read() as con:
            sec = con.execute('SELECT * FROM user_security WHERE user_id=?', (user.id,)).fetchone()
            sessions = con.execute("SELECT count(*) FROM sessions WHERE user_id=? AND stage='full' AND expires>? AND touched>?",
                                   (user.id, now, now - self.IDLE)).fetchone()[0]
            history = [dict(at=r['at'], action=r['action']) for r in con.execute(
                'SELECT at, action FROM security_events WHERE user_id=? ORDER BY id DESC LIMIT 20', (user.id,))]
        return dict(two_factor=bool(sec['totp_enabled']), recovery_remaining=len(json.loads(sec['recovery'])),
                    sessions=sessions, history=history, last_login=sec['last_login'],
                    recent=now - session['verified'] <= self.STEP_UP_WINDOW)

    def regenerate_recovery(self, session):
        self.require_recent(session)
        user = self.user(session)
        codes, hashes = security.new_recovery_codes()
        with self.db.write() as con:
            con.execute('UPDATE user_security SET recovery=? WHERE user_id=?', (json.dumps(hashes), user.id))
            self.event(con, user.id, user.username, 'Codici di recupero rigenerati')
        return dict(recovery_codes=codes)

    def rotate_start(self, session):
        self.require_recent(session)
        user = self.user(session)
        secret = security.new_totp_secret()
        with self.db.write() as con:
            con.execute('UPDATE sessions SET pending_secret=?, pending_until=? WHERE id=?',
                        (self._encrypt(secret), self.clock() + self.PENDING_LIFE, session['id']))
        uri = security.provisioning_uri(secret, user.username)
        return dict(secret=secret, uri=uri, qr=security.qr_svg_data_uri(uri), issuer=security.ISSUER, account=user.username)

    def rotate_confirm(self, session, code):
        self.require_recent(session)
        user = self.user(session)
        key = 'rotate:' + user.id
        self.check_rate(key)
        good = False
        with self.db.write() as con:
            row = con.execute('SELECT * FROM sessions WHERE id=?', (session['id'],)).fetchone()
            if not row or not row['pending_secret'] or row['pending_until'] < self.clock():
                raise Invalid('Configurazione scaduta: ripetere la procedura.')
            secret = self._decrypt(row['pending_secret'])
            step = security.totp_match(secret, code, self.clock())
            if step is not None:
                good = True
                codes, hashes = security.new_recovery_codes()
                sec = self._security(con, user.id)
                generation = sec['generation'] + 1
                con.execute('UPDATE user_security SET totp_secret=?, totp_last_step=?, recovery=?, generation=? WHERE user_id=?',
                            (self._encrypt(secret), step, json.dumps(hashes), generation, user.id))
                con.execute('DELETE FROM sessions WHERE user_id=?', (user.id,))
                raw, new = self._new(con, user_id=user.id, stage='full', generation=generation, verified=self.clock())
                self.event(con, user.id, user.username, 'App Authenticator sostituita')
                self._clear_rate(con, key)
        if not good:
            self.fail(key)
            raise Invalid('Codice del nuovo dispositivo non valido.', field='code')
        state = self.state(new)
        state['recovery_codes'] = codes
        return state, raw

    def change_password(self, session, current, new_password):
        user = self.user(session)
        key = 'password-change:' + user.id
        self.check_rate(key)
        with self.db.read() as con:
            stored = con.execute('SELECT password FROM users WHERE id=?', (user.id,)).fetchone()[0]
        if not security.verify_password(current, stored):
            self.fail(key)
            raise Invalid('Password attuale non corretta.', field='current')
        credential = security.hash_password(new_password, user.username)
        with self.db.write() as con:
            sec = self._security(con, user.id)
            generation = sec['generation'] + 1
            con.execute('UPDATE users SET password=?, updated_at=? WHERE id=?', (credential, stamp(), user.id))
            con.execute('UPDATE user_security SET generation=? WHERE user_id=?', (generation, user.id))
            con.execute('DELETE FROM sessions WHERE user_id=?', (user.id,))
            raw, new = self._new(con, user_id=user.id, stage='full', generation=generation, verified=session['verified'])
            self.event(con, user.id, user.username, 'Password cambiata')
        return self.state(new), raw

    def revoke_other_sessions(self, session):
        self.require_recent(session)
        user = self.user(session)
        with self.db.write() as con:
            con.execute('DELETE FROM sessions WHERE user_id=? AND id<>?', (user.id, session['id']))
            self.event(con, user.id, user.username, 'Altre sessioni chiuse')
        return dict(ok=True)

    # --- strumenti per l'amministrazione (sulla connessione del chiamante) -------------

    def issue_activation(self, con, user_id, actor, reason):
        """Nuovo codice di attivazione valido 7 giorni: azzera secondo fattore, recupero e sessioni."""
        code = token(24)
        self._security(con, user_id)
        con.execute('''UPDATE user_security SET totp_secret='', totp_enabled=0, totp_last_step=-1, recovery='[]',
                       activation_hash=?, activation_until=?, generation=generation+1 WHERE user_id=?''',
                    (security.digest(code), self.clock() + self.ACTIVATION_DAYS * 86400, user_id))
        con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
        name = con.execute('SELECT username FROM users WHERE id=?', (user_id,)).fetchone()[0]
        self.event(con, user_id, getattr(actor, 'username', 'console'), 'Codice di attivazione emesso', f'{name}: {reason}')
        return code

    def revoke_sessions(self, con, user_id):
        self._security(con, user_id)
        con.execute('UPDATE user_security SET generation=generation+1 WHERE user_id=?', (user_id,))
        con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

    # --- demo pubblica ----------------------------------------------------------------------

    def demo_login(self, session, user_id):
        """Solo nella demo (Auth creato con demo=True): profilo fittizio senza password."""
        if not self.demo:
            raise Forbidden('Accesso dimostrativo non disponibile.')
        with self.db.write() as con:
            sec = self._security(con, user_id)
            raw, new = self._replace(con, session, user_id=user_id, stage='full', generation=sec['generation'],
                                     verified=self.clock())
        return self.state(new), raw



# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402  (registrazione delle rotte dopo la definizione della classe)


def _peer(ctx):
    return ctx.req.remote_addr


@route('GET', '/api/session', auth='session')
def api_session(ctx):
    return ctx.app.auth.state(ctx.session)


@route('POST', '/api/session/login', auth='session')
def api_login(ctx):
    body = ctx.body
    return ctx.app.auth.login(ctx.session, body.get('username'), body.get('password'), _peer(ctx))


@route('POST', '/api/session/verify', auth='session')
def api_verify(ctx):
    body = ctx.body
    return ctx.app.auth.verify(ctx.session, body.get('code'), body.get('recovery') is True)


@route('POST', '/api/session/activation', auth='session')
def api_activation(ctx):
    body = ctx.body
    return ctx.app.auth.activation_start(ctx.session, body.get('username'), body.get('activation'), _peer(ctx))


@route('POST', '/api/session/enroll', auth='session')
def api_enroll(ctx):
    body = ctx.body
    return ctx.app.auth.enroll(ctx.session, body.get('password'), body.get('code'))


@route('POST', '/api/session/logout', auth='session')
def api_logout(ctx):
    return ctx.app.auth.logout(ctx.session)


@route('POST', '/api/session/step-up')
def api_step_up(ctx):
    body = ctx.body
    return ctx.app.auth.step_up(ctx.session, body.get('password'), body.get('code'), body.get('recovery') is True)


@route('POST', '/api/session/demo', auth='session')
def api_demo(ctx):
    """Solo demo pubblica: accesso con un profilo fittizio, senza password."""
    if not ctx.app.auth.demo:
        raise Forbidden('Accesso dimostrativo non disponibile.')
    username = str(ctx.body.get('username') or '')
    with ctx.db.read() as con:
        row = con.execute("SELECT id FROM users WHERE username=? AND active=1 AND username LIKE 'demo.%'", (username,)).fetchone()
    if not row:
        raise Invalid('Profilo dimostrativo non trovato.')
    return ctx.app.auth.demo_login(ctx.session, row['id'])


@route('GET', '/api/security')
def api_security(ctx):
    return ctx.app.auth.status(ctx.session)


@route('POST', '/api/security/recovery-codes')
def api_recovery(ctx):
    return ctx.app.auth.regenerate_recovery(ctx.session)


@route('POST', '/api/security/authenticator/start')
def api_rotate_start(ctx):
    return ctx.app.auth.rotate_start(ctx.session)


@route('POST', '/api/security/authenticator/confirm')
def api_rotate_confirm(ctx):
    return ctx.app.auth.rotate_confirm(ctx.session, ctx.body.get('code'))


@route('POST', '/api/security/password')
def api_password(ctx):
    body = ctx.body
    return ctx.app.auth.change_password(ctx.session, body.get('current'), body.get('password'))


@route('POST', '/api/security/sessions/close-others')
def api_close_others(ctx):
    return ctx.app.auth.revoke_other_sessions(ctx.session)
