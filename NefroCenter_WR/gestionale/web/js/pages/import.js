// Importa Excel: anteprima senza scritture, poi conferma. La conferma crea una nuova struttura oppure aggiunge il mese
// a una struttura esistente con lo stesso nome (mese vuoto e aperto). Le celle non riconosciute restano da completare a mano.
import { api, post } from '../api.js';
import { alertBox, button, card, clear, errorMessage, field, fmt, h, kpi, table, toast } from '../ui.js';

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
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) { clear(out, alertBox(errorMessage(err), 'bad')); } finally { analyse.disabled = false; }
  } });
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Importa il modello Excel delle presenze' }),
      h('p', { text: 'Il file viene letto senza aprire Excel e senza eseguire macro. L’anteprima non scrive nulla; la conferma fa prima un backup, poi crea una nuova struttura o aggiunge il mese a una struttura esistente con lo stesso nome.' }))),
    card('File', { subtitle: 'Modello mensile in formato .xlsx o .xlsm, massimo 12 MB.' }, h('div', { class: 'form-grid' }, field('File Excel', file),
      h('div', { class: 'field end' }, analyse)),
      h('ul', { class: 'small muted' },
        h('li', { text: 'Vengono importati: persone (dipendenti e collaboratori), turni e assenze del mese, sede esterna (sfondo giallo), festivo (carattere rosso), pazienti per fascia, festività dell’anno, pazienti di riferimento per infermiere e medico, proposte economiche dalle formule.' }),
        h('li', { text: 'Non vengono importati: orari (il modello non li ha), importi e IBAN del foglio «Collaboratori» (restano come promemoria nelle note), celle con valori non riconosciuti (vengono elencate).' }))),
    out);
}

function previewCard(ctx, res) {
  const importable = res.targets.filter(t => t.importable);
  let target = importable.length === 1 ? importable[0].id : '';
  const choice = h('div', { class: 'stack', role: 'radiogroup', 'aria-label': 'Dove importare' });
  const option = (value, label, text, disabled) => {
    const radio = h('input', { type: 'radio', name: 'target', value, checked: value === target, disabled });
    radio.addEventListener('change', () => { target = value; });
    return h('label', { class: `check ${disabled ? 'muted' : ''}`.trim() }, radio, h('span', null, h('strong', { text: label }), text ? h('span', { class: 'small muted', text: ' · ' + text }) : null));
  };
  for (const t of res.targets) {
    choice.append(option(t.id, `Aggiungi il mese alla struttura esistente «${t.name}» (${t.code})`,
      t.importable ? 'le persone con lo stesso nome vengono riutilizzate; i parametri della struttura non cambiano' : `non possibile: ${t.reason}`, !t.importable));
  }
  choice.append(option('', res.targets.length ? `Crea una nuova struttura «${res.center}»` : `Crea la struttura «${res.center}»`,
    'con i parametri letti dal file (festività, pazienti di riferimento, ruoli)', false));

  const confirm = button('Conferma l’importazione', { kind: 'primary', ic: 'check', onClick: async () => {
    confirm.disabled = true;
    try {
      const done = await post('import/confirm', { key: res.key, target: target || null });
      if (done.already_imported) toast('Questo file era già stato importato: apro la struttura esistente.', '');
      else toast(`Importazione completata: ${fmt.number(done.people)} persone` + (done.skipped ? `, ${fmt.number(done.skipped)} celle da completare a mano.` : '.'), 'ok');
      await ctx.reloadProfile();
      ctx.setContext(done.center_id, done.month);
      ctx.go('presenze');
    } catch (err) { toast(errorMessage(err), 'bad'); confirm.disabled = false; }
  } });
  const skippedRows = res.skipped.map(s => ({ ...s, when: `${fmt.date(s.day)} · ${({ m: 'Mattina', p: 'Pomeriggio', s: 'Serale', n: 'Notte' })[s.slot] || s.slot}` }));
  return h('div', { class: 'stack' },
    card(`Anteprima · ${res.center}`, { subtitle: `Mese ${fmt.month(res.month)} · impronta ${res.hash.slice(0, 12)}…` },
      h('div', { class: 'kpis' }, kpi('Persone', fmt.number(res.people), `${fmt.number(res.groups.dipendente)} dipendenti · ${fmt.number(res.groups.consulente)} collaboratori`),
        kpi('Registrazioni', fmt.number(res.entries), `${fmt.number(res.holiday_entries)} in giorno festivo`),
        kpi('Fuori sede', fmt.number(res.external), 'sede da indicare a mano', res.external ? 'warn' : ''),
        kpi('Celle non importate', fmt.number(res.skipped_total), 'da completare nel registro', res.skipped_total ? 'warn' : 'ok'),
        kpi('Giorni con pazienti', fmt.number(res.workload_days), 'pazienti per fascia'),
        kpi('Proposte economiche', fmt.number(res.proposals), 'da confermare negli accordi')),
      res.warnings.length ? h('div', { class: 'alerts' }, res.warnings.map(w => alertBox(w, 'warn'))) : alertBox('Nessuna segnalazione sul file.', 'ok')),
    res.skipped_total ? card('Celle non importate', { subtitle: 'Valori che il portale non riconosce: dopo l’importazione vanno registrati a mano nel registro.' },
      table([{ key: 'cell', label: 'Cella' }, { key: 'person', label: 'Persona' }, { key: 'when', label: 'Giorno e fascia' },
        { key: 'value', label: 'Valore', class: 'mono' }, { key: 'reason', label: 'Motivo' }], skippedRows)) : null,
    card('Persone riconosciute', { subtitle: 'Ruolo e contratto come scritti nel file; «righe» indica la posizione nel foglio «Da Compilare».' },
      table([{ key: 'name', label: 'Nome' }, { key: 'role', label: 'Ruolo' }, { key: 'group', label: 'Sezione' },
        { key: 'contract', label: 'Contratto', render: p => p.billing ? `${p.contract} (${p.billing})` : p.contract },
        { key: 'rows', label: 'Righe', render: p => p.rows.join(', ') }, { key: 'entries', label: 'Registrazioni', num: true },
        { key: 'proposal', label: 'Proposta', render: p => p.proposal ? 'sì' : '—' },
        { key: 'collaborator', label: 'Foglio Collaboratori', render: p => p.collaborator ? p.collaborator.replace('Foglio Collaboratori: ', '') : '—' }], res.persons)),
    card('Dove importare', { actions: confirm },
      choice,
      h('p', { class: 'small muted', text: 'Dopo la conferma: assegna la struttura agli account, completa matricole e orari, registra a mano le celle non importate e sostituisci «Sede esterna da specificare» con la sede reale.' })));
}
