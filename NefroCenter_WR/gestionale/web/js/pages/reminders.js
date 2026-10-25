// Promemoria HR automatici: configurazione, anteprima dei destinatari, attivazione confermata, storico. Spenti per impostazione.
import { get, post, put } from '../api.js';
import { alertBox, badge, button, card, checkbox, clear, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, toast } from '../ui.js';

const RECIPIENTS = [['structure_hr', 'Email HR di ogni struttura (dalla rubrica)'], ['central_hr', 'Solo HR centrale'], ['both', 'Entrambi']];
const STATUS_TONE = { pending: '', sending: 'info', accepted: 'ok', failed: 'bad', uncertain: 'bad', simulated: 'info' };

export async function render(ctx) {
  const data = await get('reminders');
  const cfg = data.config;
  const editable = data.can_configure;
  const topics = h('div', { class: 'row tight' }, data.topics.map(t => {
    const box = checkbox('topic', cfg.topics.includes(t.id), t.label);
    box.querySelector('input').value = t.id;
    box.querySelector('input').disabled = !editable;
    return box;
  }));
  const centerBoxes = h('div', { class: 'row tight' }, data.centers.map(c => {
    const box = checkbox('center', cfg.centers.includes(c.id), c.name);
    box.querySelector('input').value = c.id;
    box.querySelector('input').disabled = !editable;
    return box;
  }));
  const offsets = input('offsets', cfg.offsets.join(', '), { disabled: !editable });
  const mode = select('recipient_mode', RECIPIENTS, cfg.recipient_mode, { disabled: !editable });
  const central = input('central_hr_email', cfg.central_hr_email, { type: 'email', disabled: !editable });
  const hour = input('hour', cfg.hour, { type: 'number', min: '0', disabled: !editable });
  const daily = input('max_daily_messages', cfg.max_daily_messages, { type: 'number', min: '1', disabled: !editable });
  const overdue = input('max_overdue_days', cfg.max_overdue_days, { type: 'number', min: '1', disabled: !editable });
  const enabled = checkbox('enabled', cfg.enabled, 'Attiva l’invio automatico dei promemoria');
  enabled.querySelector('input').disabled = !editable;
  const confirmed = checkbox('confirmed', false, 'Ho controllato l’anteprima: destinatari e contenuti sono corretti');
  const out = h('div');
  let last = null;
  const values = () => ({
    enabled: enabled.querySelector('input').checked,
    centers: [...centerBoxes.querySelectorAll('input:checked')].map(x => x.value),
    topics: [...topics.querySelectorAll('input:checked')].map(x => x.value),
    offsets: offsets.value.split(/[,;\s]+/).filter(Boolean).map(Number),
    recipient_mode: mode.value, central_hr_email: central.value.trim(), hour: Number(hour.value),
    max_daily_messages: Number(daily.value), max_overdue_days: Number(overdue.value),
  });
  const form = h('form', { class: 'stack', novalidate: true },
    h('fieldset', { dataset: { field: 'topics' } }, h('legend', { text: 'Argomenti' }), topics),
    h('fieldset', { dataset: { field: 'centers' } }, h('legend', { text: 'Strutture (nessuna = tutte le attive)' }), centerBoxes),
    h('div', { class: 'form-grid' },
      field('Anticipi in giorni', offsets, { name: 'offsets', hint: 'Per esempio 30, 15, 7, 0 (0 = il giorno stesso).' }),
      field('Destinatari', mode, { name: 'recipient_mode' }), field('Email di HR centrale', central, { name: 'central_hr_email' }),
      field('Ora di invio (0-23)', hour, { name: 'hour' }), field('Massimo messaggi al giorno', daily, { name: 'max_daily_messages' }),
      field('Ritardi considerati (giorni)', overdue, { name: 'max_overdue_days' })),
    editable ? h('div', { class: 'form-actions' }, button('Anteprima dei destinatari', { ic: 'eye', onClick: async () => {
      try {
        last = await post('reminders/preview', values());
        clear(out, previewCard(last));
      } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
    } })) : null,
    out,
    editable ? h('fieldset', null, h('legend', { text: 'Salvataggio' }), enabled, confirmed,
      h('p', { class: 'small muted', text: 'Per attivare servono: anteprima appena generata, conferma, recapiti HR validi e server di posta aziendale attivo.' }),
      h('div', { class: 'form-actions' }, button('Salva', { kind: 'primary', type: 'submit', ic: 'check' }))) : null);
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await put('reminders', { ...values(), version: cfg.version, fingerprint: last?.fingerprint || '', confirmed: confirmed.querySelector('input').checked });
      toast('Configurazione dei promemoria salvata.', 'ok');
      ctx.refresh();
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Promemoria' }),
      h('h1', { text: 'Promemoria HR automatici' }),
      h('div', { class: 'row' }, cfg.enabled ? badge('Attivi', 'ok', true) : badge('Disattivati', '', true),
        data.smtp_ready ? badge('Server di posta pronto', 'ok') : badge('Server di posta non configurato', 'warn')))),
    alertBox('I messaggi contengono solo conteggi per struttura, senza nomi di dipendenti. Ogni promemoria parte una sola volta; errori ed esiti incerti non vengono reinviati da soli.', 'info'),
    data.changed_routes.length ? alertBox('I recapiti di alcune strutture sono cambiati dopo l’attivazione: i promemoria verso di esse sono sospesi finché non si conferma di nuovo.', 'warn') : null,
    data.warnings.length ? h('div', { class: 'alerts' }, data.warnings.map(w => alertBox(w.message, 'warn'))) : null,
    card('Configurazione', { subtitle: editable ? `Fuso orario ${data.timezone}` : 'Sola consultazione: la configurazione spetta all’amministratore.' }, form),
    h('div', { class: 'grid grid-2' },
      card('Ultimi controlli automatici', { flush: true }, table([
        { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Esito', key: 'state' },
        { label: 'Messaggi', num: true, render: r => fmt.number(r.messages) }, { label: 'Nota', key: 'note' },
      ], data.runs, { empty: 'Nessun controllo eseguito.' })),
      card('Messaggi inviati', { flush: true }, table([
        { label: 'Quando', render: r => fmt.stamp(r.created_at) }, { label: 'A', key: 'email' },
        { label: 'Eventi', num: true, render: r => fmt.number(r.events) }, { label: 'Stato', render: r => badge(r.status_label, STATUS_TONE[r.status]) },
      ], data.history, { empty: 'Nessun promemoria inviato.' }))));
}

function previewCard(p) {
  return card(`Anteprima al ${fmt.date(p.date)}`, { subtitle: `${p.total_messages} messaggi per ${p.pending_events} eventi da segnalare` },
    h('div', { class: 'kpis' }, kpi('Strutture coperte', fmt.number(Object.keys(p.routes).length)), kpi('Eventi', fmt.number(p.total_events)),
      kpi('Messaggi', fmt.number(p.total_messages)), kpi('Attivabile', p.can_enable ? 'Sì' : 'No', p.can_enable ? 'recapiti validi' : 'correggere i recapiti', p.can_enable ? 'ok' : 'bad')),
    p.warnings.length ? h('div', { class: 'alerts' }, p.warnings.map(w => alertBox(w.message, 'warn'))) : null,
    p.messages.slice(0, 3).map(m => h('article', { class: 'mail-preview' }, h('div', { class: 'small faint', text: `A: ${m.email}` }),
      h('h3', { text: m.subject }), h('pre', { class: 'mail-body', text: m.body }))));
}
