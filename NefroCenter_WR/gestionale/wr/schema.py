"""Schema del database di NefroCenter WR.

Le tabelle usano colonne tipizzate e vincoli espliciti; il JSON è riservato ai
documenti di configurazione (parametri, modelli, specifiche) che si salvano e
versionano interi. Ogni nuova versione dello schema si aggiunge a MIGRATIONS
senza modificare quelle già pubblicate.
"""

SCHEMA_V1 = r"""
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- Centri, parametri versionati e rubrica delle strutture
CREATE TABLE centers(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  code TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  config_version INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL);
CREATE TABLE center_configs(
  center_id TEXT NOT NULL REFERENCES centers(id),
  version INTEGER NOT NULL,
  data TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  PRIMARY KEY(center_id, version));
CREATE TABLE structures(
  center_id TEXT PRIMARY KEY REFERENCES centers(id),
  data TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);

-- Accessi
CREATE TABLE users(
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','hr','manager','operator','viewer')),
  active INTEGER NOT NULL DEFAULT 1,
  password TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE user_centers(
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  center_id TEXT NOT NULL REFERENCES centers(id),
  PRIMARY KEY(user_id, center_id));
CREATE TABLE user_security(
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  totp_secret TEXT NOT NULL DEFAULT '',
  totp_enabled INTEGER NOT NULL DEFAULT 0,
  totp_last_step INTEGER NOT NULL DEFAULT -1,
  recovery TEXT NOT NULL DEFAULT '[]',
  activation_hash TEXT NOT NULL DEFAULT '',
  activation_until REAL NOT NULL DEFAULT 0,
  generation INTEGER NOT NULL DEFAULT 1,
  last_login TEXT NOT NULL DEFAULT '');
CREATE TABLE sessions(
  id TEXT PRIMARY KEY,
  csrf TEXT NOT NULL,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK(stage IN ('anonymous','password','enroll','full')),
  generation INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL,
  touched REAL NOT NULL,
  expires REAL NOT NULL,
  verified REAL NOT NULL DEFAULT 0,
  pending_secret TEXT NOT NULL DEFAULT '',
  pending_until REAL NOT NULL DEFAULT 0);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE rate_limits(
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  started REAL NOT NULL,
  blocked_until REAL NOT NULL DEFAULT 0);
CREATE TABLE security_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  user_id TEXT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '');
CREATE INDEX security_events_user ON security_events(user_id, id);

-- Persone della struttura e identità di gruppo
CREATE TABLE identities(id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE people(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  identity_id TEXT NOT NULL REFERENCES identities(id),
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  registration TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '',
  contract TEXT NOT NULL DEFAULT '',
  pay_override TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(identity_id, center_id));
CREATE UNIQUE INDEX people_registration ON people(center_id, registration) WHERE registration<>'';
CREATE INDEX people_center ON people(center_id, name);

-- Registro presenze
CREATE TABLE entries(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  person_id TEXT NOT NULL REFERENCES people(id),
  day TEXT NOT NULL,
  slot TEXT NOT NULL,
  layer TEXT NOT NULL CHECK(layer IN ('actual','planned')),
  code TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('work','absence','rest')),
  label TEXT NOT NULL,
  start TEXT NOT NULL DEFAULT '',
  end TEXT NOT NULL DEFAULT '',
  pause INTEGER NOT NULL DEFAULT 0,
  overnight INTEGER NOT NULL DEFAULT 0,
  site TEXT NOT NULL DEFAULT '',
  holiday INTEGER NOT NULL DEFAULT 0,
  credit INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  review TEXT NOT NULL DEFAULT '',
  rules_version INTEGER NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  UNIQUE(person_id, day, slot, layer));
CREATE INDEX entries_center_day ON entries(center_id, day);
CREATE TABLE months(
  center_id TEXT NOT NULL REFERENCES centers(id),
  month TEXT NOT NULL,
  rules_version INTEGER NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  closed INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  PRIMARY KEY(center_id, month));
CREATE TABLE workload(
  center_id TEXT NOT NULL REFERENCES centers(id),
  day TEXT NOT NULL,
  slot TEXT NOT NULL,
  ordinary INTEGER NOT NULL,
  isolated INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  PRIMARY KEY(center_id, day, slot));
CREATE TABLE agreements(
  center_id TEXT NOT NULL REFERENCES centers(id),
  month TEXT NOT NULL,
  person_id TEXT NOT NULL REFERENCES people(id),
  data TEXT NOT NULL,
  source TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  PRIMARY KEY(center_id, month, person_id));

-- Fascicoli, onboarding e documenti
CREATE TABLE profiles(
  person_id TEXT PRIMARY KEY REFERENCES people(id),
  stage TEXT NOT NULL CHECK(stage IN ('incoming','active','ended')),
  fields TEXT NOT NULL,
  custom TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE TABLE profile_history(
  person_id TEXT NOT NULL REFERENCES people(id),
  version INTEGER NOT NULL,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY(person_id, version));
CREATE TABLE onboarding_templates(
  center_id TEXT PRIMARY KEY REFERENCES centers(id),
  tasks TEXT NOT NULL,
  fields TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE TABLE onboarding_tasks(
  person_id TEXT NOT NULL REFERENCES people(id),
  task_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  phase TEXT NOT NULL,
  label TEXT NOT NULL,
  owner TEXT NOT NULL DEFAULT '',
  due TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('todo','doing','done','na')),
  note TEXT NOT NULL DEFAULT '',
  done_at TEXT NOT NULL DEFAULT '',
  done_by TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(person_id, task_id));
CREATE TABLE documents(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  person_id TEXT NOT NULL REFERENCES people(id),
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  expiry TEXT NOT NULL DEFAULT '',
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  content BLOB NOT NULL,
  uploaded_at TEXT NOT NULL,
  uploaded_by TEXT NOT NULL);
CREATE INDEX documents_person ON documents(person_id);
CREATE INDEX documents_center ON documents(center_id, uploaded_at);
CREATE TABLE document_reviews(
  document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('received','needs_correction','verified')),
  note TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE TABLE document_review_history(
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  PRIMARY KEY(document_id, version));

-- Personale di gruppo: decorrenze contrattuali ed economiche
CREATE TABLE contracts(
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(id),
  valid_from TEXT NOT NULL,
  valid_to TEXT NOT NULL DEFAULT '',
  data TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE INDEX contracts_person ON contracts(person_id, valid_from);
CREATE TABLE economics(
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(id),
  valid_from TEXT NOT NULL,
  valid_to TEXT NOT NULL DEFAULT '',
  data TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE INDEX economics_person ON economics(person_id, valid_from);
CREATE TABLE workforce_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  record_id TEXT NOT NULL,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  before TEXT,
  after TEXT);
CREATE INDEX workforce_history_person ON workforce_history(person_id, id);

-- Approvazione mensile
CREATE TABLE approval_policies(
  center_id TEXT PRIMARY KEY REFERENCES centers(id),
  enabled INTEGER NOT NULL,
  reason TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE TABLE approvals(
  center_id TEXT NOT NULL REFERENCES centers(id),
  month TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft','submitted','manager_approved','hr_approved','returned')),
  fingerprint TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  PRIMARY KEY(center_id, month));
CREATE TABLE approval_history(
  center_id TEXT NOT NULL,
  month TEXT NOT NULL,
  version INTEGER NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  PRIMARY KEY(center_id, month, version));

-- Copertura dei turni
CREATE TABLE staffing_requirements(
  center_id TEXT PRIMARY KEY REFERENCES centers(id),
  weekly TEXT NOT NULL,
  overrides TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE TABLE availability(
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(id),
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('available','unavailable','preferred')),
  note TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL);
CREATE INDEX availability_person ON availability(person_id, start, end);
CREATE TABLE substitutions(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  person_id TEXT NOT NULL REFERENCES people(id),
  origin_center_id TEXT NOT NULL REFERENCES centers(id),
  origin_person_id TEXT NOT NULL REFERENCES people(id),
  day TEXT NOT NULL,
  slot TEXT NOT NULL,
  code TEXT NOT NULL,
  note TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected')),
  fingerprint TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  decision_note TEXT NOT NULL DEFAULT '',
  decided_at TEXT NOT NULL DEFAULT '',
  decided_by TEXT NOT NULL DEFAULT '',
  entry_id TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX substitutions_pending ON substitutions(person_id, day, slot) WHERE status='pending';

-- Uscite, trasferimenti e dotazioni
CREATE TABLE departures(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  person_id TEXT NOT NULL REFERENCES people(id),
  kind TEXT NOT NULL CHECK(kind IN ('termination','transfer')),
  destination_center_id TEXT NOT NULL DEFAULT '',
  effective_date TEXT NOT NULL,
  reason TEXT NOT NULL,
  responsible TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','in_progress','completed','cancelled')),
  tasks TEXT NOT NULL,
  closure_note TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT NOT NULL DEFAULT '',
  closed_by TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX departures_open ON departures(person_id) WHERE status IN ('open','in_progress');
CREATE TABLE equipment(
  id TEXT PRIMARY KEY,
  center_id TEXT NOT NULL REFERENCES centers(id),
  person_id TEXT NOT NULL REFERENCES people(id),
  kind TEXT NOT NULL CHECK(kind IN ('badge','keys','device','other')),
  inventory_code TEXT NOT NULL,
  asset_key TEXT NOT NULL,
  label TEXT NOT NULL,
  delivery_date TEXT NOT NULL,
  due_date TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('assigned','returned')),
  return_date TEXT NOT NULL DEFAULT '',
  return_condition TEXT NOT NULL DEFAULT '',
  return_note TEXT NOT NULL DEFAULT '',
  returned_by TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX equipment_assigned ON equipment(center_id, asset_key) WHERE status='assigned';
CREATE TABLE process_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  object_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  data TEXT NOT NULL);
CREATE INDEX process_history_object ON process_history(kind, object_id, id);

-- Paghe
CREATE TABLE payroll_templates(
  center_id TEXT NOT NULL REFERENCES centers(id),
  version INTEGER NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  PRIMARY KEY(center_id, version));

-- Comunicazioni e promemoria
CREATE TABLE mail_settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE mail_templates(id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE mail_lists(id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE mail_campaigns(
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'manual',
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL);
CREATE TABLE mail_recipients(
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES mail_campaigns(id),
  ordinal INTEGER NOT NULL,
  data TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','accepted','failed','uncertain','simulated')),
  error TEXT NOT NULL DEFAULT '',
  claimed_at REAL,
  batch_id TEXT NOT NULL DEFAULT '',
  UNIQUE(campaign_id, ordinal));
CREATE INDEX mail_recipients_campaign ON mail_recipients(campaign_id, status);
CREATE TABLE mail_attempts(
  id TEXT PRIMARY KEY,
  recipient_id TEXT NOT NULL REFERENCES mail_recipients(id),
  number INTEGER NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  started_epoch REAL NOT NULL,
  finished_at TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  message_id TEXT NOT NULL,
  UNIQUE(recipient_id, number));
CREATE INDEX mail_attempts_time ON mail_attempts(started_epoch);
CREATE TABLE reminder_settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, version INTEGER NOT NULL, enabled_by TEXT NOT NULL DEFAULT '');
CREATE TABLE reminder_events(
  event_key TEXT PRIMARY KEY,
  center_id TEXT NOT NULL,
  source_key TEXT NOT NULL,
  due TEXT NOT NULL,
  threshold INTEGER NOT NULL,
  email TEXT NOT NULL,
  topic TEXT NOT NULL,
  created_at TEXT NOT NULL,
  recipient_id TEXT NOT NULL REFERENCES mail_recipients(id));
CREATE INDEX reminder_events_recipient ON reminder_events(recipient_id);
CREATE TABLE reminder_runs(id TEXT PRIMARY KEY, at TEXT NOT NULL, state TEXT NOT NULL, messages INTEGER NOT NULL, events INTEGER NOT NULL, note TEXT NOT NULL);

-- Registro delle attività e importazioni
CREATE TABLE audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  center_id TEXT,
  action TEXT NOT NULL,
  entity TEXT NOT NULL DEFAULT '',
  entity_id TEXT NOT NULL DEFAULT '',
  before TEXT,
  after TEXT);
CREATE INDEX audit_center ON audit(center_id, id);
CREATE TABLE imports(hash TEXT PRIMARY KEY, center_id TEXT NOT NULL, month TEXT NOT NULL, at TEXT NOT NULL);
"""

MIGRATIONS = {1: SCHEMA_V1}

# Tabelle tipiche dell'archivio della versione 0.11 (Persone e Presenze Web):
# riconoscerle evita di scrivere per errore su un archivio della vecchia versione.
LEGACY_TABLES = {'periods', 'hr_profiles', 'web_security', 'patients'}
