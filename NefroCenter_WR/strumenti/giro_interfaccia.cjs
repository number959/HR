// Giro completo dell'interfaccia: ogni profilo dimostrativo apre tutte le pagine del proprio menu.
// Raccoglie errori della console, errori di pagina, risposte HTTP >= 400 e riquadri di errore mostrati.
// Uso: node giro_interfaccia.cjs CARTELLA_SCHERMATE [INDIRIZZO]   (portale di anteprima o demo con dati fittizi)
// Richiede Node.js e Playwright con Chromium. QA_CHROMIUM_NO_SANDBOX=1 solo nei contenitori senza sandbox.
const { chromium } = require('playwright');
const OUT = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:8090';
const ROLES = ['Amministratore', 'HR centrale', 'Responsabile di struttura', 'Compilatore', 'Direzione · consultazione'];

(async () => {
  const browser = await chromium.launch({ args: ['--lang=it-IT'].concat(process.env.QA_CHROMIUM_NO_SANDBOX ? ['--no-sandbox'] : []) });
  const report = [];
  for (const role of ROLES) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'it-IT' });
    const page = await context.newPage();
    const problems = [];
    page.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
    page.on('pageerror', e => problems.push('pagina: ' + e.message));
    page.on('response', r => { if (r.status() >= 400) problems.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`); });
    await page.goto(BASE + '/');
    await page.waitForSelector('.demo-role');
    await page.click(`.demo-role:has-text("${role}")`);
    await page.waitForSelector('.sidebar');
    const links = await page.$$eval('.nav-link', els => els.map(a => ({ href: a.getAttribute('href'), label: a.textContent.trim() })));
    links.push({ href: '#/sicurezza', label: 'Il mio account' });
    const visited = [];
    for (const link of links) {
      const before = problems.length;
      await page.goto(BASE + '/' + link.href);
      await page.waitForFunction(() => !document.querySelector('#content .skeleton'), null, { timeout: 15000 }).catch(() => problems.push('caricamento lento: ' + link.href));
      await page.waitForTimeout(250);
      const errorBox = await page.$$eval('#content .alert.bad', els => els.map(e => e.textContent.trim()).slice(0, 2));
      for (const text of errorBox) problems.push(`riquadro di errore in ${link.href}: ${text}`);
      if (OUT && role === 'Amministratore') {
        const name = link.href.replace('#/', '') || 'riepilogo';
        await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
      }
      visited.push(`${link.label}${problems.length > before ? ' ⚠' : ''}`);
    }
    report.push({ role, pages: visited.length, visited, problems });
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
