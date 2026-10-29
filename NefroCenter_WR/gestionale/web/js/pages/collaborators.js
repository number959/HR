// Collaboratori e compensi: il prospetto mensile dei collaboratori a prestazione (il foglio «Collaboratori» del vecchio modello Excel).
import { download, get } from '../api.js';
import { alertBox, badge, button, card, errorMessage, fmt, h, kpi, table, toast } from '../ui.js';

const TONE = { calcolato: 'ok', da_confermare: 'warn', da_verificare: 'warn', orari_mancanti: 'bad', nessun_dato: '', gestione_manuale: 'bad' };
const money = v => v === null || v === undefined ? '—' : fmt.money(v);
const percent = v => v ? `${fmt.number(v, v % 1 ? 2 : 0)}%` : '—';

export async function render(ctx) {
  const { app } = ctx;
  const data = await get(`collaborators/${app.cid}/${app.month}`);
  const exportButton = data.can_export ? button('Scarica il prospetto (Excel)', { ic: 'download', onClick: async () => {
    try {
      await download(`collaborators/${app.cid}/${app.month}/export.xlsx`, 'collaboratori.xlsx');
      toast('Prospetto scaricato. Contiene coordinate bancarie: conservarlo con cura.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } }) : null;
  const columns = [
    { label: 'Collaboratore', render: r => h('div', null, h('strong', { text: r.name }), h('div', { class: 'small faint', text: [r.role, r.billing_entity].filter(Boolean).join(' · ') })) },
    { label: 'Turni', num: true, render: r => fmt.number(r.shifts) },
    { label: 'Feriali / festivi', num: true, render: r => `${fmt.number(r.ordinary_units, r.model === 'hours' ? 1 : 0)} / ${fmt.number(r.festive_units, r.model === 'hours' ? 1 : 0)}` },
    { label: 'Tariffe', num: true, render: r => `${fmt.money(r.weekday_rate)} / ${fmt.money(r.holiday_rate)}` },
    { label: 'Lordo', num: true, render: r => r.gross === null ? '—' : h('strong', { text: fmt.money(r.gross) }) },
    { label: 'Ritenuta', num: true, render: r => r.withholding === null ? percent(r.withholding_rate) : `${fmt.money(r.withholding)} (${percent(r.withholding_rate)})` },
    { label: 'Cassa', num: true, render: r => r.fund === null ? (r.fund_name ? `${r.fund_name} ${percent(r.fund_rate)}` : '—') : `${fmt.money(r.fund)}${r.fund_name ? ` (${r.fund_name} ${percent(r.fund_rate)})` : ''}` },
    { label: 'Netto', num: true, render: r => r.net === null ? '—' : h('strong', { text: fmt.money(r.net) }) },
    ...(data.bank_visible ? [{ label: 'Pagamento', render: r => h('div', { class: 'small' }, r.iban ? h('div', { class: 'mono', text: r.iban }) : h('span', { class: 'faint', text: 'IBAN non indicato' }), r.account_holder ? h('div', { class: 'faint', text: r.account_holder }) : null) }] : []),
    { label: 'Stato', render: r => h('div', null, badge(r.status_label, TONE[r.status]), r.notes ? h('div', { class: 'small faint', text: r.notes }) : null) },
  ];
  const totalsRow = (label, t) => h('div', { class: 'row small muted', text: `${label}: ${fmt.number(t.shifts)} turni · lordo ${money(t.gross)} · ritenute ${money(t.withholding)} · cassa ${money(t.fund)} · netto ${money(t.net)} (${t.calculated} su ${t.people} con importo)` });
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Collaboratori e compensi' }),
      h('h1', { text: `${data.center.name} · ${fmt.month(data.month)}` }),
      h('div', { class: 'row' }, data.closed ? badge('Mese chiuso', 'ok', true) : badge('Mese aperto', 'info', true),
        data.approval?.frozen ? badge(`Approvazione: ${data.approval.label}`, 'warn') : null)),
    h('div', { class: 'page-actions' }, exportButton)),
    alertBox('Il prospetto riguarda chi non è dipendente della struttura (tipo di rapporto nel fascicolo, scheda Contratto). Lordo dall’accordo del mese confermato; ritenuta e cassa con le percentuali del fascicolo (scheda Amministrazione); netto = lordo + cassa − ritenuta. È una base per i pagamenti, non una fattura né un cedolino.', 'info'),
    h('div', { class: 'kpis' },
      kpi('Collaboratori', fmt.number(data.totals.people), `${fmt.number(data.totals.calculated)} con compenso calcolato`),
      kpi('Turni', fmt.number(data.totals.shifts), `unità pagate: ${fmt.number(data.totals.ordinary_units)} feriali · ${fmt.number(data.totals.festive_units)} festive (assenze conteggiate comprese)`),
      kpi('Lordo', money(data.totals.gross), 'dagli accordi confermati'),
      kpi('Ritenute', money(data.totals.withholding), 'ritenuta d’acconto'),
      kpi('Netto da pagare', money(data.totals.net), 'lordo + cassa − ritenuta')),
    ...(data.groups.length ? data.groups.map(g => card(g.label, { flush: true, subtitle: `${g.totals.people} ${g.totals.people === 1 ? 'persona' : 'persone'}` },
      table(columns, g.rows, { onRow: r => ctx.go(`accordi?persona=${r.person_id}`) }),
      h('div', { class: 'card-body' }, totalsRow('Totale del gruppo', g.totals))))
      : [card('Nessun collaboratore nel mese', {}, h('p', { class: 'muted', text: 'Per far comparire una persona qui, nel fascicolo (scheda Contratto) indica il tipo di rapporto diverso da «Dipendente della struttura» e, nella scheda Amministrazione, chi fattura, le percentuali di ritenuta e cassa e l’IBAN.' }))]),
    data.groups.length > 1 ? card('Totale complessivo', {}, totalsRow('Tutti i collaboratori', data.totals)) : null);
}
