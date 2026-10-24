"""Avvia un archivio fittizio isolato e il collaudo Chromium su loopback."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
from web_server import WebApp
from web_auth import Auth
from waitress.server import create_server


def main():
    node = os.environ.get('NODE_BINARY') or shutil.which('node')
    if not node:
        raise SystemExit('Node.js non trovato. Impostare NODE_BINARY al percorso dell’interprete.')
    with tempfile.TemporaryDirectory(prefix='presenze-qa-') as td:
        root = Path(td)
        key = root / 'private' / 'key'
        Auth.create_key(key)
        web = WebApp(root / 'data', key, 'http://127.0.0.1:8080', dev=True)
        core.setup(dict(username='admin', name='Amministrazione demo',
                        center_name='Centro Capodichino', password='Password-iniziale-test-2026!'))
        with core.connect() as c:
            uid = c.execute('SELECT id FROM users').fetchone()[0]
        activation = web.auth.activation(uid, {'username': 'console'}, 'Browser QA')
        server = create_server(web, host='127.0.0.1', port=0, threads=8)
        web.origin = 'http://127.0.0.1:' + str(server.effective_port)
        web.host = '127.0.0.1:' + str(server.effective_port)
        threading.Thread(target=server.run, daemon=True).start()
        try:
            result = subprocess.run([node, str(ROOT / 'qa' / 'browser.cjs')], cwd=ROOT,
                                    env={**os.environ, 'WEB_URL': web.origin,
                                         'WEB_ACTIVATION': activation}, timeout=240)
            return result.returncode
        finally:
            server.close()
            server.task_dispatcher.shutdown()


if __name__ == '__main__':
    sys.exit(main())
