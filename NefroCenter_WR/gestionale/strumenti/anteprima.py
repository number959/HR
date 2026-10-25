"""Anteprima locale con dati fittizi: crea un archivio dimostrativo temporaneo e avvia il portale in modalità demo.

Uso (dalla cartella gestionale):  python strumenti/anteprima.py [--port 8090] [--dir cartella-nuova]
Serve solo per prove, schermate e guide: i profili entrano senza password e i dati sono inventati.
"""
import argparse
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
    a = p.parse_args()
    folder = a.dir or Path(tempfile.mkdtemp(prefix='wr-anteprima-'))
    factory.load_modules()
    sample.build(folder, demo=True, today=a.today)
    set_today(a.today)
    application = factory.create(folder, origin=f'http://127.0.0.1:{a.port}', demo=True, dev=True)
    from waitress import serve
    print(f'Anteprima con dati fittizi: http://127.0.0.1:{a.port}  (archivio: {folder})', flush=True)
    serve(application, host='127.0.0.1', port=a.port, threads=4)


if __name__ == '__main__':
    main()
