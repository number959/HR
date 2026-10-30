// Registro presenze: griglia mensile (persona × fascia × giorno) e vista giornaliera; scelta rapida della causale dalla
// casella, modalità «Compilazione rapida» con tavolozza e «Annulla», navigazione del mese, filtro «Solo da completare»,
// riga di contesto e mirino riga/colonna. La finestra completa (orari, sede, festivo, nota) resta in «Dettagli».
import { del, download, get, post, put } from '../api.js';
import { icon } from '../icons.js';
import {
  alertBox, badge, button, card, checkbox, clear, dialog, empty, errorMessage, field, fmt, h, input, segmented, select,
  showErrors, store, table, textarea, toast,
} from '../ui.js';

const KIND_LABEL = { work: 'Lavoro', absence: 'Assenza', rest: 'Riposo' };
const KIND_ORDER = ['work', 'absence', 'rest'];
const narrow = () => window.matchMedia('(max-width: 699px)').matches;

export async function render(ctx) {
  const { app } = ctx;
  const snap = await get(`attendance/${app.cid}/${app.month}`);
  const view = {
    mode: store('att.mode') || (narrow() ? 'day' : 'month'), layer: 'actual', search: '', role: '', todoOnly: false,
    day: defaultDay(snap, app.me.today), quick: { on: false, code: store('att.quickCode') || null, eraser: false },
  };
  const root = h('div');
  // Ridisegno conservando scorrimento del registro e casella attiva: in compilazione rapida si lavora senza perdere il punto.
  const draw = () => {
    closeQuickPick();
    const wrap = root.querySelector('.register-wrap');
    const pos = wrap ? [wrap.scrollLeft, wrap.scrollTop] : null;
    const active = document.activeElement?.closest('.cell')?.dataset;
    const focusKey = active ? `${active.r}|${active.c}` : null;
    clear(root, page(ctx, snap, view, draw, reload));
    const again = root.querySelector('.register-wrap');
    if (again && pos) { again.scrollLeft = pos[0]; again.scrollTop = pos[1]; }
    if (focusKey) root.querySelector(`.cell[data-r="${focusKey.split('|')[0]}"][data-c="${focusKey.split('|')[1]}"]`)?.focus({ preventScroll: true });
  };
  async function reload() {
    Object.assign(snap, await get(`attendance/${app.cid}/${app.month}`));
    draw();
  }
  draw();
  return root;
}

function defaultDay(snap, today) {
  return snap.days.some(d => d.day === today) ? today : snap.days[0].day;
}

function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function shortDate(day) {
  return new Date(day + 'T00:00:00').toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });
}

function canEdit(snap, layer) {
  return snap.editable && (layer === 'actual' || snap.caps['presenze.pianifica']);
}

function allowedCodes(snap, slot) {
  return snap.config.codes.filter(c => c.active && (!c.allowed_slots.length || c.allowed_slots.includes(slot.id)));
}

function stateBadges(snap) {
  const out = [snap.state.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true)];
  out.push(snap.state.verified ? badge('Calendario verificato', 'ok') : badge('Calendario da verificare', 'warn'));
  if (snap.approval.enabled) out.push(badge(`Approvazione: ${snap.approval.label}`, snap.approval.frozen ? 'brand' : ''));
  out.push(badge(`Parametri v${snap.state.rules_version}`, snap.rules_outdated ? 'warn' : ''));
  return out;
}

// Giorni fino a oggi senza alcuna registrazione a consuntivo in nessuna fascia: è ciò che resta da compilare.
function missingDays(snap, person, today) {
  const done = new Set(snap.entries.filter(e => e.person_id === person.id && e.layer === 'actual').map(e => e.day));
  return snap.days.filter(d => d.day <= today && !done.has(d.day)).map(d => d.day);
}

function page(ctx, snap, view, draw, reload) {
  const { app } = ctx;
  const caps = snap.caps;
  const today = app.me.today;
  const editable = canEdit(snap, view.layer);
  const missing = view.layer === 'actual' ? Object.fromEntries(snap.people.map(p => [p.id, missingDays(snap, p, today)])) : {};
  const people = filtered(snap, view, missing);
  const todoTotal = Object.values(missing).reduce((n, list) => n + list.length, 0);
  const goToday = () => {
    const current = today.slice(0, 7);
    if (current !== snap.month) return ctx.setContext(app.cid, current);
    if (view.mode === 'day') { view.day = today; draw(); return; }
    scrollToToday(document);
  };
  const monthNav = h('div', { class: 'month-nav', role: 'group', 'aria-label': 'Mese del registro' },
    button('', { kind: 'icon', ic: 'chevronLeft', aria: 'Mese precedente', onClick: () => ctx.setContext(app.cid, shiftMonth(snap.month, -1)) }),
    h('strong', { class: 'month-label', text: fmt.month(snap.month) }),
    button('', { kind: 'icon', ic: 'chevronRight', aria: 'Mese successivo', onClick: () => ctx.setContext(app.cid, shiftMonth(snap.month, 1)) }),
    button('Oggi', { small: true, ic: 'calendar', title: 'Vai al giorno di oggi', onClick: goToday,
      disabled: today.slice(0, 7) === snap.month && view.mode === 'day' && view.day === today }));
  const actions = [
    segmented([{ id: 'month', label: 'Mese' }, { id: 'day', label: 'Giorno' }], view.mode, m => { view.mode = m; store('att.mode', m); draw(); }, 'Vista'),
    segmented([{ id: 'actual', label: 'Consuntivo' }, { id: 'planned', label: 'Pianificato' }], view.layer, l => { view.layer = l; view.todoOnly = false; draw(); }, 'Registro'),
  ];
  if (editable) {
    const quickBtn = button('Compilazione rapida', { kind: view.quick.on ? 'primary' : '', ic: 'sparkle', title: 'Scegli una causale e compila più caselle con un tocco',
      onClick: () => { view.quick.on = !view.quick.on; draw(); } });
    quickBtn.setAttribute('aria-pressed', String(view.quick.on));
    actions.push(quickBtn);
  }
  if (caps['presenze.anagrafica']) actions.push(button('Persone', { ic: 'users', onClick: () => peopleDialog(snap, reload) }));
  if (caps['presenze.esporta']) actions.push(button('Esporta', { ic: 'download', onClick: () => exportDialog(app, snap) }));
  const summaryParts = [
    view.layer === 'actual' ? 'Consuntivo' : 'Pianificato',
    view.mode === 'month' ? 'griglia del mese' : `vista giornaliera, ${fmt.dateLong(view.day)}`,
    `${people.length} ${people.length === 1 ? 'persona' : 'persone'}${view.role ? ` (${view.role})` : ''}${view.search ? ', ricerca attiva' : ''}${view.todoOnly ? ', solo da completare' : ''}`,
    view.layer === 'actual' && todoTotal ? `${todoTotal} ${todoTotal === 1 ? 'giorno da registrare' : 'giorni da registrare'} fino a oggi` : null,
    view.quick.on ? 'compilazione rapida attiva' : null,
  ].filter(Boolean);
  const head = h('div', { class: 'page-head' }, h('div', null,
    h('div', { class: 'eyebrow', text: 'Registro presenze' }), h('h1', { text: `${snap.center.name} · ${fmt.month(snap.month)}` }),
    monthNav,
    h('p', { class: 'view-summary' }, h('strong', { text: 'Stai vedendo: ' }), summaryParts.join(' · ')),
    h('div', { class: 'row' }, stateBadges(snap))), h('div', { class: 'page-actions' }, actions));
  const alerts = alertsBlock(snap);
  const notice = !snap.editable && caps['presenze.compila']
    ? alertBox(snap.state.closed ? 'Il mese è chiuso: per correggerlo serve la riapertura motivata del responsabile.'
      : 'Il mese è inviato o approvato: le modifiche richiedono la restituzione dalla pagina Approvazioni.', 'warn')
    : null;
  const todoToggle = view.layer === 'actual' && (editable || todoTotal)
    ? h('button', { class: 'btn small toggle', type: 'button', 'aria-pressed': String(view.todoOnly), title: 'Mostra solo le persone con giorni passati senza registrazione',
      on: { click: () => { view.todoOnly = !view.todoOnly; draw(); } } }, icon('checks'), `Solo da completare${todoTotal ? ` (${Object.values(missing).filter(l => l.length).length})` : ''}`)
    : null;
  const toolbar = h('div', { class: 'row' },
    h('input', { type: 'search', placeholder: 'Cerca persona o matricola', value: view.search, 'aria-label': 'Cerca persona',
      on: { input: e => { view.search = e.target.value; draw(); requestAnimationFrame(() => { const s = document.querySelector('input[type="search"]'); if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); } }); } } }),
    h('select', { 'aria-label': 'Ruolo', on: { change: e => { view.role = e.target.value; draw(); } } },
      h('option', { value: '', text: 'Tutti i ruoli' }), snap.config.roles.map(r => h('option', { value: r, selected: r === view.role, text: r }))),
    todoToggle);
  const layerLabel = view.layer === 'actual' ? 'Consuntivo' : 'Pianificato';
  const title = view.mode === 'month' ? `${layerLabel} di ${fmt.month(snap.month)}` : `${layerLabel} · ${fmt.dateLong(view.day)}`;
  const subtitle = view.mode === 'month'
    ? (editable ? 'Una riga per persona e fascia, una colonna per giorno. Tocca una casella per scegliere la causale; «Dettagli» per orari, sede e nota.'
      : 'Una riga per persona e fascia, una colonna per giorno. Tocca una casella per vedere la registrazione.')
    : (editable ? 'Le persone del giorno scelto con un pulsante per ogni fascia: toccalo per scegliere la causale.'
      : 'Le persone del giorno scelto con un pulsante per ogni fascia.');
  const legendBox = h('details', { class: 'legend-box', open: narrow() ? undefined : true }, h('summary', { text: 'Legenda: causali e segni' }), legend(snap));
  const body = view.mode === 'month' ? monthGrid(ctx, snap, view, people, missing, reload, draw) : dayView(ctx, snap, view, people, reload, draw);
  const registerCard = card(title, { subtitle, actions: [toolbar], flush: true },
    view.quick.on && editable ? quickBar(snap, view, draw) : null, legendBox,
    people.length ? body : empty('Nessuna persona', view.todoOnly ? 'Nessun giorno da registrare per le persone filtrate: tutto compilato fino a oggi.'
      : snap.people.length ? 'Nessuna persona corrisponde ai filtri.' : 'Aggiungi le persone del registro con il pulsante «Persone».'));
  if (view.quick.on && editable) registerCard.querySelector('.card-head h2')?.append(' ', badge('Compilazione rapida attiva', 'brand'));
  return h('div', null, head, alerts, notice ? h('div', { class: 'alerts' }, notice) : null, registerCard, summaryCard(snap));
}

function filtered(snap, view, missing) {
  const q = view.search.trim().toLowerCase();
  return snap.people.filter(p => (p.active || snap.entries.some(e => e.person_id === p.id))
    && (!view.role || p.role === view.role)
    && (!q || `${p.name} ${p.registration}`.toLowerCase().includes(q))
    && (!view.todoOnly || (missing[p.id] || []).length));
}

function alertsBlock(snap) {
  if (!snap.alerts.length) return null;
  const tone = { warning: 'warn', info: 'info' };
  const shown = snap.alerts.slice(0, 3);
  const box = h('div', { class: 'alerts' }, shown.map(a => alertBox(a.text, tone[a.level] || 'info')));
  if (snap.alerts.length > 3) {
    box.append(h('button', { class: 'btn ghost small', type: 'button', text: `Mostra tutti gli avvisi (${snap.alerts.length})`, on: { click: e => {
      e.target.replaceWith(...snap.alerts.slice(3).map(a => alertBox(a.text, tone[a.level] || 'info')));
    } } }));
  }
  return box;
}

function legend(snap) {
  const codes = snap.config.codes.filter(c => c.active);
  return h('div', { class: 'legend' }, codes.slice(0, 18).map(c => h('span', null,
    h('span', { class: 'code', vars: { '--c': c.color }, text: c.id }), c.label)),
  h('span', null, h('span', { class: 'code planned', text: 'm' }), 'pianificato'),
  h('span', null, h('span', { class: 'code missing', text: 'm' }), 'senza orari'),
  h('span', null, h('span', { class: 'code external', text: 'm' }), 'fuori sede'),
  h('span', null, h('span', { class: 'code festive', text: 'm' }), 'festivo'),
  h('span', null, h('span', { class: 'code todo-sample', text: ' ' }), 'giorno passato senza registrazione'));
}

function index(snap) {
  const map = new Map();
  for (const e of snap.entries) map.set(`${e.person_id}|${e.day}|${e.slot}|${e.layer}`, e);
  return map;
}

function chip(snap, entry, planned = false) {
  const code = snap.config.codes.find(c => c.id === entry.code);
  const cls = ['code'];
  if (planned) cls.push('planned');
  if (entry.kind === 'work' && !entry.start) cls.push('missing');
  if (entry.site) cls.push('external');
  if (entry.holiday) cls.push('festive');
  if (entry.review) cls.push('review');
  return h('span', { class: cls.join(' '), vars: { '--c': code?.color || 'var(--work)' }, text: entry.code });
}

function describe(snap, person, day, slot, entry) {
  const slotLabel = snap.config.slots.find(s => s.id === slot)?.label || slot;
  let text = `${person.name}, ${fmt.dateLong(day)}, ${slotLabel}`;
  if (entry) text += `: ${entry.label}${entry.start ? ` ${entry.start}–${entry.end}` : ''}`;
  else text += ': vuota';
  return text;
}

function scrollToToday(scope) {
  const wrap = scope.querySelector('.register-wrap');
  const th = wrap?.querySelector('thead th.today');
  if (!wrap || !th) return;
  const fixed = (wrap.querySelector('.name-cell')?.offsetWidth || 0) + (wrap.querySelector('.slot-cell')?.offsetWidth || 0);
  wrap.scrollTo({ left: Math.max(0, th.offsetLeft - fixed - 12), behavior: 'smooth' });
  th.classList.add('flash');
  setTimeout(() => th.classList.remove('flash'), 1600);
}

// ---------- Griglia del mese ----------
function monthGrid(ctx, snap, view, people, missing, reload, draw) {
  const map = index(snap);
  const slots = snap.config.slots.filter(s => s.active);
  const summary = Object.fromEntries(snap.summary.map(r => [r.person_id, r]));
  const today = ctx.app.me.today;
  const editable = canEdit(snap, view.layer);
  const headRow = h('tr', null, h('th', { class: 'sticky name-cell', scope: 'col', text: 'Persona' }), h('th', { class: 'slot-cell', scope: 'col', text: 'Fascia' }),
    snap.days.map((d, c) => {
      const isToday = d.day === today;
      return h('th', { scope: 'col', dataset: { c: String(c) }, class: [d.weekday === 6 ? 'weekend' : '', d.holiday ? 'holiday' : '', isToday ? 'today' : ''].join(' ').trim() || null,
        title: fmt.dateLong(d.day) + (d.holiday ? ' · festivo' : '') + (isToday ? ' · oggi' : '') },
      h('span', { class: 'day-num', text: String(Number(d.day.slice(8))) }), h('span', { class: 'wd', text: isToday ? 'oggi' : d.short }));
    }),
    h('th', { scope: 'col', text: 'Turni' }), h('th', { scope: 'col', text: 'Ore' }));
  const rows = [];
  let r = 0;
  for (const person of people) {
    const todo = new Set(missing[person.id] || []);
    slots.forEach((slot, i) => {
      const tr = h('tr', { class: i === 0 ? 'first-slot' : null, dataset: { person: person.id } });
      if (i === 0) {
        tr.append(h('th', { class: 'sticky name-cell', scope: 'row', rowspan: String(slots.length), dataset: { person: person.id } },
          h('strong', { text: person.name }), h('span', { text: [person.role, person.registration].filter(Boolean).join(' · ') }),
          todo.size ? h('span', { class: 'todo-count', text: `${todo.size} ${todo.size === 1 ? 'giorno da registrare' : 'giorni da registrare'}` }) : null));
      }
      tr.append(h('td', { class: 'slot-cell', title: `${slot.label} ${slot.start}–${slot.end}`, text: slot.id }));
      snap.days.forEach((d, c) => {
        const actual = map.get(`${person.id}|${d.day}|${slot.id}|${view.layer}`);
        const plannedOnly = view.layer === 'actual' && !actual ? map.get(`${person.id}|${d.day}|${slot.id}|planned`) : null;
        const entry = actual || null;
        const clickable = snap.editable || entry;
        const label = describe(snap, person, d.day, slot.id, entry);
        const cell = h('button', { class: `cell${!entry && todo.has(d.day) && editable ? ' todo' : ''}`, type: 'button', disabled: !clickable, dataset: { r: String(r), c: String(c) },
          'aria-label': label, title: label,
          on: { click: e => onCell(ctx, snap, view, person, d.day, slot, entry, plannedOnly, reload, e.currentTarget) } },
        entry ? chip(snap, entry) : plannedOnly ? chip(snap, plannedOnly, true) : null);
        tr.append(h('td', { class: d.weekday === 6 ? 'weekend' : null }, cell));
      });
      if (i === 0) {
        const s = summary[person.id] || {};
        tr.append(h('td', { class: 'total', rowspan: String(slots.length), text: fmt.number(s.shifts || 0) }),
          h('td', { class: 'total', rowspan: String(slots.length), text: fmt.minutes(s.minutes || 0) }));
      }
      rows.push(tr);
      r += 1;
    });
  }
  const quickColor = view.quick.on ? (snap.config.codes.find(c => c.id === view.quick.code)?.color || null) : null;
  const tableEl = h('table', { class: `register${view.quick.on ? ' quick' : ''}`, 'aria-label': 'Registro del mese', vars: quickColor ? { '--quick-c': quickColor } : null },
    h('thead', null, headRow), h('tbody', null, rows));
  tableEl.addEventListener('keydown', e => gridKeys(e, tableEl, snap, view, draw));
  crosshair(tableEl);
  return h('div', { class: 'register-wrap' }, tableEl);
}

// Mirino: al passaggio o al focus su una casella si evidenziano il giorno in alto e la persona a sinistra.
function crosshair(tableEl) {
  let current = [];
  const clearAll = () => { for (const el of current) el.classList.remove('hl'); current = []; };
  const mark = cell => {
    clearAll();
    if (!cell) return;
    const tr = cell.closest('tr');
    const th = tableEl.querySelector(`thead th[data-c="${cell.dataset.c}"]`);
    const name = tableEl.querySelector(`th.name-cell[data-person="${tr?.dataset.person}"]`);
    const slot = tr?.querySelector('.slot-cell');
    current = [th, name, slot].filter(Boolean);
    for (const el of current) el.classList.add('hl');
  };
  tableEl.addEventListener('mouseover', e => mark(e.target.closest('.cell')));
  tableEl.addEventListener('mouseleave', clearAll);
  tableEl.addEventListener('focusin', e => mark(e.target.closest('.cell')));
  tableEl.addEventListener('focusout', e => { if (!tableEl.contains(e.relatedTarget)) clearAll(); });
}

let typeBuffer = '';
let typeTimer = null;

function gridKeys(e, tableEl, snap, view, draw) {
  const cell = e.target.closest('.cell');
  if (!cell) return;
  const delta = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }[e.key];
  if (delta) {
    e.preventDefault();
    tableEl.querySelector(`.cell[data-r="${Number(cell.dataset.r) + delta[0]}"][data-c="${Number(cell.dataset.c) + delta[1]}"]`)?.focus();
    return;
  }
  if (!view.quick.on) return;
  if (e.key === 'Escape') { view.quick.on = false; draw(); return; }
  if (e.key === 'Backspace' || e.key === 'Delete') {
    if (snap.caps['presenze.elimina']) { e.preventDefault(); view.quick.eraser = true; draw(); }
    return;
  }
  if (e.key.length === 1 && /[a-z0-9]/i.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    typeBuffer += e.key.toLowerCase();
    clearTimeout(typeTimer);
    const codes = snap.config.codes.filter(c => c.active);
    const exact = codes.find(c => c.id.toLowerCase() === typeBuffer);
    const prefix = codes.filter(c => c.id.toLowerCase().startsWith(typeBuffer));
    const pick = code => { typeBuffer = ''; view.quick.code = code.id; view.quick.eraser = false; store('att.quickCode', code.id); draw(); };
    if (exact && prefix.length === 1) pick(exact);
    else if (exact) typeTimer = setTimeout(() => pick(exact), 600);
    else if (!prefix.length) typeBuffer = '';
    else typeTimer = setTimeout(() => { typeBuffer = ''; }, 600);
  }
}

// ---------- Vista giornaliera ----------
function dayView(ctx, snap, view, people, reload, draw) {
  const map = index(snap);
  const slots = snap.config.slots.filter(s => s.active);
  const pos = snap.days.findIndex(d => d.day === view.day);
  const today = ctx.app.me.today;
  const info = snap.days[pos];
  const nav = h('div', { class: 'day-nav card-body' },
    button('', { kind: 'icon', ic: 'chevronLeft', aria: 'Giorno precedente', disabled: pos <= 0, onClick: () => { view.day = snap.days[pos - 1].day; draw(); } }),
    h('select', { 'aria-label': 'Giorno', on: { change: e => { view.day = e.target.value; draw(); } } },
      snap.days.map(d => h('option', { value: d.day, selected: d.day === view.day, text: (narrow() ? shortDate(d.day) : fmt.dateLong(d.day)) + (d.holiday ? ' · festivo' : '') + (d.day === today ? ' · oggi' : '') }))),
    button('', { kind: 'icon', ic: 'chevronRight', aria: 'Giorno successivo', disabled: pos >= snap.days.length - 1, onClick: () => { view.day = snap.days[pos + 1].day; draw(); } }));
  const headline = h('div', { class: 'day-head card-body' },
    h('h3', null, fmt.dateLong(view.day), view.day === today ? [' ', badge('oggi', 'brand')] : null, info?.holiday ? [' ', badge('festivo', 'warn')] : null),
    snap.days.some(d => d.day === today) && view.day !== today ? button('Oggi', { small: true, ic: 'calendar', onClick: () => { view.day = today; draw(); } }) : null);
  const list = h('div', { class: 'day-list card-body' }, people.map(person => h('div', { class: 'day-person' },
    h('div', null, h('strong', { text: person.name }), h('div', { class: 'small faint', text: person.role })),
    h('div', { class: 'day-slots' }, slots.map(slot => {
      const entry = map.get(`${person.id}|${view.day}|${slot.id}|${view.layer}`);
      const planned = view.layer === 'actual' && !entry ? map.get(`${person.id}|${view.day}|${slot.id}|planned`) : null;
      const label = describe(snap, person, view.day, slot.id, entry);
      return h('button', { class: 'btn small', type: 'button', disabled: !snap.editable && !entry, 'aria-label': label, title: label,
        on: { click: e => onCell(ctx, snap, view, person, view.day, slot, entry, planned, reload, e.currentTarget) } },
      entry ? chip(snap, entry) : planned ? chip(snap, planned, true) : h('span', { class: 'faint', text: `+ ${slot.label}` }));
    })))));
  return h('div', null, nav, headline, list);
}

// ---------- Scelta della causale: riquadro rapido, compilazione rapida, finestra completa ----------
function onCell(ctx, snap, view, person, day, slot, entry, planned, reload, anchor) {
  if (!canEdit(snap, view.layer)) return openEntry(ctx, snap, person, day, slot, view.layer, entry, planned, reload);
  if (view.quick.on) return quickApply(ctx, snap, view, person, day, slot, entry, reload);
  return quickPick(ctx, snap, view, person, day, slot, entry, planned, reload, anchor);
}

async function saveCode(ctx, snap, person, day, slot, layer, code, entry) {
  const body = { person_id: person.id, day, slot: slot.id, layer, code: code.id };
  if (entry) Object.assign(body, { id: entry.id, version: entry.version, note: entry.note || '' });
  return post(`attendance/${ctx.app.cid}/${snap.month}/entries`, body);
}

// Corpo per ricreare o riportare una registrazione com'era (solo i campi che l'utente può impostare).
function restoreBody(snap, previous, saved) {
  const caps = snap.caps;
  const body = { person_id: previous.person_id, day: previous.day, slot: previous.slot, layer: previous.layer, code: previous.code, note: previous.note || '' };
  if (saved) Object.assign(body, { id: saved.id, version: saved.version });
  if (caps['presenze.orari'] && previous.kind === 'work') Object.assign(body, { start: previous.start, end: previous.end, pause: previous.pause, overnight: previous.overnight });
  if (caps['presenze.sede']) body.site = previous.site || '';
  if (caps['presenze.festivo']) body.holiday = previous.holiday;
  return body;
}

function announceSaved(ctx, snap, person, day, slot, code, previous, saved, reload) {
  const text = `${previous ? 'Corretto' : 'Registrato'} ${code.id} · ${code.label} per ${person.name}, ${shortDate(day)}, ${slot.label}.`;
  toast(text, 'ok', { action: { label: 'Annulla', onClick: async () => {
    try {
      if (previous) await post(`attendance/${ctx.app.cid}/${snap.month}/entries`, restoreBody(snap, previous, saved.entry));
      else await del(`attendance/${ctx.app.cid}/${snap.month}/entries/${saved.entry.id}`, { version: saved.entry.version });
      toast('Annullato.', '');
      await reload();
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } } });
  if (saved.warnings?.length) toast(saved.warnings.join(' '), 'warn');
}

async function deleteEntry(ctx, snap, person, slot, entry, reload) {
  await del(`attendance/${ctx.app.cid}/${snap.month}/entries/${entry.id}`, { version: entry.version });
  toast(`Eliminato ${entry.code} per ${person.name}, ${shortDate(entry.day)}, ${slot.label}.`, 'ok', { action: { label: 'Annulla', onClick: async () => {
    try {
      await post(`attendance/${ctx.app.cid}/${snap.month}/entries`, restoreBody(snap, entry, null));
      toast('Registrazione ripristinata.', '');
      await reload();
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } } });
}

function canDelete(snap, entry) {
  return Boolean(entry) && snap.editable && snap.caps['presenze.elimina'] && (entry.layer === 'actual' || snap.caps['presenze.pianifica']);
}

async function quickApply(ctx, snap, view, person, day, slot, entry, reload) {
  if (view.quick.eraser) {
    if (!entry) return toast('Casella già vuota.');
    if (!canDelete(snap, entry)) return toast('Eliminazione non consentita per questa registrazione.', 'warn');
    try { await deleteEntry(ctx, snap, person, slot, entry, reload); await reload(); } catch (err) { toast(errorMessage(err), 'bad'); }
    return;
  }
  const code = snap.config.codes.find(c => c.id === view.quick.code && c.active);
  if (!code) return toast('Scegli prima una causale nella tavolozza in alto.', 'warn');
  if (code.allowed_slots.length && !code.allowed_slots.includes(slot.id)) return toast(`La causale ${code.id} non è prevista nella fascia ${slot.label}.`, 'warn');
  if (entry && entry.code === code.id) return toast(`Già registrato ${code.id} in questa casella.`);
  try {
    const saved = await saveCode(ctx, snap, person, day, slot, view.layer, code, entry);
    announceSaved(ctx, snap, person, day, slot, code, entry, saved, reload);
    await reload();
  } catch (err) { toast(errorMessage(err), 'bad'); }
}

function quickBar(snap, view, draw) {
  const codes = snap.config.codes.filter(c => c.active);
  const chips = codes.map(c => h('button', { class: 'quick-code', type: 'button', 'aria-pressed': String(!view.quick.eraser && view.quick.code === c.id), title: c.label, dataset: { code: c.id },
    on: { click: () => { view.quick.code = c.id; view.quick.eraser = false; store('att.quickCode', c.id); draw(); } } },
  h('span', { class: 'code', vars: { '--c': c.color }, text: c.id }), h('span', { class: 'quick-label', text: c.label })));
  const eraser = snap.caps['presenze.elimina']
    ? h('button', { class: 'quick-code eraser', type: 'button', 'aria-pressed': String(view.quick.eraser), title: 'Svuota le caselle che tocchi',
      on: { click: () => { view.quick.eraser = !view.quick.eraser; draw(); } } }, icon('trash'), h('span', { class: 'quick-label', text: 'Gomma' }))
    : null;
  const exit = button('Esci', { small: true, ic: 'x', onClick: () => { view.quick.on = false; draw(); } });
  const chosen = view.quick.eraser ? 'Gomma attiva: tocca una casella per svuotarla.'
    : view.quick.code ? `Causale scelta: ${view.quick.code}. Tocca le caselle da compilare: ogni tocco salva subito (puoi annullare dall'avviso).`
      : 'Scegli una causale, poi tocca le caselle da compilare: ogni tocco salva subito.';
  return h('div', { class: 'quick-bar', role: 'toolbar', 'aria-label': 'Compilazione rapida' },
    h('div', { class: 'quick-options' }, chips, eraser, exit),
    h('p', { class: 'small muted', text: `${chosen} Da tastiera: digita il codice per sceglierlo, Invio sulla casella per registrare, Esc per uscire.` }));
}

let openPick = null;
function closeQuickPick() {
  if (openPick) { const close = openPick; openPick = null; close(); }
}

function quickPick(ctx, snap, view, person, day, slot, entry, planned, reload, anchor) {
  closeQuickPick();
  const codes = allowedCodes(snap, slot);
  const sheet = narrow();
  const slotLabel = `${slot.label} (${slot.start}–${slot.end})`;
  const box = h('div', { class: `quick-pick${sheet ? ' sheet' : ''}`, role: 'dialog', 'aria-modal': String(sheet), 'aria-label': `Scegli la causale per ${person.name}, ${fmt.dateLong(day)}, ${slot.label}` });
  const scrim = sheet ? h('div', { class: 'quick-scrim' }) : null;
  const error = h('div', { class: 'alert bad quick-error hidden' }, icon('alert'), h('div'));
  let busy = false;
  const cleanup = [];
  const close = (refocus = true) => {
    for (const fn of cleanup) fn();
    box.remove();
    scrim?.remove();
    if (openPick === close) openPick = null;
    if (refocus) anchor?.focus({ preventScroll: true });
  };
  const fail = err => { error.lastChild.textContent = errorMessage(err); error.classList.remove('hidden'); busy = false; };
  const choose = async code => {
    if (busy) return;
    if (entry && entry.code === code.id) return close();
    busy = true;
    try {
      const saved = await saveCode(ctx, snap, person, day, slot, view.layer, code, entry);
      close();
      announceSaved(ctx, snap, person, day, slot, code, entry, saved, reload);
      await reload();
    } catch (err) { fail(err); }
  };
  const codeButton = c => h('button', { class: 'quick-code', type: 'button', 'aria-pressed': String(entry?.code === c.id), dataset: { code: c.id }, on: { click: () => choose(c) } },
    h('span', { class: 'code', vars: { '--c': c.color }, text: c.id }), h('span', { class: 'quick-label', text: c.label }), entry?.code === c.id ? icon('check') : null);
  const groups = codes.length > 6
    ? KIND_ORDER.map(kind => [KIND_LABEL[kind], codes.filter(c => c.kind === kind)]).filter(([, list]) => list.length)
    : [[null, codes]];
  const options = h('div', { class: 'quick-codes' }, groups.map(([title, list]) => h('div', { class: 'quick-group' },
    title ? h('div', { class: 'quick-group-title', text: title }) : null, h('div', { class: 'quick-options' }, list.map(codeButton)))));
  const details = button('Dettagli e orari…', { small: true, ic: 'edit', onClick: () => { close(false); openEntry(ctx, snap, person, day, slot, view.layer, entry, planned, reload); } });
  let remove = null;
  if (canDelete(snap, entry)) {
    remove = button('Elimina', { small: true, kind: 'ghost', ic: 'trash', onClick: async () => {
      if (!remove.dataset.armed) { remove.dataset.armed = '1'; remove.classList.add('danger'); remove.classList.remove('ghost'); remove.lastChild.textContent = 'Conferma eliminazione'; return; }
      if (busy) return;
      busy = true;
      try { await deleteEntry(ctx, snap, person, slot, entry, reload); close(); await reload(); } catch (err) { fail(err); }
    } });
  }
  box.append(
    h('div', { class: 'quick-head' }, h('div', null, h('strong', { text: person.name }), h('span', { class: 'small muted', text: `${fmt.dateLong(day)} · ${slotLabel}` }),
      planned && !entry ? h('span', { class: 'small', text: `Pianificato: ${planned.label}. Scegliendo una causale registri il consuntivo.` }) : null),
    button('', { kind: 'ghost icon', ic: 'x', aria: 'Chiudi', onClick: () => close() })),
    codes.length ? options : alertBox('Nessuna causale prevista per questa fascia nei parametri della struttura.', 'warn'),
    error,
    h('div', { class: 'quick-foot' }, remove, details));
  // Tastiera: frecce fra le causali, Escape chiude, digitando il codice si sceglie la causale.
  let buffer = '';
  let timer = null;
  box.addEventListener('keydown', e => {
    const buttons = [...box.querySelectorAll('.quick-code')];
    const at = buttons.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (['ArrowRight', 'ArrowDown'].includes(e.key) && buttons.length) { e.preventDefault(); buttons[(at + 1 + buttons.length) % buttons.length].focus(); return; }
    if (['ArrowLeft', 'ArrowUp'].includes(e.key) && buttons.length) { e.preventDefault(); buttons[(at - 1 + buttons.length) % buttons.length].focus(); return; }
    if (e.key.length === 1 && /[a-z0-9]/i.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      buffer += e.key.toLowerCase();
      clearTimeout(timer);
      const exact = codes.find(c => c.id.toLowerCase() === buffer);
      const prefix = codes.filter(c => c.id.toLowerCase().startsWith(buffer));
      if (exact && prefix.length === 1) { buffer = ''; choose(exact); } else if (exact) timer = setTimeout(() => { buffer = ''; choose(exact); }, 600);
      else if (!prefix.length) buffer = ''; else timer = setTimeout(() => { buffer = ''; }, 600);
    }
  });
  if (scrim) {
    scrim.addEventListener('click', () => close());
    document.body.append(scrim);
  }
  document.body.append(box);
  if (!sheet) {
    const rect = anchor.getBoundingClientRect();
    const w = box.offsetWidth;
    const hgt = box.offsetHeight;
    const x = Math.min(Math.max(8, rect.left), window.innerWidth - w - 8);
    let y = rect.bottom + 6;
    if (y + hgt > window.innerHeight - 8) y = Math.max(8, rect.top - hgt - 6);
    box.style.setProperty('--x', `${Math.round(x)}px`);
    box.style.setProperty('--y', `${Math.round(y)}px`);
    const outside = e => { if (!box.contains(e.target) && e.target !== anchor) close(false); };
    const onResize = () => close(false);
    // Lo scorrimento del registro chiude il riquadro, ma non quello che il browser fa da solo subito dopo il tocco
    // (per portare la casella in vista): nei primi istanti si ignora.
    const openedAt = performance.now();
    const onScroll = () => { if (performance.now() - openedAt > 500) close(false); };
    const scroller = anchor.closest('.register-wrap');
    setTimeout(() => document.addEventListener('pointerdown', outside, true), 0);
    window.addEventListener('resize', onResize);
    scroller?.addEventListener('scroll', onScroll);
    cleanup.push(() => document.removeEventListener('pointerdown', outside, true), () => window.removeEventListener('resize', onResize), () => scroller?.removeEventListener('scroll', onScroll));
  }
  openPick = close;
  (box.querySelector('.quick-code[aria-pressed="true"]') || box.querySelector('.quick-code') || details).focus();
}

// ---------- Finestra completa: orari, sede, festivo, nota ----------
async function openEntry(ctx, snap, person, day, slot, layer, entry, planned, reload) {
  const caps = snap.caps;
  const editable = snap.editable && (layer === 'actual' || caps['presenze.pianifica']);
  const codes = allowedCodes(snap, slot);
  const base = entry || planned || null;
  const codeSel = select('code', codes.map(c => [c.id, `${c.id} · ${c.label}`]), base?.code || (codes.find(c => c.id === slot.id)?.id || codes[0]?.id),
    { disabled: !editable });
  const start = input('start', entry?.start ?? slot.start, { type: 'time', disabled: !editable || !caps['presenze.orari'] });
  const end = input('end', entry?.end ?? slot.end, { type: 'time', disabled: !editable || !caps['presenze.orari'] });
  const pause = input('pause', String(entry?.pause ?? slot.pause), { type: 'number', min: '0', step: '5', disabled: !editable || !caps['presenze.orari'] });
  const overnight = checkbox('overnight', entry ? entry.overnight : slot.overnight, 'Uscita il giorno dopo');
  overnight.querySelector('input').disabled = !editable || !caps['presenze.orari'];
  const sites = [['', snap.center.name], ...snap.config.sites.map(s => [s, s])];
  const site = select('site', sites, entry?.site || '', { disabled: !editable || !caps['presenze.sede'] });
  const dayInfo = snap.days.find(d => d.day === day);
  const holiday = checkbox('holiday', entry ? entry.holiday : dayInfo.holiday, 'Turno festivo');
  holiday.querySelector('input').disabled = !editable || !caps['presenze.festivo'];
  const note = textarea('note', entry?.note || '', { max: 2000, rows: 2, disabled: !editable });
  const timeBox = h('fieldset', null, h('legend', { text: 'Orari' }),
    h('div', { class: 'form-grid' }, field('Ingresso', start, { name: 'start' }), field('Uscita', end, { name: 'end' }),
      field('Pausa (minuti)', pause, { name: 'pause' })), overnight,
    !caps['presenze.orari'] ? h('p', { class: 'small faint', text: 'Gli orari seguono la fascia: la modifica è riservata al responsabile (o abilitata nei parametri).' }) : null);
  const syncKind = () => {
    const kind = snap.config.codes.find(c => c.id === codeSel.value)?.kind;
    timeBox.classList.toggle('hidden', kind !== 'work');
  };
  codeSel.addEventListener('change', syncKind);
  syncKind();
  const form = h('form', { class: 'stack' },
    h('p', { class: 'muted' }, `${person.name} · ${fmt.dateLong(day)} · ${slot.label} (${slot.start}–${slot.end})`,
      layer === 'planned' ? h('span', null, ' · ', badge('Pianificato', 'brand')) : null),
    entry?.review ? alertBox(entry.review, 'warn') : null,
    planned && !entry ? alertBox(`Pianificato: ${planned.label}. Salvando registri il consuntivo.`, 'info') : null,
    field('Causale', codeSel, { name: 'code' }), timeBox,
    h('div', { class: 'form-grid' }, field('Sede di lavoro', site, { name: 'site' }), h('div', { class: 'field' }, h('span', { class: 'small faint', text: ' ' }), holiday)),
    field('Nota', note, { name: 'note' }),
    entry ? h('p', { class: 'small faint', text: `Ultima modifica: ${entry.updated_by}, ${fmt.stamp(entry.updated_at)} · parametri v${entry.rules_version}` }) : null);

  const actions = [{ label: editable ? 'Annulla' : 'Chiudi', value: null }];
  if (canDelete(snap, entry)) {
    actions.unshift({ label: 'Elimina', kind: 'danger', onClick: async () => {
      try {
        await deleteEntry(ctx, snap, person, slot, entry, reload);
        return true;
      } catch (err) { toast(errorMessage(err), 'bad'); return false; }
    } });
  }
  if (editable) {
    actions.push({ label: 'Salva', kind: 'primary', onClick: async () => {
      const kind = snap.config.codes.find(c => c.id === codeSel.value)?.kind;
      const body = { person_id: person.id, day, slot: slot.id, layer, code: codeSel.value, note: note.value };
      if (entry) Object.assign(body, { id: entry.id, version: entry.version });
      if (kind === 'work' && caps['presenze.orari']) {
        Object.assign(body, { start: start.value, end: end.value, pause: Number(pause.value || 0), overnight: overnight.querySelector('input').checked });
      }
      if (caps['presenze.sede']) body.site = site.value;
      if (caps['presenze.festivo']) body.holiday = holiday.querySelector('input').checked;
      try {
        const result = await post(`attendance/${ctx.app.cid}/${snap.month}/entries`, body);
        if (result.warnings?.length) toast(result.warnings.join(' '), '');
        else toast('Registrazione salvata.', 'ok');
        return true;
      } catch (err) {
        if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
        return false;
      }
    } });
  }
  const saved = await dialog(entry ? 'Registrazione' : 'Nuova registrazione', form, actions);
  if (saved) await reload();
}

// ---------- Riepilogo ----------
function summaryCard(snap) {
  const causes = [...new Set(snap.summary.flatMap(r => Object.keys(r.causes)))].sort();
  return card('Riepilogo del mese', { subtitle: `${snap.working_days} giorni lavorativi da calendario`, flush: true },
    table([
      { label: 'Persona', render: r => h('div', null, h('strong', { text: r.name }), h('div', { class: 'small faint', text: r.role })) },
      { label: 'Turni', num: true, key: 'shifts' }, { label: 'Giorni', num: true, key: 'days' },
      { label: 'Ore', num: true, render: r => fmt.minutes(r.minutes) },
      { label: 'Senza orari', num: true, render: r => r.missing ? h('span', { class: 'badge warn', text: String(r.missing) }) : '0' },
      { label: 'Assenze', num: true, key: 'absences' }, { label: 'Fuori sede', num: true, key: 'external' },
      { label: 'Festivi', num: true, key: 'festive' },
      { label: 'Da consuntivare', num: true, render: r => r.pending ? h('span', { class: 'badge warn', text: String(r.pending) }) : '0' },
      { label: 'Causali', render: r => causes.filter(c => r.causes[c]).map(c => `${c} ${r.causes[c]}`).join(' · ') || '—' },
    ], snap.summary.filter(r => r.active || r.shifts || r.absences), { empty: 'Nessuna persona nel registro.' }));
}

// ---------- Persone del registro ----------
async function peopleDialog(snap, reload) {
  const list = h('div');
  const drawList = () => clear(list, table([
    { label: 'Persona', render: p => h('div', null, h('strong', { text: p.name }), h('div', { class: 'small faint', text: p.registration || 'senza matricola' })) },
    { label: 'Ruolo', key: 'role' }, { label: 'Stato', render: p => p.active ? badge('Attiva', 'ok') : badge('Non attiva') },
    { label: '', render: p => button('Modifica', { small: true, ic: 'edit', onClick: () => personForm(snap, p, reload) }) },
  ], snap.people));
  drawList();
  await dialog('Persone del registro', h('div', { class: 'stack' },
    h('p', { class: 'muted', text: 'Le persone del registro sono collegate ai fascicoli HR. Per i dati anagrafici completi usa «Persone e fascicoli».' }),
    button('Aggiungi persona', { kind: 'primary', ic: 'plus', onClick: () => personForm(snap, null, reload) }), list),
  [{ label: 'Chiudi', value: null }], { wide: true });
}

async function personForm(snap, person, reload) {
  const name = input('name', person?.name || '', { max: 150 });
  const role = select('role', snap.config.roles, person?.role || snap.config.roles[0]);
  const registration = input('registration', person?.registration || '', { max: 80 });
  const contract = input('contract', person?.contract || '', { max: 150 });
  const active = checkbox('active', person ? person.active : true, 'Abilitata alle presenze');
  const form = h('form', { class: 'form-grid' }, field('Nome e cognome', name, { name: 'name', required: true, wide: true }),
    field('Ruolo', role, { name: 'role' }), field('Matricola', registration, { name: 'registration' }),
    field('Contratto', contract, { name: 'contract', wide: true }), h('div', { class: 'wide' }, active));
  const ok = await dialog(person ? 'Modifica persona' : 'Nuova persona', form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    const body = { name: name.value, role: role.value, registration: registration.value, contract: contract.value, active: active.querySelector('input').checked };
    try {
      if (person) await put(`centers/${snap.center.id}/people/${person.id}`, { ...body, version: person.version });
      else await post(`centers/${snap.center.id}/people`, body);
      toast('Persona salvata.', 'ok');
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) {
    document.querySelector('dialog[open]')?.close();
    await reload();
  }
}

async function exportDialog(app, snap) {
  const xlsx = new URLSearchParams({ kind: 'presenze_centro', from: snap.month, to: snap.month, cid: app.cid, layer: 'actual' });
  await dialog('Esporta il registro', h('div', { class: 'stack' },
    h('p', { class: 'muted', text: 'Excel: la griglia del mese con totali per persona, dettaglio delle registrazioni e legenda (fogli separati). CSV: riepilogo con una riga per persona oppure dettaglio con una riga per registrazione. Il foglio nel formato del vecchio modello è nella pagina Esportazioni.' })),
  [{ label: 'Annulla', value: null },
    { label: 'CSV dettaglio', onClick: async () => { await download(`attendance/${app.cid}/${snap.month}/export.csv?detail=1`, 'presenze.csv'); return true; } },
    { label: 'CSV riepilogo', onClick: async () => { await download(`attendance/${app.cid}/${snap.month}/export.csv`, 'presenze.csv'); return true; } },
    { label: 'Excel', kind: 'primary', onClick: async () => { await download(`exports/xlsx?${xlsx}`, 'registro.xlsx'); return true; } }]);
}

export { chip, KIND_LABEL };
