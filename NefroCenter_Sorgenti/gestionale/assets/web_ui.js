/* Browser UI for the server-enforced authentication flow. No credentials persist in browser storage. */
let authRecovery=false, dashboardTimer=null;
const roleName={admin:'Amministratore',hr:'HR centrale',manager:'Responsabile centro',operator:'Compilatore',viewer:'Direzione / lettore'};

async function api(path,data,retry=true,background=false){
 const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:{'X-Presenze-Token':token,...(background?{'X-Background-Refresh':'1'}:{}),...(data===undefined?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:JSON.stringify(data)});
 const out=await r.json();if(out.csrf)token=out.csrf;
 if(!r.ok){
  if(r.status===428&&retry){await stepUpDialog();return api(path,data,false,background)}
  if(r.status===401&&!['login','mfa','enroll/start','enroll/confirm','security/stepup'].includes(path)){auth=null;state=null;$('#modal').close();await boot()}
  throw Error(out.error||'Operazione non riuscita.');
 }
 return out;
}

async function boot(){
 clearTimeout(dashboardTimer);
 try{auth=await api('auth');if(!auth.user){renderAuth();return}
  if(!auth.centers.length){$('#app').innerHTML='<main><section class="panel"><h1>Nessun centro assegnato</h1><p>Il tuo accesso è verificato. Chiedi all’amministratore di assegnarti un centro.</p><button class="btn" id="logoutEmpty">Esci</button></section></main>';$('#logoutEmpty').onclick=logout;return}
  if(!auth.centers.some(c=>c.id===cid))cid=auth.centers[0].id;await load();
 }catch(e){toast(e.message)}
}

async function logout(){
 if(tab==='dipendenti'&&!hrSafeLeave())return;if(tab==='comunicazioni'&&!communicationsSafeLeave())return;if(tab==='promemoria'&&!remindersSafeLeave())return;clearTimeout(dashboardTimer);hrPid=null;hrDirty=false;
 await api('logout',{});approvalsReset();staffingRequest++;departuresRequest++;remindersReset();communicationsReset();communicationsOwner='';communicationsRequest++;statsFilters=null;exportFilters=null;statsRequest++;exportsRequest++;clearTimeout(window.toastTimer);$('#toast').style.display='none';auth=null;state=null;token='';authRecovery=false;await boot();
}

function authShell(title,lead,content,step){
 $('#app').classList.remove('app-shell');
 $('#app').innerHTML=`<div class="web-login"><aside class="web-welcome"><img src="/assets/nefrocenter.png" alt="NefroCenter" class="web-logo"><div class="web-welcome-copy"><span class="web-eyebrow">PERSONE E PRESENZE</span><h1>Ogni centro.<br>Un unico spazio.</h1><p>Le persone, i turni e le attività di ingresso. Tutto ciò che serve, con gli accessi giusti.</p><div class="web-trust"><span class="web-shield" aria-hidden="true">✓</span><div><b>Accesso a due fattori</b><small>La tua password e un codice personale.</small></div></div></div><span class="web-welcome-foot">Gruppo NefroCenter · Area riservata</span></aside><main class="web-login-main"><div class="web-auth-card"><div class="web-login-tag">PORTALE DEL PERSONALE</div><div class="web-steps" aria-label="Passaggi di accesso"><span class="${step===1?'current':'done'}">1 · Credenziali</span><span class="${step===2?'current':''}">2 · Verifica</span></div><h1>${title}</h1><p class="muted">${lead}</p>${content}<p class="web-auth-foot">Account nominativi · Autorizzazioni per centro</p></div></main></div>`;
}

function authError(e){const box=$('#authError');if(box)box.innerHTML='<div class="error">'+esc(e.message)+'</div>';else toast(e.message)}
function bindAuthForm(fn){$('#authForm').onsubmit=async e=>{e.preventDefault();const btn=e.currentTarget.querySelector('[type=submit]');btn.disabled=true;try{await fn()}catch(x){authError(x)}finally{if(btn.isConnected)btn.disabled=false}}}
function authBack(){return '<button type="button" class="web-text-button" id="authBack">← Cambia account</button>'}
function wireBack(){$('#authBack').onclick=async()=>{await api('logout',{});authRecovery=false;await boot()}}

function renderAuth(){
 if(!auth.configured){authShell('Portale da attivare','L’amministratore deve completare la configurazione sul server.','<div class="note">Nessun account predefinito. Contatta il referente IT del gruppo.</div>',1);return}
 if(auth.stage==='mfa')return renderMfa();
 if(auth.stage==='enroll')return renderEnrollment();
 authShell('Bentornato.','Accedi con le credenziali assegnate al tuo account.',`<form id="authForm"><div class="field"><label for="authUser">Nome utente</label><input id="authUser" required maxlength="60" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="nome.cognome"></div><div class="field"><label for="authPassword">Password</label><input id="authPassword" type="password" required maxlength="256" autocomplete="current-password" placeholder="La tua password"></div><div id="authError" role="alert"></div><button type="submit" class="btn primary web-wide">Continua <span aria-hidden="true">→</span></button></form><p class="web-login-help">Hai perso l’accesso? Il referente del tuo centro può richiedere il ripristino all’amministratore.</p>`,1);
 bindAuthForm(async()=>{auth=await api('login',{username:$('#authUser').value,password:$('#authPassword').value});renderAuth()});$('#authUser').focus();
}

function renderMfa(){
 authShell(authRecovery?'Usa un codice di recupero.':'Conferma che sei tu.',authRecovery?'Inserisci uno dei codici conservati durante l’attivazione. Ogni codice si può usare una sola volta.':'Apri la tua app Authenticator e inserisci il codice a 6 cifre.',`<form id="authForm"><div class="field"><label for="authCode">${authRecovery?'Codice di recupero':'Codice Authenticator'}</label><input id="authCode" class="web-otp ${authRecovery?'recovery':''}" inputmode="${authRecovery?'text':'numeric'}" autocomplete="one-time-code" required maxlength="${authRecovery?50:6}" ${authRecovery?'':'pattern="[0-9]{6}"'} placeholder="${authRecovery?'XXXX-XXXX-XXXX-XXXX':'000000'}"></div><div id="authError" role="alert"></div><button type="submit" class="btn primary web-wide">Verifica e accedi</button></form><div class="web-auth-links"><button class="web-text-button" id="useRecovery">${authRecovery?'Usa Authenticator':'Usa un codice di recupero'}</button>${authBack()}</div>`,2);
 bindAuthForm(async()=>{auth=await api('mfa',{code:$('#authCode').value.trim(),recovery:authRecovery});authRecovery=false;await boot()});$('#useRecovery').onclick=()=>{authRecovery=!authRecovery;renderMfa()};wireBack();$('#authCode').focus();
}

function renderEnrollment(){
 authShell('Proteggi il tuo accesso.','Per il primo accesso serve il codice di attivazione ricevuto dall’amministratore.',`<form id="authForm"><div class="field"><label for="activationCode">Codice di attivazione</label><input id="activationCode" required autocomplete="off" spellcheck="false" maxlength="100" placeholder="Incolla il codice riservato"></div><div id="authError" role="alert"></div><button type="submit" class="btn primary web-wide">Configura Authenticator</button></form>${authBack()}`,2);
 bindAuthForm(async()=>{const data=await api('enroll/start',{activation:$('#activationCode').value.trim()});renderQr(data,false)});wireBack();$('#activationCode').focus();
}

function qrBody(data,rotation){
 return `<div class="web-qr-row"><div class="web-qr"><img src="${data.qr}" alt="QR per configurare il secondo fattore nell’app Authenticator" width="220" height="220"></div><div><h2>Collega la tua app</h2><p class="muted">Aggiungi un account nell’app Authenticator e scansiona il QR.</p><details class="web-manual"><summary>Inserimento manuale</summary><p>Account: ${esc(data.account)}</p><code class="web-secret">${esc(data.secret)}</code><small>Codice temporaneo · 6 cifre · 30 secondi · SHA-1</small></details></div></div><form id="${rotation?'rotateForm':'authForm'}"><div class="field"><label for="${rotation?'rotateCode':'authCode'}">Codice mostrato dall’app</label><input id="${rotation?'rotateCode':'authCode'}" class="web-otp" inputmode="numeric" autocomplete="one-time-code" required pattern="[0-9]{6}" maxlength="6" placeholder="000000"></div>${rotation?'':`<div class="field"><label for="ownPassword">Scegli la tua password · almeno 12 caratteri</label><input id="ownPassword" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></div><div class="field"><label for="ownPasswordRepeat">Ripeti la password</label><input id="ownPasswordRepeat" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></div>`}<div id="${rotation?'rotationError':'authError'}" role="alert"></div><button type="submit" class="btn primary web-wide">${rotation?'Conferma nuovo dispositivo':'Attiva la protezione'}</button></form>`;
}

function renderQr(data){
 authShell('Attiva il secondo fattore.','Usa un’app compatibile con i codici TOTP: la generazione dei codici non richiede SMS.',qrBody(data,false)+authBack(),2);
 bindAuthForm(async()=>{if($('#ownPassword').value!==$('#ownPasswordRepeat').value)throw Error('Le password non coincidono.');const result=await api('enroll/confirm',{code:$('#authCode').value,new_password:$('#ownPassword').value});auth=result;showRecovery(result.recovery_codes,()=>boot(),true)});wireBack();
}

function downloadText(name,text,type='text/plain;charset=utf-8'){
 const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function showRecovery(codes,done,full=false){
 const body=`<div class="note">Conserva questi codici in un luogo riservato, separato dal dispositivo Authenticator. Ognuno funziona una sola volta. Non saranno più mostrati.</div><div class="web-recovery-codes">${codes.map(c=>'<code>'+esc(c)+'</code>').join('')}</div><button class="btn web-wide" id="downloadCodes">Scarica i codici di recupero</button><label class="check web-ack"><input type="checkbox" id="codesAck"> Ho conservato i codici in un luogo sicuro</label><button class="btn primary web-wide" id="codesDone" disabled>Continua al portale</button>`;
 if(full)authShell('Il tuo accesso è protetto.','Ora conserva i codici di recupero.',body,2);else modal('Conserva i nuovi codici',body);
 $('#downloadCodes').onclick=()=>downloadText('Codici_recupero_Presenze.txt','NefroCenter · Persone e Presenze\nAccount: '+(auth?.user?.username||'')+'\nCodici monouso. Conservare separatamente da password e telefono.\n\n'+codes.join('\n'));
 $('#codesAck').onchange=e=>$('#codesDone').disabled=!e.target.checked;
 $('#codesDone').onclick=()=>{if(!full)$('#modal').close();done()};
}

function stepUpDialog(){
 return new Promise((resolve,reject)=>{
  let d=$('#securityPrompt');if(!d){d=document.createElement('dialog');d.id='securityPrompt';document.body.append(d)}
  d.innerHTML=`<div class="dialog-top"><h2>Conferma di sicurezza</h2><button class="x" id="cancelStepup" aria-label="Annulla">×</button></div><form id="stepupForm" class="dialog-body"><p class="muted">Per questa operazione verifica di nuovo la password e il secondo fattore.</p><div class="field"><label for="stepupPassword">Password attuale</label><input id="stepupPassword" type="password" required autocomplete="current-password"></div><div class="field"><label for="stepupCode">Codice Authenticator o codice di recupero</label><input id="stepupCode" required autocomplete="one-time-code" maxlength="50"></div><label class="check"><input type="checkbox" id="stepupRecovery"> Sto usando un codice di recupero</label><div id="stepupError" role="alert"></div><button type="submit" class="btn primary web-wide">Conferma</button></form>`;
  let settled=false;const cancel=()=>{if(settled)return;settled=true;d.close();d.innerHTML='';reject(Error('Operazione annullata.'))};d.oncancel=e=>{e.preventDefault();cancel()};$('#cancelStepup').onclick=cancel;
  $('#stepupForm').onsubmit=async e=>{e.preventDefault();const btn=e.currentTarget.querySelector('button');btn.disabled=true;try{await api('security/stepup',{password:$('#stepupPassword').value,code:$('#stepupCode').value.trim(),recovery:$('#stepupRecovery').checked},false);settled=true;d.close();d.innerHTML='';resolve()}catch(x){$('#stepupError').textContent=x.message;btn.disabled=false}};d.showModal();$('#stepupPassword').focus();
 });
}

async function renderDashboard(background=false){
 clearTimeout(dashboardTimer);const selectedMonth=month;const data=await api('overview?month='+month,undefined,true,background);if(tab!=='dashboard'||month!==selectedMonth)return;
 const rows=data.centers,sum=k=>rows.reduce((n,c)=>n+c[k],0);
 document.querySelector('main .heading .eyebrow').textContent='CENTRI ASSEGNATI';$('#centerSelect').hidden=true;document.querySelector('main .heading .muted').textContent=monthName()+' · Archivio centrale condiviso';
 $('#monthPick').closest('.actions').querySelectorAll('.tag,.badge-lock').forEach(e=>e.hidden=true);
 $('#content').innerHTML=`<div class="metrics web-dashboard-metrics"><div class="metric"><div class="label">Centri accessibili</div><div class="number">${rows.length}</div><div class="foot">Secondo le tue autorizzazioni</div></div><div class="metric"><div class="label">Ore consuntive</div><div class="number">${mins(sum('minutes'))}</div><div class="foot">${sum('shifts')} turni registrati</div></div><div class="metric"><div class="label">Mesi chiusi</div><div class="number">${rows.filter(c=>c.closed).length}<small> / ${rows.length}</small></div><div class="foot">${rows.filter(c=>!c.recorded).length} centri senza registrazioni</div></div><div class="metric"><div class="label">Da completare</div><div class="number">${sum('pending')+sum('missing')}</div><div class="foot">Pianificazioni e turni senza orari</div></div></div><section class="panel work-area"><div class="toolbar"><div><h2>Situazione dei centri</h2><p class="muted smalltext">Le modifiche salvate sono disponibili nello stesso archivio.</p></div><div class="actions"><button class="btn" id="refreshDashboard">Aggiorna</button>${['admin','hr','viewer'].includes(auth.user.role)?'<button class="btn primary" id="groupExport">Esporta CSV</button>':''}</div></div><div class="table-scroll"><table class="data-table web-centers"><thead><tr><th>Centro</th><th>Compilazione</th><th>Persone</th><th>Ore</th><th>Stato mese</th><th>Ultima attività</th><th></th></tr></thead><tbody>${rows.map(c=>`<tr><td><b>${esc(c.name)}</b><small class="hr-secondary">${esc(c.code)}</small></td><td><span class="tag ${c.recorded?'green':'warn'}">${c.recorded?'Presenze inserite':'Da compilare'}</span></td><td>${c.people}</td><td class="web-tabular">${mins(c.minutes)}</td><td>${c.closed?'Chiuso':'Aperto'}</td><td class="smalltext">${c.last_update?esc(new Date(c.last_update).toLocaleString('it-IT',{dateStyle:'short',timeStyle:'short'})):'—'}</td><td><button class="btn small" data-dash-center="${c.id}">Apri centro</button></td></tr>`).join('')}</tbody></table></div></section><p class="footer-note">Vista aggiornata alle ${new Date(data.generated_at).toLocaleTimeString('it-IT')} · Aggiornamento ogni minuto. In assenza di rete, le modifiche non possono essere salvate.</p>`;
 $('#refreshDashboard').onclick=()=>renderDashboard().catch(e=>toast(e.message));document.querySelectorAll('[data-dash-center]').forEach(b=>b.onclick=()=>{cid=b.dataset.dashCenter;tab='presenze';load().catch(e=>toast(e.message))});
 if($('#groupExport'))$('#groupExport').onclick=async()=>{try{const r=await fetch('/api/group_export?month='+month,{credentials:'same-origin'});if(!r.ok)throw Error((await r.json()).error);downloadText('Presenze_Gruppo_'+month+'.csv',await r.text(),'text/csv;charset=utf-8')}catch(e){toast(e.message)}};
 dashboardTimer=setTimeout(()=>{if(tab==='dashboard')renderDashboard(true).catch(e=>toast(e.message))},60000);
}

function renderCenters(){
 $('#content').innerHTML=`${superadmin()?'<div class="actions" style="margin-bottom:20px"><button class="btn primary" id="newCenter">+ Aggiungi centro</button><button class="btn" id="importExcel">Importa modello Excel</button><button class="btn" id="backup">Crea backup sul server</button></div>':''}<div class="center-list">${auth.centers.map(c=>`<section class="panel center-card"><div class="eyebrow">${esc(c.code)}</div><h2>${esc(c.name)}</h2><p class="muted smalltext">Parametri versione ${c.version}</p><button class="btn" data-center-open="${c.id}">${admin()?'Configura centro':'Apri presenze'}</button></section>`).join('')}</div><p class="footer-note">Tutti i centri lavorano sul database centrale. Il tuo profilo determina quali centri e funzioni puoi usare.</p>`;
 document.querySelectorAll('[data-center-open]').forEach(b=>b.onclick=()=>{cid=b.dataset.centerOpen;tab=admin()?'parametri':'presenze';load().catch(e=>toast(e.message))});if(!superadmin())return;
 $('#newCenter').onclick=()=>{modal('Aggiungi un centro',`<div class="formgrid"><div class="field full"><label for="newCenterName">Nome struttura</label><input id="newCenterName"></div><div class="field"><label for="newCenterCode">Codice centro</label><input id="newCenterCode" placeholder="POSILLIPO"></div><div class="field"><label for="copyCenter">Configurazione iniziale</label><select id="copyCenter"><option value="">Valori iniziali da verificare</option>${auth.centers.map(c=>`<option value="${c.id}">Copia ${esc(c.name)}</option>`).join('')}</select></div></div>`,'<button class="btn primary" id="saveCenter">Crea centro</button>');$('#saveCenter').onclick=async()=>{try{await change('center_create',{name:$('#newCenterName').value,code:$('#newCenterCode').value,copy_from:$('#copyCenter').value});$('#modal').close();tab='parametri';render()}catch(e){modalError(e)}}};
 $('#importExcel').onclick=()=>$('#fileInput').click();$('#backup').onclick=async()=>{try{const r=await api('backup',{});toast('Backup verificato creato sul server: '+r.filename)}catch(e){toast(e.message)}};
}

function renderUsers(){
 if(!superadmin()){tab='dashboard';render();return}
 $('#content').innerHTML=`<section class="panel"><div class="toolbar"><div><h2>Accessi nominativi</h2><p class="muted smalltext">Secondo fattore obbligatorio per tutti gli account.</p></div><button class="btn primary" id="newUser">+ Nuovo utente</button></div><div class="table-scroll"><table class="data-table web-centers"><thead><tr><th>Utente</th><th>Profilo</th><th>Centri</th><th>2FA</th><th>Stato</th><th></th></tr></thead><tbody>${state.users.map(u=>`<tr><td><b>${esc(u.name)}</b><small class="hr-secondary">${esc(u.username)}</small></td><td>${roleName[u.role]}</td><td>${['admin','hr'].includes(u.role)?'Tutti':u.centers.map(id=>esc(auth.centers.find(c=>c.id===id)?.name||id)).join(', ')}</td><td><span class="tag ${u.mfa_enabled?'green':'warn'}">${u.mfa_enabled?'Attivo':'Da attivare'}</span></td><td>${u.active?'Attivo':'Disabilitato'}</td><td><div class="actions"><button class="btn small" data-user="${u.id}">Modifica</button>${u.id!==auth.user.id?`<button class="btn small" data-reset-mfa="${u.id}">Ripristina 2FA</button>`:''}</div></td></tr>`).join('')}</tbody></table></div></section><div class="note">Il responsabile del centro gestisce presenze, parametri e fascicoli dei soli centri assegnati. Il compilatore inserisce le presenze. Il lettore consulta i centri assegnati. HR centrale gestisce fascicoli e documenti di tutti i centri e consulta presenze ed esportazioni. Solo l’amministratore gestisce gli account.</div>`;
 $('#newUser').onclick=()=>userDialog();document.querySelectorAll('[data-user]').forEach(b=>b.onclick=()=>userDialog(state.users.find(u=>u.id===b.dataset.user)));
 document.querySelectorAll('[data-reset-mfa]').forEach(b=>b.onclick=()=>{const u=state.users.find(u=>u.id===b.dataset.resetMfa);modal('Ripristina accesso di '+u.name,'<p>Verifica prima l’identità della persona. Il ripristino revoca dispositivo precedente, codici di recupero e sessioni.</p><div class="field"><label for="resetReason">Motivazione e riferimento della verifica</label><textarea id="resetReason" minlength="8"></textarea></div>','<button class="btn primary" id="confirmReset">Genera nuova attivazione</button>');$('#confirmReset').onclick=async()=>{try{const r=await api('security/reset_user',{user_id:u.id,reason:$('#resetReason').value});await load();showActivation(r.activation_code,u.username)}catch(e){modalError(e)}}});
}

function showActivation(code,username){
 modal('Attivazione di '+username,`<div class="note">Consegna questo codice riservatamente alla persona dopo averne verificato l’identità. È valido 7 giorni e viene mostrato una sola volta.</div><code class="web-activation">${esc(code)}</code><p>Al primo accesso sono richiesti password iniziale, questo codice, configurazione Authenticator e scelta della password personale.</p><button class="btn" id="downloadActivation">Scarica istruzioni riservate</button>`,'<button class="btn primary" id="activationDone">Ho conservato il codice</button>');
 $('#downloadActivation').onclick=()=>downloadText('Attivazione_'+username+'.txt','NefroCenter · Accesso al portale del personale\nUtente: '+username+'\nCodice di attivazione 2FA (7 giorni): '+code+'\n\nUsare la password iniziale fornita separatamente. Al primo accesso configurare Authenticator e scegliere la password personale.\n');$('#activationDone').onclick=()=>$('#modal').close();
}

function userDialog(u){
 modal(u?'Modifica utente':'Crea utente',`<div class="formgrid"><div class="field"><label for="userName">Nome</label><input id="userName" value="${esc(u?.name||'')}"></div><div class="field"><label for="userLogin">Nome utente</label><input id="userLogin" value="${esc(u?.username||'')}"></div><div class="field"><label for="userRole">Profilo</label><select id="userRole">${Object.entries(roleName).map(([v,t])=>`<option value="${v}" ${u?.role===v||!u&&v==='operator'?'selected':''}>${t}</option>`).join('')}</select></div><div class="field"><label for="userPassword">${u?'Nuova password · vuoto per mantenerla':'Password iniziale · almeno 12 caratteri'}</label><input id="userPassword" type="password" autocomplete="new-password" maxlength="256"></div><div class="field full" id="userCenterAssignment"><label>Centri assegnati</label><p class="muted smalltext" id="userCenterScope"></p><div class="checks">${auth.centers.map(c=>`<label class="check"><input name="userCenter" type="checkbox" value="${c.id}" ${u?.centers.includes(c.id)?'checked':''}>${esc(c.name)}</label>`).join('')}</div></div><label class="check"><input id="userActive" type="checkbox" ${u?.active!==false?'checked':''}>Account attivo</label></div><p class="footer-note">Le modifiche revocano le sessioni. Il cambio password non disabilita il secondo fattore.</p>`,'<button class="btn primary" id="saveUser">Salva utente</button>');
 function updateUserScope(){const global=['admin','hr'].includes($('#userRole').value);$('#userCenterScope').textContent=global?'Accesso a tutti i centri del gruppo, inclusi quelli aggiunti in futuro. Nessuna assegnazione manuale necessaria.':'Seleziona almeno un centro autorizzato.';document.querySelectorAll('[name=userCenter]').forEach(el=>el.disabled=global)}
 $('#userRole').onchange=updateUserScope;updateUserScope();
 $('#saveUser').onclick=async()=>{const btn=$('#saveUser');btn.disabled=true;try{const username=$('#userLogin').value;const r=await api('user_save',{user:{id:u?.id,name:$('#userName').value,username,role:$('#userRole').value,password:$('#userPassword').value,active:$('#userActive').checked,centers:[...document.querySelectorAll('[name=userCenter]:checked')].map(x=>x.value)}});$('#modal').close();await boot();if(r.activation_code)showActivation(r.activation_code,username);else toast('Utente aggiornato.')}catch(e){modalError(e);btn.disabled=false}};
}

async function renderSecurity(){
 const s=await api('security');if(tab!=='sicurezza')return;
 document.querySelector('main .heading .eyebrow').textContent='ACCOUNT PERSONALE';$('#centerSelect').hidden=true;document.querySelector('main .heading .muted').textContent='Password, Authenticator e accessi personali';
 $('#content').innerHTML=`<div class="web-security-grid"><section class="panel"><span class="tag green">2FA obbligatorio · attivo</span><h2 style="margin-top:16px">Il tuo accesso è protetto</h2><p class="muted">${esc(auth.user.username)} · Password e app Authenticator</p><div class="web-security-row"><div><b>App Authenticator</b><small>Collega un nuovo dispositivo prima di dismettere il precedente.</small></div><button class="btn" id="rotateMfa">Cambia dispositivo</button></div><div class="web-security-row"><div><b>Codici di recupero</b><small>${s.recovery_remaining} codici ancora disponibili</small></div><button class="btn" id="newRecovery">Rigenera codici</button></div><div class="web-security-row"><div><b>Password personale</b><small>Il cambio disconnette tutte le sessioni.</small></div><button class="btn" id="changePassword">Cambia password</button></div><div class="web-security-row"><div><b>Sessioni attive</b><small>${s.sessions} accessi verificati</small></div><button class="btn" id="revokeSessions">Esci dagli altri dispositivi</button></div></section><section class="panel"><h2>Attività del tuo account</h2><div class="web-security-history">${s.history.map(x=>`<div><b>${esc(x.action)}</b><small>${esc(new Date(x.stamp).toLocaleString('it-IT'))}</small></div>`).join('')}</div></section></div>`;
 $('#changePassword').onclick=changePassword;
 $('#newRecovery').onclick=()=>{modal('Sostituisci i codici di recupero','<p>I codici attuali non funzioneranno più. Conserva quelli nuovi prima di chiudere la finestra.</p>','<button class="btn primary" id="confirmRecovery">Genera nuovi codici</button>');$('#confirmRecovery').onclick=async()=>{try{const r=await api('security/recovery',{});showRecovery(r.recovery_codes,()=>renderSecurity())}catch(e){modalError(e)}}};
 $('#revokeSessions').onclick=async()=>{try{await api('security/sessions',{});await renderSecurity();toast('Altre sessioni revocate.')}catch(e){toast(e.message)}};
 $('#rotateMfa').onclick=async()=>{try{const r=await api('security/rotate/start',{});modal('Collega il nuovo dispositivo',qrBody(r,true));$('#rotateForm').onsubmit=async e=>{e.preventDefault();try{const result=await api('security/rotate/confirm',{code:$('#rotateCode').value});auth=result;showRecovery(result.recovery_codes,()=>renderSecurity())}catch(x){$('#rotationError').textContent=x.message}}}catch(e){toast(e.message)}};
}

function changePassword(){
 modal('Cambia la tua password','<div class="formgrid"><div class="field full"><label for="currentPassword">Password attuale</label><input id="currentPassword" type="password" autocomplete="current-password"></div><div class="field full"><label for="nextPassword">Nuova password · almeno 12 caratteri</label><input id="nextPassword" type="password" minlength="12" maxlength="256" autocomplete="new-password"></div><div class="field full"><label for="repeatPassword">Ripeti nuova password</label><input id="repeatPassword" type="password" autocomplete="new-password"></div></div>','<button class="btn primary" id="savePassword">Cambia password</button>');$('#savePassword').onclick=async()=>{try{if($('#nextPassword').value!==$('#repeatPassword').value)throw Error('Le password non coincidono.');await api('password',{current:$('#currentPassword').value,password:$('#nextPassword').value});$('#modal').close();await boot();toast('Password aggiornata. Accedi di nuovo con il secondo fattore.')}catch(e){modalError(e)}};
}
window.addEventListener('online',()=>toast('Connessione ripristinata. Ricarica i dati prima di salvare.'));
window.addEventListener('offline',()=>toast('Connessione assente. I dati non possono essere salvati finché la rete non torna disponibile.'));
boot();
