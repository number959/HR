// Accesso: password + app Authenticator, primo accesso con codice di attivazione, conferma per operazioni sensibili.
import { post, setToken } from './api.js';
import { icon } from './icons.js';
import { button, clear, dialog, field, h, input, showErrors, toast } from './ui.js';

const HERO_POINTS = ['Presenze e turni di tutte le strutture', 'Fascicoli, documenti e scadenze del personale',
  'Approvazioni, paghe e comunicazioni in un unico percorso'];

function hero(demo) {
  return h('aside', { class: 'auth-hero' },
    h('div', null,
      h('div', { class: 'logo' }, h('img', { src: 'img/nefrocenter.png', alt: 'NefroCenter' })),
      h('h1', null, 'NefroCenter ', h('span', { text: 'WR' })),
      h('p', { text: 'Work Resources: il portale del personale per presenze, persone e processi HR di tutte le strutture.' }),
      h('ul', null, HERO_POINTS.map(t => h('li', null, icon('check'), t)))),
    h('p', { class: 'legal', text: demo
      ? 'Demo pubblica con dati interamente fittizi. Le modifiche restano solo in questa scheda del browser.'
      : 'Accesso riservato al personale autorizzato. Ogni operazione è registrata.' }));
}

function page(demo, ...content) {
  return h('div', { class: 'auth-page' }, hero(demo), h('main', { class: 'auth-panel', id: 'content' },
    h('div', { class: 'card auth-card' }, h('div', { class: 'card-body' }, content))));
}

async function submit(form, action) {
  const buttonEl = form.querySelector('button[type="submit"]');
  buttonEl.disabled = true;
  try {
    return await action();
  } catch (err) {
    if (!showErrors(form, err)) toast(err.message, 'bad');
    return null;
  } finally {
    buttonEl.disabled = false;
  }
}

export function renderAuth(root, state, done) {
  if (state.demo) return demoLogin(root, done);
  if (state.stage === 'password') return codeStep(root, done);
  if (!state.configured) {
    return clear(root, page(false, h('h2', { text: 'Installazione da completare' }),
      h('p', { class: 'muted', text: 'Nessun account configurato. Il tecnico deve eseguire sul server «python manage.py init».' })));
  }
  return loginStep(root, done);
}

function loginStep(root, done) {
  const user = input('username', '', { autocomplete: 'username', required: true });
  const password = input('password', '', { type: 'password', autocomplete: 'current-password', required: true });
  const form = h('form', { novalidate: true },
    field('Nome utente', user, { name: 'username' }), field('Password', password, { name: 'password' }),
    button('Continua', { kind: 'primary', type: 'submit' }));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const result = await submit(form, () => post('session/login', { username: user.value, password: password.value }));
    if (result) codeStep(root, done);
  });
  clear(root, page(false, h('h2', { text: 'Accedi' }),
    h('p', { class: 'muted', text: 'Inserisci le credenziali personali. Poi ti verrà chiesto il codice dell’app Authenticator.' }), form,
    h('div', { class: 'auth-switch' }, 'Primo accesso o nuovo telefono? ',
      h('button', { type: 'button', text: 'Usa il codice di attivazione', on: { click: () => activationStep(root, done) } }))));
  user.focus();
}

function codeStep(root, done) {
  let recovery = false;
  const code = input('code', '', { autocomplete: 'one-time-code', inputmode: 'numeric', required: true, max: 24 });
  const label = h('span', { text: 'Codice a 6 cifre dell’app Authenticator' });
  const form = h('form', { novalidate: true }, h('div', { class: 'field', dataset: { field: 'code' } },
    h('label', { for: 'code-input' }, label), code), button('Accedi', { kind: 'primary', type: 'submit' }));
  code.id = 'code-input';
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const result = await submit(form, () => post('session/verify', { code: code.value, recovery }));
    if (result) done(result);
  });
  const toggle = h('button', { type: 'button', text: 'Usa un codice di recupero', on: { click: () => {
    recovery = !recovery;
    label.textContent = recovery ? 'Codice di recupero (XXXX-XXXX-XXXX-XXXX)' : 'Codice a 6 cifre dell’app Authenticator';
    toggle.textContent = recovery ? 'Usa l’app Authenticator' : 'Usa un codice di recupero';
    code.inputMode = recovery ? 'text' : 'numeric';
    code.value = '';
    code.focus();
  } } });
  clear(root, page(false, h('h2', { text: 'Verifica in due passaggi' }),
    h('p', { class: 'muted', text: 'Apri l’app Authenticator sul telefono e inserisci il codice di NefroCenter WR.' }), form,
    h('div', { class: 'auth-switch' }, toggle)));
  code.focus();
}

function activationStep(root, done) {
  const user = input('username', '', { autocomplete: 'username', required: true });
  const activation = input('activation', '', { required: true, autocomplete: 'off' });
  const form = h('form', { novalidate: true }, field('Nome utente', user, { name: 'username' }),
    field('Codice di attivazione', activation, { name: 'activation', hint: 'Lo ricevi di persona dall’amministratore. Vale 7 giorni e una sola volta.' }),
    button('Continua', { kind: 'primary', type: 'submit' }));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const result = await submit(form, () => post('session/activation', { username: user.value, activation: activation.value.trim() }));
    if (result) enrollStep(root, done, result.setup);
  });
  clear(root, page(false, h('h2', { text: 'Primo accesso' }),
    h('p', { class: 'muted', text: 'Attiva il tuo account: sceglierai la password personale e collegherai l’app Authenticator.' }), form,
    h('div', { class: 'auth-switch' }, h('button', { type: 'button', text: 'Torna all’accesso', on: { click: () => loginStep(root, done) } }))));
  user.focus();
}

function enrollStep(root, done, setup) {
  const password = input('password', '', { type: 'password', autocomplete: 'new-password', required: true });
  const again = input('again', '', { type: 'password', autocomplete: 'new-password', required: true });
  const code = input('code', '', { inputmode: 'numeric', autocomplete: 'one-time-code', required: true, max: 6 });
  const form = h('form', { novalidate: true },
    h('ol', { class: 'muted small' }, h('li', { text: 'Installa un’app Authenticator (per esempio Microsoft o Google Authenticator).' }),
      h('li', { text: 'Inquadra il codice QR oppure inserisci a mano la chiave.' }), h('li', { text: 'Scrivi qui il codice a 6 cifre che appare.' })),
    h('div', { class: 'qr' }, h('img', { src: setup.qr, alt: 'Codice QR per l’app Authenticator' })),
    h('p', { class: 'small muted' }, 'Chiave manuale: ', h('span', { class: 'mono', text: setup.secret.replace(/(.{4})/g, '$1 ').trim() })),
    field('Nuova password personale', password, { name: 'password', hint: 'Almeno 12 caratteri. Una frase lunga è più sicura e più facile da ricordare.' }),
    field('Ripeti la password', again, { name: 'again' }),
    field('Codice a 6 cifre dall’app', code, { name: 'code' }),
    button('Attiva l’account', { kind: 'primary', type: 'submit' }));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (password.value !== again.value) {
      showErrors(form, { field: 'again', message: 'Le due password non coincidono.' });
      return;
    }
    const result = await submit(form, () => post('session/enroll', { password: password.value, code: code.value }));
    if (result) done(result);  // i codici di recupero li mostra app.js, una sola volta
  });
  clear(root, page(false, h('h2', { text: 'Configura il secondo fattore' }), form));
  password.focus();
}

export function recoveryCodes(root, codes, next) {
  const text = codes.join('\n');
  const save = () => {
    const url = URL.createObjectURL(new Blob([`Codici di recupero NefroCenter WR\nOgni codice vale una sola volta.\n\n${text}\n`], { type: 'text/plain' }));
    const a = h('a', { href: url, download: 'codici-recupero-nefrocenter-wr.txt' });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  };
  const confirmBox = h('input', { type: 'checkbox', id: 'saved' });
  const go = button('Ho conservato i codici, entra', { kind: 'primary', disabled: true, onClick: next });
  confirmBox.addEventListener('change', () => { go.disabled = !confirmBox.checked; });
  const content = [h('h2', { text: 'Codici di recupero' }),
    h('p', { class: 'muted', text: 'Servono se perdi il telefono. Conservali in un luogo sicuro, separato dal telefono: non verranno mostrati di nuovo.' }),
    h('div', { class: 'codes', 'aria-label': 'Codici di recupero' }, codes.map(c => h('span', { text: c }))),
    h('div', { class: 'row' }, button('Scarica come file', { ic: 'download', onClick: save }),
      button('Stampa', { ic: 'print', onClick: () => window.print() })),
    h('label', { class: 'check', for: 'saved' }, confirmBox, 'Ho salvato o stampato i codici'), go];
  if (root) clear(root, page(false, content));
  return content;
}

function demoLogin(root, done) {
  const roles = [['demo.admin', 'Amministratore', 'Configura il portale, gli accessi e i servizi.'],
    ['demo.hr', 'HR centrale', 'Persone, documenti e processi HR di tutte le strutture.'],
    ['demo.manager', 'Responsabile di struttura', 'Organizza presenze e persone di Capodichino e Pozzuoli.'],
    ['demo.operator', 'Compilatore', 'Registra le presenze quotidiane di Capodichino.'],
    ['demo.viewer', 'Direzione · consultazione', 'Consulta andamento e statistiche senza modificare.']];
  const list = h('div', { class: 'demo-roles' }, roles.map(([username, label, text]) => h('button', {
    class: 'demo-role', type: 'button', on: { click: async () => {
      try { done(await post('session/demo', { username })); } catch (err) { toast(err.message, 'bad'); }
    } },
  }, h('span', { class: 'avatar', text: label.slice(0, 2).toUpperCase() }), h('span', null, h('strong', { text: label }), h('span', { text })))));
  clear(root, page(true, h('h2', { text: 'Prova la demo' }),
    h('p', { class: 'muted', text: 'Scegli un profilo: vedrai il portale con i permessi di quel ruolo. Nessuna password, dati fittizi.' }), list));
}

// Conferma recente di password e codice per le operazioni sensibili (5 minuti).
export function stepUpDialog() {
  const password = input('password', '', { type: 'password', autocomplete: 'current-password' });
  const code = input('code', '', { inputmode: 'numeric', autocomplete: 'one-time-code', max: 24 });
  const recovery = h('input', { type: 'checkbox', name: 'recovery' });
  const form = h('form', { class: 'stack' },
    h('p', { class: 'muted', text: 'Per questa operazione conferma che sei tu. La conferma vale 5 minuti.' }),
    field('Password', password, { name: 'password' }), field('Codice dell’app Authenticator', code, { name: 'code' }),
    h('label', { class: 'check' }, recovery, 'Uso un codice di recupero'));
  return dialog('Conferma di sicurezza', form, [
    { label: 'Annulla', value: false },
    { label: 'Conferma', kind: 'primary', onClick: async () => {
      try {
        await post('session/step-up', { password: password.value, code: code.value, recovery: recovery.checked }, { retry: false });
        return true;
      } catch (err) {
        if (!showErrors(form, err)) toast(err.message, 'bad');
        return false;
      }
    } },
  ]);
}

export function rememberToken(state) { if (state?.csrf) setToken(state.csrf); }
