// Videoguide di NefroCenter WR · Work Resources: 8 registrazioni senza audio con sottotitoli in italiano impressi nel video.
//
// USO (da qualunque cartella; Playwright è cercato tramite NODE_PATH):
//   export NODE_PATH=$(node -e "console.log(require.resolve('playwright').split('/playwright/')[0])")
//   QA_CHROMIUM_NO_SANDBOX=1 LANG=it_IT.UTF-8 node strumenti/guide/video.cjs [--solo 01,05] [--porta 8102]
//   --solo   registra soltanto le guide indicate (numeri a due cifre); l'indice viene ricostruito con i metadati
//            delle altre guide salvati in strumenti/guide/lavoro/video/*.meta.json
//   --porta  porta del portale di prova (predefinita 8102)
//
// REQUISITI: Node 20+, Playwright 1.63 con Chromium già installato (NON eseguire "playwright install"),
//   ffmpeg 6 con libass (filtro subtitles), libx264 e ffprobe; font Inter in /usr/share/fonts/opentype/inter;
//   Python 3 per il portale di prova (gestionale/strumenti/anteprima.py, avviato da comune.cjs con --aziendale).
//
// COSA PRODUCE in gestionale/web/help/video/ (serviti dal portale come /help/video/...):
//   NN-slug.mp4  H.264 1280×720 30 fps yuv420p, +faststart, senza traccia audio, sottotitoli impressi
//   NN-slug.vtt  gli stessi sottotitoli in WebVTT      NN-slug.txt  trascrizione (un paragrafo per passo)
//   NN-slug.jpg  copertina da un fotogramma significativo   indice.json  elenco con titoli, durate, profili e capitoli
//
// COME FUNZIONA: comune.startServer crea un portale di prova NUOVO con soli dati fittizi (3 strutture «… · Demo»,
//   12 persone inventate, oggi = 25/10/2026) in modalità aziendale; gli account di prova vengono attivati una volta
//   (il Compilatore durante la guida 01, che mostra proprio il primo accesso). Ogni guida gira in un browser context
//   con registrazione video; un evidenziatore (anello + puntatore finto) viene iniettato nella pagina senza toccare i
//   file del portale. Ogni passo = sottotitolo + azione + tempo di lettura (≥ 2,5 s, ~70 ms per carattere).
//   Il webm di Playwright viene convertito con ffmpeg imprimendo i sottotitoli (libass, Inter). Alla fine il portale
//   viene spento, l'archivio di prova e i file temporanei (webm, srt) cancellati; lo script stampa un riepilogo JSON
//   con i controlli: ffprobe di ogni mp4, sottotitoli non sovrapposti e dentro la durata, indice coerente con i file.
// I file temporanei stanno in strumenti/guide/lavoro/video/ (cartella ignorata da git). Nessun dato aziendale.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const comune = require('./comune.cjs');

const OPTS = comune.args({ solo: '', porta: '8102' });
const PORT = Number(OPTS.porta);
const OUT = path.join(comune.WEB, 'help', 'video');
const TMP = path.join(comune.WORK, 'video');
const FONTS = '/usr/share/fonts/opentype/inter';
const WIDTH = 1280;
const HEIGHT = 720;
const FPS = 30;
const MAX_LINE = 44;          // caratteri per riga di sottotitolo (massimo 2 righe per cue)
const MIN_HOLD = 2500;        // tempo minimo di lettura di un passo (ms)
const MS_PER_CHAR = 70;       // tempo di lettura per carattere (ms)
const GAP = 0.08;             // distanza minima fra due cue (s)
// Stile libass (PlayResY 288 → FontSize 17 ≈ 42 px su 720 righe): bianco su riquadro scuro semitrasparente, un riquadro
// per riga (BorderStyle=4, riempito con BackColour; Outline dà il margine interno e il suo colore è trasparente).
const STYLE = 'FontName=Inter,FontSize=17,PrimaryColour=&H00FFFFFF,OutlineColour=&HFF000000,BackColour=&H66000000,'
  + 'BorderStyle=4,Outline=6,Shadow=0,MarginV=26,MarginL=40,MarginR=40,Alignment=2,Bold=0';
const ROLE_LABEL = { operator: 'Compilatore', manager: 'Responsabile di struttura', hr: 'HR centrale', viewer: 'Direzione · consultazione' };
const { sleep } = comune;

// ---------- Testi: righe, cue e formati ----------
function wrapLines(text, max = MAX_LINE) {
  const lines = [];
  let line = '';
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (!line) line = word;
    else if ((line + ' ' + word).length <= max) line += ' ' + word;
    else { lines.push(line); line = word; }
  }
  if (line) lines.push(line);
  if (lines.length !== 2) return lines;
  // Due righe: taglio più vicino alla metà (evita una seconda riga di una sola parola).
  const words = text.split(/\s+/).filter(Boolean);
  let best = null;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    if (a.length > max || b.length > max) continue;
    const diff = Math.abs(a.length - b.length);
    if (!best || diff < best.diff) best = { lines: [a, b], diff };
  }
  return best ? best.lines : lines;
}

// Spezza il testo di un passo in gruppi di massimo 2 righe: prima ai confini di frase, poi a «:» «;» e virgole;
// fra le suddivisioni valide sceglie quella con meno gruppi e di lunghezza più equilibrata.
function chunks(text) {
  const fits = t => wrapLines(t).length <= 2;
  if (fits(text)) return [wrapLines(text)];
  let parts = [text];
  for (const sep of [/[^.!?]+[.!?]*[»)]*\s*/g, /[^:;]+[:;]?\s*/g, /[^,]+,?\s*/g]) {
    parts = parts.flatMap(p => (fits(p) ? [p] : (p.match(sep) || [p]).map(s => s.trim()).filter(Boolean)));
  }
  // Un pezzo ancora troppo lungo (senza punteggiatura) viene diviso a coppie di righe.
  parts = parts.flatMap(p => (fits(p) ? [p] : wrapLines(p).reduce((acc, line, i) => {
    if (i % 2 === 0) acc.push(line); else acc[acc.length - 1] += ' ' + line;
    return acc;
  }, [])));
  const n = Math.min(parts.length, 14);
  let best = null;
  for (let mask = 0; mask < (1 << (n - 1)); mask++) {
    const groups = [];
    let current = parts[0];
    for (let i = 1; i < n; i++) {
      if (mask & (1 << (i - 1))) { groups.push(current); current = parts[i]; } else current += ' ' + parts[i];
    }
    groups.push(current);
    if (!groups.every(fits)) continue;
    const sizes = groups.map(g => g.length);
    const score = [groups.length, Math.max(...sizes) - Math.min(...sizes)];
    if (!best || score[0] < best.score[0] || (score[0] === best.score[0] && score[1] < best.score[1])) best = { groups, score };
  }
  return (best ? best.groups : parts).map(g => wrapLines(g));
}

// Dai passi (inizio, fine, testo) ai cue: tempo ripartito in proporzione ai caratteri, mai sovrapposti.
function buildCues(steps, duration) {
  const cues = [];
  steps.forEach((step, i) => {
    const groups = chunks(step.text);
    const total = groups.reduce((n, g) => n + g.join(' ').length, 0);
    const limit = Math.min(i + 1 < steps.length ? steps[i + 1].start : step.end + 1.5, duration - 0.1);
    const span = Math.max(1, limit - step.start);
    let offset = 0;
    groups.forEach((lines, k) => {
      const share = lines.join(' ').length / total;
      const start = step.start + offset * span;
      offset += share;
      const end = Math.max(start + 0.8, (k === groups.length - 1 ? limit : step.start + offset * span) - GAP);
      cues.push({ start: round3(start), end: round3(Math.min(end, duration - 0.05)), lines, top: step.top });
    });
  });
  return cues.filter(c => c.end > c.start);
}

const round3 = n => Math.round(n * 1000) / 1000;
function stamp(seconds, sep) {
  const ms = Math.round(seconds * 1000);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}${sep}${String(ms % 1000).padStart(3, '0')}`;
}
const toSrt = cues => cues.map((c, i) => `${i + 1}\n${stamp(c.start, ',')} --> ${stamp(c.end, ',')}\n${c.top ? '{\\an8}' : ''}${c.lines.join('\n')}\n`).join('\n');
const toVtt = cues => 'WEBVTT\n\n' + cues.map((c, i) => `${i + 1}\n${stamp(c.start, '.')} --> ${stamp(c.end, '.')}${c.top ? ' line:8%' : ''}\n${c.lines.join('\n')}\n`).join('\n');
const escapeFilter = s => s.replace(/([\\:,'\[\]])/g, '\\$1');

// ---------- Evidenziatore iniettato nella pagina (anello, puntatore finto, impulso al clic) ----------
// Vive in un popover "manual", così resta sopra anche alle finestre di dialogo modali. Non modifica i file del portale.
function overlayScript() {
  const install = () => {
    if (document.getElementById('wr-guide-overlay')) return;
    const style = document.createElement('style');
    style.textContent = `
#wr-guide-overlay{position:fixed;inset:0;width:100vw;height:100vh;margin:0;padding:0;border:0;background:transparent;pointer-events:none;overflow:visible}
#wr-guide-overlay::backdrop{background:transparent}
#wr-guide-ring{position:absolute;left:0;top:0;width:0;height:0;border:3px solid #ff5a5f;border-radius:10px;box-shadow:0 0 0 4px rgba(255,90,95,.28),0 0 0 2000px rgba(16,27,61,0);opacity:0;transition:left .35s ease,top .35s ease,width .35s ease,height .35s ease,opacity .25s ease}
#wr-guide-ring.on{opacity:1}
#wr-guide-pulse{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:rgba(255,90,95,.65);opacity:0}
#wr-guide-pulse.on{animation:wr-guide-pulse .55s ease-out}
@keyframes wr-guide-pulse{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(4.5)}}
#wr-guide-pointer{position:absolute;left:0;top:0;width:26px;height:30px;transform:translate(640px,760px);transition:transform .55s cubic-bezier(.4,0,.2,1);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
.toasts{bottom:150px !important}`;
    document.head.append(style);
    const box = document.createElement('div');
    box.id = 'wr-guide-overlay';
    box.setAttribute('popover', 'manual');
    box.innerHTML = '<div id="wr-guide-ring"></div><div id="wr-guide-pulse"></div>'
      + '<svg id="wr-guide-pointer" viewBox="0 0 26 30" aria-hidden="true"><path d="M3 2 L3 24 L9 18.5 L13.5 28 L17.5 26.2 L13 17 L21 17 Z" fill="#fff" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>';
    document.body.append(box);
    const top = () => { try { box.hidePopover(); } catch { /* non ancora aperto */ } try { box.showPopover(); } catch { /* già aperto */ } };
    top();
    const ring = box.querySelector('#wr-guide-ring');
    const pointer = box.querySelector('#wr-guide-pointer');
    const pulse = box.querySelector('#wr-guide-pulse');
    window.__wrGuide = {
      aim(b) {
        top();
        Object.assign(ring.style, { left: `${b.x - 6}px`, top: `${b.y - 6}px`, width: `${b.width + 12}px`, height: `${b.height + 12}px` });
        ring.classList.add('on');
        pointer.style.transform = `translate(${b.x + b.width / 2 - 3}px, ${b.y + b.height / 2 - 2}px)`;
      },
      clear() { ring.classList.remove('on'); },
      pulse(b) {
        pulse.style.left = `${b.x + b.width / 2}px`;
        pulse.style.top = `${b.y + b.height / 2}px`;
        pulse.classList.remove('on');
        void pulse.offsetWidth;
        pulse.classList.add('on');
      },
    };
  };
  if (document.body) install(); else document.addEventListener('DOMContentLoaded', install);
}

// ---------- Registratore di una guida ----------
class Recorder {
  constructor(browser, base, guide) {
    Object.assign(this, { browser, base, guide, steps: [], chapters: [], problems: [] });
  }

  async open(storageState) {
    this.context = await this.browser.newContext({
      viewport: { width: WIDTH, height: HEIGHT }, recordVideo: { dir: TMP, size: { width: WIDTH, height: HEIGHT } },
      locale: 'it-IT', colorScheme: 'light', bypassCSP: true, storageState: storageState || undefined,
    });
    await this.context.addInitScript(overlayScript);
    this.page = await this.context.newPage();
    this.t0 = Date.now();   // riferimento della linea temporale del video
    comune.problems(this.page, this.problems);
    return this.page;
  }

  now() { return (Date.now() - this.t0) / 1000; }

  // Un passo della guida: sottotitolo, azione, attesa di lettura. `pos: 'top'` forza il sottotitolo in alto
  // (automatico quando è aperta una finestra di dialogo, per non coprire i suoi pulsanti).
  async step(text, action, opts = {}) {
    const start = this.now();
    if (opts.chapter) this.chapters.push({ tempo: round3(start), titolo: opts.chapter });
    const dialogOpen = () => this.page.evaluate(() => Boolean(document.querySelector('dialog[open]'))).catch(() => false);
    let top = await dialogOpen();
    if (action) await action();
    const actionEnd = this.now();
    top = opts.pos ? opts.pos === 'top' : (top || await dialogOpen());
    await sleep(Math.max(MIN_HOLD, MS_PER_CHAR * text.length));
    this.steps.push({ text, start: round3(start), actionEnd: round3(actionEnd), end: round3(this.now()), top, cover: Boolean(opts.cover) });
  }

  locator(target) { return typeof target === 'string' ? this.page.locator(target).first() : target; }

  // Porta l'elemento in vista, disegna l'anello e sposta il puntatore finto. Restituisce null se non c'è.
  async aim(target, { strict = false } = {}) {
    const loc = this.locator(target);
    try {
      await loc.waitFor({ state: 'visible', timeout: strict ? 15000 : 8000 });
      // Porta l'elemento nella zona libera da barra superiore e sottotitoli, solo se non lo è già.
      await loc.evaluate(el => {
        const r = el.getBoundingClientRect();
        const top = 80;
        const bottom = window.innerHeight - 140;
        if (r.top >= top && r.bottom <= bottom) return;
        if (r.height > bottom - top) { el.scrollIntoView({ block: 'start', inline: 'nearest' }); window.scrollBy(0, -top); return; }
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
      }).catch(() => {});
      await sleep(150);
      const box = await loc.boundingBox();
      if (!box) throw new Error('senza riquadro');
      await this.page.evaluate(b => window.__wrGuide.aim(b), box);
      await sleep(700);
      return { loc, box };
    } catch (err) {
      if (strict) throw new Error(`Elemento non trovato (${typeof target === 'string' ? target : 'locator'}): ${err.message}`);
      this.problems.push(`evidenziazione saltata: ${typeof target === 'string' ? target : 'locator'}`);
      return null;
    }
  }

  async show(target) { await this.aim(target); }
  async clear() { await this.page.evaluate(() => window.__wrGuide.clear()).catch(() => {}); }

  async click(target, { after = 350 } = {}) {
    const { loc, box } = await this.aim(target, { strict: true });
    await this.page.evaluate(b => window.__wrGuide.pulse(b), box);
    await loc.click();
    await sleep(after);
  }

  async type(target, text) {
    const { loc } = await this.aim(target, { strict: true });
    await loc.click();
    await loc.pressSequentially(text, { delay: 45 });
    await sleep(200);
  }

  async fill(target, value) {
    const { loc } = await this.aim(target, { strict: true });
    await loc.fill(value);
    await sleep(250);
  }

  async select(target, value) {
    const { loc } = await this.aim(target, { strict: true });
    await loc.selectOption(value);
    await sleep(450);
  }

  async hover(target) {
    const { loc } = await this.aim(target, { strict: true });
    await loc.hover();
    await sleep(300);
  }

  // Apre il portale (con la sessione già nel context) su una pagina.
  async start(route = '') {
    await this.page.goto(`${this.base}/#/${route}`);
    await this.page.waitForSelector('.sidebar');
    await comune.ready(this.page);
  }

  async nav(label) {
    await this.click(`.nav-link:has-text("${label}")`);
    await sleep(200);
    await comune.ready(this.page);
  }

  async ready() { await sleep(150); await comune.ready(this.page); }
  async dialog() { await this.page.waitForSelector('dialog[open]', { timeout: 15000 }); await sleep(350); }
  async dialogClosed() { await this.page.waitForSelector('dialog[open]', { state: 'detached', timeout: 15000 }).catch(() => this.problems.push('finestra non chiusa')); }
  async toast() { await this.page.waitForSelector('.toast', { timeout: 8000 }).catch(() => this.problems.push('nessun avviso dopo il salvataggio')); }

  async close() {
    const duration = this.now();
    await this.context.close();
    const webm = await this.page.video().path();
    return { webm, duration, steps: this.steps, chapters: this.chapters, problems: this.problems };
  }
}

// ---------- Sessioni e preparazione ----------
// Accesso in un context nascosto: la sessione (cookie) e le preferenze (struttura, mese) passano al context registrato.
async function sessionState(browser, base, account, prefs = {}) {
  const ctx = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, locale: 'it-IT' });
  const page = await ctx.newPage();
  await comune.login(page, base, account);
  await page.evaluate(p => { for (const [k, v] of Object.entries(p)) localStorage.setItem('wr.' + k, v); }, prefs);
  const state = await ctx.storageState();
  await ctx.close();
  return state;
}

async function loginSteps(rec, account) {
  await rec.type('input[name="username"]', account.username);
  await rec.fill('input[name="password"]', account.password);
  await rec.click('button[type="submit"]');
  await rec.page.waitForSelector('input[name="code"]');
  await rec.fill('input[name="code"]', await comune.nextCode(account));
  await rec.click('button[type="submit"]');
  await rec.page.waitForSelector('.sidebar');
  await comune.ready(rec.page);
}

// Un documento fittizio come immagine (le anteprime PDF non si vedono nel browser senza interfaccia).
async function fakeDocument(browser, file) {
  const ctx = await browser.newContext({ viewport: { width: 900, height: 640 } });
  const page = await ctx.newPage();
  await page.setContent(`<html><body style="margin:0;font-family:system-ui,sans-serif;background:#fff">
<div style="margin:28px;padding:54px 64px;border:12px double #293f87;height:584px;box-sizing:border-box">
<div style="font-size:13px;letter-spacing:.22em;color:#6f7c95">DOCUMENTO FITTIZIO · SOLO PER LA DIMOSTRAZIONE</div>
<h1 style="font-size:36px;color:#293f87;margin:22px 0 10px">Attestato di formazione</h1>
<p style="font-size:20px;color:#17213a;line-height:1.5">Si attesta che <strong>Anna Rossi</strong> ha partecipato al corso<br>«Sicurezza e prevenzione nei reparti di dialisi» (16 ore).</p>
<p style="font-size:16px;color:#4a5873;margin-top:36px;line-height:1.6">Ente di formazione dimostrativo · Napoli, 12 settembre 2026<br>Validità fino al 30 giugno 2027</p>
<p style="font-size:13px;color:#6f7c95;margin-top:70px">Nessun dato reale: nomi e date sono inventati per le videoguide di NefroCenter WR.</p>
</div></body></html>`);
  await page.screenshot({ path: file });
  await ctx.close();
}

async function fetchJson(page, url) {
  return page.evaluate(async u => (await fetch(u, { credentials: 'same-origin' })).json(), url);
}

const WEEKDAYS = ['domenica', 'lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato'];
const MONTHS = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'];
function dateLong(iso) {
  const d = new Date(iso + 'T12:00:00');
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}
const dateShort = iso => iso.split('-').reverse().join('/');

// ---------- Le otto guide ----------
const GUIDES = [
  {
    n: '01', slug: 'accesso-e-panoramica', titolo: 'Accesso e panoramica del portale', profili: ['operator'],
    descrizione: 'Primo accesso con codice di attivazione e app Authenticator, codici di recupero, accesso normale, riepilogo, menu, barra superiore e guida contestuale.',
    async run(rec, env) {
      const pauses = {
        accesso: async () => {
          await rec.step('Questa è la pagina di accesso di NefroCenter WR. Si entra con nome utente, password e il codice dell’app Authenticator.',
            () => rec.show('.auth-card'), { chapter: 'Primo accesso' });
          await rec.step('Al primo accesso premi «Usa il codice di attivazione»: il codice lo consegna l’amministratore e vale 7 giorni.',
            () => rec.show('.auth-switch button'));
        },
        'primo-accesso': async () => {
          await rec.step('Scrivi il nome utente e il codice di attivazione, poi premi Continua.', () => rec.show('.auth-card button[type="submit"]'));
        },
        'attivazione-app': async () => {
          await rec.step('Inquadra il codice QR con l’app Authenticator del telefono, oppure inserisci a mano la chiave scritta sotto.',
            () => rec.show('.qr'), { chapter: 'App Authenticator' });
          await rec.step('Scegli una password personale di almeno 12 caratteri e scrivi il codice a 6 cifre che appare nell’app. Poi premi «Attiva l’account».',
            () => rec.show('input[name="code"]'));
        },
        'codici-recupero': async () => {
          await rec.step('Conserva i codici di recupero: servono se perdi il telefono e non verranno mostrati di nuovo. Questi sono codici di prova, fittizi.',
            () => rec.show('.codes'), { chapter: 'Codici di recupero' });
        },
      };
      env.accounts.operator = await comune.activate(rec.page, env.base, comune.ACCOUNTS.operator, env.codes[comune.ACCOUNTS.operator],
        name => (pauses[name] ? pauses[name]() : Promise.resolve()));
      await rec.step('Sei nel Riepilogo: i numeri del mese e le attività da completare della tua struttura.', () => rec.show('.kpis'),
        { chapter: 'Riepilogo e menu', cover: true });
      await rec.step('Il menu a sinistra è diviso per aree. Vedi soltanto le pagine permesse al tuo profilo.', () => rec.show('.sidebar'));
      await rec.step('Apriamo il «Registro presenze».', () => rec.nav('Registro presenze'));
      await rec.step('In alto scegli la struttura e il mese di riferimento: valgono per tutte le pagine.', () => rec.show('.topbar .context'),
        { chapter: 'Barra superiore e guida' });
      await rec.step('Il pulsante con il punto interrogativo apre la guida della pagina in cui ti trovi.', async () => {
        await rec.click('button[aria-label="Guida della pagina"]');
        await sleep(400);
        await rec.show('.help-panel');
      });
      await rec.step('Chiudi la guida con la X. Per uscire dal portale premi «Esci», in alto a destra.', async () => {
        await rec.click('button[aria-label="Chiudi la guida"]');
        await rec.click('button[aria-label="Esci"]');
        await rec.page.waitForSelector('input[name="username"]');
      }, { chapter: 'Uscita e accesso normale' });
      await rec.step('Dai successivi accessi: nome utente e password, poi «Continua».', async () => {
        await rec.type('input[name="username"]', env.accounts.operator.username);
        await rec.fill('input[name="password"]', env.accounts.operator.password);
        await rec.click('button[type="submit"]');
        await rec.page.waitForSelector('input[name="code"]');
      });
      await rec.step('Poi il codice a 6 cifre dell’app Authenticator e «Accedi».', async () => {
        await rec.fill('input[name="code"]', await comune.nextCode(env.accounts.operator));
        await rec.click('button[type="submit"]');
        await rec.page.waitForSelector('.sidebar');
        await comune.ready(rec.page);
      });
      await rec.step('Sei di nuovo nel portale: buon lavoro.', () => rec.show('.kpis'));
    },
  },
  {
    n: '02', slug: 'registrare-le-presenze', titolo: 'Registrare le presenze', profili: ['operator'],
    descrizione: 'Il registro del mese: struttura e mese, registrazione di un turno o di un’assenza, correzione di una casella, vista Giorno, consuntivo e pianificato.',
    account: 'operator', prefs: env => ({ cid: env.ids.cap, month: '2026-10', 'att.mode': 'month' }),
    async run(rec) {
      const empty = 'button.cell[aria-label="Paolo Greco, giovedì 22 ottobre 2026, Mattina: vuota"]';
      const filled = 'button.cell[aria-label^="Paolo Greco, giovedì 22 ottobre 2026, Mattina: Mattina"]';
      await rec.start();
      await rec.step('Apri «Registro presenze» dal menu. In alto scegli struttura e mese: qui Capodichino, ottobre 2026.', async () => {
        await rec.nav('Registro presenze');
        await rec.show('.topbar .context');
      }, { chapter: 'Il registro del mese' });
      await rec.step('Ogni riga è una persona con le sue fasce: m mattina, p pomeriggio, s serale, n notte. Ogni colonna è un giorno del mese.',
        () => rec.show('table.register tbody th.name-cell'));
      await rec.step('Clicca una casella vuota: scegliamo Paolo Greco, giovedì 22 ottobre, fascia Mattina.', async () => {
        await rec.click(empty);
        await rec.dialog();
      }, { chapter: 'Registrare un turno' });
      await rec.step('Nella finestra scegli la causale: un turno (m, p, s, n) oppure un’assenza, per esempio FE ferie o MA malattia.',
        () => rec.show('dialog[open] select[name="code"]'));
      await rec.step('Gli orari sono quelli proposti dalla fascia. Il compilatore non li cambia: se serve, li corregge il responsabile.',
        () => rec.show('dialog[open] fieldset'));
      await rec.step('Premi «Salva»: la casella mostra il turno registrato.', async () => {
        await rec.click('dialog[open] .dialog-foot .btn.primary');
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
        await rec.show(filled);
      }, { cover: true });
      await rec.step('Per correggere, clicca una casella già compilata: si riapre la registrazione.', async () => {
        await rec.click(filled);
        await rec.dialog();
      }, { chapter: 'Correggere una casella' });
      await rec.step('Cambia la causale, per esempio in «PS · Permesso», e salva di nuovo. Ogni modifica resta nello storico del mese.', async () => {
        await rec.select('dialog[open] select[name="code"]', 'PS');
        await rec.click('dialog[open] .dialog-foot .btn.primary');
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
      });
      await rec.step('La vista «Giorno» elenca le persone di un giorno con un pulsante per ogni fascia: è comoda sul telefono.', async () => {
        await rec.click('.segmented button:has-text("Giorno")');
        await rec.select('select[aria-label="Giorno"]', '2026-10-22');
        await rec.show('.day-list');
      }, { chapter: 'Vista Giorno' });
      await rec.step('Torniamo alla vista «Mese».', () => rec.click('.segmented button:has-text("Mese")'));
      await rec.step('«Consuntivo» mostra i turni svolti davvero. «Pianificato» mostra i turni previsti, con il bordo tratteggiato.', async () => {
        await rec.click('.segmented button:has-text("Pianificato")');
        await rec.show('table.register');
      }, { chapter: 'Consuntivo e pianificato' });
      await rec.step('Nel consuntivo una fascia pianificata ma non ancora confermata resta tratteggiata: cliccala per registrarla.', async () => {
        await rec.click('.segmented button:has-text("Consuntivo")');
        await rec.show('button.cell[aria-label="Elena Costa, lunedì 19 ottobre 2026, Serale: vuota"]');
      });
    },
  },
  {
    n: '03', slug: 'controlli-e-chiusura', titolo: 'Controlli e chiusura del mese', profili: ['manager'],
    descrizione: 'I controlli del mese, i pazienti per fascia, la conferma di calendario e parametri, lo storico e dove si chiude (o riapre) il mese.',
    account: 'manager', prefs: env => ({ cid: env.ids.cap, month: '2026-10' }),
    async run(rec) {
      const workload = '.card:has(h2:text("Pazienti e carico per fascia"))';
      await rec.start();
      await rec.step('«Controlli e chiusura» riassume il mese della struttura: turni a consuntivo, orari mancanti, fasce da consuntivare, assenze.', async () => {
        await rec.nav('Controlli e chiusura');
        await rec.show('.kpis');
      }, { chapter: 'Controlli del mese' });
      await rec.step('Qui sono elencati i controlli da risolvere prima della chiusura.', () => rec.show('.card:has(h2:text("Controlli prima della chiusura"))'));
      await rec.step('«Pazienti e carico per fascia»: registra i pazienti del giorno per confrontare il carico con i riferimenti della struttura.', async () => {
        await rec.fill(`${workload} input[name="ordinary"]`, '18');
        await rec.fill(`${workload} input[name="isolated"]`, '1');
        await rec.click(`${workload} button[type="submit"]`);
        await rec.toast();
        await rec.ready();
      }, { chapter: 'Pazienti per fascia' });
      await rec.step('La tabella mostra, giorno per giorno, i pazienti per infermiere e per medico. È un confronto organizzativo, non clinico.',
        () => rec.show(`${workload} .table-wrap`));
      await rec.step('Quando festivi, fasce e parametri sono corretti, premi «Conferma calendario e parametri».', async () => {
        await rec.click('button:has-text("Conferma calendario e parametri")');
        await rec.toast();
        await rec.ready();
        await rec.show('.page-head .row');
      }, { chapter: 'Conferma e chiusura', cover: true });
      await rec.step('Le ultime modifiche restano nello storico, con data e autore.', () => rec.show('.card:has(h2:text("Ultime modifiche"))'));
      await rec.step('Capodichino usa il percorso di approvazione: il mese si chiude dalla pagina «Approvazioni», non da qui.',
        () => rec.show('button:has-text("Vai alle approvazioni")'));
      await rec.step('Pozzuoli non usa l’approvazione. Scegliamo Pozzuoli e il mese di settembre, già chiuso.', async () => {
        await rec.select('.context-center', { label: 'Pozzuoli · Demo' });
        await rec.ready();
        await rec.click('button[aria-label="Mese precedente"]');
        await rec.ready();
        await rec.show('.page-head .row');
      }, { chapter: 'Riaprire e chiudere un mese' });
      await rec.step('Per correggere un mese chiuso il responsabile lo riapre indicando la motivazione, che resta nello storico.', async () => {
        await rec.click('button:has-text("Riapri il mese")');
        await rec.dialog();
        await rec.type('dialog[open] textarea', 'Correzione di un turno (dimostrazione)');
        await rec.click('dialog[open] .dialog-foot .btn.primary');
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
      });
      await rec.step('Fatta la correzione, «Chiudi il mese» lo chiude di nuovo: prima tutti i controlli devono essere risolti.', async () => {
        await rec.click('button:has-text("Chiudi il mese")');
        await rec.toast();
        await rec.ready();
        await rec.show('.page-head .row');
      });
    },
  },
  {
    n: '04', slug: 'approvazione-mensile', titolo: 'Approvazione mensile', profili: ['manager', 'hr'],
    descrizione: 'Il percorso struttura → responsabile → HR: invio del mese, registro bloccato, verifica del responsabile, «Tocca a te», restituzione o approvazione da parte di HR.',
    account: 'manager', prefs: env => ({ cid: env.ids.cap, month: '2026-09' }),
    async run(rec, env) {
      const confirm = 'dialog[open] .dialog-foot .btn:last-child';
      await rec.start();
      await rec.step('«Approvazioni» mostra, per il mese scelto in alto, lo stato di ogni struttura lungo il percorso: struttura, responsabile, HR centrale.', async () => {
        await rec.nav('Approvazioni');
        await rec.show('.steps');
      }, { chapter: 'Il percorso di approvazione' });
      await rec.step('Settembre di Capodichino è già approvato. Per la dimostrazione lo riapriamo indicando una motivazione.', async () => {
        await rec.click('button:has-text("Riapri il mese")');
        await rec.dialog();
        await rec.type('dialog[open] textarea', 'Correzione di un turno (dimostrazione)');
        await rec.click(confirm);
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
      });
      await rec.step('Il compilatore o il responsabile invia il mese al responsabile: da quel momento il registro è bloccato.', async () => {
        await rec.click('button:has-text("Invia al responsabile")');
        await rec.dialog();
        await rec.click(confirm);
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
        await rec.show('.steps');
      }, { chapter: 'Invio del mese', cover: true });
      await rec.step('Nel registro le caselle non si modificano più finché il mese non viene approvato o restituito.', async () => {
        await rec.nav('Registro presenze');
        await rec.show('.alert:has-text("inviato o approvato")');
      }, { chapter: 'Registro bloccato' });
      await rec.step('Il responsabile controlla i punti aperti, spunta la conferma del calendario e inoltra il mese a HR centrale.', async () => {
        await rec.nav('Approvazioni');
        await rec.click('button:has-text("Verifica e inoltra a HR")');
        await rec.dialog();
        const calendar = rec.page.locator('dialog[open] input[name="calendar"]');
        if (await calendar.count()) await rec.click(calendar);
        await rec.click(confirm);
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
      }, { chapter: 'Verifica del responsabile' });
      await rec.step('Ora tocca a HR centrale. Il responsabile esce dal portale.', async () => {
        await rec.click('button[aria-label="Esci"]');
        await rec.page.waitForSelector('input[name="username"]');
      }, { chapter: 'Approvazione di HR' });
      await rec.step('HR centrale accede con le proprie credenziali e il codice dell’app.', () => loginSteps(rec, env.accounts.hr));
      await rec.step('Nell’elenco la struttura è segnata «Tocca a te»: il passaggio aspetta HR.', async () => {
        await rec.nav('Approvazioni');
        await rec.show('.badge:has-text("Tocca a te")');
      });
      await rec.step('HR può restituire il mese con una motivazione: la struttura corregge e lo invia di nuovo. Qui annulliamo.', async () => {
        await rec.click('button:has-text("Restituisci per correzioni")');
        await rec.dialog();
        await rec.show('dialog[open] textarea');
        await rec.click('dialog[open] .dialog-foot .btn:first-child');
        await rec.dialogClosed();
      });
      await rec.step('Oppure approva: il mese viene chiuso e i dati restano bloccati.', async () => {
        await rec.click('button:has-text("Approva e chiudi")');
        await rec.dialog();
        await rec.click(confirm);
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
        await rec.show('.steps');
      });
      await rec.step('Lo storico conserva ogni passaggio con data, autore e nota.', () => rec.show('.card:has(h2:text("Storico"))'));
    },
  },
  {
    n: '05', slug: 'fascicolo-e-documenti', titolo: 'Fascicolo del personale e documenti', profili: ['hr'],
    descrizione: 'Ricerca di una persona, le linguette del fascicolo, l’allegato di un documento e la verifica di HR centrale dalla pagina Documenti.',
    account: 'hr', prefs: env => ({ cid: env.ids.cap }),
    async run(rec, env) {
      const docName = path.basename(env.docPng);
      await rec.start();
      await rec.step('«Persone e fascicoli» elenca le persone della struttura scelta in alto: ruolo, ingresso, stato, inserimento e documenti.', async () => {
        await rec.nav('Persone e fascicoli');
        await rec.show('.card:has(h2:text("Elenco"))');
      }, { chapter: 'Elenco e ricerca' });
      await rec.step('Cerca per nome, matricola o reparto.', () => rec.type('input[aria-label="Cerca persona"]', 'Rossi'));
      await rec.step('Apri il fascicolo con un clic sulla riga.', async () => {
        await rec.click('.table tbody tr:has-text("Anna Rossi")');
        await rec.ready();
      }, { chapter: 'Il fascicolo' });
      await rec.step('Il fascicolo è diviso in linguette: anagrafica, recapiti, contratto, amministrazione, qualifiche, inserimento, documenti, scadenze.',
        () => rec.show('.tabs'), { cover: true });
      await rec.step('Recapiti: indirizzo, telefono, email personale e aziendale.', () => rec.click('.tab:has-text("Recapiti")'));
      await rec.step('Contratto: tipo, CCNL, livello, ore settimanali e date di ingresso e fine.', () => rec.click('.tab:has-text("Contratto")'));
      await rec.step('Qualifiche: titoli, iscrizione all’albo e relative scadenze.', () => rec.click('.tab:has-text("Qualifiche")'));
      await rec.step('Inserimento: le attività previste dal modello della struttura, con referente, scadenza e stato.', () => rec.click('.tab:has-text("Inserimento")'));
      await rec.step('Documenti: allega un PDF o un’immagine indicando la categoria e, se prevista, la scadenza.', async () => {
        await rec.click('.tab:has-text("Documenti")');
        await rec.page.setInputFiles('input[type="file"]', env.docPng);
        await rec.show('input[type="file"]');
        const categories = await rec.page.$$eval('select[name="category"] option', els => els.map(o => o.value));
        const chosen = categories.find(c => /attestat|formazion/i.test(c)) || categories[0];
        if (chosen) await rec.select('select[name="category"]', chosen);
        await rec.fill('input[name="expiry"]', '2027-06-30');
      }, { chapter: 'Documenti del fascicolo' });
      await rec.step('Premi «Allega»: il documento resta «Ricevuto» finché HR centrale non lo verifica.', async () => {
        await rec.click('button:has-text("Allega")');
        await rec.toast();
        await rec.ready();
        await rec.show(`.table tbody tr:has-text("${docName}")`);
      });
      await rec.step('La pagina «Documenti» raccoglie gli allegati di tutte le strutture, con scadenze e stato della verifica.', async () => {
        await rec.nav('Documenti');
        await rec.show('.kpis');
      }, { chapter: 'Verifica dei documenti' });
      await rec.step('Filtra «Da verificare» per vedere solo i documenti ricevuti e non ancora controllati.', async () => {
        await rec.select('select[aria-label="Verifica"]', 'received');
        await sleep(700);
        await rec.show('.table');
      });
      await rec.step('Apri il documento: l’anteprima mostra il file e, sotto, lo storico della verifica.', async () => {
        await rec.click(`.table tbody tr:has-text("${docName}") button:has-text("Apri")`);
        await rec.dialog();
        await rec.page.waitForSelector('dialog[open] .doc-image, dialog[open] .doc-frame');
        await sleep(600);
      });
      await rec.step('Puoi approvarlo con «Verificato» oppure premere «Chiedi correzione» spiegando nella nota che cosa manca: la struttura potrà ripresentarlo.',
        () => rec.show('dialog[open] .dialog-foot .btn:has-text("Chiedi correzione")'));
      await rec.step('Qui lo approviamo: lo stato passa a «Verificato da HR» ed esce dall’elenco dei documenti da verificare.', async () => {
        await rec.click('dialog[open] .dialog-foot .btn:has-text("Verificato")');
        await rec.dialogClosed();
        await rec.toast();
        await sleep(900);
        await rec.show('.kpis');
      });
    },
  },
  {
    n: '06', slug: 'copertura-e-sostituzioni', titolo: 'Copertura turni e sostituzioni', profili: ['manager'],
    descrizione: 'Il prospetto delle fasce sotto il fabbisogno, i fabbisogni minimi, la proposta di una sostituzione da un’altra struttura e la sua accettazione.',
    account: 'manager', prefs: env => ({ cid: env.ids.cap, month: '2026-10' }),
    async run(rec, env) {
      await rec.start();
      // Giorno e fascia della proposta: una fascia INF scoperta in cui Anna Rossi non ha già un turno né una proposta.
      const [staffing, snap] = await Promise.all([fetchJson(rec.page, `api/staffing/${env.ids.cap}/2026-10`), fetchJson(rec.page, `api/attendance/${env.ids.cap}/2026-10`)]);
      const anna = snap.people.find(p => p.name === 'Anna Rossi');
      const busy = new Set(snap.entries.filter(e => e.person_id === anna?.id).map(e => `${e.day}|${e.slot}`));
      const proposed = new Set(staffing.substitutions.map(s => `${s.day}|${s.slot}`));
      let choice = null;
      for (const r of staffing.rows.filter(r => r.state === 'uncovered' && r.role === 'INF' && r.day > env.today).sort((a, b) => a.day.localeCompare(b.day))) {
        if (!busy.has(`${r.day}|${r.slot}`) && !proposed.has(`${r.day}|${r.slot}`)) { choice = r; break; }
      }
      const day = choice?.day || '2026-10-28';
      const slot = choice?.slot || 'm';
      const slotLabel = staffing.slots.find(s => s.id === slot)?.label || slot;
      const row = `.table tbody tr:has-text("${dateShort(day)}")`;
      await rec.step('«Copertura turni» confronta i turni pianificati con il fabbisogno minimo per giorno, fascia e qualifica.', async () => {
        await rec.nav('Copertura turni');
        await rec.show('.kpis');
      }, { chapter: 'Prospetto' });
      await rec.step('Nel prospetto ogni casella indica pianificati/minimo: rosso scoperto, verde coperto, blu oltre il fabbisogno.', () => rec.show('table.coverage'));
      await rec.step('Nella scheda «Fabbisogni» il responsabile definisce i minimi settimanali e le eccezioni per singole date.', async () => {
        await rec.click('.tab:has-text("Fabbisogni")');
        await rec.show('.card:has(h2:text("Fabbisogno settimanale"))');
      }, { chapter: 'Fabbisogni' });
      await rec.step('«Sostituzioni»: una persona di un’altra struttura può coprire un turno. Diventa turno pianificato solo se il responsabile accetta.', async () => {
        await rec.click('.tab:has-text("Sostituzioni")');
        await rec.show('.card:has(h2:text("Sostituzioni fra strutture"))');
      }, { chapter: 'Proporre una sostituzione' });
      await rec.step('Premi «Proponi»: Anna Rossi lavora anche a Pozzuoli e le sue schede sono collegate in «Personale di gruppo».', async () => {
        await rec.click('button:has-text("Proponi")');
        await rec.dialog();
        await rec.show('dialog[open] select[name="candidate"]');
      });
      await rec.step(`Indica giorno, fascia, causale e motivazione. Scegliamo ${dateLong(day)}, fascia ${slotLabel}.`, async () => {
        await rec.fill('dialog[open] input[name="day"]', day);
        await rec.select('dialog[open] select[name="slot"]', slot);
        await rec.type('dialog[open] textarea[name="note"]', 'Copertura del turno: infermiere mancante (demo)');
      });
      await rec.step('Premi «Invia la proposta»: compare nell’elenco come «In attesa».', async () => {
        await rec.click('dialog[open] .dialog-foot .btn.primary');
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
        await rec.click('.tab:has-text("Sostituzioni")');
        await rec.show(row);
      }, { cover: true });
      await rec.step('Decide il responsabile della struttura che riceve la persona. Il responsabile demo segue anche Capodichino e può accettare.', async () => {
        await rec.click(`${row} button:has-text("Accetta")`);
        await rec.dialog();
        await rec.type('dialog[open] textarea', 'Accettata: copre la fascia scoperta (demo)');
        await rec.click('dialog[open] .dialog-foot .btn.primary');
        await rec.dialogClosed();
        await rec.toast();
        await rec.ready();
        await rec.click('.tab:has-text("Sostituzioni")');
        await rec.show(row);
      }, { chapter: 'Accettazione' });
      await rec.step('La sostituzione accettata è ora un turno pianificato di Capodichino: eccolo, tratteggiato, nel registro «Pianificato».', async () => {
        await rec.nav('Registro presenze');
        await rec.click('.segmented button:has-text("Pianificato")');
        await rec.show(`button.cell[aria-label^="Anna Rossi, ${dateLong(day)}, ${slotLabel}:"]`);
      }, { chapter: 'Turno pianificato' });
    },
  },
  {
    n: '07', slug: 'comunicazioni', titolo: 'Comunicazioni al personale', profili: ['hr'],
    descrizione: 'Modelli, liste di destinatari, composizione, anteprima dei messaggi e bozza; l’invio reale richiede la posta aziendale configurata.',
    account: 'hr', prefs: () => ({}),
    async run(rec) {
      await rec.start();
      await rec.step('«Comunicazioni» prepara le email al personale e alle strutture: modelli, liste di destinatari, anteprima e bozze.', async () => {
        await rec.nav('Comunicazioni');
        await rec.show('.tabs');
      }, { chapter: 'Panoramica' });
      await rec.step('Nel portale di prova la posta aziendale non è configurata: si prepara tutto, ma nessun messaggio può partire.', () => rec.show('.alert.warn'));
      await rec.step('«Modelli»: oggetto e testo con variabili, come il nome della persona, sostituite per ogni destinatario.', async () => {
        await rec.click('.tab:has-text("Modelli")');
        await rec.show('.table');
      }, { chapter: 'Modelli e liste' });
      await rec.step('«Liste»: i destinatari scelti per struttura, ruolo e stato, con gli indirizzi da escludere.', async () => {
        await rec.click('.tab:has-text("Liste")');
        await rec.show('.table');
      });
      await rec.step('«Nuova comunicazione»: scegli modello e lista. Oggetto e testo si possono adattare solo per questo invio.', async () => {
        await rec.click('.tab:has-text("Nuova comunicazione")');
        await rec.select('select[name="template_id"]', { index: 0 });
        await rec.select('select[name="list_id"]', { index: 0 });
        await rec.type('input[name="name"]', 'Promemoria scadenze (demo)');
      }, { chapter: 'Anteprima e bozza' });
      await rec.step('«Anteprima dei messaggi» mostra quanti destinatari sono validi e come appare ogni messaggio personalizzato.', async () => {
        await rec.click('button:has-text("Anteprima dei messaggi")');
        await rec.page.waitForSelector('.mail-preview, .card:has(h2:text("Anteprima"))', { timeout: 15000 });
        await rec.show('.card:has(h2:text("Anteprima")) .kpis');
        await rec.show('.mail-preview');
      }, { cover: true });
      await rec.step('«Crea la bozza» salva la comunicazione: nessun messaggio viene inviato.', async () => {
        await rec.click('button:has-text("Crea la bozza")');
        await rec.toast();
        await rec.ready();
        await rec.show('.kpis');
      }, { chapter: 'Invio' });
      await rec.step('L’invio reale richiede la configurazione della posta aziendale da parte dell’amministratore. Fino ad allora la bozza resta qui.',
        () => rec.show('.alert.warn'));
      await rec.step('Da «Bozze e invii» ritrovi tutte le comunicazioni preparate e il loro stato.', async () => {
        await rec.click('a.eyebrow:has-text("Comunicazioni")');
        await rec.ready();
        await rec.show('.table');
      });
    },
  },
  {
    n: '08', slug: 'statistiche-ed-esportazioni', titolo: 'Statistiche ed esportazioni', profili: ['viewer'],
    descrizione: 'Scelta del periodo, grafico con il valore al passaggio del puntatore, tabelle; l’elenco dei file scaricabili e lo scarico di un CSV.',
    account: 'viewer', prefs: env => ({ cid: env.ids.cap, month: '2026-10' }),
    async run(rec) {
      await rec.start();
      await rec.step('«Statistiche» mostra l’andamento delle presenze delle strutture autorizzate, fino a 24 mesi.', async () => {
        await rec.nav('Statistiche');
        await rec.show('.kpis');
      }, { chapter: 'Statistiche' });
      await rec.step('Scegli il periodo con «Dal mese» e «Al mese»; poi, se vuoi, struttura, ruolo e persona.', async () => {
        await rec.fill('input[aria-label="Dal mese"]', '2026-07');
        await sleep(900);
        await rec.show('.filter-row');
      });
      await rec.step('Passa il puntatore sopra una colonna del grafico per leggere il valore del mese.', async () => {
        await rec.page.waitForSelector('.chart-hit');
        await rec.hover(rec.page.locator('.chart-hit').last());
      }, { cover: true });
      await rec.step('Sotto, la tabella con il dettaglio per mese: turni, ore con orari, assenze, festivi e fuori sede.',
        () => rec.show('.card:has(h2:text("Dettaglio per mese"))'));
      await rec.step('Le altre linguette dividono i dati per struttura, ruolo, causale di assenza e persona, più la qualità dei dati.', async () => {
        await rec.click('.tab:has-text("Strutture")');
        await rec.show('.table');
      });
      await rec.step('«Esportazioni» elenca i prospetti Excel e i file CSV scaricabili: una copia dei dati al momento dello scarico.', async () => {
        await rec.nav('Esportazioni');
        await rec.show('.grid-3');
      }, { chapter: 'Esportazioni' });
      await rec.step('Periodo e strutture valgono per i prospetti su più mesi; il registro mensile usa struttura e mese scelti in alto.',
        () => rec.show('.card:has(h2:text("Periodo e strutture"))'));
      await rec.step('Scarichiamo il riepilogo CSV di tutte le strutture: il file arriva nella cartella dei download del browser.', async () => {
        const waiting = rec.page.waitForEvent('download', { timeout: 15000 }).catch(() => null);
        await rec.click('button:has-text("Riepilogo di gruppo")');
        const download = await waiting;
        if (download) await download.path().catch(() => null);
        else rec.problems.push('nessun file scaricato');
        await rec.toast();
      });
    },
  },
];

// ---------- Produzione dei file ----------
function probe(file) {
  const info = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file]));
  const video = info.streams.find(s => s.codec_type === 'video') || {};
  return { codec: video.codec_name, larghezza: video.width, altezza: video.height, pix_fmt: video.pix_fmt, fps: video.avg_frame_rate,
    durata: Number(info.format.duration), tracce_audio: info.streams.filter(s => s.codec_type === 'audio').length, dimensione: Number(info.format.size) };
}

function produce(guide, result) {
  const base = `${guide.n}-${guide.slug}`;
  const files = { mp4: path.join(OUT, `${base}.mp4`), vtt: path.join(OUT, `${base}.vtt`), txt: path.join(OUT, `${base}.txt`), jpg: path.join(OUT, `${base}.jpg`) };
  const srt = path.join(TMP, `${base}.srt`);
  const webmDuration = probe(result.webm).durata || result.duration + 1;
  const cues = buildCues(result.steps, webmDuration);
  fs.writeFileSync(srt, toSrt(cues), 'utf-8');
  const filter = `subtitles=filename=${escapeFilter(srt)}:fontsdir=${escapeFilter(FONTS)}:force_style='${STYLE}'`;
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', result.webm, '-vf', filter, '-c:v', 'libx264', '-preset', 'medium', '-crf', '22',
    '-pix_fmt', 'yuv420p', '-r', String(FPS), '-an', '-movflags', '+faststart', files.mp4]);
  const info = probe(files.mp4);
  const clamped = cues.map(c => ({ ...c, end: Math.min(c.end, info.durata - 0.05) })).filter(c => c.end > c.start);
  fs.writeFileSync(files.vtt, toVtt(clamped), 'utf-8');
  fs.writeFileSync(files.txt, `${guide.titolo}\n${guide.descrizione}\n\n${result.steps.map(s => s.text).join('\n\n')}\n`, 'utf-8');
  const coverStep = result.steps.find(s => s.cover) || result.steps[Math.floor(result.steps.length / 2)];
  const coverTime = Math.max(0.5, Math.min(coverStep.actionEnd + 0.5, info.durata - 0.5));
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', coverTime.toFixed(2), '-i', files.mp4, '-frames:v', '1', '-q:v', '3', files.jpg]);
  const meta = {
    file: `${base}.mp4`, titolo: guide.titolo, descrizione: guide.descrizione, durata_secondi: Math.round(info.durata * 10) / 10,
    profili: guide.profili.map(r => ROLE_LABEL[r]), copertina: `${base}.jpg`, sottotitoli: `${base}.vtt`, trascrizione: `${base}.txt`,
    capitoli: result.chapters.map(c => ({ tempo: Math.round(c.tempo * 10) / 10, titolo: c.titolo })),
    controllo: { ...info, cue: clamped.length, passi: result.steps.length, copertina_al_secondo: Math.round(coverTime * 10) / 10,
      problemi: result.problems, cue_ok: checkCues(clamped, info.durata), durata_ok: info.durata >= 45 && info.durata <= 150 },
  };
  fs.writeFileSync(path.join(TMP, `${base}.meta.json`), JSON.stringify(meta, null, 1), 'utf-8');
  fs.rmSync(result.webm, { force: true });
  fs.rmSync(srt, { force: true });
  return meta;
}

function checkCues(cues, duration) {
  const errors = [];
  cues.forEach((c, i) => {
    if (!(c.start < c.end)) errors.push(`cue ${i + 1}: inizio non precede la fine`);
    if (i && cues[i - 1].end > c.start + 1e-6) errors.push(`cue ${i + 1}: si sovrappone alla precedente`);
    if (c.end > duration + 1e-6) errors.push(`cue ${i + 1}: oltre la durata`);
    if (c.lines.length > 2 || c.lines.some(l => l.length > MAX_LINE)) errors.push(`cue ${i + 1}: troppo lungo`);
  });
  return errors.length ? errors : true;
}

function buildIndex(metas, product) {
  const index = { prodotto: product.product, versione: product.version, generato_il: new Date().toISOString(),
    video: metas.map(({ controllo, ...m }) => m) };
  fs.writeFileSync(path.join(OUT, 'indice.json'), JSON.stringify(index, null, 1) + '\n', 'utf-8');
  const missing = [];
  for (const v of index.video) {
    for (const f of [v.file, v.copertina, v.sottotitoli, v.trascrizione]) if (!fs.existsSync(path.join(OUT, f))) missing.push(f);
  }
  return { voci: index.video.length, file_mancanti: missing };
}

// ---------- Esecuzione ----------
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(TMP, { recursive: true });
  for (const f of fs.readdirSync(TMP)) if (f.endsWith('.webm') || f.endsWith('.srt')) fs.rmSync(path.join(TMP, f), { force: true });
  const wanted = OPTS.solo ? OPTS.solo.split(',').map(s => s.trim().padStart(2, '0')) : GUIDES.map(g => g.n);
  const summary = { video: [], errori: [] };
  const server = await comune.startServer(comune.WORK, PORT);
  let browser = null;
  try {
    browser = await comune.launch();
    const env = { base: server.base, codes: server.codes, accounts: {}, ids: {}, today: '' };
    // Account di prova: attivati una volta ciascuno, in un context nascosto nuovo (il Compilatore nella guida 01, se prevista).
    let product = null;
    const roles = ['manager', 'hr', 'viewer'].concat(wanted.includes('01') ? [] : ['operator']);
    for (const role of roles) {
      const hidden = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, locale: 'it-IT' });
      const page = await hidden.newPage();
      env.accounts[role] = await comune.activate(page, env.base, comune.ACCOUNTS[role], env.codes[comune.ACCOUNTS[role]]);
      if (role === 'hr') {   // profilo che vede tutte le strutture: identificativi, data di riferimento, prodotto e versione
        const me = await fetchJson(page, 'api/me');
        env.today = me.today;
        for (const c of me.centers) {
          if (c.name.startsWith('Capodichino')) env.ids.cap = c.id;
          if (c.name.startsWith('Pozzuoli')) env.ids.poz = c.id;
          if (c.name.startsWith('Vomero')) env.ids.vom = c.id;
        }
        product = await comune.catalog(page);
      }
      await hidden.close();
    }
    env.docPng = path.join(TMP, 'attestato_formazione_anna.png');
    await fakeDocument(browser, env.docPng);

    for (const guide of GUIDES) {
      if (!wanted.includes(guide.n)) continue;
      const rec = new Recorder(browser, env.base, guide);
      const label = `${guide.n}-${guide.slug}`;
      try {
        const state = guide.account ? await sessionState(browser, env.base, env.accounts[guide.account], guide.prefs(env)) : null;
        await rec.open(state);
        await guide.run(rec, env);
      } catch (err) {
        rec.problems.push(`errore durante la registrazione: ${err.message}`);
        summary.errori.push(`${label}: ${err.message}`);
        if (rec.page && !rec.page.isClosed()) await rec.page.screenshot({ path: path.join(TMP, `${label}-errore.png`) }).catch(() => {});
        if (!rec.steps.length) { await rec.context?.close().catch(() => {}); continue; }
      }
      const result = await rec.close();
      const meta = produce(guide, result);
      summary.video.push(meta);
      console.error(`${label}: ${meta.durata_secondi}s, ${meta.controllo.cue} cue, ${Math.round(meta.controllo.dimensione / 1024)} KB`);
    }
    // Indice: le guide registrate ora più i metadati salvati delle altre.
    const metas = GUIDES.map(g => {
      const fresh = summary.video.find(m => m.file.startsWith(g.n));
      if (fresh) return fresh;
      const saved = path.join(TMP, `${g.n}-${g.slug}.meta.json`);
      return fs.existsSync(saved) ? JSON.parse(fs.readFileSync(saved, 'utf-8')) : null;
    }).filter(Boolean);
    summary.indice = buildIndex(metas, product);
    summary.controlli = metas.map(m => ({ file: m.file, durata: m.durata_secondi, dimensione: m.controllo.dimensione, codec: m.controllo.codec,
      formato: `${m.controllo.larghezza}x${m.controllo.altezza} ${m.controllo.pix_fmt} ${m.controllo.fps}`, tracce_audio: m.controllo.tracce_audio,
      cue: m.controllo.cue, cue_ok: m.controllo.cue_ok, durata_ok: m.controllo.durata_ok, problemi: m.controllo.problemi }));
    summary.ok = summary.controlli.every(c => c.codec === 'h264' && c.formato.startsWith('1280x720') && c.tracce_audio === 0 && c.cue_ok === true && c.durata_ok)
      && !summary.indice.file_mancanti.length && !summary.errori.length;
    delete summary.video;
    console.log(JSON.stringify(summary, null, 1));
    process.exitCode = summary.ok ? 0 : 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    await server.stop();
    for (const f of fs.readdirSync(TMP)) if (f.endsWith('.webm')) fs.rmSync(path.join(TMP, f), { force: true });
  }
})().catch(err => { console.error(err); process.exit(1); });
