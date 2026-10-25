// Da completare: tutte le attività aperte ricavate dai dati, filtrabili per categoria.
import { get } from '../api.js';
import { button, card, clear, empty, fmt, h, kpi } from '../ui.js';
import { todoItem } from './home.js';

const LABELS = { orari: 'Orari', consuntivi: 'Consuntivi', importazione: 'Importazioni', calendario: 'Calendario', chiusure: 'Chiusure',
  approvazioni: 'Approvazioni', fascicoli: 'Fascicoli', inserimento: 'Inserimento', scadenze: 'Scadenze', documenti: 'Documenti',
  sostituzioni: 'Sostituzioni', uscite: 'Uscite', backup: 'Backup' };

export async function render(ctx) {
  const data = await get(`todo/${ctx.app.month}`);
  let filter = ctx.query.cat || '';
  const listBox = h('div');
  const filters = h('div', { class: 'row' });
  const draw = () => {
    clear(filters, button(`Tutte (${data.total})`, { small: true, kind: filter ? '' : 'primary', onClick: () => { filter = ''; draw(); } }),
      Object.entries(data.counts).map(([cat, n]) => button(`${LABELS[cat] || cat} (${n})`, { small: true, kind: filter === cat ? 'primary' : '', onClick: () => { filter = cat; draw(); } })));
    const items = data.items.filter(i => !filter || i.category === filter);
    clear(listBox, items.length ? h('ul', { class: 'list' }, items.map(i => todoItem(i, ctx)))
      : empty('Niente da completare', 'Per i filtri scelti non ci sono attività aperte.'));
  };
  draw();
  return h('div', null,
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Da completare' }),
      h('h1', { text: `Attività aperte · ${fmt.month(data.month)}` }),
      h('p', { text: 'L’elenco si aggiorna da solo: quando sistemi un dato, la voce sparisce.' }))),
    h('div', { class: 'kpis' }, kpi('Attività aperte', fmt.number(data.total), `al ${fmt.date(data.as_of)}`),
      kpi('Urgenti', fmt.number(data.urgent), 'scadute o bloccanti', data.urgent ? 'bad' : 'ok'),
      kpi('Strutture', fmt.number(data.centers.length), 'considerate')),
    card(null, { flush: true }, h('div', { class: 'card-body' }, filters), listBox));
}
