// Riepilogo: numeri del mese, attività da completare, strutture.
import { get } from '../api.js';
import { icon } from '../icons.js';
import { badge, button, card, empty, fmt, h, kpi, table } from '../ui.js';

const GREETING = () => {
  const hour = new Date().getHours();
  return hour < 13 ? 'Buongiorno' : hour < 18 ? 'Buon pomeriggio' : 'Buonasera';
};

export function todoItem(item, ctx) {
  const link = h('a', { class: 'grow', href: `#/${pageFor(item)}`, on: { click: () => {
    if (item.center_id) ctx.setContext(item.center_id, item.month);
  } } }, h('div', { class: 'title', text: item.title }),
  h('div', { class: 'detail', text: [item.center, item.detail, item.day ? fmt.date(item.day) : ''].filter(Boolean).join(' · ') }));
  return h('li', null, h('span', { class: `icon-dot ${item.priority === 'urgent' ? 'urgent' : ''}` }, icon(ICONS[item.category] || 'checks')), link,
    item.priority === 'urgent' ? h('span', { class: 'badge bad', text: 'Urgente' }) : null);
}

const ICONS = { orari: 'clock', consuntivi: 'calendar', calendario: 'shield', chiusure: 'lock', approvazioni: 'stamp', fascicoli: 'users',
  inserimento: 'checks', scadenze: 'alert', documenti: 'file', sostituzioni: 'layers', uscite: 'door', backup: 'database', importazione: 'upload' };
const PAGES = { orari: 'presenze', consuntivi: 'presenze', importazione: 'presenze', calendario: 'mese', chiusure: 'mese', approvazioni: 'approvazioni',
  fascicoli: 'persone', inserimento: 'persone', scadenze: 'persone', documenti: 'documenti', sostituzioni: 'copertura', uscite: 'uscite', backup: 'backup' };

function pageFor(item) {
  const page = PAGES[item.category] || '';
  if (['fascicoli', 'inserimento', 'scadenze'].includes(item.category) && item.person_id) return `persone/${item.person_id}`;
  return page;
}

export async function render(ctx) {
  const { app } = ctx;
  const month = app.me.today.slice(0, 7);
  const [overview, todo] = await Promise.all([get(`overview/${month}`), get(`todo/${month}`)]);
  const totals = overview.totals;
  const name = app.me.user.name.split(' ')[0];
  const quick = [];
  if (app.can('presenze.compila')) quick.push(button('Registra le presenze', { kind: 'primary', ic: 'calendar', onClick: () => ctx.go('presenze') }));
  if (app.can('mese.verifica')) quick.push(button('Controlla il mese', { ic: 'shield', onClick: () => ctx.go('mese') }));
  if (app.can('documenti.verifica')) quick.push(button('Documenti da verificare', { ic: 'file', onClick: () => ctx.go('documenti?review=received') }));
  if (app.can('approvazioni.approva')) quick.push(button('Approvazioni', { ic: 'stamp', onClick: () => ctx.go('approvazioni') }));

  const items = todo.items.slice(0, 8);
  const todoCard = card('Da completare', {
    subtitle: todo.total ? `${todo.total} attività, ${todo.urgent} urgenti` : 'Nessuna attività aperta',
    actions: todo.total > 8 ? button('Vedi tutto', { small: true, onClick: () => ctx.go('da-completare') }) : null, flush: true,
  }, items.length ? h('ul', { class: 'list' }, items.map(i => todoItem(i, ctx)))
    : empty('Tutto in ordine', 'Non ci sono attività aperte per il mese in corso.'));

  const centersCard = card('Strutture nel mese', { subtitle: fmt.month(month), flush: true },
    table([
      { label: 'Struttura', render: c => h('a', { href: '#/presenze', text: c.name, on: { click: () => ctx.setContext(c.id, month) } }) },
      { label: 'Stato', render: c => c.closed ? badge('Chiuso', 'ok', true) : c.recorded ? badge('In compilazione', 'info', true) : badge('Da iniziare', '', true) },
      { label: 'Approvazione', render: c => c.approval.enabled ? badge(c.approval.label, c.approval.status === 'hr_approved' ? 'ok' : 'brand') : h('span', { class: 'faint', text: 'Non attiva' }) },
      { label: 'Persone', num: true, render: c => fmt.number(c.people) },
      { label: 'Turni', num: true, render: c => fmt.number(c.shifts) },
      { label: 'Senza orari', num: true, render: c => c.missing ? h('span', { class: 'badge warn', text: String(c.missing) }) : '0' },
    ], overview.centers, { empty: 'Nessuna struttura assegnata.' }));

  return h('div', null,
    h('div', { class: 'page-head' }, h('div', null,
      h('div', { class: 'eyebrow', text: fmt.dateLong(app.me.today) }),
      h('h1', { text: `${GREETING()}, ${name}` }),
      h('p', { text: `${app.me.user.role_label} · ${app.me.centers.length === 1 ? app.me.centers[0].name : `${app.me.centers.length} strutture`}` })),
    h('div', { class: 'page-actions' }, quick)),
    h('div', { class: 'kpis' },
      kpi('Strutture', fmt.number(totals.centers), `${totals.closed} con il mese chiuso`),
      kpi('Persone attive', fmt.number(totals.people), 'nei registri delle strutture'),
      kpi('Turni registrati', fmt.number(totals.shifts), `nel mese di ${fmt.month(month)}`),
      kpi('Turni senza orari', fmt.number(totals.missing), totals.missing ? 'da completare' : 'nessuno', totals.missing ? 'warn' : 'ok'),
      kpi('Da consuntivare', fmt.number(totals.pending), 'fasce pianificate senza consuntivo', totals.pending ? 'warn' : 'ok'),
      kpi('Attività urgenti', fmt.number(todo.urgent), `su ${todo.total} da completare`, todo.urgent ? 'bad' : 'ok')),
    h('div', { class: 'grid grid-main' }, centersCard, todoCard));
}
