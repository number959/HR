// Prova del registro presenze: scelta rapida della causale dalla casella (con «Annulla»), compilazione rapida con
// tavolozza e gomma, navigazione (mese, «Oggi», «Solo da completare»), mirino, telefono (foglio dal basso).
// Uso: node prova_registro.cjs CARTELLA_SCHERMATE [INDIRIZZO]   (portale di anteprima con dati fittizi, modalità demo)
// Richiede Node.js e Playwright con Chromium. QA_CHROMIUM_NO_SANDBOX=1 solo nei contenitori senza sandbox.
const { chromium, devices } = require('playwright');
const OUT = process.argv[2];
const BASE = (process.argv[3] || 'http://127.0.0.1:8090').replace(/\/+$/, '');
const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); return cond; };
const settle = page => page.waitForFunction(() => !document.querySelector('#content .skeleton'), null, { timeout: 20000 }).catch(() => {});

async function enter(context, role) {
  const page = await context.newPage();
  const problems = [];
  page.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text().slice(0, 160)); });
  page.on('pageerror', e => problems.push('pagina: ' + e.message.slice(0, 160)));
  await page.goto(BASE + '/');
  await page.waitForSelector('.demo-role', { timeout: 60000 });
  await page.click(`.demo-role:has-text("${role}")`);
  await page.waitForSelector('.sidebar');
  await page.goto(BASE + '/#/presenze');
  await settle(page);
  const month = await page.$('.segmented button:has-text("Mese")');
  if (month) { await month.click(); await settle(page); }
  await page.waitForSelector('table.register');
  return { page, problems };
}

const emptyPast = 'table.register button.cell.todo:not([disabled])';
const chipIn = cell => cell.$('.code');

(async () => {
  const browser = await chromium.launch({ args: ['--lang=it-IT'].concat(process.env.QA_CHROMIUM_NO_SANDBOX ? ['--no-sandbox'] : []) });
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'it-IT' });
  const { page, problems } = await enter(desktop, 'Responsabile di struttura');

  // (a) Scelta rapida dalla casella e «Annulla»
  const cell = await page.$(emptyPast);
  ok(cell, 'nessuna casella vuota di un giorno passato (classe todo)');
  const label = await cell.getAttribute('aria-label');
  await cell.click();
  await page.waitForSelector('.quick-pick');
  const options = await page.$$eval('.quick-pick .quick-code', els => els.length);
  ok(options >= 3, `causali nel riquadro: ${options}`);
  ok(await page.$('.quick-pick .quick-foot .btn:has-text("Dettagli")'), 'manca «Dettagli e orari…»');
  await page.click('.quick-pick .quick-code[data-code="m"]');
  await page.waitForSelector('.toast .btn:has-text("Annulla")', { timeout: 10000 });
  await settle(page);
  const filledLabel = label.replace(': vuota', ': Mattina');
  const filled = await page.$(`button.cell[aria-label^="${filledLabel}"]`);
  ok(filled && await chipIn(filled), 'la casella non mostra il turno dopo la scelta rapida');
  await page.screenshot({ path: `${OUT}/registro-01-scelta-rapida.png` });
  await page.click('.toast .btn:has-text("Annulla")');
  await page.waitForFunction(l => { const c = document.querySelector(`button.cell[aria-label="${l}"]`); return c && !c.querySelector('.code'); }, label, { timeout: 10000 }).catch(() => fails.push('«Annulla» non ha svuotato la casella'));

  // (a2) Tastiera: Escape chiude e riporta il focus sulla casella
  const again = await page.$(emptyPast);
  await again.focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector('.quick-pick');
  await page.keyboard.press('Escape');
  await page.waitForSelector('.quick-pick', { state: 'detached', timeout: 5000 }).catch(() => fails.push('Escape non chiude il riquadro'));
  ok(await page.evaluate(() => document.activeElement?.classList.contains('cell')), 'il focus non torna sulla casella dopo Escape');

  // (b) Compilazione rapida: tre caselle, gomma, Escape
  await page.click('.page-actions .btn:has-text("Compilazione rapida")');
  await settle(page);
  ok(await page.$('.quick-bar'), 'tavolozza assente');
  ok(await page.$('.badge:has-text("Compilazione rapida attiva")'), 'manca il distintivo della modalità');
  // Le causali di turno valgono solo nella propria fascia: si sceglie quella della fascia della prima casella vuota.
  const slotOfFirst = await page.$eval(emptyPast, el => el.closest('tr').querySelector('.slot-cell').textContent.trim());
  await page.click(`.quick-bar .quick-code[data-code="${slotOfFirst}"]`);
  await settle(page);
  const sameSlot = `table.register tbody tr:has(> td.slot-cell:text-is("${slotOfFirst}")) button.cell.todo:not([disabled])`;
  const before = await page.$$eval('table.register .code', els => els.length);
  const targets = [];
  for (let i = 0; i < 3; i += 1) {
    const t = await page.$(sameSlot);
    if (!t) break;
    targets.push(await t.getAttribute('aria-label'));
    await t.click();
    await page.waitForFunction(n => document.querySelectorAll('table.register .code').length >= n, before + i + 1, { timeout: 10000 }).catch(() => fails.push(`casella ${i + 1} non registrata in compilazione rapida`));
  }
  const after = await page.$$eval('table.register .code', els => els.length);
  ok(after === before + 3, `compilazione rapida: ${before} → ${after} (attese +3)`);
  await page.screenshot({ path: `${OUT}/registro-02-compilazione-rapida.png` });
  const eraser = await page.$('.quick-bar .quick-code.eraser');
  if (ok(eraser, 'gomma assente per il responsabile')) {
    await eraser.click();
    await settle(page);
    const first = await page.$(`button.cell[aria-label^="${targets[0].replace(': vuota', '')}"]`);
    ok(first, 'casella registrata in compilazione rapida non ritrovata');
    if (first) await first.click();
    await page.waitForFunction(n => document.querySelectorAll('table.register .code').length === n, after - 1, { timeout: 10000 }).catch(() => fails.push('la gomma non ha svuotato la casella'));
  }
  await page.focus('table.register .cell:not([disabled])');
  await page.keyboard.press('Escape');
  await settle(page);
  ok(!(await page.$('.quick-bar')), 'Escape non esce dalla compilazione rapida');

  // (c) Navigazione e contesto
  ok(await page.$('.view-summary:has-text("Stai vedendo")'), 'manca la riga «Stai vedendo»');
  ok(await page.$('table.register thead th.today .wd:has-text("oggi")'), 'la colonna di oggi non è marcata «oggi»');
  const monthBefore = await page.$eval('.topbar input[type="month"]', el => el.value);
  await page.click('.month-nav [aria-label="Mese precedente"]');
  await settle(page);
  const monthAfter = await page.$eval('.topbar input[type="month"]', el => el.value);
  ok(monthAfter < monthBefore, `«Mese precedente» non cambia il mese (${monthBefore} → ${monthAfter})`);
  await page.click('.month-nav .btn:has-text("Oggi")');
  await settle(page);
  ok((await page.$eval('.topbar input[type="month"]', el => el.value)) === monthBefore, '«Oggi» non torna al mese corrente');
  await page.waitForSelector('table.register');
  const rows = await page.$$eval('table.register tbody th.name-cell', els => els.length);
  const toggle = await page.$('.btn.toggle:has-text("Solo da completare")');
  if (ok(toggle, 'manca «Solo da completare»')) {
    await toggle.click();
    await settle(page);
    const filteredRows = await page.$$eval('table.register tbody th.name-cell', els => els.length);
    ok(filteredRows <= rows && filteredRows > 0, `filtro «Solo da completare»: ${rows} → ${filteredRows}`);
    ok(await page.$('.todo-count'), 'manca il conteggio dei giorni da registrare accanto al nome');
    await page.click('.btn.toggle');
    await settle(page);
  }
  await page.hover('table.register .cell[data-c="3"] >> nth=0');
  await page.waitForTimeout(150);
  ok(await page.$('table.register thead th[data-c="3"].hl'), 'il mirino non evidenzia la colonna');
  ok(await page.$('table.register th.name-cell.hl'), 'il mirino non evidenzia la persona');
  ok(await page.$('details.legend-box[open]'), 'la legenda non è sopra la griglia (aperta su schermo largo)');
  await page.screenshot({ path: `${OUT}/registro-03-navigazione.png` });
  await desktop.close();

  // (d) Compilatore: scelta rapida disponibile
  const operatorCtx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'it-IT' });
  const op = await enter(operatorCtx, 'Compilatore');
  const opCell = await op.page.$(emptyPast);
  if (ok(opCell, 'compilatore: nessuna casella vuota di un giorno passato')) {
    await opCell.click();
    await op.page.waitForSelector('.quick-pick');
    const hasDelete = Boolean(await op.page.$('.quick-pick .quick-foot .btn:has-text("Elimina")'));
    await op.page.keyboard.press('Escape');
    fails.opDelete = hasDelete;
  }
  const opProblems = op.problems;
  await operatorCtx.close();

  // (e) Telefono: foglio dal basso e vista Giorno
  const phone = await browser.newContext({ ...devices['iPhone 13'], locale: 'it-IT' });
  const ph = await enter(phone, 'Responsabile di struttura');
  const phCell = await ph.page.$(emptyPast);
  await phCell.click();
  await ph.page.waitForSelector('.quick-pick.sheet');
  const sheet = await ph.page.$eval('.quick-pick.sheet', el => { const r = el.getBoundingClientRect(); return { bottom: Math.round(r.bottom), vh: window.innerHeight, w: Math.round(r.width), vw: window.innerWidth }; });
  ok(sheet.bottom <= sheet.vh + 1 && sheet.w === sheet.vw, `foglio dal basso fuori misura: ${JSON.stringify(sheet)}`);
  const minH = await ph.page.$$eval('.quick-pick .quick-code', els => Math.min(...els.map(e => e.getBoundingClientRect().height)));
  ok(minH >= 44, `pulsanti del foglio troppo bassi: ${minH}px`);
  await ph.page.screenshot({ path: `${OUT}/registro-04-telefono-foglio.png` });
  await ph.page.keyboard.press('Escape');
  await ph.page.click('.segmented button:has-text("Giorno")');
  await settle(ph.page);
  const dayBtn = await ph.page.$('.day-slots .btn:not([disabled])');
  if (ok(dayBtn, 'vista Giorno senza pulsanti di fascia')) {
    await dayBtn.click();
    ok(await ph.page.waitForSelector('.quick-pick.sheet', { timeout: 5000 }).catch(() => null), 'la vista Giorno non apre il riquadro rapido');
    await ph.page.keyboard.press('Escape');
  }
  const phProblems = ph.problems;
  await phone.close();
  await browser.close();
  const { opDelete, ...rest } = fails;
  const list = fails.filter(f => typeof f === 'string');
  console.log(JSON.stringify({ quickOptions: options, quickFill: `${before} → ${after}`, filterRows: rows, phoneSheet: sheet, operatorDelete: opDelete, fails: list,
    problems: [...new Set([...problems, ...opProblems, ...phProblems])].slice(0, 8) }, null, 1));
  if (list.length) process.exit(1);
})().catch(e => { console.error('errore della prova:', e); process.exit(1); });
