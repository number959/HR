// Avvio della demo pubblica: il motore Python del portale (lo stesso dell'installazione aziendale) gira nel browser
// con Pyodide. Nessuna richiesta a server aziendali: dati fittizi in memoria, invii di posta simulati.
import { setDownloader, setTransport } from './api.js';
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

function decodeBase64(text) {
  const binary = atob(text.replace(/\s+/g, ''));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

// Alcuni servizi di pagine pubblicano solo tipi di file web: allora archivi e database arrivano come testo base64
// (costruisci_demo.py --solo-file-web) e vengono decodificati qui, prima che la demo o Pyodide li chiedano con fetch.
// Nelle altre installazioni versione.json non ha «file_base64» e questa funzione non viene mai chiamata.
function textEncodedFiles(map) {
  const original = window.fetch.bind(window);
  const here = new URL('.', document.baseURI).href;
  window.fetch = async (input, init) => {
    const href = new URL(input instanceof Request ? input.url : String(input), document.baseURI).href;
    const rel = href.startsWith(here) ? href.slice(here.length).split(/[?#]/)[0] : '';
    if (!map[rel]) return original(input, init);
    const response = await original(new URL(map[rel], here).href, { cache: 'no-cache' });
    if (!response.ok) return response;
    const data = decodeBase64(await response.text());
    return new Response(data, { status: 200, headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': String(data.length) } });
  };
}

// versione.json (scritto dalla build) indica la data della demo, se Pyodide è incluso nella cartella pyodide/
// e gli eventuali file codificati in testo.
async function buildInfo() {
  const response = await fetch('versione.json', { cache: 'no-cache' });
  if (!response.ok) throw new Error('File versione.json della demo non disponibile.');
  return response.json();
}

// Dentro un visualizzatore che blocca gli scaricamenti diretti del browser (per esempio una pagina pubblicata su claude.ai)
// CSV, Excel e backup passano dal suo servizio di salvataggio, che chiede conferma a chi guarda. Altrove non cambia nulla.
function viewerDownloads() {
  if (!window.claude || typeof window.claude.use !== 'function') return;
  window.claude.use('downloads').then(downloads => {
    if (!downloads) return;
    setDownloader(async (blob, name) => {
      try {
        await downloads.save({ filename: name, data: blob });
      } catch (err) {
        if (err?.code === 'declined') return;
        throw new Error('Salvataggio del file non riuscito in questo visualizzatore' + (err?.message ? ` (${err.message})` : '') + '.');
      }
    });
  }).catch(() => {});
}

async function boot() {
  step('Caricamento del motore del portale…', 10);
  const info = await buildInfo();
  if (info.file_base64) textEncodedFiles(info.file_base64);
  const base = info.pyodide_locale ? new URL('pyodide/', document.baseURI).href : CDN;
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
    const u = new URL(url, document.baseURI);
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
  viewerDownloads();
  await start({ demo: true });
}

boot().catch(err => {
  console.error(err);
  step('La demo non si è avviata: ' + (err?.message || err) + '. Ricaricare la pagina; se il problema continua, '
    + 'verificare la connessione (la prima apertura scarica circa 15 MB).', 0);
  document.getElementById('boot')?.classList.add('boot-error');
});
