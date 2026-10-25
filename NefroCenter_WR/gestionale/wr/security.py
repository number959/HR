"""Primitive di sicurezza: password, codici TOTP, codici di recupero, impronte.

Le password usano PBKDF2-HMAC-SHA256 con sale casuale. I codici TOTP seguono
RFC 6238 (30 secondi, 6 cifre, HMAC-SHA1) e sono compatibili con le comuni app
Authenticator. Nessuna funzione qui accede al database.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
from urllib.parse import quote

from .errors import Invalid

PBKDF2_ITERATIONS = 600_000
PASSWORD_MIN = 12
PASSWORD_MAX = 256
TOTP_PERIOD = 30
TOTP_DIGITS = 6
RECOVERY_CODES = 10
ISSUER = 'NefroCenter WR'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


# --- Password -----------------------------------------------------------------

def check_password_policy(password, username=''):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise Invalid(f'La password deve avere da {PASSWORD_MIN} a {PASSWORD_MAX} caratteri.', field='password')
    if username and password.casefold() == username.casefold():
        raise Invalid('La password non può coincidere con il nome utente.', field='password')
    if len(set(password)) < 4:
        raise Invalid('La password è troppo ripetitiva: usare almeno quattro caratteri diversi.', field='password')
    return password


def hash_password(password, username=''):
    check_password_policy(password, username)
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
    return json.dumps({'scheme': 'pbkdf2-sha256', 'iterations': PBKDF2_ITERATIONS,
                       'salt': salt.hex(), 'hash': key.hex()}, separators=(',', ':'))


def verify_password(password, stored):
    if not isinstance(password, str) or len(password) > PASSWORD_MAX or not stored:
        return False
    try:
        data = json.loads(stored)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(data['salt']), int(data['iterations']))
    except (ValueError, KeyError, TypeError):
        return False
    return hmac.compare_digest(key.hex(), data['hash'])


def burn_password_time():
    """Stesso tempo di calcolo per utenti inesistenti: non rivela quali nomi esistono."""
    hashlib.pbkdf2_hmac('sha256', b'nefrocenter-wr', b'tempo-costante', PBKDF2_ITERATIONS)


# --- TOTP ---------------------------------------------------------------------

def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _key(secret):
    padded = secret.upper() + '=' * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_code(secret, step):
    mac = hmac.new(_key(secret), struct.pack('>Q', step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** TOTP_DIGITS).zfill(TOTP_DIGITS)


def totp_match(secret, code, now, last_step=-1):
    """Restituisce il passo temporale del codice valido (±30 secondi), oppure None.
    Un passo già usato (≤ last_step) viene rifiutato per impedire il riutilizzo."""
    if not isinstance(code, str):
        return None
    code = code.strip().replace(' ', '')
    if not re.fullmatch(r'\d{6}', code):
        return None
    current = int(now // TOTP_PERIOD)
    for step in (current, current - 1, current + 1):
        if step > last_step and hmac.compare_digest(totp_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret, account):
    label = quote(f'{ISSUER}:{account}')
    return (f'otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}'
            f'&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}')


def qr_svg_data_uri(text):
    import segno  # libreria esterna inclusa in vendor/
    return segno.make(text, micro=False).svg_data_uri(scale=5, border=3, dark='#0b2440')


# --- Codici di recupero -------------------------------------------------------

def new_recovery_codes():
    codes = ['-'.join(secrets.token_hex(8).upper()[i:i + 4] for i in range(0, 16, 4)) for _ in range(RECOVERY_CODES)]
    return codes, [digest(c.replace('-', '')) for c in codes]


def normalize_recovery(code):
    value = str(code or '').replace('-', '').replace(' ', '').upper()
    return value if re.fullmatch(r'[0-9A-F]{16}', value) else None
