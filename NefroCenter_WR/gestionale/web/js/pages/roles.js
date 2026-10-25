// Ruoli e permessi: la stessa tabella usata dal server per i controlli.
import { get } from '../api.js';
import { badge, card, h, segmented } from '../ui.js';

export async function render(ctx) {
  const data = await get('roles');
  const mine = ctx.app.me.user.role;
  let focus = mine;
  const box = h('div');
  const areas = [...new Set(data.capabilities.map(c => c.area))];
  const draw = () => {
    const role = data.roles.find(r => r.id === focus);
    box.replaceChildren(
      h('div', { class: 'row' }, segmented(data.roles.map(r => ({ id: r.id, label: r.label })), focus, id => { focus = id; draw(); }, 'Profilo')),
      card(role.label, { subtitle: role.summary, actions: badge(role.scope === 'all' ? 'Tutte le strutture' : 'Strutture assegnate', 'brand') },
        h('div', { class: 'grid grid-2' }, areas.map(area => {
          const rows = data.capabilities.filter(c => c.area === area);
          return h('div', null, h('h3', { text: area }), h('ul', { class: 'perm-list' }, rows.map(c => {
            const yes = c.roles.includes(focus);
            const maybe = !yes && c.conditional.includes(focus);
            return h('li', { class: yes ? 'yes' : maybe ? 'maybe' : 'no' },
              h('span', { class: 'perm-mark', 'aria-hidden': 'true', text: yes ? '✓' : maybe ? '◐' : '—' }),
              h('span', null, c.description, maybe ? h('span', { class: 'small faint', text: ' · se abilitato nei parametri della struttura' }) : null),
              h('span', { class: 'sr-only', text: yes ? 'consentito' : maybe ? 'consentito se abilitato' : 'non consentito' }));
          })));
        }))));
  };
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Ruoli e permessi' }),
      h('h1', { text: 'Chi può fare cosa' }),
      h('p', { text: `Il tuo profilo è «${data.roles.find(r => r.id === mine).label}». I permessi sono controllati dal server: l’interfaccia mostra solo ciò che è consentito.` }))),
    box);
}
