// Controlli e chiusura del mese: verifiche, chiusura e riapertura, nuovi parametri, pazienti e carico per fascia,
// conteggi del mese per persona e gruppo, storico.
import { get, post, put } from '../api.js';
import { alertBox, badge, button, card, clear, dialog, errorMessage, field, fmt, h, input, kpi, select, table, tabs, textarea, toast } from '../ui.js';

// Scheda aperta: resta la stessa quando la pagina si ricarica dopo un salvataggio.
let activeTab = 'controlli';

// Due letture come nel vecchio modello e nel foglio esportato (verde da soglia in su, arancione sotto);
// senza rapporto si distingue «nessuno in turno» da «pazienti non ancora registrati».
const LEVELS = { sotto: ['Sotto soglia', 'warn'], adeguato: ['Adeguata', 'ok'], nessuno: ['Nessuno in turno', ''],
  senza_dati: ['Pazienti da registrare', 'info'] };

export async function render(ctx) {
  const { app } = ctx;
  const [snap, approval] = await Promise.all([get(`attendance/${app.cid}/${app.month}`), get(`approvals/${app.cid}/${app.month}`)]);
  const caps = snap.caps;
  const state = snap.state;
  const base = `attendance/${app.cid}/${app.month}`;
  const run = async (path, body, message) => {
    try {
      await post(`${base}/${path}`, body);
      toast(message, 'ok');
      ctx.refresh();
    } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const actions = [];
  if (caps['mese.verifica'] && !state.closed && !snap.approval.frozen) {
    actions.push(button(state.verified ? 'Annulla la conferma' : 'Conferma calendario e parametri', {
      kind: state.verified ? '' : 'primary', ic: 'check',
      onClick: () => run('verify', { verified: !state.verified, version: state.version, note: state.note }, 'Verifica aggiornata.'),
    }));
  }
  if (caps['mese.chiudi'] && !approval.policy.enabled) {
    if (!state.closed) actions.push(button('Chiudi il mese', { kind: 'primary', ic: 'lock', onClick: () => run('close', { version: state.version }, 'Mese chiuso.') }));
    else actions.push(button('Riapri il mese', { ic: 'undo', onClick: () => reopen(ctx, base, state) }));
  }
  if (approval.policy.enabled) actions.push(button('Vai alle approvazioni', { ic: 'stamp', onClick: () => ctx.go(`approvazioni/${app.cid}`) }));
  const totals = snap.summary.reduce((t, r) => ({ shifts: t.shifts + r.shifts, minutes: t.minutes + r.minutes, missing: t.missing + r.missing,
    pending: t.pending + r.pending, absences: t.absences + r.absences }), { shifts: 0, minutes: 0, missing: 0, pending: 0, absences: 0 });
  const head = h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Controlli e chiusura' }),
    h('h1', { text: `${snap.center.name} · ${fmt.month(snap.month)}` }),
    h('div', { class: 'row' }, state.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true),
      state.verified ? badge('Calendario verificato', 'ok') : badge('Calendario da verificare', 'warn'),
      approval.policy.enabled ? badge(`Approvazione: ${approval.workflow.label}`, 'brand') : null)),
  h('div', { class: 'page-actions' }, actions));
  const kpis = h('div', { class: 'kpis' }, kpi('Turni a consuntivo', fmt.number(totals.shifts), fmt.minutes(totals.minutes) + ' ore con orari'),
    kpi('Turni senza orari', fmt.number(totals.missing), '', totals.missing ? 'warn' : 'ok'),
    kpi('Da consuntivare', fmt.number(totals.pending), 'fasce pianificate', totals.pending ? 'warn' : 'ok'),
    kpi('Assenze', fmt.number(totals.absences), 'fasce di assenza'),
    kpi('Giorni lavorativi', fmt.number(snap.working_days), 'secondo il calendario della struttura'));

  const items = [{ id: 'controlli', label: 'Controlli e chiusura' }];
  if (caps['presenze.carico']) items.push({ id: 'carico', label: 'Pazienti e carico per fascia' });
  items.push({ id: 'conteggi', label: 'Conteggi del mese' });
  if (!items.some(i => i.id === activeTab)) activeTab = 'controlli';
  const bar = h('div');
  const body = h('div');
  const draw = () => {
    clear(bar, tabs(items, activeTab, id => { activeTab = id; draw(); }));
    clear(body, activeTab === 'carico' ? workloadCard(ctx, snap, base)
      : activeTab === 'conteggi' ? countersCard(snap)
        : controlsSection(ctx, snap, approval, base, caps, state));
  };
  draw();
  return h('div', { class: 'stack' }, head, kpis, h('div', null, bar, body));
}

function controlsSection(ctx, snap, approval, base, caps, state) {
  const checks = approval.checks;
  return h('div', { class: 'stack' },
    h('div', { class: 'grid grid-2' },
      card('Controlli prima della chiusura', { subtitle: checks.length ? `${checks.length} da risolvere` : 'Tutto pronto' },
        checks.length ? h('div', { class: 'alerts' }, checks.map(c => alertBox(c, 'warn'))) : alertBox('Nessun controllo bloccante.', 'ok'),
        state.note ? h('p', { class: 'small muted', text: `Nota del mese: ${state.note}` }) : null),
      card('Parametri del mese', { subtitle: `Versione ${state.rules_version} · struttura alla versione ${snap.center.config_version}` },
        snap.rules_outdated
          ? h('div', { class: 'stack' }, alertBox('Sono disponibili parametri più recenti. Si possono applicare solo a un mese senza registrazioni.', 'info'),
            caps['mese.regole'] ? button('Applica i parametri più recenti', { onClick: () => applyRules(ctx, base, state) }) : null)
          : h('p', { class: 'muted', text: 'Il mese usa i parametri più recenti della struttura.' }),
        h('p', { class: 'small faint', text: `Riposo minimo ${snap.config.min_rest_hours} ore · orari obbligatori per la chiusura: ${snap.config.require_times_on_close ? 'sì' : 'no'}` }))),
    card('Ultime modifiche', { flush: true }, table([
      { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Da', key: 'actor' }, { label: 'Operazione', key: 'action' },
    ], snap.history.slice(0, 25), { empty: 'Nessuna modifica registrata.' })));
}

async function reopen(ctx, base, state) {
  const reason = textarea('reason', '', { max: 1000 });
  const ok = await dialog('Riapri il mese', h('div', { class: 'stack' }, h('p', { text: 'Il mese torna modificabile. La motivazione resta nello storico.' }),
    field('Motivazione (almeno 8 caratteri)', reason)), [{ label: 'Annulla', value: null }, { label: 'Riapri', kind: 'primary', onClick: async () => {
    try { await post(`${base}/reopen`, { version: state.version, reason: reason.value }); return true; } catch (err) { toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) { toast('Mese riaperto.', 'ok'); ctx.refresh(); }
}

async function applyRules(ctx, base, state) {
  const reason = textarea('reason', '', { max: 1000 });
  const ok = await dialog('Applica i parametri più recenti', field('Motivazione (almeno 8 caratteri)', reason), [{ label: 'Annulla', value: null },
    { label: 'Applica', kind: 'primary', onClick: async () => {
      try { await post(`${base}/apply-rules`, { version: state.version, reason: reason.value }); return true; } catch (err) { toast(errorMessage(err), 'bad'); return false; }
    } }]);
  if (ok) { toast('Parametri applicati.', 'ok'); ctx.refresh(); }
}

// ---------- Pazienti e carico per fascia ----------
const two = v => (v === null || v === undefined) ? '—' : Number(v).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ratio = v => (v === null || v === undefined) ? '—' : fmt.number(v, 2);

function efficiencyCell(value, level) {
  const [label, tone] = LEVELS[level] || LEVELS.nessuno;
  if (value === null || value === undefined) return badge(label, tone);
  return h('span', { class: 'eff' }, h('strong', { text: two(value) }), badge(label, tone));
}

// Turni del mese nella sede; sotto, quelli dei giorni con pazienti registrati (denominatore del rapporto) se diversi.
function shiftsCell(all, rated) {
  return h('div', null, fmt.number(all),
    all !== rated ? h('div', { class: 'small faint', text: `${fmt.number(rated)} nei giorni con dati` }) : null);
}

// Tabelle larghe: caratteri e spazi ridotti (classe già prevista dallo stile), aggiunta sul nodo creato da table().
function compact(wrap, extra = '') {
  wrap.querySelector?.('table')?.classList.add('compact', ...extra.split(' ').filter(Boolean));
  return wrap;
}

function stat(label, value, foot) {
  return h('div', null, h('div', { class: 'stat-label', text: label }),
    value instanceof Node ? h('div', { class: 'result-value' }, value) : h('div', { class: 'result-value', text: value }),
    foot ? h('div', { class: 'small faint', text: foot }) : null);
}

function workloadCard(ctx, snap, base) {
  const cfg = snap.config;
  const summary = snap.workload_summary;
  const slots = cfg.slots.filter(s => s.active);
  const day = input('day', snap.days.find(d => d.day === ctx.app.me.today)?.day || snap.days[0].day, { type: 'date' });
  const slot = select('slot', slots.map(s => [s.id, s.label]), slots[0]?.id);
  const ordinary = input('ordinary', '0', { type: 'number', min: '0' });
  const isolated = input('isolated', '0', { type: 'number', min: '0' });
  const editable = snap.editable;
  const form = h('form', { class: 'form-grid' }, field('Giorno', day), field('Fascia', slot), field('Pazienti', ordinary), field('In isolamento', isolated),
    h('div', { class: 'field' }, h('span', { class: 'small faint', text: ' ' }), button('Registra', { kind: 'primary', type: 'submit', disabled: !editable })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await put(`${base}/workload`, { day: day.value, slot: slot.value, ordinary: Number(ordinary.value), isolated: Number(isolated.value) });
      toast('Pazienti registrati.', 'ok');
      ctx.refresh();
    } catch (err) { toast(errorMessage(err), 'bad'); }
  });

  const patients = r => h('div', null, fmt.number(r.patients),
    r.isolated ? h('div', { class: 'small faint', text: `${fmt.number(r.isolated)} in isolamento` }) : null);
  const summaryBox = summary ? h('div', { class: 'workload-summary' },
    h('h3', { text: 'Sintesi del mese per fascia' }),
    compact(table([
      { label: 'Fascia', key: 'label' }, { label: 'Giorni con dati', num: true, key: 'days' },
      { label: 'Turni inf.', num: true, render: r => shiftsCell(r.nurse_shifts, r.nurse_rated_shifts) },
      { label: 'Turni med.', num: true, render: r => shiftsCell(r.doctor_shifts, r.doctor_rated_shifts) },
      { label: 'Pazienti', num: true, render: patients },
      { label: 'Paz. per infermiere', num: true, render: r => ratio(r.nurse_ratio) },
      { label: 'Efficienza inf.', num: true, render: r => efficiencyCell(r.nurse_efficiency, r.nurse_level) },
      { label: 'Paz. per medico', num: true, render: r => ratio(r.doctor_ratio) },
      { label: 'Efficienza med.', num: true, render: r => efficiencyCell(r.doctor_efficiency, r.doctor_level) },
    ], summary.slots, { empty: 'Nessuna fascia attiva nei parametri del mese.' }), 'fit'),
    h('div', { class: 'result-grid' },
      stat('Totale turni da lavorare', fmt.number(summary.nurse_shifts + summary.doctor_shifts),
        `${fmt.number(summary.nurse_shifts)} infermieri · ${fmt.number(summary.doctor_shifts)} medici, nella sede`),
      stat('Totale dialisi da effettuare', fmt.number(summary.patients),
        `${summary.isolated ? fmt.number(summary.isolated) + ' in isolamento · ' : ''}${fmt.number(summary.days)} giorni con dati`),
      stat('Media parametro infermieristico', ratio(summary.nurse_parameter), `pazienti per infermiere · riferimento ${fmt.number(summary.nurse_reference, 2)}`),
      stat('Media parametro medico', ratio(summary.doctor_parameter), `pazienti per medico · riferimento ${fmt.number(summary.doctor_reference, 2)}`),
      stat('Efficienza media infermieri', efficiencyCell(summary.nurse_efficiency, summary.nurse_level)),
      stat('Efficienza media medici', efficiencyCell(summary.doctor_efficiency, summary.doctor_level)),
      summary.dialysis_stations > 0 ? stat('Posti dialisi accreditati', fmt.number(summary.dialysis_stations)) : null,
      summary.isolation_stations > 0 ? stat('Posti contumaciali', fmt.number(summary.isolation_stations)) : null)) : null;

  const daily = compact(table([
    { label: 'Giorno', render: r => fmt.date(r.day) }, { label: 'Fascia', key: 'slot' },
    { label: 'Pazienti', num: true, key: 'ordinary' }, { label: 'Isolamento', num: true, key: 'isolated' },
    { label: 'Infermieri', num: true, key: 'nurses' }, { label: 'Paz. per infermiere', num: true, render: r => ratio(r.nurse_ratio) },
    { label: 'Efficienza inf.', num: true, render: r => efficiencyCell(r.nurse_efficiency, r.nurse_level) },
    { label: 'Medici', num: true, key: 'doctors' }, { label: 'Paz. per medico', num: true, render: r => ratio(r.doctor_ratio) },
    { label: 'Efficienza med.', num: true, render: r => efficiencyCell(r.doctor_efficiency, r.doctor_level) },
  ], snap.workload.slice().reverse(), { empty: 'Nessun dato sui pazienti nel mese.' }), 'fit');

  const threshold = fmt.number(cfg.efficiency_threshold, 2);
  return card('Pazienti e carico per fascia', { subtitle: `Riferimento: ${fmt.number(cfg.nurse_reference, 2)} pazienti per infermiere, ${fmt.number(cfg.doctor_reference, 2)} per medico · soglia di efficienza ${threshold}` },
    summaryBox,
    h('h3', { class: 'section-head', text: 'Pazienti registrati per giorno' }),
    form, daily,
    h('p', { class: 'small muted', text: `Rapporto = pazienti per operatore in turno nella sede (un paziente in isolamento pesa ${fmt.number(cfg.isolation_weight, 2)} per gli infermieri). `
      + 'Nella sintesi del mese il rapporto di una fascia usa solo i turni dei giorni con pazienti registrati, così resta coerente con le righe giornaliere anche a mese incompleto; '
      + '«Totale turni da lavorare» conta invece tutti i turni nella sede. '
      + `Efficienza = pazienti per operatore / riferimento: 1 = pari al riferimento; sotto ${threshold} il personale in turno è più del riferimento, oltre 1 il carico lo supera. `
      + `Come nel foglio esportato le letture sono due: «Adeguata» da ${threshold} in su, «Sotto soglia» sotto. È un confronto organizzativo, non una valutazione clinica.` }));
}

// ---------- Conteggi del mese ----------
function countersCard(snap) {
  const counters = snap.counters || { codes: [], people: [], groups: [] };
  const rows = [];
  for (const gid of ['infermieri', 'medici', 'altro']) {
    const members = counters.people.filter(p => p.group === gid);
    if (!members.length) continue;
    rows.push(...members);
    const group = counters.groups.find(g => g.id === gid);
    if (group) rows.push({ ...group, totalRow: true });
  }
  const everyone = counters.groups.find(g => g.id === 'tutti');
  if (everyone && counters.people.length) rows.push({ ...everyone, totalRow: true, grand: true });
  const num = (r, value) => (value || r.totalRow) ? fmt.number(value) : h('span', { class: 'faint', text: '0' });
  const columns = [
    { label: 'Persona', render: r => r.totalRow
      ? h('div', null, h('strong', { text: r.grand ? 'Totale personale' : `Totali ${r.label.toLowerCase()}` }),
        h('div', { class: 'small faint', text: `${fmt.number(r.people)} ${r.people === 1 ? 'persona' : 'persone'}` }))
      : h('div', null, h('strong', { text: r.name }),
        h('div', { class: 'small faint row tight' }, r.registration ? `Matr. ${r.registration}` : null, r.active ? null : badge('Non attiva'))) },
    { label: 'Ruolo', render: r => r.totalRow ? '' : r.role },
    { label: 'Turni', num: true, render: r => num(r, r.shifts) },
    { label: 'Fuori sede', num: true, render: r => num(r, r.external) },
    { label: 'Festivi', num: true, render: r => num(r, r.festive) },
    ...counters.codes.map(c => ({ label: c.id, num: true, render: r => num(r, r.codes[c.id]) })),
    { label: 'Totale', num: true, render: r => h('div', null, h('strong', { text: fmt.number(r.total) }),
      r.registrations !== r.total ? h('div', { class: 'small faint', text: `su ${fmt.number(r.registrations)} registr.` }) : null) },
  ];
  const grid = compact(table(columns, rows, { empty: 'Nessuna registrazione nel mese.', rowClass: r => r.totalRow ? (r.grand ? 'total-row grand' : 'total-row') : '' }), 'counters');
  const legend = counters.codes.map(c => `${c.id} = ${c.label}`).join(' · ');
  return card('Conteggi del mese', { flush: true, subtitle: 'Turni, fuori sede, festivi e causali per persona, con i totali di infermieri, medici e altro personale',
    foot: h('div', null,
      legend ? h('p', { class: 'small muted', text: `Causali: ${legend}.` }) : null,
      h('p', { class: 'small muted', text: 'Si contano solo le registrazioni a consuntivo; «Fuori sede» e «Festivi» sono turni svolti in un’altra sede o in giorno festivo. '
        + 'Il totale segue il vecchio file: registrazioni del mese senza recuperi turno (RC) e riposi, la stessa base della proposta di accordo in «Accordi e calcoli»; '
        + 'quando differisce, sotto compare il numero di tutte le registrazioni.' })) },
  grid);
}
