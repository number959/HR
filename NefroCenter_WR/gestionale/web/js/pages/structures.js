// Rubrica delle strutture: dati societari, sede, recapiti, referenti. Non tocca presenze né assegnazioni.
import { get, put } from '../api.js';
import { badge, button, card, clear, errorMessage, field, fmt, h, input, showErrors, textarea, toast } from '../ui.js';

export async function render(ctx) {
  const data = await get('structures');
  const selected = ctx.params[0] || data.structures[0]?.center_id;
  const detailBox = h('div');
  const list = card('Strutture', { flush: true }, h('ul', { class: 'list' }, data.structures.map(s => h('li', { class: s.center_id === selected ? 'selected' : null },
    h('a', { class: 'grow', href: `#/rubrica/${s.center_id}` }, h('div', { class: 'title', text: s.name }),
      h('div', { class: 'detail', text: [s.fields.city, s.fields.phone].filter(Boolean).join(' · ') || 'Scheda da completare' })),
    s.version ? null : badge('Vuota', 'warn')))));
  const current = data.structures.find(s => s.center_id === selected);
  if (current) clear(detailBox, sheet(ctx, current, data.fields));
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Rubrica strutture' }),
      h('h1', { text: 'Recapiti e dati delle strutture' }),
      h('p', { text: 'I recapiti appartengono alla struttura: non vengono copiati nei fascicoli delle persone.' }))),
    h('div', { class: 'grid grid-side' }, list, detailBox));
}

function sheet(ctx, s, fields) {
  const inputs = {};
  const sections = [...new Set(fields.map(f => f.section))];
  const form = h('form', { class: 'stack', novalidate: true }, sections.map(section => h('fieldset', null, h('legend', { text: section }),
    h('div', { class: 'form-grid' }, fields.filter(f => f.section === section).map(f => {
      const el = f.type === 'textarea' ? textarea(f.key, s.fields[f.key], { max: f.max_length, rows: 4 })
        : input(f.key, s.fields[f.key], { max: f.max_length, type: { tel: 'tel', email: 'email', url: 'url' }[f.type] || 'text' });
      inputs[f.key] = el;
      return field(f.label, el, { name: f.key, wide: f.type === 'textarea' });
    })))),
  h('div', { class: 'form-actions' }, button('Salva la scheda', { kind: 'primary', type: 'submit', ic: 'check' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const values = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
    try {
      await put(`structures/${s.center_id}`, { fields: values, version: s.version });
      toast('Scheda salvata.', 'ok');
      ctx.refresh();
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return card(s.name, {
    subtitle: s.version ? `Aggiornata il ${fmt.stamp(s.updated_at)} da ${s.updated_by}` : 'Scheda non ancora compilata',
    actions: [h('span', { class: 'mono small', text: s.code }), s.active ? null : badge('Disattivata', '')],
  }, form);
}
