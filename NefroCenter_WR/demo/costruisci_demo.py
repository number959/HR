"""Costruisce la demo pubblica di NefroCenter WR nella cartella dist/ (sito statico).

Uso (dalla cartella demo):   python costruisci_demo.py [--includi-pyodide]

- copia l'interfaccia del portale (gestionale/web) così com'è;
- impacchetta il motore del portale (gestionale/wr con le librerie incluse) in motore.zip;
- crea un archivio con soli dati fittizi (dati/wr.sqlite3);
- con --includi-pyodide copia anche Pyodide in pyodide/ (la demo funziona senza la rete di distribuzione pubblica).

La demo non contiene dati aziendali, chiavi o account reali e non invia email. Non viene pubblicata da questo script:
la pubblicazione su un indirizzo Internet è una scelta separata.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
GESTIONALE = HERE.parent / 'gestionale'
DIST = HERE / 'dist'
MARKER = '.demo-nefrocenter-wr'
PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/'
PYODIDE_CORE = ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']
PYODIDE_PACKAGES = ['sqlite3', 'tzdata']
CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval'; "
       "connect-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: blob:; style-src 'self'; frame-src 'self' blob:; "
       "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'")

sys.path.insert(0, str(GESTIONALE))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean():
    if DIST.exists():
        if not (DIST / MARKER).exists():
            raise SystemExit(f'La cartella {DIST} esiste ma non è una build della demo: non viene cancellata.')
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    (DIST / MARKER).write_text('Cartella generata da costruisci_demo.py: può essere ricreata in ogni momento.\n')


def interface():
    # La cartella help/ (manuale e videoguide) resta fuori dalla demo per tenerla leggera: la guida in linea c'è comunque.
    shutil.copytree(GESTIONALE / 'web', DIST, dirs_exist_ok=True, ignore=shutil.ignore_patterns('help'))
    shutil.copy(HERE / 'sorgenti' / 'demo-main.js', DIST / 'js' / 'demo-main.js')
    page = (GESTIONALE / 'web' / 'index.html').read_text(encoding='utf-8')
    replacements = {
        '<meta name="color-scheme" content="light dark">':
            '<meta name="color-scheme" content="light dark">\n  <meta name="robots" content="noindex">\n'
            f'  <meta http-equiv="Content-Security-Policy" content="{CSP}">',
        '<title>NefroCenter WR · Work Resources</title>': '<title>Demo · NefroCenter WR · Work Resources</title>',
        '<script type="module" src="js/main.js"></script>': '<script type="module" src="js/demo-main.js"></script>',
        '<div id="root"></div>':
            '<div id="root"><div class="boot" id="boot"><div class="boot-card">'
            '<img src="img/emblema.png" alt="" width="64" height="64">'
            '<h1>NefroCenter WR · demo</h1>'
            '<p class="muted">Demo pubblica con dati interamente fittizi. Il portale gira nel browser: '
            'nessun dato lascia questa scheda e nessuna email viene inviata.</p>'
            '<progress id="boot-bar" max="100" value="2" aria-label="Avvio della demo"></progress>'
            '<p class="small" id="boot-status" role="status">Avvio della demo…</p>'
            '</div></div></div>',
    }
    for old, new in replacements.items():
        if old not in page:
            raise SystemExit(f'index.html del portale cambiato: aggiornare costruisci_demo.py ({old}).')
        page = page.replace(old, new)
    (DIST / 'index.html').write_text(page, encoding='utf-8')


def engine():
    target = DIST / 'motore.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(HERE / 'sorgenti' / 'ponte.py', 'ponte.py')
        for folder in ('wr', 'vendor/xlsxwriter', 'vendor/segno', 'vendor/licenze'):
            for path in sorted((GESTIONALE / folder).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    zf.write(path, path.relative_to(GESTIONALE).as_posix())
    return target


def data():
    from wr import sample
    (DIST / 'dati').mkdir()
    with tempfile.TemporaryDirectory(prefix='wr-demo-') as tmp:
        source = Path(tmp) / 'wr.sqlite3'
        sample.build(path=source, demo=True)
        con = sqlite3.connect(source)
        con.execute('PRAGMA journal_mode=DELETE')
        con.execute('VACUUM')
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Archivio dimostrativo non valido.')
        con.close()
        shutil.copy(source, DIST / 'dati' / 'wr.sqlite3')
    return DIST / 'dati' / 'wr.sqlite3', sample.DEMO_TODAY


def pyodide_copy():
    folder = DIST / 'pyodide'
    folder.mkdir()

    def fetch(name):
        with urllib.request.urlopen(PYODIDE + name, timeout=120) as response:
            (folder / name).write_bytes(response.read())

    for name in PYODIDE_CORE:
        fetch(name)
    lock = json.loads((folder / 'pyodide-lock.json').read_text())
    for package in PYODIDE_PACKAGES:
        fetch(lock['packages'][package]['file_name'])
    (folder / 'LICENZA-PYODIDE.txt').write_text(
        'Pyodide (https://pyodide.org) è distribuito con licenza Mozilla Public License 2.0.\n'
        'Testo della licenza: https://github.com/pyodide/pyodide/blob/main/LICENSE\n'
        f'File copiati da {PYODIDE} per usare la demo senza la rete di distribuzione pubblica.\n', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description='Costruisce la demo pubblica di NefroCenter WR (solo dati fittizi).')
    p.add_argument('--includi-pyodide', action='store_true', help='copia Pyodide nella demo (circa 15 MB)')
    a = p.parse_args()
    clean()
    interface()
    motore = engine()
    archive, today = data()
    if a.includi_pyodide:
        pyodide_copy()
    from wr import PRODUCT, VERSION
    info = dict(prodotto=PRODUCT, versione=VERSION, tipo='demo pubblica con dati fittizi', data_demo=today,
                costruita_il=datetime.now(timezone.utc).isoformat(timespec='seconds'), pyodide=PYODIDE,
                pyodide_locale=a.includi_pyodide, motore_sha256=sha256(motore), dati_sha256=sha256(archive))
    (DIST / 'versione.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    size = sum(f.stat().st_size for f in DIST.rglob('*') if f.is_file())
    print(f'Demo pronta in {DIST} ({size / 1024 / 1024:.1f} MB). Prova locale: python avvia_demo.py')


if __name__ == '__main__':
    main()
