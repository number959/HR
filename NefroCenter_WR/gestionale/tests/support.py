"""Strumenti comuni alle prove: archivio temporaneo, orologio controllato e client HTTP.

Tutte le prove usano dati fittizi creati qui e cancellati alla fine.
"""
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wr import app as factory  # noqa: E402
from wr import security, users  # noqa: E402
from wr.auth import Auth  # noqa: E402
from wr.util import set_today  # noqa: E402

ORIGIN = 'http://127.0.0.1:8080'
PASSWORD = 'Prova-sicura-2026'
PRODUCTION_ITERATIONS = security.PBKDF2_ITERATIONS
# Le prove usano meno iterazioni per velocità: il valore reale è verificato in test_security.
security.PBKDF2_ITERATIONS = 2000


class Clock:
    """Orologio delle prove: il tempo avanza solo quando lo chiede il test."""

    def __init__(self, start=None):
        self.value = start if start is not None else 1_800_000_000.0

    def __call__(self):
        return self.value

    def advance(self, seconds=31):
        self.value += seconds


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def data(self):
        return json.loads(self.body.decode()) if self.body else None

    def header(self, name):
        return next((v for k, v in self.headers if k.lower() == name.lower()), None)

    def __repr__(self):
        return f'<Response {self.status} {self.body[:300]!r}>'


class Client:
    """Simula un browser: cookie di sessione, token anti-falsificazione e origine."""

    def __init__(self, app, origin=ORIGIN):
        self.app = app
        self.origin = origin
        self.cookie = ''
        self.csrf = ''

    def request(self, method, path, body=None, *, headers=None, raw=None, content_type='application/json'):
        query = ''
        if '?' in path:
            path, query = path.split('?', 1)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b'')
        environ = {
            'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': query, 'REMOTE_ADDR': '127.0.0.1',
            'HTTP_HOST': self.origin.split('://', 1)[1], 'wsgi.input': io.BytesIO(data), 'CONTENT_LENGTH': str(len(data)),
            'CONTENT_TYPE': content_type if data else '', 'wsgi.url_scheme': 'http',
        }
        if self.cookie:
            environ['HTTP_COOKIE'] = f'{self.app.cookie_name}={self.cookie}'
        if method not in ('GET', 'HEAD'):
            environ['HTTP_ORIGIN'] = self.origin
            if self.csrf:
                environ['HTTP_X_WR_TOKEN'] = self.csrf
        for key, value in (headers or {}).items():
            name = 'HTTP_' + key.upper().replace('-', '_')
            if value is None:
                environ.pop(name, None)
            else:
                environ[name] = value
        captured = {}

        def start_response(status, response_headers):
            captured['status'] = int(status.split()[0])
            captured['headers'] = response_headers

        body_out = b''.join(self.app(environ, start_response))
        response = Response(captured['status'], captured['headers'], body_out)
        for key, value in response.headers:
            if key == 'Set-Cookie':
                jar = SimpleCookie()
                jar.load(value)
                self.cookie = jar[self.app.cookie_name].value
        if response.header('Content-Type', ) and response.header('Content-Type').startswith('application/json') and body_out:
            payload = response.data
            if isinstance(payload, dict) and isinstance(payload.get('csrf'), str):
                self.csrf = payload['csrf']
        return response

    def get(self, path, **kw):
        return self.request('GET', path, **kw)

    def post(self, path, body=None, **kw):
        return self.request('POST', path, body if body is not None else {}, **kw)

    def put(self, path, body=None, **kw):
        return self.request('PUT', path, body if body is not None else {}, **kw)

    def delete(self, path, body=None, **kw):
        return self.request('DELETE', path, body if body is not None else {}, **kw)

    def ok(self, method, path, body=None):
        response = self.request(method, path, body)
        if response.status != 200:
            raise AssertionError(f'{method} {path} → {response.status}: {response.body[:500]!r}')
        return response.data


class Portal:
    """Archivio temporaneo con amministratore attivo e funzioni per creare account di prova."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='wr-test-'))
        self.clock = Clock()
        self.key = self.tmp / 'private' / 'server.key'
        Auth.create_key(self.key)
        self.app = factory.create(self.tmp / 'data', origin=ORIGIN, key_file=self.key, dev=True, clock=self.clock)
        self.db = self.app.db
        self.secrets = {}
        code = users.create_first_admin(self.db, self.app.auth, 'admin', 'Amministratore di prova')
        self.admin = self.activate('admin', code)

    def close(self):
        set_today(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def client(self):
        return Client(self.app)

    def code(self, username):
        self.clock.advance(31)
        return security.totp_code(self.secrets[username], int(self.clock() // 30))

    def activate(self, username, activation, password=PASSWORD):
        c = self.client()
        c.ok('GET', '/api/session')
        state = c.ok('POST', '/api/session/activation', {'username': username, 'activation': activation})
        self.secrets[username] = state['setup']['secret']
        done = c.ok('POST', '/api/session/enroll', {'password': password, 'code': self.code(username)})
        c.recovery = done['recovery_codes']
        c.username = username
        return c

    def login(self, username, password=PASSWORD):
        c = self.client()
        c.ok('GET', '/api/session')
        c.ok('POST', '/api/session/login', {'username': username, 'password': password})
        c.ok('POST', '/api/session/verify', {'code': self.code(username)})
        c.username = username
        return c

    def step_up(self, client, password=PASSWORD):
        return client.ok('POST', '/api/session/step-up', {'password': password, 'code': self.code(client.username)})

    def user(self, username, role, centers=(), name=None):
        """Crea un account dall'amministratore e lo attiva; restituisce il client già collegato."""
        self.step_up(self.admin)
        created = self.admin.ok('POST', '/api/users', {'username': username, 'name': name or username.title(),
                                                       'role': role, 'centers': list(centers)})
        return self.activate(username, created['activation_code'])

    def center(self, name='Centro Prova', code='PROVA'):
        self.step_up(self.admin)
        return self.admin.ok('POST', '/api/centers', {'name': name, 'code': code})['id']


class PortalCase(unittest.TestCase):
    def setUp(self):
        self.portal = Portal()
        self.admin = self.portal.admin

    def tearDown(self):
        self.portal.close()

    def assertStatus(self, response, status, text=None):
        self.assertEqual(response.status, status, response.body[:500])
        if text:
            self.assertIn(text, response.data['error']['message'])
        return response
