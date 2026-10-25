// Guida completa: procedure passo per passo, guida delle pagine, domande frequenti. Ricerca nel testo.
import { HELP } from '../help.js';
import { PAGES } from '../app.js';
import { card, clear, empty, h, input, tabs } from '../ui.js';

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

const FAQ = [
  ['Perché non vedo alcune pagine?', 'Il menu mostra solo le funzioni consentite al tuo profilo. La pagina «Ruoli e permessi» spiega cosa può fare ciascuno.'],
  ['Ho salvato un turno ma compare un avviso sul riposo.', 'Il turno è salvato: l’avviso ricorda che fra due turni c’è meno riposo del minimo indicato nei parametri della struttura.'],
  ['Non riesco a modificare un giorno.', 'Il mese potrebbe essere chiuso o inviato in approvazione. In «Controlli e chiusura» trovi lo stato; per correggere serve una riapertura motivata.'],
  ['Cosa significa «Da consuntivare»?', 'Sono turni pianificati in giorni già passati per cui non è ancora registrato il turno effettivo.'],
  ['Il portale chiede di nuovo password e codice.', 'Succede per le operazioni sensibili (accessi, backup, paghe): la conferma vale 5 minuti.'],
  ['Le email partono davvero?', 'Solo dopo la configurazione del servizio di posta aziendale da parte dell’amministratore. Prima si possono preparare bozze e anteprime.'],
];

export async function render(ctx) {
  const { app } = ctx;
  let tab = ctx.query.tab || 'procedure';
  let term = '';
  const body = h('div');
  const search = input('q', '', { placeholder: 'Cerca nella guida' });
  search.setAttribute('aria-label', 'Cerca nella guida');
  search.addEventListener('input', () => { term = search.value.trim().toLowerCase(); draw(); });
  const matches = (...texts) => !term || texts.flat().join(' ').toLowerCase().includes(term);
  const bar = h('div');
  const draw = () => {
    clear(bar, tabs([{ id: 'procedure', label: 'Procedure' }, { id: 'pagine', label: 'Pagine del portale' }, { id: 'faq', label: 'Domande frequenti' }],
      tab, id => { tab = id; draw(); }));
    let blocks = [];
    if (tab === 'procedure') {
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
