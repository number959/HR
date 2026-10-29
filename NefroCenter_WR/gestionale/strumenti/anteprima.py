"""Anteprima locale con dati fittizi: crea un archivio dimostrativo temporaneo e avvia il portale.

Uso (dalla cartella gestionale):  python strumenti/anteprima.py [--port 8090] [--dir cartella-nuova] [--aziendale]
Serve solo per prove, schermate e guide, sempre con dati inventati e solo su questo computer.
- predefinito: modalità demo, i profili entrano senza password;
- --aziendale: accesso come nel portale aziendale (password e app Authenticator). I codici di attivazione degli
  account di prova sono scritti in codici-attivazione.json nella cartella dell'archivio di prova.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wr import app as factory, sample  # noqa: E402
from wr.util import set_today  # noqa: E402


def main():
    p = argparse.ArgumentParser(description='Anteprima di NefroCenter WR con dati fittizi')
    p.add_argument('--port', type=int, default=8090)
    p.add_argument('--dir', type=Path, help='Cartella nuova per l’archivio di prova (predefinita: temporanea)')
    p.add_argument('--today', default=sample.DEMO_TODAY, help='Data di riferimento dei dati di prova')
    p.add_argument('--aziendale', action='store_true', help='Accesso con password e app Authenticator (dati sempre fittizi)')
    a = p.parse_args()
    folder = a.dir or Path(tempfile.mkdtemp(prefix='wr-anteprima-'))
    factory.load_modules()
    key = folder / 'chiave-di-prova.key' if a.aziendale else None
    _, codes = sample.build(folder, key, demo=not a.aziendale, today=a.today)
    if a.aziendale:
        (folder / 'codici-attivazione.json').write_text(json.dumps(codes, indent=2), encoding='utf-8')
    set_today(a.today)
    application = factory.create(folder, origin=f'http://127.0.0.1:{a.port}', key_file=key, demo=not a.aziendale, dev=True)
    from waitress import serve
    mode = 'accesso con password e app Authenticator' if a.aziendale else 'modalità demo'
    print(f'Anteprima con dati fittizi ({mode}): http://127.0.0.1:{a.port}  (archivio: {folder})', flush=True)
    serve(application, host='127.0.0.1', port=a.port, threads=4)


if __name__ == '__main__':
    main()
