// Esportazioni: prospetti Excel nativi e file CSV, con le stesse regole di accesso del portale.
import { download, get } from '../api.js';
import { alertBox, button, card, errorMessage, field, fmt, h, input, select, shiftMonth, toast } from '../ui.js';

const KINDS = [
  { id: 'presenze_centro', title: 'Registro mensile della struttura', text: 'La griglia del mese come nel registro: una struttura, un mese, consuntivo o pianificato.', single: true },
  { id: 'presenze_totali', title: 'Presenze totali', text: 'Totali per struttura, mese, ruolo, persona e causale nel periodo scelto.' },
  { id: 'statistiche', title: 'Statistiche', text: 'Gli stessi indicatori della pagina Statistiche, in fogli separati.' },
  { id: 'dipendenti', title: 'Anagrafiche e fascicoli', text: 'Fascicoli completi delle persone: contiene dati personali.', private: true },
  { id: 'onboarding', title: 'Inserimento e scadenze', text: 'Attività di inserimento e scadenze aperte: contiene dati personali.', private: true },
  { id: 'accordi', title: 'Accordi individuali', text: 'Accordi e importi calcolati del periodo: contiene dati economici.', private: true },
];

// Scarico del registro della struttura (foglio mensile, registro Excel, CSV): per compilatore e direzione decide il
// parametro della struttura «Compilatore e consultazione possono scaricare il CSV», quindi si chiede al server lo stesso
// permesso che applicano le rotte invece di presumerlo.
async function exportAllowed(app) {
  if (!app.cid) return false;
  if (app.can('presenze.esporta')) return true;
  try {
    const snap = await get(`attendance/${app.cid}/${app.month}`);
    return Boolean(snap.caps?.['presenze.esporta']);
  } catch { return false; }
}

const DENIED_NOTE = 'Lo scarico del registro di questa struttura non è abilitato per il tuo profilo: lo decide il responsabile nei parametri '
  + 'della struttura con «Compilatore e consultazione possono scaricare il CSV». Registro e controlli restano consultabili nel portale.';

export async function render(ctx) {
  const { app } = ctx;
  const canExport = await exportAllowed(app);
  const from = input('from', shiftMonth(app.month, -2), { type: 'month' });
  const to = input('to', app.month, { type: 'month' });
  const center = select('cid', [['all', 'Tutte le strutture autorizzate'], ...app.me.centers.filter(c => c.active).map(c => [c.id, c.name])], app.cid || 'all');
  const layer = select('layer', [['actual', 'Consuntivo'], ['planned', 'Pianificato']], 'actual');
  const run = async kind => {
    const single = kind.single;
    const params = new URLSearchParams({ kind: kind.id, from: single ? app.month : from.value, to: single ? app.month : to.value,
      cid: single ? app.cid : center.value, layer: layer.value });
    try {
      await download(`exports/xlsx?${params}`, `${kind.id}.xlsx`);
      toast('File Excel scaricato. L’esportazione è registrata nello storico.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const csvMonth = async detail => {
    try {
      await download(`attendance/${app.cid}/${app.month}/export.csv${detail ? '?detail=1' : ''}`, 'presenze.csv');
      toast('File CSV scaricato.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const groupCsv = async () => {
    try { await download(`overview/${app.month}/export.csv`, 'riepilogo.csv'); toast('Riepilogo scaricato.', 'ok'); } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const groupXlsx = async () => {
    try { await download(`overview/${app.month}/export.xlsx`, 'riepilogo.xlsx'); toast('Riepilogo di gruppo scaricato in Excel.', 'ok'); } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const collaboratorsXlsx = async () => {
    try {
      await download(`collaborators/${app.cid}/${app.month}/export.xlsx`, 'collaboratori.xlsx');
      toast('Prospetto collaboratori scaricato. Contiene coordinate bancarie: conservarlo con cura.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  // Foglio mensile come il vecchio modello Excel: struttura e mese scelti in alto, nessuna formula né macro.
  const monthlyModel = async () => {
    try {
      await download(`exports/modello/${app.cid}/${app.month}`, `Presenze_${app.month}.xlsx`);
      toast('Foglio mensile scaricato. Lo scarico è registrato nello storico della struttura.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  };
  const allowedPrivate = app.can('esportazioni.riservate');
  const centerName = app.center()?.name || 'struttura scelta in alto';
  const modelCard = app.cid ? card('Foglio mensile come il modello Excel', { id: 'foglio-mensile', subtitle: `${centerName} · ${fmt.month(app.month)}` },
    h('p', { class: 'muted', text: 'Il vecchio modello mensile, generato dai dati del portale: griglia, contatori, spazio ufficio del personale, indicatori, pazienti, fogli per il consulente paghe e per i collaboratori. Nessuna formula né macro.' }),
    h('p', { class: 'muted', text: 'Contatori e indicatori sono gli stessi della pagina «Controlli e chiusura». Le parti economiche compaiono solo per chi può consultare gli accordi; indicatori e pazienti solo per chi consulta il carico; l’IBAN solo per chi gestisce le paghe.' }),
    canExport
      ? h('div', { class: 'form-actions' }, button('Scarica il foglio mensile', { kind: 'primary', ic: 'download', onClick: monthlyModel }))
      : alertBox(DENIED_NOTE, 'info')) : null;
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Esportazioni' }),
      h('h1', { text: 'Prospetti Excel e file CSV' }),
      h('p', { text: 'I file sono una copia del registro al momento dello scarico: le modifiche fatte nel file non tornano nel portale. Ogni scarico è registrato.' }))),
    modelCard,
    card('Periodo e strutture', { subtitle: 'Valgono per i prospetti su più mesi. Il registro mensile usa struttura e mese scelti in alto.' },
      h('div', { class: 'form-grid' }, field('Dal mese', from), field('Al mese', to), field('Strutture', center), field('Registro (solo griglia mensile)', layer))),
    h('div', { class: 'grid grid-3' }, KINDS.filter(k => (!k.private || allowedPrivate) && (!k.single || canExport)).map(k => card(k.title, {
      subtitle: k.single ? `${centerName} · mese scelto in alto` : null,
    }, h('p', { class: 'muted', text: k.text }), k.private ? alertBox('Richiede la conferma di sicurezza e va conservato con cura.', 'warn') : null,
    h('div', { class: 'form-actions' }, button('Scarica Excel', { kind: 'primary', ic: 'download', onClick: () => run(k) }))))),
    card('File CSV', { subtitle: 'Per fogli di calcolo e altri programmi. Il separatore segue i parametri della struttura.' },
      h('div', { class: 'row' },
        canExport ? button('Riepilogo del mese della struttura', { ic: 'download', onClick: () => csvMonth(false) }) : null,
        canExport ? button('Dettaglio di tutte le registrazioni del mese', { ic: 'download', onClick: () => csvMonth(true) }) : null,
        app.can('gruppo.riepilogo') ? button('Riepilogo di gruppo (tutte le strutture)', { ic: 'download', onClick: groupCsv }) : null)),
    app.can('gruppo.riepilogo') || (app.cid && app.can('paghe.gestisci')) ? card('Altri prospetti Excel', { subtitle: 'Gli stessi dati delle pagine del portale, in Excel nativo.' },
      h('div', { class: 'row' },
        app.can('gruppo.riepilogo') ? button('Riepilogo di gruppo del mese (Excel)', { ic: 'download', onClick: groupXlsx }) : null,
        app.cid && app.can('paghe.gestisci') ? button('Prospetto collaboratori e compensi (Excel, riservato)', { ic: 'download', onClick: collaboratorsXlsx }) : null),
      h('p', { class: 'small muted', text: 'Il tracciato per il consulente paghe (CSV o Excel) si scarica dalla pagina Paghe; il registro di una struttura anche dal pulsante «Esporta» del registro.' })) : null);
}
