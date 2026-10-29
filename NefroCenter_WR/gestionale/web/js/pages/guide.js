// Guida completa: procedure passo per passo, guida delle pagine, domande frequenti. Ricerca nel testo.
import { HELP } from '../help.js';
import { PAGES } from '../app.js';
import { card, clear, empty, fmt, h, input, tabs } from '../ui.js';

// Procedure: cap indica il permesso che serve per eseguirle (assente = per tutti).
export const PROCEDURES = [
  { title: 'Primo accesso', steps: [
    'Ricevi dall’amministratore il nome utente e un codice di attivazione (vale 7 giorni).',
    'Nella pagina di accesso scegli «Primo accesso» e inserisci nome utente e codice.',
    'Scegli una password di almeno 12 caratteri.',
    'Inquadra il codice QR con un’app Authenticator sul telefono e inserisci il codice di 6 cifre.',
    'Scarica o stampa i codici di recupero e conservali lontano dal telefono.'] },
  { title: 'Registrare le presenze del giorno', cap: 'presenze.compila', steps: [
    'Apri «Registro presenze»: struttura e mese si scelgono in alto.',
    'Clicca la casella della persona, del giorno e della fascia.',
    'Scegli la causale (turno o assenza); controlla gli orari proposti dalla fascia e salva.',
    'Sul telefono usa la vista «Giorno»: un pulsante per ogni fascia di ogni persona.'] },
  { title: 'Preparare i turni del mese', cap: 'presenze.pianifica', steps: [
    'Nel registro passa a «Pianificato».',
    'Inserisci i turni previsti: restano tratteggiati finché non si registra il consuntivo.',
    'Ogni giorno, in «Consuntivo», conferma o correggi quanto è stato svolto davvero.',
    'Le fasce pianificate rimaste senza consuntivo nei giorni passati compaiono in «Da completare».'] },
  { title: 'Chiudere il mese', cap: 'mese.verifica', steps: [
    'Apri «Controlli e chiusura» e risolvi i controlli elencati.',
    'Premi «Conferma calendario e parametri».',
    'Se la struttura non usa l’approvazione, premi «Chiudi il mese».',
    'Se l’approvazione è attiva, invia il mese dalla pagina «Approvazioni»: dopo l’invio non si modifica più.',
    'Per correggere un mese chiuso serve la riapertura con motivazione, che resta nello storico.'] },
  { title: 'Approvare un mese', cap: 'approvazioni.vedi', steps: [
    'Apri «Approvazioni»: le strutture che aspettano te sono segnate «Tocca a te».',
    'Leggi i controlli del mese e lo storico dei passaggi.',
    'Approva per inoltrare il mese, oppure restituiscilo con una motivazione perché venga corretto.',
    'Se i dati cambiano dopo l’invio, il portale lo segnala: il mese va restituito e inviato di nuovo.'] },
  { title: 'Inserire una nuova persona', cap: 'hr.fascicoli', steps: [
    'In «Persone e fascicoli» premi «Nuova persona» e compila nome, ruolo e data di ingresso.',
    'Completa il fascicolo per schede: anagrafica, recapiti, contratto, qualifiche.',
    'Nella scheda «Inserimento» segui le attività previste dal modello della struttura.',
    'Carica i documenti nella scheda «Documenti»: HR centrale li verifica.'] },
  { title: 'Verificare un documento', cap: 'documenti.verifica', steps: [
    'Apri «Documenti» e filtra quelli «Ricevuti».',
    'Apri l’anteprima, controlla contenuto e scadenza.',
    'Approva oppure chiedi una correzione spiegando cosa manca: la struttura potrà ripresentarlo.'] },
  { title: 'Gestire un’uscita o un trasferimento', cap: 'uscite.gestisci', steps: [
    'In «Uscite e dotazioni» apri un nuovo percorso per la persona (cessazione o trasferimento).',
    'Completa le attività: comunicazioni, ultimo giorno, restituzione delle dotazioni.',
    'Registra la restituzione di badge, chiavi, divise o dispositivi.',
    'Chiudi il percorso quando tutte le attività sono completate o non applicabili.'] },
  { title: 'Proporre una sostituzione fra strutture', cap: 'copertura.proponi', steps: [
    'In «Copertura turni» guarda i giorni e le fasce sotto il fabbisogno minimo.',
    'Scegli una persona disponibile di un’altra struttura e proponi la sostituzione.',
    'Il responsabile della struttura che riceve la persona accetta o rifiuta.',
    'Una sostituzione accettata diventa un turno pianificato nella struttura di destinazione.'] },
  { title: 'Preparare i dati per le paghe', cap: 'paghe.gestisci', steps: [
    'In «Paghe» controlla l’anteprima del mese: persone, voci e importi calcolati.',
    'Il tracciato definitivo per il consulente va configurato insieme a lui: finché non c’è, si scarica solo il prospetto di controllo.',
    'Lo scaricamento del tracciato chiede la conferma di sicurezza.'] },
  { title: 'Inviare una comunicazione', cap: 'comunicazioni.usa', steps: [
    'In «Comunicazioni» prepara un modello e una lista di destinatari.',
    'Crea una bozza e controlla l’anteprima di ogni messaggio.',
    'L’invio reale è possibile solo dopo che l’amministratore ha configurato il servizio di posta aziendale.'] },
  { title: 'Importare il modello Excel di un mese', cap: 'import.excel', steps: [
    'In «Importa Excel» scegli il file mensile e premi «Analizza il file»: il portale legge il foglio «Da Compilare» senza eseguire macro.',
    'Controlla l’anteprima: persone, registrazioni, pazienti per fascia, avvisi e celle non riconosciute.',
    'Scegli la destinazione: una struttura esistente con lo stesso nome (se il mese è vuoto) oppure una nuova struttura.',
    'Dopo la conferma completa nel registro le celle non importate, gli orari e le sedi esterne; conferma gli accordi proposti.'] },
  { title: 'Backup e ripristino', cap: 'backup.gestisci', steps: [
    'Il backup giornaliero si crea da solo; puoi crearne uno in più dalla pagina «Backup».',
    'Ogni backup è verificato: in caso di problemi compare un avviso in «Da completare».',
    'La seconda copia su NAS si attiva solo dopo aver indicato e provato una destinazione reale.',
    'Il ripristino si fa sul server con la procedura descritta nel manuale tecnico.'] },
  { title: 'Se perdi o cambi il telefono', steps: [
    'Per entrare usa uno dei codici di recupero al posto del codice dell’app.',
    'Da «Il mio account» configura il nuovo telefono: il vecchio smette di funzionare.',
    'Se non hai più codici, chiedi all’amministratore un nuovo codice di attivazione.'] },
];

export const FAQ = [
  ['Perché non vedo alcune pagine?', 'Il menu mostra solo le funzioni consentite al tuo profilo. La pagina «Ruoli e permessi» spiega cosa può fare ciascuno.'],
  ['Ho salvato un turno ma compare un avviso sul riposo.', 'Il turno è salvato: l’avviso ricorda che fra due turni c’è meno riposo del minimo indicato nei parametri della struttura.'],
  ['Non riesco a modificare un giorno.', 'Il mese potrebbe essere chiuso o inviato in approvazione. In «Controlli e chiusura» trovi lo stato; per correggere serve una riapertura motivata.'],
  ['Cosa significa «Da consuntivare»?', 'Sono turni pianificati in giorni già passati per cui non è ancora registrato il turno effettivo.'],
  ['Il portale chiede di nuovo password e codice.', 'Succede per le operazioni sensibili (accessi, backup, paghe): la conferma vale 5 minuti.'],
  ['Le email partono davvero?', 'Solo dopo la configurazione del servizio di posta aziendale da parte dell’amministratore. Prima si possono preparare bozze e anteprime.'],
];

// Manuale illustrato e videoguide generati in web/help (assenti nella demo pubblica): si leggono dai loro indici.
async function materials() {
  const read = async path => {
    try {
      const response = await fetch(path, { cache: 'no-cache' });
      return response.ok ? await response.json() : null;
    } catch { return null; }
  };
  const [manual, video] = await Promise.all([read('help/manuale/indice.json'), read('help/video/indice.json')]);
  return { manual, videos: video?.video || [] };
}

function materialsBlocks(found) {
  const blocks = [];
  if (found.manual) {
    const m = found.manual;
    blocks.push(card('Manuale d’uso illustrato', { subtitle: [m.versione ? `Versione ${m.versione}` : '', m.pagine ? `${m.pagine} pagine` : '', m.data ? `aggiornato il ${fmt.date(m.data)}` : ''].filter(Boolean).join(' · ') },
      h('p', { text: 'Tutte le pagine del portale con schermate (dati fittizi), procedure passo per passo, ruoli e permessi, domande frequenti.' }),
      h('div', { class: 'row' },
        h('a', { class: 'btn primary', href: 'help/manuale/Manuale_NefroCenter_WR.pdf', target: '_blank', rel: 'noopener', text: 'Apri il PDF' }),
        h('a', { class: 'btn', href: 'help/manuale/Manuale_NefroCenter_WR.html', target: '_blank', rel: 'noopener', text: 'Versione per il browser' }))));
  }
  if (found.videos.length) {
    blocks.push(card('Videoguide', { subtitle: 'Senza audio, con sottotitoli in italiano. Ogni video dura uno o due minuti.' },
      h('div', { class: 'video-list' }, found.videos.map(v => {
        const player = h('video', { controls: true, preload: 'none', poster: 'help/video/' + v.copertina, width: 640, height: 360 },
          h('source', { src: 'help/video/' + v.file, type: 'video/mp4' }),
          v.sottotitoli ? h('track', { kind: 'subtitles', src: 'help/video/' + v.sottotitoli, srclang: 'it', label: 'Italiano', default: true }) : null);
        return h('div', { class: 'video-item' }, h('h3', { text: v.titolo }), h('p', { class: 'small muted', text: v.descrizione }), player,
          h('p', { class: 'small' }, v.durata_secondi ? `${Math.round(v.durata_secondi)} secondi · ` : '',
            v.trascrizione ? h('a', { href: 'help/video/' + v.trascrizione, target: '_blank', rel: 'noopener', text: 'trascrizione' }) : null));
      }))));
  }
  if (!blocks.length) {
    blocks.push(empty('Manuale e videoguide non disponibili', 'Nella demo pubblica non sono inclusi; nel portale aziendale si trovano nella cartella web/help.'));
  }
  return blocks;
}

export async function render(ctx) {
  const { app } = ctx;
  let tab = ctx.query.tab || 'procedure';
  let term = '';
  let found = null;
  const body = h('div');
  const search = input('q', '', { placeholder: 'Cerca nella guida' });
  search.setAttribute('aria-label', 'Cerca nella guida');
  search.addEventListener('input', () => { term = search.value.trim().toLowerCase(); draw(); });
  const matches = (...texts) => !term || texts.flat().join(' ').toLowerCase().includes(term);
  const bar = h('div');
  const draw = () => {
    clear(bar, tabs([{ id: 'procedure', label: 'Procedure' }, { id: 'pagine', label: 'Pagine del portale' }, { id: 'faq', label: 'Domande frequenti' },
      { id: 'materiali', label: 'Manuale e video' }], tab, id => { tab = id; draw(); }));
    let blocks = [];
    if (tab === 'materiali') {
      if (!found) {
        clear(body, h('p', { class: 'muted', text: 'Caricamento…' }));
        materials().then(result => { found = result; if (tab === 'materiali') draw(); });
        return;
      }
      blocks = materialsBlocks(found);
    } else if (tab === 'procedure') {
      blocks = PROCEDURES.filter(p => (!p.cap || app.can(p.cap)) && matches(p.title, p.steps))
        .map(p => card(p.title, {}, h('ol', { class: 'steps-list' }, p.steps.map(s => h('li', { text: s })))));
    } else if (tab === 'pagine') {
      blocks = PAGES.filter(p => (!p.cap || app.can(p.cap)) && HELP[p.id]).filter(p => {
        const help = HELP[p.id];
        return matches(p.label, help.intro, help.steps || [], help.notes || [], Object.values(help.roles || {}));
      }).map(p => {
        const help = HELP[p.id];
        const mine = help.roles?.[app.me.user.role];
        return card(p.label, { actions: p.group ? h('a', { class: 'btn small', href: '#/' + p.path, text: 'Apri' }) : null },
          h('p', { text: help.intro }),
          help.steps?.length ? h('ol', { class: 'steps-list' }, help.steps.map(s => h('li', { text: s }))) : null,
          mine ? h('p', { class: 'small' }, h('strong', { text: 'Per il tuo profilo: ' }), mine) : null,
          help.notes?.length ? h('ul', { class: 'small muted' }, help.notes.map(s => h('li', { text: s }))) : null);
      });
    } else {
      blocks = FAQ.filter(([q, a]) => matches(q, a)).map(([q, a]) => card(q, {}, h('p', { text: a })));
    }
    clear(body, blocks.length ? h('div', { class: 'stack' }, blocks) : empty('Nessun risultato', 'Prova con un’altra parola.'));
  };
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Guida' }),
      h('h1', { text: 'Guida e procedure' }),
      h('p', { text: 'Le procedure mostrate dipendono dal tuo profilo. In ogni pagina il pulsante «?» in alto apre la guida di quella pagina.' })),
    h('div', { class: 'page-actions guide-search' }, search)),
    bar, body);
}
