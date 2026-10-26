// Avvio della demo pubblica: il motore Python del portale (lo stesso dell'installazione aziendale) gira nel browser
// con Pyodide. Nessuna richiesta a server aziendali: dati fittizi in memoria, invii di posta simulati.
import { setTransport } from './api.js';
import { start } from './app.js';

const CDN = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
const status = document.getElementById('boot-status');
const bar = document.getElementById('boot-bar');

function step(text, value) {
  if (status) status.textContent = text;
  if (bar) bar.value = value;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src;
    el.onload = resolve;
    el.onerror = () => reject(new Error('Impossibile caricare ' + src));
    document.head.append(el);
  });
}

async function bytes(path) {
  const response = await fetch(path, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`File della demo non disponibile: ${path}`);
  return new Uint8Array(await response.arrayBuffer());
}

// versione.json (scritto dalla build) indica la data della demo e se Pyodide è incluso nella cartella pyodide/.
async function buildInfo() {
  const response = await fetch('versione.json', { cache: 'no-cache' });
  if (!response.ok) throw new Error('File versione.json della demo non disponibile.');
  return response.json();
}

async function boot() {
  step('Caricamento del motore del portale…', 10);
  const info = await buildInfo();
  const base = info.pyodide_locale ? new URL('pyodide/', location.href).href : CDN;
  await loadScript(base + 'pyodide.js');
  const pyodide = await window.loadPyodide({ indexURL: base });
  step('Preparazione di SQLite e del calendario…', 45);
  await pyodide.loadPackage(['sqlite3', 'tzdata']);
  step('Caricamento dei dati fittizi…', 65);
  const [motore, dati] = await Promise.all([bytes('motore.zip'), bytes('dati/wr.sqlite3')]);
  pyodide.unpackArchive(motore, 'zip', { extractDir: '/motore' });
  pyodide.FS.mkdirTree('/dati');
  pyodide.FS.writeFile('/dati/wr.sqlite3', dati);
  step('Avvio del portale dimostrativo…', 85);
  pyodide.runPython("import sys\nsys.path.insert(0, '/motore')");
  const ponte = pyodide.pyimport('ponte');
  ponte.avvia('/dati', info.data_demo);
  const chiama = ponte.chiama;
  const encoder = new TextEncoder();
  setTransport(async (url, init = {}) => {
    const u = new URL(url, location.href);
    let body = init.body;
    if (typeof body === 'string') body = encoder.encode(body);
    else if (body instanceof ArrayBuffer) body = new Uint8Array(body);
    else if (!(body instanceof Uint8Array)) body = new Uint8Array(0);
    const result = chiama(init.method || 'GET', u.pathname, u.search.slice(1), JSON.stringify(init.headers || {}), body);
    const [code, headers, payload] = result.toJs({ create_proxies: false });
    result.destroy();
    return new Response(code === 204 ? null : payload, { status: code, headers });
  });
  step('Pronto.', 100);
  await start({ demo: true });
}

boot().catch(err => {
  console.error(err);
  step('La demo non si è avviata: ' + (err?.message || err) + '. Ricaricare la pagina; se il problema continua, '
    + 'verificare la connessione (la prima apertura scarica circa 15 MB).', 0);
  document.getElementById('boot')?.classList.add('boot-error');
});
