// Statistiche: andamento per mese, struttura, ruolo, causale e persona, qualità dei dati, sintesi HR. Filtri in una riga sopra i risultati.
import { download, get } from '../api.js';
import { columnChart } from '../chart.js';
import { alertBox, badge, button, card, clear, errorMessage, fmt, h, input, kpi, select, shiftMonth, table, tabs, toast } from '../ui.js';

const SHORT = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];

export async function render(ctx) {
  const { app } = ctx;
  const filters = { from: ctx.query.from || shiftMonth(app.month, -5), to: ctx.query.to || app.month, cid: ctx.query.cid || 'all', role: '', person_id: '' };
  const from = input('from', filters.from, { type: 'month' });
  const to = input('to', filters.to, { type: 'month' });
  const center = select('cid', [['all', 'Tutte le strutture'], ...app.me.centers.filter(c => c.active).map(c => [c.id, c.name])], filters.cid);
  const role = select('role', [['', 'Tutti i ruoli']], '');
  const person = select('person_id', [['', 'Tutte le persone']], '');
  for (const [el, label] of [[from, 'Dal mese'], [to, 'Al mese'], [center, 'Struttura'], [role, 'Ruolo'], [person, 'Persona']]) el.setAttribute('aria-label', label);
  const csv = button('Scarica CSV', { ic: 'download' });
  const results = h('div', { class: 'stack' });
  let tab = 'mesi';
  let data = null;

  const load = async () => {
    Object.assign(filters, { from: from.value, to: to.value, cid: center.value, role: role.value, person_id: center.value === 'all' ? '' : person.value });
    results.classList.add('loading');
    try {
      data = await get(`statistics?${query(filters)}`);
      fillOptions();
      draw();
    } catch (err) {
      clear(results, alertBox(errorMessage(err), 'bad'));
    } finally { results.classList.remove('loading'); }
  };
  const fillOptions = () => {
    role.replaceChildren(...[['', 'Tutti i ruoli'], ...data.options.roles.map(r => [r, r])].map(([v, l]) => h('option', { value: v, text: l, selected: v === filters.role })));
    person.replaceChildren(...[['', 'Tutte le persone'], ...data.options.people.map(p => [p.id, p.name])].map(([v, l]) => h('option', { value: v, text: l, selected: v === filters.person_id })));
    person.classList.toggle('hidden', filters.cid === 'all');
    csv.disabled = !data.export_allowed;
    csv.title = data.export_allowed ? '' : 'Esportazione non abilitata per tutte le strutture selezionate';
  };
  const draw = () => {
    const s = data.summary;
    const bar = h('div');
    const body = h('div');
    const views = {
      mesi: () => h('div', { class: 'stack' },
        card('Turni effettivi per mese', { subtitle: 'Turni di lavoro a consuntivo nel periodo e nelle strutture scelte.' },
          columnChart(data.monthly.map(m => ({ label: `${SHORT[Number(m.month.slice(5)) - 1]} ${m.month.slice(2, 4)}`, title: fmt.month(m.month), value: m.work_shifts })),
            { format: v => fmt.number(v), unit: ' turni' })),
        card('Dettaglio per mese', { flush: true }, table(monthColumns('Mese', r => fmt.month(r.month)), data.monthly))),
      strutture: () => card('Per struttura', { flush: true }, table(monthColumns('Struttura', r => r.name), data.by_center)),
      ruoli: () => card('Per ruolo', { subtitle: data.role_note, flush: true }, table(monthColumns('Ruolo', r => r.role), data.by_role)),
      assenze: () => card('Assenze per causale', { flush: true }, table([
        { label: 'Causale', render: r => `${r.code} · ${r.label}` }, { label: 'Fasce', num: true, render: r => fmt.number(r.absence_slots) },
        { label: 'Giornate per scheda', num: true, render: r => fmt.number(r.absence_days) }, { label: 'Persone', num: true, render: r => fmt.number(r.people_count) },
      ], data.by_cause, { empty: 'Nessuna assenza nel periodo.' })),
      persone: () => card('Per persona', { flush: true }, table([
        { label: 'Persona', render: r => h('div', null, h('strong', { text: r.name }), h('div', { class: 'small faint', text: `${r.center} · ${r.role}` })) },
        ...monthColumns(null).slice(1),
      ], data.by_person, { empty: 'Nessun dato.' })),
      qualita: () => quality(data),
    };
    clear(bar, tabs([{ id: 'mesi', label: 'Andamento' }, { id: 'strutture', label: 'Strutture' }, { id: 'ruoli', label: 'Ruoli' },
      { id: 'assenze', label: 'Assenze' }, { id: 'persone', label: 'Persone' }, { id: 'qualita', label: 'Qualità dei dati' }], tab, id => { tab = id; draw(); }));
    clear(body, views[tab]());
    clear(results,
      data.has_records ? null : alertBox('Nessuna registrazione nel periodo e con i filtri scelti.', 'info'),
      h('div', { class: 'kpis' },
        kpi('Ore con orari', s.minutes === null ? '—' : fmt.hours(s.minutes), s.missing_hours ? `${s.missing_hours} turni senza orari esclusi` : 'tutti i turni hanno gli orari'),
        kpi('Turni effettivi', fmt.number(s.work_shifts), `${fmt.number(s.people_count)} persone`),
        kpi('Completezza orari', s.hours_completeness === null ? '—' : `${fmt.number(s.hours_completeness, 1)}%`, 'turni con ingresso e uscita',
          s.hours_completeness === null ? '' : s.hours_completeness < 100 ? 'warn' : 'ok'),
        kpi('Assenze', fmt.number(s.absence_slots), s.absence_share === null ? 'fasce' : `${fmt.number(s.absence_share, 1)}% delle fasce`),
        kpi('Festivi e fuori sede', `${fmt.number(s.festive_shifts)} · ${fmt.number(s.external_shifts)}`, 'turni festivi · fuori sede'),
        kpi('Senza consuntivo', fmt.number(s.pending_work), 'fasce pianificate', s.pending_work ? 'warn' : 'ok')),
      bar, body,
      data.hr ? hrCard(data.hr) : null,
      h('p', { class: 'small faint', text: `Dati aggiornati al ${fmt.stamp(data.generated_at)}.` }));
  };

  for (const el of [from, to, center, role, person]) el.addEventListener('change', load);
  center.addEventListener('change', () => { person.value = ''; });
  csv.addEventListener('click', async () => {
    try { await download(`statistics/export.csv?${query(filters)}`, 'statistiche.csv'); } catch (err) { toast(errorMessage(err), 'bad'); }
  });
  await load();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Statistiche' }),
      h('h1', { text: 'Andamento delle presenze' }),
      h('p', { text: 'Fino a 24 mesi. Le ore contano solo i turni con ingresso e uscita registrati: i turni senza orari sono indicati a parte.' }))),
    h('div', { class: 'filter-row' }, from, to, center, role, person, csv),
    results);
}

function query(f) {
  return new URLSearchParams(Object.entries({ from: f.from, to: f.to, cid: f.cid, role: f.role, person_id: f.person_id }).filter(([, v]) => v)).toString();
}

function monthColumns(label, first) {
  return [
    { label: label || '', render: first || (() => '') },
    { label: 'Turni', num: true, render: r => fmt.number(r.work_shifts) },
    { label: 'Ore con orari', num: true, render: r => r.minutes === null ? '—' : fmt.hours(r.minutes) },
    { label: 'Senza orari', num: true, render: r => r.missing_hours ? h('span', { class: 'badge warn', text: String(r.missing_hours) }) : '0' },
    { label: 'Assenze', num: true, render: r => fmt.number(r.absence_slots) },
    { label: 'Festivi', num: true, render: r => fmt.number(r.festive_shifts) },
    { label: 'Fuori sede', num: true, render: r => fmt.number(r.external_shifts) },
    { label: 'Senza consuntivo', num: true, render: r => fmt.number(r.pending_work) },
  ];
}

function quality(data) {
  const q = data.quality;
  return h('div', { class: 'stack' },
    h('div', { class: 'kpis' }, kpi('Mesi considerati', fmt.number(q.center_months), 'struttura × mese'),
      kpi('Mesi chiusi', fmt.number(q.closed_months), `su ${q.center_months}`), kpi('Calendari verificati', fmt.number(q.verified_months), `su ${q.center_months}`),
      kpi('Mesi senza consuntivi', fmt.number(q.empty_months), 'nessun dato registrato', q.empty_months ? 'warn' : 'ok')),
    card('Stato dei mesi', { flush: true }, table([
      { label: 'Struttura', key: 'name' }, { label: 'Mese', render: r => fmt.month(r.month) },
      { label: 'Stato', render: r => r.closed ? badge('Chiuso', 'ok') : badge('Aperto', 'info') },
      { label: 'Calendario', render: r => r.verified ? badge('Verificato', 'ok') : badge('Da verificare', 'warn') },
      { label: 'Dati', render: r => !r.actual_records ? badge('Senza consuntivi', '') : r.missing_hours ? badge('Orari mancanti', 'warn') : badge('Orari completi', 'ok') },
    ], data.center_months)),
    q.current_role_fallback_records ? alertBox(`${fmt.number(q.current_role_fallback_records)} registrazioni usano il ruolo attuale della scheda perché manca il contratto alla data.`, 'info') : null);
}

function hrCard(hr) {
  return card('Persone e fascicoli', { subtitle: `Situazione al ${fmt.date(hr.as_of)}` }, h('div', { class: 'result-grid' },
    [['Persone attive', hr.active_people], ['Fascicoli da compilare', hr.missing_profiles], ['Inserimenti aperti', hr.onboarding_open],
      ['Attività aperte', hr.tasks_open], ['Attività scadute', hr.tasks_overdue], ['Scadenze superate', hr.deadlines_overdue],
      ['Scadenze entro 30 giorni', hr.deadlines_next30]].map(([label, value]) =>
      h('div', null, h('div', { class: 'small faint', text: label }), h('div', { class: 'result-value', text: fmt.number(value) })))));
}
