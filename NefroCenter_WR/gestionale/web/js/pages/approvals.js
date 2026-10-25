// Approvazione mensile: stato di tutte le strutture e dettaglio del percorso struttura → responsabile → HR.
import { get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, dialog, empty, errorMessage, field, fmt, h, kpi, table, textarea, toast,
} from '../ui.js';

const TONE = { draft: '', submitted: 'info', manager_approved: 'brand', hr_approved: 'ok', returned: 'warn' };
const ORDER = ['draft', 'submitted', 'manager_approved', 'hr_approved'];

export async function render(ctx) {
  const { app } = ctx;
  const queue = await get(`approvals/${app.month}`);
  const selected = ctx.params[0] || queue.centers.find(c => c.mine)?.center_id || queue.centers[0]?.center_id;
  const root = h('div');
  const detailBox = h('div');
  const showDetail = async cid => {
    clear(detailBox, h('div', { class: 'card' }, h('div', { class: 'card-body' }, h('div', { class: 'skeleton' }))));
    try {
      clear(detailBox, await detail(ctx, cid, () => ctx.refresh()));
    } catch (err) { clear(detailBox, alertBox(errorMessage(err), 'bad')); }
  };
  const list = card('Strutture', { subtitle: fmt.month(queue.month), flush: true },
    table([
      { label: 'Struttura', render: c => h('strong', { text: c.center }) },
      { label: 'Stato', render: c => c.enabled ? badge(c.label, TONE[c.status], true) : badge(c.label, c.closed ? 'ok' : '') },
      { label: '', render: c => c.mine ? badge('Tocca a te', 'bad') : c.stale ? badge('Dati cambiati', 'warn') : null },
    ], queue.centers, { empty: 'Nessuna struttura.', onRow: c => { ctx.go(`approvazioni/${c.center_id}`); } }));
  clear(root,
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Approvazione mensile' }),
      h('h1', { text: `Approvazioni · ${fmt.month(queue.month)}` }),
      h('p', { text: 'Struttura → responsabile → HR centrale. Dopo l’invio il mese resta bloccato finché non viene approvato o restituito.' }))),
    h('div', { class: 'kpis' }, kpi('Da gestire da te', fmt.number(queue.waiting), 'passaggi in attesa', queue.waiting ? 'bad' : 'ok'),
      kpi('Strutture con il percorso attivo', fmt.number(queue.centers.filter(c => c.enabled).length), `su ${queue.centers.length}`),
      kpi('Approvate da HR', fmt.number(queue.centers.filter(c => c.status === 'hr_approved').length), 'mese chiuso')),
    h('div', { class: 'grid grid-main' }, detailBox, list));
  if (selected) showDetail(selected);
  else clear(detailBox, empty('Nessuna struttura', 'Non ci sono strutture da mostrare.'));
  return root;
}

async function detail(ctx, cid, reload) {
  const { app } = ctx;
  const data = await get(`approvals/${cid}/${app.month}`);
  const wf = data.workflow;
  const reached = ORDER.indexOf(wf.status === 'returned' ? 'draft' : wf.status);
  const steps = h('div', { class: 'steps', 'aria-label': 'Percorso di approvazione' },
    [['Compilazione', 0], ['Inviato al responsabile', 1], ['Verificato dal responsabile', 2], ['Approvato da HR', 3]].map(([label, i]) =>
      h('div', { class: `step ${i < reached || (i === reached && i === 3) ? 'done' : i === reached ? 'current' : ''}`, text: label })));
  const actions = data.actions.map(a => button(a.label, {
    kind: ['return', 'reopen'].includes(a.id) ? '' : 'primary', onClick: () => act(ctx, cid, data, a, reload),
  }));
  const checks = data.checks.length
    ? h('ul', { class: 'list' }, data.checks.map(c => h('li', null, h('span', { class: 'icon-dot urgent', text: '!' }), h('div', { class: 'grow', text: c }))))
    : alertBox('Nessun controllo bloccante: il mese è pronto per il passaggio successivo.', 'ok');
  const policy = data.can_configure ? button(data.policy.enabled ? 'Disattiva il percorso' : 'Attiva il percorso', {
    small: true, onClick: () => configure(ctx, cid, data, reload),
  }) : null;
  return h('div', { class: 'stack' },
    card(data.center.name, {
      subtitle: data.policy.enabled ? `Stato: ${wf.label}` : 'Percorso di approvazione non attivo per questa struttura', actions: policy,
    }, data.policy.enabled ? steps : alertBox('La struttura chiude il mese direttamente dalla pagina «Controlli e chiusura».', 'info'),
    data.stale ? alertBox('I dati sono cambiati dopo l’invio: il mese va restituito e inviato di nuovo.', 'warn') : null,
    wf.note ? alertBox(`Nota: ${wf.note}`, 'info') : null,
    h('div', { class: 'row' }, actions.length ? actions : h('span', { class: 'muted', text: data.policy.enabled ? 'Nessun passaggio disponibile per il tuo profilo in questo momento.' : '' })),
    h('p', { class: 'small faint', text: `${data.summary.people} persone · ${data.summary.work_entries} turni a consuntivo · ${data.summary.entries} registrazioni` })),
    card('Controlli del mese', { flush: true }, checks),
    card('Storico', { flush: true }, table([
      { label: 'Passaggio', key: 'label' }, { label: 'Nota', render: r => r.note || '—' },
      { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Da', key: 'actor' },
    ], data.history, { empty: 'Nessun passaggio registrato.' })));
}

async function act(ctx, cid, data, action, reload) {
  const needsNote = ['return', 'reopen'].includes(action.id);
  const note = textarea('note', '', { max: 2000 });
  const calendar = checkbox('calendar', false, 'Ho verificato calendario e parametri del mese');
  const body = h('div', { class: 'stack' },
    h('p', { text: {
      submit: 'Il mese viene inviato al responsabile e da questo momento non si può più modificare.',
      manager_approve: 'Confermi i controlli e inoltri il mese a HR centrale.',
      hr_approve: 'Approvi il mese: viene chiuso e i dati restano bloccati.',
      return: 'Il mese torna alla struttura per le correzioni.',
      reopen: 'Il mese viene riaperto e l’approvazione precedente non vale più.',
    }[action.id] }),
    action.id === 'manager_approve' && !data.verified ? calendar : null,
    field(needsNote ? 'Motivazione (almeno 8 caratteri)' : 'Nota (facoltativa)', note));
  const ok = await dialog(action.label, body, [{ label: 'Annulla', value: null }, { label: action.label, kind: needsNote ? 'danger' : 'primary', onClick: async () => {
    try {
      await post(`approvals/${cid}/${ctx.app.month}`, { action: action.id, version: data.workflow.version, fingerprint: data.fingerprint,
        note: note.value, calendar_checked: calendar.querySelector('input').checked });
      toast('Passaggio registrato.', 'ok');
      return true;
    } catch (err) { toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) reload();
}

async function configure(ctx, cid, data, reload) {
  const reason = textarea('reason', '', { max: 1000 });
  const enable = !data.policy.enabled;
  const ok = await dialog(enable ? 'Attiva il percorso di approvazione' : 'Disattiva il percorso di approvazione', h('div', { class: 'stack' },
    h('p', { text: enable ? 'Da ora la struttura invierà ogni mese al responsabile e a HR centrale.' : 'La struttura tornerà a chiudere i mesi direttamente.' }),
    field('Motivazione (almeno 8 caratteri)', reason)), [{ label: 'Annulla', value: null }, { label: enable ? 'Attiva' : 'Disattiva', kind: 'primary', onClick: async () => {
    try {
      await put(`approvals/${cid}/policy`, { enabled: enable, reason: reason.value, version: data.policy.version });
      return true;
    } catch (err) { toast(errorMessage(err), 'bad'); return false; }
  } }]);
  if (ok) reload();
}
