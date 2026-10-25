// Archivio documenti: tutti gli allegati dei fascicoli delle strutture autorizzate, con filtri e verifica HR.
import { get } from '../api.js';
import { badge, button, card, clear, errorMessage, fmt, h, input, kpi, select, table, toast } from '../ui.js';
import { openDocument } from './people.js';

const TONE = { received: 'warn', needs_correction: 'bad', verified: 'ok' };

export async function render(ctx) {
  const filters = { cid: ctx.query.cid || 'all', person: ctx.query.person || '', category: ctx.query.category || '',
    expiry: ctx.query.expiry || 'all', review: ctx.query.review || 'all' };
  const listBox = h('div');
  const kpiBox = h('div', { class: 'kpis' });
  let data = await load(filters);
  const center = select('cid', [['all', 'Tutte le strutture'], ...(data.centers || ctx.app.me.centers).map(c => [c.id, c.name])], filters.cid);
  const person = input('person', filters.person, { placeholder: 'Persona o matricola', max: 150 });
  const category = select('category', [['', 'Tutte le categorie'], ...data.categories.map(c => [c, c])], filters.category);
  const expiry = select('expiry', [['all', 'Qualsiasi scadenza'], ['expired', 'Scaduti'], ['soon', 'In scadenza entro 30 giorni'],
    ['dated', 'Con scadenza'], ['none', 'Senza scadenza']], filters.expiry);
  const review = select('review', [['all', 'Qualsiasi verifica'], ['received', 'Da verificare'], ['needs_correction', 'Da correggere'],
    ['verified', 'Verificati'], ['expired', 'Scaduti (verifica)']], filters.review);
  for (const [el, label] of [[center, 'Struttura'], [person, 'Persona'], [category, 'Categoria'], [expiry, 'Scadenza'], [review, 'Verifica']]) {
    el.setAttribute('aria-label', label);
  }

  const draw = () => {
    const docs = data.documents;
    clear(kpiBox,
      kpi('Documenti', fmt.number(data.total), 'con i filtri scelti'),
      kpi('Da verificare', fmt.number(docs.filter(d => d.review.status === 'received').length), 'in attesa di HR centrale', 'warn'),
      kpi('Da correggere', fmt.number(docs.filter(d => d.review.status === 'needs_correction').length), 'restituiti alla struttura'),
      kpi('Scaduti', fmt.number(docs.filter(d => d.late).length), 'da rinnovare', docs.some(d => d.late) ? 'bad' : 'ok'));
    clear(listBox, table([
      { label: 'Documento', render: d => h('div', null, h('strong', { text: d.name }), h('div', { class: 'small faint', text: `${d.category} · ${fmt.bytes(d.size)}` })) },
      { label: 'Persona', render: d => h('div', null, h('div', { text: d.person }), h('div', { class: 'small faint', text: d.center })) },
      { label: 'Scadenza', render: d => d.expiry ? (d.late ? badge(`Scaduto ${fmt.date(d.expiry)}`, 'bad') : fmt.date(d.expiry)) : '—' },
      { label: 'Verifica', render: d => badge(d.review.label, TONE[d.review.status]) },
      { label: 'Caricato', render: d => h('div', { class: 'small' }, fmt.date(d.uploaded_at), h('div', { class: 'faint', text: d.uploaded_by })) },
      { label: '', render: d => button('Apri', { small: true, ic: 'eye', onClick: () => openDocument(ctx, d, reload) }) },
    ], docs, { empty: 'Nessun documento con questi filtri.', onRow: d => openDocument(ctx, d, reload) }));
  };
  const reload = async () => {
    Object.assign(filters, { cid: center.value, person: person.value.trim(), category: category.value, expiry: expiry.value, review: review.value });
    try { data = await load(filters); draw(); } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  for (const el of [center, category, expiry, review]) el.addEventListener('change', reload);
  let timer = null;
  person.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(reload, 300); });
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Documenti' }),
      h('h1', { text: 'Archivio documenti del personale' }),
      h('p', { text: data.can_review ? 'Apri un documento per vederlo e registrare l’esito della verifica.'
        : 'I documenti caricati dalle strutture vengono verificati da HR centrale.' }))),
    kpiBox,
    card(null, { flush: true }, h('div', { class: 'card-body filters' }, center, person, category, expiry, review), listBox));
}

function load(filters) {
  const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  return get(`documents?${params}`);
}
