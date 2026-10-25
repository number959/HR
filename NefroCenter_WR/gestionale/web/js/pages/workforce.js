// Personale di gruppo: persone presenti in più strutture, contratti ed economia con decorrenza, applicazione al mese.
import { get, post, put } from '../api.js';
import { agreementForm, modelLabel } from '../agreement-form.js';
import {
  alertBox, badge, button, card, clear, dialog, empty, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, textarea, toast,
} from '../ui.js';

export async function render(ctx) {
  if (ctx.params[0]) return detail(ctx, ctx.params[0]);
  const data = await get('workforce');
  let term = '';
  let filter = ctx.query.filter || 'all';
  const box = h('div');
  const search = input('q', '', { placeholder: 'Cerca persona, matricola o struttura' });
  search.setAttribute('aria-label', 'Cerca');
  const which = select('filter', [['all', 'Tutte le persone'], ['linked', 'Presenti in più strutture'], ['missing', 'Senza contratto in vigore']], filter);
  which.setAttribute('aria-label', 'Filtro');
  const draw = () => {
    const rows = data.groups.filter(g => (filter === 'all' || (filter === 'linked' ? g.linked : g.missing_contract))
      && (!term || `${g.name} ${g.assignments.map(a => `${a.registration} ${a.center}`).join(' ')}`.toLowerCase().includes(term)));
    clear(box, table([
      { label: 'Persona', render: g => h('strong', { text: g.name }) },
      { label: 'Strutture', render: g => h('div', { class: 'stack-tight' }, g.assignments.map(a => h('div', { class: 'small' },
        `${a.center} · ${a.role}${a.registration ? ' · ' + a.registration : ''}`, a.active ? null : badge('non attiva', '')))) },
      { label: 'Contratto in vigore', render: g => h('div', { class: 'stack-tight' }, g.assignments.map(a => h('div', { class: 'small' },
        a.contract ? `${a.contract.contract_type || 'Contratto'} · ${fmt.number(a.contract.weekly_hours, 1)} h/sett.` : badge('Mancante', a.active ? 'warn' : '')))) },
      { label: '', render: g => g.linked ? badge(`${g.assignments.length} strutture`, 'brand') : null },
    ], rows, { empty: 'Nessuna persona con questi filtri.', onRow: g => ctx.go(`gruppo/${g.identity_id}`) }));
  };
  search.addEventListener('input', () => { term = search.value.trim().toLowerCase(); draw(); });
  which.addEventListener('change', () => { filter = which.value; draw(); });
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Personale di gruppo' }),
      h('h1', { text: 'Persone, contratti ed economia' }),
      h('p', { text: 'Ogni struttura ha la sua scheda; qui le schede della stessa persona si collegano a mano e si registrano contratti e condizioni con decorrenza.' }))),
    h('div', { class: 'kpis' },
      kpi('Persone', fmt.number(data.groups.length), data.scope),
      kpi('In più strutture', fmt.number(data.groups.filter(g => g.linked).length), 'schede collegate'),
      kpi('Senza contratto', fmt.number(data.groups.filter(g => g.missing_contract).length), `in vigore al ${fmt.date(data.on)}`,
        data.groups.some(g => g.missing_contract) ? 'warn' : 'ok')),
    card(null, { flush: true }, h('div', { class: 'card-body filters' }, search, which), box));
}

async function detail(ctx, identityId) {
  const data = await get(`workforce/${identityId}`);
  const name = data.assignments[0].person.name;
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('a', { class: 'eyebrow back', href: '#/gruppo', text: '← Personale di gruppo' }),
      h('h1', { text: name }),
      h('div', { class: 'row' }, badge(`${data.assignments.length} ${data.assignments.length === 1 ? 'struttura' : 'strutture'}`, 'brand'),
        data.hidden_assignments ? badge(`${data.hidden_assignments} in strutture non autorizzate`, '') : null))),
    data.assignments.map(a => assignmentCard(ctx, data, a)));
}

function assignmentCard(ctx, data, a) {
  const p = a.person;
  const contracts = table([
    { label: 'Dal', render: r => fmt.date(r.valid_from) }, { label: 'Al', render: r => r.valid_to ? fmt.date(r.valid_to) : 'in corso' },
    { label: 'Ruolo', render: r => r.data.role }, { label: 'Contratto', render: r => [r.data.contract_type, r.data.ccnl, r.data.level].filter(Boolean).join(' · ') || '—' },
    { label: 'Ore', num: true, render: r => `${fmt.number(r.data.weekly_hours, 1)} (${fmt.number(r.data.part_time_percent)}%)` },
    { label: '', render: r => button('Modifica', { small: true, ic: 'edit', onClick: () => contractDialog(ctx, a, r) }) },
  ], a.contracts, { empty: 'Nessun contratto registrato.' });
  const economics = table([
    { label: 'Dal', render: r => fmt.date(r.valid_from) }, { label: 'Al', render: r => r.valid_to ? fmt.date(r.valid_to) : 'in corso' },
    { label: 'Modello', render: r => modelLabel(r.data.model) },
    { label: 'Tariffe', render: r => r.data.model === 'fixed' ? fmt.money(r.data.fixed_amount) : `${fmt.money(r.data.weekday_rate)} / ${fmt.money(r.data.holiday_rate)}` },
    { label: 'Confermata', render: r => r.data.confirmed ? badge('Sì', 'ok') : badge('No', 'warn') },
    { label: '', render: r => button('Modifica', { small: true, ic: 'edit', onClick: () => economicDialog(ctx, a, r) }) },
  ], a.economics, { empty: 'Nessuna condizione economica registrata.' });
  return card(`${a.center}`, {
    subtitle: `${p.role}${p.registration ? ' · matricola ' + p.registration : ''}${p.active ? '' : ' · non attiva'}`,
    actions: [button('Fascicolo', { small: true, ic: 'users', onClick: () => { ctx.setContext(a.center_id, ctx.app.month); ctx.go(`persone/${p.id}`); } }),
      button('Collega o separa', { small: true, ic: 'link', onClick: () => linkDialog(ctx, data, a) })],
  },
  a.contract ? h('p', { class: 'muted' }, `In vigore al ${fmt.date(data.on)}: `, h('strong', { text: `${a.contract.role} · ${a.contract.contract_type || 'contratto'} · ${fmt.number(a.contract.weekly_hours, 1)} ore settimanali` }))
    : alertBox(`Nessun contratto in vigore al ${fmt.date(data.on)}.`, 'warn'),
  h('div', { class: 'section-head' }, h('h3', { text: 'Contratti' }), button('Nuova decorrenza', { small: true, ic: 'plus', onClick: () => contractDialog(ctx, a, null) })), contracts,
  h('div', { class: 'section-head' }, h('h3', { text: 'Condizioni economiche' }), h('div', { class: 'row' },
    button('Applica a un mese', { small: true, ic: 'calculator', onClick: () => applyDialog(ctx, a) }),
    button('Nuova decorrenza', { small: true, ic: 'plus', onClick: () => economicDialog(ctx, a, null) }))), economics,
  a.history.length ? h('details', { class: 'history' }, h('summary', { text: `Storico (${a.history.length})` }), table([
    { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Operazione', key: 'label' }, { label: 'Motivazione', key: 'reason' }, { label: 'Da', key: 'actor' },
  ], a.history)) : null);
}

function intervalFields(record) {
  const from = input('valid_from', record?.valid_from || '', { type: 'date' });
  const to = input('valid_to', record?.valid_to || '', { type: 'date' });
  const reason = textarea('reason', '', { max: 1000, rows: 2 });
  return { from, to, reason, node: h('div', { class: 'form-grid' }, field('Decorrenza', from, { name: 'valid_from' }),
    field('Fine validità (vuota se in corso)', to, { name: 'valid_to' }), field('Motivazione (almeno 8 caratteri)', reason, { name: 'reason', wide: true })) };
}

async function contractDialog(ctx, a, record) {
  const d = record?.data || { role: a.person.role, contract_type: '', ccnl: '', level: '', weekly_hours: 36, part_time_percent: 100, note: '' };
  const role = select('role', a.roles, d.role);
  const type = input('contract_type', d.contract_type, { max: 150 });
  const ccnl = input('ccnl', d.ccnl, { max: 150 });
  const level = input('level', d.level, { max: 150 });
  const hours = input('weekly_hours', d.weekly_hours, { type: 'number', min: '0', step: 'any' });
  const pct = input('part_time_percent', d.part_time_percent, { type: 'number', min: '0', step: 'any' });
  const note = textarea('note', d.note, { max: 2000, rows: 2 });
  const interval = intervalFields(record);
  const form = h('form', { class: 'stack', novalidate: true }, interval.node,
    h('div', { class: 'form-grid' }, field('Ruolo', role, { name: 'role' }), field('Tipo di contratto', type, { name: 'contract_type' }),
      field('CCNL', ccnl, { name: 'ccnl' }), field('Livello', level, { name: 'level' }), field('Ore settimanali', hours, { name: 'weekly_hours' }),
      field('Percentuale part-time', pct, { name: 'part_time_percent' }), field('Note', note, { name: 'note', wide: true })),
    h('p', { class: 'small muted', text: 'Gli intervalli non si sovrappongono: chiudi prima quello precedente al giorno prima della nuova decorrenza.' }));
  const ok = await dialog(record ? 'Modifica contratto' : 'Nuovo contratto', form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    try {
      await put(`workforce/${a.center_id}/${a.person.id}/contracts`, { id: record?.id || '', version: record?.version || 0,
        valid_from: interval.from.value, valid_to: interval.to.value, reason: interval.reason.value,
        data: { role: role.value, contract_type: type.value, ccnl: ccnl.value, level: level.value, weekly_hours: Number(hours.value),
          part_time_percent: Number(pct.value), note: note.value } });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }], { wide: true });
  if (ok) { toast('Contratto salvato.', 'ok'); ctx.refresh(); }
}

async function economicDialog(ctx, a, record) {
  const form = agreementForm(record?.data || a.economic_proposal, a.absence_codes);
  const interval = intervalFields(record);
  const body = h('form', { class: 'stack', novalidate: true }, interval.node, form.node,
    h('p', { class: 'small muted', text: 'Le condizioni non cambiano da sole i mesi già compilati: si usano con «Applica a un mese».' }));
  const ok = await dialog(record ? 'Modifica condizioni economiche' : 'Nuove condizioni economiche', body, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    try {
      await put(`workforce/${a.center_id}/${a.person.id}/economics`, { id: record?.id || '', version: record?.version || 0,
        valid_from: interval.from.value, valid_to: interval.to.value, reason: interval.reason.value, data: form.value() });
      return true;
    } catch (err) { if (!showErrors(body, err)) toast(errorMessage(err), 'bad'); return false; }
  } }], { wide: true });
  if (ok) { toast('Condizioni economiche salvate.', 'ok'); ctx.refresh(); }
}

async function applyDialog(ctx, a) {
  const month = input('month', ctx.app.month, { type: 'month' });
  const out = h('div');
  const reason = textarea('reason', '', { max: 1000, rows: 2 });
  let preview = null;
  const load = async () => {
    try {
      preview = await get(`workforce/${a.center_id}/${a.person.id}/preview/${month.value}`);
      clear(out, preview.manual_required ? alertBox(preview.message, 'warn') : h('div', { class: 'stack' },
        h('p', null, `${preview.segments.length} ${preview.segments.length === 1 ? 'periodo' : 'periodi'} nel mese. Importo calcolato: `,
          h('strong', { text: preview.result?.amount === null || preview.result?.amount === undefined ? '—' : fmt.money(preview.result.amount) })),
        preview.result?.warnings?.length ? h('div', { class: 'alerts' }, preview.result.warnings.map(w => alertBox(w, 'warn'))) : null,
        preview.closed ? alertBox('Il mese è chiuso: non si può applicare.', 'bad') : null,
        preview.current ? alertBox('Esiste già un accordo per il mese: verrà sostituito (resta nello storico).', 'info') : null));
    } catch (err) { clear(out, alertBox(errorMessage(err), 'bad')); }
  };
  month.addEventListener('change', load);
  await load();
  const body = h('div', { class: 'stack' }, field('Mese', month), out, field('Motivazione (almeno 8 caratteri)', reason, { name: 'reason' }));
  const ok = await dialog('Applica le condizioni a un mese', body, [{ label: 'Annulla', value: null }, { label: 'Applica', kind: 'primary', onClick: async () => {
    try {
      await post(`workforce/${a.center_id}/${a.person.id}/apply`, { month: month.value, reason: reason.value,
        agreement_version: preview?.current?.version || 0 });
      return true;
    } catch (err) { if (!showErrors(body, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) { toast('Accordo del mese aggiornato.', 'ok'); ctx.refresh(); }
}

async function linkDialog(ctx, data, a) {
  let groups = [];
  try { groups = (await get('workforce')).groups; } catch (err) { toast(errorMessage(err), 'bad'); return; }
  const candidates = groups.filter(g => g.identity_id !== data.identity_id && !g.assignments.some(x => x.center_id === a.center_id));
  const target = select('identity_id', [['', data.assignments.length > 1 ? '— Separa questa scheda dalle altre strutture —' : '— Scegli la persona —'],
    ...candidates.map(g => [g.identity_id, `${g.name} · ${g.assignments.map(x => x.center).join(', ')}`])], '');
  const reason = textarea('reason', '', { max: 1000, rows: 2 });
  const body = h('div', { class: 'stack' },
    alertBox('Collega solo schede della stessa persona, dopo averlo verificato: il portale non lo fa mai in automatico.', 'warn'),
    field(`Collega la scheda di ${a.center} a`, target, { name: 'identity_id' }), field('Motivazione (almeno 8 caratteri)', reason, { name: 'reason' }));
  if (!candidates.length && data.assignments.length < 2) return dialog('Collega o separa', h('div', null, empty('Nessuna scheda collegabile', 'Non ci sono altre persone senza scheda in questa struttura.')), [{ label: 'Chiudi', value: null }]);
  const result = await dialog('Collega o separa', body, [{ label: 'Annulla', value: null }, { label: 'Conferma', kind: 'primary', onClick: async () => {
    const chosen = candidates.find(g => g.identity_id === target.value);
    try {
      return await post(`workforce/${a.center_id}/${a.person.id}/link`, { identity_id: target.value, identity_version: chosen?.version ?? 0,
        version: a.person.version, reason: reason.value });
    } catch (err) { if (!showErrors(body, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (result?.identity_id) { toast('Collegamento aggiornato.', 'ok'); ctx.go(`gruppo/${result.identity_id}`); }
}
