/* Actionable issues, derived afresh from the authorized server scope. */
let taskFilters={cid:'all',category:'',priority:''},taskRequest=0;
const taskLabels={orari:'Orari mancanti',consuntivi:'Da consuntivare',calendario:'Calendari',chiusure:'Mesi aperti',fascicoli:'Fascicoli',onboarding:'Onboarding',scadenze:'Scadenze',backup:'Backup'};
async function renderTasks(){
 const request=++taskRequest,selectedMonth=month;
 if(taskFilters.cid!=='all'&&!auth.centers.some(c=>c.id===taskFilters.cid))taskFilters.cid='all';
 $('#content').innerHTML=`<section class="panel tasks-intro"><div><span class="eyebrow">IL LAVORO DA COMPLETARE</span><h2>Una lista, il prossimo passo.</h2><p class="muted">Presenze del mese selezionato e situazione attuale dei fascicoli. Ogni voce apre la pagina utile; scompare quando il dato viene completato.</p></div><div class="tasks-filters"><label>Centro<select id="tasksCenter"><option value="all">Tutti i centri autorizzati</option>${auth.centers.map(c=>`<option value="${esc(c.id)}" ${c.id===taskFilters.cid?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>Tipo<select id="tasksCategory"><option value="">Tutti</option>${Object.entries(taskLabels).map(([k,v])=>`<option value="${k}" ${k===taskFilters.category?'selected':''}>${v}</option>`).join('')}</select></label><label>Priorità<select id="tasksPriority"><option value="">Tutte</option><option value="urgent" ${taskFilters.priority==='urgent'?'selected':''}>Da controllare subito</option></select></label><button class="btn" id="tasksRefresh">Aggiorna</button></div></section><div id="tasksResult" role="status" aria-live="polite">Caricamento…</div>`;
 $('#tasksCenter').onchange=e=>{taskFilters.cid=e.target.value;renderTasks()};
 $('#tasksCategory').onchange=e=>{taskFilters.category=e.target.value;renderTasks()};
 $('#tasksPriority').onchange=e=>{taskFilters.priority=e.target.value;renderTasks()};$('#tasksRefresh').onclick=renderTasks;
 try{
  const d=await api('tasks?'+new URLSearchParams({month:selectedMonth,cid:taskFilters.cid}));
  if(request!==taskRequest||tab!=='attivita'||selectedMonth!==month)return;
  const rows=d.items.filter(x=>(!taskFilters.category||x.category===taskFilters.category)&&(!taskFilters.priority||x.priority===taskFilters.priority));
  $('#tasksResult').innerHTML=`<div class="tasks-summary"><b>${rows.length} voci mostrate</b><span>${d.total} totali · ${d.urgent} da controllare subito · ${esc(d.as_of)}</span></div><div class="tasks-list">${rows.map((x,i)=>`<article class="panel task-card"><div><span class="tag ${x.priority==='urgent'?'warn':''}">${taskLabels[x.category]||esc(x.category)}${x.priority==='urgent'?' · Priorità alta':''}</span><h3>${esc(x.title)}</h3><p>${esc(x.detail)}</p><small>${esc(x.center)}${x.day?' · '+esc(x.day):''}</small></div><button class="btn" data-task-index="${i}">Apri pagina</button></article>`).join('')||'<div class="panel empty">Nessuna attività nei filtri selezionati.</div>'}</div>`;
  document.querySelectorAll('[data-task-index]').forEach(b=>b.onclick=async()=>{try{
   const x=rows[Number(b.dataset.taskIndex)];
   if(x.cid){cid=x.cid;month=x.month;tab='attivita';await load()}
   if(['fascicoli','onboarding','scadenze'].includes(x.category)){hrPid=null;tab='dipendenti';render();await hrOpen(x.pid);const section=document.querySelector('[data-hr-section="'+x.section+'"]');if(section)section.click()}
   else if(['orari','consuntivi'].includes(x.category)){personFilter=x.pid;roleFilter='';search='';layer=x.category==='consuntivi'?'planned':'actual';gridWindow='week';gridWeek=Math.floor((Number(x.day.slice(-2))-1)/7);tab='presenze';render()}
   else{tab=x.section||'controlli';render()}
  }catch(e){toast(e.message)}});
 }catch(e){if(request===taskRequest&&tab==='attivita')$('#tasksResult').innerHTML='<div class="error">'+esc(e.message)+'</div>'}
}
