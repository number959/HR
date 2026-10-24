/* Contextual help is independent from application forms and never writes data. */
(() => {
  'use strict';
  const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const folded = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('it');
  let selectedTopic = 'avvio';
  let stopTour = null;
  const aliases = {attivita:'completare',gruppo:'personale',documenti_hr:'hrcentrale',struttura:'strutture'};
  const extraTours = {
    completare: [
      {selector:'#tasksCenter',text:'Limita la lista a un centro oppure consulta tutti i centri autorizzati.'},
      {selector:'#tasksCategory',text:'Scegli il tipo di attività da completare.'},
      {selector:'#tasksPriority',text:'Metti in evidenza ciò che richiede un controllo immediato.'},
      {selector:'[data-task-index]',text:'Apri la pagina del dato da completare. La voce scompare dopo la correzione e l’aggiornamento della lista.'}
    ],
    personale: [
      {selector:'#workforceOn',text:'La data mostra le condizioni contrattuali valide in quel giorno.'},
      {selector:'#workforceSearch',text:'Cerca la persona nelle assegnazioni dei centri autorizzati.'},
      {selector:'[data-wf-group]',text:'Apri la persona per verificare i fascicoli e le assegnazioni.'},
      {selector:'[data-wf-link]',text:'Collega due anagrafiche solo dopo aver verificato che appartengono alla stessa persona.'},
      {selector:'[data-wf-contract]',text:'Aggiungi una decorrenza contrattuale con date inclusive e una motivazione.'},
      {selector:'[data-wf-economics]',text:'Registra le condizioni economiche e il periodo in cui valgono.'},
      {selector:'[data-wf-preview]',text:'Controlla il calcolo prima di applicare le condizioni al mese aperto.'}
    ],
    hrcentrale: [
      {selector:'#hrDocCenter',text:'Consulta tutti i centri autorizzati oppure una sola sede.'},
      {selector:'#hrDocPerson',text:'Cerca la persona per nome o matricola.'},
      {selector:'#hrDocCategory',text:'Filtra gli allegati per categoria.'},
      {selector:'#hrDocExpiry',text:'Individua documenti scaduti o prossimi alla scadenza.'},
      {selector:'#hrDocApply',text:'Applica i filtri alla ricerca centrale.'},
      {selector:'[data-central-person]',text:'Apri il fascicolo del centro di origine per gestire gli allegati.'}
    ],
    guida: [
      {selector:'#nfHelpSearch',text:'Cerca una procedura, un campo o un’impostazione.'},
      {selector:'[data-help-mode="settings"]',text:'Il riferimento delle impostazioni spiega effetto ed esempio di ogni campo censito.'},
      {selector:'.nf-help-video',text:'Le videoguide sono illustrate e senza audio. Puoi attivare sottotitoli, scegliere un capitolo o leggere la trascrizione.'}
    ]
  };

  function catalog() { return window.NefroHelp || {topics:[],settings:[],version:'0.9'}; }
  function canonical(id) { return aliases[id] || id; }
  function topicById(id) { return catalog().topics.find(t => t.id === canonical(id)); }
  function topicSettings(id) { return catalog().settings.filter(s => s.topic === id); }
  function currentTopic(page) {
    const name = page || (typeof tab !== 'undefined' ? tab : 'avvio');
    if (name === 'dipendenti' && typeof hrPid !== 'undefined' && hrPid && typeof hrSection !== 'undefined' && topicById(hrSection)) return hrSection;
    return topicById(name)?.id || 'avvio';
  }
  window.helpTopicForPage = currentTopic;

  function settingsMarkup(items) {
    return items.map(s => `<article class="nf-help-setting"><h4>${html(s.label)}</h4><p>${html(s.effect)}</p><p class="nf-help-example"><strong>Esempio:</strong> ${html(s.example)}</p><span class="nf-help-meta">${html(s.section)}</span></article>`).join('');
  }

  function articleMarkup(topic, query, ordered) {
    const settings = topicSettings(topic.id), video = (window.NefroHelpVideos || []).find(v => v.id === topic.id);
    const safeId = /^[a-z0-9_-]+$/.test(topic.id) ? topic.id : '';
    const tour = [...(topic.tour || []), ...(extraTours[topic.id] || [])];
    const position = ordered.findIndex(t => t.id === topic.id), previous = ordered[position-1], next = ordered[position+1];
    const picture = topic.image && /^\/assets\/guide_screens\/[a-z0-9_-]+\.webp$/.test(topic.image) ? topic.image : '';
    return `<article class="nf-help-article" aria-labelledby="nfHelpArticleTitle">
      <div class="nf-help-article-top"><span class="nf-help-kicker">PROCEDURA OPERATIVA</span><span class="nf-help-meta">${html(topic.duration || '')}</span></div>
      <h2 id="nfHelpArticleTitle">${html(topic.title)}</h2>
      <p class="nf-help-goal">${html(topic.goal)}</p><p class="nf-help-audience"><strong>A chi serve</strong> ${html(topic.audience)}</p>
      ${topic.before?.length ? `<section class="nf-help-before"><h3>Prima di iniziare</h3><ul>${topic.before.map(x=>`<li>${html(x)}</li>`).join('')}</ul></section>` : ''}
      ${picture ? `<figure class="nf-help-figure"><a href="${picture}" target="_blank" rel="noopener" aria-label="Apri la schermata a piena risoluzione: ${html(topic.title)}"><img src="${picture}" alt="${html(topic.image_caption || topic.title)}" loading="lazy"></a><figcaption>${html(topic.image_caption || 'Schermata del portale')} · dati dimostrativi. <a href="${picture}" target="_blank" rel="noopener">Ingrandisci schermata</a></figcaption></figure>` : ''}
      <section class="nf-help-procedure"><div class="nf-help-section-heading"><h3>Segui questi passaggi</h3><span class="nf-help-meta">${topic.steps.length} passaggi</span></div><ol class="nf-help-steps">${topic.steps.map((step,i)=>`<li><span class="nf-help-step-number" aria-hidden="true">${i+1}</span><p>${html(step)}</p></li>`).join('')}</ol></section>
      ${tour.length ? '<button type="button" class="btn nf-help-tour-button" data-help-tour>Individua i comandi nella pagina</button><p class="nf-help-meta">Il tour evidenzia i comandi presenti nella pagina aperta e non modifica i dati.</p>' : ''}
      <div class="nf-help-result"><strong>Come capire se è riuscito</strong><p>${html(topic.result)}</p></div>
      ${topic.example ? `<section class="nf-help-worked-example"><span class="nf-help-kicker">UN ESEMPIO PRATICO</span><p>${html(topic.example)}</p></section>` : ''}
      ${video && safeId ? `<section class="nf-help-video-section" aria-label="Videoguida"><div class="nf-help-section-heading"><h3>Guarda la procedura</h3><span class="nf-help-video-badge">${video.width>=1920?'FULL HD · ':''}${Math.ceil(video.duration/60)} MIN</span></div><p class="nf-help-meta">Videoguida illustrata senza audio, con schermate dimostrative e sottotitoli. Scegli un capitolo o metti in pausa per leggere.</p>
        <video class="nf-help-video" controls playsinline preload="none" ${video.poster?`poster="/assets/guides/${safeId}.jpg"`:''} aria-label="Videoguida: ${html(topic.title)}"><source src="/assets/guides/${safeId}.mp4" type="video/mp4"><track kind="captions" src="/assets/guides/${safeId}.vtt" srclang="it" label="Italiano">Il browser non riproduce il video. Scaricalo o leggi la trascrizione.</video>
        <details class="nf-help-video-chapters"><summary>Scegli il capitolo (${video.chapters?.length || 0})</summary><div class="nf-help-chapters" aria-label="Capitoli del video">${(video.chapters || []).map(ch=>`<button type="button" class="btn small" data-help-chapter="${Number(ch.start)}"><span>${Math.floor(ch.start/60)}:${String(ch.start%60).padStart(2,'0')}</span> ${html(ch.title)}</button>`).join('')}</div></details>
        <div class="nf-help-links"><a class="btn small" href="/assets/guides/${safeId}.mp4" download>Scarica video</a><a class="btn small" href="/assets/guides/${safeId}.txt" target="_blank" rel="noopener">Leggi trascrizione</a></div></section>` : ''}
      ${topic.errors?.length ? `<section class="nf-help-errors"><h3>Problemi frequenti</h3>${topic.errors.map(error=>{const cut=error.indexOf(':');return `<details><summary>${html(cut>0?error.slice(0,cut):error)}</summary>${cut>0?`<p>${html(error.slice(cut+1).trim())}</p>`:''}</details>`}).join('')}</section>` : ''}
      ${settings.length ? `<details class="nf-help-settings-detail" ${query?'open':''}><summary>Campi e impostazioni spiegati (${settings.length})</summary><div class="nf-help-settings">${settingsMarkup(settings)}</div></details>` : ''}
      <nav class="nf-help-pagination" aria-label="Prosegui nella guida">${previous?`<button class="btn" data-help-page="${html(previous.id)}"><small>← Procedura precedente</small>${html(previous.title)}</button>`:'<span></span>'}${next?`<button class="btn" data-help-page="${html(next.id)}"><small>Procedura successiva →</small>${html(next.title)}</button>`:''}</nav>
      <p class="nf-help-status" role="status" aria-live="polite"></p></article>`;
  }

  function mountHelp(container, initial) {
    const data=catalog();let topicId=topicById(initial)?.id || topicById(selectedTopic)?.id || data.topics[0]?.id,mode='topics',query='',pathId='';
    container.classList.add('nf-help');
    if(!data.topics.length){container.innerHTML='<p class="error">Guide non disponibili. Ricarica la pagina o consulta GUIDE_UTENTE.md.</p>';return}
    const paths=data.quickstarts || [];
    container.innerHTML=`<section class="nf-help-hero"><div><span class="nf-help-kicker">IL PORTALE, PASSO DOPO PASSO</span><h2>Una guida per il tuo lavoro.</h2><p>Trova una procedura, segui i passaggi e verifica il risultato. Le schermate e gli esempi usano dati dimostrativi.</p></div>${data.manual_url?`<a class="btn nf-help-download" href="${html(data.manual_url)}" target="_blank" rel="noopener">Manuale illustrato · PDF</a>`:''}</section>
      <div class="nf-help-controls"><label class="nf-help-search" for="nfHelpSearch">Che cosa vuoi fare?<input id="nfHelpSearch" type="search" placeholder="Cerca: documento, chiusura mese, NAS…" autocomplete="off"></label>${paths.length?`<label class="nf-help-path-select" for="nfHelpPath">Oppure scegli un percorso<select id="nfHelpPath"><option value="">Tutte le procedure</option>${paths.map(p=>`<option value="${html(p.id)}">${html(p.role)} · ${html(p.title)}</option>`).join('')}</select></label>`:''}</div>
      <div class="nf-help-path-note" hidden></div><div class="nf-help-modes" aria-label="Tipo di contenuto"><button class="btn primary" data-help-mode="topics" aria-pressed="true">Procedure e video</button><button class="btn" data-help-mode="settings" aria-pressed="false">Cerca un’impostazione</button><span class="nf-help-count" role="status" aria-live="polite"></span></div><div class="nf-help-body"></div><p class="nf-help-footer">Guida ${html(data.version)} · ${data.topics.length} procedure · ${data.settings.length} impostazioni. Le funzioni disponibili dipendono dal ruolo e dai centri autorizzati.</p>`;
    const body=container.querySelector('.nf-help-body');
    function draw(){
      body.querySelectorAll('video').forEach(v=>v.pause());
      const normalized=folded(query.trim()),matches=value=>!normalized||folded(value).includes(normalized),path=paths.find(p=>p.id===pathId);
      const available=path?path.topics.map(topicById).filter(Boolean):data.topics;
      const topics=available.filter(t=>matches([t.title,t.audience,t.goal,t.example,...(t.before||[]),...t.steps,...(t.errors||[]),...topicSettings(t.id).flatMap(s=>[s.label,s.effect,s.example,s.section])].join(' ')));
      const settings=data.settings.filter(s=>(!path||path.topics.includes(s.topic))&&matches([s.label,s.effect,s.example,s.section,topicById(s.topic)?.title].join(' ')));
      const note=container.querySelector('.nf-help-path-note');note.hidden=!path;note.innerHTML=path?`<strong>${html(path.title)}</strong><p>${html(path.description)}</p><span>${path.topics.length} procedure · ${html(path.role)}</span>`:'';
      container.querySelector('.nf-help-count').textContent=mode==='topics'?`${topics.length} procedure trovate`:`${settings.length} impostazioni trovate`;
      container.querySelectorAll('[data-help-mode]').forEach(b=>{const active=mode===b.dataset.helpMode;b.classList.toggle('primary',active);b.setAttribute('aria-pressed',String(active))});
      if(mode==='settings')body.innerHTML=`<div class="nf-help-reference">${settings.length?settings.map(s=>`<section class="nf-help-reference-item">${settingsMarkup([s])}<button class="btn small" data-help-topic="${html(s.topic)}">Apri: ${html(topicById(s.topic)?.title||s.topic)}</button></section>`).join(''):'<p class="empty">Nessuna impostazione trovata. Prova un termine più breve o seleziona Tutte le procedure.</p>'}</div>`;
      else{
        if(!topics.some(t=>t.id===topicId))topicId=topics[0]?.id;
        const topic=topics.find(t=>t.id===topicId);if(topic)selectedTopic=topic.id;
        body.innerHTML=`<div class="nf-help-layout"><aside class="nf-help-index" aria-label="Indice delle procedure"><span class="nf-help-index-heading">${path?'IL TUO PERCORSO':'INDICE DELLA GUIDA'}</span>${topics.map((t,i)=>`<button data-help-topic="${html(t.id)}" ${t.id===topicId?'aria-current="true"':''}><span>${String(i+1).padStart(2,'0')}</span>${html(t.title)}</button>`).join('')||'<p>Nessuna procedura trovata.</p>'}</aside><div class="nf-help-detail">${topic?articleMarkup(topic,query,topics):'<p class="empty">Prova un’altra parola o seleziona Tutte le procedure.</p>'}</div></div>`;
      }
      body.querySelectorAll('[data-help-topic],[data-help-page]').forEach(b=>b.onclick=()=>{topicId=b.dataset.helpTopic||b.dataset.helpPage;mode='topics';query='';container.querySelector('#nfHelpSearch').value='';draw();const title=body.querySelector('#nfHelpArticleTitle');if(title){title.tabIndex=-1;title.focus({preventScroll:true});title.scrollIntoView({block:'nearest'})}});
      const tourButton=body.querySelector('[data-help-tour]');if(tourButton)tourButton.onclick=()=>window.startHelpTour(topicId);
      body.querySelectorAll('[data-help-chapter]').forEach(b=>b.onclick=()=>{const video=body.querySelector('video');if(!video)return;const play=()=>{video.currentTime=Number(b.dataset.helpChapter);video.play().catch(()=>{const status=body.querySelector('.nf-help-status');if(status)status.textContent='Premi Riproduci nel lettore per avviare la videoguida.'})};if(video.readyState>=1)play();else{video.addEventListener('loadedmetadata',play,{once:true});video.load()}});
    }
    container.querySelector('#nfHelpSearch').oninput=e=>{query=e.target.value;draw()};
    const pathSelect=container.querySelector('#nfHelpPath');if(pathSelect)pathSelect.onchange=e=>{pathId=e.target.value;query='';container.querySelector('#nfHelpSearch').value='';mode='topics';topicId=paths.find(p=>p.id===pathId)?.topics[0]||topicId;draw()};
    container.querySelectorAll('[data-help-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.helpMode;draw()});draw();
  }

  window.renderHelp = function(topic) {
    if (stopTour) stopTour();
    const onHelpPage = typeof tab !== 'undefined' && tab === 'guida';
    if (onHelpPage) {
      const old = document.getElementById('nfHelpDialog');
      if (old?.open) old.close();
      const content = document.getElementById('content');
      if (content) mountHelp(content, topic || selectedTopic);
      return;
    }
    let dialog = document.getElementById('nfHelpDialog');
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.id = 'nfHelpDialog';
      dialog.className = 'nf-help-dialog';
      dialog.setAttribute('aria-labelledby', 'nfHelpDialogTitle');
      document.body.appendChild(dialog);
      dialog.addEventListener('close', () => {
        dialog.querySelectorAll('video').forEach(v => v.pause());
        dialog.remove();
      });
    }
    dialog.innerHTML = '<div class="nf-help-dialog-top"><h2 id="nfHelpDialogTitle" tabindex="-1">Guida del portale</h2><button type="button" class="btn" data-help-close aria-label="Chiudi la guida">Chiudi ×</button></div><div class="nf-help-dialog-body"></div>';
    mountHelp(dialog.querySelector('.nf-help-dialog-body'), topic || currentTopic());
    dialog.querySelector('[data-help-close]').onclick = () => dialog.close();
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('#nfHelpDialogTitle').focus();
  };

  function visibleTarget(selector) {
    let target;
    try { target = document.querySelector(selector); } catch (_) { return null; }
    if (!target || target.closest('[hidden]')) return null;
    const style = getComputedStyle(target);
    const bounds = target.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden' || !bounds.width || !bounds.height) return null;
    return target;
  }

  window.startHelpTour = function(id) {
    const topic = topicById(id || currentTopic());
    if (!topic) return;
    if (stopTour) stopTour();
    const steps = [...(topic.tour || []), ...(extraTours[topic.id] || [])].filter(step => visibleTarget(step.selector));
    if (!steps.length) {
      const message = 'Per questo argomento non ci sono comandi visibili nella pagina aperta. Apri la pagina descritta, poi usa Aiuto pagina; la guida scritta e il video restano disponibili qui.';
      const status = document.querySelector('#nfHelpDialog .nf-help-status') || document.querySelector('.nf-help-status');
      if (status) status.textContent = message;
      else if (typeof toast === 'function') toast(message);
      return;
    }
    const helpDialog = document.getElementById('nfHelpDialog');
    if (helpDialog?.open) helpDialog.close();
    let current = 0;
    const previousFocus = document.activeElement;
    const dialog = document.createElement('dialog');
    dialog.className = 'nf-help-tour';
    dialog.setAttribute('aria-labelledby', 'nfTourTitle');
    dialog.setAttribute('aria-describedby', 'nfTourText');
    dialog.innerHTML = `<div class="nf-help-spotlight" aria-hidden="true"></div><section class="nf-help-tour-card"><span class="nf-help-meta" id="nfTourProgress"></span><h2 id="nfTourTitle">${html(topic.title)}</h2><p id="nfTourText"></p><p class="nf-help-meta">Esc o Fine chiude il tutorial. I dati rimangono invariati.</p><div class="nf-help-tour-controls"><button type="button" class="btn" data-tour-previous>Indietro</button><button type="button" class="btn primary" data-tour-next>Avanti</button><button type="button" class="btn" data-tour-close>Fine</button></div></section>`;
    document.body.appendChild(dialog);
    const card = dialog.querySelector('.nf-help-tour-card');
    const spotlight = dialog.querySelector('.nf-help-spotlight');
    function position() {
      const target = visibleTarget(steps[current].selector);
      if (!target) { finish(); return; }
      const r = target.getBoundingClientRect();
      spotlight.style.left = `${Math.max(2, r.left - 4)}px`;
      spotlight.style.top = `${Math.max(2, r.top - 4)}px`;
      spotlight.style.width = `${Math.max(0, Math.min(r.width + 8, window.innerWidth - Math.max(2,r.left - 4) - 2))}px`;
      spotlight.style.height = `${Math.max(0, Math.min(r.height + 8, window.innerHeight - Math.max(2,r.top - 4) - 2))}px`;
      const roomBelow = window.innerHeight - r.bottom;
      const top = roomBelow > card.offsetHeight + 24 ? r.bottom + 14 : r.top > card.offsetHeight + 24 ? r.top - card.offsetHeight - 14 : Math.max(12, window.innerHeight - card.offsetHeight - 12);
      card.style.top = `${Math.max(12, Math.min(top, window.innerHeight - card.offsetHeight - 12))}px`;
      card.style.left = `${Math.max(12, Math.min(r.left, window.innerWidth - card.offsetWidth - 12))}px`;
    }
    function draw() {
      const target = visibleTarget(steps[current].selector);
      if (!target) { finish(); return; }
      target.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      dialog.querySelector('#nfTourProgress').textContent = `Passo ${current + 1} di ${steps.length}`;
      dialog.querySelector('#nfTourText').textContent = steps[current].text;
      dialog.querySelector('[data-tour-previous]').disabled = current === 0;
      dialog.querySelector('[data-tour-next]').textContent = current === steps.length - 1 ? 'Concludi' : 'Avanti';
      position();
    }
    function finish() {
      window.removeEventListener('resize', position);
      document.removeEventListener('scroll', position, true);
      if (dialog.open) dialog.close();
      dialog.remove();
      stopTour = null;
      if (previousFocus?.isConnected) previousFocus.focus({preventScroll:true});
    }
    stopTour = finish;
    dialog.querySelector('[data-tour-previous]').onclick = () => { if (current) { current--; draw(); } };
    dialog.querySelector('[data-tour-next]').onclick = () => { if (current < steps.length - 1) { current++; draw(); } else finish(); };
    dialog.querySelector('[data-tour-close]').onclick = finish;
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(); });
    window.addEventListener('resize', position);
    document.addEventListener('scroll', position, true);
    dialog.showModal();
    draw();
    dialog.querySelector('[data-tour-next]').focus();
  };
})();
