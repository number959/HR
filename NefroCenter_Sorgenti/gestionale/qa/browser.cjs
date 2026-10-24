const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),crypto=require('crypto');
function totp(secret){const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';for(const c of secret)bits+=alphabet.indexOf(c).toString(2).padStart(5,'0');const key=Buffer.from(bits.match(/.{8}/g).map(b=>parseInt(b,2)));const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));const mac=crypto.createHmac('sha1',key).update(b).digest(),offset=mac[19]&15;return String((mac.readUInt32BE(offset)&0x7fffffff)%1e6).padStart(6,'0')}
(async()=>{
 const outputDir=path.resolve(process.env.QA_OUTPUT_DIR||'qa-output');fs.mkdirSync(outputDir,{recursive:true});
 const launch={};if(process.env.CHROMIUM_EXECUTABLE)launch.executablePath=process.env.CHROMIUM_EXECUTABLE;if(process.env.QA_CHROMIUM_NO_SANDBOX==='1')launch.args=['--no-sandbox'];
 const browser=await chromium.launch(launch);
 const context=await browser.newContext({baseURL:process.env.WEB_URL,viewport:{width:1400,height:1000},locale:'it-IT'}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy/.test(m.text()))errors.push(m.text())});
 await page.goto(process.env.WEB_URL);await page.waitForSelector('#authUser');await page.screenshot({path:outputDir+'/v08-login.png',fullPage:true});
 await page.fill('#authUser','admin');await page.fill('#authPassword','Password-iniziale-test-2026!');await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('#activationCode');
 const denied=await page.evaluate(async()=>{const r=await fetch('/api/overview?month=2026-10');return r.status});if(denied!==403)throw Error('Password-only data leak');
 await page.fill('#activationCode',process.env.WEB_ACTIVATION);await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('.web-secret',{state:'attached'});
 const secret=await page.locator('.web-secret').textContent();await page.fill('#authCode',totp(secret));await page.fill('#ownPassword','Password-personale-test-2026!');await page.fill('#ownPasswordRepeat','Password-personale-test-2026!');await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('.web-recovery-codes');
 const codes=await page.locator('.web-recovery-codes code').allTextContents();if(codes.length!==10)throw Error('Recovery count');await page.check('#codesAck');await page.click('#codesDone');await page.waitForSelector('#refreshDashboard');console.log('Prima attivazione 2FA, password personale e codici di recupero OK');
 await page.click('[data-tab=dipendenti]');await page.click('#hrNew');await page.fill('#hr_display_name','Anna Rossi');await page.fill('#hr_registration','WEB001');await page.click('[data-hr-section=contratto]');await page.fill('#hr_start_date','2026-10-20');await page.fill('#hr_department','Dialisi');await page.click('#hrSave');await page.waitForFunction(()=>document.querySelector('#hrSaveState').textContent==='Versione 1');await page.click('[data-hr-section=onboarding]');await page.locator('[data-hr-task]').first().click();await page.selectOption('#hrTaskStatus','done');await page.click('#hrTaskSave');await page.waitForFunction(()=>!document.querySelector('#modal').open);
 await page.click('[data-hr-section=documenti]');await page.setInputFiles('#hrDocumentFile',{name:'contratto-demo.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nExample\n%%EOF')});await page.click('#hrUpload');await page.waitForSelector('[data-hr-download]');
 await page.click('[data-hr-section=anagrafica]');await page.fill('#hr_identity_type','Documento demo');await page.fill('#hr_identity_number','DOC-DEMO-001');await page.fill('#hr_identity_expiry','2027-02-01');await page.click('[data-hr-section=recapiti]');await page.fill('#hr_email','persona@example.invalid');await page.fill('#hr_company_email','azienda@example.invalid');await page.click('[data-hr-section=amministrazione]');await page.fill('#hr_iban','IT60X0542811101000000123456');await page.fill('#hr_bank_name','Banca dimostrativa');await page.fill('#hr_account_holder','Anna Rossi');await page.click('#hrSave');await page.waitForFunction(()=>document.querySelector('#hrSaveState').textContent==='Versione 3');await page.screenshot({path:outputDir+'/v08-hr-administration.png',fullPage:true});await page.click('[data-hr-section=anagrafica]');await page.screenshot({path:outputDir+'/v08-hr-profile.png',fullPage:true});
 await page.reload();await page.waitForSelector('#refreshDashboard');await page.click('[data-tab=dipendenti]');await page.locator('[data-hr]').first().click();await page.waitForSelector('#hr_identity_number');if(await page.inputValue('#hr_identity_number')!=='DOC-DEMO-001')throw Error('Identity persistence');await page.click('[data-hr-section=amministrazione]');if(await page.inputValue('#hr_iban')!=='IT60X0542811101000000123456')throw Error('IBAN persistence');await page.click('[data-hr-section=scadenze]');if(!(await page.textContent('#hrPersonalDeadlines')).includes('Documento di identità'))throw Error('Identity deadline');
 await page.click('#hrOpenAgreement');await page.waitForSelector('#saveAgreement');await page.locator('#modal [data-close]').first().click();await page.click('#hrOpenAttendance');await page.waitForSelector('#clearPersonFilter');if(await page.locator('.monthly-person-button').count()!==1)throw Error('Person attendance filter');await page.locator('[data-person-edit]').first().click();await page.waitForSelector('#hr_identity_number');
 for(const width of [390,320]){await page.setViewportSize({width,height:900});for(const section of ['anagrafica','recapiti','contratto','amministrazione','qualifiche','onboarding','documenti','scadenze']){await page.click('[data-hr-section='+section+']');if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('HR overflow '+section+' '+width)}if(width===390){await page.click('[data-hr-section=recapiti]');await page.screenshot({path:outputDir+'/v08-hr-mobile.png',fullPage:true})}}
 await page.setViewportSize({width:1400,height:1000});console.log('Dati personali e amministrativi persistenti, scadenze, collegamenti e mobile HR OK');
 const annaId=await page.evaluate(()=>hrPid);
 const otherId=await page.evaluate(async()=>{const fresh=await api(`state?cid=${cid}&month=${month}`);return (await api('hr_save',{cid,revision:fresh.center.revision,version:0,name:'Marco Bianchi',role:'INF',registration:'WEB002',active:false,stage:'incoming',fields:{first_name:'Marco',last_name:'Bianchi'},custom:{}})).pid});
 await page.route('**/api/hr?**',async route=>{const u=new URL(route.request().url());if(u.searchParams.get('pid')!==annaId)return route.continue();const response=await route.fetch();await new Promise(r=>setTimeout(r,400));await route.fulfill({response})});
 await page.evaluate(async ids=>{await Promise.all([hrOpen(ids[0]),hrOpen(ids[1])])},[annaId,otherId]);
 if(await page.evaluate(()=>hrPid)!==otherId)throw Error('RACE: la risposta in ritardo ha riaperto il dipendente precedente');
 await page.unroute('**/api/hr?**');await page.evaluate(async id=>{state=await api(`state?cid=${cid}&month=${month}`);await hrOpen(id)},annaId);
 await page.click('[data-hr-section=recapiti]');await page.fill('#hr_company_email','indirizzo non valido');await page.click('[data-hr-section=anagrafica]');await page.click('#hrSave');
 if(!await page.locator('#hr_company_email').isVisible())throw Error('VALIDATION: errore email nascosto in una sezione non visibile');
 await page.fill('#hr_company_email','azienda@example.invalid');await page.click('#hrSave');await page.waitForFunction(()=>document.querySelector('#hrSaveState').textContent==='Versione 4');
 console.log('Risposte fuori ordine e validazione dei campi nascosti OK');
 await page.route('**/api/hr_save',async route=>{const response=await route.fetch();await new Promise(r=>setTimeout(r,350));await route.fulfill({response})});
 await page.click('[data-hr-section=recapiti]');await page.fill('#hr_phone','000-DEMO');await page.click('#hrSave');await page.click('[data-tab=presenze]');
 if(await page.evaluate(()=>tab)!=='dipendenti'||!await page.locator('#hr_phone').isDisabled())throw Error('Navigazione o modifica durante salvataggio');
 await page.waitForFunction(()=>document.querySelector('#hrSaveState')?.textContent==='Versione 5');await page.unroute('**/api/hr_save');
 for(const style of ['workspace','essential','editorial','classic']){
  await page.selectOption('#interfaceStyle',style);
  for(const width of [1400,1024,390,320]){
   await page.setViewportSize({width,height:1000});
   if(await page.locator('#interfaceStyle').evaluate(el=>el.getBoundingClientRect().width)<100)throw Error('Selettore stile compresso');
   for(const section of ['anagrafica','recapiti','contratto','amministrazione','qualifiche','onboarding','documenti','scadenze']){
    await page.click('[data-hr-section='+section+']');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Overflow stile '+style+' '+section+' '+width);
   }
   await page.click('[data-hr-section=anagrafica]');
   if(width===1024||width===390)await page.screenshot({path:outputDir+'/v08-'+style+'-'+width+'.png',fullPage:true});
  }
 }
 await page.selectOption('#interfaceStyle','workspace');await page.reload();await page.waitForSelector('#interfaceStyle');if(await page.inputValue('#interfaceStyle')!=='workspace')throw Error('Persistenza stile');await page.selectOption('#interfaceStyle','classic');await page.click('[data-tab=dipendenti]');await page.locator('[data-hr]').filter({hasText:'Apri fascicolo'}).first().click();await page.waitForSelector('#hr_phone',{state:'attached'});
 console.log('Quattro stili: tutte le sezioni HR a 1400/1024/390/320 px, persistenza e ritorno ad Attuale OK');
 const firstCenter=await page.evaluate(()=>cid);const secondCenter=await page.evaluate(async()=> (await api('center_create',{name:'Centro Z demo',code:'ZDEMO'})).cid);
 const secondPerson=await page.evaluate(async center=>{
  const fresh=await api(`state?cid=${center}&month=${month}`);
  return (await api('hr_save',{cid:center,revision:fresh.center.revision,version:0,name:'Lucia Verdi',role:'MED',registration:'WEB003',active:true,stage:'active',fields:{first_name:'Lucia',last_name:'Verdi'},custom:{}})).pid;
 },secondCenter);
 await page.route('**/api/state?**',async route=>{if(new URL(route.request().url()).searchParams.get('cid')!==firstCenter)return route.continue();const response=await route.fetch();await new Promise(r=>setTimeout(r,350));await route.fulfill({response})});
 await page.evaluate(async centers=>{hrPid=null;tab='presenze';cid=centers[0];const slow=load();cid=centers[1];await Promise.all([slow,load()])},[firstCenter,secondCenter]);
 if(await page.evaluate(()=>state.center.id)!==secondCenter)throw Error('Centro errato dopo risposte fuori ordine');
 await page.unroute('**/api/state?**');await page.evaluate(async args=>{cid=args[0];hrPid=args[1];tab='dipendenti';await load()},[firstCenter,annaId]);
 await page.setViewportSize({width:1400,height:1000});console.log('Salvataggi protetti dalla navigazione e risposte fuori ordine tra centri OK');


 await page.click('[data-tab=presenze]');await page.locator('[data-day]').first().click();await page.click('#saveEntry');await page.waitForFunction(()=>!document.querySelector('#modal').open);await page.click('[data-tab=dashboard]');await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('6:00'));
 await page.click('[data-tab=presenze]');await page.selectOption('#gridWindow','week');if(await page.locator('.monthly-grid tbody tr').count()!==4)throw Error('Rows per active slot');await page.screenshot({path:outputDir+'/v08-monthly.png',fullPage:true});
 await page.click('[data-tab=accordi]');await page.waitForSelector('[data-agreement]');await page.locator('[data-agreement="'+annaId+'"]').click();await page.selectOption('#ag-basis','all');await page.fill('#ag-fixed_deduction','0');await page.check('#ag-confirmed');await page.fill('#ag-reason','Verifica accordo browser demo');await page.click('#saveAgreement');await page.waitForFunction(()=>!document.querySelector('#modal').open);await page.waitForFunction(()=>document.querySelector('.agreement-table').textContent.includes('50,00'));await page.screenshot({path:outputDir+'/v08-agreements.png',fullPage:true});
 for(const width of [390,320]){await page.setViewportSize({width,height:900});await page.click('[data-tab=presenze]');if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Monthly overflow '+width);if(width===390)await page.screenshot({path:outputDir+'/v08-monthly-mobile.png',fullPage:true});await page.click('[data-tab=accordi]');await page.waitForSelector('[data-agreement]');if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Agreement overflow '+width)}
 await page.setViewportSize({width:1400,height:1000});console.log('Griglia mensile, accordo per persona, salvataggio e mobile OK');

 // Regression: a role and HR selection from center A must not hide center B's staff.
 await page.click('[data-tab=presenze]');await page.selectOption('#roleFilter','INF');
 await page.click('[data-tab=dipendenti]');await page.locator('[data-hr="'+annaId+'"]').click();await page.waitForSelector('#hr_identity_number');
 await page.click('[data-tab=dashboard]');await page.locator('[data-dash-center="'+secondCenter+'"]').click();
 await page.waitForFunction(id=>state.center.id===id,secondCenter);await page.waitForSelector('#roleFilter');
 if(await page.inputValue('#roleFilter')!==''||await page.locator('[data-person-edit="'+secondPerson+'"]').count()!==1)throw Error('Cambio centro: filtro ruolo invisibile nasconde le persone');
 await page.click('[data-tab=dipendenti]');await page.waitForSelector('[data-hr="'+secondPerson+'"]');
 if(await page.locator('[data-hr="'+annaId+'"]').count()||await page.locator('#hr_identity_number').count())throw Error('Cambio centro: fascicolo della sede precedente');
 await page.selectOption('#centerSelect',firstCenter);await page.waitForFunction(id=>state.center.id===id,firstCenter);
 await page.waitForSelector('[data-hr="'+annaId+'"]');
 console.log('Regressioni cambio centro: filtro ruolo e archivio HR corretti OK');

 await page.click('[data-tab=statistiche]');await page.waitForSelector('.stats-metric strong');
 if(!(await page.locator('.stats-metric').first().innerText()).includes('6:00'))throw Error('Statistiche: ore non riconciliate');
 const report=await page.evaluate(async()=>api('statistics?'+statsQuery(statsFilters)));
 if(report.summary.minutes!==360||report.centers.length!==2)throw Error('Statistiche: totale e ambito centri');
 const downloadable=async(selector,name)=>{const waiting=page.waitForEvent('download');await page.click(selector);const d=await waiting;await d.saveAs(outputDir+'/'+name);const bytes=fs.readFileSync(outputDir+'/'+name);if(bytes.slice(0,2).toString()!=='PK')throw Error('Download non XLSX: '+name)};
 await downloadable('#statsExcel','statistiche.xlsx');
 await page.selectOption('#statsCenter',secondCenter);await page.waitForFunction(()=>document.querySelector('#statsBody').textContent.includes('Nessuna registrazione nei filtri'));
 if(!(await page.locator('.stats-metric strong').first().textContent()).includes('—'))throw Error('Statistiche: assenza dati mostrata come zero');
 await page.selectOption('#statsCenter',firstCenter);await page.waitForFunction(()=>document.querySelector('.stats-metric strong')?.textContent==='6:00');
 await page.selectOption('#statsRole','INF');await page.waitForFunction(()=>document.querySelector('#statsPerson option[value]')!==null);
 await page.selectOption('#statsPerson',annaId);await page.waitForFunction(()=>document.querySelector('#statsBody').getAttribute('aria-busy')==='false');
 const scoped=await page.evaluate(async()=>api('statistics?'+statsQuery(statsFilters)));if(scoped.by_person.length!==1||scoped.by_person[0].id!==annaId)throw Error('Statistiche: filtro persona');
 for(const style of ['workspace','essential','editorial','classic']){
  await page.selectOption('#interfaceStyle',style);
  for(const width of [1400,1024,390,320]){
   await page.setViewportSize({width,height:1000});await page.click('[data-tab=statistiche]');await page.waitForSelector('.stats-metric strong');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Statistiche overflow '+style+' '+width);
   await page.evaluate(()=>{clearTimeout(window.toastTimer);document.querySelector('#toast').style.display='none'});
   if(width===1400)await page.screenshot({path:outputDir+'/v081-statistiche-'+style+'.png',fullPage:true});
   if(style==='workspace'&&[1400,390].includes(width))await page.screenshot({path:outputDir+'/v08-statistiche-'+width+'.png',fullPage:true});
   await page.click('[data-tab=esportazioni]');await page.waitForSelector('[data-backup-file]');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)){await page.screenshot({path:outputDir+'/overflow-export.png',fullPage:true});console.log(await page.evaluate(()=>[...document.querySelectorAll('main *')].filter(x=>x.getBoundingClientRect().right>innerWidth+1).map(x=>({tag:x.tagName,cls:x.className,width:x.getBoundingClientRect().width})).slice(0,15)));throw Error('Export overflow '+style+' '+width)}
   if(style==='workspace'&&[1400,390].includes(width))await page.screenshot({path:outputDir+'/v08-esportazioni-'+width+'.png',fullPage:true});
  }
 }
 await page.setViewportSize({width:1400,height:1000});await page.selectOption('#interfaceStyle','workspace');await page.waitForSelector('#exportDownload');
 await page.selectOption('#exportCenter',firstCenter);
 for(const kind of ['presenze_centro','presenze_totali','statistiche','dipendenti','onboarding','accordi']){await page.selectOption('#exportKind',kind);await downloadable('#exportDownload',kind+'.xlsx')}
 // Regression: required month fields hidden by a different export kind cannot block submission.
 const exportMonth=await page.inputValue('#exportFrom');
 await page.selectOption('#exportKind','presenze_totali');await page.fill('#exportTo','');await page.locator('#exportKind').focus();
 await page.selectOption('#exportKind','presenze_centro');await downloadable('#exportDownload','regressione-mese-nascosto.xlsx');
 await page.fill('#exportFrom','');await page.locator('#exportKind').focus();
 for(const kind of ['dipendenti','onboarding']){await page.selectOption('#exportKind',kind);await downloadable('#exportDownload','regressione-'+kind+'.xlsx')}
 await page.selectOption('#exportKind','presenze_totali');await page.fill('#exportFrom',exportMonth);await page.fill('#exportTo',exportMonth);await page.locator('#exportKind').focus();
 console.log('Regressioni export: mesi vuoti e cambio prospetto senza blocchi nascosti OK');
 const previous=await page.locator('[data-backup-file]').count();await page.click('#backupNow');await page.waitForFunction(n=>document.querySelectorAll('[data-backup-file]').length>n,previous);
 const bWait=page.waitForEvent('download');await page.locator('[data-backup-file]').first().click();const b=await bWait;await b.saveAs(outputDir+'/backup.sqlite3');if(!fs.readFileSync(outputDir+'/backup.sqlite3').slice(0,16).equals(Buffer.from('SQLite format 3\0')))throw Error('Backup download invalido');
 await page.click('[data-tab=statistiche]');await page.waitForSelector('.stats-metric strong');await page.locator('.stats-detail summary').click();await page.locator('[data-stats-person]').first().click();await page.waitForSelector('#clearPersonFilter');
 console.log('Statistiche riconciliate, filtri, dati mancanti, sei Excel, backup scaricabile e 4 stili a 1400/1024/390/320 px OK');
 await require('./v09_ui.cjs')({page,browser,totp,outputDir,firstCenter,secondCenter,annaId,errors});
 await require('./v010_ui.cjs')({page,outputDir,firstCenter,annaId});
 await require('./v011_ui.cjs')({page,outputDir,firstCenter,annaId});
 await page.click('[data-tab=utenti]');await page.click('#newUser');await page.fill('#userName','Compilatore demo');await page.fill('#userLogin','operatore');await page.fill('#userPassword','Password-iniziale-test-2026!');await page.selectOption('#userRole','operator');await page.locator('[name=userCenter]').first().check();await page.click('#saveUser');await page.waitForSelector('.web-activation');const activation=await page.locator('.web-activation').textContent();await page.click('#activationDone');
 await page.click('#account');await page.waitForSelector('#newRecovery');await page.screenshot({path:outputDir+'/v08-security.png',fullPage:true});await page.click('[data-tab=dashboard]');await page.waitForSelector('#refreshDashboard');await page.screenshot({path:outputDir+'/v08-dashboard.png',fullPage:true});
 await page.click('#logout');await page.fill('#authUser','admin');await page.fill('#authPassword','Password-personale-test-2026!');await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('#authCode');await page.screenshot({path:outputDir+'/v08-mfa.png',fullPage:true});await page.click('#useRecovery');await page.fill('#authCode',codes[0]);await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('#refreshDashboard');console.log('HR, onboarding, documento, presenze condivise e rientro con recovery OK');
 for(const width of [390,320]){await page.setViewportSize({width,height:900});await page.click('#account');await page.waitForSelector('#newRecovery');if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Security overflow '+width);if(width===390)await page.screenshot({path:outputDir+'/v08-mobile-security.png',fullPage:true});await page.click('[data-tab=dashboard]');await page.waitForSelector('#refreshDashboard');if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Dashboard overflow '+width)}
 await page.click('#logout');await page.fill('#authUser','operatore');await page.fill('#authPassword','Password-iniziale-test-2026!');await page.locator('#authForm button[type=submit]').click();await page.fill('#activationCode',activation);await page.locator('#authForm button[type=submit]').click();await page.waitForSelector('.web-secret',{state:'attached'});const opsecret=await page.locator('.web-secret').textContent();await page.fill('#authCode',totp(opsecret));await page.fill('#ownPassword','Password-personale-test-2026!');await page.fill('#ownPasswordRepeat','Password-personale-test-2026!');await page.locator('#authForm button[type=submit]').click();await page.check('#codesAck');await page.click('#codesDone');await page.waitForSelector('#refreshDashboard');
 if(await page.locator('[data-tab=dipendenti]').count()||await page.locator('[data-tab=utenti]').count())throw Error('Operator navigation');const code=await page.evaluate(async()=>{const r=await fetch('/api/hr?cid='+cid);return r.status});if(code!==403)throw Error('Operator HR');

 await page.click('[data-tab=statistiche]');await page.waitForSelector('.stats-metric strong');if(await page.locator('.stats-hr').count())throw Error('HR statistiche esposto al compilatore');
 await page.click('[data-tab=esportazioni]');await page.waitForSelector('#exportKind');if(await page.locator('#exportKind option').count()!==3||await page.locator('#backupNow').count())throw Error('Export riservati esposti al compilatore');
 await page.click('#logout');await page.setViewportSize({width:390,height:844});await page.waitForSelector('#authUser');await page.screenshot({path:outputDir+'/v08-mobile-login.png',fullPage:true});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Login overflow');
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('#authUser').focus();await page.keyboard.press('Tab');if(!await page.locator('#authPassword').evaluate(e=>e===document.activeElement))throw Error('Keyboard order');
 if(errors.length)throw Error(errors.join('; '));await browser.close();console.log('V0.11 BROWSER PASS · accessi, 2FA, permessi, desktop, 390/320 px, tastiera e CSP');
})().catch(e=>{console.error(e);process.exit(1)});
