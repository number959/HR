"""Serve la demo pubblica sul proprio computer, solo per prove, e apre il browser.

Uso:  python avvia_demo.py [--port 8000] [--lan] [--senza-browser]
Serve la cartella dist/ accanto a questo file (cartella del progetto) oppure, nel pacchetto della demo già costruita,
la cartella in cui si trova. Senza --lan la demo è raggiungibile solo da questo computer; con --lan anche dagli altri
computer della stessa rete. Serve soltanto file statici con dati fittizi: nessun dato lascia il computer.
"""
import argparse
import functools
import http.server
import json
import socket
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent


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


def demo_folder():
    """dist/ accanto allo script (progetto) oppure la cartella dello script stesso (pacchetto della demo)."""
    for folder in (HERE / 'dist', HERE):
        info = folder / 'versione.json'
        if (folder / 'index.html').exists() and info.exists():
            try:
                if 'demo' in json.loads(info.read_text(encoding='utf-8')).get('tipo', ''):
                    return folder
            except (ValueError, OSError):
                pass
    return None


def lan_address():
    """Indirizzo di questo computer nella rete locale (senza inviare nulla), per chi usa --lan."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    p = argparse.ArgumentParser(description='Demo di NefroCenter WR (dati fittizi)')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--lan', action='store_true', help='raggiungibile anche dagli altri computer della rete')
    p.add_argument('--senza-browser', action='store_true', help='non aprire il browser da solo')
    a = p.parse_args()
    folder = demo_folder()
    if folder is None:
        raise SystemExit('Demo non ancora costruita: eseguire prima «python costruisci_demo.py».')
    host = '0.0.0.0' if a.lan else '127.0.0.1'
    try:
        server = http.server.ThreadingHTTPServer((host, a.port), functools.partial(Handler, directory=str(folder)))
    except OSError as e:
        raise SystemExit(f'Porta {a.port} non disponibile ({e.strerror}): chiudere l’altra demo oppure usare --port {a.port + 1}.')
    url = f'http://127.0.0.1:{a.port}/'
    print(f'Demo di NefroCenter WR con dati fittizi: {url}', flush=True)
    if a.lan:
        ip = lan_address()
        print(f'Dagli altri computer della rete: http://{ip}:{a.port}/' if ip else 'Raggiungibile anche dalla rete locale.', flush=True)
    print('Per fermarla: Ctrl+C (o chiudere questa finestra).', flush=True)
    if not a.senza_browser:
        threading.Timer(0.8, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
