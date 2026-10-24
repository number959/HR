/* Server-authorized downloads. Files are never cached in browser storage. */
let exportFilters=null,exportsRequest=0;
const exportKinds={
 presenze_centro:['Presenze del singolo centro','Registro mensile con giorni in colonna e fasce per persona, totali individuali, dettaglio e legenda.'],
 presenze_totali:['Presenze complessive','Totali dei centri autorizzati, riepiloghi per mese, ruolo, persona e causale.'],
 statistiche:['Statistiche','Indicatori del periodo con ore note, turni, assenze e completezza degli orari.'],
 dipendenti:['Anagrafiche e fascicoli','Dati del personale e campi personalizzati. Situazione attuale, indipendente dal periodo.'],
 onboarding:['Onboarding e scadenze','Attività di ingresso, scadenze e inventario dei documenti. Gli allegati restano nel database.'],
 accordi:['Accordi individuali','Parametri per dipendente e mese; importi solo per accordi confermati e calcolabili.']
};
async function downloadFile(path,filename,retry=true){
 const r=await fetch('/api/'+path,{credentials:'same-origin',cache:'no-store',headers:{'X-Presenze-Token':token}});
 if(!r.ok){
  const out=await r.json().catch(()=>({error:'Download non riuscito.'}));
  if(r.status===428&&retry){await stepUpDialog();return downloadFile(path,filename,false)}
  if(r.status===401){auth=null;state=null;await boot()}
  throw Error(out.error||'Download non riuscito.');
 }
 const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
async function renderExports(){
 const request=++exportsRequest;
 if(!exportFilters)exportFilters={kind:'presenze_centro',cid:cid,first:month,last:month,layer:'actual',role:'',person_id:''};
 if(exportFilters.cid!=='all'&&!auth.centers.some(c=>c.id===exportFilters.cid))exportFilters.cid=auth.centers[0]?.id||'all';
 if(!hrAccess()&&['dipendenti','onboarding','accordi'].includes(exportFilters.kind))exportFilters.kind='presenze_centro';
 const f=exportFilters;
 $('#content').innerHTML=`<div class="export-page"><section class="panel export-builder"><div class="export-intro"><span class="eyebrow">REPORT EXCEL</span><h2>I dati, pronti da utilizzare.</h2><p class="muted">File .xlsx con fogli organizzati, filtri e date e ore utilizzabili in Excel.</p></div><form id="exportForm"><div class="export-fields"><label class="export-wide">Prospetto<select id="exportKind">${Object.entries(exportKinds).filter(([k])=>hrAccess()||!['dipendenti','onboarding','accordi'].includes(k)).map(([k,v])=>`<option value="${k}" ${f.kind===k?'selected':''}>${v[0]}</option>`).join('')}</select></label><label>Centro<select id="exportCenter"><option value="all" ${f.cid==='all'?'selected':''}>Tutti i centri autorizzati</option>${auth.centers.map(c=>`<option value="${esc(c.id)}" ${f.cid===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label id="exportLayerLabel">Registro<select id="exportLayer"><option value="actual" ${f.layer==='actual'?'selected':''}>Consuntivo</option><option value="planned" ${f.layer==='planned'?'selected':''}>Pianificato</option></select></label><label id="exportFromLabel">Dal mese<input type="month" id="exportFrom" value="${f.first}" required></label><label id="exportToLabel">Al mese<input type="month" id="exportTo" value="${f.last}" required></label></div><div class="export-description" id="exportDescription"></div><p class="muted smalltext" id="exportHint"></p><div class="export-bottom"><span>Solo i centri e i dati autorizzati per il tuo account.</span><button type="submit" class="btn primary" id="exportDownload">Scarica Excel (.xlsx)</button></div><div id="exportError" role="alert"></div></form></section>${superadmin()?'<section class="panel export-backups"><div class="toolbar"><div><span class="eyebrow">CONTINUITÀ DEI DATI</span><h2>Backup del database</h2></div><button class="btn" id="backupNow">Crea backup adesso</button></div><p class="muted">Comprende presenze, fascicoli, allegati, configurazioni e account. La chiave di protezione 2FA originale va conservata separatamente.</p><div id="backupBody" aria-live="polite">Caricamento dei backup…</div><p class="export-backup-note">Il download richiede una verifica di sicurezza recente. Il ripristino si esegue sul server seguendo la guida inclusa nel software.</p></section><div id="backupPolicy"></div>':''}</div>`;
 function describe(){
  const single=f.kind==='presenze_centro',hr=['dipendenti','onboarding'].includes(f.kind);
  $('#exportDescription').textContent=exportKinds[f.kind][1];
  $('#exportLayerLabel').hidden=!single;$('#exportToLabel').hidden=single||hr;$('#exportFromLabel').hidden=hr;
  $('#exportLayer').disabled=!single;$('#exportTo').disabled=single||hr;$('#exportFrom').disabled=hr;
  $('#exportHint').textContent=single?'Seleziona un solo centro e il mese da esportare.':hr?'Prospetto riservato: può contenere dati personali. È richiesta una verifica di sicurezza recente.':f.kind==='accordi'?'Fino a 24 mesi. Gli importi non calcolabili restano vuoti. È richiesta una verifica di sicurezza recente.':'Fino a 24 mesi. Le ore mancanti restano non disponibili; i totali includono solo quelle registrate.';
 }
 $('#exportKind').onchange=e=>{f.kind=e.target.value;describe()};$('#exportCenter').onchange=e=>{f.cid=e.target.value};
 $('#exportFrom').onchange=e=>{f.first=e.target.value};$('#exportTo').onchange=e=>{f.last=e.target.value};$('#exportLayer').onchange=e=>{f.layer=e.target.value};
 $('#exportForm').onsubmit=async e=>{
  e.preventDefault();const btn=$('#exportDownload');btn.disabled=true;$('#exportError').textContent='';
  try{
   if(f.kind==='presenze_centro'&&f.cid==='all')throw Error('Scegli un centro per il registro mensile, oppure il prospetto Presenze complessive.');
   const hr=['dipendenti','onboarding'].includes(f.kind),first=hr?month:f.first;
   const query={...f,first,last:f.kind==='presenze_centro'||hr?first:f.last};
   await downloadFile('export_xlsx?'+statsQuery(query)+'&kind='+f.kind+'&layer='+f.layer,'Presenze_'+f.kind+'_'+first+'.xlsx');
   toast('File Excel pronto per il download.');
  }catch(x){if(request===exportsRequest&&$('#exportError'))$('#exportError').innerHTML='<div class="error">'+esc(x.message)+'</div>'}finally{if(btn.isConnected)btn.disabled=false}
 };
 describe();
 if(superadmin()){
  $('#backupNow').onclick=async()=>{const btn=$('#backupNow');btn.disabled=true;try{await api('backup',{});await loadBackups(request);toast('Backup creato e integrità verificata.')}catch(e){toast(e.message)}finally{if(btn.isConnected)btn.disabled=false}};
  await Promise.all([loadBackups(request),renderBackupPolicy($('#backupPolicy'))]);
 }
}
function exportBytes(n){return n<1024*1024?(n/1024).toLocaleString('it-IT',{maximumFractionDigits:1})+' KB':(n/1024/1024).toLocaleString('it-IT',{maximumFractionDigits:1})+' MB'}
async function loadBackups(request){
 try{
  const data=await api('backups');if(request!==exportsRequest||tab!=='esportazioni'||!$('#backupBody'))return;
  $('#backupBody').innerHTML=`<div class="export-backup-stats"><div><strong>${data.count}</strong><span>copie sul server</span></div><div><strong>${exportBytes(data.bytes)}</strong><span>spazio occupato</span></div><p>${esc(data.automatic_policy)}</p></div><div class="table-scroll"><table class="data-table export-backup-table"><thead><tr><th>Creato il</th><th>Dimensione</th><th>Download</th></tr></thead><tbody>${data.files.map(b=>`<tr><td><b>${new Date(b.created_at).toLocaleString('it-IT',{dateStyle:'medium',timeStyle:'short'})}</b><small>${esc(b.filename)}</small></td><td>${exportBytes(b.bytes)}</td><td>${b.downloadable?`<button class="btn small" data-backup-file="${esc(b.filename)}">Scarica copia</button>`:'Copia dal server (oltre 256 MiB)'}</td></tr>`).join('')||'<tr><td colspan="3">Nessun backup disponibile. Crea la prima copia.</td></tr>'}</tbody></table></div>${data.count>data.shown?`<p class="muted smalltext">Mostrate le ${data.shown} copie più recenti. Nessuna copia viene eliminata automaticamente.</p>`:'<p class="muted smalltext">Nessuna copia viene eliminata automaticamente.</p>'}`;
  document.querySelectorAll('[data-backup-file]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await downloadFile('backup_download?filename='+encodeURIComponent(b.dataset.backupFile),b.dataset.backupFile)}catch(e){toast(e.message)}finally{if(b.isConnected)b.disabled=false}});
 }catch(e){if(request===exportsRequest&&$('#backupBody'))$('#backupBody').innerHTML='<div class="error">'+esc(e.message)+'</div>'}
}
