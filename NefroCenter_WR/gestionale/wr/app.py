"""Costruzione dell'applicazione: archivio, chiave del server, moduli e interfaccia."""
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
DB_NAME = 'wr.sqlite3'

# Ordine di registrazione delle rotte: prima le più specifiche quando condividono un prefisso.
MODULES = ('auth', 'users', 'portal', 'centers', 'structures', 'people', 'attendance', 'approvals', 'agreements',
           'workforce', 'hr', 'reviews')


def load_modules():
    for name in MODULES:
        importlib.import_module('wr.' + name)


def database(data_dir):
    from .db import Database
    return Database(Path(data_dir) / DB_NAME)


def create(data_dir, *, origin, key_file=None, dev=False, demo=False, web_dir=None, migrate=True, clock=None):
    from .auth import Auth
    from .web import App
    db = database(data_dir)
    if migrate:
        db.migrate()
    auth = Auth(db, key_file, demo=demo, **({'clock': clock} if clock else {}))
    load_modules()
    return App(db=db, auth=auth, origin=origin, dev=dev, demo=demo, web_dir=web_dir if web_dir is not None else WEB)
