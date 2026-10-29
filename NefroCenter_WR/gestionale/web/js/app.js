// Avvio dell'interfaccia: sessione, struttura della pagina, menu per aree, contesto (struttura e mese), navigazione.
import { get, onSessionLost, onStepUp, post } from './api.js';
import { recoveryCodes, renderAuth, rememberToken, stepUpDialog } from './auth.js';
import { HELP } from './help.js';
import { icon } from './icons.js';
import { button, clear, errorMessage, fmt, h, shiftMonth, skeleton, store, toast } from './ui.js';

export const PAGES = [
  { id: 'home', path: '', label: 'Riepilogo', icon: 'home', group: 'Panoramica', module: 'home' },
  { id: 'todo', path: 'da-completare', label: 'Da completare', icon: 'checks', group: 'Panoramica', cap: 'presenze.vedi', module: 'todo', context: ['month'] },
  { id: 'attendance', path: 'presenze', label: 'Registro presenze', icon: 'calendar', group: 'Presenze', cap: 'presenze.vedi', module: 'attendance', context: ['center', 'month'] },
  { id: 'month', path: 'mese', label: 'Controlli e chiusura', icon: 'shield', group: 'Presenze', cap: 'presenze.vedi', module: 'month', context: ['center', 'month'] },
  { id: 'approvals', path: 'approvazioni', label: 'Approvazioni', icon: 'stamp', group: 'Presenze', cap: 'approvazioni.vedi', module: 'approvals', context: ['month'] },
  { id: 'coverage', path: 'copertura', label: 'Copertura turni', icon: 'layers', group: 'Presenze', cap: 'copertura.vedi', module: 'coverage', context: ['center', 'month'] },
  { id: 'people', path: 'persone', label: 'Persone e fascicoli', icon: 'users', group: 'Persone', cap: 'hr.fascicoli', module: 'people', context: ['center'] },
  { id: 'documents', path: 'documenti', label: 'Documenti', icon: 'file', group: 'Persone', cap: 'hr.fascicoli', module: 'documents' },
  { id: 'workforce', path: 'gruppo', label: 'Personale di gruppo', icon: 'link', group: 'Persone', cap: 'gruppo.gestisci', module: 'workforce' },
  { id: 'departures', path: 'uscite', label: 'Uscite e dotazioni', icon: 'door', group: 'Persone', cap: 'uscite.gestisci', module: 'departures' },
  { id: 'structures', path: 'rubrica', label: 'Rubrica strutture', icon: 'building', group: 'Persone', cap: 'strutture.gestisci', module: 'structures' },
  { id: 'agreements', path: 'accordi', label: 'Accordi e calcoli', icon: 'calculator', group: 'Amministrazione', cap: 'accordi.vedi', module: 'agreements', context: ['center', 'month'] },
  { id: 'collaborators', path: 'collaboratori', label: 'Collaboratori e compensi', icon: 'users', group: 'Amministrazione', cap: 'accordi.vedi', module: 'collaborators', context: ['center', 'month'] },
  { id: 'payroll', path: 'paghe', label: 'Paghe', icon: 'wallet', group: 'Amministrazione', cap: 'paghe.gestisci', module: 'payroll', context: ['center', 'month'] },
  { id: 'mail', path: 'comunicazioni', label: 'Comunicazioni', icon: 'mail', group: 'Amministrazione', cap: 'comunicazioni.usa', module: 'mail' },
  { id: 'reminders', path: 'promemoria', label: 'Promemoria', icon: 'bell', group: 'Amministrazione', cap: 'promemoria.vedi', module: 'reminders' },
  { id: 'stats', path: 'statistiche', label: 'Statistiche', icon: 'chart', group: 'Analisi', cap: 'statistiche.vedi', module: 'stats' },
  { id: 'exports', path: 'esportazioni', label: 'Esportazioni', icon: 'download', group: 'Analisi', cap: 'statistiche.vedi', module: 'exports', context: ['center', 'month'] },
  { id: 'settings', path: 'parametri', label: 'Parametri struttura', icon: 'sliders', group: 'Sistema', cap: 'presenze.vedi', module: 'settings', context: ['center'] },
  { id: 'centers', path: 'strutture', label: 'Strutture', icon: 'building', group: 'Sistema', cap: 'centri.crea', module: 'centers' },
  { id: 'users', path: 'accessi', label: 'Accessi e ruoli', icon: 'key', group: 'Sistema', cap: 'utenti.gestisci', module: 'users' },
  { id: 'backups', path: 'backup', label: 'Backup', icon: 'database', group: 'Sistema', cap: 'backup.gestisci', module: 'backups' },
  { id: 'import', path: 'importa', label: 'Importa Excel', icon: 'upload', group: 'Sistema', cap: 'import.excel', module: 'import' },
  { id: 'guide', path: 'guida', label: 'Guida', icon: 'help', group: 'Aiuto', module: 'guide' },
  { id: 'roles', path: 'ruoli', label: 'Ruoli e permessi', icon: 'shieldUser', group: 'Aiuto', module: 'roles' },
  { id: 'security', path: 'sicurezza', label: 'Il mio account', icon: 'lock', group: null, module: 'security' },
];

const app = {
  me: null, demo: false, cid: '', month: '', root: null, current: null, renderToken: 0,
  can(cap) { return Boolean(this.me?.caps?.[cap]); },
  center() { return this.me?.centers.find(c => c.id === this.cid) || null; },
};
window.WR = app;  // utile per le prove automatiche e la console del browser

// ---------- Tema ----------
function applyTheme(theme) {
  const value = theme || store('theme') || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = value;
  return value;
}

// ---------- Avvio ----------
export async function start(opts = {}) {
  app.root = document.getElementById('root');
  applyTheme();
  onStepUp(stepUpDialog);
  onSessionLost(() => { toast('Sessione scaduta: accedi di nuovo.', 'bad'); boot(); });
  window.addEventListener('hashchange', () => app.me && route());
  app.demo = Boolean(opts.demo);
  await boot();
}

async function boot() {
  clear(app.root, h('div', { class: 'content' }, skeleton(6)));
  let state;
  try {
    state = await get('session');
  } catch (err) {
    clear(app.root, h('div', { class: 'content' }, h('div', { class: 'alert bad' }, errorMessage(err))));
    return;
  }
  rememberToken(state);
  app.demo = app.demo || Boolean(state.demo);
  if (state.stage !== 'full') {
    app.me = null;
    renderAuth(app.root, { ...state, demo: app.demo }, async result => {
      rememberToken(result);
      if (result.recovery_codes) return recoveryCodes(app.root, result.recovery_codes, () => enter());
      return enter();
    });
    return;
  }
  await enter();
}

async function enter() {
  app.me = await get('me');
  app.demo = app.demo || app.me.demo;
  const saved = store('cid');
  const centers = app.me.centers.filter(c => c.active);
  app.cid = centers.some(c => c.id === saved) ? saved : (centers[0]?.id || '');
  app.month = store('month') || app.me.today.slice(0, 7);
  shell();
  route();
  watchIdle();
}

// ---------- Struttura della pagina ----------
let refs = {};

function shell() {
  const nav = h('nav', { class: 'sidebar', id: 'sidebar', 'aria-label': 'Menu principale' },
    h('a', { class: 'brand', href: '#/' }, h('img', { src: 'img/emblema.png', alt: '' }),
      h('div', { class: 'brand-name' }, 'NefroCenter WR', h('span', { text: 'Work Resources' }))));
  let group = null;
  let groupEl = null;
  for (const p of PAGES) {
    if (!p.group || (p.cap && !app.can(p.cap))) continue;
    if (p.group !== group) {
      group = p.group;
      groupEl = h('div', { class: 'nav-group', role: 'group', 'aria-label': group }, h('div', { class: 'nav-group-title', text: group }));
      nav.append(groupEl);
    }
    groupEl.append(h('a', { class: 'nav-link', href: '#/' + p.path, dataset: { page: p.id } }, icon(p.icon), h('span', { text: p.label }),
      p.id === 'todo' ? h('span', { class: 'nav-count hidden', id: 'todo-count' }) : null));
  }
  nav.append(h('div', { class: 'sidebar-foot' }, h('div', null, h('strong', { text: app.me.user.name })),
    h('div', { text: app.me.user.role_label }), h('div', { text: `${app.me.product} ${app.me.version}` })));

  const centerSelect = h('select', { class: 'context-center', 'aria-label': 'Struttura', on: { change: e => setContext(e.target.value, app.month) } },
    centerOptions());
  const monthInput = h('input', { type: 'month', value: app.month, 'aria-label': 'Mese', on: { change: e => e.target.value && setContext(app.cid, e.target.value) } });
  const monthBox = h('div', { class: 'row', role: 'group', 'aria-label': 'Mese di riferimento' },
    button('', { kind: 'ghost icon', ic: 'chevronLeft', aria: 'Mese precedente', onClick: () => setContext(app.cid, shiftMonth(app.month, -1)) }),
    monthInput,
    button('', { kind: 'ghost icon', ic: 'chevronRight', aria: 'Mese successivo', onClick: () => setContext(app.cid, shiftMonth(app.month, 1)) }));
  const title = h('div', { class: 'page-title' });
  const themeBtn = button('', { kind: 'ghost icon', ic: document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon', aria: 'Cambia tema',
    onClick: () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      store('theme', next);
      applyTheme(next);
      themeBtn.replaceChildren(icon(next === 'dark' ? 'sun' : 'moon'));
    } });
  const userMenu = button('', { kind: 'ghost icon', ic: 'lock', aria: 'Il mio account', onClick: () => { location.hash = '#/sicurezza'; } });
  const logout = button('', { kind: 'ghost icon', ic: 'logout', aria: 'Esci', onClick: async () => {
    await post('session/logout').catch(() => null);
    app.me = null;
    location.hash = '';
    boot();
  } });
  const helpBtn = button('', { kind: 'ghost icon', ic: 'help', aria: 'Guida della pagina', onClick: () => toggleHelp(true) });
  const menuBtn = button('', { kind: 'ghost icon menu-button', ic: 'menu', aria: 'Apri il menu', onClick: () => toggleNav(true) });
  const context = h('div', { class: 'context' }, centerSelect, monthBox);
  const topbar = h('header', { class: 'topbar' }, menuBtn, title, context,
    h('div', { class: 'tools' }, helpBtn, themeBtn, userMenu, logout));
  const content = h('main', { class: 'content', id: 'content', tabindex: '-1' });
  const helpPanel = h('aside', { class: 'help-panel', 'aria-label': 'Guida della pagina', 'aria-hidden': 'true' });
  const shellEl = h('div', { class: 'shell' }, nav, h('div', { class: 'main' }, app.demo ? h('div', { class: 'demo-banner',
    text: 'Demo pubblica · dati fittizi · le modifiche restano solo in questa scheda del browser' }) : null, topbar, content), helpPanel);
  nav.addEventListener('click', e => { if (e.target.closest('a')) toggleNav(false); });
  clear(app.root, shellEl);
  refs = { shell: shellEl, nav, title, context, centerSelect, monthInput, monthBox, content, helpPanel };
  refreshTodoCount();
}

function centerOptions() {
  return app.me.centers.filter(c => c.active || app.can('centri.crea'))
    .map(c => h('option', { value: c.id, selected: c.id === app.cid, text: c.active ? c.name : `${c.name} (disattivata)` }));
}

// Dopo la creazione o la modifica di strutture: ricarica profilo e selettore della struttura.
export async function reloadProfile() {
  const me = await get('me');
  app.me = me;
  if (!me.centers.some(c => c.id === app.cid)) app.cid = me.centers.find(c => c.active)?.id || '';
  refs.centerSelect.replaceChildren(...centerOptions());
  refs.centerSelect.value = app.cid;
}

function toggleNav(open) {
  refs.shell.classList.toggle('nav-open', open);
  document.querySelector('.scrim')?.remove();
  if (open) {
    const scrim = h('div', { class: 'scrim', on: { click: () => toggleNav(false) } });
    refs.shell.append(scrim);
    refs.nav.querySelector('a')?.focus();
  }
}

export function setContext(cid, month) {
  app.cid = cid;
  app.month = month;
  store('cid', cid);
  store('month', month);
  refs.centerSelect.value = cid;
  refs.monthInput.value = month;
  route();
}

// ---------- Navigazione ----------
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const parts = path.split('/').filter(Boolean);
  return { parts, query: Object.fromEntries(new URLSearchParams(qs || '')) };
}

export function go(path) {
  const target = '#/' + path;
  if (location.hash === target) route();
  else location.hash = target;
}

async function route() {
  const { parts, query } = parseHash();
  const page = PAGES.find(p => p.path === (parts[0] || '')) || PAGES[0];
  const token = ++app.renderToken;
  for (const link of refs.nav.querySelectorAll('.nav-link')) {
    link.toggleAttribute('aria-current', link.dataset.page === page.id);
    if (link.dataset.page === page.id) link.setAttribute('aria-current', 'page');
  }
  refs.title.textContent = page.label;
  document.title = `${page.label} · NefroCenter WR`;
  const ctx = page.context || [];
  refs.centerSelect.classList.toggle('hidden', !ctx.includes('center'));
  refs.monthBox.classList.toggle('hidden', !ctx.includes('month'));
  refs.context.classList.toggle('hidden', !ctx.length);
  toggleHelp(false);
  app.current = page;
  if (page.cap && !app.can(page.cap)) {
    clear(refs.content, h('div', { class: 'alert warn' }, 'Questa pagina non è disponibile per il tuo profilo.'));
    return;
  }
  if (ctx.includes('center') && !app.cid) {
    clear(refs.content, h('div', { class: 'alert info' }, 'Nessuna struttura assegnata al tuo account: chiedi all’amministratore.'));
    return;
  }
  clear(refs.content, skeleton(5));
  try {
    const module = await import(`./pages/${page.module}.js`);
    const node = await module.render({ app, params: parts.slice(1), query, go, refresh: route, setContext, reloadProfile });
    if (token !== app.renderToken) return;
    clear(refs.content, node);
    refs.content.focus({ preventScroll: true });
  } catch (err) {
    if (token !== app.renderToken) return;
    if (err?.status === 401) return;
    clear(refs.content, h('div', { class: 'alert bad', role: 'alert' }, errorMessage(err)));
    console.error(err);
  }
}

export function rerender() { return route(); }

async function refreshTodoCount() {
  if (!app.can('presenze.vedi')) return;
  try {
    const data = await get(`todo/${app.me.today.slice(0, 7)}`, { background: true });
    const badgeEl = document.getElementById('todo-count');
    if (badgeEl && data.urgent) {
      badgeEl.textContent = String(data.urgent);
      badgeEl.classList.remove('hidden');
      badgeEl.title = `${data.urgent} attività urgenti`;
    }
  } catch { /* il conteggio è solo un aiuto visivo */ }
}

// ---------- Guida contestuale ----------
function toggleHelp(open) {
  const panel = refs.helpPanel;
  if (!panel) return;
  panel.classList.toggle('open', open);
  panel.setAttribute('aria-hidden', String(!open));
  if (!open) return;
  const page = app.current || PAGES[0];
  const help = HELP[page.id] || HELP.home;
  const role = app.me.user.role;
  clear(panel, h('div', { class: 'panel-head' }, h('h2', { text: `Guida · ${page.label}` }),
    button('', { kind: 'ghost icon', ic: 'x', aria: 'Chiudi la guida', onClick: () => toggleHelp(false) })),
  h('div', { class: 'panel-body' }, h('p', { text: help.intro }),
    help.steps?.length ? [h('h3', { text: 'Come si fa' }), h('ol', null, help.steps.map(s => h('li', { text: s })))] : null,
    help.roles?.[role] ? [h('h3', { text: 'Per il tuo profilo' }), h('p', { text: help.roles[role] })] : null,
    help.notes?.length ? [h('h3', { text: 'Da sapere' }), h('ul', null, help.notes.map(s => h('li', { text: s })))] : null,
    h('p', { class: 'small faint' }, 'Guida completa: ', h('a', { href: '#/guida', text: 'Guida e procedure' }))));
  panel.querySelector('button')?.focus();
}

// ---------- Sessione inattiva ----------
let idleTimer = null;
function watchIdle() {
  const reset = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(warnIdle, 13 * 60 * 1000);
  };
  for (const ev of ['click', 'keydown']) document.addEventListener(ev, reset, { passive: true });
  reset();
}

async function warnIdle() {
  if (!app.me || app.demo) return;
  toast('La sessione scade fra due minuti per inattività: fai un clic per restare collegato.');
  const keep = () => get('me').catch(() => null);
  document.addEventListener('click', keep, { once: true });
}

export { app, fmt };
