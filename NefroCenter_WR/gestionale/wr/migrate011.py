"""Migrazione da un archivio della versione 0.11 (Persone e Presenze Web) a un nuovo archivio WR.

Regole:
- l'archivio 0.11 si apre solo in lettura e non cambia (conviene usare una copia di backup);
- il nuovo archivio WR si crea in una cartella senza archivio: se ne esiste già uno, la migrazione si ferma;
- tutto avviene in una sola transazione: o si importa tutto, o niente;
- password, codici di recupero e attivazioni in corso restano validi (stesso formato);
- l'app Authenticator resta valida solo se si fornisce la chiave 2FA della 0.11; altrimenti le persone
  che la usavano ricevono un codice di attivazione nuovo;
- posta e promemoria arrivano sempre DISATTIVATI: vanno ricontrollati e riattivati a mano;
- alla fine si confrontano i conteggi e si salva un rapporto senza segreti (migrazione-011.json).
"""
import base64
import hashlib
import json
import sqlite3
from pathlib import Path

from . import SCHEMA_VERSION, agreements, hr, rules, structures
from .util import dumps, new_id, stamp

REQUIRED = {'users', 'centers', 'people', 'entries', 'periods'}
KIND_HISTORY = {'contratto': 'contract', 'economia': 'economic', 'collegamento': 'link', 'applicazione al mese': 'apply',
                'contract': 'contract', 'economic': 'economic', 'link': 'link', 'apply': 'apply'}
KIND_PROCESS = {'case': 'departure', 'asset': 'equipment'}
LEGACY_ACTOR = 'migrazione-011'
REVIEW_COLOR = 'Colore della cella non riconosciuto: verificare la sede.'


class MigrationError(RuntimeError):
    """Errore che ferma la migrazione: nel nuovo archivio non resta nulla."""


def _loads(value, default=None):
    if value is None or value == '':
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _mime(name, content):
    if content[:5] == b'%PDF-':
        return 'application/pdf'
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if content[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    lower = name.lower()
    for ext, mime in (('.pdf', 'application/pdf'), ('.png', 'image/png'), ('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg')):
        if lower.endswith(ext):
            return mime
    return 'application/octet-stream'


class Source:
    """Archivio 0.11 aperto in sola lettura."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise MigrationError(f'Archivio 0.11 non trovato: {self.path}')
        self.con = sqlite3.connect(f'file:{self.path.resolve().as_posix()}?mode=ro', uri=True)
        self.con.row_factory = sqlite3.Row
        self.tables = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'identities' in self.tables:
            raise MigrationError('Il file indicato è già un archivio NefroCenter WR, non della versione 0.11.')
        missing = REQUIRED - self.tables
        if missing:
            raise MigrationError('Il file non sembra un archivio della versione 0.11: mancano le tabelle '
                                 + ', '.join(sorted(missing)) + '.')
        if self.con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise MigrationError('L’archivio 0.11 risulta danneggiato (controllo di integrità non superato): usare un backup valido.')
        self.user_version = self.con.execute('PRAGMA user_version').fetchone()[0]
        if self.user_version < 8:
            raise MigrationError('Archivio di una versione precedente alla 0.11: aprirlo prima con la 0.11.2 '
                                 'perché ne aggiorni la struttura, poi ripetere la migrazione da un backup.')

    def rows(self, table, order=''):
        if table not in self.tables:
            return []
        return [dict(r) for r in self.con.execute(f'SELECT * FROM "{table}" {order}')]

    def count(self, table):
        return self.con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] if table in self.tables else 0

    def close(self):
        self.con.close()


class Migration:
    def __init__(self, source, con, auth, legacy_cipher, now):
        self.src = source
        self.con = con
        self.auth = auth
        self.legacy_cipher = legacy_cipher
        self.now = now
        self.warnings = []
        self.counts = {}
        self.activation_codes = []
        self.person_ids = {}      # (cid, pid 0.11) -> id WR
        self.person_center = {}   # id WR -> cid
        self.configs = {}         # (cid, versione) -> parametri
        self.current = {}         # cid -> versione corrente
        self.center_names = {}

    # --- utilità -------------------------------------------------------------------------------
    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    def add(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def insert(self, table, values):
        cols = ','.join(values)
        marks = ','.join('?' * len(values))
        self.con.execute(f'INSERT INTO {table}({cols}) VALUES({marks})', tuple(values.values()))

    def person(self, cid, pid):
        return self.person_ids.get((cid, pid))

    # --- strutture e parametri -----------------------------------------------------------------
    def centers(self):
        periods = {}
        for p in self.src.rows('periods'):
            periods.setdefault(p['cid'], []).append((p['month'], _loads(p['data'], {})))
        for c in self.src.rows('centers', 'ORDER BY rowid'):
            cid = c['id']
            self.center_names[cid] = c['name']
            current = _loads(c['config'], {})
            versions = {int(c['version']): current}
            for month, data in periods.get(cid, []):
                version = int(data.get('version') or c['version'])
                cfg = data.get('config') or current
                if version in versions and dumps(versions[version]) != dumps(cfg):
                    self.warn(f'{c["name"]}: parametri diversi con lo stesso numero di versione {version}; '
                              f'si conserva quello del mese {month} come versione separata.')
                    version = max(versions) + 1
                    data['version'] = version
                versions.setdefault(version, cfg)
            self.insert('centers', dict(id=cid, name=c['name'][:150], code=c['code'], active=1,
                                        config_version=int(c['version']), version=1, created_at=self.now))
            for version in sorted(versions):
                cfg = self.validated_config(c['name'], versions[version], version)
                self.configs[(cid, version)] = cfg
                self.insert('center_configs', dict(center_id=cid, version=version, data=dumps(cfg),
                                                   note='Parametri importati dalla versione 0.11' if version == int(c['version'])
                                                   else 'Parametri di un mese della versione 0.11',
                                                   created_at=self.now, created_by=LEGACY_ACTOR))
                self.add('center_configs')
            self.current[cid] = int(c['version'])
            self.add('centers')
        self._period_data = periods

    def validated_config(self, name, cfg, version):
        merged = {**rules.defaults(), **(cfg or {})}
        try:
            return rules.validate_config(merged)
        except Exception as exc:  # noqa: BLE001 - messaggio rivolto all'amministratore
            raise MigrationError(f'{name}: parametri della versione {version} non validi ({getattr(exc, "message", exc)}). '
                                 'Correggerli nella 0.11 e ripetere la migrazione da un nuovo backup.') from None

    def structures(self):
        for r in self.src.rows('structure_profiles'):
            if r['cid'] not in self.center_names:
                continue
            raw = _loads(r['data'], {})
            raw = raw.get('fields', raw) if isinstance(raw, dict) else {}
            fields = {k: str(raw.get(k, '') or '') for k in structures.KEYS}
            self.insert('structures', dict(center_id=r['cid'], data=dumps(fields), version=int(r['version'] or 1),
                                           updated_at=self.now, updated_by=LEGACY_ACTOR))
            self.add('structures')

    # --- accessi ----------------------------------------------------------------------------------
    def users(self):
        security_rows = {r['user_id']: r for r in self.src.rows('web_security')}
        for u in self.src.rows('users'):
            role = u['role'] if u['role'] in ('admin', 'hr', 'manager', 'operator', 'viewer') else 'viewer'
            if role != u['role']:
                self.warn(f'Account {u["username"]}: ruolo «{u["role"]}» non riconosciuto, impostato «consultazione».')
            self.insert('users', dict(id=u['id'], username=u['username'], name=u['name'], role=role, active=int(bool(u['active'])),
                                      password=u['credential'], version=1, created_at=self.now, updated_at=self.now))
            assigned = [] if role in ('admin', 'hr') else [c for c in _loads(u['centers'], []) if c in self.center_names]
            for cid in sorted(set(assigned)):
                self.insert('user_centers', dict(user_id=u['id'], center_id=cid))
            sec = security_rows.get(u['id'])
            values = dict(user_id=u['id'], totp_secret='', totp_enabled=0, totp_last_step=-1, recovery='[]',
                          activation_hash='', activation_until=0, generation=1, last_login='')
            needs_code = False
            if sec:
                values['last_login'] = sec['last_login'] or ''
                values['recovery'] = sec['recovery'] if isinstance(_loads(sec['recovery']), list) else '[]'
                if sec['activation'] and float(sec['activation_until'] or 0) > self.auth.clock():
                    values['activation_hash'] = sec['activation']
                    values['activation_until'] = float(sec['activation_until'])
                    self.add('activation_pending_kept')
                if sec['enabled'] and sec['secret']:
                    secret = self.decrypt_secret(sec['secret'])
                    if secret:
                        values.update(totp_secret=self.auth._encrypt(secret), totp_enabled=1,
                                      totp_last_step=int(sec['last_step'] if sec['last_step'] is not None else -1))
                        self.add('authenticator_kept')
                    else:
                        values['recovery'] = '[]'
                        needs_code = bool(u['active'])
            self.insert('user_security', values)
            if needs_code:
                code = self.auth.issue_activation(self.con, u['id'], None, 'Migrazione dalla 0.11 senza la chiave 2FA')
                self.activation_codes.append((u['username'], code))
            self.add('users')
        for e in self.src.rows('web_events', 'ORDER BY id'):
            self.insert('security_events', dict(at=e['stamp'], user_id=e['user_id'], actor=e['actor'], action=e['action'],
                                                detail=e['detail'] or ''))
            self.add('security_events')
        if not self.con.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone():
            self.warn('Nessun amministratore attivo nell’archivio 0.11: crearne uno con «python manage.py activate».')

    def decrypt_secret(self, value):
        if self.legacy_cipher is None:
            return None
        try:
            return self.legacy_cipher.decrypt(value.encode()).decode()
        except Exception:  # noqa: BLE001 - chiave non corrispondente: si chiede una nuova attivazione
            self.warn('La chiave 2FA indicata non apre il segreto di almeno un account: per quegli account serve '
                      'una nuova attivazione.')
            return None

    # --- persone e identità ------------------------------------------------------------------------
    def people(self):
        assignments = {(r['cid'], r['pid']): r['global_id'] for r in self.src.rows('workforce_assignments')}
        identities = {r['id']: int(r['version'] or 1) for r in self.src.rows('group_people')}
        used_identity = set()
        used_ids = set()
        registrations = set()
        created = {}
        for r in self.src.rows('people', 'ORDER BY rowid'):
            cid = r['cid']
            if cid not in self.center_names:
                self.warn(f'Persona {r["id"]} riferita a una struttura inesistente: non importata.')
                continue
            d = _loads(r['data'], {})
            pid = r['id'] if r['id'] not in used_ids else new_id()
            if pid != r['id']:
                self.warn(f'{d.get("name", r["id"])}: identificativo ripetuto in più strutture, assegnato uno nuovo.')
            used_ids.add(pid)
            identity = assignments.get((cid, r['id'])) or new_id()
            if (identity, cid) in used_identity:
                self.warn(f'{d.get("name", "")}: due schede della stessa persona nella stessa struttura; la seconda resta separata.')
                identity = new_id()
            used_identity.add((identity, cid))
            if identity not in created:
                self.insert('identities', dict(id=identity, version=identities.get(identity, 1)))
                created[identity] = True
                self.add('identities')
            registration = str(d.get('registration') or '').strip()
            if registration and (cid, registration) in registrations:
                self.warn(f'{d.get("name", "")}: matricola {registration} già usata nella struttura, lasciata vuota.')
                registration = ''
            if registration:
                registrations.add((cid, registration))
            cfg = self.configs[(cid, self.current[cid])]
            role = d.get('role') or 'ALTRO'
            if role not in cfg['roles']:
                self.warn(f'{d.get("name", "")}: ruolo «{role}» non presente fra i ruoli della struttura.')
            pay = d.get('pay_override')
            self.insert('people', dict(id=pid, center_id=cid, identity_id=identity, name=str(d.get('name') or 'Senza nome')[:150],
                                       role=role, registration=registration, active=int(bool(d.get('active', True))),
                                       note=str(d.get('note') or '')[:2000], contract=str(d.get('contract') or '')[:150],
                                       pay_override=dumps(pay) if pay else '', version=1, created_at=self.now, updated_at=self.now))
            self.person_ids[(cid, r['id'])] = pid
            self.person_center[pid] = cid
            self.add('people')

    # --- registro, mesi, pazienti, accordi ------------------------------------------------------------
    def entries(self):
        seen = {}
        rows = []
        for r in self.src.rows('entries'):
            d = _loads(r['data'], {})
            pid = self.person(r['cid'], d.get('person_id'))
            if not pid:
                self.warn('Registrazioni riferite a persone non presenti: non importate (vedere il conteggio «entries_skipped»).')
                self.add('entries_skipped')
                continue
            rows.append((r['cid'], pid, d))
        rows.sort(key=lambda x: (x[2].get('updated_at') or '', x[2].get('id') or ''))
        for cid, pid, d in rows:
            key = (pid, d.get('day'), d.get('slot'), d.get('layer'))
            if key in seen:
                self.warn('Registrazioni doppie nella stessa fascia: si conserva la più recente (vedere «entries_duplicates»).')
                self.add('entries_duplicates')
                self.con.execute('DELETE FROM entries WHERE id=?', (seen[key],))
                self.add('entries', -1)
            site_raw = str(d.get('work_site') or '')
            home = {'', self.center_names.get(cid, '')}
            note = str(d.get('note') or '')
            review = ''
            site = '' if site_raw in home else site_raw
            if site_raw == rules.IMPORT_SITE or 'da specificare' in site_raw:
                site, review = rules.IMPORT_SITE, rules.IMPORT_SITE_REVIEW
            if 'Colore sede da verificare' in note:
                review = REVIEW_COLOR
            source = ''
            if note.startswith('Importato da '):
                source = 'excel:' + note[len('Importato da '):].split(' | ')[0][:40]
            kind = d.get('kind') if d.get('kind') in ('work', 'absence', 'rest') else 'work'
            pause = d.get('pause')
            pause = int((d.get('break_minutes') if pause is None else pause) or 0)
            eid = d.get('id') or new_id()
            version = int(d.get('config_version') or self.current[cid])
            if (cid, version) not in self.configs:
                version = self.current[cid]
            self.insert('entries', dict(
                id=eid, center_id=cid, person_id=pid, day=d['day'], slot=d['slot'],
                layer=d.get('layer') if d.get('layer') in ('actual', 'planned') else 'actual',
                code=d.get('code') or '', kind=kind, label=str(d.get('code_label') or d.get('code') or ''),
                start=d.get('start') or '', end=d.get('end') or '', pause=pause,
                overnight=int(bool(d.get('overnight'))), site=site, holiday=int(bool(d.get('holiday'))),
                credit=int(d.get('credit_minutes') or 0), note=note[:2000], source=source, review=review,
                rules_version=version, version=1, updated_at=d.get('updated_at') or self.now,
                updated_by=d.get('updated_by') or LEGACY_ACTOR))
            seen[key] = eid
            self.add('entries')

    def months(self):
        people_by_center = {}
        for (cid, legacy_pid), pid in self.person_ids.items():
            people_by_center.setdefault(cid, {})[legacy_pid] = pid
        for cid, items in self._period_data.items():
            if cid not in self.center_names:
                continue
            for month, data in items:
                version = int(data.get('version') or self.current[cid])
                self.insert('months', dict(center_id=cid, month=month, rules_version=version,
                                           verified=int(bool(data.get('verified'))), closed=int(bool(data.get('closed'))),
                                           note=str(data.get('note') or '')[:2000], version=1, updated_at=self.now,
                                           updated_by=LEGACY_ACTOR))
                self.add('months')
                cfg = self.configs[(cid, version)]
                for legacy_pid, ag in (data.get('agreements') or {}).items():
                    pid = people_by_center.get(cid, {}).get(legacy_pid)
                    if not pid or not isinstance(ag, dict):
                        continue
                    if not ag.get('version'):
                        self.add('agreements_proposals_recalculated')
                        continue
                    try:
                        clean = agreements.validate({k: ag[k] for k in agreements.FIELDS if k in ag}, cfg)
                    except Exception as exc:  # noqa: BLE001
                        self.warn(f'Accordo del mese {month} non importato ({getattr(exc, "message", exc)}).')
                        self.add('agreements_skipped')
                        continue
                    if ag.get('workforce_segments'):
                        clean['segments'] = [dict(id=s.get('id') or new_id(), version=int(s.get('version') or 1),
                                                  valid_from=s.get('effective_from'), valid_to=s.get('effective_to'),
                                                  data=s.get('data') or {}) for s in ag['workforce_segments']]
                    self.insert('agreements', dict(center_id=cid, month=month, person_id=pid, data=dumps(clean),
                                                   source=str(ag.get('source') or 'Accordo importato dalla 0.11')[:1000],
                                                   version=int(ag['version']), updated_at=ag.get('updated_at') or self.now,
                                                   updated_by=ag.get('updated_by') or LEGACY_ACTOR))
                    self.add('agreements')

    def workload(self):
        for r in self.src.rows('patients'):
            d = _loads(r['data'], {})
            if r['cid'] not in self.center_names or not d.get('day'):
                continue
            self.insert('workload', dict(center_id=r['cid'], day=d['day'], slot=d['slot'], ordinary=int(d.get('ordinary') or 0),
                                         isolated=int(d.get('isolated') or 0), updated_at=d.get('updated_at') or self.now,
                                         updated_by=d.get('updated_by') or LEGACY_ACTOR))
            self.add('workload')

    # --- fascicoli, inserimento, documenti ----------------------------------------------------------------
    def hr(self):
        for r in self.src.rows('hr_settings'):
            if r['cid'] not in self.center_names:
                continue
            d = _loads(r['data'], {})
            try:
                tasks, fields = hr.validate_template(dict(tasks=d.get('tasks') or [], fields=d.get('fields') or [], version=0))
            except Exception as exc:  # noqa: BLE001
                self.warn(f'Modello di inserimento di {self.center_names[r["cid"]]} non importato ({getattr(exc, "message", exc)}).')
                continue
            self.insert('onboarding_templates', dict(center_id=r['cid'], tasks=dumps(tasks), fields=dumps(fields),
                                                     version=int(r['version'] or 1), updated_at=self.now, updated_by=LEGACY_ACTOR))
            self.add('onboarding_templates')
        for r in self.src.rows('hr_profiles'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            d = _loads(r['data'], {})
            raw = d.get('fields') or {}
            fields = {k: str(raw.get(k, '') or '') for k in hr.KEYS}
            stage = d.get('stage') if d.get('stage') in hr.STAGES else 'active'
            self.insert('profiles', dict(person_id=pid, stage=stage, fields=dumps(fields), custom=dumps(d.get('custom') or {}),
                                         version=int(r['version'] or 1), updated_at=d.get('updated_at') or self.now,
                                         updated_by=d.get('updated_by') or LEGACY_ACTOR))
            for position, t in enumerate(d.get('tasks') or []):
                status = t.get('status') if t.get('status') in hr.TASK_STATES else 'todo'
                self.insert('onboarding_tasks', dict(person_id=pid, task_id=str(t.get('id') or f'attivita{position}')[:40], position=position,
                                                     phase=str(t.get('phase') or '')[:80], label=str(t.get('label') or '')[:200],
                                                     owner=str(t.get('owner') or '')[:150], due=t.get('due') or '', status=status,
                                                     note=str(t.get('note') or '')[:1000], done_at=t.get('completed_at') or '',
                                                     done_by=t.get('completed_by') or ''))
                self.add('onboarding_tasks')
            self.add('profiles')
        for r in self.src.rows('hr_history', 'ORDER BY rowid'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            self.con.execute('INSERT OR IGNORE INTO profile_history(person_id,version,at,actor,data) VALUES(?,?,?,?,?)',
                             (pid, int(r['version']), r['stamp'], r['actor'], r['data'] or '{}'))
            self.add('profile_history')
        for r in self.src.rows('hr_documents', 'ORDER BY uploaded_at, id'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                self.warn('Documenti di persone non presenti: non importati (vedere «documents_skipped»).')
                self.add('documents_skipped')
                continue
            content = r['content']
            if isinstance(content, str):
                content = base64.b64decode(content)
            content = bytes(content or b'')
            digest = hashlib.sha256(content).hexdigest()
            if r['sha256'] and r['sha256'] != digest:
                self.warn(f'Documento «{r["name"]}»: impronta registrata diversa dal contenuto; si usa quella ricalcolata.')
            self.insert('documents', dict(id=r['id'], center_id=r['cid'], person_id=pid, name=r['name'], category=r['category'] or 'Altro',
                                          expiry=r['expiry'] or '', mime=_mime(r['name'], content), size=len(content), sha256=digest,
                                          content=content, uploaded_at=r['uploaded_at'] or self.now, uploaded_by=r['uploaded_by'] or LEGACY_ACTOR))
            self.add('documents')
        reviewed = set()
        for r in self.src.rows('hr_document_reviews'):
            if not self.con.execute('SELECT 1 FROM documents WHERE id=?', (r['document_id'],)).fetchone():
                continue
            status = r['status'] if r['status'] in ('received', 'needs_correction', 'verified') else 'received'
            self.insert('document_reviews', dict(document_id=r['document_id'], status=status, note=r['note'] or '',
                                                 version=int(r['version'] or 1), updated_at=r['updated_at'] or self.now,
                                                 updated_by=r['updated_by'] or LEGACY_ACTOR))
            reviewed.add(r['document_id'])
            self.add('document_reviews')
        for (doc_id,) in self.con.execute('SELECT id FROM documents').fetchall():
            if doc_id not in reviewed:
                self.insert('document_reviews', dict(document_id=doc_id, status='received', note='', version=1,
                                                     updated_at=self.now, updated_by=LEGACY_ACTOR))
                self.add('document_reviews')
        for r in self.src.rows('hr_document_review_history', 'ORDER BY rowid'):
            if r['document_id'] in reviewed:
                self.con.execute('INSERT OR IGNORE INTO document_review_history(document_id,version,status,note,at,actor) '
                                 'VALUES(?,?,?,?,?,?)', (r['document_id'], int(r['version']), r['status'], r['note'] or '',
                                                         r['stamp'], r['actor']))
                self.add('document_review_history')

    # --- personale di gruppo -------------------------------------------------------------------------------
    def workforce(self):
        for table, target in (('workforce_contracts', 'contracts'), ('workforce_economics', 'economics')):
            for r in self.src.rows(table):
                pid = self.person(r['cid'], r['pid'])
                if not pid:
                    continue
                self.insert(target, dict(id=r['id'], person_id=pid, valid_from=r['effective_from'], valid_to=r['effective_to'] or '',
                                         data=r['data'], version=int(r['version'] or 1), updated_at=self.now, updated_by=LEGACY_ACTOR))
                self.add(target)
        for r in self.src.rows('workforce_history', 'ORDER BY id'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            self.insert('workforce_history', dict(person_id=pid, kind=KIND_HISTORY.get(r['kind'], r['kind']), record_id=r['record_id'] or '',
                                                  at=r['stamp'], actor=r['actor'], reason=r['reason'] or '',
                                                  before=r['before_data'], after=r['after_data']))
            self.add('workforce_history')

    # --- approvazioni, copertura, uscite, paghe ------------------------------------------------------------
    def approvals(self):
        from . import approvals as wr_approvals
        for r in self.src.rows('approval_policies'):
            if r['cid'] in self.center_names:
                self.insert('approval_policies', dict(center_id=r['cid'], enabled=int(bool(r['enabled'])), reason=r['reason'] or '',
                                                      version=int(r['version'] or 1), updated_at=r['updated_at'] or self.now,
                                                      updated_by=r['updated_by'] or LEGACY_ACTOR))
                self.add('approval_policies')
        for r in self.src.rows('approval_months'):
            if r['cid'] not in self.center_names:
                continue
            status = r['status'] if r['status'] in ('draft', 'submitted', 'manager_approved', 'hr_approved', 'returned') else 'draft'
            self.insert('approvals', dict(center_id=r['cid'], month=r['month'], status=status, fingerprint=r['fingerprint'] or '',
                                          note=r['note'] or '', version=int(r['version'] or 1), updated_at=r['updated_at'] or self.now,
                                          updated_by=r['updated_by'] or LEGACY_ACTOR))
            self.add('approvals')
        for r in self.src.rows('approval_history', 'ORDER BY rowid'):
            if r['cid'] in self.center_names:
                self.con.execute('INSERT OR IGNORE INTO approval_history(center_id,month,version,action,status,note,fingerprint,at,actor) '
                                 'VALUES(?,?,?,?,?,?,?,?,?)', (r['cid'], r['month'], int(r['version']), r['action'], r['status'],
                                                              r['note'] or '', r['fingerprint'] or '', r['stamp'], r['actor']))
                self.add('approval_history')
        # L'impronta dell'approvazione si calcola sui dati: la 0.11 usava un altro calcolo, quindi si ricalcola qui,
        # sugli stessi dati appena importati, per i mesi già inviati o approvati.
        for r in self.con.execute("SELECT center_id, month FROM approvals WHERE status<>'draft'").fetchall():
            value = wr_approvals.fingerprint(self.con, r['center_id'], r['month'])
            self.con.execute('UPDATE approvals SET fingerprint=? WHERE center_id=? AND month=?', (value, r['center_id'], r['month']))
            self.add('approvals_fingerprint_recalculated')

    def staffing(self):
        from . import staffing as wr_staffing
        for r in self.src.rows('staffing_requirements'):
            if r['cid'] not in self.center_names:
                continue
            d = _loads(r['data'], {})
            self.insert('staffing_requirements', dict(center_id=r['cid'], weekly=dumps(d.get('weekly') or []),
                                                      overrides=dumps(d.get('overrides') or []), version=int(r['version'] or 1),
                                                      updated_at=self.now, updated_by=LEGACY_ACTOR))
            self.add('staffing_requirements')
        for r in self.src.rows('staffing_availability'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            status = r['status'] if r['status'] in ('available', 'unavailable', 'preferred') else 'unavailable'
            self.insert('availability', dict(id=r['id'], person_id=pid, start=r['start'], end=r['end'], status=status, note=r['note'] or '',
                                             active=int(bool(r['active'])), version=int(r['version'] or 1),
                                             updated_at=r['stamp'] or self.now, updated_by=r['actor'] or LEGACY_ACTOR))
            self.add('availability')
        for r in self.src.rows('staffing_proposals'):
            pid, origin = self.person(r['cid'], r['pid']), self.person(r['origin_cid'], r['origin_pid'])
            if not pid or not origin:
                self.warn('Proposte di sostituzione con persone non presenti: non importate.')
                continue
            status = r['status'] if r['status'] in ('pending', 'accepted', 'rejected') else 'rejected'
            self.insert('substitutions', dict(id=r['id'], center_id=r['cid'], person_id=pid, origin_center_id=r['origin_cid'],
                                              origin_person_id=origin, day=r['day'], slot=r['slot'], code=r['code'], note=r['note'] or '',
                                              status=status, fingerprint=r['fingerprint'] or '', version=int(r['version'] or 1),
                                              created_at=r['stamp'] or self.now, created_by=r['actor'] or LEGACY_ACTOR,
                                              decision_note=r['decision_note'] or '', decided_at=r['decided_at'] or '',
                                              decided_by=r['decided_by'] or '', entry_id=r['entry_id'] or ''))
            self.add('substitutions')
            if status == 'pending':
                sub = dict(self.con.execute('SELECT * FROM substitutions WHERE id=?', (r['id'],)).fetchone())
                try:
                    value, _, _ = wr_staffing._state(self.con, sub)
                    self.con.execute('UPDATE substitutions SET fingerprint=? WHERE id=?', (value, r['id']))
                except Exception:  # noqa: BLE001 - resta l'impronta 0.11: chi decide dovrà rifare la proposta
                    self.warn('Una proposta di sostituzione in attesa non è più valida con i dati attuali: '
                              'andrà rifiutata e rifatta.')

    def departures(self):
        for r in self.src.rows('departure_cases'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            d = _loads(r['data'], {})
            status = r['status'] if r['status'] in ('open', 'in_progress', 'completed', 'cancelled') else 'open'
            kind = d.get('kind') if d.get('kind') in ('termination', 'transfer') else 'termination'
            self.insert('departures', dict(id=r['id'], center_id=r['cid'], person_id=pid, kind=kind,
                                           destination_center_id=d.get('destination_cid') or '', effective_date=d.get('effective_date') or '',
                                           reason=d.get('reason') or '', responsible=d.get('responsible') or '', status=status,
                                           tasks=dumps(d.get('tasks') or []), closure_note=d.get('closure_note') or '',
                                           version=int(r['version'] or 1), created_at=d.get('created_at') or self.now,
                                           updated_at=d.get('updated_at') or self.now, closed_at=d.get('closed_at') or '',
                                           closed_by=d.get('closed_by') or ''))
            self.add('departures')
        for r in self.src.rows('equipment_assignments'):
            pid = self.person(r['cid'], r['pid'])
            if not pid:
                continue
            d = _loads(r['data'], {})
            kind = d.get('kind') if d.get('kind') in ('badge', 'keys', 'device', 'other') else 'other'
            self.insert('equipment', dict(id=r['id'], center_id=r['cid'], person_id=pid, kind=kind, inventory_code=d.get('inventory_code') or '',
                                          asset_key=r['asset_key'] or ' '.join(str(d.get('inventory_code') or '').split()).casefold(),
                                          label=d.get('label') or '', delivery_date=d.get('delivery_date') or '', due_date=d.get('due_date') or '',
                                          note=d.get('note') or '', status='returned' if r['status'] == 'returned' else 'assigned',
                                          return_date=d.get('return_date') or '', return_condition=d.get('return_condition') or '',
                                          return_note=d.get('return_note') or '', returned_by=d.get('returned_by') or '',
                                          version=int(r['version'] or 1), created_at=d.get('created_at') or self.now,
                                          updated_at=d.get('updated_at') or self.now))
            self.add('equipment')
        for r in self.src.rows('departure_history', 'ORDER BY id'):
            self.insert('process_history', dict(kind=KIND_PROCESS.get(r['kind'], r['kind']), object_id=r['object_id'], version=int(r['version'] or 1),
                                                at=r['stamp'], actor=r['actor'], action=r['action'], data=r['data'] or '{}'))
            self.add('process_history')

    def payroll(self):
        for r in self.src.rows('payroll_templates', 'ORDER BY cid, version'):
            if r['cid'] not in self.center_names:
                continue
            d = _loads(r['data'], {})
            regs = d.get('registrations') or {}
            d['registrations'] = {self.person(r['cid'], k): val for k, val in regs.items() if self.person(r['cid'], k)}
            self.insert('payroll_templates', dict(center_id=r['cid'], version=int(r['version']), data=dumps(d),
                                                  created_at=r['created_at'] or self.now, created_by=r['created_by'] or LEGACY_ACTOR))
            self.add('payroll_templates')

    # --- posta e promemoria: sempre disattivati -------------------------------------------------------------------
    def mail(self):
        for r in self.src.rows('communication_settings'):
            d = _loads(r['data'], {})
            if d.get('enabled'):
                self.warn('Il servizio di posta era attivo nella 0.11: arriva DISATTIVATO. Ricontrollarlo e riattivarlo a mano.')
            d['enabled'] = False
            self.insert('mail_settings', dict(id=1, data=dumps(d), version=int(r['version'] or 1)))
        for table, target in (('communication_templates', 'mail_templates'), ('communication_lists', 'mail_lists')):
            for r in self.src.rows(table):
                self.insert(target, dict(id=r['id'], data=r['data'], version=int(r['version'] or 1)))
                self.add(target)
        reminder_recipients = {r['recipient_id'] for r in self.src.rows('reminder_events')}
        recipients = self.src.rows('communication_recipients', 'ORDER BY campaign_id, ordinal')
        by_campaign = {}
        for r in recipients:
            by_campaign.setdefault(r['campaign_id'], []).append(r)
        for c in self.src.rows('communication_campaigns'):
            items = by_campaign.get(c['id'], [])
            source = 'reminders' if any(r['id'] in reminder_recipients for r in items) else 'manual'
            self.insert('mail_campaigns', dict(id=c['id'], source=source, data=c['data'], created_at=c['created_at'], created_by=c['created_by']))
            self.add('mail_campaigns')
            for r in items:
                d = _loads(r['data'], {})
                d = {('center_id' if k == 'cid' else 'person_id' if k == 'pid' else k): val for k, val in d.items()}
                if d.get('person_id'):
                    d['person_id'] = self.person(d.get('center_id'), d['person_id']) or d['person_id']
                status, error = r['status'], r['error'] or ''
                if status == 'sending':
                    status, error = 'uncertain', 'Invio interrotto prima della migrazione: verificare lo storico del server di posta.'
                if status not in ('pending', 'accepted', 'failed', 'uncertain', 'simulated'):
                    status = 'uncertain'
                self.insert('mail_recipients', dict(id=r['id'], campaign_id=c['id'], ordinal=int(r['ordinal']), data=dumps(d), status=status,
                                                    error=error, claimed_at=r['claimed_at'], batch_id=''))
                self.add('mail_recipients')
        known = {r[0] for r in self.con.execute('SELECT id FROM mail_recipients')}
        for a in self.src.rows('communication_attempts', 'ORDER BY rowid'):
            if a['recipient_id'] not in known:
                continue
            status = 'uncertain' if a['status'] == 'sending' else a['status']
            self.insert('mail_attempts', dict(id=a['id'], recipient_id=a['recipient_id'], number=int(a['number']), status=status,
                                              started_at=a['started_at'], started_epoch=float(a['started_epoch'] or 0),
                                              finished_at=a['finished_at'] or '', error=a['error'] or '', message_id=a['message_id'] or ''))
            self.add('mail_attempts')
        for r in self.src.rows('reminder_settings'):
            d = _loads(r['data'], {})
            if d.get('enabled'):
                self.warn('I promemoria automatici erano attivi nella 0.11: arrivano DISATTIVATI. Ricontrollarli e riattivarli a mano.')
            d.update(enabled=False, approved_routes={})
            self.insert('reminder_settings', dict(id=1, data=dumps(d), version=int(r['version'] or 1), enabled_by=''))
        for e in self.src.rows('reminder_events'):
            if e['recipient_id'] in known:
                self.insert('reminder_events', dict(event_key=e['event_key'], center_id=e['cid'], source_key=e['source_key'], due=e['due'],
                                                    threshold=int(e['threshold']), email=e['email'], topic=e['topic'],
                                                    created_at=e['created_at'], recipient_id=e['recipient_id']))
                self.add('reminder_events')
        for r in self.src.rows('reminder_runs'):
            self.insert('reminder_runs', dict(id=r['id'], at=r['stamp'], state=r['state'], messages=int(r['messages']),
                                              events=int(r['events']), note=r['note'] or ''))
            self.add('reminder_runs')

    # --- registro attività e importazioni ---------------------------------------------------------------------------
    def history(self):
        for r in self.src.rows('audit', 'ORDER BY id'):
            self.insert('audit', dict(at=r['stamp'] or self.now, actor=r['username'] or LEGACY_ACTOR,
                                      center_id=r['cid'] if r['cid'] in self.center_names else None, action=r['action'] or '',
                                      entity='0.11', entity_id='', before=r['before_data'], after=r['after_data']))
            self.add('audit')
        for r in self.src.rows('imports'):
            if r['cid'] in self.center_names:
                self.insert('imports', dict(hash=r['hash'], center_id=r['cid'], month=r['month'], at=self.now))
                self.add('imports')

    def run(self):
        self.centers()
        self.structures()
        self.users()
        self.people()
        self.entries()
        self.months()
        self.workload()
        self.hr()
        self.workforce()
        self.approvals()
        self.staffing()
        self.departures()
        self.payroll()
        self.mail()
        self.history()


def run(source_path, data_dir, key_file, legacy_key=None, clock=None):
    """Crea un nuovo archivio WR in data_dir partendo da un archivio 0.11. Restituisce il rapporto."""
    from . import app
    from .auth import Auth
    from .permissions import User
    from . import audit
    source = Source(source_path)
    data_dir = Path(data_dir)
    db = app.database(data_dir)
    if db.path.exists():
        source.close()
        raise MigrationError(f'Nella cartella {data_dir} esiste già un archivio: la migrazione crea sempre un archivio nuovo '
                             'e non modifica quelli esistenti. Indicare una cartella vuota.')
    legacy_cipher = None
    if legacy_key:
        from cryptography.fernet import Fernet
        legacy_cipher = Fernet(Path(legacy_key).read_bytes().strip())
    source_hash = _sha256(source.path)
    source_counts = {t: source.count(t) for t in sorted(source.tables) if not t.startswith('sqlite_')}
    created = False
    try:
        db.migrate()
        created = True
        auth = Auth(db, key_file, **({'clock': clock} if clock else {}))
        app.load_modules()
        now = stamp()
        with db.write() as con:
            job = Migration(source, con, auth, legacy_cipher, now)
            job.run()
            problems = con.execute('PRAGMA foreign_key_check').fetchall()
            if problems:
                raise MigrationError(f'Riferimenti incoerenti dopo l’importazione ({len(problems)}): nessun dato è stato salvato.')
            for key, value in (('migrated_from', f'0.11 (schema {source.user_version})'), ('migrated_at', now),
                               ('migration_source_sha256', source_hash)):
                con.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, value))
            audit.record(con, User(id='', username='console', name='Console del server', role='admin'),
                         'Migrazione dalla versione 0.11', entity='migration', entity_id=source_hash[:16],
                         after=dict(counts=job.counts, warnings=len(job.warnings)))
        with db.read() as con:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise MigrationError('Controllo di integrità del nuovo archivio non superato.')
            target_counts = {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in (
                'centers', 'users', 'people', 'entries', 'months', 'documents', 'audit')}
    except BaseException:
        source.close()
        if created:
            for suffix in ('', '-wal', '-shm'):
                part = Path(str(db.path) + suffix)
                if part.exists():
                    part.unlink()
        raise
    source.close()
    expected = dict(centers=source_counts.get('centers', 0), users=source_counts.get('users', 0), people=source_counts.get('people', 0),
                    entries=source_counts.get('entries', 0) - job.counts.get('entries_skipped', 0) - job.counts.get('entries_duplicates', 0),
                    documents=source_counts.get('hr_documents', 0) - job.counts.get('documents_skipped', 0))
    mismatches = {k: (expected[k], target_counts[k]) for k in expected if expected[k] != target_counts[k]}
    if mismatches:
        job.warn('Conteggi diversi fra 0.11 e WR: ' + ', '.join(f'{k} {a}→{b}' for k, (a, b) in mismatches.items()))
    from . import backups
    backup = backups.create(db, 'dopo-migrazione-011')
    summary = dict(sorgente=str(Path(source_path).resolve()), impronta_sorgente=source_hash, schema_sorgente=source.user_version,
                   archivio_wr=str(db.path), schema_wr=SCHEMA_VERSION, eseguita_il=now, backup=Path(str(backup)).name,
                   conteggi_0_11=source_counts, conteggi_wr=target_counts, importati=job.counts, avvisi=job.warnings,
                   account_da_riattivare=[u for u, _ in job.activation_codes],
                   posta='disattivata', promemoria='disattivati')
    (data_dir / 'migrazione-011.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return dict(summary=summary, activation_codes=job.activation_codes)
