// Registro presenze: griglia mensile (persona × fascia × giorno) e vista giornaliera per il telefono.
import { del, download, get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, dialog, empty, errorMessage, field, fmt, h, input, segmented, select, showErrors,
  store, table, textarea, toast,
} from '../ui.js';

const KIND_LABEL = { work: 'Lavoro', absence: 'Assenza', rest: 'Riposo' };

export async function render(ctx) {
  const { app } = ctx;
  const snap = await get(`attendance/${app.cid}/${app.month}`);
  const view = { mode: store('att.mode') || (window.innerWidth < 700 ? 'day' : 'month'), layer: 'actual', search: '', role: '',
    day: defaultDay(snap, app.me.today) };
  const root = h('div');
  const draw = () => clear(root, page(ctx, snap, view, draw, async () => {
    Object.assign(snap, await get(`attendance/${app.cid}/${app.month}`));
    draw();
  }));
  draw();
  return root;
}

function defaultDay(snap, today) {
  return snap.days.some(d => d.day === today) ? today : snap.days[0].day;
}

function stateBadges(snap) {
  const out = [snap.state.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true)];
  out.push(snap.state.verified ? badge('Calendario verificato', 'ok') : badge('Calendario da verificare', 'warn'));
  if (snap.approval.enabled) out.push(badge(`Approvazione: ${snap.approval.label}`, snap.approval.frozen ? 'brand' : ''));
  out.push(badge(`Parametri v${snap.state.rules_version}`, snap.rules_outdated ? 'warn' : ''));
  return out;
}

function page(ctx, snap, view, draw, reload) {
  const { app } = ctx;
  const caps = snap.caps;
  const actions = [
    segmented([{ id: 'month', label: 'Mese' }, { id: 'day', label: 'Giorno' }], view.mode, m => { view.mode = m; store('att.mode', m); draw(); }, 'Vista'),
    segmented([{ id: 'actual', label: 'Consuntivo' }, { id: 'planned', label: 'Pianificato' }], view.layer, l => { view.layer = l; draw(); }, 'Registro'),
  ];
  if (caps['presenze.anagrafica']) actions.push(button('Persone', { ic: 'users', onClick: () => peopleDialog(snap, reload) }));
  if (caps['presenze.esporta']) actions.push(button('Esporta', { ic: 'download', onClick: () => exportDialog(app, snap) }));
  const head = h('div', { class: 'page-head' }, h('div', null,
    h('div', { class: 'eyebrow', text: 'Registro presenze' }), h('h1', { text: `${snap.center.name} · ${fmt.month(snap.month)}` }),
    h('div', { class: 'row' }, stateBadges(snap))), h('div', { class: 'page-actions' }, actions));
  const alerts = alertsBlock(snap);
  const notice = !snap.editable && caps['presenze.compila']
    ? alertBox(snap.state.closed ? 'Il mese è chiuso: per correggerlo serve la riapertura motivata del responsabile.'
      : 'Il mese è inviato o approvato: le modifiche richiedono la restituzione dalla pagina Approvazioni.', 'warn')
    : null;
  const people = filtered(snap, view);
  const toolbar = h('div', { class: 'row' },
    h('input', { type: 'search', placeholder: 'Cerca persona o matricola', value: view.search, 'aria-label': 'Cerca persona',
      on: { input: e => { view.search = e.target.value; draw(); requestAnimationFrame(() => document.querySelector('input[type="search"]')?.focus()); } } }),
    h('select', { 'aria-label': 'Ruolo', on: { change: e => { view.role = e.target.value; draw(); } } },
      h('option', { value: '', text: 'Tutti i ruoli' }), snap.config.roles.map(r => h('option', { value: r, selected: r === view.role, text: r }))));
  const body = view.mode === 'month' ? monthGrid(ctx, snap, view, people, reload) : dayView(ctx, snap, view, people, reload, draw);
  return h('div', null, head, alerts, notice ? h('div', { class: 'alerts' }, notice) : null,
    card(view.mode === 'month' ? 'Griglia del mese' : 'Vista giornaliera', {
      subtitle: view.layer === 'actual' ? 'Turni e assenze effettivi (consuntivo)' : 'Turni pianificati', actions: [toolbar], flush: true,
      foot: legend(snap),
    }, people.length ? body : empty('Nessuna persona', snap.people.length ? 'Nessuna persona corrisponde ai filtri.' : 'Aggiungi le persone del registro con il pulsante «Persone».')),
    summaryCard(snap));
}

function filtered(snap, view) {
  const q = view.search.trim().toLowerCase();
  return snap.people.filter(p => (p.active || snap.entries.some(e => e.person_id === p.id))
    && (!view.role || p.role === view.role)
    && (!q || `${p.name} ${p.registration}`.toLowerCase().includes(q)));
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
  h('span', null, h('span', { class: 'code festive', text: 'm' }), 'festivo'));
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

function monthGrid(ctx, snap, view, people, reload) {
  const map = index(snap);
  const slots = snap.config.slots.filter(s => s.active);
  const summary = Object.fromEntries(snap.summary.map(r => [r.person_id, r]));
  const today = ctx.app.me.today;
  const headRow = h('tr', null, h('th', { class: 'sticky name-cell', scope: 'col', text: 'Persona' }), h('th', { class: 'slot-cell', scope: 'col', text: 'Fascia' }),
    snap.days.map(d => h('th', { scope: 'col', class: [d.weekday === 6 ? 'weekend' : '', d.holiday ? 'holiday' : '', d.day === today ? 'today' : ''].join(' ').trim() || null,
      title: fmt.dateLong(d.day) + (d.holiday ? ' · festivo' : '') }, String(Number(d.day.slice(8))), h('span', { class: 'wd', text: d.short }))),
    h('th', { scope: 'col', text: 'Turni' }), h('th', { scope: 'col', text: 'Ore' }));
  const rows = [];
  let r = 0;
  for (const person of people) {
    slots.forEach((slot, i) => {
      const tr = h('tr', { class: i === 0 ? 'first-slot' : null });
      if (i === 0) {
        tr.append(h('th', { class: 'sticky name-cell', scope: 'row', rowspan: String(slots.length) },
          h('strong', { text: person.name }), h('span', { text: [person.role, person.registration].filter(Boolean).join(' · ') })));
      }
      tr.append(h('td', { class: 'slot-cell', title: `${slot.label} ${slot.start}–${slot.end}`, text: slot.id }));
      snap.days.forEach((d, c) => {
        const actual = map.get(`${person.id}|${d.day}|${slot.id}|${view.layer}`);
        const plannedOnly = view.layer === 'actual' && !actual ? map.get(`${person.id}|${d.day}|${slot.id}|planned`) : null;
        const entry = actual || null;
        const clickable = snap.editable || entry;
        const cell = h('button', { class: 'cell', type: 'button', disabled: !clickable, dataset: { r: String(r), c: String(c) },
          'aria-label': describe(snap, person, d.day, slot.id, entry), on: { click: () => openEntry(ctx, snap, person, d.day, slot, view.layer, entry, plannedOnly, reload) } },
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
  const tableEl = h('table', { class: 'register', 'aria-label': 'Registro del mese' }, h('thead', null, headRow), h('tbody', null, rows));
  tableEl.addEventListener('keydown', e => moveFocus(e, tableEl));
  return h('div', { class: 'register-wrap' }, tableEl);
}

function moveFocus(e, tableEl) {
  const cell = e.target.closest('.cell');
  if (!cell) return;
  const delta = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }[e.key];
  if (!delta) return;
  e.preventDefault();
  const next = tableEl.querySelector(`.cell[data-r="${Number(cell.dataset.r) + delta[0]}"][data-c="${Number(cell.dataset.c) + delta[1]}"]`);
  next?.focus();
}

function dayView(ctx, snap, view, people, reload, draw) {
  const map = index(snap);
  const slots = snap.config.slots.filter(s => s.active);
  const pos = snap.days.findIndex(d => d.day === view.day);
  const nav = h('div', { class: 'day-nav card-body' },
    button('', { kind: 'icon', ic: 'chevronLeft', aria: 'Giorno precedente', disabled: pos <= 0, onClick: () => { view.day = snap.days[pos - 1].day; draw(); } }),
    h('select', { 'aria-label': 'Giorno', on: { change: e => { view.day = e.target.value; draw(); } } },
      snap.days.map(d => h('option', { value: d.day, selected: d.day === view.day, text: fmt.dateLong(d.day) + (d.holiday ? ' · festivo' : '') }))),
    button('', { kind: 'icon', ic: 'chevronRight', aria: 'Giorno successivo', disabled: pos >= snap.days.length - 1, onClick: () => { view.day = snap.days[pos + 1].day; draw(); } }));
  const list = h('div', { class: 'day-list card-body' }, people.map(person => h('div', { class: 'day-person' },
    h('div', null, h('strong', { text: person.name }), h('div', { class: 'small faint', text: person.role })),
    h('div', { class: 'day-slots' }, slots.map(slot => {
      const entry = map.get(`${person.id}|${view.day}|${slot.id}|${view.layer}`);
      const planned = view.layer === 'actual' && !entry ? map.get(`${person.id}|${view.day}|${slot.id}|planned`) : null;
      return h('button', { class: 'btn small', type: 'button', disabled: !snap.editable && !entry, 'aria-label': describe(snap, person, view.day, slot.id, entry),
        on: { click: () => openEntry(ctx, snap, person, view.day, slot, view.layer, entry, planned, reload) } },
      entry ? chip(snap, entry) : planned ? chip(snap, planned, true) : h('span', { class: 'faint', text: `+ ${slot.label}` }));
    })))));
  return h('div', null, nav, list);
}

// ---------- Inserimento e correzione ----------
async function openEntry(ctx, snap, person, day, slot, layer, entry, planned, reload) {
  const caps = snap.caps;
  const editable = snap.editable && (layer === 'actual' || caps['presenze.pianifica']);
  const codes = snap.config.codes.filter(c => c.active && (!c.allowed_slots.length || c.allowed_slots.includes(slot.id)));
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
  const canDelete = entry && editable && caps['presenze.elimina'] && (entry.layer === 'actual' || caps['presenze.pianifica']);
  if (canDelete) {
    actions.unshift({ label: 'Elimina', kind: 'danger', onClick: async () => {
      try {
        await del(`attendance/${ctx.app.cid}/${snap.month}/entries/${entry.id}`, { version: entry.version });
        toast('Registrazione eliminata.', 'ok');
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
