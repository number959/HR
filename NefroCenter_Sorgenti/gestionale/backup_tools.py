"""Elenco e download dei backup completati. Nessun ripristino o cancellazione via web."""
import re
from datetime import datetime

MAX_DOWNLOAD = 256 * 1024 * 1024
PATTERN = re.compile(r'presenze_\d{8}_\d{6}_\d{6}\.sqlite3')


def require_admin(core, user):
    with core.connect() as c:
        core.require_admin(core.fresh_user(c, user))


def completed_files(directory):
    """Ignore partial names, non-files and files missing the SQLite header."""
    if not directory.exists():
        return
    for path in directory.iterdir():
        if not PATTERN.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open('rb') as source:
                if source.read(16) != b'SQLite format 3\x00':
                    continue
        except FileNotFoundError:
            continue
        yield path


def listing(core, user):
    require_admin(core, user)
    directory = core.DB.parent / 'backups'
    files = []
    for path in completed_files(directory):
        stat = path.stat()
        files.append(dict(filename=path.name, bytes=stat.st_size,
                          created_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec='seconds'),
                          downloadable=stat.st_size <= MAX_DOWNLOAD))
    files.sort(key=lambda r: r['filename'], reverse=True)
    return dict(files=files[:50], count=len(files), bytes=sum(f['bytes'] for f in files),
                shown=min(50, len(files)), automatic_policy='Un backup al giorno mentre il servizio è attivo; verifica ogni ora.')


def download(core, user, filename):
    require_admin(core, user)
    if not isinstance(filename, str) or not PATTERN.fullmatch(filename):
        raise ValueError('Nome del backup non valido.')
    directory = core.DB.parent / 'backups'; path = directory / filename
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
        raise ValueError('Backup non disponibile.')
    if path.stat().st_size > MAX_DOWNLOAD:
        raise ValueError('Backup oltre 256 MiB: usare una copia amministrativa dal server.')
    content = path.read_bytes()
    if not content.startswith(b'SQLite format 3\x00'):
        raise ValueError('Il file non è un database SQLite valido.')
    with core.connect() as c:
        core.audit(c, user, 'Download backup', after={'filename': filename}); c.commit()
    return content
