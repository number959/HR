"""Errori applicativi con stato HTTP e messaggio in italiano per l'utente."""


class WRError(Exception):
    status = 400
    code = 'invalid'

    def __init__(self, message, *, field=None, code=None, data=None):
        super().__init__(message)
        self.message = message
        self.field = field
        if code:
            self.code = code
        self.data = data or {}

    def payload(self):
        out = {'code': self.code, 'message': self.message}
        if self.field:
            out['field'] = self.field
        out.update(self.data)
        return out


class Invalid(WRError):
    status = 400
    code = 'invalid'


class Unauthorized(WRError):
    status = 401
    code = 'unauthorized'


class Forbidden(WRError):
    status = 403
    code = 'forbidden'


class NotFound(WRError):
    status = 404
    code = 'not_found'


class Conflict(WRError):
    """Dati cambiati da un'altra sessione: ricaricare prima di salvare."""
    status = 409
    code = 'conflict'


class TooLarge(WRError):
    status = 413
    code = 'too_large'


class StepUpRequired(WRError):
    """Operazione sensibile: serve una conferma recente di password e secondo fattore."""
    status = 428
    code = 'step_up'


class RateLimited(WRError):
    status = 429
    code = 'rate_limited'
