// Importa Excel: anteprima senza scritture, poi conferma. La conferma crea una nuova struttura oppure aggiunge il mese
// a una struttura esistente con lo stesso nome (mese vuoto e aperto). Le celle non riconosciute restano da completare a mano.
// Serve per i mesi passati e per la transizione: il lavoro quotidiano si fa nel portale.
import { api, post } from '../api.js';
import { alertBox, button, card, clear, errorMessage, field, fmt, h, kpi, table, toast } from '../ui.js';

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const SLOTS = { m: 'Mattina', p: 'Pomeriggio', s: 'Serale', n: 'Notte' };

export async function render(ctx) {
  const file = h('input', { type: 'file', accept: '.xlsx,.xlsm,' + XLSX, 'aria-label': 'File Excel' });
  const out = h('div');
  const analyse = button('Analizza il file', { kind: 'primary', ic: 'upload', onClick: async () => {
    const chosen = file.files[0];
    if (!chosen) return toast('Scegli prima il file Excel.', 'bad');
    if (chosen.size > 12_000_000) return toast('Il file supera 12 MB.', 'bad');
    analyse.disabled = true;
    try {
      // Il tipo dichiarato dal browser cambia da un sistema all'altro: il contenuto lo controlla comunque il server.
      const res = await api('import/preview', { method: 'POST', raw: await chosen.arrayBuffer(), contentType: XLSX });
      clear(out, previewCard(ctx, res));
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) { clear(out, alertBox(errorMessage(err), 'bad')); } finally { analyse.disabled = false; }
  } });
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Importa il modello Excel delle presenze' }),
      h('p', { text: 'Per i mesi passati e per la transizione dal vecchio file: il lavoro quotidiano si fa nel portale. Il file viene letto senza aprire Excel e senza eseguire macro. L’anteprima non scrive nulla; la conferma fa prima un backup, poi crea una nuova struttura o aggiunge il mese a una struttura esistente con lo stesso nome.' }))),
    card('File', { subtitle: 'Modello mensile in formato .xlsx o .xlsm, massimo 12 MB.' }, h('div', { class: 'form-grid' }, field('File Excel', file),
      h('div', { class: 'field end' }, analyse)),
      h('ul', { class: 'small muted' },
        h('li', { text: 'Vengono importati: persone (dipendenti e collaboratori), turni e assenze del mese, sede esterna (sfondo giallo), festivo (carattere rosso), pazienti per fascia, festività dell’anno, pazienti di riferimento per infermiere e medico, posti dialisi e contumaciali, proposte economiche dalle formule.' }),
        h('li', { text: 'Non vengono importati: orari (il modello non li ha); gli importi del foglio «Collaboratori» restano solo come promemoria nelle note; l’IBAN non viene letto; le celle con valori non riconosciuti vengono elencate.' }))),
    out);
}

function previewCard(ctx, res) {
  if (res.already_imported) {
    const done = res.already_imported;
    return card(`Anteprima · ${res.center}`, { subtitle: `Mese ${fmt.month(res.month)} · impronta ${res.hash.slice(0, 12)}…` },
      alertBox(`Questo file è già stato importato il ${fmt.stamp ? fmt.stamp(done.at) : done.at} nella struttura «${done.center}». Lo stesso file non si importa due volte: per correggere i dati si lavora nel registro.`, 'info'),
      h('div', { class: 'form-actions' }, button('Apri il registro', { kind: 'primary', ic: 'calendar', onClick: async () => {
        await ctx.reloadProfile();
        ctx.setContext(done.center_id, done.month);
        ctx.go('presenze');
      } })));
  }
  const importable = res.targets.filter(t => t.importable);
  // Una sola struttura importabile: proposta; strutture omonime ma non importabili: nessuna scelta preselezionata.
  let target = importable.length === 1 ? importable[0].id : (res.targets.length ? null : '');
  const blocked = res.blocking.length > 0;
  const confirm = button('Conferma l’importazione', { kind: 'primary', ic: 'check', disabled: blocked || target === null, onClick: async () => {
    confirm.disabled = true;
    try {
      const done = await post('import/confirm', { key: res.key, target: target || null });
      if (done.already_imported) toast('Questo file era già stato importato: apro la struttura esistente.', '');
      else {
        const people = done.new_people !== done.people
          ? `${fmt.number(done.people)} persone nel file (${fmt.number(done.new_people)} nuove, ${fmt.number(done.people - done.new_people)} già presenti)`
          : `${fmt.number(done.people)} persone create`;
        toast(`Importazione completata: ${people}` + (done.skipped ? `; ${fmt.number(done.skipped)} celle da completare a mano.` : '.'), 'ok');
      }
      await ctx.reloadProfile();
      ctx.setContext(done.center_id, done.month);
      ctx.go('presenze');
    } catch (err) { toast(errorMessage(err), 'bad'); confirm.disabled = false; }
  } });
  const choice = h('div', { class: 'stack', role: 'radiogroup', 'aria-label': 'Dove importare' });
  const option = (value, label, text, disabled) => {
    const radio = h('input', { type: 'radio', name: 'target', value, checked: value === target, disabled });
    radio.addEventListener('change', () => { target = value; confirm.disabled = blocked; });
    return h('label', { class: `check ${disabled ? 'muted' : ''}`.trim() }, radio, h('span', null, h('strong', { text: label }), text ? h('span', { class: 'small muted', text: ' · ' + text }) : null));
  };
  for (const t of res.targets) {
    choice.append(option(t.id, `Aggiungi il mese alla struttura esistente «${t.name}» (${t.code})`,
      t.importable ? 'le persone con lo stesso nome vengono riutilizzate; i parametri della struttura non cambiano' : `non possibile: ${t.reason}`, !t.importable));
  }
  choice.append(option('', res.targets.length ? `Crea una nuova struttura «${res.center}»` : `Crea la struttura «${res.center}»`,
    'con i parametri letti dal file (festività, pazienti di riferimento, ruoli)' + (res.targets.length ? '; esiste già una struttura con questo nome: nel portale compariranno due voci uguali, distinte dal codice' : ''), false));

  const skippedRows = res.skipped.map(s => ({ ...s, when: `${fmt.date(s.day)} · ${SLOTS[s.slot] || s.slot}` }));
  const skippedSubtitle = res.skipped_total > res.skipped_shown
    ? `Prime ${fmt.number(res.skipped_shown)} di ${fmt.number(res.skipped_total)} celle: l’elenco completo resta nel registro delle attività dopo l’importazione.`
    : 'Valori che il portale non riconosce: dopo l’importazione vanno registrati a mano nel registro.';
  const alerts = [
    ...res.blocking.map(b => alertBox(b, 'bad')),
    ...res.warnings.map(w => alertBox(w, 'warn')),
    ...(res.warnings.length ? [] : [alertBox('Nessuna segnalazione sul file.', 'ok')]),
    ...res.notes.map(n => alertBox(n, 'info')),
  ];
  return h('div', { class: 'stack' },
    card(`Anteprima · ${res.center}`, { subtitle: `Mese ${fmt.month(res.month)} · impronta ${res.hash.slice(0, 12)}…` },
      h('div', { class: 'kpis' }, kpi('Persone', fmt.number(res.people), `${fmt.number(res.groups.dipendente)} dipendenti · ${fmt.number(res.groups.consulente)} collaboratori` + (res.groups[''] ? ` · ${fmt.number(res.groups[''])} senza sezione` : '')),
        kpi('Registrazioni', fmt.number(res.entries), `${fmt.number(res.holiday_entries)} in giorno festivo`),
        kpi('Fuori sede', fmt.number(res.external), 'sede da indicare a mano', res.external ? 'warn' : ''),
        kpi('Celle non importate', fmt.number(res.skipped_total), 'da completare nel registro', res.skipped_total ? 'warn' : 'ok'),
        kpi('Giorni con pazienti', fmt.number(res.workload_days), 'pazienti per fascia'),
        kpi('Proposte economiche', fmt.number(res.proposals), 'da confermare negli accordi')),
      h('div', { class: 'alerts' }, alerts)),
    res.skipped_total ? card('Celle non importate', { subtitle: skippedSubtitle },
      table([{ key: 'cell', label: 'Cella' }, { key: 'person', label: 'Persona' }, { key: 'when', label: 'Giorno e fascia' },
        { key: 'value', label: 'Valore', class: 'mono' }, { key: 'reason', label: 'Motivo' }], skippedRows)) : null,
    card('Persone riconosciute', { subtitle: 'Ruolo e contratto come scritti nel file; «righe» indica la posizione nel foglio «Da Compilare».' },
      table([{ key: 'name', label: 'Nome' }, { key: 'role', label: 'Ruolo', render: p => p.role || '—' }, { key: 'group', label: 'Sezione' },
        { key: 'contract', label: 'Contratto', render: p => p.billing ? `${p.contract} (${p.billing})` : (p.contract || '—') },
        { key: 'rows', label: 'Righe', render: p => p.rows.join(', ') }, { key: 'entries', label: 'Registrazioni', num: true },
        { key: 'proposal', label: 'Proposta', render: p => p.proposal ? 'sì' : '—' },
        { key: 'collaborator', label: 'Foglio Collaboratori', render: p => p.collaborator ? p.collaborator.replace('Foglio Collaboratori: ', '') : '—' }], res.persons)),
    card('Dove importare', { actions: confirm },
      choice,
      blocked ? alertBox('La conferma è bloccata finché i problemi segnalati in rosso non vengono risolti nel file.', 'bad') : null,
      h('p', { class: 'small muted', text: 'Dopo la conferma: assegna la struttura agli account, completa matricole e orari, registra a mano le celle non importate e sostituisci «Sede esterna da specificare» con la sede reale.' })));
}
