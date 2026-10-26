"""SOLO PROVE: crea un archivio 0.11 con soli dati fittizi usando il codice originale della 0.11 (qa/demo_seed.py),
per collaudare «manage.py migra-011» su un archivio prodotto dalla 0.11 vera.

Uso: python archivio_011_di_prova.py CARTELLA_SORGENTI_011 CARTELLA_USCITA_NUOVA
L'archivio resta in CARTELLA_USCITA/data/presenze.sqlite3, con la chiave 2FA di prova in CARTELLA_USCITA/chiave-2fa-prova.key.
"""
import contextlib
import json
import sys
from pathlib import Path

legacy, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
if out.exists():
    raise SystemExit(f'La cartella {out} esiste già: indicarne una nuova.')
out.mkdir(parents=True)
sys.path.insert(0, str(legacy))
sys.path.insert(0, str(legacy / 'qa'))
import demo_seed  # noqa: E402


@contextlib.contextmanager
def keep(prefix=''):
    yield str(out)


demo_seed.tempfile.TemporaryDirectory = keep
demo_seed.build(out / 'seed')

# --- Dati aggiuntivi per collaudare tutte le parti della migrazione (sempre fittizi) ---------------
import core, hr, approvals, staffing, departures, payroll, communications as mail, reminders  # noqa: E402,E401
from datetime import datetime, timezone  # noqa: E402
problems = []


def step(label, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        problems.append(f'{label}: {type(exc).__name__}: {exc}')
        return None


with core.connect() as c:
    users = {r['username']: core.public_user(r) for r in c.execute('SELECT * FROM users')}
    centers = [r['id'] for r in c.execute('SELECT id FROM centers ORDER BY rowid')]
    people = {(r['cid'], json.loads(r['data'])['name']): r['id'] for r in c.execute('SELECT cid, id, data FROM people')}
admin, hr_user = users['demo.admin'], users['demo.hr']
first, second, third = centers


def revision(cid):
    with core.connect() as c:
        return core.center(c, cid)['revision']


def entry(cid, pid, day, slot='m', code='m', layer='actual'):
    return core.mutate(admin, 'entry', dict(cid=cid, month=day[:7], revision=revision(cid),
                                             entry=dict(person_id=pid, day=day, slot=slot, code=code, layer=layer)))


# Modello di inserimento personalizzato (prima struttura)
def template():
    cfg = hr.read(core, admin, first)['settings']
    cfg['fields'] = [dict(id='badge', label='Numero badge', type='text', required=False)]
    return hr.settings_save(core, admin, {'cid': first, 'settings': cfg})
step('modello inserimento', template)

# Mese di settembre: Vomero con approvazione completa, Pozzuoli chiuso senza approvazione
for cid in (second, third):
    names = [n for (c_, n) in people if c_ == cid][:2]
    for name in names:
        for d in ('2026-09-01', '2026-09-02', '2026-09-03'):
            step(f'presenza {name} {d}', lambda cid=cid, name=name, d=d: entry(cid, people[(cid, name)], d))
    step(f'verifica {cid}', lambda cid=cid: core.mutate(admin, 'period_verify', dict(cid=cid, month='2026-09', revision=revision(cid), verified=True, note='Calendario verificato')))
step('chiusura Pozzuoli', lambda: core.mutate(admin, 'close', dict(cid=third, month='2026-09', revision=revision(third))))


def approval_flow():
    policy = approvals.read(core, admin, second, '2026-09')['policy']
    approvals.configure(core, admin, dict(cid=second, version=policy['version'], enabled=True, reason='Processo concordato con HR'))
    for action, extra in (('submit', {}), ('manager_approve', {'calendar_checked': True}), ('hr_approve', {})):
        data = approvals.read(core, admin, second, '2026-09')
        approvals.transition(core, admin, dict(cid=second, month='2026-09', version=data['workflow']['version'],
                                               fingerprint=data['fingerprint'], action=action, note='Passaggio di prova', **extra))
step('approvazione Vomero', approval_flow)

# Copertura: fabbisogni, indisponibilità, proposta di sostituzione
anna_first, anna_third = people[(first, 'Anna Rossi')], people[(third, 'Anna Rossi')]
step('fabbisogni', lambda: staffing.save_requirements(core, admin, dict(cid=first, version=0,
     weekly=[dict(weekday=0, slot='m', role='INF', minimum=2)], overrides=[dict(day='2026-10-12', slot='m', role='INF', minimum=1)])))
step('disponibilità', lambda: staffing.save_availability(core, hr_user, dict(cid=first, pid=people[(first, 'Marco Bianchi')], version=0,
     **{'from': '2026-10-26', 'to': '2026-10-27'}, status='unavailable', note='Assenza concordata', active=True)))
step('sostituzione', lambda: staffing.propose(core, hr_user, dict(cid=first, pid=anna_first, origin_cid=third, origin_pid=anna_third,
     day='2026-10-29', slot='p', code='p', note='Copertura concordata del pomeriggio')))

# Uscite e dotazioni
paolo = people[(first, 'Paolo Greco')]
step('dotazione', lambda: departures.equipment_save(core, admin, dict(cid=first, pid=paolo, version=0, kind='badge',
     inventory_code='BADGE 001', label='Badge dipendente', delivery_date='2026-10-01', due_date='2026-11-14')))
case = step('percorso uscita', lambda: departures.case_save(core, admin, dict(cid=first, pid=paolo, version=0, kind='termination',
            effective_date='2026-11-14', responsible='Responsabile Demo', reason='Cessazione pianificata')))
if case:
    step('attività uscita', lambda: departures.task_save(core, admin, dict(cid=first, id=case['id'], version=case['version'],
         task_id=case['tasks'][0]['id'], status='doing', note='In corso')))


# Paghe: modello in bozza con alcune causali associate
def payroll_template():
    current = payroll.read(core, admin, first)
    cfg = current['config']
    cfg['causes'].update(m='ORD', p='ORD', FE='FER')
    cfg['name'] = 'Tracciato di prova da concordare'
    payroll.save(core, admin, {'cid': first, 'expected_version': current['version'], 'config': cfg})
step('modello paghe', payroll_template)


# Posta: configurazione di prova DISATTIVATA e una bozza (nessun invio)
def mail_setup():
    version = mail.overview(core, admin)['settings']['version']
    mail.save_configuration(core, admin, {**mail.DEFAULT_SETTINGS, 'version': version, 'enabled': False,
                                          'host': 'smtp.example.invalid', 'from_email': 'hr@example.invalid'})
    view = mail.overview(core, hr_user)
    body = dict(template_id=view['templates'][0]['id'], list_id=view['lists'][0]['id'])
    prev = mail.preview(core, hr_user, body)
    mail.create_campaign(core, hr_user, {**body, 'fingerprint': prev['fingerprint']})
step('posta', mail_setup)


# Promemoria: configurazione salvata ma NON attiva
def reminder_setup():
    with core.connect() as c:
        current = reminders._settings(c)
    body = {k: current[k] for k in ['version', *reminders.DEFAULTS]}
    body.update(enabled=False, offsets=[30, 7, 0])
    reminders.configure(core, admin, body, datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc))
step('promemoria', reminder_setup)

with core.connect() as c:
    c.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?)', ('a' * 64, first, '2026-08'))
    c.commit()
print('problemi arricchimento:', problems or 'nessuno')

# Secondo fattore per un utente, come farebbe l'attivazione via web della 0.11.
import core, web_auth, pyotp  # noqa: E402,E401
key = out / 'chiave-2fa-prova.key'
web_auth.Auth.create_key(key)
auth = web_auth.Auth(key)
secret = pyotp.random_base32()
with core.connect() as c:
    uid = c.execute("SELECT id FROM users WHERE username='demo.hr'").fetchone()[0]
    c.execute("UPDATE web_security SET secret=?, enabled=1, recovery=?, last_login='2026-10-20T08:00:00' WHERE user_id=?",
              (auth.cipher.encrypt(secret.encode()).decode(), '[]', uid))
    c.commit()
(out / 'segreto-totp-prova.txt').write_text(secret)
print('archivio:', core.DB)
