"""Informazioni per l'avvio dell'interfaccia: utente, strutture visibili, permessi."""
from . import PRODUCT, SUBTITLE, VERSION, centers, users
from .permissions import capability_map, matrix
from .util import today_iso


def me(db, user, demo=False):
    with db.read() as con:
        user = users.reload(con, user)
        visible = centers.visible(con, user)
    return dict(product=PRODUCT, subtitle=SUBTITLE, version=VERSION, demo=demo, today=today_iso(),
                user=user.public(), centers=visible, caps=capability_map(user))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/me')
def api_me(ctx):
    return me(ctx.db, ctx.user, ctx.app.demo)


@route('GET', '/api/roles', auth='public')
def api_roles(ctx):
    return matrix()
