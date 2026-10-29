// Strumenti comuni a manuale e videoguide.
// - avvia un portale di prova con dati fittizi in una cartella nuova (gestionale/strumenti/anteprima.py --aziendale);
// - attiva gli account di prova come farebbe una persona: codice di attivazione, password, app Authenticator
//   (il codice a 6 cifre è calcolato qui dalla chiave mostrata a video);
// - aspetta che le pagine del portale abbiano finito di caricare.
// Nessun dato aziendale: ogni esecuzione crea un archivio fittizio nuovo e lo cancella alla fine.
'use strict';
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const GESTIONALE = path.join(ROOT, 'gestionale');
const WEB = path.join(GESTIONALE, 'web');
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
// Password degli account fittizi del portale di prova: esiste solo per la durata dell'esecuzione.
const PASSWORD = 'Frase-di-prova-delle-guide-2026';
const ACCOUNTS = { admin: 'demo.admin', hr: 'demo.hr', manager: 'demo.manager', operator: 'demo.operator', viewer: 'demo.viewer' };

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function base32(text) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const ch of text.replace(/=+$/, '').toUpperCase()) {
    const value = alphabet.indexOf(ch);
    if (value < 0) throw new Error('Chiave dell’app Authenticator non valida');
    bits += value.toString(2).padStart(5, '0');
  }
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

function totp(secret, step) {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const mac = crypto.createHmac('sha1', base32(secret)).update(counter).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  const value = (mac.readUInt32BE(offset) & 0x7fffffff) % 1000000;
  return String(value).padStart(6, '0');
}

// Il portale rifiuta un codice già usato: si passa al successivo (è accettato anche quello dei 30 secondi dopo).
async function nextCode(account) {
  for (;;) {
    const current = Math.floor(Date.now() / 30000);
    const step = Math.max(current, account.lastStep + 1);
    if (step <= current + 1) {
      account.lastStep = step;
      return totp(account.secret, step);
    }
    await sleep(1000);
  }
}

async function launch() {
  const args = ['--lang=it-IT'];
  if (process.env.QA_CHROMIUM_NO_SANDBOX) args.push('--no-sandbox');
  return chromium.launch({ args });
}

// Portale di prova in una cartella nuova dentro `work`; restituisce indirizzo, codici di attivazione e stop().
async function startServer(work, port) {
  fs.mkdirSync(work, { recursive: true });
  const dir = fs.mkdtempSync(path.join(work, 'archivio-'));
  const child = spawn(PYTHON, ['strumenti/anteprima.py', '--aziendale', '--port', String(port), '--dir', dir],
    { cwd: GESTIONALE, stdio: ['ignore', 'pipe', 'pipe'] });
  const orphan = () => child.kill();
  process.once('exit', orphan);
  let output = '';
  child.stdout.on('data', d => { output += d; });
  child.stderr.on('data', d => { output += d; });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; ; i++) {
    if (child.exitCode !== null) throw new Error('Il portale di prova non si è avviato:\n' + output);
    if (output.includes('Anteprima con dati fittizi')) {
      try {
        const res = await fetch(base + '/');
        if (res.ok) break;
      } catch { /* non ancora pronto */ }
    }
    if (i > 120) throw new Error('Il portale di prova non risponde:\n' + output);
    await sleep(250);
  }
  const codes = JSON.parse(fs.readFileSync(path.join(dir, 'codici-attivazione.json'), 'utf-8'));
  const stop = async () => {
    process.removeListener('exit', orphan);
    child.kill();
    await new Promise(resolve => (child.exitCode !== null ? resolve() : child.once('exit', resolve)));
    fs.rmSync(dir, { recursive: true, force: true });
  };
  return { base, codes, stop, log: () => output };
}

// Attende la fine del caricamento della pagina del portale (niente segnaposto grigi) e un attimo di assestamento.
async function ready(page, extra = 300) {
  await page.waitForFunction(() => document.querySelector('#content') && !document.querySelector('#content .skeleton'),
    null, { timeout: 30000 });
  await page.waitForTimeout(extra);
}

async function open(page, base, route) {
  await page.goto(`${base}/#/${route}`);
  await page.waitForSelector('.sidebar');
  await ready(page);
}

// Primo accesso completo. `pause(name)` (facoltativa) viene chiamata nei momenti da fotografare.
async function activate(page, base, username, code, pause = async () => {}) {
  await page.goto(base + '/');
  await page.waitForSelector('input[name="username"]');
  await pause('accesso');
  await page.click('button:has-text("Usa il codice di attivazione")');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="activation"]', code);
  await pause('primo-accesso');
  await page.click('button[type="submit"]');
  await page.waitForSelector('.qr img');
  const secret = (await page.textContent('.auth-card .mono')).replace(/\s+/g, '');
  const account = { username, password: PASSWORD, secret, lastStep: -1 };
  await page.fill('input[name="password"]', PASSWORD);
  await page.fill('input[name="again"]', PASSWORD);
  await page.fill('input[name="code"]', await nextCode(account));
  await pause('attivazione-app');
  await page.click('button[type="submit"]');
  await page.waitForSelector('.codes');
  await pause('codici-recupero');
  await page.check('#saved');
  await page.click('button:has-text("Ho conservato i codici, entra")');
  await page.waitForSelector('.sidebar');
  await ready(page);
  return account;
}

async function login(page, base, account, pause = async () => {}) {
  await page.goto(base + '/');
  await page.waitForSelector('input[name="username"]');
  await page.fill('input[name="username"]', account.username);
  await page.fill('input[name="password"]', account.password);
  await page.click('button[type="submit"]');
  await page.waitForSelector('input[name="code"]');
  await page.fill('input[name="code"]', await nextCode(account));
  await pause('codice-app');
  await page.click('button[type="submit"]');
  await page.waitForSelector('.sidebar');
  await ready(page);
}

// Conferma di sicurezza (password e codice) richiesta dal portale per le operazioni sensibili.
async function confirmIdentity(page, account) {
  const dlg = page.locator('dialog[open]', { hasText: 'Conferma di sicurezza' });
  await dlg.waitFor();
  await dlg.locator('input[name="password"]').fill(account.password);
  await dlg.locator('input[name="code"]').fill(await nextCode(account));
  await dlg.locator('button', { hasText: 'Conferma' }).click();
  await dlg.waitFor({ state: 'detached' }).catch(() => {});
}

// Testi della guida del portale (gli stessi della guida in linea) e tabella dei ruoli.
async function catalog(page) {
  return page.evaluate(async () => {
    const [{ HELP }, guide, { PAGES }] = await Promise.all([import('./js/help.js'), import('./js/pages/guide.js'), import('./js/app.js')]);
    const roles = await (await fetch('api/roles', { credentials: 'same-origin' })).json();
    const me = await (await fetch('api/me', { credentials: 'same-origin' })).json();
    return { HELP, PROCEDURES: guide.PROCEDURES, FAQ: guide.FAQ, PAGES: PAGES.map(p => ({ ...p })), roles,
      product: me.product, version: me.version, today: me.today };
  });
}

function problems(page, list) {
  page.on('console', m => { if (m.type() === 'error') list.push('console: ' + m.text()); });
  page.on('pageerror', e => list.push('pagina: ' + e.message));
  page.on('response', r => {
    if (r.status() >= 400 && r.status() !== 428) list.push(`${r.status()} ${r.request().method()} ${r.url()}`);
  });
}

function args(defaults) {
  const out = { ...defaults };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i].replace(/^--/, '');
    if (!(key in defaults)) throw new Error(`Opzione sconosciuta: ${argv[i]}`);
    if (typeof defaults[key] === 'boolean') out[key] = true;
    else out[key] = argv[++i];
  }
  return out;
}

module.exports = {
  ACCOUNTS, GESTIONALE, PASSWORD, ROOT, WEB, activate, args, catalog, confirmIdentity, launch, login, nextCode, open,
  problems, ready, sleep, startServer, totp, WORK: path.join(__dirname, 'lavoro'),
};
