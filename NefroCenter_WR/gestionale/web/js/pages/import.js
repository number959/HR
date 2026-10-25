// Importa Excel: anteprima senza scritture, poi conferma che crea una nuova struttura con persone e registrazioni del mese.
import { api, post } from '../api.js';
import { alertBox, button, card, clear, errorMessage, field, fmt, h, kpi, toast } from '../ui.js';

export async function render(ctx) {
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'aria-label': 'File Excel' });
  const out = h('div');
  const analyse = button('Analizza il file', { kind: 'primary', ic: 'upload', onClick: async () => {
    const chosen = file.files[0];
    if (!chosen) return toast('Scegli prima il file Excel.', 'bad');
    if (chosen.size > 12_000_000) return toast('Il file supera 12 MB.', 'bad');
    analyse.disabled = true;
    try {
      const res = await api('import/preview', { method: 'POST', raw: await chosen.arrayBuffer(),
        contentType: chosen.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      clear(out, previewCard(ctx, res));
    } catch (err) { clear(out, alertBox(errorMessage(err), 'bad')); } finally { analyse.disabled = false; }
  } });
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Importa il modello Excel delle presenze' }),
      h('p', { text: 'Il file viene letto senza aprire Excel e senza eseguire macro. L’anteprima non scrive nulla; la conferma crea una nuova struttura e fa prima un backup.' }))),
    card('File', { subtitle: 'Modello mensile in formato .xlsx o .xlsm, massimo 12 MB.' }, h('div', { class: 'form-grid' }, field('File Excel', file),
      h('div', { class: 'field end' }, analyse))),
    out);
}

function previewCard(ctx, res) {
  const confirm = button('Conferma l’importazione', { kind: 'primary', ic: 'check', onClick: async () => {
    confirm.disabled = true;
    try {
      const done = await post('import/confirm', { key: res.key });
      if (done.already_imported) toast('Questo file era già stato importato: apro la struttura esistente.', '');
      else toast('Importazione completata. Controlla le registrazioni segnalate da verificare.', 'ok');
      await ctx.reloadProfile();
      ctx.setContext(done.center_id, done.month);
      ctx.go('presenze');
    } catch (err) { toast(errorMessage(err), 'bad'); confirm.disabled = false; }
  } });
  return card(`Anteprima · ${res.center}`, { subtitle: `Mese ${fmt.month(res.month)} · impronta ${res.hash.slice(0, 12)}…`, actions: confirm },
    h('div', { class: 'kpis' }, kpi('Persone', fmt.number(res.people)), kpi('Registrazioni', fmt.number(res.entries)),
      kpi('Fuori sede', fmt.number(res.external), 'sede da indicare a mano', res.external ? 'warn' : ''),
      kpi('Proposte economiche', fmt.number(res.proposals), 'da confermare negli accordi')),
    res.warnings.length ? h('div', { class: 'alerts' }, res.warnings.map(w => alertBox(w, 'warn'))) : alertBox('Nessuna segnalazione sul file.', 'ok'),
    h('p', { class: 'small muted', text: 'Dopo la conferma: assegna la nuova struttura agli account, completa matricole e orari e sostituisci «Sede esterna da specificare» con la sede reale.' }));
}
