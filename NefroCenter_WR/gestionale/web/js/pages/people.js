// Persone e fascicoli: elenco della struttura e scheda completa della persona.
import { api, blobUrl, del, download, get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, confirmBox, dialog, empty, errorMessage, field, fmt, h, input, kpi, personCell,
  select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const STAGE_TONE = { incoming: 'info', active: 'ok', ended: '' };
const REVIEW_TONE = { received: 'warn', needs_correction: 'bad', verified: 'ok' };

export async function render(ctx) {
  if (ctx.params[0]) return detail(ctx, ctx.params[0] === 'nuova' ? null : ctx.params[0]);
  return listing(ctx);
}

async function listing(ctx) {
  const { app } = ctx;
  const data = await get(`hr/${app.cid}`);
  const state = { search: '', stage: '' };
  const rowsBox = h('div');
  const drawRows = () => {
    const q = state.search.trim().toLowerCase();
    const rows = data.employees.filter(p => (!state.stage || p.stage === state.stage)
      && (!q || `${p.name} ${p.registration} ${p.department}`.toLowerCase().includes(q)));
    clear(rowsBox, table([
      { label: 'Persona', render: p => personCell(p.name, [p.registration, p.department].filter(Boolean).join(' · ') || p.role) },
      { label: 'Ruolo', key: 'role' },
      { label: 'Ingresso', render: p => fmt.date(p.start) },
      { label: 'Stato', render: p => p.version ? badge(p.stage_label, STAGE_TONE[p.stage], true) : badge('Fascicolo da compilare', 'warn') },
      { label: 'Inserimento', render: p => p.total ? h('span', null, `${p.done}/${p.total}`, p.overdue ? h('span', { class: 'badge bad', text: `${p.overdue} in ritardo` }) : null) : '—' },
      { label: 'Documenti', num: true, render: p => p.to_review ? h('span', { class: 'badge warn', text: `${p.to_review} da verificare` }) : String(p.documents) },
    ], rows, { empty: 'Nessuna persona corrisponde ai filtri.', onRow: p => ctx.go(`persone/${p.id}`) }));
  };
  drawRows();
  const incoming = data.employees.filter(p => p.stage === 'incoming').length;
  const toReview = data.employees.reduce((n, p) => n + p.to_review, 0);
  return h('div', null,
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Persone e fascicoli' }),
      h('h1', { text: data.center.name }), h('p', { text: 'Un fascicolo per ogni persona: dati, contratto, inserimento, documenti e scadenze.' })),
    h('div', { class: 'page-actions' },
      app.can('hr.modello') ? button('Modello di inserimento', { ic: 'sliders', onClick: () => templateDialog(ctx, data) }) : null,
      button('Nuova persona', { kind: 'primary', ic: 'plus', onClick: () => ctx.go('persone/nuova') }))),
    h('div', { class: 'kpis' }, kpi('Persone', fmt.number(data.employees.length), `${data.employees.filter(p => p.active).length} abilitate alle presenze`),
      kpi('In ingresso', fmt.number(incoming), 'inserimenti in corso', incoming ? 'warn' : ''),
      kpi('Scadenze entro 30 giorni', fmt.number(data.deadlines.length), `${data.deadlines.filter(d => d.late).length} già superate`, data.deadlines.some(d => d.late) ? 'bad' : ''),
      kpi('Documenti da verificare', fmt.number(toReview), 'in attesa di HR centrale', toReview ? 'warn' : 'ok')),
    h('div', { class: 'grid grid-main' },
      card('Elenco', { flush: true, actions: [
        h('input', { type: 'search', placeholder: 'Cerca nome, matricola o reparto', 'aria-label': 'Cerca persona', on: { input: e => { state.search = e.target.value; drawRows(); } } }),
        h('select', { 'aria-label': 'Stato', on: { change: e => { state.stage = e.target.value; drawRows(); } } },
          h('option', { value: '', text: 'Tutti gli stati' }), Object.entries(data.stages).map(([v, l]) => h('option', { value: v, text: l }))),
      ] }, rowsBox),
      card('Prossime scadenze', { subtitle: 'Contratti, documenti, qualifiche e attività', flush: true },
        data.deadlines.length ? h('ul', { class: 'list' }, data.deadlines.slice(0, 12).map(d => h('li', null,
          h('div', { class: 'grow' }, h('div', { class: 'title', text: d.label }), h('div', { class: 'detail', text: `${d.name} · ${fmt.date(d.date)}` })),
          d.late ? badge('Superata', 'bad') : badge(fmt.date(d.date), 'warn'))))
          : empty('Nessuna scadenza', 'Nei prossimi 30 giorni non ci sono scadenze.'))));
}

// ---------- Scheda della persona ----------
async function detail(ctx, pid) {
  const { app } = ctx;
  const data = pid ? await get(`hr/${app.cid}/${pid}`) : await blank(app);
  const fieldsMeta = await fieldDefinitions();
  const state = { tab: ctx.query.tab || 'anagrafica', dirty: false };
  const root = h('div');
  const values = { ...data.profile.fields };
  const custom = { ...data.profile.custom };
  const person = { name: data.person.name || '', role: data.person.role || data.roles[0], registration: data.person.registration || '',
    active: data.person.active ?? true, stage: data.profile.stage };

  const draw = () => clear(root, view());
  const save = async () => {
    try {
      const body = { name: person.name, role: person.role, registration: person.registration, active: person.active, stage: person.stage,
        fields: values, custom, version: data.profile.version };
      const result = pid ? await put(`hr/${app.cid}/${pid}`, body) : await post(`hr/${app.cid}`, body);
      toast('Fascicolo salvato.', 'ok');
      state.dirty = false;
      if (!pid) return ctx.go(`persone/${result.person_id}`);
      return ctx.refresh();
    } catch (err) {
      const form = root.querySelector('form');
      if (!(form && showErrors(form, err))) toast(errorMessage(err), 'bad');
    }
  };
  const sections = [
    { id: 'anagrafica', label: 'Anagrafica' }, { id: 'recapiti', label: 'Recapiti' }, { id: 'contratto', label: 'Contratto' },
    { id: 'amministrazione', label: 'Amministrazione' }, { id: 'qualifiche', label: 'Qualifiche' },
    ...(data.template.fields.length ? [{ id: 'aggiuntivi', label: 'Campi aggiuntivi' }] : []),
    ...(pid ? [{ id: 'inserimento', label: 'Inserimento', count: data.progress.total - data.progress.done },
      { id: 'documenti', label: 'Documenti', count: data.documents.length }, { id: 'scadenze', label: 'Scadenze' },
      { id: 'storico', label: 'Storico' }] : []),
    { id: 'struttura', label: 'Struttura' },
  ];

  function view() {
    const header = h('div', { class: 'page-head' }, h('div', null,
      h('div', { class: 'eyebrow' }, h('a', { href: '#/persone', text: '← Persone e fascicoli' })),
      h('h1', { text: person.name || 'Nuova persona' }),
      h('div', { class: 'row' }, badge(data.center.name, 'brand'), person.role ? badge(person.role) : null,
        badge({ incoming: 'In ingresso', active: 'In servizio', ended: 'Cessato' }[person.stage], STAGE_TONE[person.stage], true),
        pid ? badge(`Versione ${data.profile.version}`) : null)),
    h('div', { class: 'page-actions' }, button(pid ? 'Salva le modifiche' : 'Crea la persona', { kind: 'primary', ic: 'check', onClick: save })));
    const missing = data.missing?.length ? alertBox(`Campi richiesti dalla struttura ancora vuoti: ${data.missing.join(', ')}.`, 'warn') : null;
    return h('div', null, header, missing ? h('div', { class: 'alerts' }, missing) : null,
      tabs(sections, state.tab, id => { state.tab = id; draw(); }), card(null, {}, section()));
  }

  function bindInput(el, target, key, after) {
    el.addEventListener('input', () => {
      target[key] = el.type === 'checkbox' ? el.checked : el.value;
      state.dirty = true;
      after?.();
    });
    el.addEventListener('change', () => { target[key] = el.type === 'checkbox' ? el.checked : el.value; state.dirty = true; });
    return el;
  }

  function section() {
    if (['anagrafica', 'recapiti', 'contratto', 'amministrazione', 'qualifiche'].includes(state.tab)) {
      const form = h('form', { class: 'form-grid', on: { submit: e => { e.preventDefault(); save(); } } });
      if (state.tab === 'anagrafica') {
        form.append(field('Nome e cognome (come nel registro)', bindInput(input('name', person.name, { max: 150 }), person, 'name'), { name: 'name', required: true }),
          field('Ruolo', bindInput(select('role', data.roles, person.role), person, 'role'), { name: 'role' }),
          field('Matricola', bindInput(input('registration', person.registration, { max: 80 }), person, 'registration'), { name: 'registration' }),
          field('Stato', bindInput(select('stage', [['incoming', 'In ingresso'], ['active', 'In servizio'], ['ended', 'Cessato']], person.stage), person, 'stage'), { name: 'stage' }),
          h('div', { class: 'field' }, h('span', { class: 'small faint', text: ' ' }), bindCheckbox(checkbox('active', person.active, 'Abilitata alle presenze'), person, 'active')));
      }
      for (const f of fieldsMeta.filter(f => f.section === state.tab)) {
        const type = { date: 'date', email: 'email', tel: 'tel' }[f.type] || 'text';
        const el = f.type === 'textarea' ? textarea(f.key, values[f.key], { max: f.max_length, rows: 4 }) : input(f.key, values[f.key], { type, max: f.max_length });
        form.append(field(f.label, bindInput(el, values, f.key), { name: f.key, wide: f.type === 'textarea' }));
      }
      return form;
    }
    if (state.tab === 'aggiuntivi') {
      return h('form', { class: 'form-grid' }, data.template.fields.map(d => {
        const el = d.type === 'boolean' ? select(d.id, [['', 'Da indicare'], ['si', 'Sì'], ['no', 'No']], custom[d.id] || '')
          : input(d.id, custom[d.id] || '', { type: d.type === 'date' ? 'date' : 'text', max: 500 });
        return field(d.label, bindInput(el, custom, d.id), { name: 'custom_' + d.id, required: d.required });
      }));
    }
    if (state.tab === 'inserimento') return tasksSection(ctx, data, pid);
    if (state.tab === 'documenti') return documentsSection(ctx, data, pid);
    if (state.tab === 'scadenze') {
      return table([{ label: 'Scadenza', key: 'label' }, { label: 'Data', render: d => fmt.date(d.date) },
        { label: 'Sezione', key: 'section' }, { label: 'Stato', render: d => d.late ? badge('Superata', 'bad') : badge('In arrivo', 'warn') }],
      data.deadlines, { empty: 'Nessuna scadenza registrata.' });
    }
    if (state.tab === 'storico') {
      return table([{ label: 'Versione', key: 'version' }, { label: 'Salvato il', render: r => fmt.stamp(r.at) }, { label: 'Da', key: 'actor' }],
        data.history, { empty: 'Nessuna versione.' });
    }
    const s = data.structure.fields;
    return h('div', { class: 'stack' }, h('p', { class: 'muted', text: 'Recapiti della struttura di riferimento (dalla rubrica delle strutture).' }),
      table([{ label: 'Voce', key: 'k' }, { label: 'Valore', key: 'v' }], [
        ['Ragione sociale', s.legal_name], ['Indirizzo', [s.address, s.postal_code, s.city, s.province].filter(Boolean).join(', ')],
        ['Telefono', s.phone], ['Email HR', s.hr_email], ['Referente', s.contact_name], ['Direttore', s.director],
      ].map(([k, v]) => ({ k, v: v || '—' }))));
  }

  function bindCheckbox(label, target, key) {
    label.querySelector('input').addEventListener('change', e => { target[key] = e.target.checked; state.dirty = true; });
    return label;
  }

  window.onbeforeunload = () => (state.dirty ? true : undefined);
  draw();
  return root;
}

async function blank(app) {
  const listing = await get(`hr/${app.cid}`);
  const config = await get(`centers/${app.cid}/config`);
  return { center: listing.center, person: {}, profile: { version: 0, stage: 'incoming', fields: {}, custom: {} }, tasks: [], progress: { done: 0, total: 0 },
    documents: [], deadlines: [], template: listing.template, missing: [], history: [], roles: config.config.roles,
    structure: (await get(`structures/${app.cid}`)).structure, categories: [], can_review: false };
}

let definitionsCache = null;
async function fieldDefinitions() {
  if (!definitionsCache) definitionsCache = (await get('hr-fields')).fields;
  return definitionsCache;
}

function tasksSection(ctx, data, pid) {
  const TONE = { todo: '', doing: 'info', done: 'ok', na: '' };
  return h('div', { class: 'stack' },
    h('p', { class: 'muted', text: `${data.progress.done} attività su ${data.progress.total} completate${data.progress.overdue ? `, ${data.progress.overdue} in ritardo` : ''}.` }),
    table([
      { label: 'Fase', key: 'phase' }, { label: 'Attività', key: 'label' }, { label: 'Referente', key: 'owner' },
      { label: 'Scadenza', render: t => fmt.date(t.due) },
      { label: 'Stato', render: t => badge(t.status_label, TONE[t.status]) },
      { label: '', render: t => button('Aggiorna', { small: true, onClick: () => taskDialog(ctx, data, pid, t) }) },
    ], data.tasks, { empty: 'Nessuna attività di inserimento.' }));
}

async function taskDialog(ctx, data, pid, task) {
  const status = select('status', [['todo', 'Da fare'], ['doing', 'In corso'], ['done', 'Completata'], ['na', 'Non applicabile']], task.status);
  const due = input('due', task.due, { type: 'date' });
  const owner = input('owner', task.owner, { max: 150 });
  const note = textarea('note', task.note, { max: 1000 });
  const form = h('form', { class: 'form-grid' }, field('Stato', status, { name: 'status' }), field('Scadenza', due, { name: 'due' }),
    field('Referente', owner, { name: 'owner', wide: true }), field('Nota (obbligatoria se non applicabile)', note, { name: 'note', wide: true }));
  const ok = await dialog(task.label, form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    try {
      await put(`hr/${ctx.app.cid}/${pid}/tasks/${task.id}`, { status: status.value, due: due.value, owner: owner.value, note: note.value, version: data.profile.version });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) ctx.go(`persone/${pid}?tab=inserimento`), ctx.refresh();
}

function documentsSection(ctx, data, pid) {
  const fileInput = h('input', { type: 'file', accept: '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg', 'aria-label': 'File da allegare' });
  const category = select('category', data.categories, 'Documento amministrativo');
  const expiry = input('expiry', '', { type: 'date' });
  const upload = button('Allega', { kind: 'primary', ic: 'upload', onClick: async () => {
    const file = fileInput.files[0];
    if (!file) return toast('Scegli prima un file.', 'bad');
    if (file.size > 6 * 1024 * 1024) return toast('Il file supera 6 MiB.', 'bad');
    try {
      const params = new URLSearchParams({ name: file.name, category: category.value, expiry: expiry.value });
      await api(`hr/${ctx.app.cid}/${pid}/documents?${params}`, { method: 'POST', raw: await file.arrayBuffer(), contentType: file.type || 'application/octet-stream' });
      toast('Documento allegato: in attesa della verifica di HR.', 'ok');
      ctx.go(`persone/${pid}?tab=documenti`);
      ctx.refresh();
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } });
  return h('div', { class: 'stack' },
    h('fieldset', null, h('legend', { text: 'Allega un documento' }), h('div', { class: 'form-grid' },
      field('File (PDF, PNG o JPEG, massimo 6 MiB)', fileInput), field('Categoria', category), field('Scadenza (se prevista)', expiry)),
    h('div', { class: 'form-actions' }, upload)),
    table([
      { label: 'Documento', render: d => h('div', null, h('strong', { text: d.name }), h('div', { class: 'small faint', text: `${d.category} · ${fmt.bytes(d.size)}` })) },
      { label: 'Scadenza', render: d => d.expiry ? (d.review.expired ? badge(`Scaduto ${fmt.date(d.expiry)}`, 'bad') : fmt.date(d.expiry)) : '—' },
      { label: 'Verifica', render: d => badge(d.review.label, REVIEW_TONE[d.review.status]) },
      { label: 'Caricato', render: d => `${fmt.date(d.uploaded_at)} · ${d.uploaded_by}` },
      { label: '', render: d => h('div', { class: 'row' }, button('Apri', { small: true, ic: 'eye', onClick: () => openDocument(ctx, d) }),
        button('', { small: true, kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => removeDocument(ctx, pid, d) })) },
    ], data.documents, { empty: 'Nessun documento allegato.' }));
}

export async function openDocument(ctx, doc, after) {
  const url = await blobUrl(`documents/${doc.center_id}/${doc.id}/content`);
  const review = await get(`documents/${doc.center_id}/${doc.id}/review`);
  const viewer = doc.mime === 'application/pdf'
    ? h('iframe', { src: url, title: doc.name, class: 'doc-frame' })
    : h('img', { src: url, alt: doc.name, class: 'doc-image' });
  const note = textarea('note', '', { max: 2000, rows: 2 });
  const actions = [{ label: 'Chiudi', value: null }, { label: 'Scarica', onClick: async () => {
    await download(`documents/${doc.center_id}/${doc.id}/content?download=1`, doc.name); return false;
  } }];
  const decide = status => async () => {
    try {
      await post(`documents/${doc.center_id}/${doc.id}/review`, { status, note: note.value, version: review.review.version });
      toast('Verifica registrata.', 'ok');
      return true;
    } catch (err) { toast(errorMessage(err), 'bad'); return false; }
  };
  if (review.can_review && review.review.status !== 'verified') actions.push({ label: 'Verificato', kind: 'primary', onClick: decide('verified') });
  if (review.can_review && review.review.status !== 'needs_correction') actions.push({ label: 'Chiedi correzione', onClick: decide('needs_correction') });
  if (review.can_resubmit) actions.push({ label: 'Ripresenta corretto', kind: 'primary', onClick: decide('received') });
  const body = h('div', { class: 'stack' }, h('div', { class: 'row' }, badge(review.review.label, REVIEW_TONE[review.review.status]),
    review.review.expired ? badge('Scaduto', 'bad') : null, h('span', { class: 'small faint', text: `SHA-256 ${doc.sha256.slice(0, 16)}…` })),
  viewer,
  (review.can_review || review.can_resubmit) ? field('Nota per la verifica (obbligatoria per correzioni e ripresentazioni)', note) : null,
  h('h3', { text: 'Storico della verifica' }),
  table([{ label: 'Esito', key: 'label' }, { label: 'Nota', key: 'note' }, { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Da', key: 'actor' }], review.history));
  const done = await dialog(doc.name, body, actions, { wide: true });
  URL.revokeObjectURL(url);
  if (done) (after ? after() : ctx.refresh());
}

async function removeDocument(ctx, pid, doc) {
  const reason = await confirmBox('Rimuovere il documento?', `«${doc.name}» verrà rimosso dal fascicolo. L’operazione resta nel registro attività.`,
    { reason: true, danger: true, confirmLabel: 'Rimuovi' });
  if (!reason) return;
  try {
    await del(`documents/${ctx.app.cid}/${doc.id}`, { reason });
    toast('Documento rimosso.', 'ok');
    ctx.refresh();
  } catch (err) { toast(errorMessage(err), 'bad'); }
}

async function templateDialog(ctx, data) {
  const tpl = data.template;
  const tasks = tpl.tasks.map(t => ({ ...t }));
  const fields = tpl.fields.map(f => ({ ...f }));
  const box = h('div');
  const drawBox = () => clear(box,
    h('h3', { text: 'Attività' }),
    table([{ label: 'Fase', key: 'phase' }, { label: 'Attività', key: 'label' }, { label: 'Referente', key: 'owner' },
      { label: 'Giorni rispetto all’ingresso', num: true, key: 'offset' },
      { label: '', render: t => button('', { small: true, kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi attività', onClick: () => { tasks.splice(tasks.indexOf(t), 1); drawBox(); } }) }], tasks),
    h('h3', { text: 'Campi aggiuntivi del fascicolo' }),
    table([{ label: 'Campo', key: 'label' }, { label: 'Tipo', key: 'type' }, { label: 'Obbligatorio', render: f => f.required ? 'Sì' : 'No' },
      { label: '', render: f => button('', { small: true, kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi campo', onClick: () => { fields.splice(fields.indexOf(f), 1); drawBox(); } }) }],
    fields, { empty: 'Nessun campo aggiuntivo.' }));
  drawBox();
  const label = input('label', '', { max: 200 });
  const phase = select('phase', ['Prima dell’ingresso', 'Primo giorno', 'Inserimento'], 'Inserimento');
  const offset = input('offset', '7', { type: 'number' });
  const fieldLabel = input('flabel', '', { max: 100 });
  const fieldType = select('ftype', [['text', 'Testo'], ['date', 'Data'], ['number', 'Numero'], ['boolean', 'Sì/No']], 'text');
  const body = h('div', { class: 'stack' }, box,
    h('fieldset', null, h('legend', { text: 'Aggiungi attività' }), h('div', { class: 'form-grid' }, field('Attività', label), field('Fase', phase), field('Giorni', offset)),
      button('Aggiungi', { small: true, ic: 'plus', onClick: () => {
        if (!label.value.trim()) return;
        tasks.push({ id: `a${Date.now().toString(36)}`, label: label.value.trim(), phase: phase.value, owner: '', offset: Number(offset.value || 0) });
        label.value = ''; drawBox();
      } })),
    h('fieldset', null, h('legend', { text: 'Aggiungi campo' }), h('div', { class: 'form-grid' }, field('Etichetta', fieldLabel), field('Tipo', fieldType)),
      button('Aggiungi', { small: true, ic: 'plus', onClick: () => {
        if (!fieldLabel.value.trim()) return;
        fields.push({ id: `c${Date.now().toString(36)}`, label: fieldLabel.value.trim(), type: fieldType.value, required: false });
        fieldLabel.value = ''; drawBox();
      } })));
  const ok = await dialog('Modello di inserimento', body, [{ label: 'Annulla', value: null }, { label: 'Salva il modello', kind: 'primary', onClick: async () => {
    try {
      await put(`hr/${ctx.app.cid}/template`, { tasks, fields, version: tpl.version });
      toast('Modello salvato: vale per i nuovi fascicoli.', 'ok');
      return true;
    } catch (err) { toast(errorMessage(err), 'bad'); return false; }
  } }], { wide: true });
  if (ok) ctx.refresh();
}
