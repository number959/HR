/* Una scheda per centro: i fascicoli leggono sempre i recapiti condivisi. */
let structureFocus='',structureRequest=0;
const structureLabels={legal_name:'Ragione sociale',vat_number:'Partita IVA',tax_code:'Codice fiscale',address:'Indirizzo',city:'Comune',postal_code:'CAP',province:'Provincia',phone:'Telefono',email:'Email generale',hr_email:'Email ufficio HR',admin_email:'Email amministrazione',pec:'PEC',contact_name:'Referente della struttura',director:'Direttore',website:'Sito web',notes:'Note organizzative'};

function structureDetailsMarkup(structure){
 if(!structure)return '<p class="muted">Dati della struttura non disponibili. Apri la rubrica per consultarli.</p>';
 const f=structure.fields||{};
 return `<dl class="structure-details">${Object.entries(structureLabels).map(([key,label])=>`<div class="${key==='notes'?'full':''}"><dt>${esc(label)}</dt><dd>${esc(f[key]||'Da indicare')}</dd></div>`).join('')}</dl>`;
}

async function renderStructures(){
 if(!hrAccess())return;
 const request=++structureRequest,data=await api('structures?cid=all');
 if(tab!=='strutture'||request!==structureRequest)return;
 $('#content').innerHTML=`<div class="structure-intro"><div><p class="eyebrow">RUBRICA STRUTTURE</p><h2>Recapiti condivisi, sempre aggiornati.</h2><p class="muted">Ogni dipendente trova nel fascicolo i dati del proprio centro. Un aggiornamento della scheda è subito visibile a tutti i fascicoli della struttura.</p></div><div class="actions"><input class="structure-search" id="structureSearch" type="search" aria-label="Cerca struttura" placeholder="Cerca nome, codice o referente"></div></div><div id="structureCards" class="structure-grid"></div><p class="footer-note">Le schede sono visibili a HR centrale, amministratori e responsabili dei centri assegnati. Nome, codice e assegnazioni si gestiscono nelle rispettive anagrafiche.</p>`;
 function draw(){
  const q=$('#structureSearch').value.trim().toLocaleLowerCase('it-IT'),rows=data.structures.filter(s=>[s.name,s.code,...Object.values(s.fields)].join(' ').toLocaleLowerCase('it-IT').includes(q));
  $('#structureCards').innerHTML=rows.map(s=>`<section class="panel structure-card"><div><p class="eyebrow">${esc(s.code)}</p><h3>${esc(s.name)}</h3></div><p class="muted">${esc(s.fields.legal_name||'Ragione sociale da indicare')}</p><dl class="structure-details"><div><dt>Email HR</dt><dd>${esc(s.fields.hr_email||'Da indicare')}</dd></div><div><dt>Telefono</dt><dd>${esc(s.fields.phone||'Da indicare')}</dd></div><div><dt>Comune</dt><dd>${esc(s.fields.city||'Da indicare')}</dd></div><div><dt>Referente</dt><dd>${esc(s.fields.contact_name||'Da indicare')}</dd></div></dl><div class="actions"><button class="btn primary" data-structure-open="${esc(s.cid)}">Apri scheda</button><span class="muted smalltext">${s.version?'Versione '+s.version:'Da compilare'}</span></div></section>`).join('')||'<div class="panel"><p class="muted">Nessuna struttura trovata tra i centri autorizzati.</p></div>';
  document.querySelectorAll('[data-structure-open]').forEach(b=>b.onclick=()=>structureEdit(data.structures.find(s=>s.cid===b.dataset.structureOpen),data.fields));
 }
 draw();$('#structureSearch').oninput=draw;
 const focus=structureFocus;structureFocus='';if(focus){const selected=data.structures.find(s=>s.cid===focus);if(selected)structureEdit(selected,data.fields)}
}

function structureEdit(structure,definitions){
 let dirty=false,busy=false;
 const sections=[...new Set(definitions.map(f=>f.section))],controls=definitions.map(f=>({...f,value:structure.fields[f.key]||''}));
 modal('Scheda struttura · '+structure.name,`<p class="muted smalltext">${esc(structure.code)} · ${structure.version?'Versione '+structure.version:'Scheda da compilare'}. I recapiti vengono condivisi con tutti i fascicoli di questo centro.</p><form id="structureForm" class="structure-editor">${sections.map(section=>`<h3>${esc(section)}</h3><div class="formgrid">${controls.filter(f=>f.section===section).map(f=>`<div class="field ${f.type==='textarea'?'full':''}"><label for="structure_${esc(f.key)}">${esc(f.label)}</label>${f.type==='textarea'?`<textarea id="structure_${esc(f.key)}" data-structure-field="${esc(f.key)}" maxlength="${f.max_length}">${esc(f.value)}</textarea>`:`<input id="structure_${esc(f.key)}" data-structure-field="${esc(f.key)}" type="${f.type}" maxlength="${f.max_length}" value="${esc(f.value)}" ${f.type==='url'?'placeholder="https://www.esempio.it"':''}>`}</div>`).join('')}</div>`).join('')}<p id="structureSaveState" class="muted smalltext" role="status">Campi facoltativi: compila solo i dati disponibili.</p></form>`,'<button type="submit" form="structureForm" class="btn primary" id="structureSave">Salva struttura</button>');
 const dialog=$('#modal'),form=$('#structureForm');
 form.oninput=()=>{dirty=true;$('#structureSaveState').textContent='Modifiche da salvare'};
 function canClose(){return !busy&&(!dirty||confirm('Ci sono modifiche non salvate alla struttura. Chiudere senza salvarle?'))}
 const cancel=e=>{if(!canClose())e.preventDefault()};dialog.addEventListener('cancel',cancel);
 dialog.addEventListener('close',()=>dialog.removeEventListener('cancel',cancel),{once:true});
 dialog.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{if(canClose())dialog.close()});
 form.onsubmit=async e=>{
  e.preventDefault();if(busy||!form.reportValidity())return;
  const fields=Object.fromEntries([...form.querySelectorAll('[data-structure-field]')].map(el=>[el.dataset.structureField,el.value]));
  busy=true;dialog.querySelectorAll('button,input,textarea').forEach(el=>el.disabled=true);
  try{await api('structure_save',{cid:structure.cid,version:structure.version,fields});dirty=false;dialog.close();if(tab==='strutture')await renderStructures();toast('Struttura aggiornata nei fascicoli del centro.')}
  catch(error){modalError(error)}finally{busy=false;dialog.querySelectorAll('button,input,textarea').forEach(el=>el.disabled=false)}
 };
}
