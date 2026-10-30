// Guida completa: procedure passo per passo, guida delle pagine, domande frequenti. Ricerca nel testo.
import { downloadFile } from '../api.js';
import { HELP } from '../help.js';
import { PAGES } from '../app.js';
import { button, card, clear, dialog, empty, errorMessage, fmt, h, input, tabs, toast } from '../ui.js';

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
  { title: 'Dal vecchio foglio Excel al portale', steps: [
    'I codici si scelgono da un elenco: niente minuscole/maiuscole da ricordare, niente completamento automatico da spegnere.',
    'Il turno fuori sede non si colora di giallo: si indica la sede nella registrazione. Il festivo non si colora di rosso: si spunta «festivo» (le festività nazionali sono già nel calendario).',
    'I pazienti per fascia (ordinari e in isolamento) si registrano in «Controlli e chiusura»; rapporto ed efficienza si calcolano da soli.',
    'Lo spazio riservato all’ufficio del personale è la pagina «Accordi e calcoli»; il foglio «Collaboratori» è la pagina «Collaboratori e compensi».',
    'Il foglio per il consulente paghe si scarica da «Esportazioni» («Foglio mensile come il modello Excel»): nessuna formula o macro da far girare.'] },
  { title: 'Compensi dei collaboratori a prestazione', cap: 'accordi.vedi', steps: [
    'Nel fascicolo del collaboratore indica il tipo di rapporto (fattura, associazione, volontario…), chi fattura, ritenuta e cassa in percentuale, IBAN.',
    'A fine mese conferma il suo accordo in «Accordi e calcoli» con le tariffe reali (base «Tutti i turni» per chi è pagato a prestazione).',
    'Apri «Collaboratori e compensi»: lordo, ritenuta, cassa e netto sono calcolati; scarica il prospetto Excel per l’amministrazione.'] },
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

// ---------- Manuale illustrato e videoguide (cartella web/help, letta dai suoi indici) ----------
const MANUAL_DIR = 'help/manuale/';
const VIDEO_DIR = 'help/video/';
const MANUAL_PDF = 'Manuale_NefroCenter_WR.pdf';
const MANUAL_HTML = 'Manuale_NefroCenter_WR.html';

// Videoguide collegate alle pagine (numero del video → id delle pagine): il pannello «?» le propone nel contesto giusto.
export const VIDEO_PAGES = {
  '01': ['home', 'todo', 'security', 'guide', 'roles'],
  '02': ['attendance'],
  '03': ['month', 'settings'],
  '04': ['approvals'],
  '05': ['people', 'documents'],
  '06': ['coverage', 'workforce'],
  '07': ['mail', 'reminders'],
  '08': ['stats', 'exports'],
};

let materialsCache = null;

// Indici di manuale e videoguide; mancano nelle installazioni senza la cartella web/help (o senza una delle due parti).
export function materials() {
  if (!materialsCache) {
    materialsCache = (async () => {
      const read = async path => {
        try {
          const response = await fetch(path, { cache: 'no-cache' });
          return response.ok ? await response.json() : null;
        } catch { return null; }
      };
      const [manual, video] = await Promise.all([read(MANUAL_DIR + 'indice.json'), read(VIDEO_DIR + 'indice.json')]);
      return { manual, videos: video?.video || [] };
    })();
  }
  return materialsCache;
}

export function videosForPage(pageId, videos) {
  return videos.filter(v => (VIDEO_PAGES[String(v.file || '').slice(0, 2)] || []).includes(pageId));
}

function duration(seconds) {
  const s = Math.round(Number(seconds) || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// Lettore della videoguida dentro il portale: capitoli cliccabili, sottotitoli e trascrizione.
export async function playVideo(v) {
  const video = h('video', { controls: true, playsinline: 'true', preload: 'metadata', poster: VIDEO_DIR + v.copertina, 'aria-label': v.titolo },
    h('source', { src: VIDEO_DIR + v.file, type: 'video/mp4' }),
    // I sottotitoli sono già impressi nel video: la traccia resta disponibile dai comandi, ma non è attiva da sola.
    v.sottotitoli ? h('track', { kind: 'subtitles', src: VIDEO_DIR + v.sottotitoli, srclang: 'it', label: 'Italiano' }) : null,
    'Il browser non riproduce questo video: scarica il file dalla cartella help/video.');
  const seek = time => { video.currentTime = time; video.play().catch(() => {}); };
  const chapters = v.capitoli?.length
    ? h('div', { class: 'chapters', role: 'group', 'aria-label': 'Capitoli del video' },
      v.capitoli.map(c => h('button', { class: 'btn small', type: 'button', text: `${duration(c.tempo)} · ${c.titolo}`, on: { click: () => seek(c.tempo) } })))
    : null;
  let transcript = null;
  if (v.trascrizione) {
    const pre = h('pre', { text: 'Caricamento…' });
    transcript = h('details', { class: 'transcript' }, h('summary', { text: 'Trascrizione (testo dei sottotitoli)' }), pre);
    transcript.addEventListener('toggle', async () => {
      if (!transcript.open || transcript.dataset.loaded) return;
      transcript.dataset.loaded = '1';
      try {
        const response = await fetch(VIDEO_DIR + v.trascrizione, { cache: 'no-cache' });
        pre.textContent = response.ok ? await response.text() : 'Trascrizione non disponibile.';
      } catch { pre.textContent = 'Trascrizione non disponibile.'; }
    });
  }
  const body = h('div', { class: 'player stack' }, h('p', { class: 'muted', text: v.descrizione }), video, chapters, transcript,
    h('p', { class: 'small faint', text: `Durata ${duration(v.durata_secondi)} · senza audio, sottotitoli in italiano` }));
  await dialog(v.titolo, body, [{ label: 'Chiudi', value: null }], { wide: true });
  video.pause();
}

// Riquadro con copertina: premendolo si apre il lettore. Usato nella scheda «Manuale e video» e nel pannello «?».
export function videoButton(v, compact = false) {
  const label = `Guarda la videoguida «${v.titolo}» (${duration(v.durata_secondi)})`;
  const thumb = h('span', { class: 'thumb' }, h('img', { src: VIDEO_DIR + v.copertina, alt: '', loading: 'lazy', width: '320', height: '180' }),
    h('span', { class: 'play', 'aria-hidden': 'true', text: '▶' }));
  if (compact) {
    return h('button', { class: 'video-cta', type: 'button', 'aria-label': label, on: { click: () => playVideo(v) } }, thumb,
      h('span', null, h('span', { class: 'video-title', text: v.titolo }), h('span', { class: 'small muted', text: duration(v.durata_secondi) })));
  }
  return h('button', { class: 'video-tile', type: 'button', 'aria-label': label, on: { click: () => playVideo(v) } }, thumb,
    h('span', { class: 'video-title', text: v.titolo }),
    h('span', { class: 'small muted', text: `${duration(v.durata_secondi)} · ${(v.profili || []).join(', ') || 'tutti i profili'}` }));
}

function pdfButton(kind = '') {
  return button('Scarica il PDF', { kind, ic: 'download', onClick: async e => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try { await downloadFile(MANUAL_DIR + MANUAL_PDF, MANUAL_PDF); } catch (err) { toast(errorMessage(err), 'bad'); } finally { btn.disabled = false; }
  } });
}

function materialsBlocks(found) {
  const blocks = [];
  if (found.manual) {
    const m = found.manual;
    blocks.push(card('Manuale d’uso illustrato', { subtitle: [m.versione ? `Versione ${m.versione}` : '', m.pagine ? `${m.pagine} pagine` : '', m.data ? `aggiornato il ${fmt.date(m.data)}` : ''].filter(Boolean).join(' · ') },
      h('p', { text: 'Tutte le pagine del portale con schermate (dati fittizi), procedure passo per passo, ruoli e permessi, domande frequenti. Si legge qui nel portale, capitolo per capitolo; il PDF serve per stamparlo o conservarlo.' }),
      h('div', { class: 'row' },
        h('a', { class: 'btn primary', href: '#/guida/manuale', text: 'Leggi nel portale' }),
        pdfButton(),
        h('a', { class: 'btn ghost', href: MANUAL_DIR + MANUAL_HTML, target: '_blank', rel: 'noopener', text: 'Apri in una nuova scheda' })),
      m.capitoli?.length ? h('ol', { class: 'toc-list' }, m.capitoli.map(c => h('li', null,
        h('a', { href: `#/guida/manuale?a=cap-${c.id}`, text: c.titolo })))) : null));
  }
  if (found.videos.length) {
    blocks.push(card('Videoguide', { subtitle: `${found.videos.length} video brevi senza audio, con sottotitoli in italiano. Premi un riquadro: il video si apre qui, con i capitoli e la trascrizione.` },
      h('div', { class: 'video-grid' }, found.videos.map(v => videoButton(v)))));
  }
  if (!blocks.length) {
    blocks.push(empty('Manuale e videoguide non presenti in questa installazione',
      'Si trovano nella cartella web/help del portale: se manca, il tecnico può copiarla dal pacchetto di installazione.'));
  }
  return blocks;
}

// Il manuale dentro il portale: il suo HTML viene letto e mostrato in un contenitore isolato (shadow DOM), così i suoi
// stili non toccano il portale e i collegamenti interni scorrono alla sezione invece di cambiare pagina.
async function manualReader(ctx) {
  const found = await materials();
  const head = (actions, text) => h('div', { class: 'page-head' }, h('div', null,
    h('a', { class: 'eyebrow', href: '#/guida?tab=materiali', text: '‹ Guida e procedure' }), h('h1', { text: 'Manuale d’uso' }),
    text ? h('p', { text }) : null), h('div', { class: 'page-actions' }, actions));
  if (!found.manual) {
    return h('div', { class: 'stack' }, head([]), empty('Manuale non presente in questa installazione',
      'Il manuale si trova nella cartella web/help/manuale del portale: se manca, il tecnico può copiarla dal pacchetto di installazione.'));
  }
  const m = found.manual;
  const host = h('div', { class: 'manual-inline' });
  const shadow = host.attachShadow({ mode: 'open' });
  const sheet = h('link', { rel: 'stylesheet', href: MANUAL_DIR + (m.file?.css?.nome || 'manuale.css') });
  shadow.append(sheet, h('p', { text: 'Caricamento del manuale…' }));
  const jump = id => {
    const target = id && shadow.getElementById(id);
    if (target) target.scrollIntoView({ block: 'start', behavior: 'smooth' });
    else host.scrollIntoView({ block: 'start' });
  };
  const chapterSelect = h('select', { 'aria-label': 'Vai al capitolo', on: { change: e => { jump(e.target.value); e.target.value = ''; } } },
    h('option', { value: '', text: 'Vai al capitolo…' }), (m.capitoli || []).map(c => h('option', { value: `cap-${c.id}`, text: `${c.numero}. ${c.titolo}` })));
  shadow.addEventListener('click', e => {
    const link = e.composedPath().find(n => n.tagName === 'A');
    if (!link) return;
    const href = link.getAttribute('href') || '';
    if (href.startsWith('#')) { e.preventDefault(); jump(href.slice(1)); } else if (/^https?:/.test(href)) { link.target = '_blank'; link.rel = 'noopener'; }
  });
  (async () => {
    try {
      const [page, css] = await Promise.all([fetch(MANUAL_DIR + (m.file?.html?.nome || MANUAL_HTML), { cache: 'no-cache' }), fetch(sheet.href, { cache: 'no-cache' })]);
      if (!page.ok) throw new Error('manuale non disponibile');
      // Le variabili definite su :root nel foglio del manuale valgono solo per il documento: si riportano sul contenitore.
      const vars = /:root\s*{([^}]*)}/.exec(css.ok ? await css.text() : '');
      for (const decl of (vars ? vars[1] : '').split(';')) {
        const [name, value] = decl.split(':').map(s => s.trim());
        if (name?.startsWith('--') && value) host.style.setProperty(name, value);
      }
      // Gli stili incorporati nell'HTML sono gli stessi di manuale.css e la CSP li bloccherebbe: si tolgono prima
      // dell'analisi, così non compare nemmeno l'avviso in console.
      const text = (await page.text()).replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/gi, '');
      const doc = new DOMParser().parseFromString(text, 'text/html');
      shadow.replaceChildren(sheet, ...Array.from(doc.body.children));
      if (ctx.query.a) requestAnimationFrame(() => jump(ctx.query.a));
    } catch {
      shadow.replaceChildren(sheet, h('p', { text: 'Il manuale non si è caricato. Prova a scaricare il PDF oppure ad aprirlo in una nuova scheda.' }));
    }
  })();
  return h('div', { class: 'stack reader' },
    head([chapterSelect, pdfButton('primary'), h('a', { class: 'btn ghost', href: MANUAL_DIR + (m.file?.html?.nome || MANUAL_HTML), target: '_blank', rel: 'noopener', text: 'Nuova scheda' })],
      `${m.pagine || ''} pagine con schermate su dati fittizi, aggiornato il ${fmt.date(m.data)}. I collegamenti dell’indice scorrono alla sezione.`),
    host);
}

export async function render(ctx) {
  const { app } = ctx;
  if (ctx.params[0] === 'manuale') return manualReader(ctx);
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
