// Strumenti comuni dell'interfaccia: creazione di elementi, formati italiani, finestre e notifiche.
// Gli elementi si creano sempre come nodi DOM (mai HTML con dati), quindi i testi sono sempre sicuri.
import { icon } from './icons.js';

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') el.className = value;
      else if (key === 'text') el.textContent = value;
      else if (key === 'on') for (const [ev, fn] of Object.entries(value)) el.addEventListener(ev, fn);
      else if (key === 'dataset') Object.assign(el.dataset, value);
      else if (key === 'vars') for (const [name, v] of Object.entries(value)) el.style.setProperty(name, v);
      else if (key === 'value') el.value = value;
      else if (key === 'checked') el.checked = Boolean(value);
      else if (key === 'selected') el.selected = Boolean(value);
      else if (key === 'disabled') el.disabled = Boolean(value);
      else if (value === true) el.setAttribute(key, '');
      else el.setAttribute(key, value);
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === '') continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

// ---------- Formati ----------
const MONTHS = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre',
  'novembre', 'dicembre'];
const DAYS = ['domenica', 'lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato'];
export const fmt = {
  date(iso) {
    if (!iso) return '—';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
  },
  dateLong(iso) {
    if (!iso) return '—';
    const d = new Date(iso.slice(0, 10) + 'T12:00:00');
    return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  },
  stamp(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  },
  month(value) {
    if (!value) return '';
    const [y, m] = value.split('-');
    return `${MONTHS[Number(m) - 1]} ${y}`;
  },
  minutes(n) {
    if (n === null || n === undefined) return '—';
    const sign = n < 0 ? '−' : '';
    n = Math.abs(n);
    return `${sign}${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  },
  hours(n) {
    if (n === null || n === undefined) return '—';
    return (n / 60).toLocaleString('it-IT', { maximumFractionDigits: 1 }) + ' h';
  },
  number(n, digits = 0) {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    return Number(n).toLocaleString('it-IT', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  },
  money(n) {
    if (n === null || n === undefined) return '—';
    return Number(n).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  },
  bytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toLocaleString('it-IT', { maximumFractionDigits: 0 })} KB`;
    return `${(n / 1024 / 1024).toLocaleString('it-IT', { maximumFractionDigits: 1 })} MB`;
  },
  initials(name) {
    return String(name || '?').split(/\s+/).filter(p => /\p{L}/u.test(p)).slice(0, 2).map(p => p[0].toUpperCase()).join('') || '?';
  },
};

export function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function shiftMonth(month, delta) {
  let [y, m] = month.split('-').map(Number);
  m += delta;
  while (m < 1) { m += 12; y -= 1; }
  while (m > 12) { m -= 12; y += 1; }
  return `${y}-${String(m).padStart(2, '0')}`;
}

// ---------- Componenti ----------
export function badge(text, tone = '', dot = false) {
  return h('span', { class: `badge ${tone} ${dot ? 'dot' : ''}`.trim(), text });
}

export function button(label, opts = {}) {
  const { kind = '', ic, onClick, title, small, type = 'button', disabled } = opts;
  return h('button', {
    class: `btn ${kind} ${small ? 'small' : ''}`.trim(), type, title, disabled, 'aria-label': opts.aria || null,
    on: onClick ? { click: onClick } : null,
  }, ic ? icon(ic) : null, label);
}

export function card(title, opts = {}, ...body) {
  const { subtitle, actions, flush, foot, id } = opts;
  const head = title || actions ? h('div', { class: 'card-head' },
    h('div', null, title ? h('h2', { text: title }) : null, subtitle ? h('p', { text: subtitle }) : null),
    actions ? h('div', { class: 'row' }, actions) : null) : null;
  return h('section', { class: 'card', id }, head, h('div', { class: `card-body ${flush ? 'flush' : ''}` }, body),
    foot ? h('div', { class: 'card-foot' }, foot) : null);
}

export function kpi(label, value, foot, tone = '') {
  return h('div', { class: `kpi ${tone ? 'tone-' + tone : ''}` },
    h('div', { class: 'kpi-label', text: label }), h('div', { class: 'kpi-value', text: value }),
    foot ? h('div', { class: 'kpi-foot', text: foot }) : null);
}

export function alertBox(text, tone = 'info', extra) {
  const ic = { info: 'info', warn: 'alert', bad: 'alert', ok: 'check' }[tone] || 'info';
  return h('div', { class: `alert ${tone}`, role: tone === 'bad' ? 'alert' : null }, icon(ic), h('div', null, text, extra || null));
}

export function empty(title, text, action) {
  return h('div', { class: 'empty' }, icon('inbox'), h('h3', { text: title }), text ? h('p', { text }) : null, action || null);
}

export function pageHead(title, opts = {}) {
  const { eyebrow, text, actions } = opts;
  return h('div', { class: 'page-head' },
    h('div', null, eyebrow ? h('div', { class: 'eyebrow', text: eyebrow }) : null, h('h1', { text: title }),
      text ? h('p', { text }) : null),
    actions ? h('div', { class: 'page-actions' }, actions) : null);
}

export function personCell(name, sub) {
  return h('div', { class: 'person' }, h('span', { class: 'avatar', 'aria-hidden': 'true', text: fmt.initials(name) }),
    h('div', null, h('strong', { text: name }), sub ? h('span', { text: sub }) : null));
}

export function table(columns, rows, opts = {}) {
  const { empty: emptyText = 'Nessun dato.', onRow, caption, rowClass } = opts;
  if (!rows.length) return empty(emptyText);
  const thead = h('thead', null, h('tr', null, columns.map(c => h('th', { class: c.num ? 'num' : c.class, scope: 'col', text: c.label }))));
  const tbody = h('tbody', null, rows.map(row => {
    const tr = h('tr', { class: [onRow ? 'clickable' : '', rowClass ? rowClass(row) : ''].join(' ').trim() || null },
      columns.map(c => {
        const value = c.render ? c.render(row) : row[c.key];
        return h('td', { class: c.num ? 'num' : c.class }, value instanceof Node ? value : (value ?? '—'));
      }));
    if (onRow) {
      tr.tabIndex = 0;
      tr.addEventListener('click', e => { if (!e.target.closest('button, a, input, select')) onRow(row); });
      tr.addEventListener('keydown', e => { if (e.key === 'Enter') onRow(row); });
    }
    return tr;
  }));
  return h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, caption ? h('caption', { class: 'sr-only', text: caption }) : null,
    thead, tbody));
}

export function tabs(items, active, onChange) {
  const bar = h('div', { class: 'tabs', role: 'tablist' });
  for (const item of items) {
    bar.append(h('button', {
      class: 'tab', role: 'tab', type: 'button', 'aria-selected': String(item.id === active),
      on: { click: () => onChange(item.id) },
    }, item.label, item.count ? h('span', { class: 'badge', text: String(item.count) }) : null));
  }
  return bar;
}

export function segmented(options, active, onChange, label) {
  return h('div', { class: 'segmented', role: 'group', 'aria-label': label },
    options.map(o => h('button', { type: 'button', 'aria-pressed': String(o.id === active), text: o.label, on: { click: () => onChange(o.id) } })));
}

// ---------- Moduli ----------
let fieldCounter = 0;
export function field(label, input, opts = {}) {
  const id = input.id || `f${++fieldCounter}`;
  input.id = id;
  const hint = opts.hint ? h('div', { class: 'hint', id: `${id}-hint`, text: opts.hint }) : null;
  if (hint) input.setAttribute('aria-describedby', `${id}-hint`);
  return h('div', { class: `field ${opts.wide ? 'wide' : ''}`.trim(), dataset: { field: opts.name || input.name || '' } },
    h('label', { for: id, text: label + (opts.required ? ' *' : '') }), input, hint);
}

export function input(name, value = '', opts = {}) {
  return h('input', { name, value: value ?? '', type: opts.type || 'text', required: opts.required, maxlength: opts.max,
    min: opts.min, step: opts.step, placeholder: opts.placeholder, autocomplete: opts.autocomplete || 'off',
    inputmode: opts.inputmode, disabled: opts.disabled, list: opts.list });
}

export function select(name, options, value, opts = {}) {
  return h('select', { name, required: opts.required, disabled: opts.disabled },
    options.map(o => {
      const [v, label] = typeof o === 'string' ? [o, o] : Array.isArray(o) ? o : [o.value ?? o.id, o.label ?? o.name];
      return h('option', { value: v, selected: String(v) === String(value), text: label });
    }));
}

export function textarea(name, value = '', opts = {}) {
  return h('textarea', { name, maxlength: opts.max, rows: opts.rows || 3, value: value ?? '', disabled: opts.disabled });
}

export function checkbox(name, checked, label) {
  return h('label', { class: 'check' }, h('input', { type: 'checkbox', name, checked }), label);
}

export function showErrors(form, error) {
  for (const el of form.querySelectorAll('.field.invalid')) {
    el.classList.remove('invalid');
    el.querySelector('.error')?.remove();
  }
  if (error?.field) {
    const target = form.querySelector(`[data-field="${CSS.escape(error.field)}"]`) || form.querySelector(`[name="${CSS.escape(error.field)}"]`)?.closest('.field');
    if (target) {
      target.classList.add('invalid');
      target.append(h('div', { class: 'error', role: 'alert', text: error.message }));
      target.querySelector('input, select, textarea')?.focus();
      return true;
    }
  }
  return false;
}

// ---------- Finestre ----------
export function dialog(title, body, actions = [], opts = {}) {
  return new Promise(resolve => {
    const dlg = h('dialog', { class: opts.wide ? 'wide' : null, 'aria-label': title });
    const close = value => { dlg.close(); dlg.remove(); resolve(value); };
    const footer = h('div', { class: 'dialog-foot' });
    for (const a of actions) {
      footer.append(button(a.label, { kind: a.kind, onClick: async () => {
        if (a.onClick) {
          const result = await a.onClick(close);
          if (result === false) return;
          if (result !== undefined) return close(result);
        }
        if (a.value !== undefined) close(a.value);
      } }));
    }
    dlg.append(h('div', { class: 'dialog-head' }, h('h2', { text: title }),
      button('', { kind: 'ghost icon', ic: 'x', aria: 'Chiudi', onClick: () => close(null) })),
    h('div', { class: 'dialog-body' }, body), actions.length ? footer : null);
    dlg.addEventListener('cancel', e => { e.preventDefault(); close(null); });
    document.body.append(dlg);
    dlg.showModal();
    const first = dlg.querySelector('input, select, textarea, .dialog-foot .btn.primary');
    first?.focus();
  });
}

export async function confirmBox(title, text, opts = {}) {
  const reasonField = opts.reason ? textarea('reason', '', { max: 1000 }) : null;
  const body = h('div', null, h('p', { text }), reasonField ? field(opts.reasonLabel || 'Motivazione (almeno 8 caratteri)', reasonField) : null);
  return dialog(title, body, [
    { label: 'Annulla', value: false },
    { label: opts.confirmLabel || 'Conferma', kind: opts.danger ? 'danger' : 'primary', onClick: () => {
      if (reasonField) {
        const value = reasonField.value.trim();
        if (value.length < 8) { toast('Indica una motivazione di almeno 8 caratteri.', 'bad'); reasonField.focus(); return false; }
        return value;
      }
      return true;
    } },
  ]);
}

export function toast(text, tone = '') {
  const box = document.getElementById('toasts');
  if (!box) return;
  const item = h('div', { class: `toast ${tone}` }, icon(tone === 'bad' ? 'alert' : tone === 'ok' ? 'check' : 'info'), h('div', { text }));
  box.append(item);
  setTimeout(() => item.remove(), tone === 'bad' ? 9000 : 5000);
}

export function errorMessage(err) {
  return err?.message || 'Operazione non riuscita. Riprovare.';
}

export function skeleton(lines = 4) {
  return h('div', { class: 'card' }, h('div', { class: 'card-body stack' },
    Array.from({ length: lines }, () => h('div', { class: 'skeleton' }))));
}

export function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem('wr.' + key);
    localStorage.setItem('wr.' + key, value);
  } catch { /* archiviazione del browser non disponibile: si usa il valore predefinito */ }
  return null;
}
