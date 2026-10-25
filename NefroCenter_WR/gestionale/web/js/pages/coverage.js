// Copertura turni: prospetto fabbisogni/pianificato, fabbisogni, disponibilità e sostituzioni fra strutture.
import { get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, clear, dialog, empty, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];
const WEEKDAY_NAMES = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica'];
const SUB_STATES = { pending: ['In attesa', 'warn'], accepted: ['Accettata', 'ok'], rejected: ['Rifiutata', ''] };

export async function render(ctx) {
  const { app } = ctx;
  const data = await get(`staffing/${app.cid}/${app.month}`);
  const perm = data.permissions;
  const privateView = data.people.length > 0 || perm.availability;
  let tab = ctx.query.tab || 'prospetto';
  const bar = h('div');
  const body = h('div');
  const pending = data.substitutions.filter(s => s.status === 'pending').length;
  const items = [{ id: 'prospetto', label: 'Prospetto' }, { id: 'fabbisogni', label: 'Fabbisogni' }];
  if (privateView) items.push({ id: 'disponibilita', label: 'Disponibilità', count: data.availability.filter(a => a.active).length },
    { id: 'sostituzioni', label: 'Sostituzioni', count: pending });
  if (data.problems.length) items.push({ id: 'verifiche', label: 'Da verificare', count: data.problems.length });
  const draw = () => {
    clear(bar, tabs(items, tab, id => { tab = id; draw(); }));
    const views = { prospetto, fabbisogni, disponibilita, sostituzioni, verifiche };
    clear(body, (views[tab] || prospetto)());
  };

  function prospetto() {
    if (!data.rows.length) return empty('Nessun fabbisogno', perm.configure ? 'Definisci i fabbisogni minimi nella scheda «Fabbisogni».' : 'I fabbisogni minimi non sono ancora stati definiti.');
    const allDays = monthDays(app.month);
    const keys = [...new Set(data.rows.map(r => `${r.slot}|${r.role}`))].sort();
    const byKey = Object.fromEntries(data.rows.map(r => [`${r.slot}|${r.role}|${r.day}`, r]));
    const slotLabel = Object.fromEntries(data.slots.map(s => [s.id, s.label]));
    const head = h('tr', null, h('th', { class: 'sticky name-cell', text: 'Fascia · qualifica' }), allDays.map(d => {
      const wd = (new Date(d + 'T12:00:00').getDay() + 6) % 7;
      return h('th', { class: wd >= 5 ? 'weekend' : null }, String(Number(d.slice(8))), h('span', { class: 'wd', text: WEEKDAYS[wd] }));
    }));
    const rows = keys.map(key => {
      const [slot, role] = key.split('|');
      return h('tr', null, h('th', { class: 'sticky name-cell', scope: 'row' }, h('strong', { text: slotLabel[slot] || slot }), h('span', { text: role })),
        allDays.map(d => {
          const r = byKey[`${key}|${d}`];
          if (!r) return h('td', { class: 'cov-cell' });
          const text = r.minimum === null ? String(r.planned) : `${r.planned}/${r.minimum}`;
          return h('td', { class: `cov-cell ${r.state}`, title: `${fmt.date(d)} · ${slotLabel[slot] || slot} · ${role}: ${r.state_label}` +
            (r.excluded ? ` · ${r.excluded} turni da verificare` : '') }, text);
        }));
    });
    return card('Prospetto del mese', { subtitle: 'Pianificati rispetto al minimo (pianificati/minimo). Rosso: scoperto · verde: coperto · blu: oltre il fabbisogno.', flush: true },
      h('div', { class: 'register-wrap' }, h('table', { class: 'register coverage' }, h('thead', null, head), h('tbody', null, rows))));
  }

  function fabbisogni() {
    const req = structuredClone(data.requirements);
    const editable = perm.configure;
    const activeSlots = data.slots.filter(s => s.active).map(s => [s.id, s.label]);
    const roles = data.roles.map(r => [r, r]);
    const weeklyBox = h('div');
    const overBox = h('div');
    const line = (list, row, i, first) => h('tr', null,
      h('td', null, first),
      h('td', null, bindSelect(select('slot', activeSlots, row.slot, { disabled: !editable }), row, 'slot')),
      h('td', null, bindSelect(select('role', roles, row.role, { disabled: !editable }), row, 'role')),
      h('td', null, bindNumber(input('minimum', row.minimum, { type: 'number', min: '0', disabled: !editable }), row, 'minimum')),
      h('td', null, editable ? button('', { kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => { list.splice(i, 1); redraw(); } }) : null));
    const redraw = () => {
      clear(weeklyBox, req.weekly.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table editor' },
        h('thead', null, h('tr', null, ['Giorno', 'Fascia', 'Qualifica', 'Minimo', ''].map(t => h('th', { text: t })))),
        h('tbody', null, req.weekly.map((row, i) => line(req.weekly, row, i,
          bindSelect(select('weekday', WEEKDAY_NAMES.map((n, k) => [k, n]), row.weekday, { disabled: !editable }), row, 'weekday', Number))))))
        : h('p', { class: 'muted', text: 'Nessun fabbisogno settimanale.' }));
      clear(overBox, req.overrides.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table editor' },
        h('thead', null, h('tr', null, ['Data', 'Fascia', 'Qualifica', 'Minimo', ''].map(t => h('th', { text: t })))),
        h('tbody', null, req.overrides.map((row, i) => line(req.overrides, row, i,
          bindNumber(input('day', row.day, { type: 'date', disabled: !editable }), row, 'day', x => x))))))
        : h('p', { class: 'muted', text: 'Nessuna eccezione per giorni particolari.' }));
    };
    redraw();
    const blank = () => ({ slot: activeSlots[0]?.[0] || '', role: data.roles[0] || '', minimum: 1 });
    const save = async () => {
      try {
        await put(`staffing/${app.cid}/requirements`, { weekly: req.weekly, overrides: req.overrides, version: req.version });
        toast('Fabbisogni salvati.', 'ok');
        ctx.refresh();
      } catch (err) { toast(errorMessage(err), 'bad'); }
    };
    return h('div', { class: 'stack' },
      alertBox('I fabbisogni sono riferimenti organizzativi indicati dall’azienda, non soglie cliniche.', 'info'),
      card('Fabbisogno settimanale', { subtitle: 'Minimo di persone per giorno della settimana, fascia e qualifica.',
        actions: editable ? button('Aggiungi riga', { small: true, ic: 'plus', onClick: () => { req.weekly.push({ weekday: 0, ...blank() }); redraw(); } }) : null }, weeklyBox),
      card('Eccezioni per data', { subtitle: 'Valgono al posto del fabbisogno settimanale nel giorno indicato.',
        actions: editable ? button('Aggiungi eccezione', { small: true, ic: 'plus', onClick: () => { req.overrides.push({ day: `${app.month}-01`, ...blank() }); redraw(); } }) : null }, overBox),
      editable ? h('div', { class: 'form-actions' }, button('Salva i fabbisogni', { kind: 'primary', ic: 'check', onClick: save })) : null);
  }

  function disponibilita() {
    return card('Disponibilità e indisponibilità', {
      subtitle: 'Le indisponibilità escludono la persona dalle proposte di sostituzione.',
      actions: perm.availability ? button('Registra', { small: true, ic: 'plus', onClick: () => availabilityDialog(ctx, data, null) }) : null, flush: true,
    }, table([
      { label: 'Persona', key: 'person' },
      { label: 'Periodo', render: a => `${fmt.date(a.start)} → ${fmt.date(a.end)}` },
      { label: 'Stato', render: a => badge(a.status_label, a.status === 'unavailable' ? 'bad' : a.status === 'preferred' ? 'ok' : 'info') },
      { label: 'Nota', render: a => a.note || '—' },
      { label: '', render: a => a.active ? (perm.availability ? button('Modifica', { small: true, ic: 'edit', onClick: () => availabilityDialog(ctx, data, a) }) : null) : badge('Ritirata', '') },
    ], data.availability, { empty: 'Nessuna disponibilità registrata per il mese.' }));
  }

  function sostituzioni() {
    return card('Sostituzioni fra strutture', {
      subtitle: 'Una proposta diventa un turno pianificato solo quando il responsabile della struttura la accetta.',
      actions: perm.propose && data.candidates.length ? button('Proponi', { small: true, ic: 'plus', onClick: () => proposeDialog(ctx, data) }) : null, flush: true,
    }, data.candidates.length || !perm.propose ? null : h('div', { class: 'card-body' }, alertBox('Per proporre una sostituzione, la persona deve avere una scheda anche in questa struttura, collegata in «Personale di gruppo».', 'info')),
    table([
      { label: 'Giorno', render: s => fmt.date(s.day) }, { label: 'Fascia', key: 'slot' }, { label: 'Persona', key: 'person' },
      { label: 'Da', key: 'origin_center' }, { label: 'Motivazione', key: 'note' },
      { label: 'Stato', render: s => badge(...SUB_STATES[s.status]) },
      { label: '', render: s => s.status === 'pending' && perm.decide ? h('div', { class: 'row' },
        button('Accetta', { small: true, kind: 'primary', onClick: () => decide(ctx, s, 'accept') }),
        button('Rifiuta', { small: true, onClick: () => decide(ctx, s, 'reject') })) : (s.decision_note || null) },
    ], data.substitutions, { empty: 'Nessuna sostituzione nel mese.' }));
  }

  function verifiche() {
    return card('Turni da verificare', { subtitle: 'Non contano come copertura finché il registro non è sistemato.', flush: true }, table([
      { label: 'Giorno', render: p => fmt.date(p.day) }, { label: 'Fascia', key: 'slot' }, { label: 'Persona', key: 'person' },
      { label: 'Registro', render: p => p.layer === 'planned' ? 'Pianificato' : 'Consuntivo' }, { label: 'Motivo', key: 'reason' },
    ], data.problems));
  }

  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Copertura turni' }),
      h('h1', { text: `${data.center.name} · ${fmt.month(data.month)}` }),
      h('p', { text: data.note }))),
    h('div', { class: 'kpis' },
      kpi('Fasce con fabbisogno', fmt.number(data.summary.configured), 'giorno · fascia · qualifica'),
      kpi('Scoperte', fmt.number(data.summary.uncovered), 'sotto il minimo', data.summary.uncovered ? 'bad' : 'ok'),
      kpi('Persone mancanti', fmt.number(data.summary.missing), 'somma delle unità sotto il minimo', data.summary.missing ? 'warn' : 'ok'),
      privateView ? kpi('Proposte in attesa', fmt.number(pending), 'sostituzioni da valutare', pending ? 'warn' : 'ok') : null),
    bar, body);
}

function monthDays(month) {
  const [y, m] = month.split('-').map(Number);
  const count = new Date(y, m, 0).getDate();
  return Array.from({ length: count }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`);
}

function bindSelect(el, row, key, conv = x => x) { el.addEventListener('change', () => { row[key] = conv(el.value); }); return el; }
function bindNumber(el, row, key, conv = Number) { el.addEventListener('input', () => { row[key] = conv(el.value); }); return el; }

async function availabilityDialog(ctx, data, current) {
  const person = select('person', data.people.map(p => [p.id, `${p.name} · ${p.role}`]), current?.person_id, { disabled: Boolean(current) });
  const start = input('start', current?.start || `${ctx.app.month}-01`, { type: 'date' });
  const end = input('end', current?.end || `${ctx.app.month}-01`, { type: 'date' });
  const status = select('status', [['unavailable', 'Non disponibile'], ['available', 'Disponibile'], ['preferred', 'Disponibilità preferita']], current?.status || 'unavailable');
  const note = textarea('note', current?.note || '', { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Persona', person, { name: 'person', wide: true }),
    field('Dal', start, { name: 'start' }), field('Al', end, { name: 'end' }), field('Stato', status, { name: 'status' }),
    field('Nota', note, { name: 'note', wide: true }));
  const send = async active => {
    try {
      await put(`staffing/${ctx.app.cid}/availability/${person.value}`, { id: current?.id || '', version: current?.version || 0,
        start: start.value, end: end.value, status: status.value, note: note.value, active });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  };
  const actions = [{ label: 'Annulla', value: null }];
  if (current) actions.push({ label: 'Ritira', kind: 'danger', onClick: () => send(false) });
  actions.push({ label: 'Salva', kind: 'primary', onClick: () => send(true) });
  if (await dialog(current ? 'Modifica disponibilità' : 'Registra disponibilità', form, actions)) { toast('Disponibilità salvata.', 'ok'); ctx.refresh(); }
}

async function proposeDialog(ctx, data) {
  const candidate = select('candidate', data.candidates.map((c, i) => [i, `${c.name} · da ${c.origin_center}`]), 0);
  const day = input('day', `${ctx.app.month}-01`, { type: 'date' });
  const activeSlots = data.slots.filter(s => s.active);
  const slot = select('slot', activeSlots.map(s => [s.id, `${s.label} (${s.start}–${s.end})`]), activeSlots[0]?.id);
  const code = select('code', [], '');
  const fillCodes = () => {
    const allowed = data.codes.filter(c => c.active && c.kind === 'work' && (!c.allowed_slots.length || c.allowed_slots.includes(slot.value)));
    code.replaceChildren(...allowed.map(c => h('option', { value: c.id, text: `${c.id} · ${c.label}` })));
  };
  slot.addEventListener('change', fillCodes);
  fillCodes();
  const note = textarea('note', '', { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Persona', candidate, { name: 'person_id', wide: true }),
    field('Giorno', day, { name: 'day' }), field('Fascia', slot, { name: 'slot' }), field('Causale', code, { name: 'code' }),
    field('Motivazione (almeno 8 caratteri)', note, { name: 'note', wide: true }));
  const result = await dialog('Proponi una sostituzione', form, [{ label: 'Annulla', value: null }, { label: 'Invia la proposta', kind: 'primary', onClick: async () => {
    const c = data.candidates[Number(candidate.value)];
    try {
      return await post(`staffing/${ctx.app.cid}/substitutions`, { person_id: c.person_id, origin_center_id: c.origin_center_id,
        origin_person_id: c.origin_person_id, day: day.value, slot: slot.value, code: code.value, note: note.value });
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (!result) return;
  toast(result.warnings?.length ? `Proposta inviata. Attenzione: ${result.warnings.join(' ')}` : 'Proposta inviata al responsabile.', result.warnings?.length ? '' : 'ok');
  ctx.refresh();
}

async function decide(ctx, sub, decision) {
  const note = textarea('note', '', { max: 1000, rows: 2 });
  const form = h('div', { class: 'stack' },
    h('p', { text: decision === 'accept' ? `Il turno di ${sub.person} del ${fmt.date(sub.day)} diventa un turno pianificato della struttura.`
      : 'La proposta viene chiusa senza creare turni.' }),
    field('Motivazione (almeno 8 caratteri)', note, { name: 'note' }));
  const result = await dialog(decision === 'accept' ? 'Accetta la sostituzione' : 'Rifiuta la sostituzione', form, [{ label: 'Annulla', value: null },
    { label: decision === 'accept' ? 'Accetta' : 'Rifiuta', kind: decision === 'accept' ? 'primary' : 'danger', onClick: async () => {
      try { return await post(`staffing/${ctx.app.cid}/substitutions/${sub.id}`, { decision, note: note.value, version: sub.version }); } catch (err) {
        if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
        return false;
      }
    } }]);
  if (!result) return;
  toast(decision === 'accept' ? 'Sostituzione accettata: turno pianificato.' : 'Sostituzione rifiutata.', 'ok');
  ctx.refresh();
}
