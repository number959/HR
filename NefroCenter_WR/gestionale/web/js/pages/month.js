// Controlli e chiusura del mese: verifiche, chiusura e riapertura, nuovi parametri, pazienti per fascia, storico.
import { get, post, put } from '../api.js';
import { alertBox, badge, button, card, dialog, errorMessage, field, fmt, h, input, kpi, select, table, textarea, toast } from '../ui.js';

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
    actions.push(button(state.verified ? 'Annulla la verifica' : 'Calendario e parametri verificati', {
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
  const checks = approval.checks;
  const blocks = [
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Controlli e chiusura' }),
      h('h1', { text: `${snap.center.name} · ${fmt.month(snap.month)}` }),
      h('div', { class: 'row' }, state.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true),
        state.verified ? badge('Calendario verificato', 'ok') : badge('Calendario da verificare', 'warn'),
        approval.policy.enabled ? badge(`Approvazione: ${approval.workflow.label}`, 'brand') : null)),
    h('div', { class: 'page-actions' }, actions)),
    h('div', { class: 'kpis' }, kpi('Turni a consuntivo', fmt.number(totals.shifts), fmt.minutes(totals.minutes) + ' ore con orari'),
      kpi('Turni senza orari', fmt.number(totals.missing), '', totals.missing ? 'warn' : 'ok'),
      kpi('Da consuntivare', fmt.number(totals.pending), 'fasce pianificate', totals.pending ? 'warn' : 'ok'),
      kpi('Assenze', fmt.number(totals.absences), 'fasce di assenza'),
      kpi('Giorni lavorativi', fmt.number(snap.working_days), 'secondo il calendario della struttura')),
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
  ];
  if (caps['presenze.carico']) blocks.push(workloadCard(ctx, snap, base));
  blocks.push(card('Ultime modifiche', { flush: true }, table([
    { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Da', key: 'actor' }, { label: 'Operazione', key: 'action' },
  ], snap.history.slice(0, 25), { empty: 'Nessuna modifica registrata.' })));
  return h('div', { class: 'stack' }, blocks);
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

function workloadCard(ctx, snap, base) {
  const slots = snap.config.slots.filter(s => s.active);
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
  const fmtRatio = (v, over) => v === null ? h('span', { class: 'badge bad', text: 'Nessuno in turno' }) : h('span', { class: over ? 'badge warn' : '', text: fmt.number(v, 1) });
  return card('Pazienti e carico per fascia', { subtitle: `Riferimento: ${snap.config.nurse_reference} pazienti per infermiere, ${snap.config.doctor_reference} per medico` },
    form, h('div', { class: 'table-wrap' }, table([
      { label: 'Giorno', render: r => fmt.date(r.day) }, { label: 'Fascia', key: 'slot' },
      { label: 'Pazienti', num: true, key: 'ordinary' }, { label: 'Isolamento', num: true, key: 'isolated' },
      { label: 'Infermieri', num: true, key: 'nurses' }, { label: 'Pazienti per infermiere', num: true, render: r => fmtRatio(r.nurse_ratio, r.nurse_over) },
      { label: 'Medici', num: true, key: 'doctors' }, { label: 'Pazienti per medico', num: true, render: r => fmtRatio(r.doctor_ratio, r.doctor_over) },
    ], snap.workload.slice().reverse().slice(0, 31), { empty: 'Nessun dato sui pazienti nel mese.' })),
    h('p', { class: 'small faint', text: 'Confronto organizzativo con i riferimenti della struttura: non è una valutazione clinica.' }));
}

