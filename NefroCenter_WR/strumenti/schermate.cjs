// Schermate di anteprima dell'interfaccia WR (dati fittizi, server di anteprima locale: gestionale/strumenti/anteprima.py).
// Uso: node schermate.cjs CARTELLA_SCHERMATE [INDIRIZZO]
const { chromium } = require('playwright');
const OUT = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:8090';
const problems = [];

async function role(page, label) {
  await page.goto(BASE + '/#/');
  await page.waitForSelector('.demo-role');
  await page.click(`.demo-role:has-text("${label}")`);
  await page.waitForSelector('.sidebar');
  await page.waitForTimeout(400);
}

async function shot(page, name, full = false) {
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full });
}

async function logout(page) {
  await page.click('button[aria-label="Esci"]');
  await page.waitForSelector('.demo-role');
}

(async () => {
  const browser = await chromium.launch({ args: ['--lang=it-IT'].concat(process.env.QA_CHROMIUM_NO_SANDBOX ? ['--no-sandbox'] : []) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'it-IT', colorScheme: 'light' });
  const page = await context.newPage();
  page.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
  page.on('pageerror', e => problems.push('pagina: ' + e.message));
  page.on('response', r => { if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });

  await page.goto(BASE + '/');
  await page.waitForSelector('.demo-role');
  await shot(page, '01-accesso');
  await role(page, 'Responsabile di struttura');
  await shot(page, '02-riepilogo-responsabile');
  await page.goto(BASE + '/#/presenze');
  await page.waitForSelector('table.register');
  await shot(page, '03-registro-mese');
  await page.click('table.register tbody tr:nth-child(2) td:nth-child(28) .cell');
  await page.waitForSelector('dialog[open]');
  await shot(page, '04-registrazione');
  await page.keyboard.press('Escape');
  await page.goto(BASE + '/#/mese');
  await page.waitForSelector('.kpis');
  await shot(page, '05-controlli-mese');
  await logout(page);

  await role(page, 'HR centrale');
  await page.goto(BASE + '/#/persone');
  await page.waitForSelector('.table');
  await shot(page, '06-persone');
  await page.click('.table tbody tr:first-child');
  await page.waitForSelector('.tabs');
  await shot(page, '07-fascicolo');
  await page.goto(BASE + '/#/approvazioni');
  await page.waitForSelector('.steps, .alert');
  await shot(page, '08-approvazioni');
  await page.evaluate(() => { localStorage.setItem('wr.theme', 'dark'); document.documentElement.dataset.theme = 'dark'; });
  await page.goto(BASE + '/#/presenze');
  await page.waitForSelector('table.register');
  await shot(page, '09-registro-tema-scuro');
  await page.evaluate(() => { localStorage.setItem('wr.theme', 'light'); document.documentElement.dataset.theme = 'light'; });
  await logout(page);

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: 'it-IT', isMobile: true, hasTouch: true });
  const m = await mobile.newPage();
  m.on('pageerror', e => problems.push('mobile: ' + e.message));
  await role(m, 'Compilatore');
  await m.goto(BASE + '/#/presenze');
  await m.waitForSelector('.day-list');
  await shot(m, '10-telefono-giorno');
  await m.click('button[aria-label="Apri il menu"]');
  await m.waitForTimeout(300);
  await shot(m, '11-telefono-menu');
  await browser.close();
  console.log(JSON.stringify({ problems }, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
