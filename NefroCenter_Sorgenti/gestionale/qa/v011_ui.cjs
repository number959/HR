/* v0.11 actual server workflows. All SMTP settings remain disabled. */
module.exports=async function({page,outputDir,firstCenter,annaId}){
 const assert=require('node:assert/strict');
 const closeModal=async()=>page.locator('#modal [data-close]').first().click();
 const noOverflow=async(label)=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,label);
 const originalMonth=await page.evaluate(()=>month);
 await page.setViewportSize({width:1400,height:1000});

 await page.click('[data-tab=documenti_hr]');await page.waitForSelector('[data-central-review]');
 await page.locator('[data-central-review]').first().click();await page.waitForSelector('#hrReviewStatus');
 for(const [status,note,count] of [['needs_correction','Firma da verificare nella pagina finale',2],['received','Firma controllata con la sede di provenienza',3],['verified','Verifica HR conclusa',4]]){
  await page.selectOption('#hrReviewStatus',status);await page.fill('#hrReviewNote',note);await page.click('#hrReviewSave');
  await page.waitForFunction(n=>document.querySelectorAll('#hrReviewHistory li').length===n,count);
 }
 assert.match(await page.textContent('#hrReviewHistory'),/Verificato da HR/);
 await page.screenshot({path:outputDir+'/v011-documento-verificato.png',fullPage:true});await closeModal();
 await page.selectOption('#hrDocReview','verified');await page.click('#hrDocApply');await page.waitForSelector('[data-central-review]');
 assert.match(await page.textContent('#hrCentralRows'),/Verificato da HR/);
 console.log('V0.11 documenti: correzione, nuova verifica, decisione HR, storico e filtro OK');

 // Isolate the approval exercise from earlier attendance regression fixtures.
 await page.evaluate(async({center,pid})=>{const m='2026-11',s=await api(`state?cid=${center}&month=${m}`);await api('entry',{cid:center,month:m,revision:s.center.revision,entry:{person_id:pid,day:m+'-14',slot:'m',code:'m',layer:'actual'}});cid=center;month=m;tab='approvazioni';await load()},{center:firstCenter,pid:annaId});
 await page.waitForSelector('#approvalPolicy');await page.click('#approvalPolicy > summary');await page.check('#approvalEnabled');await page.fill('#approvalPolicyReason','Avvio del processo dimostrativo QA');await page.click('#approvalPolicySave');
 await page.waitForSelector('[data-approval-action=submit]');await page.fill('#approvalNote','Invio delle presenze per la verifica');await page.click('[data-approval-action=submit]');
 await page.waitForSelector('[data-approval-action=manager_approve]');assert.match(await page.textContent('#approvalStatus'),/responsabile/i);
 const frozen=await page.evaluate(async()=>{const s=await api(`state?cid=${cid}&month=${month}`);return s.approval.frozen});assert.equal(frozen,true);
 await page.fill('#approvalNote','Controllare gli orari prima del nuovo invio');await page.click('[data-approval-action=return]');
 await page.waitForSelector('[data-approval-action=submit]');assert.match(await page.textContent('#approvalStatus'),/Restituito/i);
 await page.click('[data-approval-action=submit]');await page.waitForSelector('#approvalCalendarChecked');await page.check('#approvalCalendarChecked');await page.click('[data-approval-action=manager_approve]');
 await page.waitForSelector('[data-approval-action=hr_approve]');assert.match(await page.textContent('#approvalStatus'),/attesa di HR/i);
 await page.screenshot({path:outputDir+'/v011-approvazioni.png',fullPage:true});
 await page.fill('#approvalNote','Restituzione conclusiva per il collaudo');await page.click('[data-approval-action=return]');await page.waitForSelector('[data-approval-action=submit]');
 await page.click('#approvalPolicy > summary');await page.uncheck('#approvalEnabled');await page.fill('#approvalPolicyReason','Fine del collaudo del flusso mensile');await page.click('#approvalPolicySave');await page.waitForSelector('#approvalDisabled');
 await page.evaluate(async m=>{month=m;await load()},originalMonth);
 console.log('V0.11 approvazioni: attivazione, invio, blocco, restituzione e verifica responsabile OK');

 await page.click('[data-tab=copertura]');await page.waitForSelector('#staffingRows');await page.click('[data-staffing-section=requirements]');await page.click('#staffingEditRequirements');await page.click('#staffingAddWeekly');
 await page.locator('[data-staffing-requirement=weekly] [data-field=role]').selectOption('INF');await page.locator('[data-staffing-requirement=weekly] [data-field=minimum]').fill('2');await page.click('#staffingFormSave');
 await page.waitForFunction(()=>!document.querySelector('#modal').open&&staffingData.requirements.version===1);
 assert.equal(await page.evaluate(()=>staffingData.requirements.weekly[0].minimum),2);
 await page.click('[data-staffing-section=availability]');await page.click('#staffingNewAvailability');await page.selectOption('#staffingAvailabilityPerson',annaId);await page.selectOption('#staffingAvailabilityStatus','preferred');await page.fill('#staffingAvailabilityNote','Preferenza organizzativa di prova');await page.click('#staffingFormSave');
 await page.waitForFunction(()=>!document.querySelector('#modal').open&&staffingData.availability.length===1);
 assert.match(await page.textContent('#staffingBody'),/Preferenza organizzativa di prova/);await page.click('[data-staffing-section=coverage]');await page.selectOption('#staffingState','uncovered');
 assert.ok(await page.locator('#staffingRows tr').count()>0);await page.screenshot({path:outputDir+'/v011-copertura.png',fullPage:true});
 console.log('V0.11 copertura: fabbisogno salvato, disponibilità e turni da coprire OK');

 await page.click('[data-tab=uscite]');await page.waitForSelector('#departureNew');await page.click('[data-departure-section=assets]');await page.click('#departureNew');await page.selectOption('#departureCid',firstCenter);await page.selectOption('#departurePid',annaId);await page.fill('#equipmentCode','QA-BADGE-01');await page.fill('#equipmentLabel','Badge temporaneo di collaudo');await page.click('#departureSave');
 await page.waitForFunction(()=>!document.querySelector('#modal').open&&departuresData.assets.length===1);
 await page.click('[data-departure-section=cases]');await page.click('#departureNew');await page.selectOption('#departureCid',firstCenter);await page.selectOption('#departurePid',annaId);await page.fill('#departureReason','Percorso dimostrativo di cessazione');await page.click('#departureSave');await page.waitForSelector('#departureComplete');assert.equal(await page.locator('#departureComplete').isDisabled(),true);
 await closeModal();await page.click('[data-departure-section=assets]');await page.locator('[data-equipment-return]').first().click();await page.selectOption('#equipmentCondition','good');await page.click('#departureSave');
 await page.waitForFunction(()=>!document.querySelector('#modal').open&&departuresData.assets[0].status==='returned');
 await page.click('[data-departure-section=cases]');await page.locator('[data-departure-open]').first().click();await page.waitForSelector('[data-departure-task]');
 for(const [index,id] of ['badge','keys','devices','documents','access'].entries()){
  await page.click('[data-departure-task='+id+']');await page.selectOption('#departureTaskStatus','done');await page.click('#departureSave');
  await page.waitForFunction(n=>departuresData.cases[0].tasks.filter(t=>t.status==='done').length===n,index+1);await page.waitForSelector('#departureComplete');
 }
 assert.equal(await page.locator('#departureComplete').isDisabled(),false);await page.screenshot({path:outputDir+'/v011-uscite.png',fullPage:true});await page.click('#departureComplete');await page.fill('#departureCloseNote','Attività e restituzione controllate in QA');await page.check('#departureCloseConfirm');await page.click('#departureSave');
 await page.waitForFunction(()=>departuresData.cases[0].status==='completed');await page.waitForSelector('.departure-detail');assert.match(await page.textContent('.departure-detail'),/Completato/);await closeModal();
 const personStillActive=await page.evaluate(async pid=>(await api(`hr?cid=${cid}&pid=${pid}`)).person.active,annaId);assert.equal(personStillActive,true);
 console.log('V0.11 uscite: consegna, blocchi, restituzione, attività e chiusura senza cambiare anagrafica OK');

 await page.click('[data-tab=promemoria]');await page.waitForSelector('#reminderPreview');assert.equal(await page.isChecked('#reminderEnabled'),false);
 const historyBefore=await page.evaluate(()=>remindersData.history.length);await page.click('#reminderPreview');await page.waitForSelector('.reminder-preview');
 assert.match(await page.textContent('#reminderPreviewResult'),/anteprima non invia email/i);assert.equal(await page.evaluate(()=>remindersData.history.length),historyBefore);assert.equal(await page.isChecked('#reminderEnabled'),false);
 await page.screenshot({path:outputDir+'/v011-promemoria.png',fullPage:true});
 console.log('V0.11 promemoria: configurazione disattivata, anteprima e nessun invio OK');

 await page.click('[data-tab=paghe]');await page.waitForSelector('#payrollConnectorMode');await page.selectOption('#payrollConnectorMode','consultant');await page.locator('#payrollConnectorDetails details > summary').click();await page.fill('#payrollSpecText','registration;day;payroll_code;worked_hours');await page.click('#payrollSpecRead');
 await page.waitForFunction(()=>document.querySelectorAll('[data-payroll-map]').length===4);assert.equal(await page.inputValue('#payrollStatus'),'draft');assert.equal(await page.inputValue('#payrollProvider'),'');
 assert.equal(await page.inputValue('[data-payroll-map="0"]'),'registration');await page.click('#payrollSave');await page.waitForFunction(()=>document.querySelector('#payrollSaveState')?.textContent.includes('Modello salvato'));
 const saved=await page.evaluate(async()=>api('payroll_config?cid='+cid));assert.equal(saved.config.connector.mode,'consultant');assert.equal(saved.config.status,'draft');assert.equal(saved.config.connector.provider,'');
 await page.screenshot({path:outputDir+'/v011-paghe-specifiche.png',fullPage:true});
 console.log('V0.11 paghe: intestazioni importate, associazioni riconosciute e tracciato in bozza senza gestionale inventato OK');

 for(const width of [390,320]){
  await page.setViewportSize({width,height:1000});
  for(const [name,ready] of [['approvazioni','#approvalRefresh'],['copertura','#staffingRows'],['uscite','#departureNew'],['promemoria','#reminderPreview'],['paghe','#payrollConnectorMode'],['documenti_hr','#hrDocReview']]){
   await page.click('[data-tab='+name+']');await page.waitForSelector(ready);await noOverflow('V0.11 overflow '+name+' '+width);
   if(width===390)await page.screenshot({path:outputDir+'/v011-'+name+'-mobile.png',fullPage:true});
  }
  await page.locator('[data-central-review]').first().click();await page.waitForSelector('#hrReviewHistory');await noOverflow('V0.11 modal verifica '+width);await closeModal();
  await page.click('[data-tab=uscite]');await page.waitForSelector('#departureNew');await page.locator('[data-departure-open]').first().click();await page.waitForSelector('.departure-detail');await noOverflow('V0.11 modal uscita '+width);await closeModal();
 }
 await page.setViewportSize({width:1400,height:1000});
 console.log('V0.11 nuove pagine e finestre verificate a 390/320 px OK');
};
