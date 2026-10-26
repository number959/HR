"""Ponte della demo pubblica: nel browser ogni richiesta /api diventa una chiamata WSGI al motore WR, senza rete.

Il motore è lo stesso del portale aziendale, avviato in modalità demo: profili senza password, invii di posta
simulati, dati fittizi in memoria. Le modifiche restano nella scheda del browser e spariscono alla chiusura.
"""
import io
import json
import sys
from http.cookies import SimpleCookie

sys.path.insert(0, '/motore')

from wr import app as factory  # noqa: E402
from wr.util import set_today  # noqa: E402

ORIGIN = 'https://demo.nefrocenter.invalid'
STATO = dict(app=None, cookie='')


def avvia(cartella_dati, oggi):
    set_today(oggi)
    STATO['app'] = factory.create(cartella_dati, origin=ORIGIN, demo=True, dev=True, migrate=False, web_dir='/nessuna')
    return STATO['app'].cookie_name


def chiama(metodo, percorso, query, intestazioni_json, corpo):
    """Restituisce (stato, intestazioni, corpo in byte)."""
    app = STATO['app']
    dati = corpo.to_bytes() if hasattr(corpo, 'to_bytes') else bytes(corpo or b'')
    intestazioni = json.loads(intestazioni_json or '{}')
    environ = {
        'REQUEST_METHOD': metodo, 'PATH_INFO': percorso, 'QUERY_STRING': query or '', 'REMOTE_ADDR': '127.0.0.1',
        'HTTP_HOST': ORIGIN.split('://', 1)[1], 'wsgi.input': io.BytesIO(dati), 'CONTENT_LENGTH': str(len(dati)),
        'CONTENT_TYPE': intestazioni.get('Content-Type', '') if dati else '', 'wsgi.url_scheme': 'https',
        'HTTP_ORIGIN': ORIGIN,
    }
    for nome, valore in intestazioni.items():
        if nome.lower() != 'content-type':
            environ['HTTP_' + nome.upper().replace('-', '_')] = str(valore)
    if STATO['cookie']:
        environ['HTTP_COOKIE'] = f'{app.cookie_name}={STATO["cookie"]}'
    risposta = {}

    def start_response(stato, headers):
        risposta['stato'] = int(stato.split()[0])
        risposta['headers'] = headers

    corpo_out = b''.join(app(environ, start_response))
    uscita = []
    for nome, valore in risposta['headers']:
        if nome.lower() == 'set-cookie':
            jar = SimpleCookie()
            jar.load(valore)
            if app.cookie_name in jar:
                STATO['cookie'] = jar[app.cookie_name].value
            continue
        uscita.append([nome, valore])
    return risposta['stato'], uscita, corpo_out
