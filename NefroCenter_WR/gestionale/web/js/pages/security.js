// Il mio account: password, app Authenticator, codici di recupero, sessioni e accessi recenti.
import { get, post } from '../api.js';
import { recoveryCodes } from '../auth.js';
import { alertBox, badge, button, card, dialog, errorMessage, field, fmt, h, input, kpi, showErrors, table, toast } from '../ui.js';

export async function render(ctx) {
  const { app } = ctx;
  const data = await get('security');
  const user = app.me.user;
  const demo = data.demo;
  const locked = demo ? alertBox('Nella demo pubblica password, app Authenticator e codici di recupero non si modificano.', 'info') : null;
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Il mio account' }),
      h('h1', { text: user.name }),
      h('div', { class: 'row' }, badge(user.role_label, 'brand'), h('span', { class: 'muted', text: `Nome utente: ${user.username}` })))),
    h('div', { class: 'kpis' },
      kpi('Secondo fattore', data.two_factor ? 'Attivo' : 'Da attivare', 'app Authenticator', data.two_factor ? 'ok' : 'bad'),
      kpi('Codici di recupero', fmt.number(data.recovery_remaining), 'ancora utilizzabili', data.recovery_remaining > 2 ? 'ok' : 'warn'),
      kpi('Sessioni aperte', fmt.number(data.sessions), 'compresa questa'),
      kpi('Ultimo accesso', data.last_login ? fmt.stamp(data.last_login) : '—', 'prima di questa sessione')),
    locked,
    h('div', { class: 'grid grid-2' },
      card('Password', { subtitle: 'Almeno 12 caratteri, diversa dal nome utente.' }, demo ? h('p', { class: 'muted', text: 'Non disponibile nella demo.' }) : passwordForm(ctx)),
      card('App Authenticator e codici di recupero', { subtitle: 'Servono per entrare e per confermare le operazioni sensibili.' },
        h('div', { class: 'stack' },
          h('p', { class: 'muted', text: 'Se cambi telefono, configura qui il nuovo dispositivo: il vecchio smette di funzionare e ricevi nuovi codici di recupero.' }),
          h('div', { class: 'row' },
            button('Configura un nuovo telefono', { ic: 'refresh', disabled: demo, onClick: () => rotate(ctx) }),
            button('Nuovi codici di recupero', { ic: 'key', disabled: demo, onClick: () => newCodes(ctx) }))))),
    card('Sessioni', { subtitle: 'Se hai usato il portale su un computer condiviso, chiudi le altre sessioni.',
      actions: button('Chiudi le altre sessioni', { small: true, ic: 'logout', disabled: data.sessions < 2, onClick: () => closeOthers(ctx) }) },
    h('p', { class: 'small faint', text: 'Le sessioni scadono dopo 15 minuti senza attività e comunque dopo 8 ore.' })),
    card('Ultime operazioni di sicurezza', { flush: true }, table([
      { label: 'Quando', render: r => fmt.stamp(r.at) }, { label: 'Operazione', key: 'action' },
    ], data.history, { empty: 'Nessuna operazione registrata.' })));
}

function passwordForm(ctx) {
  const current = input('current', '', { type: 'password', autocomplete: 'current-password' });
  const next = input('password', '', { type: 'password', autocomplete: 'new-password' });
  const again = input('again', '', { type: 'password', autocomplete: 'new-password' });
  const form = h('form', { class: 'stack', novalidate: true },
    field('Password attuale', current, { name: 'current' }), field('Nuova password', next, { name: 'password' }),
    field('Ripeti la nuova password', again, { name: 'again' }),
    h('div', { class: 'form-actions' }, button('Cambia password', { kind: 'primary', type: 'submit' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (next.value !== again.value) {
      showErrors(form, { field: 'again', message: 'Le due password non coincidono.' });
      return;
    }
    try {
      await post('security/password', { current: current.value, password: next.value });
      toast('Password cambiata. Le altre sessioni sono state chiuse.', 'ok');
      ctx.refresh();
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return form;
}

async function rotate(ctx) {
  let setup;
  try { setup = await post('security/authenticator/start'); } catch (err) { toast(errorMessage(err), 'bad'); return; }
  const code = input('code', '', { inputmode: 'numeric', autocomplete: 'one-time-code', max: 8 });
  const body = h('div', { class: 'stack' },
    h('p', { text: 'Inquadra il codice con l’app Authenticator del nuovo telefono, poi inserisci il codice di 6 cifre che compare.' }),
    h('div', { class: 'qr' }, h('img', { src: setup.qr, alt: 'Codice QR per l’app Authenticator' })),
    h('p', { class: 'small muted' }, 'Se non puoi inquadrarlo, inserisci a mano questa chiave: ', h('span', { class: 'mono', text: setup.secret })),
    field('Codice del nuovo telefono', code, { name: 'code' }));
  const result = await dialog('Nuovo telefono per l’accesso', body, [{ label: 'Annulla', value: null }, { label: 'Conferma', kind: 'primary', onClick: async () => {
    try { return await post('security/authenticator/confirm', { code: code.value }); } catch (err) {
      if (!showErrors(body, err)) toast(errorMessage(err), 'bad');
      return false;
    }
  } }]);
  if (result?.recovery_codes) showCodes(ctx, result.recovery_codes, 'Nuovo telefono configurato: conserva i nuovi codici di recupero.');
}

async function newCodes(ctx) {
  try {
    const result = await post('security/recovery-codes');
    showCodes(ctx, result.recovery_codes, 'I codici precedenti non valgono più.');
  } catch (err) { toast(errorMessage(err), 'bad'); }
}

async function showCodes(ctx, codes, message) {
  const content = recoveryCodes(null, codes, () => document.querySelector('dialog[open] .dialog-head button')?.click());
  await dialog('Codici di recupero', h('div', { class: 'stack' }, alertBox(message, 'info'), content));
  ctx.refresh();
}

async function closeOthers(ctx) {
  try {
    await post('security/sessions/close-others');
    toast('Le altre sessioni sono state chiuse.', 'ok');
    ctx.refresh();
  } catch (err) { toast(errorMessage(err), 'bad'); }
}
