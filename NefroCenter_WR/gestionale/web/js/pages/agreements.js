// Accordi e calcoli del mese: proposta, accordo individuale confermato, simulatore del modello Excel.
import { get, post, put } from '../api.js';
import { agreementForm, modelLabel } from '../agreement-form.js';
import {
  alertBox, badge, button, card, clear, dialog, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, textarea, toast,
} from '../ui.js';

const TONE = { calcolato: 'ok', da_confermare: 'warn', da_verificare: 'warn', orari_mancanti: 'bad', nessun_dato: '', gestione_manuale: 'bad' };

export async function render(ctx) {
  const { app } = ctx;
  const data = await get(`agreements/${app.cid}/${app.month}`);
  const units = r => r.agreement?.model === 'hours' ? `${fmt.number(r.units, 1)} h` : fmt.number(r.units, 1);
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Accordi e calcoli' }),
      h('h1', { text: `${data.center.name} · ${fmt.month(data.month)}` }),
      h('div', { class: 'row' }, data.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true),
        data.approval?.frozen ? badge('In approvazione: non modificabile', 'warn') : null,
        h('span', { class: 'small muted', text: `Parametri v${data.rules_version}` })))),
    alertBox('Il calcolo è una base di verifica per l’ufficio paghe, non un cedolino. Senza accordo confermato non si calcola alcun importo.', 'info'),
    h('div', { class: 'kpis' },
      kpi('Totale calcolato', fmt.money(data.totals.amount), `${data.totals.calculated} persone con importo`),
      kpi('Da confermare', fmt.number(data.totals.to_confirm), 'accordi senza conferma', data.totals.to_confirm ? 'warn' : 'ok'),
      kpi('Tariffe della struttura', `${fmt.money(data.parameters.weekday_rate)} / ${fmt.money(data.parameters.holiday_rate)}`, 'feriale / festiva per unità')),
    card('Persone del mese', { flush: true }, table([
      { label: 'Persona', render: r => h('div', null, h('strong', { text: r.name }), h('div', { class: 'small faint', text: `${r.role} · ${r.saved ? 'accordo salvato' : 'proposta'}` })) },
      { label: 'Modello', render: r => modelLabel(r.agreement.model) },
      { label: 'Turni', num: true, render: r => fmt.number(r.shifts) },
      { label: 'Unità', num: true, render: units },
      { label: 'Teorico', num: true, render: r => r.theoretical === null ? 'per periodo' : fmt.number(r.theoretical, 1) },
      { label: 'Feriali / festive', num: true, render: r => `${fmt.number(r.ordinary_units, 1)} / ${fmt.number(r.festive_units, 1)}` },
      { label: 'Importo', num: true, render: r => r.amount === null ? '—' : h('strong', { text: fmt.money(r.amount) }) },
      { label: 'Stato', render: r => badge(r.status_label, TONE[r.status]) },
    ], data.rows, { empty: 'Nessuna persona nel registro.', onRow: r => openAgreement(ctx, data, r) })),
    simulator(ctx, data));
}

async function openAgreement(ctx, data, row) {
  const form = agreementForm(row.agreement, data.absence_codes, { disabled: !data.editable });
  const reason = textarea('reason', '', { max: 1000, rows: 2 });
  const result = h('div', { class: 'result-grid' },
    resultItem('Turni registrati', fmt.number(row.shifts)), resultItem('Giorni lavorativi del calendario', fmt.number(row.calendar_days)),
    resultItem('Unità conteggiate', fmt.number(row.units, 2)), resultItem('Base del calcolo', fmt.number(row.base_units, 2)),
    resultItem('Importo feriale', fmt.money(row.ordinary_amount)), resultItem('Importo festivo', fmt.money(row.festive_amount)),
    resultItem('Importo totale', row.amount === null ? '—' : fmt.money(row.amount)));
  const body = h('div', { class: 'stack' },
    h('div', { class: 'row' }, badge(row.status_label, TONE[row.status]), row.saved ? h('span', { class: 'small muted', text: `Salvato da ${row.updated_by} il ${fmt.stamp(row.updated_at)} · ${row.source}` }) : badge('Proposta dai parametri', '')),
    row.warnings.length ? h('div', { class: 'alerts' }, row.warnings.map(w => alertBox(w, 'warn'))) : null,
    row.agreement.segments ? alertBox('Questo accordo deriva dalle condizioni con decorrenza del personale di gruppo: salvando diventa un accordo manuale del mese.', 'info') : null,
    card('Risultato attuale', {}, result),
    form.node,
    data.editable ? field('Motivazione del salvataggio (almeno 8 caratteri)', reason, { name: 'reason' }) : null);
  const actions = [{ label: 'Chiudi', value: null }];
  if (data.editable) actions.push({ label: 'Salva l’accordo', kind: 'primary', onClick: async () => {
    try {
      await put(`agreements/${ctx.app.cid}/${ctx.app.month}/${row.person_id}`, { agreement: form.value(), reason: reason.value, version: row.version });
      return true;
    } catch (err) { if (!showErrors(body, err)) toast(errorMessage(err), 'bad'); return false; }
  } });
  if (await dialog(`Accordo del mese · ${row.name}`, body, actions, { wide: true })) {
    toast('Accordo salvato. Calendario e parametri del mese vanno confermati di nuovo.', 'ok');
    ctx.refresh();
  }
}

function resultItem(label, value) {
  return h('div', null, h('div', { class: 'small faint', text: label }), h('div', { class: 'result-value', text: value }));
}

function simulator(ctx, data) {
  const person = select('person_id', [['', 'Parametri della struttura'], ...data.rows.map(r => [r.person_id, r.name])], '');
  const total = input('total', '0', { type: 'number', min: '0' });
  const festive = input('festive', '0', { type: 'number', min: '0' });
  const ccnl = input('ccnl_festive', '0', { type: 'number', min: '0' });
  const out = h('div');
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Con i parametri di', person), field('Turni totali', total, { name: 'total' }),
    field('Di cui festivi', festive, { name: 'festive' }), field('Festivi già riconosciuti dal CCNL', ccnl, { name: 'ccnl_festive' }),
    h('div', { class: 'field end' }, button('Calcola', { kind: 'primary', type: 'submit' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await post(`agreements/${ctx.app.cid}/${ctx.app.month}/simulate`, { person_id: person.value, total: Number(total.value),
        festive: Number(festive.value), ccnl_festive: Number(ccnl.value) });
      clear(out, res.calculated ? h('div', { class: 'result-grid mt' },
        resultItem('Teorico (giorni lavorativi)', fmt.number(res.theoretical)), resultItem('Turni considerati', fmt.number(res.extra)),
        resultItem('Feriali', fmt.number(res.ordinary)), resultItem('Importo feriale', fmt.money(res.ordinary_amount)),
        resultItem('Importo festivo', fmt.money(res.holiday_amount)), resultItem('Totale', fmt.money(res.total)))
        : alertBox(res.reason, 'info'));
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return card('Simulatore del modello Excel', { subtitle: 'Riproduce il calcolo del vecchio foglio Excel per un controllo veloce. Non salva nulla.' }, form, out);
}
