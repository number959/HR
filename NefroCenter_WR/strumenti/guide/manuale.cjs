// Manuale d'uso illustrato di NefroCenter WR · Work Resources.
//
// Cosa produce (in gestionale/web/help/manuale/, servito dal portale come /help/manuale/…):
//   - Manuale_NefroCenter_WR.html  pagina autonoma: CSS incorporato, schermate incorporate in base64, nessuno script;
//   - manuale.css                  lo stesso CSS in un file a parte: il portale vieta gli stili in linea (CSP),
//                                  quindi aprendo il manuale dal portale lo stile arriva da questo file;
//   - Manuale_NefroCenter_WR.pdf   A4 verticale con sfondi, numero di pagina nel piè di pagina, segnalibri, PDF taggato;
//   - indice.json                  titolo, versione, data, pagine, capitoli e immagini.
//
// Come funziona: avvia un portale di prova con soli dati fittizi (comune.startServer), attiva gli account di prova
// come farebbe una persona (codice di attivazione, password, app Authenticator), apre ogni pagina con il profilo
// più adatto e la fotografa; i testi vengono dal portale stesso (guida contestuale, procedure, FAQ, tabella dei ruoli,
// parametri della prima struttura). Alla fine spegne il portale e cancella l'archivio di prova.
//
// Uso (dalla cartella del progetto o da qualunque cartella):
//   export NODE_PATH=$(node -e "console.log(require.resolve('playwright').split('/playwright/')[0])")
//   export QA_CHROMIUM_NO_SANDBOX=1 LANG=it_IT.UTF-8        # il primo solo nei contenitori senza sandbox
//   node strumenti/guide/manuale.cjs [--port 8101] [--out CARTELLA] [--scratch CARTELLA] [--keep]
//     --port     porta del portale di prova (predefinita 8101)
//     --out      cartella di destinazione (predefinita gestionale/web/help/manuale)
//     --scratch  cartella per le schermate di lavoro (predefinita strumenti/guide/lavoro/manuale-schermate)
//     --keep     non cancellare le schermate di lavoro alla fine
//
// Requisiti: Node.js 20+, Playwright 1.63 con Chromium già installato, Python 3 con le dipendenze del gestionale
// (waitress; xlsxwriter per il file Excel di prova dell'importazione). Facoltativi, da poppler-utils: pdfinfo (conteggio
// delle pagine), pdftohtml (numeri di pagina nell'indice, letti dai segnalibri del PDF; in alternativa Python con pypdf),
// pdftotext e pdfimages (controllo delle pagine quasi vuote). Senza di essi il manuale viene comunque prodotto.
// Le pagine più alte di SLICE_MAX px vengono fotografate in più parti, tagliate fra un blocco e l'altro, così nel PDF
// restano leggibili a tutta larghezza. Le figure sono numerate nell'ordine in cui compaiono nel documento.
// Non tocca mai file aziendali: il file Excel importato è generato al momento con dati inventati.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const comune = require('./comune.cjs');

const OPTS = comune.args({ port: '8101', out: '', scratch: '', keep: false });
const PORT = Number(OPTS.port);
const OUT = path.resolve(OPTS.out || path.join(comune.WEB, 'help', 'manuale'));
const SCRATCH = path.resolve(OPTS.scratch || path.join(comune.WORK, 'manuale-schermate'));
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const HTML_NAME = 'Manuale_NefroCenter_WR.html';
const PDF_NAME = 'Manuale_NefroCenter_WR.pdf';
const CSS_NAME = 'manuale.css';
const VIEWPORT = { width: 1366, height: 860 };
const PHONE = { width: 390, height: 844 };
const MAX_HEIGHT = 2200;          // le pagine lunghe si tagliano a questa altezza
const SLICE_MAX = 1200;           // oltre questa altezza la schermata si divide in parti (a 178 mm di larghezza: ≤ 156 mm)
const JPEG_AFTER = 320 * 1024;    // oltre questa dimensione la schermata viene rifatta in JPEG (qualità 85)
const MAX_HTML = 16 * 1024 * 1024;

// Profilo con cui si fotografa ogni pagina.
const PROFILE_OF = {
  home: 'admin', todo: 'admin',
  attendance: 'manager', month: 'manager', approvals: 'manager', coverage: 'manager',
  people: 'hr', documents: 'hr', workforce: 'hr', departures: 'hr', structures: 'hr',
  agreements: 'hr', collaborators: 'hr', payroll: 'hr', mail: 'hr', reminders: 'hr',
  stats: 'viewer', exports: 'viewer',
  settings: 'admin', centers: 'admin', users: 'admin', backups: 'admin', import: 'admin',
  guide: 'admin', roles: 'admin', security: 'admin',
};
// Schermate aggiuntive mostrate nella scheda di una pagina (dopo la schermata principale).
const EXTRAS = {
  attendance: ['presenze-registrazione', 'presenze-pianificato'],
  people: ['persone-fascicolo', 'persone-fascicolo-documenti', 'persone-fascicolo-inserimento'],
  mail: ['comunicazioni-anteprima'],
  stats: ['statistiche-grafico'],
  settings: ['parametri-fasce', 'parametri-causali'],
  users: ['accessi-nuovo-account', 'accessi-codice'],
  import: ['importa-anteprima'],
};
// Procedure in cui il permesso indicato in guide.js (quello che le fa comparire nella guida) è più ampio di chi può
// davvero eseguirle: qui i permessi delle azioni vere, nell'ordine dei passi.
const PROCEDURE_CAPS = {
  'Approvare un mese': ['approvazioni.verifica', 'approvazioni.approva'],
  'Compensi dei collaboratori a prestazione': ['accordi.vedi', 'accordi.modifica', 'paghe.gestisci'],
};
const KIND_LABEL = { work: 'Turno di lavoro', absence: 'Assenza', rest: 'Riposo' };
const GROUPS = ['Panoramica', 'Presenze', 'Persone', 'Amministrazione', 'Analisi', 'Sistema', 'Aiuto'];

const problems = [];
const shots = [];
const shotIndex = {};
let figureCounter = 0;  // numerazione delle figure nell'ordine del documento, azzerata a ogni composizione

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/«([^»]+)»/g, '«$1»');
const itDate = d => `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
const fmtBytes = n => n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;

// ---------- Schermate ----------
function imageSize(buf, type) {
  if (type === 'png') return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) { i += 1; continue; }
    const marker = buf[i + 1];
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      return { height: buf.readUInt16BE(i + 5), width: buf.readUInt16BE(i + 7) };
    }
    i += 2 + buf.readUInt16BE(i + 2);
  }
  return { width: 0, height: 0 };
}

// Attende la fine dei caricamenti e la scomparsa delle notifiche a comparsa, poi un attimo di assestamento.
async function settle(page, extra = 400) {
  await page.waitForFunction(() => !document.querySelector('#content .skeleton') && !document.querySelector('.loading'),
    null, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => !document.querySelector('#toasts .toast'), null, { timeout: 12000 }).catch(() => {});
  await page.waitForTimeout(extra);
}

// Bordi superiori dei blocchi del contenuto (schede, righe, voci, paragrafi): sono i punti in cui una pagina lunga
// si può tagliare senza spezzare una riga o una casella.
async function cutCandidates(page) {
  return page.evaluate(() => {
    const sel = '#content .card, #content .card > *, #content .card-body > *, #content .kpis, #content tr, #content li, '
      + '#content p, #content h2, #content h3, #content .tabs, #content .segmented';
    const ys = new Set();
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.width > 0) ys.add(Math.round(r.top + window.scrollY));
    }
    return [...ys].sort((a, b) => a - b);
  });
}

// Divide l'altezza in parti bilanciate di al massimo SLICE_MAX px; ogni taglio cade, se possibile, dove inizia un blocco.
function sliceBounds(height, candidates) {
  const n = Math.ceil(height / SLICE_MAX);
  const part = height / n;
  const bounds = [0];
  for (let i = 1; i < n; i++) {
    const target = Math.round(part * i);
    const previous = bounds[bounds.length - 1];
    const near = candidates.filter(y => y >= target - part * 0.25 && y <= target + part * 0.15 && y > previous + 300);
    bounds.push(near.length ? near.reduce((best, y) => (Math.abs(y - target) < Math.abs(best - target) ? y : best)) : target);
  }
  bounds.push(height);
  return bounds;
}

// Fotografa la pagina (o un elemento, o la sola finestra). Le pagine a tutta altezza più alte di SLICE_MAX vengono
// divise in parti: la prima ha l'id richiesto, le altre `id-parteN`; shotIndex[id].slices le elenca tutte.
async function shot(page, id, caption, opts = {}) {
  if (shotIndex[id]) throw new Error(`Schermata duplicata: ${id}`);
  await settle(page, opts.extra);
  const vp = page.viewportSize();
  let bounds = null;
  if (!opts.locator && opts.full !== false) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(150);
    const height = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
    bounds = sliceBounds(Math.min(height, MAX_HEIGHT), await cutCandidates(page));
  }
  const take = async (type, clip) => {
    const base = type === 'jpeg' ? { type, quality: 85 } : { type };
    if (opts.locator) return opts.locator.screenshot(base);
    if (!clip) return page.screenshot(base);
    return page.screenshot({ ...base, fullPage: true, clip });
  };
  const parts = bounds ? bounds.length - 1 : 1;
  const slices = [];
  for (let i = 0; i < parts; i++) {
    const clip = bounds ? { x: 0, y: bounds[i], width: vp.width, height: bounds[i + 1] - bounds[i] } : null;
    let type = 'png';
    let buffer = await take('png', clip);
    if (buffer.length > JPEG_AFTER) {
      type = 'jpeg';
      buffer = await take('jpeg', clip);
    }
    const partId = i === 0 ? id : `${id}-parte${i + 1}`;
    const partCaption = parts === 1 ? caption
      : i === 0 ? `${caption} Parte 1 di ${parts}.` : `${caption} Parte ${i + 1} di ${parts}: seguito della pagina, scorrendo verso il basso.`;
    const file = path.join(SCRATCH, `${String(shots.length + 1).padStart(2, '0')}-${partId}.${type === 'png' ? 'png' : 'jpg'}`);
    fs.writeFileSync(file, buffer);
    const entry = { id: partId, caption: partCaption, file, type, bytes: buffer.length, phone: Boolean(opts.phone), part: i + 1, parts,
      ...imageSize(buffer, type), data: buffer.toString('base64') };
    shots.push(entry);
    shotIndex[partId] = entry;
    slices.push(entry);
    process.stdout.write(`  schermata ${partId} (${entry.width}×${entry.height}, ${fmtBytes(entry.bytes)}, ${type})\n`);
  }
  shotIndex[id].slices = slices;
  return shotIndex[id];
}

async function openPage(page, base, p) {
  await page.goto(`${base}/#/${p.path}`);
  await page.waitForSelector('.sidebar');
  await page.waitForFunction(label => document.querySelector('.topbar .page-title')?.textContent === label, p.label, { timeout: 20000 });
  await comune.ready(page);
  await settle(page);
}

// Sceglie la struttura nella barra superiore (solo nelle pagine che la mostrano).
async function chooseCenter(page, name) {
  const select = page.locator('.context-center');
  if (!(await select.isVisible())) return;
  const current = await select.evaluate(el => el.selectedOptions[0]?.textContent || '');
  if (current === name) return;
  await select.selectOption({ label: name });
  await comune.ready(page);
  await settle(page);
}

async function newSession(browser, extra = {}) {
  const { init, ...options } = extra;
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1, locale: 'it-IT', colorScheme: 'light', ...options });
  if (init) await context.addInitScript(init.fn, init.arg);
  const page = await context.newPage();
  comune.problems(page, problems);
  return { context, page };
}

function fetchJson(page, url) {
  return page.evaluate(async u => (await fetch(u, { credentials: 'same-origin' })).json(), url);
}

// ---------- Raccolta: pagine e schermate ----------
async function capturePages(page, base, role, ids, byId, roleLabel, hooks, centerName) {
  for (const id of ids) {
    const p = byId[id];
    await openPage(page, base, p);
    if (p.context?.includes('center')) await chooseCenter(page, centerName);
    await shot(page, `pag-${id}`, `«${p.label}»: la pagina con il profilo ${roleLabel[role]}.`);
    if (hooks[id]) await hooks[id](page, base);
  }
}

async function run() {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(SCRATCH, { recursive: true });
  const started = new Date();
  console.log(`Portale di prova sulla porta ${PORT}…`);
  const server = await comune.startServer(comune.WORK, PORT);
  const browser = await comune.launch();
  const accounts = {};
  let catalog, me, centers, firstCenter, config, demoTable;
  try {
    const base = server.base;
    // ----- Amministratore: primo accesso fotografato, cataloghi, pagine di sistema -----
    console.log('Profilo Amministratore');
    let { context, page } = await newSession(browser);
    const authCaptions = {
      accesso: 'La pagina di accesso: nome utente e password. Il collegamento «Usa il codice di attivazione» serve al primo accesso o dopo un cambio di telefono.',
      'primo-accesso': 'Primo accesso: nome utente e codice di attivazione ricevuto di persona dall’amministratore.',
      'attivazione-app': 'Configurazione del secondo fattore: codice QR per l’app Authenticator, chiave manuale, nuova password personale e codice a 6 cifre.',
      'codici-recupero': 'I codici di recupero: compaiono una sola volta. Vanno scaricati o stampati e conservati lontano dal telefono.',
      'codice-app': 'Accesso normale: dopo la password il portale chiede il codice a 6 cifre dell’app Authenticator (o un codice di recupero).',
    };
    accounts.admin = await comune.activate(page, base, comune.ACCOUNTS.admin, server.codes[comune.ACCOUNTS.admin],
      async name => { await shot(page, name, authCaptions[name]); });
    const adminVerifiedAt = Date.now();  // la conferma di sicurezza viene richiesta solo dopo 5 minuti dall'ultima verifica
    catalog = await comune.catalog(page);
    me = await fetchJson(page, 'api/me');
    centers = (await fetchJson(page, 'api/centers')).centers.filter(c => c.active);
    firstCenter = centers[0];
    config = (await fetchJson(page, `api/centers/${firstCenter.id}/config`)).config;
    const CAP = centers.find(c => c.code === 'DEMO-CAP') || firstCenter;
    const byId = Object.fromEntries(catalog.PAGES.map(p => [p.id, p]));
    const roleLabel = Object.fromEntries(catalog.roles.roles.map(r => [r.id, r.label]));
    const pagesOf = role => catalog.PAGES.filter(p => PROFILE_OF[p.id] === role).map(p => p.id);
    const initCenter = { fn: id => { try { localStorage.setItem('wr.cid', id); } catch { /* niente */ } }, arg: CAP.id };

    // Il file Excel di prova per l'importazione (dati inventati, generato dai test del gestionale).
    const xlsx = path.join(SCRATCH, 'prova.xlsx');
    execFileSync(PYTHON, ['-c', "import sys; sys.path[:0]=['tests','.']; from test_import import real_like_workbook; "
      + `open(sys.argv[1],'wb').write(real_like_workbook(center='Struttura di prova'))`, xlsx], { cwd: comune.GESTIONALE, stdio: 'inherit' });

    const adminHooks = {
      home: async () => {
        await page.click('button[aria-label="Guida della pagina"]');
        await page.waitForSelector('.help-panel.open');
        await page.waitForTimeout(450);
        await shot(page, 'guida-contestuale', 'La guida contestuale: il pulsante «?» in alto a destra apre il pannello con cosa si fa nella pagina, i passi e le note per il tuo profilo.', { full: false });
        await page.click('button[aria-label="Chiudi la guida"]');
        await page.waitForTimeout(350);
        await page.click('button[aria-label="Cambia tema"]');
        await page.waitForTimeout(350);
        await shot(page, 'tema-scuro', 'Il tema scuro: si attiva con il pulsante con la luna (o il sole) in alto a destra; la scelta viene ricordata dal browser.', { full: false });
        await page.click('button[aria-label="Cambia tema"]');
        await page.waitForTimeout(250);
      },
      settings: async () => {
        await page.click('.tabs .tab:has-text("Fasce orarie")');
        await settle(page);
        await shot(page, 'parametri-fasce', 'Parametri struttura, linguetta «Fasce orarie»: le righe del registro con codice, descrizione, orari, pausa e colore.');
        await page.click('.tabs .tab:has-text("Causali")');
        await settle(page);
        await shot(page, 'parametri-causali', 'Parametri struttura, linguetta «Causali»: turni, assenze e riposi selezionabili nel registro, con le fasce autorizzate.');
      },
      import: async () => {
        await page.setInputFiles('input[type="file"]', xlsx);
        await page.click('button:has-text("Analizza il file")');
        await page.locator('.card-head h2', { hasText: 'Anteprima' }).waitFor({ timeout: 90000 });
        await settle(page, 600);
        await shot(page, 'importa-anteprima', 'Anteprima dell’importazione di un file Excel di prova: numeri, avvisi, celle non importate, persone riconosciute e scelta della destinazione. Nulla è stato ancora scritto.');
      },
    };
    await capturePages(page, base, 'admin', pagesOf('admin'), byId, roleLabel, adminHooks, CAP.name);
    const admin = { context, page };  // resta aperta: il flusso «Nuovo account» si fotografa alla fine (vedi sotto)

    // ----- Responsabile di struttura: presenze -----
    console.log('Profilo Responsabile di struttura');
    ({ context, page } = await newSession(browser, { init: initCenter }));
    accounts.manager = await comune.activate(page, base, comune.ACCOUNTS.manager, server.codes[comune.ACCOUNTS.manager]);
    const managerHooks = {
      attendance: async () => {
        await page.locator('table.register .cell:has(.code:not(.planned))').first().click();
        const dlg = page.locator('dialog[open]');
        await dlg.waitFor();
        await page.waitForTimeout(300);
        await shot(page, 'presenze-registrazione', 'Il dialogo di registrazione: si apre con un clic su una casella del registro. Causale, orari proposti dalla fascia, sede di lavoro, festivo e nota.', { full: false });
        await page.keyboard.press('Escape');
        await dlg.waitFor({ state: 'detached' }).catch(() => {});
        await page.click('.segmented button:has-text("Pianificato")');
        await settle(page);
        await shot(page, 'presenze-pianificato', 'Il registro in vista «Pianificato»: i turni previsti restano tratteggiati finché non si registra il consuntivo.');
        await page.click('.segmented button:has-text("Consuntivo")');
        await settle(page);
      },
    };
    await capturePages(page, base, 'manager', pagesOf('manager'), byId, roleLabel, managerHooks, CAP.name);
    await context.close();

    // ----- HR centrale: persone e amministrazione -----
    console.log('Profilo HR centrale');
    ({ context, page } = await newSession(browser, { init: initCenter }));
    accounts.hr = await comune.activate(page, base, comune.ACCOUNTS.hr, server.codes[comune.ACCOUNTS.hr]);
    const hrHooks = {
      people: async () => {
        await page.locator('.table tbody tr.clickable', { hasText: 'Marco Bianchi' }).first().click();
        await page.waitForSelector('.tabs');
        await comune.ready(page);
        await settle(page);
        await shot(page, 'persone-fascicolo', 'La scheda di un fascicolo: le linguette raccolgono anagrafica, recapiti, contratto, amministrazione, qualifiche, inserimento, documenti, scadenze e storico.');
        await page.click('.tabs .tab:has-text("Documenti")');
        await settle(page);
        await shot(page, 'persone-fascicolo-documenti', 'Linguetta «Documenti» del fascicolo: allegati con categoria, scadenza e stato della verifica di HR centrale.');
        await page.click('.tabs .tab:has-text("Inserimento")');
        await settle(page);
        await shot(page, 'persone-fascicolo-inserimento', 'Linguetta «Inserimento»: le attività previste dal modello della struttura, con scadenze, referenti e stato.');
      },
      mail: async () => {
        await page.click('button[type="submit"]:has-text("Anteprima dei messaggi")');
        await page.waitForSelector('.mail-preview', { timeout: 30000 });
        await settle(page, 600);
        await shot(page, 'comunicazioni-anteprima', 'Anteprima di una comunicazione: destinatari validi ed esclusi, avvisi e i primi messaggi personalizzati. La bozza si crea solo dopo il controllo.',
          { locator: page.locator('.card', { has: page.locator('.mail-preview') }).first() });
      },
    };
    await capturePages(page, base, 'hr', pagesOf('hr'), byId, roleLabel, hrHooks, CAP.name);
    await context.close();

    // ----- Direzione · consultazione: analisi -----
    console.log('Profilo Direzione · consultazione');
    ({ context, page } = await newSession(browser, { init: initCenter }));
    accounts.viewer = await comune.activate(page, base, comune.ACCOUNTS.viewer, server.codes[comune.ACCOUNTS.viewer]);
    const viewerHooks = {
      stats: async () => {
        await page.waitForSelector('.chart');
        await shot(page, 'statistiche-grafico', 'Il grafico dei turni effettivi per mese nella pagina Statistiche: passando sulle colonne si legge il valore di ogni mese.',
          { locator: page.locator('.card', { has: page.locator('.chart') }).first() });
      },
    };
    await capturePages(page, base, 'viewer', pagesOf('viewer'), byId, roleLabel, viewerHooks, CAP.name);
    await context.close();

    // ----- Accesso normale (codice dell'app) -----
    console.log('Accesso normale');
    ({ context, page } = await newSession(browser));
    await comune.login(page, base, accounts.admin, async name => { await shot(page, name, authCaptions[name]); });
    await context.close();

    // ----- Telefono -----
    console.log('Telefono');
    ({ context, page } = await newSession(browser, { viewport: PHONE, deviceScaleFactor: 2, isMobile: true, hasTouch: true, init: initCenter }));
    await comune.login(page, base, accounts.manager);
    await settle(page);
    await shot(page, 'telefono-riepilogo', 'Il riepilogo sul telefono: i numeri del mese e le attività da completare in una sola colonna.', { full: false, phone: true });
    await page.goto(`${base}/#/presenze`);
    await page.waitForSelector('.day-list', { timeout: 30000 });
    await settle(page);
    await shot(page, 'telefono-giorno', 'Il registro sul telefono in vista «Giorno»: le persone del giorno scelto con un pulsante per ogni fascia.', { full: false, phone: true });
    await page.click('button[aria-label="Apri il menu"]');
    await page.waitForTimeout(450);
    await shot(page, 'telefono-menu', 'Il menu sul telefono: si apre con il pulsante ☰ in alto a sinistra e mostra le stesse aree del computer.', { full: false, phone: true });
    await context.close();

    // ----- Amministratore: nuovo account con conferma di sicurezza (richiesta solo dopo 5 minuti dalla verifica) -----
    const wait = adminVerifiedAt + 305000 - Date.now();
    if (wait > 0) {
      console.log(`Attesa di ${Math.ceil(wait / 1000)} s perché il portale richieda la conferma di sicurezza…`);
      await comune.sleep(wait);
    }
    console.log('Profilo Amministratore: nuovo account');
    ({ context, page } = admin);
    await openPage(page, base, byId.users);
    await page.click('button:has-text("Nuovo account")');
    const dlg = page.locator('dialog[open]', { hasText: 'Nuovo account' });
    await dlg.waitFor();
    await dlg.locator('input[name="name"]').fill('Maria Esempio');
    await dlg.locator('input[name="username"]').fill('maria.esempio');
    await dlg.locator('select[name="role"]').selectOption('operator');
    await dlg.locator('fieldset label.check', { hasText: CAP.name }).locator('input').check();
    await page.waitForTimeout(300);
    await shot(page, 'accessi-nuovo-account', 'Il dialogo «Nuovo account»: nome, nome utente, ruolo e strutture assegnate (account fittizio di esempio).', { full: false });
    await dlg.locator('.dialog-foot .btn.primary').click();
    const stepUp = page.locator('dialog[open]', { hasText: 'Conferma di sicurezza' });
    await stepUp.waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);
    await shot(page, 'conferma-sicurezza', 'La «Conferma di sicurezza»: prima di un’operazione sensibile il portale chiede di nuovo password e codice dell’app. La conferma vale 5 minuti.', { full: false });
    await comune.confirmIdentity(page, accounts.admin);
    const codeDlg = page.locator('dialog[open]', { has: page.locator('.codes') });
    await codeDlg.waitFor({ timeout: 20000 });
    await page.waitForTimeout(300);
    await shot(page, 'accessi-codice', 'Il codice di attivazione appena generato: si comunica di persona o per telefono, vale 7 giorni e una sola volta (account fittizio).', { full: false });
    await codeDlg.locator('.dialog-foot .btn.primary').click();
    await settle(page);
    await context.close();

    // ----- Tabella demo/aziendale dal LEGGIMI della demo -----
    demoTable = readDemoTable(path.join(comune.ROOT, 'demo', 'LEGGIMI.md'));

    // ----- Composizione e PDF -----
    // Due passaggi: il primo PDF serve a leggere, dai segnalibri, la pagina di ogni titolo; il secondo scrive quei numeri
    // nell'indice. L'indice occupa le stesse righe in entrambi (i numeri hanno larghezza fissa), quindi la paginazione non
    // cambia; per sicurezza si confrontano i segnalibri del nuovo PDF con i numeri usati (al massimo tre passaggi).
    console.log('Composizione del manuale');
    const data = { catalog, me, centers, firstCenter, config, demoTable, roleLabel, byId, started };
    const htmlPath = path.join(OUT, HTML_NAME);
    const pdfPath = path.join(OUT, PDF_NAME);
    let built = buildHtml(data, null);
    let tocStable = false;
    for (let pass = 1; ; pass++) {
      fs.writeFileSync(htmlPath, built.html);
      fs.writeFileSync(path.join(OUT, CSS_NAME), built.css);
      console.log(`PDF (passaggio ${pass})`);
      await renderPdf(browser, htmlPath, pdfPath);
      const found = readOutline(pdfPath);
      if (!found) {
        console.log('  segnalibri non leggibili (servono pdftohtml o pypdf): indice senza numeri di pagina');
        break;
      }
      tocStable = Boolean(built.pageOf) && built.tocEntries.every(e => built.pageOf.get(e.key) === found.get(e.key));
      if (tocStable || pass >= 3) {
        if (!tocStable) console.log('  attenzione: i numeri di pagina dell’indice non si sono stabilizzati in tre passaggi');
        break;
      }
      built = buildHtml(data, found);
    }
    const { html, css, chapters, tocEntries, pageOf } = built;

    // ----- Controlli -----
    const pdfBytes = fs.readFileSync(pdfPath);
    const pdfPages = countPdfPages(pdfPath, pdfBytes);
    const htmlBytes = Buffer.byteLength(html);
    const stripped = html.replace(/data:image\/[a-z]+;base64,[A-Za-z0-9+/=]+/g, 'data:…');
    const forbidden = [...stripped.matchAll(/\b(undefined|null)\b|\[object/g)].map(m => m[0]);
    const expected = problems.filter(x => /428 \(Precondition Required\)/.test(x));  // conferma di sicurezza richiesta: previsto
    const real = problems.filter(x => !expected.includes(x));
    const missingShots = catalog.PAGES.filter(p => !shotIndex[`pag-${p.id}`]).map(p => p.id);
    const missingText = catalog.PAGES.filter(p => !catalog.HELP[p.id]?.intro).map(p => p.id);
    const sizeOk = htmlBytes < MAX_HTML;
    // Figure numerate 1, 2, 3… nell'ordine del documento; indice con una pagina per ogni voce, in ordine crescente.
    const figureNumbers = [...stripped.matchAll(/<strong>Figura (\d+)<\/strong>/g)].map(m => Number(m[1]));
    const figuresInOrder = figureNumbers.length > 0 && figureNumbers.every((n, i) => n === i + 1);  // ogni figura numerata una sola volta, nell'ordine del documento
    const tocPages = tocEntries.map(e => pageOf?.get(e.key));
    const tocComplete = tocStable && tocPages.every((n, i) => Number.isInteger(n) && (i === 0 || n >= tocPages[i - 1]));
    const nearEmpty = nearEmptyPages(pdfPath);
    const ok = !forbidden.length && !missingShots.length && !missingText.length && !real.length && pdfPages >= 40 && sizeOk
      && figuresInOrder && tocComplete && (nearEmpty === null || !nearEmpty.length);
    const summary = {
      ok,
      html: { path: htmlPath, bytes: htmlBytes, under16MB: sizeOk },
      css: { path: path.join(OUT, CSS_NAME), bytes: Buffer.byteLength(css) },
      pdf: { path: pdfPath, bytes: pdfBytes.length, pages: pdfPages, atLeast40: pdfPages >= 40 },
      images: shots.length, jpeg: shots.filter(s => s.type === 'jpeg').length, sliced: shots.filter(s => s.parts > 1 && s.part === 1).length,
      figuresInOrder, tocEntries: tocEntries.length, tocComplete, nearEmptyPages: nearEmpty,
      pagesCovered: `${catalog.PAGES.length - missingShots.length}/${catalog.PAGES.length}`, missingShots, missingText,
      forbiddenStrings: forbidden, problems: real, expectedStepUp: expected.length, chapters: chapters.length, version: catalog.version,
    };
    fs.writeFileSync(path.join(OUT, 'indice.json'), JSON.stringify({
      titolo: 'Manuale d’uso', prodotto: `${me.product} · ${me.subtitle}`, versione: catalog.version,
      data: started.toISOString().slice(0, 10), generato: started.toISOString(), data_dati_fittizi: catalog.today,
      pagine: pdfPages, pagine_pdf: pdfPages,
      file: { html: { nome: HTML_NAME, byte: htmlBytes }, css: { nome: CSS_NAME, byte: Buffer.byteLength(css) }, pdf: { nome: PDF_NAME, byte: pdfBytes.length } },
      capitoli: chapters.map(c => ({ numero: c.number, id: c.id, titolo: c.title, pagina_pdf: pageOf?.get(c.key) ?? null, pagine: c.pages || [],
        sezioni: c.sections.map(x => ({ titolo: x.text, id: x.anchor, pagina_pdf: pageOf?.get(x.key) ?? null })) })),
      immagini: shots.map(s => ({ id: s.id, figura: s.figure || null, didascalia: s.caption, formato: s.type, larghezza: s.width, altezza: s.height, byte: s.bytes,
        parte: s.parts > 1 ? s.part : null, parti: s.parts > 1 ? s.parts : null })),
      controlli: { tutte_le_pagine: !missingShots.length && !missingText.length, stringhe_vietate: forbidden.length, problemi: real.length,
        pagine_pdf_minime: pdfPages >= 40, html_sotto_16MB: sizeOk, figure_in_ordine: figuresInOrder, indice_con_pagine: tocComplete,
        pagine_quasi_vuote: nearEmpty === null ? null : nearEmpty.map(p => p.pagina) },
    }, null, 1));
    console.log(JSON.stringify(summary, null, 1));
    if (!ok) process.exitCode = 1;
  } finally {
    await browser.close().catch(() => {});
    await server.stop();
    if (!OPTS.keep) fs.rmSync(SCRATCH, { recursive: true, force: true });
  }
}

function countPdfPages(pdfPath, bytes) {
  try {
    const out = execFileSync('pdfinfo', [pdfPath], { encoding: 'utf-8' });
    const m = /Pages:\s+(\d+)/.exec(out);
    if (m) return Number(m[1]);
  } catch { /* pdfinfo assente: si conta nel file */ }
  return (bytes.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
}

// Stampa il PDF della pagina HTML: A4 verticale, sfondi, segnalibri dai titoli, PDF taggato, numero di pagina nel piè di pagina.
async function renderPdf(browser, htmlPath, pdfPath) {
  const { context, page } = await newSession(browser);
  try {
    await page.goto('file://' + htmlPath, { waitUntil: 'load', timeout: 120000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    await page.pdf({
      path: pdfPath, format: 'A4', printBackground: true, preferCSSPageSize: true, outline: true, tagged: true,
      displayHeaderFooter: true, headerTemplate: '<span></span>',
      footerTemplate: '<div style="width:100%;font-size:8.5px;color:#6f7c95;text-align:center;font-family:Inter,system-ui,sans-serif;">'
        + 'NefroCenter WR · Manuale d’uso · pagina <span class="pageNumber"></span> di <span class="totalPages"></span></div>',
      margin: { top: '16mm', right: '16mm', bottom: '16mm', left: '16mm' },
    });
  } finally {
    await context.close();
  }
}

const norm = s => String(s).normalize('NFC').replace(/\s+/g, ' ').trim();
const unentity = s => s.replace(/&(amp|lt|gt|quot|apos|#39|#x27);/g,
  m => ({ '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'", '&#39;': "'", '&#x27;': "'" }[m]));

// Segnalibri del PDF (testo del titolo → numero di pagina): Chromium li genera dai titoli h1-h3.
// Con pdftohtml (poppler-utils) oppure, in alternativa, con Python e pypdf; null se nessuno dei due è disponibile.
function readOutline(pdfPath) {
  const found = new Map();
  const add = (title, page) => { const key = norm(title); if (!found.has(key)) found.set(key, page); };
  const quiet = { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 16 * 1024 * 1024 };
  try {
    const xml = execFileSync('pdftohtml', ['-xml', '-i', '-f', '1', '-l', '1', '-stdout', pdfPath], quiet);
    for (const m of xml.matchAll(/<item page="(\d+)">([^<]*)<\/item>/g)) add(unentity(m[2]), Number(m[1]));
  } catch { /* pdftohtml assente */ }
  if (!found.size) {
    const script = ['import sys', 'from pypdf import PdfReader', 'r = PdfReader(sys.argv[1])', 'def walk(items):',
      '    for it in items:', '        if isinstance(it, list): walk(it)',
      '        else: print(r.get_destination_page_number(it) + 1, it.title.replace("\\n", " "), sep="\\t")', 'walk(r.outline)'].join('\n');
    try {
      for (const line of execFileSync(PYTHON, ['-I', '-c', script, pdfPath], quiet).split('\n')) {
        const m = /^(\d+)\t(.*)$/.exec(line);
        if (m) add(m[2], Number(m[1]));
      }
    } catch { /* pypdf assente */ }
  }
  return found.size ? found : null;
}

// Pagine del PDF senza immagini e con poco testo oltre il piè di pagina: sono quelle che sembrano incompiute.
// Richiede pdftotext e pdfimages (poppler-utils); null se non verificabile.
function nearEmptyPages(pdfPath) {
  const quiet = { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 };
  try {
    const pages = execFileSync('pdftotext', ['-layout', pdfPath, '-'], quiet).split('\f');
    const list = execFileSync('pdfimages', ['-list', pdfPath], quiet);
    const withImages = new Set([...list.matchAll(/^\s*(\d+)\s+\d+\s+image/gm)].map(m => Number(m[1])));
    const out = [];
    pages.forEach((t, i) => {
      const chars = t.replace(/NefroCenter WR · Manuale d.uso · pagina \d+ di \d+/, '').replace(/\s+/g, ' ').trim().length;
      if (chars > 0 && chars < 600 && !withImages.has(i + 1)) out.push({ pagina: i + 1, caratteri: chars });
    });
    return out;
  } catch { return null; }
}

function readDemoTable(file) {
  const lines = fs.readFileSync(file, 'utf-8').split('\n').filter(l => l.trim().startsWith('|'));
  const rows = lines.map(l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
  const [head, , ...body] = rows;
  return { head, body: body.filter(r => r.length === head.length) };
}

// ---------- Composizione HTML ----------
function figure(id, alt) {
  const s = shotIndex[id];
  if (!s) throw new Error(`Manca la schermata ${id}`);
  figureCounter += 1;
  s.figure = figureCounter;
  return `<figure class="fig${s.phone ? ' phone' : ''}" id="fig-${figureCounter}">`
    + `<img src="data:image/${s.type};base64,${s.data}" alt="${esc(alt || s.caption)}" width="${s.width}" height="${s.height}">`
    + `<figcaption><strong>Figura ${figureCounter}</strong> · ${esc(s.caption)}</figcaption></figure>`;
}

function list(tag, items, cls = '') {
  return `<${tag}${cls ? ` class="${cls}"` : ''}>${items.map(i => `<li>${esc(i)}</li>`).join('')}</${tag}>`;
}

function buildHtml(data, pageOf = null) {
  figureCounter = 0;
  for (const s of Object.values(shotIndex)) s.figure = null;
  const { catalog, me, centers, firstCenter, config, demoTable, roleLabel, byId, started } = data;
  const { HELP, PROCEDURES, FAQ, PAGES, roles } = catalog;
  const capOf = Object.fromEntries(roles.capabilities.map(c => [c.id, c]));
  const chapters = [];
  const chapter = (id, title, pages) => {
    const number = chapters.length + 1;
    chapters.push({ number, id, title, pages, key: norm(`${number} ${title}`), sections: [] });
    return chapters[chapters.length - 1];
  };
  const emblem = fs.readFileSync(path.join(comune.WEB, 'img', 'emblema.png')).toString('base64');
  const generated = itDate(started);
  const fictitiousMonth = catalog.today.slice(0, 7);
  const monthName = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'][Number(fictitiousMonth.slice(5)) - 1];
  // Il permesso che fa comparire una procedura nella guida può essere di sola consultazione: per queste procedure
  // «chi può farlo» si ricava dai permessi che servono davvero a eseguirla.
  const WHO_OVERRIDES = { 'Approvare un mese': ['approvazioni.verifica', 'approvazioni.approva'], 'Chiudere il mese': ['mese.verifica', 'mese.chiudi'],
    'Compensi dei collaboratori a prestazione': ['accordi.modifica', 'paghe.gestisci'] };
  const whoCan = (cap, title) => {
    const caps = WHO_OVERRIDES[title] || (cap ? [cap] : []);
    if (!caps.length) return 'Tutti i profili.';
    const rows = caps.map(c => capOf[c]).filter(Boolean);
    if (!rows.length) return caps.join(', ');
    const allowed = roles.roles.map(r => r.id).filter(id => rows.some(row => row.roles.includes(id)));
    const cond = roles.roles.map(r => r.id).filter(id => !allowed.includes(id) && rows.some(row => row.conditional.includes(id)));
    return `${[...allowed.map(r => roleLabel[r]), ...cond.map(r => `${roleLabel[r]} (se abilitato nei parametri della struttura)`)].join(', ')}`
      + ` — ${rows.length === 1 ? 'permesso' : 'permessi'} «${rows.map(row => row.description).join('», «')}».`;
  };

  const sections = [];

  // 1. Come è fatto il portale
  let c = chapter('portale', 'Come è fatto il portale');
  const menu = GROUPS.map(g => `<li><strong>${esc(g)}</strong>: ${PAGES.filter(p => p.group === g).map(p => esc(p.label)).join(', ')}.</li>`).join('');
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p>${esc(me.product)} è il portale del personale delle strutture: presenze e turni, fascicoli delle persone, processi HR, analisi e amministrazione. Si usa dal browser, dal computer o dal telefono, con un account personale.</p>
<h3>${c.number}.1 Il menu per aree</h3>
<p>A sinistra c’è il menu, diviso per aree. Ogni profilo vede soltanto le pagine che può usare; la voce «Da completare» mostra un contatore rosso con le attività urgenti.</p>
<ul class="menu">${menu}</ul>
<p>In basso nel menu compaiono il tuo nome, il tuo profilo e la versione del portale.</p>
<h3>${c.number}.2 La barra superiore</h3>
<p>In alto trovi il titolo della pagina e, dove serve, la <strong>struttura</strong> e il <strong>mese di riferimento</strong>: le pagine delle presenze lavorano sempre sulla struttura e sul mese scelti qui (le frecce spostano il mese avanti e indietro). A destra ci sono quattro pulsanti: la guida della pagina «?», il cambio di tema chiaro/scuro, «Il mio account» (lucchetto) ed «Esci».</p>
<h3>${c.number}.3 La guida contestuale</h3>
<p>Il pulsante «?» apre un pannello laterale con la spiegazione della pagina in cui ti trovi: cosa serve, come si fa, cosa vale per il tuo profilo e le cose da sapere. Lo stesso testo è raccolto, pagina per pagina, nei capitoli di questo manuale e nella pagina «Guida» del portale.</p>
${figure('guida-contestuale')}
<h3>${c.number}.4 Tema chiaro e scuro</h3>
<p>Il portale segue il tema del sistema; con il pulsante in alto a destra puoi scegliere il tema chiaro o scuro, e la scelta resta memorizzata nel browser. Le schermate di questo manuale usano il tema chiaro; qui sotto, per confronto, il riepilogo nel tema scuro.</p>
${figure('tema-scuro')}
<h3>${c.number}.5 Uso dal telefono</h3>
<p>Dal telefono il portale si adatta a una sola colonna: il menu si apre con il pulsante ☰ in alto a sinistra e il registro passa automaticamente alla vista <strong>Giorno</strong>, che elenca le persone del giorno scelto con un pulsante per ogni fascia. Le altre pagine funzionano come sul computer.</p>
<div class="fig-row">${figure('telefono-riepilogo')}${figure('telefono-giorno')}${figure('telefono-menu')}</div>
<h3>${c.number}.6 Avvisi e conferme</h3>
<p>Dopo un salvataggio compare in basso a destra una breve notifica (verde se è andato tutto bene, rossa in caso di errore). Le operazioni che non si possono annullare chiedono una conferma e, spesso, una motivazione che resta nello storico.</p>
</section>`);

  // 2. Accesso e sicurezza
  c = chapter('accesso', 'Accesso e sicurezza', ['Il mio account']);
  const sec = HELP.security;
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p>Ogni persona ha un account nominativo. Per entrare servono la password personale e un codice a 6 cifre generato da un’app Authenticator sul telefono (per esempio Microsoft o Google Authenticator). Nessuno, nemmeno l’amministratore, conosce la tua password.</p>
<h3>${c.number}.1 Primo accesso con il codice di attivazione</h3>
<p>L’amministratore crea l’account e ti consegna di persona un <strong>codice di attivazione</strong>, valido 7 giorni e una sola volta. Nella pagina di accesso scegli «Usa il codice di attivazione», inserisci nome utente e codice e prosegui.</p>
${figure('accesso')}
${figure('primo-accesso')}
<h3>${c.number}.2 App Authenticator e password</h3>
<p>Il portale mostra un codice QR: inquadralo con l’app Authenticator (oppure inserisci a mano la chiave scritta sotto). Scegli una password personale di almeno 12 caratteri — una frase lunga è più sicura e più facile da ricordare — e scrivi il codice a 6 cifre che l’app mostra. Premi «Attiva l’account».</p>
${figure('attivazione-app')}
<h3>${c.number}.3 Codici di recupero</h3>
<p>Alla fine dell’attivazione compaiono i <strong>codici di recupero</strong>: servono se perdi il telefono. Scaricali o stampali e conservali in un luogo sicuro, separato dal telefono. Non verranno mostrati di nuovo; ogni codice vale una sola volta.</p>
${figure('codici-recupero')}
<h3>${c.number}.4 Accesso normale</h3>
<p>Dalla volta successiva inserisci nome utente e password, poi il codice a 6 cifre dell’app. Se non hai il telefono, scegli «Usa un codice di recupero» e inserisci uno dei codici conservati.</p>
${figure('codice-app')}
<h3>${c.number}.5 Conferma di sicurezza per le operazioni sensibili</h3>
<p>Per alcune operazioni (accessi e ruoli, backup, paghe, esportazioni con dati personali, creazione di strutture) il portale chiede di nuovo password e codice dell’app: è la finestra «Conferma di sicurezza». La conferma vale 5 minuti, poi viene richiesta di nuovo.</p>
${figure('conferma-sicurezza')}
<h3>${c.number}.6 La pagina «Il mio account»</h3>
<p>${esc(sec.intro)} Si apre dal lucchetto in alto a destra. Qui cambi la password, configuri un nuovo telefono (il vecchio smette di funzionare), generi nuovi codici di recupero e chiudi le altre sessioni aperte, per esempio dopo aver usato un computer condiviso.</p>
${figure('pag-security')}
<h3>${c.number}.7 Sessione inattiva</h3>
<p>Dopo 13 minuti senza clic né tasti compare un avviso; al quindicesimo minuto la sessione scade e bisogna accedere di nuovo. In ogni caso una sessione dura al massimo 8 ore. Quando hai finito, usa «Esci».</p>
<div class="callout"><strong>Se perdi o cambi il telefono.</strong> Entra con un codice di recupero e, da «Il mio account», configura il nuovo telefono. Se non hai più codici, chiedi all’amministratore un nuovo codice di attivazione: dovrai rifare il primo accesso.</div>
</section>`);

  // 3-9. Un capitolo per area
  for (const group of GROUPS) {
    const pages = PAGES.filter(p => p.group === group);
    c = chapter(group.toLowerCase().normalize('NFD').replace(/[^a-z]/g, ''), group, pages.map(p => p.label));
    const blocks = pages.map((p, i) => pageSection(p, c.number, i + 1, HELP[p.id], roleLabel, capOf));
    const intro = {
      Panoramica: 'Le due pagine di partenza: il riepilogo del mese e l’elenco delle cose da fare, ricavato in automatico dai dati.',
      Presenze: 'Il cuore del portale: il registro dei turni e delle assenze, i controlli di fine mese, il percorso di approvazione e la copertura dei turni.',
      Persone: 'I fascicoli del personale, l’archivio dei documenti, i collegamenti fra strutture, le uscite e la rubrica delle strutture.',
      Amministrazione: 'Accordi individuali e calcoli del mese, preparazione dei dati per le paghe, comunicazioni email e promemoria automatici.',
      Analisi: 'Statistiche e prospetti da scaricare, sempre con le stesse regole di accesso del portale.',
      Sistema: 'Le pagine dell’amministratore e dei responsabili: parametri delle strutture, strutture, accessi, backup e importazione dal modello Excel.',
      Aiuto: 'La guida completa con procedure e domande frequenti, e la tabella dei ruoli e permessi.',
    }[group];
    sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(group)}</h2><p class="lead">${esc(intro)}</p>${blocks.join('')}</section>`);
  }

  // 10. Procedure
  c = chapter('procedure', 'Procedure passo per passo', PROCEDURES.map(p => p.title));
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p class="lead">Le stesse procedure della pagina «Guida» del portale. Per ciascuna è indicato chi può eseguirla.</p>
${PROCEDURES.map((p, i) => `<section class="procedure"><h3>${c.number}.${i + 1} ${esc(p.title)}</h3><p class="who"><strong>Chi può farlo:</strong> ${esc(whoCan(p.cap, p.title))}</p>${list('ol', p.steps, 'steps')}</section>`).join('')}
</section>`);

  // 11. Ruoli e permessi
  c = chapter('ruoli', 'Ruoli e permessi');
  const areas = [...new Set(roles.capabilities.map(r => r.area))];
  const roleRows = roles.roles.map(r => `<tr><th scope="row">${esc(r.label)}</th><td>${esc(r.summary)}</td><td>${r.scope === 'all' ? 'Tutte le strutture' : 'Solo le strutture assegnate'}</td></tr>`).join('');
  const matrixRows = areas.map(area => `<tr class="area"><th colspan="${roles.roles.length + 1}">${esc(area)}</th></tr>`
    + roles.capabilities.filter(r => r.area === area).map(r => `<tr><td>${esc(r.description)}</td>${roles.roles.map(role => {
      const yes = r.roles.includes(role.id);
      const maybe = !yes && r.conditional.includes(role.id);
      return `<td class="mark ${yes ? 'yes' : maybe ? 'maybe' : 'no'}">${yes ? '✓' : maybe ? '◐' : '—'}</td>`;
    }).join('')}</tr>`).join('')).join('');
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p class="lead">Cosa può fare ogni profilo. I controlli sono applicati dal server: l’interfaccia mostra soltanto le funzioni consentite. La stessa tabella è nella pagina «Ruoli e permessi» del portale.</p>
<table class="plain"><thead><tr><th>Profilo</th><th>Cosa fa</th><th>Strutture</th></tr></thead><tbody>${roleRows}</tbody></table>
<p class="legend">✓ consentito · ◐ consentito se abilitato nei parametri della struttura · — non consentito</p>
<div class="scroll"><table class="matrix"><thead><tr><th>Permesso</th>${roles.roles.map(r => `<th>${esc(r.label)}</th>`).join('')}</tr></thead><tbody>${matrixRows}</tbody></table></div>
</section>`);

  // 12. Fasce e causali
  c = chapter('fasce', 'Fasce e causali');
  const slotRows = config.slots.map(s => `<tr><td><span class="code sw-s-${esc(s.id)}">${esc(s.id)}</span></td><td>${esc(s.label)}</td><td>${esc(s.start)}–${esc(s.end)}${s.overnight ? ' (uscita il giorno dopo)' : ''}</td><td class="num">${esc(s.pause)}</td><td>${s.active ? 'Sì' : 'No'}</td></tr>`).join('');
  const codeRows = config.codes.map(x => `<tr><td><span class="code sw-c-${esc(x.id)}">${esc(x.id)}</span></td><td>${esc(x.label)}</td><td>${esc(KIND_LABEL[x.kind] || x.kind)}</td><td>${x.kind === 'work' ? (x.allowed_slots.length ? x.allowed_slots.map(esc).join(', ') : 'tutte') : '—'}</td><td>${x.active ? 'Sì' : 'No'}</td></tr>`).join('');
  const swatches = [...config.slots.map(s => `.sw-s-${s.id}{--c:${s.color}}`), ...config.codes.map(x => `.sw-c-${x.id}{--c:${x.color}}`)].join('\n');
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p class="lead">Le <strong>fasce</strong> sono le righe del registro (una per persona e fascia); le <strong>causali</strong> sono i codici che si registrano nelle caselle: turni di lavoro, assenze e riposi. Ogni struttura ha i propri valori nella pagina «Parametri struttura»; qui sono riportati quelli della struttura di prova «${esc(firstCenter.name)}».</p>
<h3>${c.number}.1 Fasce orarie</h3>
<table class="plain"><thead><tr><th>Codice</th><th>Nome</th><th>Orari</th><th>Pausa (min)</th><th>Attiva</th></tr></thead><tbody>${slotRows}</tbody></table>
<h3>${c.number}.2 Causali</h3>
<table class="plain"><thead><tr><th>Codice</th><th>Descrizione</th><th>Tipo</th><th>Fasce autorizzate</th><th>Attiva</th></tr></thead><tbody>${codeRows}</tbody></table>
<p class="small">Nel registro un pallino arancione segnala un turno senza orari, la linea gialla un turno fuori sede, la sottolineatura rossa un festivo, il bordo tratteggiato un turno pianificato non ancora consuntivato.</p>
</section>`);

  // 13. FAQ
  c = chapter('faq', 'Domande frequenti', FAQ.map(([q]) => q));
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
${FAQ.map(([q, a]) => `<section class="faq"><h3>${esc(q)}</h3><p>${esc(a)}</p></section>`).join('')}
</section>`);

  // 14. Demo pubblica e portale aziendale
  c = chapter('demo', 'Demo pubblica e portale aziendale');
  const head = demoTable.head.map((h, i) => `<th>${esc(h || 'Aspetto')}</th>`).join('');
  const body = demoTable.body.map(r => `<tr>${r.map((cell, i) => i === 0 ? `<th scope="row">${inline(cell)}</th>` : `<td>${inline(cell)}</td>`).join('')}</tr>`).join('');
  sections.push(`<section class="chapter" id="cap-${c.id}"><h2><span class="num">${c.number}</span> ${esc(c.title)}</h2>
<p class="lead">Esiste una demo pubblica del portale, utile per provarlo senza installare nulla: ha lo stesso motore e le stesse pagine del portale aziendale, ma dati inventati e nessun collegamento con l’azienda. Questa tabella riassume le differenze.</p>
<table class="plain"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
<p>Nella demo i cinque profili si scelgono con un clic, senza password; nel portale aziendale ogni persona entra con il proprio account, la password e l’app Authenticator, come descritto nel capitolo «Accesso e sicurezza».</p>
</section>`);

  // Sottosezioni (titoli h3) di ogni capitolo: per l'indice e per i numeri di pagina letti dai segnalibri del PDF.
  const plain = html => norm(html.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, '\''));
  sections.forEach((html, i) => {
    chapters[i].sections = [...html.matchAll(/<h3>(.*?)<\/h3>/g)].map(m => ({ text: plain(m[1]), key: plain(m[1]), anchor: '' }));
  });
  const tocEntries = chapters.flatMap(ch => [{ key: ch.key }, ...ch.sections.map(s => ({ key: s.key }))]);
  // Copertina e indice (con i numeri di pagina quando il PDF è già stato letto una prima volta)
  const pg = key => pageOf && pageOf.get(key) ? `<span class="pg">${pageOf.get(key)}</span>` : '';
  const toc = `<nav class="toc" id="indice" aria-label="Indice"><h2>Indice</h2><ol>${chapters.map(ch => `<li><a href="#cap-${ch.id}"><span class="num">${ch.number}</span> ${esc(ch.title)}</a>${pg(ch.key)}${ch.sections.length ? `<ul>${ch.sections.map(s => `<li>${esc(s.text)}${pg(s.key)}</li>`).join('')}</ul>` : ''}</li>`).join('')}</ol></nav>`;
  const cover = `<header class="cover"><img class="emblem" src="data:image/png;base64,${emblem}" alt="" width="96" height="96">
<p class="eyebrow">${esc(me.product)} · ${esc(me.subtitle)}</p><h1>Manuale d’uso</h1>
<p class="version">Versione ${esc(catalog.version)} · generato il ${generated}</p>
<p class="note">Le schermate mostrano dati interamente fittizi (strutture «Demo», persone inventate, mese di ${monthName} ${fictitiousMonth.slice(0, 4)}).</p>
<p class="small">Il manuale è rivolto a chi lavora negli uffici e nelle strutture. I testi delle pagine sono gli stessi della guida contestuale del portale.</p></header>`;
  const css = stylesheet(swatches);
  const html = `<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Manuale d’uso di ${esc(me.product)} ${esc(catalog.version)}, con schermate su dati fittizi.">
<title>Manuale d’uso · ${esc(me.product)}</title>
<link rel="stylesheet" href="${CSS_NAME}">
<style>
${css}
</style>
</head>
<body>
<div class="sheet">
${cover}
${toc}
${sections.join('\n')}
<footer class="colophon">${esc(me.product)} ${esc(catalog.version)} · Manuale generato il ${generated} dal portale di prova con dati fittizi.</footer>
</div>
</body>
</html>
`;
  return { html, css, chapters, tocEntries, pageOf };
}

function pageSection(p, chapterNo, idx, help, roleLabel, capOf) {
  const roleUsed = roleLabel[PROFILE_OF[p.id]];
  const ctx = p.context || [];
  const meta = [`Menu «${p.group}»`, `indirizzo #/${p.path || ''}`,
    p.cap ? `permesso: ${capOf[p.cap]?.description.toLowerCase() || p.cap}` : 'per tutti i profili',
    ctx.length ? `in alto si scelgono ${[ctx.includes('center') ? 'la struttura' : '', ctx.includes('month') ? 'il mese' : ''].filter(Boolean).join(' e ')}` : ''].filter(Boolean);
  // La schermata principale va numerata prima delle figure aggiuntive: nel documento compare per prima.
  const main = figure(`pag-${p.id}`, `Schermata della pagina ${p.label} (profilo ${roleUsed})`);
  const extras = (EXTRAS[p.id] || []).map(id => figure(id)).join('');
  const rolesRows = help.roles ? Object.entries(help.roles).map(([r, t]) => `<tr><th scope="row">${esc(roleLabel[r] || r)}</th><td>${esc(t)}</td></tr>`).join('') : '';
  return `<section class="page" id="pag-${p.id}"><h3>${chapterNo}.${idx} ${esc(p.label)}</h3>
<p class="meta">${meta.map(esc).join(' · ')}.</p>
<p class="intro">${esc(help.intro)}</p>
${main}
${help.steps?.length ? `<p class="h4">Come si fa</p>${list('ol', help.steps, 'steps')}` : ''}
${extras}
${help.notes?.length ? `<div class="block"><p class="h4">Da sapere</p>${list('ul', help.notes, 'notes')}</div>` : ''}
${rolesRows ? `<div class="block"><p class="h4">Per il tuo profilo</p><table class="roles-text">${rolesRows}</table></div>` : ''}
</section>`;
}

function stylesheet(swatches) {
  return `/* Manuale d'uso NefroCenter WR: stile generato da strumenti/guide/manuale.cjs (anche incorporato nell'HTML). */
:root { --blue: #1f3a8a; --ink: #17213a; --muted: #4a5873; --faint: #6f7c95; --line: #dfe4ee; --soft: #e9edf8; --bg: #f4f6fb; --ok: #1f7a4d; --warn: #9a5b00; --accent: #c30e1a; }
@page { size: A4 portrait; margin: 16mm; }
* { box-sizing: border-box; }
html { font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: var(--bg); color: var(--ink); font-size: 11pt; line-height: 1.5; }
.sheet { max-width: 920px; margin: 0 auto; padding: 32px 40px 48px; background: #fff; }
h1, h2, h3, h4 { color: var(--blue); line-height: 1.25; margin: 0; letter-spacing: -.01em; }
h1 { font-size: 30pt; font-weight: 800; }
h2 { font-size: 19pt; font-weight: 750; margin: 0 0 10px; padding-bottom: 8px; border-bottom: 2px solid var(--soft); }
h3 { font-size: 13.5pt; font-weight: 700; margin: 22px 0 6px; break-after: avoid; page-break-after: avoid; }
h4, .h4 { font-size: 10.5pt; font-weight: 700; margin: 12px 0 4px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); break-after: avoid; page-break-after: avoid; }
p { margin: 0 0 8px; }
h1 .num, h2 .num, h3 .num, .toc .num { display: inline-block; min-width: 1.6em; color: var(--accent); font-weight: 800; }
.small { font-size: 9.5pt; color: var(--muted); }
.lead { font-size: 11.5pt; color: var(--muted); }
.meta { font-size: 9pt; color: var(--faint); margin-bottom: 6px; }
.intro { font-weight: 500; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .92em; }
a { color: var(--blue); }
/* Copertina e indice */
.cover { min-height: 230mm; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 10px; break-after: page; page-break-after: always; }
.cover .emblem { width: 96px; height: 96px; border-radius: 50%; background: #fff; box-shadow: 0 2px 10px rgba(16,27,61,.12); }
.cover .eyebrow { font-size: 10.5pt; letter-spacing: .14em; text-transform: uppercase; color: var(--accent); font-weight: 700; margin: 10px 0 0; }
.cover .version { font-size: 12pt; color: var(--muted); }
.cover .note { max-width: 60ch; background: var(--soft); border-radius: 10px; padding: 8px 14px; color: var(--blue); font-weight: 600; font-size: 10pt; }
.toc { break-after: page; page-break-after: always; }
.toc ol { list-style: none; padding: 0; margin: 0; columns: 2; column-gap: 28px; }
.toc > ol > li { break-inside: avoid; margin-bottom: 7px; font-weight: 600; }
.toc a { text-decoration: none; color: var(--ink); }
.toc ul { list-style: none; padding-left: 1.6em; margin: 2px 0 0; font-weight: 400; font-size: 9.5pt; color: var(--muted); }
.toc .pg { float: right; color: var(--muted); font-weight: 400; font-variant-numeric: tabular-nums; padding-left: 8px; }
.toc ol { columns: 1; }
/* Capitoli */
.chapter { break-before: page; page-break-before: always; }
.chapter > h2 { margin-bottom: 12px; }
.page + .page { margin-top: 26px; border-top: 1px solid var(--line); padding-top: 10px; }
.page > h3 { break-before: auto; }
.page > h3 { margin-top: 10px; }
.menu li { margin-bottom: 3px; }
.steps, .notes { margin: 0 0 8px; padding-left: 22px; }
.steps li, .notes li { margin-bottom: 4px; }
.block { break-inside: avoid; page-break-inside: avoid; }
.scroll { overflow-x: auto; }
.callout { border-left: 4px solid var(--blue); background: var(--soft); padding: 8px 14px; border-radius: 0 8px 8px 0; margin: 12px 0; break-inside: avoid; page-break-inside: avoid; }
.procedure, .faq { break-inside: avoid; page-break-inside: avoid; }
.who { font-size: 10pt; color: var(--muted); }
/* Figure */
.fig { margin: 12px 0 16px; break-inside: avoid; page-break-inside: avoid; }
.fig img { display: block; max-width: 100%; max-height: 185mm; width: auto; height: auto; border: 1px solid var(--line); border-radius: 6px; box-shadow: 0 1px 3px rgba(16,27,61,.08); }
.fig figcaption { font-size: 9pt; color: var(--muted); margin-top: 6px; line-height: 1.4; }
.fig figcaption strong { color: var(--blue); }
.fig-row { display: flex; gap: 14px; align-items: flex-start; break-inside: avoid; page-break-inside: avoid; }
.fig-row .fig { flex: 1 1 0; min-width: 0; }
.fig-row .fig img { max-height: 135mm; margin: 0 auto; }
/* Tabelle */
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 6px 0 12px; }
th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
thead th { background: var(--soft); color: var(--blue); font-weight: 700; }
tbody th { font-weight: 650; }
tr { break-inside: avoid; page-break-inside: avoid; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.roles-text th { width: 28%; color: var(--blue); }
.matrix th, .matrix td { font-size: 8.8pt; padding: 4px 6px; }
.matrix thead th { text-align: center; }
.matrix thead th:first-child { text-align: left; }
.matrix tr.area th { background: #f8f9fc; color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-size: 8pt; padding-top: 9px; }
.matrix td.mark { text-align: center; font-weight: 800; width: 12%; }
.matrix td.yes { color: var(--ok); }
.matrix td.maybe { color: var(--warn); }
.matrix td.no { color: #b8c0d0; }
.legend { font-size: 9pt; color: var(--muted); }
.code { --c: #2f5fb3; display: inline-grid; place-items: center; min-width: 30px; height: 22px; padding: 0 6px; border-radius: 6px; font-weight: 750; font-size: 9pt; background: color-mix(in srgb, var(--c) 18%, transparent); color: color-mix(in srgb, var(--c) 82%, var(--ink)); border: 1px solid color-mix(in srgb, var(--c) 45%, transparent); }
${swatches}
.colophon { margin-top: 36px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 9pt; color: var(--faint); }
@media screen and (max-width: 700px) { .sheet { padding: 16px; } .toc ol { columns: 1; } .fig-row { flex-wrap: wrap; } h1 { font-size: 24pt; } }
@media print { body { background: #fff; } .sheet { max-width: none; padding: 0; } .fig img { box-shadow: none; } .page + .page { border-top: 0; padding-top: 0; margin-top: 0; } .scroll { overflow: visible; } }
`;
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
