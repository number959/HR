/* Public demonstration. Only synthetic fixtures; no authentication or live server.
 * Every visitor works on a private copy kept in this browser tab's sessionStorage.
 */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  try {if(!localStorage.getItem('presenze-interface-style')) localStorage.setItem('presenze-interface-style','workspace')} catch {}
  const STORE = 'nefrocenter-public-demo-v011';
  const ROLE_STORE = STORE + '-role';
  const TODAY = '2026-10-19';
  const ROLES = {
    admin: ['Amministratore', 'Esplora tutte le pagine, i centri e le configurazioni.', 'Tutto il portale'],
    hr: ['HR centrale', 'Consulta tutti i fascicoli e i documenti caricati dalle sedi.', 'Tutti i centri'],
    manager: ['Responsabile centro', 'Gestisci presenze, dipendenti e onboarding della sede.', 'Una sede'],
    operator: ['Compilatore', 'Prova a inserire e aggiornare le presenze del centro.', 'Registro presenze'],
    viewer: ['Direzione / lettore', 'Esplora dashboard, statistiche e presenze in lettura.', 'Consultazione']
  };
  const ROLE_HELP = {
    admin: {
      purpose:'Configura il gestionale e coordina gli accessi e le funzioni dell’intero gruppo.',
      scope:'Tutte le strutture.',
      can:['Gestire centri, utenti, ruoli e permessi.', 'Gestire il percorso sede → responsabile → HR, validare documenti e preparare i tracciati paghe.', 'Configurare email e promemoria, fabbisogni e sostituzioni; seguire uscite, dotazioni e backup anche sul NAS.'],
      boundary:'È il profilo con i permessi più estesi: va assegnato a chi amministra il sistema.',
      demo:'Esplora tutte le pagine. Account, 2FA reale, NAS, importazioni e configurazione SMTP richiedono l’installazione aziendale.'
    },
    hr: {
      purpose:'Lavora sul personale di tutte le sedi e raccoglie in un unico punto le attività dell’ufficio HR.',
      scope:'Tutte le strutture, anche quando un documento viene caricato da una sede remota.',
      can:['Creare e aggiornare fascicoli, onboarding, scadenze e documenti; consultare l’archivio documentale centrale.', 'Gestire recapiti delle strutture, personale di gruppo, decorrenze contrattuali ed economiche e preparazione paghe.', 'Approvare il mese verificato dal responsabile, validare o restituire i documenti, consultare promemoria e proporre sostituzioni.', 'Seguire uscite e restituzioni; preparare modelli, liste e comunicazioni email.'],
      boundary:'Non modifica direttamente le presenze o i parametri. La chiusura avviene con l’approvazione finale nel flusso attivo. Utenti, backup, SMTP e programmazione promemoria spettano all’amministratore.',
      demo:'In Documenti HR richiedi una correzione. In Approvazioni approva un mese già verificato dal responsabile. Le email restano simulate.'
    },
    manager: {
      purpose:'Organizza il lavoro della sede e verifica la completezza di presenze e informazioni del personale.',
      scope:'Solo le strutture assegnate. Nella demo: una sede.',
      can:['Gestire presenze, pianificazione, parametri, accordi mensili e conteggi di carico per fascia.', 'Verificare il mese inviato dalla sede e inoltrarlo a HR; restituirlo con motivazione se occorrono correzioni.', 'Aggiornare i fascicoli e ripresentare documenti corretti; gestire fabbisogni, disponibilità, sostituzioni autorizzate e restituzione dotazioni.'],
      boundary:'Nel flusso attivo non dà l’approvazione finale HR. Non valida i documenti, non crea account e non configura email, promemoria o backup.',
      demo:'Apri un fascicolo, allega il PDF dimostrativo, poi cambia profilo in HR centrale per ritrovarlo nella stessa sessione.'
    },
    operator: {
      purpose:'Compila il registro delle presenze della sede durante il lavoro quotidiano.',
      scope:'Solo le strutture assegnate. Nella demo: una sede.',
      can:['Inserire e aggiornare presenze e causali nei mesi aperti.', 'Usare pianificazione, variazioni di orario, sede, festivi ed eliminazione quando i parametri del centro lo consentono.', 'Consultare riepiloghi e copertura aggregata; inviare il mese al responsabile e riprendere la compilazione dopo una restituzione.'],
      boundary:'Non accede a fascicoli HR, documenti del personale, accordi economici, paghe o Comunicazioni. Non cambia parametri e non chiude il mese.',
      demo:'Apri Presenze, registra un turno consentito e controlla come cambiano i totali.'
    },
    viewer: {
      purpose:'Offre a direzione e referenti una vista di consultazione sull’andamento delle presenze.',
      scope:'Solo le strutture assegnate nell’installazione aziendale. Nella demo sono visibili tutte e tre le sedi.',
      can:['Consultare dashboard, presenze, riepiloghi, controlli e statistiche.', 'Confrontare i dati delle sedi autorizzate e scaricare i prospetti consentiti.', 'Consultare lo stato delle approvazioni e la copertura aggregata; usare le guide senza modificare i dati.'],
      boundary:'Non modifica dati e non accede a fascicoli HR, documenti del personale, accordi economici, paghe o Comunicazioni.',
      demo:'Apri Statistiche e cambia sede o filtri per confrontare i dati fittizi.'
    }
  };
  const copy = value => structuredClone(value);
  const now = () => new Date().toISOString();
  const uid = () => 'demo-' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const storage = {get(k){try{return sessionStorage.getItem(k)}catch{return null}},set(k,v){try{sessionStorage.setItem(k,v)}catch{}},remove(k){try{sessionStorage.removeItem(k)}catch{}}};
  let seed, db, role = storage.get(ROLE_STORE) || '', initialized = false, roleResolve;
  if (!ROLES[role]) role = '';
  const seedReady = nativeFetch('/demo_seed.json', {cache:'no-cache'}).then(r => {
    if (!r.ok) throw Error('Impossibile caricare i dati dimostrativi. Ricarica la pagina.');
    return r.json();
  }).then(data => {
    seed = data;
    try {const saved = JSON.parse(storage.get(STORE)); db = saved?.fixtureVersion === (seed.version || seed.month) ? saved.data : copy(seed)} catch {db = copy(seed)}
    db.periodOverrides ||= {};
    return data;
  });
  const persist = () => storage.set(STORE, JSON.stringify({fixtureVersion:seed.version || seed.month, data:db}));
  const tell = message => {if (typeof toast === 'function') toast(message); else console.info(message)};
  const fail = (message, status=400) => {const e = Error(message); e.status=status; throw e};
  const unavailable = () => fail('Disponibile nell’installazione completa. Questa demo non gestisce account reali, credenziali, backup o collegamenti a sistemi aziendali.');
  const hrAllowed = () => ['admin','hr','manager'].includes(role);
  const writeAllowed = () => ['admin','manager','operator'].includes(role);
  const managerAllowed = () => ['admin','manager'].includes(role);
  const centers = () => copy(['admin','hr','viewer'].includes(role) ? db.centers : db.centers.slice(0,1));
  const user = () => ({id:'demo-user-'+role,username:'demo.'+role,name:ROLES[role][0]+' · Demo',role,active:true,centers:centers().map(c=>c.id),mfa_enabled:false});
  const allowedCenter = cid => {if (!centers().some(c=>c.id===cid)) fail('Questo profilo dimostrativo non è assegnato al centro.',403); return db.snapshots[cid]};
  const requireHR = cid => {if (!hrAllowed()) fail('Pagina riservata a HR e responsabili.',403); if(cid && cid!=='all') allowedCenter(cid)};
  const selectedCenters = cid => {if(cid && cid!=='all') {allowedCenter(cid); return centers().filter(c=>c.id===cid)} return centers()};
  const response = (data,status=200) => new Response(JSON.stringify(data), {status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});

  function banner() {
    let bar=document.getElementById('demoBanner');
    if(!bar){bar=document.createElement('div');bar.id='demoBanner';document.body.prepend(bar)}
    bar.className='demo-banner';
    bar.innerHTML=`<div class="demo-banner-copy"><b>DEMO</b><span>Dati fittizi · modifiche solo in questa sessione</span><small>Non inserire dati personali reali.</small></div><div class="demo-banner-actions"><button id="demoShare" type="button">Condividi link</button>${role?'<button id="demoChangeRole" type="button">Cambia profilo</button><button id="demoReset" type="button">Ripristina demo</button>':''}<button id="demoInfo" type="button" aria-label="Informazioni sulla demo">ⓘ</button></div>`;
    document.body.classList.add('demo-mode');
    new ResizeObserver(entries=>document.documentElement.style.setProperty('--demo-banner-height',entries[0].target.getBoundingClientRect().height+'px')).observe(bar);
    bar.querySelector('#demoShare').onclick=async()=>{
      try{await navigator.clipboard.writeText(location.origin+location.pathname);tell('Link copiato. Chi lo apre può scegliere un profilo e provare la propria copia.')}catch{showInfo('Il link da condividere',`<input class="demo-share-link" readonly value="${escape(location.origin+location.pathname)}" aria-label="Link della demo"><p>Copia questo indirizzo e invialo alle persone che vuoi invitare.</p>`);document.querySelector('.demo-share-link').select()}
    };
    bar.querySelector('#demoInfo').onclick=()=>showInfo();
    if(role){
      bar.querySelector('#demoChangeRole').onclick=()=>{storage.remove(ROLE_STORE);location.reload()};
      bar.querySelector('#demoReset').onclick=()=>{if(confirm('Ripristinare i dati iniziali? Le modifiche fatte in questa scheda saranno eliminate.')){storage.remove(STORE);location.reload()}};
    }
  }
  function showInfo(title='Come funziona questa demo',body='') {
    let dialog=document.getElementById('demoInfoDialog');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='demoInfoDialog';document.body.append(dialog)}
    dialog.innerHTML=`<div class="demo-info"><h2>${escape(title)}</h2>${body||'<p>Puoi condividere il link con altre persone, senza creare account. Ogni visitatore ha una copia personale dei dati fittizi; le modifiche restano nella scheda del browser e non cambiano quelle degli altri visitatori.</p><p>Prova presenze, fascicoli e checklist. Per simulare un documento inviato dalla sede, apri un fascicolo, allega il documento dimostrativo e poi scegli <b>Cambia profilo → HR centrale</b>.</p><p>La demo mostra ottobre 2026. Nella rubrica strutture puoi modificare i recapiti fittizi. In Comunicazioni puoi preparare modelli, liste e bozze: gli invii sono soltanto simulati e non contattano alcun servizio di posta. Autenticazione a due fattori, gestione utenti, backup NAS e importazioni reali richiedono l’installazione completa. I file Excel di esempio rappresentano i dati iniziali; il CSV del registro riflette le modifiche della sessione.</p><p><b>Usa soltanto dati inventati.</b> La demo non è un archivio aziendale.</p>'}<button class="btn primary" id="demoInfoClose">Ho capito</button> <button class="btn" id="demoInfoWatch">Guarda la presentazione</button></div>`;
    dialog.querySelector('#demoInfoClose').onclick=()=>dialog.close();dialog.querySelector('#demoInfoWatch').onclick=showPresentation;dialog.showModal();
  }
  function showPresentation(){
    document.getElementById('demoInfoDialog')?.close();
    let dialog=document.getElementById('demoPresentationDialog');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='demoPresentationDialog';document.body.append(dialog)}
    const chapters=[{"id":"intro","title":"Un portale per sedi e HR","start":0,"end":10},{"id":"dashboard","title":"La visione del gruppo","start":10,"end":21},{"id":"presenze","title":"Presenze e pianificazione","start":21,"end":36},{"id":"fascicolo","title":"Fascicolo e struttura","start":36,"end":50},{"id":"documenti","title":"Verifica documentale HR","start":50,"end":65},{"id":"approvazioni","title":"Approvazione del mese","start":65,"end":80},{"id":"copertura","title":"Copertura e sostituzioni","start":80,"end":95},{"id":"comunicazioni","title":"Email e promemoria","start":95,"end":111},{"id":"paghe","title":"Preparazione dei dati paghe","start":111,"end":126},{"id":"uscite","title":"Uscite e restituzioni","start":126,"end":142},{"id":"guide","title":"Guide e prova della demo","start":142,"end":157}];
    const time=seconds=>Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
    dialog.innerHTML=`<div class="demo-info"><span class="demo-video-quality">PRESENTAZIONE · FULL HD</span><h2>Scopri NefroCenter in 2 minuti e 37 secondi</h2><p>Dal lavoro delle sedi alla verifica HR: una panoramica guidata, con voce sintetica italiana, sottotitoli e schermate della demo.</p><video id="demoPresentationVideo" controls playsinline preload="metadata" poster="/presentation/poster.jpg" aria-label="Presentazione di NefroCenter con voce narrante italiana"><source src="/presentation/presentazione-con-audio.mp4" type="video/mp4"><track kind="subtitles" src="/presentation/presentazione-con-audio.vtt" srclang="it" label="Italiano">Il browser non supporta il video. Usa il collegamento per scaricarlo.</video><details class="demo-video-chapters"><summary>Vai a un argomento · 11 capitoli</summary><nav aria-label="Capitoli della presentazione">${chapters.map(c=>`<button type="button" data-presentation-chapter="${c.start}"><span>${time(c.start)}</span>${escape(c.title)}</button>`).join('')}</nav></details><p class="demo-video-downloads"><a href="/presentation/presentazione-con-audio.mp4" download>Scarica con audio</a><a href="/presentation/presentazione.mp4" download>Scarica senza audio</a><a href="/presentation/trascrizione.txt" target="_blank" rel="noopener">Leggi la trascrizione</a><a href="/presentation/guida-ufficio-hr.pdf" target="_blank" rel="noopener">Presentazione HR · PDF</a></p><button class="btn primary" id="demoPresentationClose">Chiudi presentazione</button></div>`;
    const video=dialog.querySelector('video');
    dialog.querySelectorAll('[data-presentation-chapter]').forEach(button=>{button.onclick=()=>{
      const seek=()=>{video.currentTime=Number(button.dataset.presentationChapter);video.focus()};
      if(video.readyState>=1)seek();else{video.addEventListener('loadedmetadata',seek,{once:true});video.load()}
    }});
    dialog.onclose=()=>video.pause();
    dialog.querySelector('#demoPresentationClose').onclick=()=>dialog.close();dialog.showModal();
  }
  function chooseRole(){
    return new Promise(resolve=>{
      roleResolve=resolve;banner();
      const app=document.getElementById('app');app.classList.remove('app-shell');
      app.innerHTML=`<main class="demo-welcome"><section class="demo-intro"><img src="/assets/nefrocenter.png" alt="NefroCenter"><span class="demo-eyebrow">PERSONE E PRESENZE · DEMO INTERATTIVA</span><h1>Dalle sedi<br>all’ufficio HR.</h1><p>Un portale per registrare le presenze, gestire i fascicoli del personale e rendere disponibili a HR i documenti caricati dalle strutture. Riunisce approvazioni mensili, validazione documenti, promemoria, copertura dei turni, uscite e dotazioni, preparazione paghe e comunicazioni email.</p><div class="demo-intro-actions"><button class="btn primary demo-watch" id="demoWatch">Guarda la presentazione</button><a class="btn demo-watch" href="/presentation/guida-ufficio-hr.pdf" target="_blank" rel="noopener">Guida per l’ufficio HR · PDF</a></div><div class="demo-facts"><span>Ottobre 2026</span><span>Nessuna password richiesta</span><span>Dati interamente fittizi</span></div></section><section class="demo-role-heading"><h2>Scegli il ruolo da provare</h2><p>Le schede spiegano i permessi del gestionale operativo. Per presentarlo all’ufficio del personale, inizia da <b>HR centrale</b>. Puoi cambiare profilo in qualsiasi momento dal pulsante in alto.</p><p class="demo-role-flow"><b>Un esempio:</b> la sede compila il mese → il responsabile verifica → HR approva. Un documento caricato dalla sede può essere verificato o restituito per correzioni da HR.</p></section><section class="demo-roles" aria-label="Ruoli e permessi del gestionale">${['hr','manager','operator','viewer','admin'].map(key=>{const v=ROLES[key],h=ROLE_HELP[key];return `<article class="demo-role" data-role-description="${key}" aria-labelledby="demo-role-${key}"><span class="demo-role-tag">${key==='hr'?'CONSIGLIATO PER LA PRESENTAZIONE HR':escape(v[2])}</span><h3 id="demo-role-${key}">${escape(v[0])}</h3><p class="demo-role-purpose">${escape(h.purpose)}</p><p class="demo-role-scope"><b>Quali dati vede</b>${escape(h.scope)}</p><div class="demo-role-capabilities"><h4>Cosa può fare</h4><ul>${h.can.map(x=>`<li>${escape(x)}</li>`).join('')}</ul></div><p class="demo-role-boundary"><b>Limiti del ruolo</b>${escape(h.boundary)}</p><p class="demo-role-example"><b>Da provare nella demo</b>${escape(h.demo)}</p><button class="demo-role-start" data-demo-role="${key}" aria-label="Entra come ${escape(v[0])}">Prova ${escape(v[0])} <span aria-hidden="true">→</span></button></article>`}).join('')}</section><p class="demo-welcome-foot">Ogni persona prova una copia separata. Le modifiche restano nella scheda del browser; gli invii email sono simulati. Il gestionale aziendale usa invece un archivio centrale condiviso e account nominativi. <button id="demoWelcomeInfo">Come funziona la demo</button></p></main>`;
      app.querySelectorAll('[data-demo-role]').forEach(button=>button.onclick=()=>{
        role=button.dataset.demoRole;storage.set(ROLE_STORE,role);banner();
        app.innerHTML='<main class="demo-loading" role="status">Apertura del portale…</main>';
        roleResolve?.();roleResolve=null;
      });
      app.querySelector('#demoWelcomeInfo').onclick=()=>showInfo();
      app.querySelector('#demoWatch').onclick=showPresentation;
    });
  }

  function period(cid,month){
    const s=db.snapshots[cid];
    if(month===db.month) return s.period;
    const key=cid+'|'+month;
    return db.periodOverrides[key] ||= {...copy(s.period),month,closed:false,verified:false,agreements:{},note:'Periodo vuoto della demo'};
  }
  function minutes(e){
    if(e.kind!=='work'||!e.start||!e.end)return null;
    const clock=t=>Number(t.slice(0,2))*60+Number(t.slice(3,5));
    return clock(e.end)-clock(e.start)+(e.overnight?1440:0)-Number(e.pause||0);
  }
  const entryKey = e=>[e.person_id,e.day,e.slot].join('|');
  const entriesFor=(cid,month)=>db.snapshots[cid].entries.filter(e=>e.day.startsWith(month));
  function summary(cid,month){
    const snap=db.snapshots[cid],all=entriesFor(cid,month);
    return snap.people.map(p=>{
      const actual=all.filter(e=>e.person_id===p.id&&e.layer==='actual'),work=actual.filter(e=>e.kind==='work'),absence=actual.filter(e=>e.kind==='absence'),known=work.map(minutes).filter(x=>x!==null),planned=all.filter(e=>e.person_id===p.id&&e.layer==='planned');
      return {...copy(p),shifts:work.length,days:new Set(work.map(e=>e.day)).size,minutes:known.reduce((a,b)=>a+b,0),missing:work.length-known.length,external:work.filter(e=>e.work_site!==p.home_site).length,festive:work.filter(e=>e.holiday).length,absence_slots:absence.length,credit_minutes:absence.reduce((a,e)=>a+Number(e.credit_minutes||0),0),pending:planned.filter(e=>!actual.some(a=>a.day===e.day&&a.slot===e.slot)).length,causes:Object.fromEntries([...new Set(actual.map(e=>e.code))].map(code=>[code,actual.filter(e=>e.code===code).length]))};
    });
  }
  function snapshot(cid,month){
    const source=allowedCenter(cid),out=copy(source);out.user=user();out.centers=centers();out.period=copy(period(cid,month));if(db.v011){out.approval=approvalRead(cid,month);out.approval.frozen=out.approval.policy.enabled&&['submitted','manager_approved','hr_approved'].includes(out.approval.workflow.status);}out.entries=copy(entriesFor(cid,month));out.summary=summary(cid,month);out.alerts=[];
    if(!out.period.verified)out.alerts.push('Calendario e parametri del mese da verificare dal responsabile.');
    out.summary.forEach(r=>{if(r.missing)out.alerts.push(`${r.name}: ${r.missing} turni senza orari.`);if(r.pending)out.alerts.push(`${r.name}: ${r.pending} fasce pianificate da consuntivare.`)});
    if(month!==db.month)out.workload=[];
    if(role!=='admin')out.users=[];
    else out.users=Object.keys(ROLES).map(r=>({id:'demo-user-'+r,username:'demo.'+r,name:ROLES[r][0]+' · Demo',role:r,centers:['manager','operator'].includes(r)?db.centers.slice(0,1).map(c=>c.id):db.centers.map(c=>c.id),active:true,mfa_enabled:false}));
    if(!hrAllowed()){out.people.forEach(p=>{delete p.pay_override;delete p.note});out.summary.forEach(p=>{delete p.pay_override;delete p.note});delete out.period.agreements}
    const n=new Date(+month.slice(0,4),+month.slice(5),0).getDate();out.working_days=Array.from({length:n},(_,i)=>`${month}-${String(i+1).padStart(2,'0')}`).filter(d=>out.period.config.weekdays.includes((new Date(d+'T12:00:00').getDay()+6)%7)&&!out.period.config.holidays.includes(d)).length;
    return out;
  }
  function audit(cid,action){const s=db.snapshots[cid];s.center.revision++;const c=db.centers.find(c=>c.id===cid);if(c)c.revision=s.center.revision;s.audit.unshift({stamp:now(),username:'demo.'+role,action:action+' · sessione demo'});s.audit=s.audit.slice(0,60);persist()}
  function overview(month){return {centers:centers().map(c=>{const s=snapshot(c.id,month),sum=k=>s.summary.reduce((a,r)=>a+r[k],0);return {...c,people:s.people.filter(p=>p.active).length,minutes:sum('minutes'),shifts:sum('shifts'),missing:sum('missing'),pending:sum('pending'),closed:s.period.closed,recorded:s.entries.some(e=>e.layer==='actual'),last_update:s.audit[0]?.stamp||''}}),generated_at:now()}}

  function hrProgress(p){const open=p.tasks.filter(t=>!['done','na'].includes(t.status));return {done:p.tasks.length-open.length,total:p.tasks.length,overdue:open.filter(t=>t.due&&t.due<TODAY).length}}
  function deadlines(person,p,documents){
    const out=[],add=(label,date,section)=>{if(date)out.push({pid:person.id,name:person.name,label,date,section,late:date<TODAY})};
    [['identity_expiry','Documento di identità','anagrafica'],['end_date','Fine contratto','contratto'],['probation_end','Fine periodo di prova','contratto'],['registration_expiry','Iscrizione / abilitazione','qualifiche'],['work_permit_expiry','Titolo di soggiorno / lavoro','qualifiche'],['next_review','Verifica amministrativa','qualifiche']].forEach(([key,label,section])=>add(label,p.fields[key],section));
    p.tasks.filter(t=>!['done','na'].includes(t.status)).forEach(t=>add(t.label,t.due,'onboarding'));documents.forEach(d=>add(d.category+' · '+d.name,d.expiry,'documenti'));return out.sort((a,b)=>a.date.localeCompare(b.date));
  }
  function hrDetail(cid,pid){
    requireHR(cid);let detail=db.hrDetails[cid]?.[pid];
    if(!detail){const person=db.snapshots[cid].people.find(p=>p.id===pid);if(!person)fail('Dipendente non trovato.');detail={person:copy(person),profile:{version:0,fields:{},custom:{},tasks:[],stage:'incoming'},documents:[],settings:copy(db.hrLists[cid].settings),history:[]};db.hrDetails[cid]||={};db.hrDetails[cid][pid]=detail}
    detail.person=copy(db.snapshots[cid].people.find(p=>p.id===pid));detail.progress=hrProgress(detail.profile);detail.deadlines=deadlines(detail.person,detail.profile,detail.documents);detail.settings=copy(db.hrLists[cid].settings);detail.structure=structureRead(cid).structure;const result=copy(detail);if(db.v011)result.documents=result.documents.map(doc=>({...doc,review:reviewMetadata(doc)}));return result;
  }
  function structureRead(cid='all'){
    requireHR(cid==='all'?'':cid);
    const fields=copy(db.structures?.fields||[]),visible=new Set(centers().map(c=>c.id));
    const structures=copy(db.structures?.structures||[]).filter(s=>visible.has(s.cid));
    if(!cid||cid==='all')return {structures,fields};
    const structure=structures.find(s=>s.cid===cid);if(!structure)fail('Struttura non trovata.');return {structure,fields};
  }
  function structureSave(body){
    const current=structureRead(body.cid).structure;
    if(body.version!==current.version)fail('Scheda struttura aggiornata: riapri prima di salvare.');
    const values={};
    for(const f of db.structures.fields){
      const value=body.fields?.[f.key]??'';if(typeof value!=='string'||value.length>f.max_length)fail(f.label+': valore troppo lungo.');
      if(f.type!=='textarea'&&/[\x00-\x1f\x7f]/.test(value))fail(f.label+': caratteri non validi.');
      if(value.trim()&&f.type==='email'&&!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(value.trim()))fail(f.label+': indirizzo email non valido.');
      if(value.trim()&&f.type==='url'){try{const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw Error()}catch{fail('Sito web: usa un indirizzo http:// o https:// valido.')}}
      values[f.key]=value.trim();
    }
    const structure={...current,version:current.version+1,fields:values};db.structures.structures=db.structures.structures.map(s=>s.cid===body.cid?structure:s);audit(body.cid,'Rubrica struttura aggiornata');return {ok:true,structure:copy(structure)};
  }
  function communicationAccess(){if(!['admin','hr'].includes(role))fail('Comunicazioni riservate a HR centrale e amministratore.',403)}
  function communicationSettings(){
    const common={enabled:true,configured:true,batch_size:20,simulation:true,demo_simulated:true};
    return role==='admin'?{...copy(db.communications.settings),...common,password_configured:false}:common;
  }
  // This checksum detects stale demo previews only; the public demo has no security boundary.
  function communicationFingerprint(value){let hash=2166136261;for(const ch of JSON.stringify(value)){hash^=ch.charCodeAt(0);hash=Math.imul(hash,16777619)}return 'demo-'+(hash>>>0).toString(16)}
  function communicationRecord(kind,id){const row=db.communications[kind].find(x=>x.id===id);if(!row)fail('Modello o lista non trovato.');return row}
  function communicationText(value,label,maximum,multiline=false){
    if(typeof value!=='string'||!value.trim()||value.length>maximum||(!multiline&&/[\x00-\x1f\x7f]/.test(value)))fail(label+': testo non valido.');return value.trim();
  }
  function communicationEmail(value){
    if(typeof value!=='string'||value.length>254||! /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9.-]+\.[A-Za-z0-9-]+$/.test(value.trim())||/[\r\n]/.test(value))fail('Indirizzo email non valido.');
    const [local,domain]=value.trim().split('@');if(local.startsWith('.')||local.endsWith('.')||local.includes('..'))fail('Indirizzo email non valido.');return local+'@'+domain.toLowerCase();
  }
  function communicationContent(body){
    const subject=communicationText(body.subject,'Oggetto',300),text=communicationText(body.body,'Messaggio',20000,true),allowed=new Set(db.communications.variables.map(v=>v.id));
    for(const value of [subject,text]){const cleared=value.replace(/{{\s*([^{}]+?)\s*}}/g,(_,key)=>{if(!allowed.has(key.trim()))fail('Variabile non riconosciuta: usa quelle elencate nella guida.');return ''});if(cleared.includes('{{')||cleared.includes('}}'))fail('Variabile non riconosciuta.');}
    return {subject,body:text};
  }
  function communicationSave(kind,body){
    communicationAccess();const old=body.id?communicationRecord(kind,body.id):null;if(body.version!==(old?.version||0))fail('La versione è cambiata. Ricarica prima di salvare.');
    const row={id:old?.id||uid(),version:(old?.version||0)+1,name:communicationText(body.name,'Nome',120)};
    if(kind==='templates')Object.assign(row,communicationContent(body));
    else {
      const choice=(key,allowed)=>{const a=body[key]||[];if(!Array.isArray(a)||a.some(x=>typeof x!=='string'||allowed&&!allowed.includes(x)))fail('Filtro '+key+' non valido.');return [...new Set(a)].sort()};
      Object.assign(row,{cids:choice('cids',centers().map(x=>x.id)),roles:choice('roles',db.communications.roles),stages:choice('stages',db.communications.stages),email_field:body.email_field||'company_email',recipient_type:body.recipient_type||'employees',structure_field:body.structure_field||'email',exclude_emails:[...new Set(choice('exclude_emails').map(e=>communicationEmail(e).toLowerCase()))]});
      if(!['company_email','email'].includes(row.email_field)||!['employees','structures'].includes(row.recipient_type)||!['email','hr_email','admin_email'].includes(row.structure_field))fail('Tipo destinatario o campo email non valido.');
      if(row.recipient_type==='structures'&&(row.roles.length||row.stages.length))fail('I filtri ruolo e stato si applicano solo ai dipendenti.');
    }
    if(old)db.communications[kind]=db.communications[kind].map(x=>x.id===old.id?row:x);else db.communications[kind].push(row);persist();return copy(row);
  }
  function communicationPreview(body){
    communicationAccess();const template=communicationRecord('templates',body.template_id),list=communicationRecord('lists',body.list_id),content=communicationContent({subject:body.subject??template.subject,body:body.body??template.body});
    const recipients=[],warnings=[],seen=new Set(),counts={selected:0,valid:0,missing:0,invalid:0,duplicates:0,excluded:0},excluded=new Set(list.exclude_emails);
    const warn=(code,message,severity='warning')=>warnings.push({code,message,severity});
    for(const center of centers().filter(c=>!list.cids.length||list.cids.includes(c.id))){
      const sf=structureRead(center.id).structure.fields,base={struttura:center.name,codice_struttura:center.code,ragione_sociale:sf.legal_name,email_hr:sf.hr_email,email_struttura:sf.email,email_amministrazione:sf.admin_email,telefono_struttura:sf.phone,indirizzo_struttura:sf.address,referente_struttura:sf.contact_name};
      const audience=[];
      if(list.recipient_type==='structures')audience.push({cid:center.id,pid:'',name:center.name,email:sf[list.structure_field],variables:{...base,nome:sf.contact_name||center.name}});
      else for(const person of [...db.snapshots[center.id].people].sort((a,b)=>a.name.localeCompare(b.name))){
        const p=hrDetail(center.id,person.id).profile,f=p.fields,stage=p.version?p.stage:person.active?'active':'ended';
        if(list.roles.length&&!list.roles.includes(person.role)||list.stages.length&&!list.stages.includes(stage))continue;
        audience.push({cid:center.id,pid:person.id,name:person.name,email:f[list.email_field],variables:{...base,nome:person.name,nome_battesimo:f.first_name,cognome:f.last_name,matricola:person.registration,ruolo:person.role,data_ingresso:f.start_date}});
      }
      for(const row of audience){
        counts.selected++;const description=row.name+' · '+center.name;
        if(!row.email){counts.missing++;warn('missing_email',description+': email mancante; escluso.');continue}
        try{row.email=communicationEmail(row.email)}catch{counts.invalid++;warn('invalid_email',description+': email non valida; escluso.');continue}
        const key=row.email.toLowerCase();if(excluded.has(key)){counts.excluded++;continue}if(seen.has(key)){counts.duplicates++;warn('duplicate_email',description+': indirizzo già presente; resta il primo destinatario mostrato.');continue}seen.add(key);
        const variables={...row.variables,email_destinatario:row.email},missing=new Set();delete row.variables;
        const render=value=>value.replace(/{{\s*([^{}]+?)\s*}}/g,(_,key)=>{const value=variables[key.trim()];if(!value)missing.add(key.trim());return String(value||'')});
        row.subject=render(content.subject);row.body=render(content.body);
        if(missing.size)warn('missing_variable',description+': mancano i valori per '+[...missing].sort().join(', ')+'.','error');
        if(/[\x00-\x1f\x7f]/.test(row.subject))warn('invalid_content',description+': oggetto personalizzato non valido.','error');recipients.push(row);
      }
    }
    counts.valid=recipients.length;if(!recipients.length)warn('empty_audience','Nessun destinatario valido nella lista.','error');
    const snapshot={template_id:template.id,template_version:template.version,list_id:list.id,list_version:list.version,...content,recipients,warnings,counts};
    return {...snapshot,fingerprint:communicationFingerprint(snapshot),can_create:!warnings.some(w=>w.severity==='error')};
  }
  function communicationCampaign(id,detail=true){
    communicationAccess();const c=(db.communicationCampaigns||[]).find(x=>x.id===id);if(!c)fail('Campagna non trovata.');
    const counts={pending:0,sending:0,accepted:0,failed:0,uncertain:0,simulated:0,total:c.recipients.length};for(const r of c.recipients)counts[r.status]++;
    const result={id:c.id,name:c.name,created_at:c.created_at,created_by:c.created_by,status:counts.pending?(counts.simulated?'partial':'draft'):'simulated',counts,remaining:counts.pending,can_send:!!counts.pending,can_retry_failed:!!counts.failed,template_id:c.template_id,list_id:c.list_id,fingerprint:c.fingerprint,confirmation_token:communicationFingerprint({id:c.id,recipients:c.recipients.map(r=>({id:r.id,status:r.status,attempts:r.attempts.length}))}),simulation:true,demo_simulated:true};
    for(const [mode,status] of [['send_plan','pending'],['retry_plan','failed']]){const ids=c.recipients.filter(r=>r.status===status).slice(0,20).map(r=>r.id);result[mode]={recipient_ids:ids,count:ids.length,token:result.confirmation_token}}result.can_reconcile=false;
    if(detail)Object.assign(result,{subject:c.subject,body:c.body,warnings:copy(c.warnings),recipients:copy(c.recipients)});return result;
  }
  function communicationCreate(body){
    const p=communicationPreview(body);if(body.fingerprint!==p.fingerprint)fail('Destinatari o contenuti cambiati. Ripeti l’anteprima.');if(!p.can_create)fail('Correggi gli errori dell’anteprima.');
    const c={...p,id:uid(),name:communicationText(body.name||p.subject,'Nome campagna',300),created_at:now(),created_by:'demo.'+role,recipients:p.recipients.map(r=>({...r,id:uid(),status:'pending',error:'',attempts:[]}))};db.communicationCampaigns||=[];db.communicationCampaigns.unshift(c);persist();return communicationCampaign(c.id);
  }
  function communicationSend(body){
    const current=communicationCampaign(body.id);if(body.confirm!==true)fail('Conferma esplicitamente prima della simulazione.');
    if(body.confirmation_token!==current.confirmation_token)fail('La bozza è cambiata: riapri il riepilogo prima di confermare.');
    const c=db.communicationCampaigns.find(x=>x.id===body.id),pending=c.recipients.filter(r=>r.status===(body.retry_failed?'failed':'pending')).slice(0,20);if(!pending.length)fail('Nessun destinatario disponibile. Gli esiti incerti non vengono reinviati.');
    for(const r of pending){r.status='simulated';r.error='';r.attempts.push({number:r.attempts.length+1,status:'simulated',started_at:now(),finished_at:now(),error:'',message_id:'demo-'+uid()})}persist();return communicationCampaign(c.id);
  }
  function communicationOverview(){communicationAccess();return {...copy(db.communications),settings:communicationSettings(),centers:centers(),campaigns:(db.communicationCampaigns||[]).map(c=>communicationCampaign(c.id,false))}}
  function hrListing(cid){
    requireHR(cid);const employees=[],due=[];
    db.snapshots[cid].people.forEach(person=>{const d=hrDetail(cid,person.id),p=d.profile;employees.push({id:person.id,name:person.name,role:person.role,registration:person.registration,active:person.active,stage:p.stage,department:p.fields.department||'',start:p.fields.start_date||'',version:p.version,...d.progress});due.push(...d.deadlines.filter(d=>d.date<='2026-11-18'))});
    return {employees:employees.sort((a,b)=>a.name.localeCompare(b.name)),deadlines:due.sort((a,b)=>a.date.localeCompare(b.date)),settings:copy(db.hrLists[cid].settings)};
  }
  function qReview(value){return ['received','needs_correction','verified','expired'].includes(value)?value:'all'}
  function documents(query){
    requireHR(query.get('cid'));const rows=[];
    selectedCenters(query.get('cid')).forEach(ct=>Object.entries(db.hrDetails[ct.id]||{}).forEach(([pid,d])=>{const p=db.snapshots[ct.id].people.find(p=>p.id===pid);if(!p)return;d.documents.forEach(doc=>rows.push({...copy(doc),review:reviewMetadata(doc),cid:ct.id,pid,person:p.name,registration:p.registration,center:ct.name,late:!!doc.expiry&&doc.expiry<TODAY}))}));
    const categories=[...new Set(rows.map(d=>d.category))].sort(),q=(query.get('person')||'').toLocaleLowerCase(),expiry=query.get('expiry')||'all',category=query.get('category');
    const filtered=rows.filter(d=>(!q||(d.person+' '+d.registration).toLocaleLowerCase().includes(q))&&(!category||d.category===category)&&({all:true,expired:!!d.expiry&&d.expiry<TODAY,soon:d.expiry>=TODAY&&d.expiry<='2026-11-18',dated:!!d.expiry,none:!d.expiry}[expiry]));
    const review=qReview(query.get('review')),reviewed=filtered.filter(d=>review==='all'||(review==='expired'?d.review.expired:d.review.status===review));return {centers:centers(),categories,documents:reviewed,total:reviewed.length,generated_at:now()};
  }
  function tasks(query){
    const month=query.get('month')||db.month,items=[];
    const add=(ct,category,title,pid='',day='',section='',detail='',priority='normal')=>items.push({id:String(items.length+1),cid:ct.id,center:ct.name,category,title,pid,day,month,section,detail,priority});
    selectedCenters(query.get('cid')).forEach(ct=>{
      const s=snapshot(ct.id,month),actual=new Set(s.entries.filter(e=>e.layer==='actual').map(entryKey));
      s.entries.forEach(e=>{const p=s.people.find(p=>p.id===e.person_id);if(!p)return;const detail=`${p.name} · ${e.day} · ${e.slot}`;if(e.layer==='actual'&&e.kind==='work'&&minutes(e)===null)add(ct,'orari','Completa gli orari del turno',p.id,e.day,'',detail);else if(e.layer==='planned'&&e.kind==='work'&&e.day<=TODAY&&!actual.has(entryKey(e)))add(ct,'consuntivi','Registra il consuntivo',p.id,e.day,'',detail)});
      if(!s.period.verified)add(ct,'calendario','Verifica calendario e parametri del mese','','','controlli',month+' · verifica riservata al responsabile');
      if(s.entries.length&&!s.period.closed&&month<TODAY.slice(0,7))add(ct,'chiusure','Controlla il mese ancora aperto','','','riepilogo',month);
      if(hrAllowed()){
        const listing=hrListing(ct.id),active=new Set(listing.employees.filter(p=>p.active&&p.stage!=='ended').map(p=>p.id));
        listing.employees.filter(p=>active.has(p.id)).forEach(p=>{if(!p.version)add(ct,'fascicoli','Compila il fascicolo',p.id,'','anagrafica',p.name);else if(p.total>p.done)add(ct,'onboarding','Completa le attività di onboarding',p.id,'','onboarding',`${p.name} · ${p.total-p.done} attività aperte`,p.overdue?'urgent':'normal')});
        listing.deadlines.filter(d=>active.has(d.pid)).forEach(d=>add(ct,'scadenze',d.label,d.pid,d.date,d.section,d.name,d.late?'urgent':'normal'));
      }
    });
    items.sort((a,b)=>(a.priority==='urgent'?-1:1)-(b.priority==='urgent'?-1:1)||(a.day||'9999').localeCompare(b.day||'9999'));
    return {items,counts:Object.fromEntries([...new Set(items.map(x=>x.category))].map(k=>[k,items.filter(x=>x.category===k).length])),total:items.length,urgent:items.filter(x=>x.priority==='urgent').length,centers:centers(),month,as_of:TODAY,generated_at:now(),hr_visible:hrAllowed()};
  }

  function monthsBetween(first,last){
    if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(first)||!/^\d{4}-(0[1-9]|1[0-2])$/.test(last))fail('Seleziona mesi validi.');
    const a=+first.slice(0,4)*12+ +first.slice(5)-1,b=+last.slice(0,4)*12+ +last.slice(5)-1;
    if(b<a||b-a>=24)fail('Seleziona un intervallo ordinato di massimo 24 mesi.');
    return Array.from({length:b-a+1},(_,i)=>`${Math.floor((a+i)/12)}-${String((a+i)%12+1).padStart(2,'0')}`);
  }
  function effectivePerson(cid,pid,day){
    const p=copy(db.snapshots[cid].people.find(p=>p.id===pid));
    for(const detail of Object.values(db.workforceDetails||{})){const a=detail.groups?.flatMap(g=>g.assignments).find(a=>a.cid===cid&&a.pid===pid);if(a){p.global_id=a.global_id||detail.groups[0].global_id;const c=a.contracts?.find(c=>c.effective_from<=day&&(!c.effective_to||c.effective_to>=day));if(c){Object.assign(p,c.data);p.effective_contract=c}break}}
    return p;
  }
  function statsBucket(){return {known_minutes:0,work_shifts:0,missing_hours:0,absence_slots:0,rest_slots:0,actual_records:0,planned_work:0,pending_work:0,external_shifts:0,festive_shifts:0,people:new Set(),workdays:new Set(),absenceDays:new Set()}}
  function statsAdd(b,e,c,actual){
    const p=c.id+'|'+e.person_id;b.people.add(p);
    if(e.layer==='planned'){if(e.kind==='work'){b.planned_work++;if(!actual.has(entryKey(e)))b.pending_work++}return}
    b.actual_records++;const day=p+'|'+e.day;
    if(e.kind==='work'){b.work_shifts++;const m=minutes(e);if(m===null)b.missing_hours++;else b.known_minutes+=m;b.workdays.add(day);b.external_shifts+=Number(e.work_site!==c.name);b.festive_shifts+=Number(!!e.holiday)}else if(e.kind==='absence'){b.absence_slots++;b.absenceDays.add(day)}else if(e.kind==='rest')b.rest_slots++;
  }
  function statsFinish(b){const {people,workdays,absenceDays,...s}=b;const known=s.work_shifts-s.missing_hours;return {...s,people_count:people.size,work_days:workdays.size,absence_days:absenceDays.size,known_work_shifts:known,hours_completeness:s.work_shifts?Math.round(1000*known/s.work_shifts)/10:null,absence_share:s.work_shifts+s.absence_slots?Math.round(1000*s.absence_slots/(s.work_shifts+s.absence_slots))/10:null,minutes:s.actual_records&&(!s.work_shifts||known)?s.known_minutes:null}}
  function statistics(query){
    const first=query.get('from')||db.month,last=query.get('to')||db.month,ctList=selectedCenters(query.get('cid')),months=monthsBetween(first,last),total=statsBucket(),monthly=Object.fromEntries(months.map(m=>[m,statsBucket()])),byRole={},byCause={},byPerson=[],byCenter=[],roles=new Set(),peopleOptions=[],centerMonths=[];
    const quality={closed_months:0,verified_months:0,center_months:ctList.length*months.length,empty_months:0,unmatched_records:0};
    const hr=hrAllowed()?{active_people:0,missing_profiles:0,onboarding_open:0,tasks_open:0,tasks_overdue:0,deadlines_overdue:0,deadlines_next30:0,as_of:TODAY}:null;
    ctList.forEach(ct=>{
      const s=db.snapshots[ct.id],bucket=statsBucket(),personBuckets={};
      s.people.forEach(p=>{roles.add(p.role);peopleOptions.push({id:p.id,name:p.name,role:p.role,cid:ct.id})});
      const entries=s.entries.filter(e=>e.day.slice(0,7)>=first&&e.day.slice(0,7)<=last),actual=new Set(entries.filter(e=>e.layer==='actual').map(entryKey));
      entries.forEach(e=>{const person=effectivePerson(ct.id,e.person_id,e.day);if(!person){quality.unmatched_records++;return}roles.add(person.role);if(query.get('role')&&person.role!==query.get('role')||query.get('person_id')&&e.person_id!==query.get('person_id'))return;
        const pr=personBuckets[e.person_id]||=( {person,bucket:statsBucket()} );
        const bs=[total,bucket,monthly[e.day.slice(0,7)],byRole[person.role]||=statsBucket(),pr.bucket];if(e.kind==='absence')bs.push(byCause[e.code]||={...statsBucket(),label:e.code_label});bs.forEach(b=>statsAdd(b,e,ct,actual));
      });
      months.forEach(month=>{const p=period(ct.id,month),has=entries.some(e=>e.day.startsWith(month)&&e.layer==='actual');quality.closed_months+=Number(p.closed);quality.verified_months+=Number(p.verified);quality.empty_months+=Number(!has);centerMonths.push({cid:ct.id,name:ct.name,month,closed:p.closed,verified:p.verified,has_records:has})});
      byCenter.push({cid:ct.id,name:ct.name,code:ct.code,...statsFinish(bucket)});
      Object.entries(personBuckets).forEach(([id,p])=>byPerson.push({id,cid:ct.id,center:ct.name,name:p.person.name,role:p.person.role,...statsFinish(p.bucket)}));
      if(hr){const list=hrListing(ct.id);list.employees.filter(p=>p.active&&(!query.get('role')||p.role===query.get('role'))&&(!query.get('person_id')||p.id===query.get('person_id'))).forEach(p=>{hr.active_people++;hr.missing_profiles+=Number(!p.version);hr.onboarding_open+=Number(p.total>p.done);hr.tasks_open+=p.total-p.done;hr.tasks_overdue+=p.overdue;const d=hrDetail(ct.id,p.id);hr.deadlines_overdue+=d.deadlines.filter(x=>x.date<TODAY).length;hr.deadlines_next30+=d.deadlines.filter(x=>x.date>=TODAY&&x.date<='2026-11-18').length})}
    });
    return {filters:{first,last,cid:query.get('cid')||'all',role:query.get('role')||'',person_id:query.get('person_id')||''},options:{roles:[...roles].sort(),people:peopleOptions},centers:ctList,summary:statsFinish(total),monthly:months.map(month=>({month,...statsFinish(monthly[month])})),by_center:byCenter,by_role:Object.entries(byRole).map(([role,b])=>({role,...statsFinish(b)})),by_cause:Object.entries(byCause).map(([code,b])=>({code,label:b.label,...statsFinish(b)})),by_person:byPerson,center_months:centerMonths,quality,hr,export_allowed:role!=='operator'||ctList.every(c=>db.snapshots[c.id].center.config.operator_export),generated_at:now(),has_records:byPerson.length>0,role_history_note:'Il ruolo segue le decorrenze dimostrative disponibili.'};
  }

  function workforce(query){
    requireHR();const gid=query.get('gid'),source=gid?db.workforceDetails[gid]:db.workforce;if(!source)fail('Identità non trovata.');const data=copy(source),ids=new Set(centers().map(c=>c.id)),on=query.get('on')||TODAY;
    data.groups=data.groups.map(g=>({...g,assignments:g.assignments.filter(a=>ids.has(a.cid)).map(a=>({...a,person:effectivePerson(a.cid,a.pid,on),documents:copy(db.hrDetails[a.cid]?.[a.pid]?.documents||a.documents||[])}))})).filter(g=>g.assignments.length);data.scope=['admin','hr'].includes(role)?'gruppo':'centri assegnati';return data;
  }
  function payrollPreview(cid,first,last){
    requireHR(cid);monthsBetween(first,last);const cfg=db.payrollConfigs[cid],s=db.snapshots[cid],config=cfg.config,issues=[],rows=[],all=s.entries.filter(e=>e.layer==='actual'&&e.day.slice(0,7)>=first&&e.day.slice(0,7)<=last),people=new Set();let known=0;
    const add=(message,e,severity='error')=>issues.push({severity,message,day:e?.day||'',person_id:e?.person_id||''});
    if(config.status!=='confirmed')add('Modèle en bozza: il tracciato deve essere verificato con il consulente.'.replace('Modèle','Modello'));
    all.forEach(e=>{const p=effectivePerson(cid,e.person_id,e.day),m=minutes(e),registration=config.registrations[p.id]||p.registration,code=config.causes[e.code]||'';people.add(p.id);if(m!==null)known+=m;if(!registration)add('Matricola mancante per '+p.name,e);if(!code)add('Associa la causale '+e.code+' al codice del consulente.',e);if(e.kind==='work'&&m===null)add('Orari mancanti per '+p.name,e);if(!p.effective_contract)add('Decorrenza contrattuale non disponibile: '+p.name,e,'warning');
      const row={template_version:cfg.version,center_code:s.center.code,registration,person_name:p.name,global_id:p.global_id||'',day:e.day,slot:e.slot,payroll_code:code,source_code:e.code,kind:e.kind,start:e.start,end:e.end,overnight:Number(e.overnight),pause_minutes:e.pause,worked_minutes:m,worked_hours:m===null?null:Math.round(m/60*100)/100,work_shifts:Number(e.kind==='work'),absence_slots:Number(e.kind==='absence'),absence_days:e.kind==='absence'?Number(all.find(x=>x.person_id===e.person_id&&x.day===e.day&&x.code===e.code)?.id===e.id):0,credited_minutes:e.credit_minutes||0,holiday:Number(e.holiday),work_site:e.work_site,role:p.role,weekly_hours:p.weekly_hours??null,part_time_percent:p.part_time_percent??null,contract_type:p.contract_type||'',ccnl:p.ccnl||'',level:p.level||'',source_id:e.id};
      config.columns.forEach(c=>{if(['weekly_hours','part_time_percent'].includes(c.field)&&row[c.field]===null)add('Dato contrattuale mancante per '+p.name+': '+c.label,e)});rows.push(config.columns.map(c=>c.field==='day'&&config.connector?.date_format==='DD/MM/YYYY'?row.day.split('-').reverse().join('/'):row[c.field]??null));
    });
    if(!all.length)add('Nessun consuntivo nel periodo.');
    s.entries.filter(e=>e.layer==='planned'&&e.kind==='work'&&e.day.slice(0,7)>=first&&e.day.slice(0,7)<=last&&!all.some(a=>entryKey(a)===entryKey(e))).forEach(e=>add('Pianificazione senza consuntivo.',e));
    if(monthsBetween(first,last).some(m=>!period(cid,m).closed))add('Il periodo contiene mesi aperti.',null,'warning');
    if(db.v011)for(const m of monthsBetween(first,last)){const approval=approvalRead(cid,m);if(approval.policy.enabled&&(!approval.legacy_closed&&(approval.workflow.status!=='hr_approved'||approval.stale)))add('Mese '+m+': approvazione finale HR richiesta.');}
    const errors=issues.filter(i=>i.severity==='error').length;
    return {connector:copy(config.connector||connectorDefault()),connector_status:config.connector?.mode==='consultant'?(config.status==='confirmed'?'verified':'draft'):'generic',format_settings:{delimiter:config.delimiter,decimal_separator:config.decimal_separator,date_format:config.connector?.date_format||'YYYY-MM-DD',encoding:config.connector?.encoding||'utf-8-sig'},cid,center_code:s.center.code,first,last,version:cfg.version,template_name:config.name,columns:copy(config.columns),rows:rows.slice(0,100),issues:issues.slice(0,200),summary:{rows:rows.length,people:people.size,known_minutes:known,blocking_issues:errors,warnings:issues.length-errors},shown_rows:Math.min(rows.length,100),shown_issues:Math.min(issues.length,200),can_download:!errors,fingerprint:[cfg.version,s.center.revision,first,last].join('|'),_rows:rows};
  }

  function saveEntry(body){
    const s=allowedCenter(body.cid),p=period(body.cid,body.month),raw=body.entry,cfg=p.config;
    if(!writeAllowed())fail('Questo profilo può consultare le presenze, senza modificarle.',403);
    if(p.closed)fail('Mese chiuso: il responsabile deve riaprirlo.');
    if(body.revision!==s.center.revision)fail('I dati sono cambiati. Ricarica prima di salvare.');
    const person=s.people.find(x=>x.id===raw.person_id&&x.active),slot=cfg.slots.find(x=>x.id===raw.slot&&x.active),code=cfg.codes.find(x=>x.id===raw.code&&x.active),old=s.entries.find(x=>x.id===raw.id);
    if(!person||!slot||!code)fail('Persona, fascia o causale non valida.');
    if(!raw.day.startsWith(body.month+'-')||!/^\d{4}-\d{2}-\d{2}$/.test(raw.day))fail('Data fuori dal mese selezionato.');
    if(!['actual','planned'].includes(raw.layer))fail('Registro non valido.');
    if(code.allowed_slots.length&&!code.allowed_slots.includes(slot.id))fail('Causale non autorizzata per questa fascia.');
    if(role==='operator'&&raw.layer==='planned'&&!cfg.operator_planned)fail('Pianificazione riservata al responsabile.',403);
    if(raw.id&&!old)fail('Registrazione non trovata.');
    if(old&&['day','slot','person_id','layer'].some(k=>old[k]!==raw[k]))fail('Per spostare una registrazione, eliminala e reinseriscila.');
    const expected=old?.kind==='work'?old:slot;
    const e={id:old?.id||uid(),person_id:person.id,day:raw.day,slot:slot.id,code:code.id,kind:code.kind,code_label:code.label,layer:raw.layer,start:'',end:'',pause:0,overnight:false,work_site:old?.work_site||s.center.name,holiday:old?.holiday??cfg.holidays.includes(raw.day),note:String(raw.note||'').slice(0,2000),credit_minutes:code.credit_minutes,updated_by:'demo.'+role,updated_at:now(),config_version:p.version};
    if(code.kind==='work')for(const k of ['start','end','pause','overnight'])e[k]=role==='operator'&&!cfg.operator_edit_times?expected[k]:raw[k]??slot[k];
    if(managerAllowed()||cfg.operator_choose_site)e.work_site=raw.work_site||e.work_site;
    if(managerAllowed()||cfg.operator_mark_holiday)e.holiday=raw.holiday??e.holiday;
    if(![s.center.name,...cfg.sites].includes(e.work_site))fail('Sede non autorizzata.');
    if(!!e.start!==!!e.end||[e.start,e.end].some(t=>t&&!/^([01]\d|2[0-3]):[0-5]\d$/.test(t)))fail('Indica entrambi gli orari nel formato HH:MM.');
    if(e.kind==='work'&&e.start&&(minutes(e)<=0||minutes(e)+Number(e.pause)>1440)||!Number.isInteger(Number(e.pause))||e.pause<0||!e.start&&e.pause)fail('Durata o pausa non valida.');
    const span=x=>{if(minutes(x)===null)return null;const a=new Date(x.day+'T'+x.start).getTime(),b=new Date(x.day+'T'+x.end).getTime()+(x.overnight?86400000:0);return[a,b]};
    for(const other of s.entries){if(other.id===e.id||other.person_id!==e.person_id||other.layer!==e.layer)continue;if(entryKey(other)===entryKey(e))fail('La fascia è già compilata. Aprila per modificarla.');const a=span(e),b=span(other);if(a&&b&&a[0]<b[1]&&b[0]<a[1])fail('Sovrapposizione con il '+other.day)}
    if(old)s.entries[s.entries.indexOf(old)]=e;else s.entries.push(e);audit(body.cid,'Presenza salvata');return {ok:true,warnings:[]};
  }
  function saveHR(body){
    requireHR(body.cid);const s=db.snapshots[body.cid],pid=body.pid||uid();
    if(body.revision!==s.center.revision)fail('I dati del centro sono cambiati. Ricarica prima di salvare.');
    let existing=db.hrDetails[body.cid]?.[pid];
    if(body.pid&&!existing)hrDetail(body.cid,pid);existing=db.hrDetails[body.cid]?.[pid];
    if((existing?.profile.version||0)!==body.version)fail('Fascicolo modificato. Ricarica prima di salvare.');
    if(!String(body.name||'').trim())fail('Nome obbligatorio.');
    if(!s.center.config.roles.includes(body.role))fail('Ruolo non valido.');
    if(s.people.some(p=>p.id!==pid&&p.registration&&p.registration===body.registration))fail('Matricola già presente nel centro.');
    const fields=copy(body.fields||{}),settings=db.hrLists[body.cid].settings;
    for(const [key,max] of [['weekly_hours',168],['part_time_percent',100]])if(fields[key]&&(!/^\d+(?:[.,]\d{1,2})?$/.test(fields[key])||Number(String(fields[key]).replace(',','.'))<=0||Number(String(fields[key]).replace(',','.'))>max))fail('Ore o percentuale non valide.');
    if(fields.start_date&&fields.end_date&&fields.end_date<fields.start_date)fail('Fine contratto precedente all’ingresso.');
    const old=s.people.find(p=>p.id===pid),person={...(old||{id:pid,home_site:s.center.name,note:'',pay_override:null}),name:body.name.trim(),registration:body.registration||'',role:body.role,active:!!body.active,contract:fields.contract_type||''};
    if(old)s.people[s.people.indexOf(old)]=person;else s.people.push(person);
    const initialTasks=(settings.tasks||[]).map(t=>({...copy(t),status:'todo',note:'',due:fields.start_date?new Date(new Date(fields.start_date+'T12:00:00Z').getTime()+Number(t.offset||0)*86400000).toISOString().slice(0,10):''}));
    const profile={version:body.version+1,fields,custom:copy(body.custom||{}),tasks:existing?.profile.version?existing.profile.tasks:initialTasks,stage:body.stage||'incoming',updated_at:now(),updated_by:'demo.'+role};
    const d={person,profile,documents:existing?.documents||[],history:[{version:profile.version,stamp:now(),actor:'demo.'+role},...(existing?.history||[])],settings:copy(settings)};db.hrDetails[body.cid]||={};db.hrDetails[body.cid][pid]=d;audit(body.cid,'Fascicolo aggiornato');return {ok:true,pid};
  }

  async function sampleDocument(){const r=await nativeFetch('/samples/contratto-demo.pdf');if(!r.ok)fail('Documento dimostrativo non disponibile.');const bytes=new Uint8Array(await r.arrayBuffer());let raw='';bytes.forEach(b=>raw+=String.fromCharCode(b));return {content:btoa(raw),name:'Documento-dimostrativo.pdf',size:bytes.length}}
  function csv(rows,delimiter=';'){return '\uFEFF'+rows.map(row=>row.map(v=>{const value=String(v??'');const safe=/^[=+@\-\t\r]/.test(value)?"'"+value:value;return '"'+safe.replaceAll('"','""')+'"'}).join(delimiter)).join('\r\n')}
  const csvResponse=text=>new Response(text,{headers:{'Content-Type':'text/csv; charset=utf-8'}});

  // Browser-local simulation of the 0.11 workflows. It never opens SMTP or a company system.
  const reviewLabels={received:'Ricevuto',needs_correction:'Da correggere',verified:'Verificato'};
  const departureKinds={termination:'Cessazione',transfer:'Trasferimento'};
  const assetKinds={badge:'Badge',keys:'Chiavi',device:'Dispositivo',other:'Altra dotazione'};
  const departureTaskLabels={badge:'Restituzione badge',keys:'Restituzione chiavi',devices:'Restituzione dispositivi e altre dotazioni',documents:'Consegna e verifica dei documenti',access:'Conferma con IT della gestione degli accessi'};
  const departureNotice='La chiusura del percorso non cambia automaticamente rapporto, sede o stato del dipendente e non disattiva account esterni. Aggiorna fascicolo e accessi nelle rispettive procedure autorizzate.';
  const reminderTopics={contract:'Contratti e periodo di prova',document:'Documenti',qualification:'Qualifiche e verifiche',onboarding:'Attività di onboarding',attendance:'Presenze del mese precedente'};
  const connectorDefault=()=>({mode:'generic',provider:'',format_name:'',format_version:'',specification_reference:'',expected_columns:[],date_format:'YYYY-MM-DD',encoding:'utf-8-sig'});
  const checkVersion=(body,item)=>{if(!Number.isInteger(body.version)||body.version!==(item?.version||0))fail('I dati sono cambiati. Ricarica prima di salvare.')};
  const requiredNote=(value,label='Motivazione')=>{if(typeof value!=='string'||value.trim().length<8||value.length>2000)fail(label+': indica almeno 8 caratteri.');return value.trim()};
  const validDay=value=>{if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||Number.isNaN(Date.parse(value+'T12:00:00Z'))||new Date(value+'T12:00:00Z').toISOString().slice(0,10)!==value)fail('Data non valida.');return value};
  const getPerson=(cid,pid)=>{const p=allowedCenter(cid).people.find(p=>p.id===pid);if(!p)fail('Dipendente non trovato.');return p};
  const stampHistory=(item,action)=>{item.history||=[];item.history.unshift({version:item.version,stamp:now(),actor:user().username,action});item.updated_at=now()};
  function initV011(){
    db.v011 ||= {policies:{},approvals:{},reviews:{},cases:[],assets:[],requirements:{},availability:[],proposals:[],reminders:{version:0,enabled:false,centers:[],topics:Object.keys(reminderTopics),offsets:[30,15,7,0],recipient_mode:'structure_hr',central_hr_email:'',hour:8,max_daily_messages:20,max_overdue_days:30}};
    for(const ct of db.centers){
      db.v011.policies[ct.id]||={enabled:true,version:1};
      db.v011.requirements[ct.id]||={cid:ct.id,version:1,weekly:[0,1,2,3,4].map(weekday=>({weekday,slot:'m',role:'INF',minimum:2})),overrides:[]};
      db.payrollConfigs[ct.id].config.connector ||= connectorDefault();
    }
  }
  const approvalKey=(cid,month)=>cid+'|'+month;
  function approvalFingerprint(cid,month){return communicationFingerprint({people:db.snapshots[cid].people,entries:entriesFor(cid,month),config:period(cid,month).config,verified:period(cid,month).verified})}
  function approvalRead(cid,month){
    allowedCenter(cid);monthsBetween(month,month);const p=period(cid,month),policy=db.v011.policies[cid],workflow=db.v011.approvals[approvalKey(cid,month)]||{status:'draft',version:0,note:'',history:[]},fingerprint=approvalFingerprint(cid,month),checks=[],rows=summary(cid,month),entries=entriesFor(cid,month);
    if(!p.verified)checks.push('Verifica calendario e parametri del mese.');
    if(!entries.some(e=>e.layer==='actual'))checks.push('Mese senza registrazioni effettive.');
    if(rows.some(r=>r.pending))checks.push('Completa le fasce pianificate prive di consuntivo.');
    if(p.config.require_times_on_close&&rows.some(r=>r.missing))checks.push('Completa gli orari richiesti per la chiusura.');
    const legacy_closed=p.closed&&workflow.status!=='hr_approved',stale=['submitted','manager_approved','hr_approved'].includes(workflow.status)&&workflow.fingerprint!==fingerprint,actions=[];
    if(policy.enabled&&!legacy_closed){
      if(['draft','returned'].includes(workflow.status)&&writeAllowed())actions.push('submit');
      if(workflow.status==='submitted'&&managerAllowed())actions.push('manager_approve','return');
      if(workflow.status==='manager_approved'&&['admin','hr'].includes(role))actions.push('hr_approve','return');
      if(workflow.status==='hr_approved'&&['admin','hr'].includes(role))actions.push('reopen');
    }
    if(legacy_closed&&managerAllowed())actions.push('reopen');
    return {cid,month,policy:copy(policy),workflow:copy(workflow),actions,checks,fingerprint,verified:p.verified,history:copy(workflow.history||[]),summary:{people:rows.length,entries:entries.length,work_entries:entries.filter(e=>e.kind==='work').length},legacy_closed,stale,can_configure:role==='admin'};
  }
  function approvalGuard(cid,month,action){
    const d=approvalRead(cid,month);if(!d.policy.enabled)return;
    if(action==='close')fail('Usa Approvazioni: la chiusura richiede la verifica del responsabile e l’approvazione HR.');
    if(['submitted','manager_approved','hr_approved'].includes(d.workflow.status))fail('Mese inviato in approvazione: occorre una restituzione o riapertura prima di modificarlo.');
  }
  function approvalConfigure(body){
    allowedCenter(body.cid);if(role!=='admin')fail('Configurazione riservata all’amministratore.',403);const item=db.v011.policies[body.cid];checkVersion(body,item);requiredNote(body.reason);
    if(typeof body.enabled!=='boolean')fail('Attivazione non valida.');
    if(!body.enabled&&Object.entries(db.v011.approvals).some(([k,w])=>k.startsWith(body.cid+'|')&&['submitted','manager_approved'].includes(w.status)))fail('Restituisci i mesi in corso prima di disattivare il flusso.');
    Object.assign(item,{enabled:body.enabled,version:item.version+1});audit(body.cid,'Configurazione approvazione aggiornata');return {ok:true,policy:copy(item)};
  }
  function approvalTransition(body){
    const d=approvalRead(body.cid,body.month),w=d.workflow;checkVersion(body,w);if(body.fingerprint!==d.fingerprint)fail('I dati del mese sono cambiati: aggiorna la pagina.');if(!d.actions.includes(body.action))fail('Passaggio non consentito al tuo ruolo.',403);
    const action=body.action,note=['return','reopen'].includes(action)?requiredNote(body.note):String(body.note||'').slice(0,2000);
    if(['manager_approve','hr_approve'].includes(action)&&d.stale)fail('Dati cambiati dopo l’invio: restituisci il mese.');
    if(action==='manager_approve'){
      const remaining=d.checks.filter(x=>!x.startsWith('Verifica calendario'));
      if(remaining.length)fail(remaining.join(' '));if(!d.verified&&body.calendar_checked!==true)fail('Conferma la verifica del calendario.');period(body.cid,body.month).verified=true;
    }
    if(action==='hr_approve'&&d.checks.length)fail(d.checks.join(' '));
    const status={submit:'submitted',manager_approve:'manager_approved',hr_approve:'hr_approved',return:'returned',reopen:'draft'}[action];
    const next={...w,status,version:w.version+1,note,updated_at:now(),updated_by:user().username,fingerprint:approvalFingerprint(body.cid,body.month)};
    next.history=[{version:next.version,status,action,note,stamp:now(),actor:user().username},...(w.history||[])];db.v011.approvals[approvalKey(body.cid,body.month)]=next;
    if(action==='hr_approve')period(body.cid,body.month).closed=true;if(['return','reopen'].includes(action))period(body.cid,body.month).closed=false;
    audit(body.cid,'Approvazione: '+status);return approvalRead(body.cid,body.month);
  }
  function documentLocate(cid,id){requireHR(cid);for(const [pid,d] of Object.entries(db.hrDetails[cid]||{})){const doc=d.documents.find(x=>x.id===id);if(doc)return {...copy(doc),cid,pid}}fail('Documento non trovato.')}
  function reviewMetadata(doc){const r=db.v011.reviews[doc.id]||{version:0,status:'received',note:'',updated_at:doc.uploaded_at,updated_by:doc.uploaded_by},expired=!!doc.expiry&&doc.expiry<TODAY;const {history,...current}=r;return {...copy(current),label:reviewLabels[r.status],expired,effective_status:expired?'expired':r.status}}
  function reviewRead(cid,id,offset=0,limit=25){
    offset=Number(offset);limit=Number(limit);if(!Number.isInteger(offset)||offset<0||!Number.isInteger(limit)||limit<1||limit>100)fail('Pagina storico non valida.');
    const doc=documentLocate(cid,id),review=reviewMetadata(doc),history=db.v011.reviews[id]?.history||[];return {document:doc,review,history:copy(history.slice(offset,offset+limit)),history_total:history.length,offset,limit,can_review:['admin','hr'].includes(role),can_resubmit:review.status==='needs_correction',legacy_unreviewed:review.version===0};
  }
  function reviewSave(body){
    const d=reviewRead(body.cid,body.id);checkVersion(body,d.review);const status=body.status;
    if(!Object.hasOwn(reviewLabels,status))fail('Stato non valido.');
    if(status==='received'){if(d.review.status!=='needs_correction')fail('Il documento non richiede una nuova verifica.')}else if(!d.can_review)fail('La validazione è riservata a HR centrale.',403);
    if(status==='verified'&&d.review.expired)fail('Un documento scaduto non può essere verificato.');
    const note=['needs_correction','received'].includes(status)?requiredNote(body.note):String(body.note||'');
    const r={version:d.review.version+1,status,note,updated_at:now(),updated_by:user().username,history:[{version:d.review.version+1,status,note,stamp:now(),actor:user().username},...(db.v011.reviews[body.id]?.history||[])]};db.v011.reviews[body.id]=r;audit(body.cid,'Stato documento: '+reviewLabels[status]);return {ok:true,...reviewRead(body.cid,body.id)};
  }
  function departureItem(list,cid,id){requireHR(cid);const item=db.v011[list].find(x=>x.cid===cid&&x.id===id);if(!item)fail('Elemento non trovato.');return item}
  function departureDetail(item){
    const outstanding=db.v011.assets.filter(a=>a.cid===item.cid&&a.pid===item.pid&&a.status==='assigned'),blockers=item.tasks.filter(t=>t.required&&!['done','na'].includes(t.status)).map(t=>t.label);if(outstanding.length)blockers.push('Dotazioni ancora da restituire: '+outstanding.length);
    return {...copy(item),person_name:getPerson(item.cid,item.pid).name,outstanding_assets:copy(outstanding),blockers,can_complete:['open','in_progress'].includes(item.status)&&!blockers.length,notice:departureNotice};
  }
  function departuresOverview(cid){requireHR(cid);const cts=selectedCenters(cid),ids=new Set(cts.map(c=>c.id));return {centers:cts,people:cts.flatMap(c=>db.snapshots[c.id].people.map(p=>({cid:c.id,...copy(p)}))),cases:db.v011.cases.filter(x=>ids.has(x.cid)).map(departureDetail),assets:db.v011.assets.filter(x=>ids.has(x.cid)).map(a=>({...copy(a),person_name:getPerson(a.cid,a.pid).name,overdue:a.status==='assigned'&&!!a.due_date&&a.due_date<TODAY})),kinds:departureKinds,asset_kinds:assetKinds,notice:departureNotice,today:TODAY}}
  function departureCaseSave(body){
    requireHR(body.cid);getPerson(body.cid,body.pid);const old=body.id?departureItem('cases',body.cid,body.id):null;checkVersion(body,old);if(old&&!['open','in_progress'].includes(old.status))fail('Percorso già chiuso.');if(old&&body.pid!==old.pid)fail('Il dipendente non può essere cambiato.');
    if(!Object.hasOwn(departureKinds,body.kind))fail('Tipo percorso non valido.');if(body.kind==='transfer'){allowedCenter(body.destination_cid);if(body.destination_cid===body.cid)fail('Indica una destinazione diversa.');}
    if(db.v011.cases.some(c=>c.cid===body.cid&&c.pid===body.pid&&c.id!==body.id&&['open','in_progress'].includes(c.status)))fail('Esiste già un percorso aperto per questa persona.');
    if(!String(body.responsible||'').trim())fail('Responsabile obbligatorio.');const item={...(old||{}),id:old?.id||uid(),cid:body.cid,pid:body.pid,version:(old?.version||0)+1,status:old?.status||'open',kind:body.kind,destination_cid:body.kind==='transfer'?body.destination_cid:'',effective_date:validDay(body.effective_date),reason:requiredNote(body.reason),responsible:String(body.responsible).trim(),created_at:old?.created_at||now(),closure_note:'',tasks:old?.tasks||Object.entries(departureTaskLabels).map(([id,label])=>({id,label,required:true,status:'todo',owner:body.responsible,due:body.effective_date,note:''}))};
    stampHistory(item,old?'Percorso aggiornato':'Percorso creato');if(old)db.v011.cases[db.v011.cases.indexOf(old)]=item;else db.v011.cases.unshift(item);audit(body.cid,'Percorso uscita salvato');return departureDetail(item);
  }
  function departureTaskSave(body){
    const item=departureItem('cases',body.cid,body.id);checkVersion(body,item);if(!['open','in_progress'].includes(item.status))fail('Percorso già chiuso.');const task=item.tasks.find(t=>t.id===body.task_id);if(!task||!['todo','doing','done','na'].includes(body.status))fail('Attività non valida.');if(body.status==='na')requiredNote(body.note);if(!String(body.owner||'').trim())fail('Responsabile obbligatorio.');validDay(body.due);
    Object.assign(task,{status:body.status,note:String(body.note||''),owner:body.owner,due:body.due});item.version++;item.status='in_progress';stampHistory(item,'Attività aggiornata');audit(body.cid,'Attività uscita aggiornata');return departureDetail(item);
  }
  function departureTransitionDemo(body){
    const item=departureItem('cases',body.cid,body.id);checkVersion(body,item);if(!['open','in_progress'].includes(item.status)||!['completed','cancelled'].includes(body.status))fail('Passaggio non valido.');const note=requiredNote(body.note);
    if(body.status==='completed'){if(body.confirm!==true)fail('Conferma il completamento.');if(!departureDetail(item).can_complete)fail('Completa le attività e registra tutte le restituzioni.');}
    item.status=body.status;item.closure_note=note;item.version++;stampHistory(item,body.status==='completed'?'Percorso completato':'Percorso annullato');audit(body.cid,'Percorso uscita chiuso');return departureDetail(item);
  }
  function equipmentSave(body){
    requireHR(body.cid);getPerson(body.cid,body.pid);checkVersion(body,null);if(body.id)fail('In questa demo registra una nuova consegna.');if(!Object.hasOwn(assetKinds,body.kind))fail('Tipo dotazione non valido.');const code=String(body.inventory_code||'').trim(),key=code.replace(/\s+/g,' ').toLocaleLowerCase();if(!code||!String(body.label||'').trim())fail('Codice e descrizione obbligatori.');
    if(db.v011.assets.some(a=>a.cid===body.cid&&a.asset_key===key&&a.status==='assigned'))fail('Codice inventario già assegnato nella struttura.');validDay(body.delivery_date);if(body.delivery_date>TODAY)fail('La consegna non può essere futura.');if(body.due_date){validDay(body.due_date);if(body.due_date<body.delivery_date)fail('Restituzione prevista prima della consegna.');}
    const item={id:uid(),cid:body.cid,pid:body.pid,version:1,status:'assigned',kind:body.kind,inventory_code:code,asset_key:key,label:body.label,delivery_date:body.delivery_date,due_date:body.due_date||'',note:String(body.note||'')};stampHistory(item,'Dotazione consegnata');db.v011.assets.unshift(item);audit(body.cid,'Dotazione consegnata');return {ok:true,asset:copy(item)};
  }
  function equipmentReturn(body){
    const item=departureItem('assets',body.cid,body.id);checkVersion(body,item);if(item.status!=='assigned')fail('Restituzione già registrata.');validDay(body.return_date);if(body.return_date<item.delivery_date||body.return_date>TODAY)fail('Data restituzione non valida.');if(!['good','damaged','unusable'].includes(body.condition))fail('Condizione non valida.');if(body.condition!=='good')requiredNote(body.note);
    Object.assign(item,{status:'returned',version:item.version+1,return_date:body.return_date,return_condition:body.condition,return_note:String(body.note||'')});stampHistory(item,'Dotazione restituita');audit(body.cid,'Dotazione restituita');return {ok:true,asset:copy(item)};
  }
  function linkedPeople(cid,pid){const group=db.workforce.groups.find(g=>g.assignments.some(a=>a.cid===cid&&a.pid===pid));return group?group.assignments.map(a=>({cid:a.cid,pid:a.pid})):[{cid,pid}]}
  function staffingCandidates(cid){const ids=new Set(centers().map(c=>c.id));return db.snapshots[cid].people.filter(p=>p.active).flatMap(p=>linkedPeople(cid,p.id).filter(a=>a.cid!==cid&&ids.has(a.cid)&&db.snapshots[a.cid].people.some(x=>x.id===a.pid&&x.active)).map(a=>({pid:p.id,origin_cid:a.cid,origin_pid:a.pid,name:p.name,origin_name:db.snapshots[a.cid].center.name})))}
  function staffingSpan(e){if(e.kind!=='work'||!e.start||!e.end)return null;const a=Date.parse(e.day+'T'+e.start+':00Z'),b=Date.parse(e.day+'T'+e.end+':00Z')+(e.overnight?86400000:0);return [a,b]}
  function staffingConflict(cid,e){
    const links=linkedPeople(cid,e.person_id),span=staffingSpan(e);if(!span||span[1]<=span[0])return 'Orari da completare';
    const endDay=new Date(span[1]-1).toISOString().slice(0,10);
    for(const a of links){
      if(db.v011.availability.some(v=>v.cid===a.cid&&v.pid===a.pid&&v.active&&v.status==='unavailable'&&v.start<=endDay&&v.end>=e.day))return 'Persona non disponibile';
      for(const other of db.snapshots[a.cid].entries){if(other.id===e.id&&cid===a.cid||other.person_id!==a.pid||other.layer!==e.layer)continue;const next=staffingSpan(other);if(next&&span[0]<next[1]&&next[0]<span[1])return 'Sovrapposizione di turni';if(other.day===e.day&&other.slot===e.slot&&other.kind!=='work')return 'Causale di assenza o riposo nella fascia';}
    }return '';
  }
  function staffingReport(cid,month){
    const source=allowedCenter(cid),p=period(cid,month),cfg=p.config,req=db.v011.requirements[cid],entries=entriesFor(cid,month),n=new Date(+month.slice(0,4),+month.slice(5),0).getDate(),rows=[],problems=[];
    for(let daynum=1;daynum<=n;daynum++){const day=month+'-'+String(daynum).padStart(2,'0'),weekday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7;for(const slot of cfg.slots.filter(s=>s.active))for(const qualification of cfg.roles){
      const exact=req.overrides.find(r=>r.day===day&&r.slot===slot.id&&r.role===qualification),weekly=req.weekly.find(r=>r.weekday===weekday&&r.slot===slot.id&&r.role===qualification),minimum=exact?.minimum??weekly?.minimum??null;
      const matching=entries.filter(e=>e.day===day&&e.slot===slot.id&&e.kind==='work'&&effectivePerson(cid,e.person_id,day)?.role===qualification);if(minimum===null&&!matching.length)continue;
      const planned=new Set(),actual=new Set();let excluded=0;
      for(const e of matching){const reason=staffingConflict(cid,e);if(reason){excluded++;problems.push({day,slot:slot.id,layer:e.layer,person_name:hrAllowed()?getPerson(cid,e.person_id).name:'Personale della struttura',reason})}else(e.layer==='planned'?planned:actual).add(e.person_id)}
      const gap=minimum===null?null:Math.max(0,minimum-planned.size);rows.push({day,slot:slot.id,role:qualification,minimum,planned:planned.size,actual:actual.size,gap,excluded,state:minimum===null?'unconfigured':gap?'uncovered':'covered'});
    }}
    const privateView=hrAllowed();return {cid,month,center_name:source.center.name,closed:p.closed,requirements:copy(req),slots:copy(cfg.slots),roles:copy(cfg.roles),codes:copy(cfg.codes),rows,summary:{configured:rows.filter(r=>r.minimum!==null).length,uncovered:rows.filter(r=>r.state==='uncovered').length,missing:rows.reduce((n,r)=>n+(r.gap||0),0)},availability:privateView?db.v011.availability.filter(a=>a.cid===cid&&a.start<=month+'-31'&&a.end>=month+'-01').map(a=>({...copy(a),person_name:getPerson(cid,a.pid).name})):[],proposals:privateView?db.v011.proposals.filter(a=>a.cid===cid&&a.day.startsWith(month)&&centers().some(c=>c.id===a.origin_cid)).map(a=>({...copy(a),person_name:getPerson(cid,a.pid).name,center_name:source.center.name,origin_name:db.snapshots[a.origin_cid].center.name})):[],candidates:privateView?staffingCandidates(cid):[],people:privateView?source.people.filter(p=>p.active).map(p=>({id:p.id,name:p.name})):[],problems,permissions:{configure:managerAllowed(),availability:privateView,propose:privateView,decide:managerAllowed()},note:'Confronto organizzativo sul pianificato: non certifica l’adeguatezza clinica. I turni notturni appartengono al giorno di inizio; i conflitti considerano anche il giorno successivo.'};
  }
  function staffingRequirementsSave(body){
    allowedCenter(body.cid);if(!managerAllowed())fail('Fabbisogni riservati al responsabile.',403);const item=db.v011.requirements[body.cid],cfg=db.snapshots[body.cid].center.config;checkVersion(body,item);
    for(const key of ['weekly','overrides']){if(!Array.isArray(body[key])||body[key].length>1000)fail('Fabbisogni non validi.');const seen=new Set();for(const r of body[key]){if(key==='weekly'&&(!Number.isInteger(r.weekday)||r.weekday<0||r.weekday>6))fail('Giorno settimanale non valido.');if(key==='overrides')validDay(r.day);if(!cfg.slots.some(s=>s.id===r.slot&&s.active)||!cfg.roles.includes(r.role)||!Number.isInteger(r.minimum)||r.minimum<0||r.minimum>1000)fail('Fascia, qualifica o minimo non valido.');const id=[r.weekday??r.day,r.slot,r.role].join('|');if(seen.has(id))fail('Minimo duplicato.');seen.add(id)}}
    item.version++;item.weekly=copy(body.weekly);item.overrides=copy(body.overrides);audit(body.cid,'Fabbisogni aggiornati');return {ok:true,requirements:copy(item)};
  }
  function staffingAvailabilitySave(body){
    requireHR(body.cid);getPerson(body.cid,body.pid);validDay(body.from);validDay(body.to);if(body.from>body.to||!['available','unavailable','preferred'].includes(body.status)||typeof body.active!=='boolean')fail('Disponibilità non valida.');const old=body.id?db.v011.availability.find(a=>a.id===body.id&&a.cid===body.cid):null;if(body.id&&!old)fail('Disponibilità non trovata.');checkVersion(body,old);if(old&&old.pid!==body.pid)fail('Dipendente non modificabile.');
    const item={id:old?.id||uid(),cid:body.cid,pid:body.pid,version:(old?.version||0)+1,start:body.from,end:body.to,status:body.status,note:String(body.note||'').slice(0,1000),active:body.active,stamp:now(),actor:user().username};if(old)db.v011.availability[db.v011.availability.indexOf(old)]=item;else db.v011.availability.push(item);audit(body.cid,'Disponibilità aggiornata');return {ok:true,availability:copy(item)};
  }
  function staffingProposalState(body){
    allowedCenter(body.origin_cid);allowedCenter(body.cid);const person=getPerson(body.cid,body.pid);getPerson(body.origin_cid,body.origin_pid);if(!staffingCandidates(body.cid).some(x=>x.pid===body.pid&&x.origin_cid===body.origin_cid&&x.origin_pid===body.origin_pid))fail('Collega prima le anagrafiche della stessa persona nelle due strutture.');
    validDay(body.day);const month=body.day.slice(0,7),p=period(body.cid,month);if(p.closed||period(body.origin_cid,month).closed)fail('Uno dei mesi coinvolti è chiuso.');approvalGuard(body.cid,month,'entry');
    const slot=p.config.slots.find(s=>s.id===body.slot&&s.active),code=p.config.codes.find(c=>c.id===body.code&&c.active&&c.kind==='work');if(!slot||!code||code.allowed_slots.length&&!code.allowed_slots.includes(slot.id))fail('Fascia o causale non valida.');
    const entry={person_id:person.id,day:body.day,slot:slot.id,code:code.id,layer:'planned',kind:'work',start:slot.start,end:slot.end,overnight:slot.overnight,pause:slot.pause,work_site:db.snapshots[body.cid].center.name,note:body.note};
    const conflict=staffingConflict(body.cid,entry);if(conflict)fail(conflict);const fingerprint=communicationFingerprint({linked:linkedPeople(body.cid,body.pid).map(a=>({entries:db.snapshots[a.cid].entries.filter(e=>e.person_id===a.pid),availability:db.v011.availability.filter(v=>v.cid===a.cid&&v.pid===a.pid)})),config:p.config,approval:db.v011.approvals[approvalKey(body.cid,month)]||null});return {entry,fingerprint};
  }
  function staffingPropose(body){
    requireHR(body.cid);requiredNote(body.note);if(db.v011.proposals.some(p=>p.cid===body.cid&&p.pid===body.pid&&p.day===body.day&&p.slot===body.slot&&p.status==='pending'))fail('Esiste già una proposta in attesa per questa fascia.');
    const current=staffingProposalState(body),item={id:uid(),cid:body.cid,pid:body.pid,origin_cid:body.origin_cid,origin_pid:body.origin_pid,day:body.day,slot:body.slot,code:body.code,note:body.note,status:'pending',version:1,fingerprint:current.fingerprint,stamp:now(),actor:user().username,decision_note:'',decided_by:'',decided_at:'',entry_id:''};db.v011.proposals.unshift(item);audit(body.cid,'Sostituzione proposta');return {ok:true,id:item.id,version:1,warnings:[]};
  }
  function staffingDecide(body){
    const item=db.v011.proposals.find(p=>p.id===body.id);if(!item)fail('Proposta non trovata.');allowedCenter(item.cid);allowedCenter(item.origin_cid);if(!managerAllowed())fail('Conferma riservata al responsabile della destinazione.',403);checkVersion(body,item);if(item.status!=='pending'||!['accept','reject'].includes(body.decision))fail('Proposta già valutata o decisione non valida.');const note=requiredNote(body.note);
    if(body.decision==='accept'){const current=staffingProposalState(item);if(current.fingerprint!==item.fingerprint)fail('Presenze o disponibilità cambiate: richiedi una nuova proposta.');saveEntry({cid:item.cid,month:item.day.slice(0,7),revision:db.snapshots[item.cid].center.revision,entry:current.entry});item.entry_id=db.snapshots[item.cid].entries.find(e=>e.layer==='planned'&&e.day===item.day&&e.person_id===item.pid&&e.slot===item.slot).id;}
    item.status=body.decision==='accept'?'accepted':'rejected';item.version++;item.decision_note=note;item.decided_by=user().username;item.decided_at=now();audit(item.cid,'Sostituzione '+item.status);return {ok:true,id:item.id,status:item.status,version:item.version,entry_id:item.entry_id,warnings:[]};
  }
  function reminderConfig(raw){
    const current=db.v011.reminders,config={...copy(current),...copy(raw)};delete config.fingerprint;delete config.confirmed;
    if(typeof config.enabled!=='boolean'||!Array.isArray(config.centers)||config.centers.some(id=>!db.centers.some(c=>c.id===id))||!Array.isArray(config.topics)||!config.topics.length||config.topics.some(id=>!Object.hasOwn(reminderTopics,id)))fail('Strutture o argomenti non validi.');
    if(!Array.isArray(config.offsets)||!config.offsets.length||config.offsets.length>8||config.offsets.some(n=>!Number.isInteger(n)||n<0||n>365)||new Set(config.offsets).size!==config.offsets.length)fail('Anticipi non validi.');
    for(const [k,min,max] of [['hour',0,23],['max_daily_messages',1,200],['max_overdue_days',1,90]])if(!Number.isInteger(config[k])||config[k]<min||config[k]>max)fail('Limite o orario non valido.');
    if(!['structure_hr','central_hr','both'].includes(config.recipient_mode))fail('Destinazione non valida.');if(config.recipient_mode!=='structure_hr')config.central_hr_email=communicationEmail(config.central_hr_email).toLowerCase();return config;
  }
  function reminderPreview(body){
    communicationAccess();const config=reminderConfig(body),routes={},warnings=[],candidates=[];
    for(const ct of db.centers.filter(c=>!config.centers.length||config.centers.includes(c.id))){const emails=new Set();if(config.recipient_mode!=='central_hr'){try{emails.add(communicationEmail(db.structures.structures.find(s=>s.cid===ct.id)?.fields.hr_email).toLowerCase())}catch{warnings.push({cid:ct.id,message:ct.name+': recapito HR mancante o non valido.'})}}if(config.recipient_mode!=='structure_hr')emails.add(config.central_hr_email);routes[ct.id]=[...emails].sort();
      for(const person of db.snapshots[ct.id].people.filter(p=>p.active)){const d=hrDetail(ct.id,person.id);if(d.profile.stage==='ended')continue;
        function add(topic,key,due){if(!due||!config.topics.includes(topic))return;const delta=Math.round((Date.parse(due)-Date.parse(TODAY))/86400000);if(delta< -config.max_overdue_days||topic==='onboarding'&&delta>0)return;const options=config.offsets.filter(n=>n>=Math.max(delta,0));if(!options.length||delta<0&&!config.offsets.includes(0))return;const threshold=Math.min(...options);for(const email of emails){const event_key=communicationFingerprint([ct.id,key,due,threshold,email]);candidates.push({event_key,cid:ct.id,source_key:key,due,threshold,email,topic,label:person.name,status:(db.v011.reminderProcessed||[]).includes(event_key)?'simulated':'pending'})}}
        for(const [key,topic] of [['end_date','contract'],['probation_end','contract'],['identity_expiry','document'],['registration_expiry','qualification'],['work_permit_expiry','qualification'],['next_review','qualification']])add(topic,person.id+':'+key,d.profile.fields[key]);
        for(const doc of d.documents)add('document','document:'+doc.id,doc.expiry);for(const task of d.profile.tasks.filter(t=>!['done','na'].includes(t.status)))add('onboarding','task:'+person.id+':'+task.id,task.due);
      }
    }
    const grouped=new Map();for(const e of candidates.filter(e=>e.status==='pending')){const key=e.cid+'|'+e.email;if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(e)}
    const messages=[...grouped.values()].map(events=>{const {cid,email}=events[0],name=db.snapshots[cid].center.name,counts={};for(const e of events)counts[e.topic]=(counts[e.topic]||0)+1;return {cid,email,name:'Ufficio HR · '+name,subject:'Promemoria HR · '+name,body:'Riepilogo dimostrativo delle attività per '+name+'.\n\n'+Object.entries(counts).map(([k,n])=>reminderTopics[k]+': '+n).join('\n')+'\n\nConsulta il portale con il tuo account autorizzato. Questo messaggio non contiene nomi di dipendenti o allegati. Nessuna email viene inviata dalla demo.',event_keys:events.map(e=>e.event_key),count:events.length}});
    return {config,routes,warnings,candidates:candidates.slice(0,500),total_events:candidates.length,pending_events:candidates.filter(e=>e.status==='pending').length,messages,total_messages:messages.length,fingerprint:communicationFingerprint({config,routes,date:TODAY}),can_enable:Object.keys(routes).length>0&&!warnings.length&&Object.values(routes).every(r=>r.length),date:TODAY,timezone:'Europe/Rome'};
  }
  function remindersOverview(){communicationAccess();const p=reminderPreview(db.v011.reminders);return {config:copy(db.v011.reminders),can_configure:role==='admin',topics:Object.entries(reminderTopics).map(([id,label])=>({id,label})),centers:centers(),smtp_ready:true,warnings:p.warnings,changed_routes:[],history:copy(db.v011.reminderHistory||[]),runs:[],timezone:'Europe/Rome',simulation:true,demo_simulated:true}}
  function reminderSave(body){
    communicationAccess();if(role!=='admin')fail('Configurazione riservata all’amministratore.',403);checkVersion(body,db.v011.reminders);const p=reminderPreview(body);
    if(p.config.enabled&&(body.confirmed!==true||body.fingerprint!==p.fingerprint||!p.can_enable))fail('Genera l’anteprima e conferma i destinatari.');
    db.v011.reminders={...p.config,version:db.v011.reminders.version+1};
    if(p.config.enabled){db.v011.reminderHistory||=[];db.v011.reminderProcessed||=[];for(const m of p.messages.slice(0,p.config.max_daily_messages)){db.v011.reminderHistory.unshift({...m,id:uid(),status:'simulated',error:'',created_at:now(),event_count:m.count});db.v011.reminderProcessed.push(...m.event_keys)}}persist();return remindersOverview();
  }
  function payrollSpecPreview(body){
    requireHR(body.cid);if(typeof body.text!=='string'||!body.text.trim()||new TextEncoder().encode(body.text).length>32768)fail('Invia una specifica di massimo 32 KiB.');let connector={...connectorDefault(),mode:'consultant'},delimiter=body.delimiter||';',decimal_separator=',',columns=[];const fields=db.payrollConfigs[body.cid].fields;
    const header=value=>{if(typeof value!=='string'||!value.trim()||value.length>120||/^[=+@-]/.test(value.trim()))fail('Intestazione non valida.');return value.trim()};
    if(body.kind==='csv_header'){
      if(![';',',','\t'].includes(delimiter))fail('Separatore non valido.');const lines=body.text.replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines.length!==1)fail('Invia solo le intestazioni, senza righe dei dipendenti.');
      // Header-only CSV parser supporting escaped double quotes.
      const values=[];let value='',quoted=false;for(let i=0;i<lines[0].length;i++){const ch=lines[0][i];if(ch==='"'){if(quoted&&lines[0][i+1]==='"'){value+='"';i++}else quoted=!quoted}else if(ch===delimiter&&!quoted){values.push(value);value=''}else value+=ch}if(quoted)fail('Intestazione CSV non leggibile.');values.push(value);
      columns=values.map(v=>{const label=header(v),found=fields.find(f=>[f.id,f.label].some(x=>x.toLowerCase()===label.toLowerCase()));return {field:found?.id||'',label}});connector.expected_columns=columns.map(c=>({header:c.label,required:true,type:fields.find(f=>f.id===c.field)?.type||'text',max_length:null}));
    }else if(body.kind==='json'){
      let spec;try{spec=JSON.parse(body.text)}catch{fail('Specifica JSON non leggibile.')}const keys=['schema','provider','format_name','format_version','specification_reference','delimiter','decimal_separator','date_format','encoding','columns'];if(!spec||spec.schema!=='nefrocenter.payroll-spec.v1'||Object.keys(spec).some(k=>!keys.includes(k))||!Array.isArray(spec.columns))fail('Specifica non valida o contenente dati aggiuntivi.');
      for(const k of ['provider','format_name','format_version','specification_reference','date_format','encoding'])if(k in spec)connector[k]=spec[k];delimiter=spec.delimiter||';';decimal_separator=spec.decimal_separator||',';
      columns=spec.columns.map(c=>{if(!c||Object.keys(c).some(k=>!['header','field','required','type','max_length'].includes(k))||c.field&&!fields.some(f=>f.id===c.field))fail('Colonna non valida.');return {field:c.field||'',label:header(c.header)}});connector.expected_columns=spec.columns.map((c,i)=>({header:columns[i].label,required:c.required??true,type:c.type||fields.find(f=>f.id===c.field)?.type||'text',max_length:c.max_length??null}));
    }else fail('Scegli intestazioni CSV o specifica JSON.');
    if(columns.length<3||columns.length>fields.length||new Set(columns.map(c=>c.label.toLowerCase())).size!==columns.length||new Set(columns.filter(c=>c.field).map(c=>c.field)).size!==columns.filter(c=>c.field).length)fail('Colonne mancanti, ripetute o eccessive.');
    if(![';',',','\t'].includes(delimiter)||!['.',','].includes(decimal_separator)||!['YYYY-MM-DD','DD/MM/YYYY'].includes(connector.date_format)||!['utf-8-sig','utf-8','cp1252'].includes(connector.encoding))fail('Formato della specifica non supportato.');
    return {cid:body.cid,connector,columns,delimiter,decimal_separator,unmapped:columns.filter(c=>!c.field).length,stored:false,notice:'Specifica letta senza righe dei dipendenti. Completa le associazioni e salva una nuova versione in bozza.'};
  }
  function payrollSpecification(cid){requireHR(cid);const cfg=db.payrollConfigs[cid].config,c=cfg.connector;return {schema:'nefrocenter.payroll-spec.v1',...Object.fromEntries(['provider','format_name','format_version','specification_reference','date_format','encoding'].map(k=>[k,c[k]])),delimiter:cfg.delimiter,decimal_separator:cfg.decimal_separator,columns:cfg.columns.map(col=>({...c.expected_columns.find(x=>x.header===col.label),header:col.label,field:col.field}))}}
  function payrollConnectorValidate(body){
    const cfg=body.config,c=cfg?.connector||connectorDefault();if(c.mode!=='consultant')return;
    if(cfg.status==='confirmed'){
      if(body.confirm_connector!==true)fail('Conferma esplicitamente la verifica del tracciato.');
      if(['provider','format_name','format_version','specification_reference'].some(k=>!String(c[k]||'').trim())||['non so','da definire','non definito','unknown','sconosciuto'].includes(c.provider.trim().toLowerCase()))fail('Completa gestionale, nome, versione e riferimento delle specifiche.');
      if(c.expected_columns.length!==cfg.columns.length||cfg.columns.some((col,i)=>!col.field||col.label!==c.expected_columns[i].header))fail('Associa tutte le colonne nello stesso ordine della specifica.');
    }
  }
  async function routeV011(path,q,body,method,cid,selectedMonth){
    initV011();
    if(method==='GET')switch(path){
      case 'approvals':return approvalRead(cid,selectedMonth);
      case 'hr_document_review':return reviewRead(cid,q.get('id'),q.get('offset')||0,q.get('limit')||25);
      case 'departures':return departuresOverview(q.get('cid')||'all');
      case 'departure_case':return departureDetail(departureItem('cases',cid,q.get('id')));
      case 'staffing':return staffingReport(cid,selectedMonth);
      case 'reminders':return remindersOverview();
      case 'payroll_specification':return payrollSpecification(cid);
    }
    if(method==='POST')switch(path){
      case 'approval_config_save':return approvalConfigure(body);
      case 'approval_transition':return approvalTransition(body);
      case 'hr_document_review':return reviewSave(body);
      case 'departure_case_save':return departureCaseSave(body);
      case 'departure_task_save':return departureTaskSave(body);
      case 'departure_case_transition':return departureTransitionDemo(body);
      case 'equipment_save':return equipmentSave(body);
      case 'equipment_return':return equipmentReturn(body);
      case 'staffing_requirements_save':return staffingRequirementsSave(body);
      case 'staffing_availability_save':return staffingAvailabilitySave(body);
      case 'staffing_propose':return staffingPropose(body);
      case 'staffing_decide':return staffingDecide(body);
      case 'reminder_preview':return reminderPreview(body);
      case 'reminder_config_save':return reminderSave(body);
      case 'payroll_spec_preview':return payrollSpecPreview(body);
    }
    if(method==='POST'&&['entry','delete','period_verify','close','reopen'].includes(path))approvalGuard(cid,selectedMonth,path);
    if(method==='POST'&&path==='payroll_save')payrollConnectorValidate(body);
    return undefined;
  }

  async function route(path,q,body,method){
    if(path==='auth'){
      if(!initialized){month=seed.month;workforceOn=TODAY;initialized=true}
      if(!role)await chooseRole();else if(!document.getElementById('demoBanner')?.querySelector('#demoChangeRole'))banner();
      return {configured:true,stage:'authenticated',user:user(),centers:centers(),csrf:'demo-no-real-authentication'};
    }
    if(path==='logout'){role='';storage.remove(ROLE_STORE);return {ok:true}}
    if(!role)fail('Scegli prima un profilo dimostrativo.',403);
    const cid=q.get('cid')||body.cid||db.centers[0].id,selectedMonth=q.get('month')||body.month||db.month;
    const extension=await routeV011(path,q,body,method,cid,selectedMonth);if(extension!==undefined)return extension;
    if(method==='GET')switch(path){
      case 'state':return snapshot(cid,selectedMonth);
      case 'overview':return overview(selectedMonth);
      case 'structures':return structureRead(q.get('cid')||'all');
      case 'communications':return communicationOverview();
      case 'communication_campaign':return communicationCampaign(q.get('id'));
      case 'hr':return q.get('pid')?hrDetail(cid,q.get('pid')):hrListing(cid);
      case 'hr_documents':return documents(q);
      case 'hr_document':{requireHR(cid);const found=Object.values(db.hrDetails[cid]||{}).some(d=>d.documents.some(x=>x.id===q.get('id')));if(!found)fail('Documento non trovato.');const sample=await sampleDocument();return {name:sample.name,content:sample.content,sha256:''}}
      case 'tasks':return tasks(q);
      case 'statistics':return statistics(q);
      case 'workforce':return workforce(q);
      case 'workforce_preview':{requireHR(cid);const p=copy(db.workforcePreviews?.[cid]?.[q.get('pid')]);if(!p)fail('Anteprima dimostrativa non disponibile per questa persona. Consulta gli accordi del mese.');if(selectedMonth!==db.month)fail('L’anteprima economica dimostrativa riguarda ottobre 2026.');p.closed=true;p.message='Anteprima dei dati iniziali della demo.';return p}
      case 'agreements':{requireHR(cid);const data=copy(db.agreements[cid]);if(!data)fail('Accordi non disponibili.');if(selectedMonth!==db.month){data.rows=[];data.month=selectedMonth}data.closed=true;return data}
      case 'payroll_config':requireHR(cid);return copy(db.payrollConfigs[cid]);
      case 'payroll_preview':return payrollPreview(cid,q.get('from'),q.get('to'));
      case 'security':return {recovery_remaining:0,sessions:1,history:[{stamp:now(),action:'Profilo dimostrativo: '+ROLES[role][0]}]};
      case 'backups':if(role!=='admin')fail('Riservato all’amministratore.',403);return {count:0,bytes:0,files:[],shown:0,automatic_policy:'La demo non esegue backup. Questa area mostra le funzioni disponibili nell’installazione completa.'};
      case 'backup_policy':if(role!=='admin')fail('Riservato all’amministratore.',403);return {enabled:false,destination:'',retention_count:0,probe_interval_days:30,last_success:null,last_probe:null,last_error:'',retention_error:'',destination_error:'',schedule:'La copia su NAS è disponibile nell’installazione completa.',protection_note:'Nessun collegamento a NAS o sistemi aziendali viene effettuato da questa demo.',same_filesystem:null};
      case 'export':case 'group_export':{
        const cts=path==='group_export'?centers():[allowedCenter(cid).center],rows=[['DEMO - DATI FITTIZI'],['Centro','Matricola','Nome','Giorno','Fascia','Causale','Ingresso','Uscita','Minuti','Registro']];
        cts.forEach(c=>{const s=snapshot(c.id,selectedMonth);s.entries.forEach(e=>{const p=s.people.find(p=>p.id===e.person_id);rows.push([c.name,p?.registration,p?.name,e.day,e.slot,e.code,e.start,e.end,minutes(e),e.layer])})});return csvResponse(csv(rows));
      }
      case 'export_xlsx':{
        const kind=q.get('kind')||'presenze_centro';if(['dipendenti','onboarding','accordi'].includes(kind))requireHR(cid==='all'?'':cid);else if(cid!=='all')allowedCenter(cid);
        if(role==='operator'&&!selectedCenters(cid).every(c=>db.snapshots[c.id].center.config.operator_export))fail('Esportazione non abilitata per questo profilo.',403);
        if(q.get('role')||q.get('person_id')||q.get('layer')==='planned')fail('Gli Excel dimostrativi contengono il consuntivo iniziale senza filtri per ruolo o persona. Rimuovi questi filtri oppure usa il CSV del registro.');
        tell('Scarico un esempio Excel dei dati iniziali di ottobre 2026; le modifiche della sessione non sono incluse.');
        const file=db.exportFiles?.[kind]?.[cid]||`/samples/${kind}_${cid}.xlsx`,r=await nativeFetch(file);if(!r.ok)fail('Esempio Excel non disponibile per questa selezione.');return r;
      }
      case 'payroll_download':{const p=payrollPreview(cid,q.get('from'),q.get('to'));if(!p.can_download||p.fingerprint!==q.get('fingerprint'))fail('Genera una nuova anteprima e risolvi i controlli bloccanti.');if(db.payrollConfigs[cid].config.connector?.encoding==='cp1252')fail('La demo esporta CSV UTF-8. Windows-1252 è disponibile nell’installazione completa.');if(q.get('format')==='xlsx')fail('Per le modifiche della demo usa il CSV. L’Excel paghe è disponibile nell’installazione completa.');return csvResponse(csv([['DEMO - DATI FITTIZI'],p.columns.map(c=>c.label),...p._rows],db.payrollConfigs[cid].config.delimiter))}
      default:unavailable();
    }
    if(method!=='POST')fail('Operazione non disponibile nella demo.');
    switch(path){
      case 'structure_save':return structureSave(body);
      case 'communication_template_save':return communicationSave('templates',body);
      case 'communication_list_save':return communicationSave('lists',body);
      case 'communication_preview':return communicationPreview(body);
      case 'communication_campaign_create':return communicationCreate(body);
      case 'communication_send':return communicationSend(body);
      case 'communication_config_save':communicationAccess();fail('La demo simula soltanto gli invii. Non inserire server o credenziali reali: configura SMTP nell’installazione aziendale.');break;
      case 'entry':return saveEntry(body);
      case 'delete':{const s=allowedCenter(cid),p=period(cid,selectedMonth);if(!writeAllowed()||role==='operator'&&!p.config.operator_delete)fail('Eliminazione riservata al responsabile.',403);if(p.closed)fail('Mese chiuso.');const e=s.entries.find(e=>e.id===body.id&&e.day.startsWith(selectedMonth));if(!e)fail('Registrazione non trovata.');s.entries=s.entries.filter(x=>x!==e);audit(cid,'Presenza eliminata');return {ok:true}}
      case 'hr_save':return saveHR(body);
      case 'hr_task':{requireHR(cid);hrDetail(cid,body.pid);const d=db.hrDetails[cid][body.pid];if(d.profile.version!==body.version)fail('Fascicolo modificato: ricarica.');const t=d.profile.tasks.find(t=>t.id===body.task_id);if(!t||!['todo','doing','done','na'].includes(body.status))fail('Attività non valida.');if(body.status==='na'&&!String(body.note||'').trim())fail('Indica il motivo della non applicabilità.');Object.assign(t,{status:body.status,due:body.due||'',owner:String(body.owner||'').slice(0,150),note:String(body.note||'').slice(0,1000)});d.profile.version++;d.history.unshift({version:d.profile.version,stamp:now(),actor:'demo.'+role});audit(cid,'Attività di onboarding aggiornata');return {ok:true}}
      case 'hr_settings':requireHR(cid);db.hrLists[cid].settings={...copy(body.settings),version:(db.hrLists[cid].settings.version||0)+1};audit(cid,'Modello onboarding aggiornato');return {ok:true};
      case 'hr_document_add':{requireHR(cid);if(!body.demoSample)fail('Nella demo puoi allegare soltanto il documento dimostrativo. Non caricare documenti reali.');hrDetail(cid,body.pid);const sample=await sampleDocument(),d={id:uid(),name:sample.name,category:String(body.category||'Contratto').slice(0,100),expiry:body.expiry||'',uploaded_at:now(),uploaded_by:'demo.'+role,sha256:'',size:sample.size};db.hrDetails[cid][body.pid].documents.unshift(d);db.v011.reviews[d.id]={version:1,status:'received',note:'',updated_at:now(),updated_by:user().username,history:[{version:1,status:'received',note:'',stamp:now(),actor:user().username}]};audit(cid,'Documento dimostrativo allegato');return {ok:true,id:d.id}}
      case 'hr_document_delete':{requireHR(cid);if(!String(body.reason||'').trim())fail('Indica una motivazione.');for(const d of Object.values(db.hrDetails[cid]||{}))d.documents=d.documents.filter(x=>x.id!==body.id);audit(cid,'Documento dimostrativo rimosso');return {ok:true}}
      case 'payroll_save':{requireHR(cid);const existing=db.payrollConfigs[cid],cfg=body.config;if(body.expected_version!==existing.version)fail('Modello aggiornato: ricarica.');if(!String(cfg.name||'').trim()||!cfg.columns?.length)fail('Nome e colonne obbligatori.');if(cfg.status==='confirmed'&&String(cfg.confirmation_note||'').trim().length<8)fail('Indica la verifica effettuata (almeno 8 caratteri).');if(new Set(cfg.columns.map(c=>c.field)).size!==cfg.columns.length)fail('Colonna ripetuta.');existing.history.unshift({version:existing.version,name:existing.config.name,status:existing.config.status,created_at:now(),created_by:'demo.'+role});existing.config=copy(cfg);existing.version++;audit(cid,'Modello paghe dimostrativo aggiornato');return {ok:true,version:existing.version}}
      case 'period_verify':{allowedCenter(cid);if(!managerAllowed())fail('Verifica riservata al responsabile.',403);period(cid,selectedMonth).verified=!!body.verified;period(cid,selectedMonth).note=body.note||'';audit(cid,'Calendario verificato');return {ok:true}}
      case 'close':{const s=snapshot(cid,selectedMonth);if(!managerAllowed())fail('Chiusura riservata al responsabile.',403);if(!s.period.verified)fail('Verifica calendario e parametri prima della chiusura.');if(!s.entries.some(e=>e.layer==='actual'))fail('Mese senza registrazioni effettive.');if(s.summary.some(r=>r.pending))fail('Completa le fasce pianificate.');if(s.period.config.require_times_on_close&&s.summary.some(r=>r.missing))fail('Completa gli orari richiesti.');period(cid,selectedMonth).closed=true;audit(cid,'Mese chiuso');return {ok:true}}
      case 'reopen':allowedCenter(cid);if(!managerAllowed())fail('Riapertura riservata al responsabile.',403);if(!String(body.reason||'').trim())fail('Motivazione obbligatoria.');period(cid,selectedMonth).closed=false;period(cid,selectedMonth).note=body.reason;audit(cid,'Mese riaperto');return {ok:true};
      case 'agreement_save':case 'workforce_apply':case 'workforce_contract':case 'workforce_economic':case 'workforce_link':fail('La demo consente di consultare identità, decorrenze e accordi di esempio. Il salvataggio di queste condizioni è disponibile nell’installazione completa.');break;
      default:unavailable();
    }
  }

  window.fetch=async(input,options={})=>{
    const raw=typeof input==='string'||input instanceof URL?String(input):input.url,url=new URL(raw,location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return nativeFetch(input,options);
    try{await seedReady;let body={};if(options.body){try{body=JSON.parse(options.body)}catch{fail('Richiesta non valida.')}}const result=await route(url.pathname.slice(5),url.searchParams,body,(options.method||'GET').toUpperCase());return result instanceof Response?result:response(result)}catch(error){console.warn('Demo:',error.message);return response({error:error.message},error.status||400)}
  };
  window.Demo={version:'0.11',ready:seedReady,reset(){storage.remove(STORE);location.reload()},changeRole(){storage.remove(ROLE_STORE);location.reload()},info:showInfo,get role(){return role},get month(){return seed?.month}};

  // Navigation links bypass fetch. Point fixture documents at the public sample.
  // Real file upload is replaced with an explicit synthetic-document action.
  document.addEventListener('click',async event=>{
    const target=event.target instanceof Element?event.target:null;if(!target)return;
    const link=target.closest('a[href^="/api/hr_document_view"]');if(link){link.href='/samples/contratto-demo.pdf';return}
    if(target.closest('#hrDocumentFile,#fileInput,#importExcel')){event.preventDefault();event.stopImmediatePropagation();tell('La demo usa solo dati fittizi. Per i documenti puoi allegare il file dimostrativo del fascicolo.');return}
    if(target.closest('#hrUpload')){
      event.preventDefault();event.stopImmediatePropagation();const button=target.closest('#hrUpload');button.disabled=true;
      try{await api('hr_document_add',{cid,pid:hrPid,demoSample:true,category:document.getElementById('hrDocumentCategory').value,expiry:document.getElementById('hrDocumentExpiry').value});hrDirty=false;await hrOpen(hrPid);tell('Documento dimostrativo aggiunto. Cambia profilo in HR centrale per ritrovarlo nell’archivio.')}catch(e){tell(e.message)}finally{if(button.isConnected)button.disabled=false}
    }
  },true);
  let patchScheduled=false;
  function patchDemoLabels(){
    patchScheduled=false;
    // Rewrite before interaction so context-menu and middle-click navigation work too.
    document.querySelectorAll('a[href^="/api/hr_document_view"]').forEach(link=>{link.href='/samples/contratto-demo.pdf'});
    const file=document.getElementById('hrDocumentFile');if(file&&!file.dataset.demoPatched){file.dataset.demoPatched='1';file.disabled=true;file.hidden=true;const note=document.createElement('p');note.className='demo-inline-note';note.textContent='Documento-dimostrativo.pdf · esempio fittizio già pronto. Nessun file personale viene caricato.';file.after(note)}
    document.querySelectorAll('a[href^="/api/hr_document_view"]').forEach(link=>{link.href='/samples/contratto-demo.pdf'});
    const upload=document.getElementById('hrUpload');if(upload&&upload.textContent!=='Allega documento dimostrativo')upload.textContent='Allega documento dimostrativo';
    const sec=document.querySelector('.web-security-grid');if(sec&&!sec.dataset.demoPatched){sec.dataset.demoPatched='1';const tag=sec.querySelector('.tag'),title=sec.querySelector('h2'),sub=sec.querySelector('p.muted');if(tag)tag.textContent='Demo pubblica · senza autenticazione';if(title)title.textContent='La sicurezza del portale completo';if(sub)sub.textContent='Qui usi un profilo dimostrativo. Nell’installazione aziendale ogni account richiede password e secondo fattore.'}
    const ag=document.querySelector('.agreement-intro');if(ag&&!ag.dataset.demoPatched){ag.dataset.demoPatched='1';const tag=ag.querySelector('.badge-lock');if(tag)tag.textContent='Esempio iniziale · sola consultazione';const p=ag.querySelector('p');if(p)p.textContent='Accordi economici dei dati iniziali di ottobre 2026. Le modifiche alle presenze della demo non ricalcolano questi esempi; il calcolo completo è disponibile nell’installazione.'}
    const foot=document.querySelector('.web-dashboard-metrics')?.parentElement?.querySelector('.footer-note');if(foot&&!foot.dataset.demoPatched){foot.dataset.demoPatched='1';foot.textContent='Dati dimostrativi · le modifiche sono disponibili solo in questa scheda del browser. Gli altri visitatori usano una propria copia.'}
    const exports=document.querySelector('.export-builder');if(exports&&!exports.dataset.demoPatched){exports.dataset.demoPatched='1';const note=document.createElement('p');note.className='demo-inline-note';note.textContent='Excel di esempio: dati iniziali di ottobre 2026. Le modifiche di questa sessione e i filtri del periodo non vengono applicati al file. Il CSV del registro include le modifiche.';exports.prepend(note)}
    const reminder=document.querySelector('.reminder-intro');if(reminder&&!reminder.dataset.demoPatched){reminder.dataset.demoPatched='1';const note=document.createElement('p');note.className='demo-inline-note';note.textContent='Simulazione: salvando una programmazione attiva viene eseguito un solo controllo dimostrativo; gli esiti compaiono come Simulato. Non ci sono invii o attività in background. Il server aziendale esegue invece i controlli periodici.';reminder.append(note)}
    const account=document.getElementById('account');if(account&&account.textContent!=='Sicurezza · demo')account.textContent='Sicurezza · demo';
  }
  const observe=()=>{banner();new MutationObserver(()=>{if(!patchScheduled){patchScheduled=true;queueMicrotask(patchDemoLabels)}}).observe(document.getElementById('app'),{childList:true,subtree:true});patchDemoLabels()};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',observe);else observe();
})();
