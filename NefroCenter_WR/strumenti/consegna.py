"""Prepara i materiali di consegna di NefroCenter WR nella cartella materiali/ (ignorata da git).

Uso (dalla cartella NefroCenter_WR):  python strumenti/consegna.py [--out materiali] [--senza-media]

Produce:
- NefroCenter_WR_<versione>.zip                 tutto il progetto in un unico archivio (gestionale, demo, strumenti, documenti)
- Codice_Sorgente_NefroCenter_WR_<versione>.txt tutti i file in un solo testo UTF-8, che è anche uno script Python:
                                                 «python Codice_Sorgente_NefroCenter_WR_<versione>.txt --directory CARTELLA»
                                                 ricrea l'albero dei sorgenti verificando le impronte SHA-256
- SHA256SUMS_<versione>.txt                     impronte di ogni file consegnato
- VERIFICA_PACCHETTO_<versione>.txt             esito dei controlli eseguiti sui pacchetti (ricostruzione dal TXT, ZIP)

Restano fuori: dati, chiavi, backup, ambienti virtuali, cache, la build della demo (dist/) e le cartelle di lavoro.
Con --senza-media il TXT non contiene manuale e videoguide (restano nello ZIP) e pesa molto meno.
"""
import argparse
import base64
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'gestionale'))
from wr import PRODUCT, VERSION  # noqa: E402

EXCLUDED_DIRS = {'.git', '__pycache__', 'node_modules', 'dist', 'lavoro', 'materiali', 'data', 'private', 'backups', '.venv', '.venv313'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.sqlite3', '.sqlite3-wal', '.sqlite3-shm', '.key', '.pid', '.log'}
EXCLUDED_NAMES = {'.env', '.DS_Store', 'Thumbs.db'}
MEDIA_DIR = PurePosixPath('gestionale/web/help')
TEXT_SUFFIXES = {'.py', '.js', '.cjs', '.mjs', '.css', '.html', '.md', '.txt', '.json', '.svg', '.vtt', '.srt', '.example',
                 '.service', '.gitignore', '.cfg', '.toml', '.ini', '.yml', '.yaml', '.csv'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def collect(root, include_media=True):
    """Elenco (percorso relativo posix, bytes) dei file da consegnare, ordinato."""
    files = []
    for folder, dirs, names in os.walk(root):
        rel_folder = PurePosixPath(Path(folder).relative_to(root).as_posix()) if Path(folder) != root else PurePosixPath('.')
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('.'))
        if not include_media and (rel_folder == MEDIA_DIR or MEDIA_DIR in rel_folder.parents):
            continue
        for name in sorted(names):
            path = Path(folder) / name
            rel = (rel_folder / name) if rel_folder != PurePosixPath('.') else PurePosixPath(name)
            if name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES or path.is_symlink():
                continue
            files.append((rel.as_posix(), path.read_bytes()))
    return files


def is_text(rel, data):
    if Path(rel).suffix.lower() not in TEXT_SUFFIXES and Path(rel).name not in ('.gitignore',):
        return False
    try:
        data.decode('utf-8')
        return b'\x00' not in data
    except UnicodeDecodeError:
        return False


def literal_lines(text):
    """Stringa Python come concatenazione di una riga per riga (leggibile e fedele, a capo compresi)."""
    lines = text.splitlines(keepends=True) or ['']
    return '(\n' + ''.join('        ' + repr(line) + '\n' for line in lines) + '    )'


def literal_base64(data):
    encoded = base64.b64encode(data).decode('ascii')
    chunks = [encoded[i:i + 76] for i in range(0, len(encoded), 76)] or ['']
    return '(\n' + ''.join('        ' + repr(c) + '\n' for c in chunks) + '    )'


RECONSTRUCTOR = '''

def _write(target, rel, data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Impronta non valida per {rel}: il file TXT è incompleto o alterato, scaricarlo di nuovo.')
    path = target / PurePosixPath(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    p = argparse.ArgumentParser(description=f'Ricrea i sorgenti di {PRODOTTO} {VERSIONE} da questo file.')
    p.add_argument('--directory', help='cartella nuova (o vuota) in cui ricreare i sorgenti')
    p.add_argument('--list', action='store_true', help='elenca i file senza scrivere nulla')
    a = p.parse_args()
    names = sorted(set(TEXT_FILES) | set(BINARY_FILES))
    if a.list or not a.directory:
        for name in names:
            print(name)
        print(f'{len(names)} file ({len(TEXT_FILES)} di testo, {len(BINARY_FILES)} binari).')
        if not a.directory:
            print('Per ricreare i sorgenti: --directory CARTELLA')
        return
    target = Path(a.directory)
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f'La cartella {target} non è vuota: scegliere una cartella nuova. Nessun file scritto.')
    target.mkdir(parents=True, exist_ok=True)
    for rel, text in TEXT_FILES.items():
        _write(target, rel, text.encode('utf-8'), TEXT_HASHES[rel])
    for rel, digest in BINARY_FILES.items():
        _write(target, rel, base64.b64decode(BINARY_CONTENTS[digest]), digest)
    print(f'{len(names)} file ricreati in {target.resolve()}. Non è stato installato né avviato nulla.')


if __name__ == '__main__':
    main()
'''


def build_txt(files, version, include_media):
    out = io.StringIO()
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    out.write(f'# {PRODUCT.upper()} · WORK RESOURCES — SORGENTI COMPLETI {version}' + ('' if include_media else ' (senza manuale e videoguide)') + '\n')
    out.write(f'# Generato il {stamp} da strumenti/consegna.py. File UTF-8 che è anche uno script Python 3.10+.\n')
    out.write(f'# Per ricreare i sorgenti:  python Codice_Sorgente_NefroCenter_WR_{version}.txt --directory NefroCenter_WR\n')
    out.write('# Il comando verifica le impronte SHA-256, rifiuta una cartella non vuota, non installa dipendenze, non avvia servizi.\n')
    out.write('# TEXT_FILES: codice e documenti leggibili. BINARY_FILES: impronta di ogni file binario; BINARY_CONTENTS: Base64 (una sola volta).\n')
    out.write('# Esclusi: dati aziendali, chiavi, backup, ambienti virtuali, cache, build della demo.\n\n')
    out.write('import argparse\nimport base64\nimport hashlib\nfrom pathlib import Path, PurePosixPath\n\n')
    out.write(f'PRODOTTO = {PRODUCT!r}\nVERSIONE = {version!r}\n\n')
    texts, binaries, contents, hashes = [], [], {}, []
    for rel, data in files:
        digest = sha256(data)
        if is_text(rel, data):
            texts.append((rel, data.decode('utf-8'), digest))
        else:
            binaries.append((rel, digest))
            contents.setdefault(digest, data)
    out.write('TEXT_FILES = {\n')
    for rel, text, _ in texts:
        out.write(f'\n    # FILE: {rel}\n    {rel!r}: {literal_lines(text)},\n')
    out.write('}\n\nTEXT_HASHES = {\n')
    for rel, _, digest in texts:
        out.write(f'    {rel!r}: {digest!r},\n')
    out.write('}\n\nBINARY_FILES = {\n')
    for rel, digest in binaries:
        out.write(f'    {rel!r}: {digest!r},\n')
    out.write('}\n\nBINARY_CONTENTS = {\n')
    for digest, data in contents.items():
        out.write(f'    {digest!r}: {literal_base64(data)},\n')
    out.write('}\n')
    out.write(RECONSTRUCTOR)
    return out.getvalue().encode('utf-8'), len(texts), len(binaries), len(contents)


def build_zip(files, version, target):
    top = f'NefroCenter_WR_{version}/'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, data in files:
            info = zipfile.ZipInfo(top + rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)


def verify_txt(txt_path, files, results):
    with tempfile.TemporaryDirectory(prefix='wr-consegna-') as tmp:
        target = Path(tmp) / 'ricostruito'
        run = subprocess.run([sys.executable, '-I', str(txt_path), '--directory', str(target)], capture_output=True, text=True, timeout=1800)
        if run.returncode != 0:
            results.append('FAIL: ricostruzione dal TXT non riuscita: ' + run.stderr.strip()[:300])
            return
        mismatch = []
        for rel, data in files:
            path = target / rel
            if not path.exists() or sha256(path.read_bytes()) != sha256(data):
                mismatch.append(rel)
        extra = sum(1 for p in target.rglob('*') if p.is_file()) - len(files)
        if mismatch or extra:
            results.append(f'FAIL: TXT ricostruito con differenze ({len(mismatch)} file diversi, {extra} in più).')
        else:
            results.append(f'PASS: TXT eseguito in una cartella temporanea; {len(files)} file ricostruiti identici ai sorgenti.')
        busy = Path(tmp) / 'occupata'
        busy.mkdir()
        (busy / 'qualcosa.txt').write_text('x')
        refused = subprocess.run([sys.executable, '-I', str(txt_path), '--directory', str(busy)], capture_output=True, text=True, timeout=600)
        if refused.returncode != 0 and 'non è vuota' in refused.stderr and len(list(busy.iterdir())) == 1:
            results.append('PASS: il TXT rifiuta una cartella già occupata senza scrivere nulla.')
        else:
            results.append('FAIL: il TXT non ha rifiutato una cartella occupata.')


def verify_zip(zip_path, files, version, results):
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        names = {i.filename for i in zf.infolist()}
        expected = {f'NefroCenter_WR_{version}/{rel}' for rel, _ in files}
        same = all(sha256(zf.read(f'NefroCenter_WR_{version}/{rel}')) == sha256(data) for rel, data in files)
    if bad is None and names == expected and same:
        results.append(f'PASS: ZIP integro, {len(names)} file identici ai sorgenti.')
    else:
        results.append('FAIL: ZIP con differenze o danneggiato.')


def main():
    p = argparse.ArgumentParser(description='Materiali di consegna di NefroCenter WR')
    p.add_argument('--out', type=Path, default=ROOT / 'materiali')
    p.add_argument('--senza-media', action='store_true', help='TXT senza manuale e videoguide (lo ZIP li contiene comunque)')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    version = VERSION
    files = collect(ROOT)
    forbidden = [rel for rel, _ in files if Path(rel).suffix in ('.key', '.sqlite3') or rel.endswith('.env')]
    if forbidden:
        raise SystemExit('File riservati nel perimetro di consegna: ' + ', '.join(forbidden))
    zip_path = a.out / f'NefroCenter_WR_{version}.zip'
    build_zip(files, version, zip_path)
    txt_files = collect(ROOT, include_media=not a.senza_media)
    txt, n_text, n_bin, n_unique = build_txt(txt_files, version, not a.senza_media)
    txt_path = a.out / f'Codice_Sorgente_NefroCenter_WR_{version}.txt'
    txt_path.write_bytes(txt)
    results = [f'{PRODUCT} {version} — verifica dei pacchetti del {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}']
    verify_zip(zip_path, files, version, results)
    verify_txt(txt_path, txt_files, results)
    results.append(f'TXT: {txt_path.stat().st_size} byte; {n_text} file di testo, {n_bin} file binari ({n_unique} contenuti distinti).'
                   + (' Senza manuale e videoguide.' if a.senza_media else ''))
    results.append(f'ZIP: {zip_path.stat().st_size} byte, {len(files)} file.')
    sums = a.out / f'SHA256SUMS_{version}.txt'
    sums.write_text(''.join(f'{sha256(data)}  {rel}\n' for rel, data in files), encoding='utf-8')
    (a.out / f'VERIFICA_PACCHETTO_{version}.txt').write_text('\n'.join(results) + '\n', encoding='utf-8')
    print('\n'.join(results))
    if any(r.startswith('FAIL') for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
