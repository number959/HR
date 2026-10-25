"""Applicazione WSGI: instradamento, sicurezza HTTP, file statici ed errori.

Le funzioni dei moduli si registrano con @route. Ogni richiesta API:
1. verifica host e origine; rifiuta richieste da altri siti;
2. carica la sessione (cookie HttpOnly) e, per le scritture, il token anti-falsificazione;
3. controlla autenticazione, permesso e, se richiesto, la conferma di sicurezza recente;
4. restituisce JSON, oppure un file con intestazioni di download sicure.
"""
import hashlib
import json
import logging
import mimetypes
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from . import PRODUCT, VERSION
from .errors import Forbidden, Invalid, NotFound, TooLarge, Unauthorized, WRError
from .permissions import require, require_center

LOG = logging.getLogger('wr.web')
ROUTES = []
STATIC_TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.mp4': 'video/mp4', '.webm': 'video/webm',
    '.vtt': 'text/vtt; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.pdf': 'application/pdf',
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
       "font-src 'self'; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'; object-src 'none'")
UPLOAD_TYPES = {'application/pdf', 'image/png', 'image/jpeg', 'application/octet-stream',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-excel.sheet.macroenabled.12'}
DOCUMENT_CSP = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'self'"
STATUS_TEXT = {200: 'OK', 204: 'No Content', 206: 'Partial Content', 304: 'Not Modified', 400: 'Bad Request',
               401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed', 409: 'Conflict',
               413: 'Content Too Large', 415: 'Unsupported Media Type', 416: 'Range Not Satisfiable',
               428: 'Precondition Required', 429: 'Too Many Requests', 500: 'Internal Server Error'}


@dataclass
class Route:
    method: str
    pattern: str
    handler: object
    auth: str = 'user'
    cap: str = None
    step_up: bool = False
    regex: object = None

    def __post_init__(self):
        parts = re.sub(r'<([a-z_]+)>', r'(?P<\1>[^/]+)', self.pattern)
        self.regex = re.compile('^' + parts + '$')


def route(method, pattern, *, auth='user', cap=None, step_up=False):
    """auth: 'public' (nessuna sessione), 'session' (anche anonima), 'user' (accesso completo)."""
    def register(fn):
        ROUTES.append(Route(method, pattern, fn, auth, cap, step_up))
        return fn
    return register


class Reply:
    """Risposta non JSON (file, CSV, Excel) o con stato diverso da 200."""

    def __init__(self, body=b'', status=200, content_type='application/json; charset=utf-8', *,
                 filename=None, inline=False, headers=None):
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status
        self.content_type = content_type
        self.headers = list(headers or [])
        if filename:
            safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:120] or 'file'
            disposition = 'inline' if inline else 'attachment'
            self.headers.append(('Content-Disposition', f"{disposition}; filename=\"{safe}\"; filename*=UTF-8''{quote(filename)}"))


class Request:
    def __init__(self, environ, max_body):
        self.environ = environ
        self.method = environ.get('REQUEST_METHOD', 'GET').upper()
        self.path = environ.get('PATH_INFO', '/') or '/'
        self.query = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)
        self.max_body = max_body
        self._json = None

    def header(self, name, default=''):
        return self.environ.get('HTTP_' + name.upper().replace('-', '_'), default)

    @property
    def remote_addr(self):
        return self.environ.get('REMOTE_ADDR', '')

    def cookie(self, name):
        jar = SimpleCookie()
        try:
            jar.load(self.environ.get('HTTP_COOKIE', ''))
        except Exception:
            return ''
        return jar[name].value if name in jar else ''

    def raw(self, limit):
        """Contenuto binario (allegati): tipo dichiarato ammesso e dimensione massima."""
        ctype = self.environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
        if ctype not in UPLOAD_TYPES:
            raise WRError('Formato del file non ammesso.', code='media_type')
        length = int(self.environ.get('CONTENT_LENGTH') or 0)
        if length > limit:
            raise TooLarge('File troppo grande.')
        return self.environ['wsgi.input'].read(length) if length else b''

    def json(self):
        if self._json is not None:
            return self._json
        length = int(self.environ.get('CONTENT_LENGTH') or 0)
        if length == 0:
            self._json = {}
            return self._json
        if length > self.max_body:
            raise TooLarge('Richiesta troppo grande.')
        if self.environ.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
            raise WRError('Inviare i dati in formato JSON.', code='media_type')
        try:
            data = json.loads(self.environ['wsgi.input'].read(length))
        except ValueError:
            raise Invalid('Dati JSON non leggibili.') from None
        if not isinstance(data, dict):
            raise Invalid('Formato dei dati non valido.')
        self._json = data
        return data


@dataclass
class Context:
    app: object
    req: Request
    session: dict = None
    user: object = None
    params: dict = field(default_factory=dict)
    cookie: str = None

    @property
    def db(self):
        return self.app.db

    @property
    def body(self):
        return self.req.json()

    def q(self, name, default=''):
        values = self.req.query.get(name)
        return values[0] if values else default

    def need(self, capability, config=None):
        require(self.user, capability, config)

    def center(self, center_id):
        require_center(self.user, center_id)
        return center_id

    def recent(self):
        self.app.auth.require_recent(self.session)


class App:
    def __init__(self, *, db, auth, origin, dev=False, web_dir=None, services=None, max_body=20_000_000, demo=False):
        url = urlsplit(origin)
        if url.path not in ('', '/') or url.query or url.fragment or url.username or url.password or not url.hostname:
            raise ValueError('Indirizzo del servizio non valido: usare solo https://nome-server.')
        loopback = url.hostname in ('127.0.0.1', 'localhost', '::1')
        if url.scheme != 'https' and not (dev and url.scheme == 'http' and loopback) and not demo:
            raise ValueError('È obbligatorio HTTPS. La modalità di prova HTTP è ammessa solo su questo computer (127.0.0.1).')
        self.db = db
        self.auth = auth
        self.origin = origin.rstrip('/')
        self.host = url.netloc.lower()
        self.secure = url.scheme == 'https'
        self.demo = demo
        self.cookie_name = '__Host-wr' if self.secure else 'wr_dev'
        self.web_dir = Path(web_dir) if web_dir else None
        self.services = services or {}
        self.max_body = max_body
        self._etags = {}

    # --- WSGI ---------------------------------------------------------------------

    def __call__(self, environ, start_response):
        req = Request(environ, self.max_body)
        status, headers, body = self.handle(req)
        start_response(f'{status} {STATUS_TEXT.get(status, "Error")}', headers)
        return [body]

    def handle(self, req):
        ctx = Context(self, req)
        extra = []
        try:
            self._check_origin(req)
            if req.path.startswith('/api/'):
                data = self._dispatch(ctx)
            elif req.method in ('GET', 'HEAD') and req.path == '/health':
                data = {'product': PRODUCT, 'version': VERSION}
            elif req.method in ('GET', 'HEAD'):
                return self._static(req)
            else:
                raise WRError('Metodo non consentito.', code='method')
            if isinstance(data, Reply):
                status, body, ctype, extra = data.status, data.body, data.content_type, data.headers
            else:
                status, body, ctype = 200, _json(data), 'application/json; charset=utf-8'
        except WRError as exc:
            status = exc.status if exc.code not in ('method', 'media_type') else (405 if exc.code == 'method' else 415)
            body, ctype = _json({'error': exc.payload()}), 'application/json; charset=utf-8'
        except sqlite3.IntegrityError:
            LOG.info('Vincolo del database non rispettato', exc_info=True)
            status = 409
            body = _json({'error': {'code': 'conflict', 'message': 'Valore già presente o collegamento non valido: '
                                    'ricaricare la pagina e controllare i dati.'}})
            ctype = 'application/json; charset=utf-8'
        except Exception:
            LOG.exception('Errore applicativo')
            status = 500
            body = _json({'error': {'code': 'server', 'message': 'Errore del servizio. Riprovare; se continua, '
                                    'avvisare l’amministratore.'}})
            ctype = 'application/json; charset=utf-8'
        csp = next((value for key, value in extra if key == 'Content-Security-Policy'), CSP)
        extra = [(key, value) for key, value in extra if key != 'Content-Security-Policy']
        headers = self._headers(ctype, len(body), csp=csp) + extra
        if ctx.cookie is not None:
            headers.append(('Set-Cookie', self._cookie(ctx.cookie)))
        return status, headers, body if req.method != 'HEAD' else b''

    # --- controlli di sicurezza ------------------------------------------------------------

    def _check_origin(self, req):
        if self.demo:
            return
        if req.header('Host').lower() != self.host:
            raise Forbidden('Indirizzo del servizio non consentito.')
        origin = req.header('Origin', None)
        if origin is not None and origin != self.origin:
            raise Forbidden('Richiesta proveniente da un altro sito.')
        if req.header('Sec-Fetch-Site') == 'cross-site':
            raise Forbidden('Richiesta proveniente da un altro sito.')
        if req.method not in ('GET', 'HEAD') and origin != self.origin:
            raise Forbidden('Origine della richiesta obbligatoria.')

    def _dispatch(self, ctx):
        req = ctx.req
        allowed = []
        for r in ROUTES:
            match = r.regex.match(req.path)
            if not match:
                continue
            allowed.append(r.method)
            if r.method == req.method or (req.method == 'HEAD' and r.method == 'GET'):
                ctx.params = match.groupdict()
                return self._run(ctx, r)
        if allowed:
            raise WRError('Metodo non consentito.', code='method')
        raise NotFound('Indirizzo non trovato.')

    def _run(self, ctx, r):
        req = ctx.req
        if r.auth != 'public':
            raw = req.cookie(self.cookie_name)
            if r.auth == 'session' and req.method == 'GET':
                ctx.session, new_raw = self.auth.ensure(raw)
                if new_raw:
                    self._limit_new_sessions(req)
                    ctx.cookie = new_raw
            else:
                ctx.session = self.auth.session(raw, touch=req.header('X-WR-Background') != '1')
            if req.method not in ('GET', 'HEAD'):
                sent = req.header('X-WR-Token')
                if not sent or not secrets.compare_digest(sent, ctx.session['csrf']):
                    raise Forbidden('La pagina è scaduta o è stata aperta in un’altra scheda: ricaricare.')
            if r.auth == 'user':
                ctx.user = self.auth.user(ctx.session)
                if r.cap:
                    require(ctx.user, r.cap)
                if r.step_up:
                    ctx.recent()
        result = r.handler(ctx)
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], str):
            result, ctx.cookie = result  # (dati, nuovo cookie di sessione)
        return result

    def _limit_new_sessions(self, req):
        key = 'browser:' + req.remote_addr
        self.auth.check_rate(key)
        self.auth.fail(key, limit=120, window=60, block=120)

    def _cookie(self, raw):
        return (f'{self.cookie_name}={raw}; HttpOnly; SameSite=Strict; Path=/'
                + ('; Secure' if self.secure else ''))

    def _headers(self, ctype, length, *, csp=CSP, cache='no-store'):
        headers = [('Content-Type', ctype), ('Content-Length', str(length)), ('Cache-Control', cache),
                   ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                   ('X-Frame-Options', 'DENY' if 'sandbox' not in csp else 'SAMEORIGIN'),
                   ('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()'),
                   ('Content-Security-Policy', csp), ('Cross-Origin-Opener-Policy', 'same-origin')]
        if self.secure:
            headers.append(('Strict-Transport-Security', 'max-age=31536000'))
        return headers

    def document_headers(self):
        """Intestazioni per mostrare un allegato HR dentro il portale, isolato dal resto della pagina."""
        return [('Content-Security-Policy', DOCUMENT_CSP)]

    # --- file statici ----------------------------------------------------------------------------

    def _static(self, req):
        if self.web_dir is None:
            raise NotFound('Pagina non trovata.')
        rel = 'index.html' if req.path in ('/', '/index.html') else req.path.lstrip('/')
        if '..' in rel.split('/') or rel.startswith('.') or '\\' in rel:
            raise NotFound('Pagina non trovata.')
        target = (self.web_dir / rel).resolve()
        if self.web_dir.resolve() not in target.parents or not target.is_file():
            raise NotFound('Pagina non trovata.')
        ctype = STATIC_TYPES.get(target.suffix.lower())
        if not ctype:
            raise NotFound('Pagina non trovata.')
        data = target.read_bytes()
        etag = self._etag(target, data)
        if req.header('If-None-Match') == etag:
            headers = self._headers(ctype, 0, cache='no-cache')
            headers.append(('ETag', etag))
            return 304, headers, b''
        status, extra = 200, [('ETag', etag)]
        if target.suffix.lower() in ('.mp4', '.webm'):
            extra.append(('Accept-Ranges', 'bytes'))
            status, data, more = _byte_range(req.header('Range'), data)
            extra += more
        headers = self._headers(ctype, len(data), cache='no-cache') + extra
        return status, headers, data if req.method != 'HEAD' else b''

    def _etag(self, path, data):
        key = (str(path), path.stat().st_mtime_ns, len(data))
        if key not in self._etags:
            self._etags[key] = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
        return self._etags[key]


def _byte_range(header, data):
    """Richieste parziali per spostarsi nei video (capitoli) prima della riproduzione."""
    size = len(data)
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header or '')
    if not header or not match or not any(match.groups()):
        return 200, data, []
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        start, end = max(0, size - int(last)), size - 1
    if not (0 <= start <= end < size):
        return 416, b'', [('Content-Range', f'bytes */{size}')]
    return 206, data[start:end + 1], [('Content-Range', f'bytes {start}-{end}/{size}')]


def _json(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def guess_type(name):
    return mimetypes.guess_type(name)[0] or 'application/octet-stream'
