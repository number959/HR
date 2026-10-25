// Accessi e ruoli: account, ruoli, strutture assegnate, attivazione e ripristino dell'accesso.
import { get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, dialog, errorMessage, field, fmt, h, input, kpi, personCell, select, showErrors, table, textarea, toast,
} from '../ui.js';

export async function render(ctx) {
  const { app } = ctx;
  const data = await get('users');
  const centers = app.me.centers;
  const names = Object.fromEntries(centers.map(c => [c.id, c.name]));
  const scopeAll = Object.fromEntries(data.roles.map(r => [r.id, r.scope === 'all']));
  const active = data.users.filter(u => u.active);
  const columns = [
    { label: 'Persona', render: u => personCell(u.name, u.username) },
    { label: 'Ruolo', render: u => badge(u.role_label, u.role === 'admin' ? 'bad' : 'brand') },
    { label: 'Strutture', render: u => scopeAll[u.role] ? h('span', { class: 'muted', text: 'Tutte' }) : u.centers.map(c => names[c] || c).join(', ') || '—' },
    { label: 'Stato', render: u => !u.active ? badge('Disattivato', '') : u.activation_pending ? badge('Attivazione in attesa', 'warn', true)
      : u.two_factor ? badge('Attivo', 'ok', true) : badge('Secondo fattore mancante', 'bad', true) },
    { label: 'Ultimo accesso', render: u => u.last_login ? fmt.stamp(u.last_login) : '—' },
    { label: '', render: u => h('div', { class: 'row' },
      button('Modifica', { small: true, ic: 'edit', onClick: () => edit(ctx, data, u) }),
      u.id !== app.me.user.id ? button('Nuovo codice', { small: true, ic: 'key', onClick: () => reset(ctx, u) }) : null) },
  ];
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Accessi e ruoli' }),
      h('p', { text: 'Ogni persona ha un account personale. La password la sceglie l’interessato al primo accesso con il codice di attivazione.' })),
    h('div', { class: 'page-actions' }, button('Nuovo account', { kind: 'primary', ic: 'plus', onClick: () => edit(ctx, data, null) }))),
    h('div', { class: 'kpis' },
      kpi('Account attivi', fmt.number(active.length), `su ${data.users.length}`),
      kpi('Attivazioni in attesa', fmt.number(active.filter(u => u.activation_pending).length), 'codice non ancora usato'),
      kpi('Senza secondo fattore', fmt.number(active.filter(u => !u.two_factor && !u.activation_pending).length), 'da sistemare',
        active.some(u => !u.two_factor && !u.activation_pending) ? 'bad' : 'ok'),
      kpi('Amministratori', fmt.number(active.filter(u => u.role === 'admin').length), 'ne serve almeno uno')),
    card('Account', { flush: true }, table(columns, data.users, { empty: 'Nessun account.' })),
    h('p', { class: 'small faint', text: 'Le modifiche a ruolo, strutture o stato chiudono le sessioni aperte dell’account interessato.' }));
}

async function edit(ctx, data, user) {
  const creating = !user;
  const name = input('name', user?.name || '', { max: 150 });
  const username = input('username', user?.username || '', { max: 60, autocomplete: 'off', disabled: !creating });
  const role = select('role', data.roles.map(r => [r.id, r.label]), user?.role || 'operator');
  const active = checkbox('active', user ? user.active : true, 'Account attivo');
  const chosen = new Set(user?.centers || []);
  const centerBox = h('fieldset', { dataset: { field: 'centers' } }, h('legend', { text: 'Strutture assegnate' }),
    h('div', { class: 'form-grid' }, ctx.app.me.centers.map(c => {
      const box = checkbox('center', chosen.has(c.id), c.name + (c.active ? '' : ' (disattivata)'));
      box.querySelector('input').value = c.id;
      return box;
    })));
  const scopeNote = h('p', { class: 'small muted', text: 'Questo ruolo vede tutte le strutture: non serve assegnarle.' });
  const sync = () => {
    const all = data.roles.find(r => r.id === role.value)?.scope === 'all';
    centerBox.classList.toggle('hidden', all);
    scopeNote.classList.toggle('hidden', !all);
  };
  role.addEventListener('change', sync);
  sync();
  const form = h('form', { class: 'stack', novalidate: true },
    h('div', { class: 'form-grid' }, field('Nome e cognome', name, { name: 'name', required: true }),
      field('Nome utente', username, { name: 'username', required: true, hint: creating ? 'Minuscole, numeri, punto o trattino. Non si cambia dopo.' : null }),
      field('Ruolo', role, { name: 'role' })),
    scopeNote, centerBox, creating ? null : active);
  const result = await dialog(creating ? 'Nuovo account' : `Modifica · ${user.name}`, form, [{ label: 'Annulla', value: null }, {
    label: creating ? 'Crea e genera il codice' : 'Salva', kind: 'primary', onClick: async () => {
      const body = { name: name.value, role: role.value,
        centers: [...centerBox.querySelectorAll('input:checked')].map(i => i.value) };
      try {
        if (creating) return await post('users', { ...body, username: username.value });
        await put(`users/${user.id}`, { ...body, active: active.querySelector('input').checked, version: user.version });
        return { saved: true };
      } catch (err) {
        if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
        return false;
      }
    },
  }], { wide: true });
  if (!result) return;
  if (result.activation_code) await showCode(`Account creato: ${name.value}`, username.value, result);
  else toast('Account aggiornato.', 'ok');
  ctx.refresh();
}

async function reset(ctx, user) {
  const reason = textarea('reason', '', { max: 1000 });
  const form = h('div', { class: 'stack' },
    alertBox('Il secondo fattore e le sessioni dell’account vengono azzerati: la persona dovrà rifare il primo accesso.', 'warn'),
    field('Motivazione (almeno 8 caratteri)', reason, { name: 'reason' }));
  const result = await dialog(`Ripristina l’accesso · ${user.name}`, form, [{ label: 'Annulla', value: null }, {
    label: 'Genera il codice', kind: 'danger', onClick: async () => {
      try { return await post(`users/${user.id}/activation`, { reason: reason.value }); } catch (err) {
        if (!showErrors(form, err)) toast(errorMessage(err), 'bad');
        return false;
      }
    },
  }]);
  if (!result) return;
  await showCode(`Nuovo codice per ${user.name}`, user.username, result);
  ctx.refresh();
}

function showCode(title, username, result) {
  return dialog(title, h('div', { class: 'stack' },
    h('p', { text: 'Comunica questi dati di persona o per telefono, non per email. Il codice si vede solo adesso.' }),
    h('div', { class: 'codes' }, h('span', { text: `Utente: ${username}` }), h('span', { text: `Codice: ${result.activation_code}` })),
    h('p', { class: 'small muted', text: `Il codice vale ${result.activation_days} giorni. All’accesso la persona sceglie «Primo accesso».` })),
  [{ label: 'Ho comunicato il codice', kind: 'primary', value: true }]);
}
