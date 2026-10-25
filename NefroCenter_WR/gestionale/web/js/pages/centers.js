// Strutture del gruppo: creazione (anche copiando i parametri di un'altra), ridenominazione, disattivazione.
import { get, post, put } from '../api.js';
import { badge, button, card, checkbox, dialog, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, toast } from '../ui.js';

export async function render(ctx) {
  const data = await get('centers');
  const list = data.centers;
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Strutture' }),
      h('p', { text: 'Ogni struttura ha il suo registro, i suoi parametri e le persone assegnate. Una struttura disattivata resta consultabile dall’amministratore.' })),
    h('div', { class: 'page-actions' }, button('Nuova struttura', { kind: 'primary', ic: 'plus', onClick: () => create(ctx, list) }))),
    h('div', { class: 'kpis' }, kpi('Strutture attive', fmt.number(list.filter(c => c.active).length), `su ${list.length}`)),
    card('Elenco', { flush: true }, table([
      { label: 'Struttura', render: c => h('strong', { text: c.name }) },
      { label: 'Codice', render: c => h('span', { class: 'mono', text: c.code }) },
      { label: 'Parametri', render: c => `versione ${c.config_version}` },
      { label: 'Stato', render: c => c.active ? badge('Attiva', 'ok', true) : badge('Disattivata', '') },
      { label: '', render: c => h('div', { class: 'row' },
        button('Parametri', { small: true, ic: 'sliders', onClick: () => { ctx.setContext(c.id, ctx.app.month); ctx.go('parametri'); } }),
        button('Modifica', { small: true, ic: 'edit', onClick: () => edit(ctx, c) })) },
    ], list, { empty: 'Nessuna struttura: creane una.' })));
}

async function create(ctx, list) {
  const name = input('name', '', { max: 150 });
  const code = input('code', '', { max: 30 });
  const copy = select('copy_from', [['', 'Parametri iniziali standard'], ...list.map(c => [c.id, `Copia da ${c.name}`])], '');
  const form = h('form', { class: 'stack', novalidate: true },
    field('Nome della struttura', name, { name: 'name', required: true }),
    field('Codice', code, { name: 'code', required: true, hint: 'Da 2 a 30 caratteri: lettere maiuscole, numeri, trattino. Compare nei nomi dei file.' }),
    field('Parametri di partenza', copy, { name: 'copy_from' }));
  const ok = await dialog('Nuova struttura', form, [{ label: 'Annulla', value: null }, { label: 'Crea', kind: 'primary', onClick: async () => {
    try {
      const res = await post('centers', { name: name.value, code: code.value.toUpperCase(), copy_from: copy.value });
      return res.id;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (!ok) return;
  toast('Struttura creata. Ricordati di assegnarla agli account che devono usarla.', 'ok');
  await ctx.reloadProfile();
  if (!ctx.app.cid) return ctx.setContext(ok, ctx.app.month);
  ctx.refresh();
}

async function edit(ctx, center) {
  const name = input('name', center.name, { max: 150 });
  const active = checkbox('active', center.active, 'Struttura attiva');
  const form = h('form', { class: 'stack', novalidate: true }, field('Nome della struttura', name, { name: 'name', required: true }), active,
    h('p', { class: 'small muted', text: 'Una struttura disattivata sparisce dai menu degli utenti; i dati restano conservati.' }));
  const ok = await dialog(`Modifica · ${center.name}`, form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    try {
      await put(`centers/${center.id}`, { name: name.value, active: active.querySelector('input').checked, version: center.version });
      return true;
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (!ok) return;
  toast('Struttura aggiornata.', 'ok');
  await ctx.reloadProfile();
  ctx.refresh();
}
