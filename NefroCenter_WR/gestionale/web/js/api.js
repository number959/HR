// Comunicazione con il servizio: sessione nel cookie (HttpOnly), token anti-falsificazione nell'intestazione.
// Nella demo pubblica il trasporto viene sostituito dal motore che gira nel browser (nessuna rete).

let token = '';
let transport = (url, init) => window.fetch(url, init);
let stepUp = null;
let sessionLost = null;
let downloader = null;  // consegna alternativa dei file (demo dentro un visualizzatore che blocca gli scaricamenti diretti)

export function setTransport(fn) { transport = fn; }
export function setDownloader(fn) { downloader = fn; }
export function setToken(value) { token = value || ''; }
export function onStepUp(fn) { stepUp = fn; }
export function onSessionLost(fn) { sessionLost = fn; }

export class ApiError extends Error {
  constructor(status, payload = {}) {
    super(payload.message || 'Operazione non riuscita. Riprovare.');
    this.status = status;
    this.code = payload.code || '';
    this.field = payload.field || '';
    this.payload = payload;
  }
}

export async function api(path, opts = {}) {
  const { method = 'GET', body, raw, contentType, background = false, retry = true } = opts;
  const headers = {};
  if (method !== 'GET' && method !== 'HEAD') headers['X-WR-Token'] = token;
  if (background) headers['X-WR-Background'] = '1';
  let payload;
  if (raw !== undefined) {
    payload = raw;
    headers['Content-Type'] = contentType || 'application/octet-stream';
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers['Content-Type'] = 'application/json';
  }
  let response;
  try {
    response = await transport('/api/' + path, { method, headers, body: payload, credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, { message: 'Servizio non raggiungibile. Controllare la connessione e riprovare.' });
  }
  const type = response.headers.get('Content-Type') || '';
  if (type.startsWith('application/json')) {
    const data = await response.json();
    if (data && typeof data.csrf === 'string') token = data.csrf;
    if (!response.ok) {
      const error = new ApiError(response.status, data?.error || {});
      if (response.status === 428 && retry && stepUp && await stepUp()) return api(path, { ...opts, retry: false });
      if (response.status === 401 && sessionLost && !path.startsWith('session')) sessionLost(error);
      throw error;
    }
    return data;
  }
  if (!response.ok) throw new ApiError(response.status, { message: 'Operazione non riuscita.' });
  return response;
}

export const get = (path, opts) => api(path, opts);
export const post = (path, body, opts) => api(path, { ...opts, method: 'POST', body });
export const put = (path, body, opts) => api(path, { ...opts, method: 'PUT', body });
export const del = (path, body, opts) => api(path, { ...opts, method: 'DELETE', body });

function filename(disposition, fallback) {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '');
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="([^"]+)"/i.exec(disposition || '');
  return plain ? plain[1] : fallback;
}

// Scarica un file prodotto dal servizio (CSV, Excel, PDF, backup) senza aprire nuove finestre.
export async function download(path, fallback = 'file') {
  const response = await api(path);
  if (!(response instanceof Response)) throw new ApiError(500, { message: 'Il servizio non ha restituito un file.' });
  const blob = await response.blob();
  await deliver(blob, filename(response.headers.get('Content-Disposition'), fallback));
}

// Scarica un file statico del portale (per esempio il manuale in PDF) con la stessa consegna dei file del servizio.
export async function downloadFile(url, name) {
  let response;
  try {
    response = await window.fetch(url, { cache: 'no-cache' });
  } catch {
    throw new ApiError(0, { message: 'File non raggiungibile. Controllare la connessione e riprovare.' });
  }
  if (!response.ok) throw new ApiError(response.status, { message: 'File non disponibile in questa installazione.' });
  await deliver(await response.blob(), name);
}

async function deliver(blob, name) {
  if (downloader) { await downloader(blob, name); return; }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

// Restituisce un indirizzo temporaneo per mostrare un allegato dentro il portale.
export async function blobUrl(path) {
  const response = await api(path);
  return URL.createObjectURL(await response.blob());
}
