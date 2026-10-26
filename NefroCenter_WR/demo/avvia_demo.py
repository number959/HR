"""Serve la demo pubblica (cartella dist/) sul proprio computer, solo per prove.

Uso:  python avvia_demo.py [--port 8000] [--lan]
Senza --lan la demo è raggiungibile solo da questo computer (http://localhost:8000).
Con --lan anche dagli altri computer della stessa rete. Serve soltanto file statici con dati fittizi.
"""
import argparse
import functools
import http.server
from pathlib import Path

DIST = Path(__file__).resolve().parent / 'dist'


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript',
                      '.wasm': 'application/wasm', '.zip': 'application/zip', '.sqlite3': 'application/octet-stream',
                      '.json': 'application/json', '.whl': 'application/zip'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    p = argparse.ArgumentParser(description='Demo di NefroCenter WR (dati fittizi)')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--lan', action='store_true', help='raggiungibile anche dagli altri computer della rete')
    a = p.parse_args()
    if not (DIST / 'index.html').exists():
        raise SystemExit('Demo non ancora costruita: eseguire prima «python costruisci_demo.py».')
    host = '0.0.0.0' if a.lan else '127.0.0.1'
    server = http.server.ThreadingHTTPServer((host, a.port), functools.partial(Handler, directory=str(DIST)))
    print(f'Demo con dati fittizi: http://localhost:{a.port}' + ('  (anche dalla rete locale)' if a.lan else ''), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
