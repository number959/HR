// Uscite e dotazioni: percorsi di cessazione o trasferimento (lista di controllo) e consegne di badge, chiavi, dispositivi.
import { get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, dialog, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const STATUS_TONE = { open: 'info', in_progress: 'warn', completed: 'ok', cancelled: '' };
const TASK_TONE = { todo: '', doing: 'warn', done: 'ok', na: 'info' };

export async function render(ctx) {
  if (ctx.params.length >= 2) return caseDetail(ctx, ctx.params[0], ctx.params[1]);
  const data = await get('departures');
  let tab = ctx.query.tab || 'percorsi';
  const bar = h('div');
  const body = h('div');
  const draw = () => {
    clear(bar, tabs([{ id: 'percorsi', label: 'Percorsi di uscita', count: data.summary.open }, { id: 'dotazioni', label: 'Dotazioni', count: data.summary.assigned }],
      tab, id => { tab = id; draw(); }));
    clear(body, tab === 'percorsi' ? casesTable(ctx, data) : assetsTable(ctx, data));
  };
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Uscite e dotazioni' }),
      h('h1', { text: 'Cessazioni, trasferimenti e dotazioni' }),
      h('p', { text: data.notice })),
    h('div', { class: 'page-actions' },
      button('Consegna una dotazione', { ic: 'key', onClick: () => assetDialog(ctx, data, null) }),
      button('Nuovo percorso', { kind: 'primary', ic: 'plus', onClick: () => caseDialog(ctx, data, null) }))),
    h('div', { class: 'kpis' },
      kpi('Percorsi aperti', fmt.number(data.summary.open), 'cessazioni e trasferimenti'),
      kpi('Dotazioni assegnate', fmt.number(data.summary.assigned), 'non ancora restituite'),
      kpi('Restituzioni in ritardo', fmt.number(data.summary.overdue), 'oltre la data prevista', data.summary.overdue ? 'bad' : 'ok')),
    bar, body);
}

function casesTable(ctx, data) {
  return card(null, { flush: true }, table([
    { label: 'Persona', render: c => h('div', null, h('strong', { text: c.person }), h('div', { class: 'small faint', text: c.center })) },
    { label: 'Tipo', key: 'kind_label' },
    { label: 'Data prevista', render: c => fmt.date(c.effective_date) },
    { label: 'Attività', render: c => `${c.tasks.filter(t => ['done', 'na'].includes(t.status)).length}/${c.tasks.length}` },
    { label: 'Stato', render: c => badge(c.status_label, STATUS_TONE[c.status]) },
  ], data.cases, { empty: 'Nessun percorso di uscita.', onRow: c => ctx.go(`uscite/${c.center_id}/${c.id}`) }));
}

function assetsTable(ctx, data) {
  return card(null, { flush: true }, table([
    { label: 'Dotazione', render: a => h('div', null, h('strong', { text: a.label }), h('div', { class: 'small faint', text: `${a.kind_label} · ${a.inventory_code}` })) },
    { label: 'Persona', render: a => h('div', null, h('div', { text: a.person }), h('div', { class: 'small faint', text: a.center })) },
    { label: 'Consegna', render: a => fmt.date(a.delivery_date) },
    { label: 'Restituzione', render: a => a.status === 'returned' ? `${fmt.date(a.return_date)} · ${data.conditions[a.return_condition] || ''}`
      : a.due_date ? (a.overdue ? badge(`Prevista ${fmt.date(a.due_date)}`, 'bad') : `Prevista ${fmt.date(a.due_date)}`) : '—' },
    { label: 'Stato', render: a => a.status === 'returned' ? badge('Restituita', 'ok') : badge('Assegnata', a.overdue ? 'bad' : 'warn') },
    { label: '', render: a => a.status === 'assigned' ? h('div', { class: 'row' },
      button('Restituzione', { small: true, ic: 'undo', onClick: () => returnDialog(ctx, data, a) }),
      button('', { small: true, kind: 'ghost icon', ic: 'edit', aria: 'Modifica', onClick: () => assetDialog(ctx, data, a) })) : button('Storico', { small: true, onClick: () => assetHistory(a) }) },
  ], data.assets, { empty: 'Nessuna dotazione registrata.' }));
}

function peopleSelect(data, centerId, value) {
  const list = data.people.filter(p => p.center_id === centerId && (p.active || p.id === value));
  return select('person_id', list.map(p => [p.id, `${p.name}${p.registration ? ' · ' + p.registration : ''}`]), value);
}

async function caseDialog(ctx, data, current) {
  const centerSel = select('center', data.centers.map(c => [c.id, c.name]), current?.center_id || ctx.app.cid, { disabled: Boolean(current) });
  const personBox = h('div');
  let person = peopleSelect(data, centerSel.value, current?.person_id);
  person.disabled = Boolean(current);
  const refreshPeople = () => { person = peopleSelect(data, centerSel.value); clear(personBox, field('Persona', person, { name: 'person_id' })); };
  clear(personBox, field('Persona', person, { name: 'person_id' }));
  centerSel.addEventListener('change', refreshPeople);
  const kind = select('kind', Object.entries(data.kinds), current?.kind || 'termination');
  const destination = select('destination_center_id', [['', '—'], ...data.centers.map(c => [c.id, c.name])], current?.destination_center_id || '');
  const destField = field('Struttura di destinazione', destination, { name: 'destination_center_id' });
  const syncKind = () => destField.classList.toggle('hidden', kind.value !== 'transfer');
  kind.addEventListener('change', syncKind);
  syncKind();
  const effective = input('effective_date', current?.effective_date || data.today, { type: 'date' });
  const responsible = input('responsible', current?.responsible || ctx.app.me.user.name, { max: 150 });
  const reason = textarea('reason', current?.reason || '', { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Struttura', centerSel), personBox, field('Tipo', kind, { name: 'kind' }), destField,
    field('Data prevista', effective, { name: 'effective_date' }), field('Responsabile del percorso', responsible, { name: 'responsible' }),
    field('Motivazione (almeno 8 caratteri)', reason, { name: 'reason', wide: true }));
  const result = await dialog(current ? 'Modifica il percorso' : 'Nuovo percorso di uscita', form, [{ label: 'Annulla', value: null }, {
    label: current ? 'Salva' : 'Apri il percorso', kind: 'primary', onClick: async () => {
      const body = { person_id: person.value, kind: kind.value, destination_center_id: kind.value === 'transfer' ? destination.value : '',
        effective_date: effective.value, responsible: responsible.value, reason: reason.value, version: current?.version || 0 };
      try {
        return current ? await put(`departures/${current.center_id}/${current.id}`, body) : await post(`departures/${centerSel.value}`, body);
      } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
    },
  }], { wide: true });
  if (!result) return;
  toast(current ? 'Percorso aggiornato.' : 'Percorso aperto con le attività standard.', 'ok');
  if (current) ctx.refresh(); else ctx.go(`uscite/${result.center_id}/${result.id}`);
}

async function caseDetail(ctx, cid, caseId) {
  const item = await get(`departures/${cid}/${caseId}`);
  const meta = await get(`departures?cid=${encodeURIComponent(cid)}`);
  const active = ['open', 'in_progress'].includes(item.status);
  const tasks = table([
    { label: 'Attività', render: t => h('div', null, h('strong', { text: t.label }), t.note ? h('div', { class: 'small faint', text: t.note }) : null) },
    { label: 'Referente', key: 'owner' },
    { label: 'Scadenza', render: t => fmt.date(t.due) },
    { label: 'Stato', render: t => badge(meta.task_states[t.status], TASK_TONE[t.status]) },
    { label: '', render: t => active ? button('Aggiorna', { small: true, ic: 'edit', onClick: () => taskDialog(ctx, meta, item, t) }) : null },
  ], item.tasks);
  const actions = active ? [
    button('Modifica', { ic: 'edit', onClick: () => caseDialog(ctx, meta, item) }),
    button('Annulla il percorso', { onClick: () => closeDialog(ctx, item, 'cancelled') }),
    button('Completa', { kind: 'primary', ic: 'check', disabled: !item.can_complete, onClick: () => closeDialog(ctx, item, 'completed') }),
  ] : [];
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('a', { class: 'eyebrow', href: '#/uscite', text: '← Uscite e dotazioni' }),
      h('h1', { text: `${item.kind_label} · ${item.person}` }),
      h('div', { class: 'row' }, badge(item.status_label, STATUS_TONE[item.status], true), h('span', { class: 'muted', text: `Data prevista ${fmt.date(item.effective_date)}` }),
        item.destination ? h('span', { class: 'muted', text: `verso ${item.destination}` }) : null)),
    h('div', { class: 'page-actions' }, actions)),
    alertBox(item.notice, 'info'),
    active && item.blockers.length ? card('Prima di completare', {}, h('ul', null, item.blockers.map(b => h('li', { text: b })))) : null,
    item.closure_note ? alertBox(`Chiusura: ${item.closure_note} (${item.closed_by}, ${fmt.stamp(item.closed_at)})`, item.status === 'completed' ? 'ok' : 'info') : null,
    card('Attività', { subtitle: `Motivazione: ${item.reason} · responsabile ${item.responsible}`, flush: true }, tasks),
    card('Dotazioni ancora assegnate', { flush: true }, table([
      { label: 'Dotazione', render: a => `${a.kind_label} · ${a.label}` }, { label: 'Codice', key: 'inventory_code' },
      { label: 'Consegna', render: a => fmt.date(a.delivery_date) },
      { label: '', render: a => button('Restituzione', { small: true, ic: 'undo', onClick: () => returnDialog(ctx, meta, a) }) },
    ], item.outstanding, { empty: 'Nessuna dotazione da restituire.' })),
    card('Storico', { flush: true }, table([
      { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Operazione', key: 'action' }, { label: 'Da', key: 'actor' },
    ], item.history)));
}

async function taskDialog(ctx, meta, item, task) {
  const status = select('status', Object.entries(meta.task_states), task.status);
  const owner = input('owner', task.owner, { max: 150 });
  const due = input('due', task.due, { type: 'date' });
  const note = textarea('note', task.note, { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Stato', status, { name: 'status' }), field('Referente', owner, { name: 'owner' }),
    field('Scadenza', due, { name: 'due' }), field('Nota (obbligatoria se non applicabile)', note, { name: 'note', wide: true }));
  const ok = await dialog(task.label, form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    try {
      await put(`departures/${item.center_id}/${item.id}/tasks/${task.id}`, { status: status.value, owner: owner.value, due: due.value, note: note.value, version: item.version });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) { toast('Attività aggiornata.', 'ok'); ctx.refresh(); }
}

async function closeDialog(ctx, item, target) {
  const note = textarea('note', '', { max: 1000, rows: 2 });
  const confirm = checkbox('confirm', false, 'Confermo che tutte le attività sono state svolte');
  const form = h('div', { class: 'stack' },
    h('p', { text: target === 'completed' ? 'Il percorso viene chiuso come completato. Fascicolo e accessi vanno aggiornati nelle rispettive procedure.'
      : 'Il percorso viene annullato e resta nello storico.' }),
    field(target === 'completed' ? 'Nota di chiusura (almeno 8 caratteri)' : 'Motivo dell’annullamento (almeno 8 caratteri)', note, { name: 'note' }),
    target === 'completed' ? confirm : null);
  const ok = await dialog(target === 'completed' ? 'Completa il percorso' : 'Annulla il percorso', form, [{ label: 'Indietro', value: null }, {
    label: target === 'completed' ? 'Completa' : 'Annulla il percorso', kind: target === 'completed' ? 'primary' : 'danger', onClick: async () => {
      try {
        await post(`departures/${item.center_id}/${item.id}/close`, { status: target, note: note.value, version: item.version,
          confirm: confirm.querySelector('input').checked });
        return true;
      } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
    },
  }]);
  if (ok) { toast('Percorso chiuso.', 'ok'); ctx.refresh(); }
}

async function assetDialog(ctx, data, current) {
  const centerSel = select('center', data.centers.map(c => [c.id, c.name]), current?.center_id || ctx.app.cid, { disabled: Boolean(current) });
  const personBox = h('div');
  let person = peopleSelect(data, centerSel.value, current?.person_id);
  const placePerson = () => { person.disabled = Boolean(current); clear(personBox, field('Persona', person, { name: 'person_id' })); };
  placePerson();
  centerSel.addEventListener('change', () => { person = peopleSelect(data, centerSel.value); placePerson(); });
  const kind = select('kind', Object.entries(data.asset_kinds), current?.kind || 'badge', { disabled: Boolean(current) });
  const code = input('inventory_code', current?.inventory_code || '', { max: 80, disabled: Boolean(current) });
  const label = input('label', current?.label || '', { max: 200 });
  const delivered = input('delivery_date', current?.delivery_date || data.today, { type: 'date', disabled: Boolean(current) });
  const due = input('due_date', current?.due_date || '', { type: 'date' });
  const note = textarea('note', current?.note || '', { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Struttura', centerSel), personBox, field('Tipo', kind, { name: 'kind' }),
    field('Codice inventario', code, { name: 'inventory_code' }), field('Descrizione', label, { name: 'label' }),
    field('Data di consegna', delivered, { name: 'delivery_date' }), field('Restituzione prevista', due, { name: 'due_date' }),
    field('Nota', note, { name: 'note', wide: true }),
    current ? h('p', { class: 'small muted wide', text: 'Persona, tipo, codice e data di consegna non si riscrivono: per correggerli registra prima la restituzione.' }) : null);
  const ok = await dialog(current ? 'Modifica la dotazione' : 'Consegna una dotazione', form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    const body = { person_id: person.value, kind: kind.value, inventory_code: code.value, label: label.value, delivery_date: delivered.value,
      due_date: due.value, note: note.value, version: current?.version || 0 };
    try {
      if (current) await put(`equipment/${current.center_id}/${current.id}`, body); else await post(`equipment/${centerSel.value}`, body);
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }], { wide: true });
  if (ok) { toast('Dotazione salvata.', 'ok'); ctx.refresh(); }
}

async function returnDialog(ctx, data, asset) {
  const day = input('return_date', data.today, { type: 'date' });
  const condition = select('condition', Object.entries(data.conditions), 'good');
  const note = textarea('note', '', { max: 1000, rows: 2 });
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Data di restituzione', day, { name: 'return_date' }),
    field('Condizioni', condition, { name: 'condition' }), field('Nota (obbligatoria se danneggiata)', note, { name: 'note', wide: true }));
  const ok = await dialog(`Restituzione · ${asset.label}`, form, [{ label: 'Annulla', value: null }, { label: 'Registra', kind: 'primary', onClick: async () => {
    try {
      await post(`equipment/${asset.center_id}/${asset.id}/return`, { return_date: day.value, condition: condition.value, note: note.value, version: asset.version });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) { toast('Restituzione registrata.', 'ok'); ctx.refresh(); }
}

async function assetHistory(asset) {
  try {
    const res = await get(`equipment/${asset.center_id}/${asset.id}`);
    await dialog(`Storico · ${asset.label}`, table([
      { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Operazione', key: 'action' }, { label: 'Da', key: 'actor' },
    ], res.history), [{ label: 'Chiudi', value: null }]);
  } catch (err) { toast(errorMessage(err), 'bad'); }
}
