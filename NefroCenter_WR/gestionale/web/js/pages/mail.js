// Comunicazioni email: modelli, liste, anteprima, bozze e invio a lotti. Senza server di posta configurato non parte nulla.
import { get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, dialog, empty, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const CAMPAIGN_TONE = { draft: '', partial: 'warn', sending: 'info', uncertain: 'bad', failed: 'bad', accepted: 'ok', simulated: 'info' };
const RECIPIENT_TONE = { pending: '', sending: 'info', accepted: 'ok', failed: 'bad', uncertain: 'bad', simulated: 'info' };

export async function render(ctx) {
  if (ctx.params[0]) return campaignPage(ctx, ctx.params[0]);
  const data = await get('mail');
  let tab = ctx.query.tab || 'nuova';
  const bar = h('div');
  const body = h('div');
  const draw = () => {
    clear(bar, tabs([{ id: 'nuova', label: 'Nuova comunicazione' }, { id: 'bozze', label: 'Bozze e invii', count: data.campaigns.length },
      { id: 'modelli', label: 'Modelli', count: data.templates.length }, { id: 'liste', label: 'Liste', count: data.lists.length },
      { id: 'server', label: 'Server di posta' }], tab, id => { tab = id; draw(); }));
    const views = { nuova: () => compose(ctx, data), bozze: () => campaigns(ctx, data), modelli: () => templates(ctx, data),
      liste: () => lists(ctx, data), server: () => server(ctx, data) };
    clear(body, views[tab]());
  };
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Comunicazioni' }),
      h('h1', { text: 'Email al personale e alle strutture' }),
      h('p', { text: 'Prepara modelli e liste, controlla l’anteprima di ogni messaggio e crea una bozza: l’invio avviene a piccoli lotti, sempre dopo una conferma.' }))),
    serviceBanner(data.settings), bar, body);
}

function serviceBanner(s) {
  if (s.simulated) return alertBox('Demo pubblica: gli invii sono soltanto simulati, nessun messaggio esce dal browser.', 'info');
  if (!s.configured) return alertBox('Servizio di posta non ancora configurato: si possono preparare modelli, liste, anteprime e bozze, ma nessun messaggio può partire.', 'warn');
  if (!s.enabled) return alertBox('Servizio di posta configurato ma disattivato: nessun messaggio può partire finché l’amministratore non lo attiva.', 'warn');
  return alertBox('Servizio di posta attivo: i messaggi partono solo dopo la conferma di ogni lotto.', 'ok');
}

function compose(ctx, data) {
  if (!data.templates.length || !data.lists.length) {
    return empty('Prima prepara un modello e una lista', 'Servono almeno un modello di messaggio e una lista di destinatari.');
  }
  const template = select('template_id', data.templates.map(t => [t.id, t.name]), data.templates[0].id);
  const list = select('list_id', data.lists.map(l => [l.id, l.name]), data.lists[0].id);
  const name = input('name', '', { max: 300, placeholder: 'Facoltativo: un nome per ritrovare la bozza' });
  const subject = input('subject', '', { max: 300 });
  const body = textarea('body', '', { rows: 10, max: 20000 });
  const fill = () => { const t = data.templates.find(x => x.id === template.value); subject.value = t.subject; body.value = t.body; };
  template.addEventListener('change', fill);
  fill();
  const out = h('div');
  const form = h('form', { class: 'stack', novalidate: true },
    h('div', { class: 'form-grid' }, field('Modello', template, { name: 'template_id' }), field('Lista dei destinatari', list, { name: 'list_id' }),
      field('Nome della bozza', name, { name: 'name' })),
    field('Oggetto', subject, { name: 'subject' }), field('Messaggio', body, { name: 'body', hint: 'Il testo modificato qui vale solo per questa comunicazione.' }),
    variablesHelp(data.variables),
    h('div', { class: 'form-actions' }, button('Anteprima dei messaggi', { kind: 'primary', type: 'submit', ic: 'eye' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const payload = { template_id: template.value, list_id: list.value, subject: subject.value, body: body.value };
    try {
      const res = await post('mail/preview', payload);
      clear(out, previewCard(ctx, res, { ...payload, name: name.value }));
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return h('div', { class: 'stack' }, card('Componi', {}, form), out);
}

function variablesHelp(variables) {
  return h('details', { class: 'history' }, h('summary', { text: 'Variabili disponibili' }),
    h('div', { class: 'result-grid' }, variables.map(v => h('div', null, h('span', { class: 'mono', text: `{{${v.id}}}` }), h('div', { class: 'small faint', text: v.label })))));
}

function previewCard(ctx, res, payload) {
  const c = res.counts;
  const create = button('Crea la bozza', { kind: 'primary', ic: 'check', disabled: !res.can_create, onClick: async () => {
    try {
      const campaign = await post('mail/campaigns', { ...payload, fingerprint: res.fingerprint });
      toast('Bozza creata: nessun messaggio è stato inviato.', 'ok');
      ctx.go(`comunicazioni/${campaign.id}`);
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } });
  return card('Anteprima', { subtitle: `${c.valid} destinatari validi su ${c.selected} selezionati`, actions: create },
    h('div', { class: 'kpis' }, kpi('Validi', fmt.number(c.valid), 'riceveranno il messaggio', 'ok'),
      kpi('Senza email', fmt.number(c.missing), 'esclusi', c.missing ? 'warn' : ''), kpi('Email non valide', fmt.number(c.invalid), 'esclusi', c.invalid ? 'warn' : ''),
      kpi('Doppioni ed esclusi', fmt.number(c.duplicates + c.excluded), 'non ripetuti')),
    res.warnings.length ? h('div', { class: 'alerts' }, res.warnings.slice(0, 30).map(w => alertBox(w.message, w.severity === 'error' ? 'bad' : 'warn'))) : null,
    res.recipients.slice(0, 5).map(r => h('article', { class: 'mail-preview' }, h('div', { class: 'small faint', text: `A: ${r.name} <${r.email}>` }),
      h('h3', { text: r.subject }), h('pre', { class: 'mail-body', text: r.body }))),
    res.recipients.length > 5 ? h('p', { class: 'small muted', text: `… e altri ${res.recipients.length - 5} messaggi personalizzati.` }) : null);
}

function campaigns(ctx, data) {
  return card(null, { flush: true }, table([
    { label: 'Bozza', render: c => h('div', null, h('strong', { text: c.name }), h('div', { class: 'small faint', text: c.source === 'reminders' ? 'Promemoria automatico' : `Creata da ${c.created_by}` })) },
    { label: 'Creata', render: c => fmt.stamp(c.created_at) },
    { label: 'Destinatari', num: true, render: c => fmt.number(c.counts.total) },
    { label: 'Da inviare', num: true, render: c => fmt.number(c.remaining) },
    { label: 'Stato', render: c => badge(c.status_label, CAMPAIGN_TONE[c.status]) },
  ], data.campaigns, { empty: 'Nessuna bozza.', onRow: c => ctx.go(`comunicazioni/${c.id}`) }));
}

function templates(ctx, data) {
  return card('Modelli dei messaggi', { actions: button('Nuovo modello', { small: true, ic: 'plus', onClick: () => templateDialog(ctx, data, null) }), flush: true },
    table([{ label: 'Nome', render: t => h('strong', { text: t.name }) }, { label: 'Oggetto', key: 'subject' },
      { label: '', render: t => button('Modifica', { small: true, ic: 'edit', onClick: () => templateDialog(ctx, data, t) }) }], data.templates));
}

async function templateDialog(ctx, data, t) {
  const name = input('name', t?.name || '', { max: 120 });
  const subject = input('subject', t?.subject || '', { max: 300 });
  const body = textarea('body', t?.body || '', { rows: 10, max: 20000 });
  const form = h('form', { class: 'stack', novalidate: true }, field('Nome del modello', name, { name: 'name' }), field('Oggetto', subject, { name: 'subject' }),
    field('Messaggio', body, { name: 'body' }), variablesHelp(data.variables));
  const ok = await dialog(t ? 'Modifica modello' : 'Nuovo modello', form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    const payload = { name: name.value, subject: subject.value, body: body.value, version: t?.version || 0 };
    try { if (t) await put(`mail/templates/${t.id}`, payload); else await post('mail/templates', payload); return true; } catch (err) {
      if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
      return false;
    }
  } }], { wide: true });
  if (ok) { toast('Modello salvato.', 'ok'); ctx.go('comunicazioni?tab=modelli'); }
}

function lists(ctx, data) {
  const centerName = id => data.centers.find(c => c.id === id)?.name || id;
  return card('Liste dei destinatari', { actions: button('Nuova lista', { small: true, ic: 'plus', onClick: () => listDialog(ctx, data, null) }), flush: true },
    table([{ label: 'Nome', render: l => h('strong', { text: l.name }) },
      { label: 'Destinatari', render: l => l.recipient_type === 'structures' ? 'Strutture' : 'Dipendenti' },
      { label: 'Strutture', render: l => l.cids.length ? l.cids.map(centerName).join(', ') : 'Tutte' },
      { label: 'Filtri', render: l => [l.roles.join(', '), l.stages.map(s => data.stages.find(x => x.id === s)?.label || s).join(', ')].filter(Boolean).join(' · ') || '—' },
      { label: '', render: l => button('Modifica', { small: true, ic: 'edit', onClick: () => listDialog(ctx, data, l) }) }], data.lists, { empty: 'Nessuna lista.' }));
}

async function listDialog(ctx, data, l) {
  const name = input('name', l?.name || '', { max: 120 });
  const type = select('recipient_type', [['employees', 'Dipendenti'], ['structures', 'Strutture (recapiti della rubrica)']], l?.recipient_type || 'employees');
  const emailField = select('email_field', [['company_email', 'Email aziendale'], ['email', 'Email personale']], l?.email_field || 'company_email');
  const structureField = select('structure_field', [['email', 'Email generale'], ['hr_email', 'Email ufficio HR'], ['admin_email', 'Email amministrazione']], l?.structure_field || 'email');
  const checks = (items, chosen) => h('div', { class: 'row tight' }, items.map(([id, label]) => {
    const box = checkbox('x', chosen.includes(id), label);
    box.querySelector('input').value = id;
    return box;
  }));
  const cids = checks(data.centers.map(c => [c.id, c.name]), l?.cids || []);
  const roles = checks(data.roles.map(r => [r, r]), l?.roles || []);
  const stages = checks(data.stages.map(s => [s.id, s.label]), l?.stages || []);
  const exclude = textarea('exclude_emails', (l?.exclude_emails || []).join('\n'), { rows: 3 });
  const employeeOnly = h('div', { class: 'stack' }, field('Indirizzo da usare', emailField),
    h('fieldset', null, h('legend', { text: 'Ruoli (nessuno = tutti)' }), roles), h('fieldset', null, h('legend', { text: 'Stato nel fascicolo (nessuno = tutti)' }), stages));
  const structureOnly = field('Recapito della struttura', structureField);
  const sync = () => { employeeOnly.classList.toggle('hidden', type.value !== 'employees'); structureOnly.classList.toggle('hidden', type.value === 'employees'); };
  type.addEventListener('change', sync);
  sync();
  const values = box => [...box.querySelectorAll('input:checked')].map(x => x.value);
  const form = h('form', { class: 'stack', novalidate: true }, field('Nome della lista', name, { name: 'name' }), field('Destinatari', type, { name: 'recipient_type' }),
    h('fieldset', { dataset: { field: 'cids' } }, h('legend', { text: 'Strutture (nessuna = tutte quelle visibili)' }), cids), employeeOnly, structureOnly,
    field('Indirizzi da escludere (uno per riga)', exclude, { name: 'exclude_emails' }));
  const ok = await dialog(l ? 'Modifica lista' : 'Nuova lista', form, [{ label: 'Annulla', value: null }, { label: 'Salva', kind: 'primary', onClick: async () => {
    const employees = type.value === 'employees';
    const payload = { name: name.value, recipient_type: type.value, cids: values(cids), roles: employees ? values(roles) : [], stages: employees ? values(stages) : [],
      email_field: emailField.value, structure_field: structureField.value, exclude_emails: exclude.value.split('\n').map(x => x.trim()).filter(Boolean), version: l?.version || 0 };
    try { if (l) await put(`mail/lists/${l.id}`, payload); else await post('mail/lists', payload); return true; } catch (err) {
      if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
      return false;
    }
  } }], { wide: true });
  if (ok) { toast('Lista salvata.', 'ok'); ctx.go('comunicazioni?tab=liste'); }
}

function server(ctx, data) {
  const s = data.settings;
  if (!ctx.app.can('comunicazioni.configura')) {
    return card('Server di posta', {}, h('p', { text: s.configured ? (s.enabled ? 'Configurato e attivo.' : 'Configurato ma disattivato.') : 'Non configurato.' }),
      h('p', { class: 'small muted', text: 'La configurazione spetta all’amministratore.' }));
  }
  const f = {
    host: input('host', s.host, { max: 254, placeholder: 'es. smtp.dominio-aziendale.it' }), port: input('port', s.port, { type: 'number', min: '1' }),
    security: select('security', [['ssl', 'SSL/TLS'], ['starttls', 'STARTTLS']], s.security), username: input('username', s.username, { max: 254 }),
    from_email: input('from_email', s.from_email, { type: 'email', max: 254 }), from_name: input('from_name', s.from_name, { max: 254 }),
    reply_to: input('reply_to', s.reply_to, { type: 'email', max: 254 }), batch_size: input('batch_size', s.batch_size, { type: 'number', min: '1' }),
    max_per_hour: input('max_per_hour', s.max_per_hour, { type: 'number', min: '1' }),
  };
  const enabled = checkbox('enabled', s.enabled, 'Invio abilitato (i messaggi partono davvero dopo la conferma di ogni lotto)');
  const form = h('form', { class: 'stack', novalidate: true },
    alertBox('Usa solo i dati forniti dal reparto IT o dal fornitore della posta aziendale. La password non si scrive qui: va impostata sul server nella variabile WR_SMTP_PASSWORD.', 'info'),
    h('div', { class: 'form-grid' }, field('Server di posta', f.host, { name: 'host' }), field('Porta', f.port, { name: 'port' }), field('Sicurezza', f.security, { name: 'security' }),
      field('Utente', f.username, { name: 'username' }), field('Mittente (email)', f.from_email, { name: 'from_email' }), field('Nome del mittente', f.from_name, { name: 'from_name' }),
      field('Rispondi a', f.reply_to, { name: 'reply_to' }), field('Messaggi per lotto (massimo 20)', f.batch_size, { name: 'batch_size' }),
      field('Massimo all’ora', f.max_per_hour, { name: 'max_per_hour' })),
    h('p', { class: 'small' }, 'Password sul server: ', s.password_configured ? badge('impostata', 'ok') : badge('non impostata', 'warn')),
    enabled,
    h('div', { class: 'form-actions' }, button('Salva la configurazione', { kind: 'primary', type: 'submit' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const payload = { enabled: enabled.querySelector('input').checked, host: f.host.value.trim(), port: Number(f.port.value), security: f.security.value,
      username: f.username.value.trim(), from_email: f.from_email.value.trim(), from_name: f.from_name.value, reply_to: f.reply_to.value.trim(),
      batch_size: Number(f.batch_size.value), max_per_hour: Number(f.max_per_hour.value), version: s.version };
    try {
      await put('mail/settings', payload);
      toast('Configurazione salvata.', 'ok');
      ctx.go('comunicazioni?tab=server');
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return card('Server di posta aziendale', { subtitle: s.configured ? 'Configurato' : 'Da configurare' }, form);
}

async function campaignPage(ctx, key) {
  const c = await get(`mail/campaigns/${key}`);
  const actions = [];
  if (c.can_send) actions.push(button(`Invia il prossimo lotto (${c.send_plan.count})`, { kind: 'primary', ic: 'send', onClick: () => sendBatch(ctx, c, false) }));
  if (c.can_retry_failed) actions.push(button(`Ritenta i non riusciti (${c.retry_plan.count})`, { ic: 'refresh', onClick: () => sendBatch(ctx, c, true) }));
  if (c.can_reconcile) actions.push(button('Verifica invii interrotti', { ic: 'alert', onClick: async () => {
    try { await post(`mail/campaigns/${key}/reconcile`); toast('Invii interrotti segnati come esito incerto.', 'ok'); ctx.refresh(); } catch (err) { toast(errorMessage(err), 'bad'); }
  } }));
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('a', { class: 'eyebrow', href: '#/comunicazioni?tab=bozze', text: '← Comunicazioni' }),
      h('h1', { text: c.name }), h('div', { class: 'row' }, badge(c.status_label, CAMPAIGN_TONE[c.status], true),
        h('span', { class: 'small muted', text: `Creata il ${fmt.stamp(c.created_at)} da ${c.created_by}` }))),
    h('div', { class: 'page-actions' }, actions)),
    c.simulated ? alertBox('Demo: l’invio è simulato, nessun messaggio esce.', 'info')
      : !c.can_send && c.remaining ? alertBox('Invio non disponibile: servizio di posta non configurato o disattivato, oppure limite orario raggiunto. La bozza resta salvata.', 'warn') : null,
    h('div', { class: 'kpis' }, kpi('Destinatari', fmt.number(c.counts.total)), kpi('Da inviare', fmt.number(c.counts.pending)),
      kpi('Accettati dal server', fmt.number(c.counts.accepted + c.counts.simulated), c.counts.simulated ? 'simulati nella demo' : 'consegna non garantita', 'ok'),
      kpi('Non riusciti o incerti', fmt.number(c.counts.failed + c.counts.uncertain), 'da controllare', c.counts.failed + c.counts.uncertain ? 'bad' : 'ok')),
    card('Messaggio', {}, h('h3', { text: c.subject }), h('pre', { class: 'mail-body', text: c.body })),
    card('Destinatari', { flush: true }, table([
      { label: 'Destinatario', render: r => h('div', null, h('strong', { text: r.name }), h('div', { class: 'small faint', text: r.email })) },
      { label: 'Stato', render: r => badge(r.status_label, RECIPIENT_TONE[r.status]) },
      { label: 'Tentativi', num: true, render: r => fmt.number(r.attempts.length) },
      { label: 'Note', render: r => r.error || '—' },
    ], c.recipients)));
}

async function sendBatch(ctx, c, retry) {
  const plan = retry ? c.retry_plan : c.send_plan;
  const confirm = checkbox('confirm', false, `Confermo destinatari e contenuto: invia ${plan.count} messaggi`);
  const ok = await dialog(retry ? 'Ritenta i non riusciti' : 'Invia un lotto', h('div', { class: 'stack' },
    h('p', { text: c.simulated ? 'Nella demo l’invio è simulato.' : 'I messaggi partono dal server di posta aziendale. Gli esiti incerti non vengono reinviati automaticamente.' }),
    confirm), [{ label: 'Annulla', value: null }, { label: 'Invia', kind: 'primary', onClick: async () => {
    if (!confirm.querySelector('input').checked) { toast('Spunta la conferma per procedere.', 'bad'); return false; }
    try { await post(`mail/campaigns/${c.id}/send`, { confirm: true, retry_failed: retry, confirmation_token: plan.token }); return true; } catch (err) {
      toast(errorMessage(err), 'bad');
      return false;
    }
  } }]);
  if (ok) { toast('Lotto elaborato: controlla lo stato dei destinatari.', 'ok'); ctx.refresh(); }
}
