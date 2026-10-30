// Prova della demo pubblica: avvio del motore nel browser, profili, pagine, una registrazione e un'esportazione.
// Uso: python avvia_demo.py --port 8095  e poi  node prova_demo.cjs CARTELLA_SCHERMATE http://127.0.0.1:8095
const { chromium } = require('playwright');
const OUT = process.argv[2];
const BASE = (process.argv[3] || 'http://127.0.0.1:8095').replace(/\/+$/, '');  // anche una sottocartella
(async () => {
  const browser = await chromium.launch({ args: ['--lang=it-IT'].concat(process.env.QA_CHROMIUM_NO_SANDBOX ? ['--no-sandbox'] : []) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'it-IT', acceptDownloads: true });
  const page = await context.newPage();
  const problems = [];
  page.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
  page.on('pageerror', e => problems.push('pagina: ' + e.message));
  page.on('response', r => { if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });
  const t0 = Date.now();
  await page.goto(BASE + '/');
  await page.screenshot({ path: `${OUT}/demo-00-avvio.png` });
  await page.waitForSelector('.demo-role', { timeout: 120000 });
  const bootMs = Date.now() - t0;
  await page.screenshot({ path: `${OUT}/demo-01-profili.png` });
  await page.click('.demo-role:has-text("Responsabile di struttura")');
  await page.waitForSelector('.sidebar');
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/demo-02-riepilogo.png` });
  const links = await page.$$eval('.nav-link', els => els.map(a => a.getAttribute('href')));
  for (const href of links) {
    await page.goto(BASE + '/' + href);
    await page.waitForFunction(() => !document.querySelector('#content .skeleton'), null, { timeout: 30000 }).catch(() => problems.push('lento: ' + href));
    const bad = await page.$$eval('#content .alert.bad', els => els.map(e => e.textContent.trim()));
    for (const b of bad) problems.push(`errore in ${href}: ${b}`);
  }
  // una registrazione nel registro (mese aperto)
  await page.goto(BASE + '/#/presenze');
  await page.waitForSelector('table.register');
  const before = await page.$$eval('table.register .code', els => els.length);
  const cell = await page.$('table.register tbody tr:nth-child(3) td:nth-child(30) .cell:not([disabled])');
  let saved = 'cella non trovata';
  if (cell) {
    await cell.click();
    await page.waitForSelector('dialog[open]');
    await page.click('dialog[open] .dialog-foot .btn.primary');
    await page.waitForTimeout(800);
    const after = await page.$$eval('table.register .code', els => els.length);
    saved = after > before ? 'registrazione salvata' : `nessuna nuova casella (${before} → ${after})`;
  }
  // esportazione CSV
  await page.goto(BASE + '/#/esportazioni');
  await page.waitForSelector('.card');
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }).catch(() => null),
    page.click('button:has-text("Riepilogo del mese della struttura")')]);
  const csv = download ? download.suggestedFilename() : 'nessun file';
  await page.screenshot({ path: `${OUT}/demo-03-esportazioni.png` });
  await browser.close();
  console.log(JSON.stringify({ bootMs, pages: links.length, saved, csv, problems }, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
