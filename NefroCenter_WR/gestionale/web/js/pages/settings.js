// Parametri della struttura: regole, fasce, causali, ruoli, sedi, calendario. Ogni salvataggio crea una nuova versione.
import { get, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, errorMessage, field, fmt, h, input, select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const WEEKDAYS = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica'];
const KINDS = [['work', 'Turno di lavoro'], ['absence', 'Assenza'], ['rest', 'Riposo']];
const GROUPS = [
  ['Regole del registro', ['min_rest_hours', 'require_times_on_close']],
  ['Cosa può fare il compilatore', ['operator_planned', 'operator_edit_times', 'operator_choose_site', 'operator_mark_holiday', 'operator_delete', 'operator_export']],
  ['Carico per fascia', ['nurse_reference', 'doctor_reference', 'isolation_weight', 'efficiency_threshold', 'dialysis_stations', 'isolation_stations']],
  ['Accordi del mese (valori proposti)', ['weekday_rate', 'holiday_rate', 'fixed_deduction', 'ccnl_rate', 'pay_mode']],
  ['File', ['csv_separator']],
];
const CHOICE_LABELS = { surplus: 'Solo turni oltre il fabbisogno', all: 'Tutti i turni', ';': 'Punto e virgola (;)', ',': 'Virgola (,)', '\t': 'Tabulazione' };

export async function render(ctx) {
  const { app } = ctx;
  const data = await get(`centers/${app.cid}/config`);
  const cfg = structuredClone(data.config);
  const editable = data.can_edit;
  const spec = Object.fromEntries(data.parameters.map(p => [p.id, p]));
  let tab = ctx.query.tab || 'regole';
  const holidayNames = {};
  let calYear = app.month.slice(0, 4);
  const box = h('div');
  const bar = h('div');
  const note = textarea('note', '', { max: 500, rows: 2 });
  const form = h('form', { novalidate: true }, bar, box);

  const draw = () => {
    clear(bar, tabs([{ id: 'regole', label: 'Regole' }, { id: 'fasce', label: 'Fasce orarie', count: cfg.slots.length },
      { id: 'causali', label: 'Causali', count: cfg.codes.length }, { id: 'ruoli', label: 'Ruoli e sedi' },
      { id: 'calendario', label: 'Calendario' }, { id: 'versioni', label: 'Versioni', count: data.versions.length }], tab, id => { tab = id; draw(); }));
    const views = { regole, fasce, causali, ruoli, calendario, versioni };
    clear(box, views[tab]());
  };

  function regole() {
    return h('div', { class: 'grid grid-2' }, GROUPS.map(([title, keys]) => card(title, {}, h('div', { class: 'stack' }, keys.map(key => {
      const p = spec[key];
      if (p.type === 'bool') {
        const wrap = checkbox(key, cfg[key], p.label);
        const el = wrap.querySelector('input');
        el.disabled = !editable;
        el.addEventListener('change', () => { cfg[key] = el.checked; });
        return wrap;
      }
      if (p.type === 'choice') {
        const el = select(key, p.options.map(o => [o, CHOICE_LABELS[o] || o]), cfg[key], { disabled: !editable });
        el.addEventListener('change', () => { cfg[key] = el.value; });
        return field(p.label, el, { name: key });
      }
      const el = input(key, cfg[key], { type: 'number', min: p.minimum, step: 'any', disabled: !editable });
      el.addEventListener('input', () => { cfg[key] = el.value === '' ? '' : Number(el.value); });
      return field(p.label, el, { name: key, hint: `Da ${fmt.number(p.minimum, 2)} a ${fmt.number(p.maximum, 2)}` });
    })))),
    card('Note sui parametri', {}, (() => {
      const el = textarea('cfg-note', cfg.note, { max: 4000, rows: 4, disabled: !editable });
      el.addEventListener('input', () => { cfg.note = el.value; });
      return field('Annotazioni per chi compila (facoltative)', el, { name: 'note' });
    })()));
  }

  function fasce() {
    const rows = cfg.slots.map((slot, i) => {
      const fresh = !data.config.slots.some(s => s.id === slot.id);
      const bind = (el, key, conv = x => x) => { el.disabled = !editable; el.addEventListener('input', () => { slot[key] = conv(el.value); }); return el; };
      const check = (key) => { const el = h('input', { type: 'checkbox', checked: slot[key], disabled: !editable, 'aria-label': key });
        el.addEventListener('change', () => { slot[key] = el.checked; }); return el; };
      return h('tr', null,
        h('td', null, fresh ? bind(input('id', slot.id, { max: 12 }), 'id') : h('strong', { class: 'mono', text: slot.id })),
        h('td', null, bind(input('label', slot.label, { max: 100 }), 'label')),
        h('td', null, bind(input('start', slot.start, { type: 'time' }), 'start')),
        h('td', null, bind(input('end', slot.end, { type: 'time' }), 'end')),
        h('td', { class: 'center' }, check('overnight')),
        h('td', null, bind(input('pause', slot.pause, { type: 'number', min: '0' }), 'pause', Number)),
        h('td', null, bind(h('input', { type: 'color', value: slot.color, class: 'color-input', 'aria-label': 'Colore' }), 'color')),
        h('td', { class: 'center' }, check('active')),
        h('td', null, fresh && editable ? button('', { kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => { cfg.slots.splice(i, 1); draw(); } }) : null));
    });
    return card('Fasce orarie', {
      subtitle: 'Le fasce sono le righe del registro. Una fascia usata non si elimina: si disattiva.',
      actions: editable ? button('Aggiungi fascia', { small: true, ic: 'plus', onClick: () => {
        cfg.slots.push({ id: '', label: '', start: '08:00', end: '14:00', overnight: false, pause: 0, color: '#4f7fbf', active: true }); draw();
      } }) : null, flush: true,
    }, h('div', { class: 'table-wrap' }, h('table', { class: 'table editor' },
      h('thead', null, h('tr', null, ['Codice', 'Descrizione', 'Inizio', 'Fine', 'Giorno dopo', 'Pausa min', 'Colore', 'Attiva', ''].map(t => h('th', { text: t })))),
      h('tbody', null, rows))));
  }

  function causali() {
    const slots = cfg.slots.filter(s => s.id);
    const rows = cfg.codes.map((code, i) => {
      const fresh = !data.config.codes.some(c => c.id === code.id);
      const bind = (el, key, conv = x => x) => { el.disabled = !editable; el.addEventListener('input', () => { code[key] = conv(el.value); }); return el; };
      const active = h('input', { type: 'checkbox', checked: code.active, disabled: !editable, 'aria-label': 'Attiva' });
      active.addEventListener('change', () => { code.active = active.checked; });
      const kind = select('kind', KINDS, code.kind, { disabled: !editable });
      kind.addEventListener('change', () => { code.kind = kind.value; if (code.kind !== 'absence') code.credit_minutes = 0; if (code.kind !== 'work') code.allowed_slots = []; draw(); });
      const allowed = code.kind === 'work' ? h('div', { class: 'row tight' }, slots.map(s => {
        const el = h('input', { type: 'checkbox', checked: code.allowed_slots.includes(s.id), disabled: !editable });
        el.addEventListener('change', () => {
          code.allowed_slots = el.checked ? [...code.allowed_slots, s.id] : code.allowed_slots.filter(x => x !== s.id);
        });
        return h('label', { class: 'check small' }, el, s.id);
      })) : h('span', { class: 'faint small', text: 'tutte' });
      return h('tr', null,
        h('td', null, fresh ? bind(input('id', code.id, { max: 12 }), 'id') : h('span', { class: 'code', vars: { '--c': code.color }, text: code.id })),
        h('td', null, bind(input('label', code.label, { max: 100 }), 'label')),
        h('td', null, kind),
        h('td', null, code.kind === 'absence' ? bind(input('credit', code.credit_minutes, { type: 'number', min: '0' }), 'credit_minutes', Number) : h('span', { class: 'faint', text: '—' })),
        h('td', null, allowed),
        h('td', null, bind(h('input', { type: 'color', value: code.color, class: 'color-input', 'aria-label': 'Colore' }), 'color')),
        h('td', { class: 'center' }, active),
        h('td', null, fresh && editable ? button('', { kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => { cfg.codes.splice(i, 1); draw(); } }) : null));
    });
    return card('Causali', {
      subtitle: 'Turni, assenze e riposi selezionabili nel registro. Il credito in minuti vale solo per le assenze.',
      actions: editable ? button('Aggiungi causale', { small: true, ic: 'plus', onClick: () => {
        cfg.codes.push({ id: '', label: '', kind: 'absence', credit_minutes: 0, color: '#3f8f7a', active: true, allowed_slots: [] }); draw();
      } }) : null, flush: true,
    }, h('div', { class: 'table-wrap' }, h('table', { class: 'table editor' },
      h('thead', null, h('tr', null, ['Codice', 'Descrizione', 'Tipo', 'Credito min', 'Fasce consentite', 'Colore', 'Attiva', ''].map(t => h('th', { text: t })))),
      h('tbody', null, rows))));
  }

  function ruoli() {
    const roles = textarea('roles', cfg.roles.join('\n'), { rows: 6, disabled: !editable });
    roles.addEventListener('change', () => {
      cfg.roles = roles.value.split('\n').map(x => x.trim()).filter(Boolean);
      cfg.nurse_roles = cfg.nurse_roles.filter(r => cfg.roles.includes(r));
      cfg.doctor_roles = cfg.doctor_roles.filter(r => cfg.roles.includes(r));
      draw();
    });
    const pick = key => h('div', { class: 'row' }, cfg.roles.map(r => {
      const el = h('input', { type: 'checkbox', checked: cfg[key].includes(r), disabled: !editable });
      el.addEventListener('change', () => { cfg[key] = el.checked ? [...cfg[key], r] : cfg[key].filter(x => x !== r); });
      return h('label', { class: 'check' }, el, r);
    }));
    const sites = textarea('sites', cfg.sites.join('\n'), { rows: 6, disabled: !editable });
    sites.addEventListener('input', () => { cfg.sites = sites.value.split('\n').map(x => x.trim()).filter(Boolean); });
    return h('div', { class: 'grid grid-2' },
      card('Ruoli del personale', { subtitle: 'Un ruolo per riga (per esempio INF, MED, OSS).' },
        field('Ruoli', roles, { name: 'roles' }),
        h('h3', { class: 'mt', text: 'Ruoli infermieristici nel calcolo del carico' }), pick('nurse_roles'),
        h('h3', { class: 'mt', text: 'Ruoli medici nel calcolo del carico' }), pick('doctor_roles')),
      card('Sedi esterne', { subtitle: 'Sedi dove il personale può lavorare fuori dalla struttura. Una per riga.' },
        field('Sedi', sites, { name: 'sites' })));
  }

  function calendario() {
    const days = h('div', { class: 'row' }, WEEKDAYS.map((label, i) => {
      const el = h('input', { type: 'checkbox', checked: cfg.weekdays.includes(i), disabled: !editable });
      el.addEventListener('change', () => { cfg.weekdays = el.checked ? [...cfg.weekdays, i].sort() : cfg.weekdays.filter(d => d !== i); });
      return h('label', { class: 'check' }, el, label);
    }));
    const year = input('year', calYear, { type: 'number', min: '2000' });
    const day = input('day', '', { type: 'date' });
    const list = cfg.holidays.slice().sort().filter(d => d.startsWith(year.value));
    const rows = h('ul', { class: 'list' }, list.length ? list.map(d => h('li', null, h('div', { class: 'grow' },
      h('div', { class: 'title', text: fmt.dateLong(d) }), holidayNames[d] ? h('div', { class: 'detail', text: holidayNames[d] }) : null),
    editable ? button('', { kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => { cfg.holidays = cfg.holidays.filter(x => x !== d); draw(); } }) : null))
      : h('li', null, h('span', { class: 'muted', text: 'Nessuna festività per l’anno scelto.' })));
    year.addEventListener('change', () => { calYear = year.value; draw(); });
    return h('div', { class: 'grid grid-2' },
      card('Giorni lavorativi', { subtitle: 'Servono per contare i giorni lavorativi del mese.' }, days),
      card('Festività', { subtitle: 'Le festività nazionali si aggiungono con un clic; il santo patrono va aggiunto a mano.', flush: true },
        h('div', { class: 'card-body' }, h('div', { class: 'form-grid' }, field('Anno', year), editable ? field('Aggiungi un giorno', day) : null),
          editable ? h('div', { class: 'row mt' },
            button('Aggiungi il giorno', { small: true, ic: 'plus', onClick: () => {
              if (day.value && !cfg.holidays.includes(day.value)) cfg.holidays.push(day.value);
              draw();
            } }),
            button('Aggiungi le festività nazionali', { small: true, ic: 'calendar', onClick: async () => {
              try {
                const res = await get(`holidays/${year.value}`);
                for (const x of res.holidays) { holidayNames[x.day] = x.name; if (!cfg.holidays.includes(x.day)) cfg.holidays.push(x.day); }
                toast(`Aggiunte le festività nazionali del ${year.value}.`, 'ok');
                draw();
              } catch (err) { toast(errorMessage(err), 'bad'); }
            } })) : null),
        rows));
  }

  function versioni() {
    return card('Versioni dei parametri', { subtitle: 'Ogni mese resta legato alla versione con cui è stato compilato.', flush: true },
      table([
        { label: 'Versione', render: r => r.version === data.version ? badge(`v${r.version} · in uso`, 'ok') : `v${r.version}` },
        { label: 'Motivo', key: 'note' }, { label: 'Quando', render: r => fmt.stamp(r.created_at) }, { label: 'Da', key: 'created_by' },
      ], data.versions));
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await put(`centers/${app.cid}/config`, { config: cfg, version: data.version, note: note.value });
      toast(`Parametri salvati: versione ${res.version}.`, 'ok');
      ctx.refresh();
    } catch (err) {
      if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
    }
  });
  draw();
  const saveBar = editable ? card(null, {}, h('div', { class: 'form-grid' }, field('Motivo della modifica', note, { name: 'note', hint: 'Resta nello storico delle versioni.' }),
    h('div', { class: 'field end' }, button('Salva una nuova versione', { kind: 'primary', ic: 'check', onClick: () => form.requestSubmit() })))) : null;
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Parametri struttura' }),
      h('h1', { text: data.center.name }),
      h('div', { class: 'row' }, badge(`Versione ${data.version}`, 'brand'), editable ? null : badge('Sola lettura', '')))),
    editable ? alertBox('I mesi già compilati mantengono i parametri con cui sono stati registrati; i permessi del compilatore valgono subito per tutti i mesi aperti.', 'info') : null,
    form, saveBar);
}
