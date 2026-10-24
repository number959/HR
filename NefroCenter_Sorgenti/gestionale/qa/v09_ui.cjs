/* Integrated v0.9 workflows, called from the authenticated browser regression. */
module.exports=async function({page,browser,totp,outputDir,firstCenter,secondCenter,annaId,errors}){
 const assert=require('node:assert/strict');
 await page.click('[data-tab=attivita]');await page.waitForSelector('.tasks-summary');
 await page.selectOption('#tasksCategory','onboarding');await page.waitForSelector('[data-task-index]');
 await page.locator('[data-task-index]').first().click();await page.waitForSelector('[data-hr-task]');
 assert.equal(await page.evaluate(()=>tab),'dipendenti');
 await page.click('[data-tab=gruppo]');await page.waitForSelector('#workforceSearch');
 await page.fill('#workforceSearch','Anna Rossi');await page.locator('[data-wf-group]').first().click();
 await page.waitForSelector('[data-wf-contract]');await page.locator('[data-wf-contract]').first().click();
 await page.fill('#wfFrom','2026-10-01');await page.fill('#wfType','Indeterminato');await page.fill('#wfHours','36');await page.fill('#wfPartTime','100');await page.fill('#wfReason','Contratto dimostrativo verificato');await page.click('#wfIntervalSave');
 await page.waitForFunction(()=>!document.querySelector('#modal').open);await page.waitForSelector('[data-wf-edit-contract]');
 await page.screenshot({path:outputDir+'/v09-personale-decorrenze.png',fullPage:true});
 await page.locator('[data-wf-hr]').first().click();await page.waitForSelector('#hr_display_name');
 assert.equal(await page.inputValue('#hr_display_name'),'Anna Rossi');
 // Contextual help must preserve in-progress HR form changes.
 const previousPhone=await page.evaluate(()=>hrData.profile.fields.phone||'');
 await page.click('[data-hr-section=recapiti]');await page.fill('#hr_phone','NON SALVATO DEMO');
 await page.click('#pageHelp');await page.waitForSelector('#nfHelpDialog[open]');
 await page.click('#nfHelpDialog [data-help-close]');
 assert.equal(await page.inputValue('#hr_phone'),'NON SALVATO DEMO');
 await page.fill('#hr_phone',previousPhone);await page.evaluate(()=>{hrDirty=false});
 await page.click('[data-tab=documenti_hr]');await page.waitForSelector('#hrDocApply');
 await page.fill('#hrDocPerson','Anna Rossi');await page.click('#hrDocApply');await page.waitForSelector('[data-central-person]');
 const documentURL=await page.locator('#hrCentralRows a').first().getAttribute('href');
 const response=await page.request.get(documentURL);assert.equal(response.status(),200);assert.equal(response.headers()['content-type'],'application/pdf');
 assert.ok((await response.body()).subarray(0,5).equals(Buffer.from('%PDF-')));
 await page.screenshot({path:outputDir+'/v09-documenti-centrali.png',fullPage:true});
 // Jump from a different active center must keep the document's person selected.
 await page.evaluate(id=>{cid=id},secondCenter);await page.locator('[data-central-person]').first().click();
 await page.waitForSelector('[data-hr-download]');assert.equal(await page.evaluate(()=>hrPid),annaId);assert.equal(await page.evaluate(()=>cid),firstCenter);
 await page.click('[data-tab=paghe]');await page.waitForSelector('#payrollStatus');
 assert.equal(await page.inputValue('#payrollStatus'),'draft');
 await page.click('#payrollPreviewLoad');await page.waitForSelector('.payroll-summary');
 assert.equal(await page.locator('[data-payroll-download="csv"]').isDisabled(),true);
 assert.match(await page.textContent('#payrollPreviewResult'),/bozza|verificat|confermat/i);
 await page.screenshot({path:outputDir+'/v09-paghe-bozza.png',fullPage:true});
 await page.click('[data-tab=esportazioni]');await page.waitForSelector('#backupPolicyEnabled');
 assert.equal(await page.locator('#backupPolicyEnabled').isChecked(),false);
 assert.equal(await page.locator('#backupPolicyRun').isDisabled(),true);
 await page.click('[data-tab=guida]');await page.waitForSelector('#nfHelpSearch');
 await page.click('[data-help-topic="presenze"]');await page.locator('.nf-help-video').evaluate(v=>v.load());
 await page.waitForFunction(()=>document.querySelector('.nf-help-video').readyState>=1);
 assert.ok(await page.locator('.nf-help-video').evaluate(v=>v.duration)>0);
 await page.locator('.nf-help-video-chapters > summary').click();
 await page.locator('[data-help-chapter]').last().click();
 await page.waitForFunction(()=>document.querySelector('.nf-help-video').currentTime>0);
 await page.locator('.nf-help-video').evaluate(v=>v.pause());
 await page.fill('#nfHelpSearch','NAS');assert.ok(await page.locator('.nf-help-index [data-help-topic]').count()>0);
 await page.click('[data-help-mode="settings"]');assert.match(await page.textContent('.nf-help-reference'),/NAS|destinazione|copia/i);
 await page.screenshot({path:outputDir+'/v09-guide-impostazioni.png',fullPage:true});
 await page.click('[data-tab=presenze]');await page.click('#pageHelp');await page.waitForSelector('#nfHelpDialog[open]');await page.click('[data-help-tour]');await page.waitForSelector('.nf-help-tour[open]');await page.keyboard.press('Escape');assert.equal(await page.locator('.nf-help-tour').count(),0);
 for(const width of [390,320]){
  await page.setViewportSize({width,height:900});
  for(const [name,ready] of [['attivita','.tasks-summary'],['gruppo','#workforceOn'],['documenti_hr','#hrDocApply'],['paghe','#payrollStatus'],['guida','#nfHelpSearch']]){
   await page.click('[data-tab='+name+']');await page.waitForSelector(ready);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)){await page.screenshot({path:outputDir+'/v09-overflow-'+name+'-'+width+'.png',fullPage:true});throw Error('v0.9 overflow '+name+' '+width)}
   if(width===390)await page.screenshot({path:outputDir+'/v09-'+name+'-mobile.png',fullPage:true});
  }
 }
 await page.setViewportSize({width:1400,height:1000});
 const activation=await page.evaluate(async()=>{const r=await api('user_save',{user:{username:'hrcentrale',name:'HR centrale demo',role:'hr',centers:[],active:true,password:'Password-iniziale-test-2026!'}});return r.activation_code});
 const context=await browser.newContext({baseURL:process.env.WEB_URL,viewport:{width:1400,height:1000},locale:'it-IT'}),hrPage=await context.newPage();
 hrPage.on('pageerror',e=>errors.push(e.message));
 await hrPage.goto(process.env.WEB_URL);await hrPage.fill('#authUser','hrcentrale');await hrPage.fill('#authPassword','Password-iniziale-test-2026!');await hrPage.locator('#authForm button[type=submit]').click();await hrPage.fill('#activationCode',activation);await hrPage.locator('#authForm button[type=submit]').click();await hrPage.waitForSelector('.web-secret',{state:'attached'});
 const secret=await hrPage.locator('.web-secret').textContent();await hrPage.fill('#authCode',totp(secret));await hrPage.fill('#ownPassword','Password-personale-test-2026!');await hrPage.fill('#ownPasswordRepeat','Password-personale-test-2026!');await hrPage.locator('#authForm button[type=submit]').click();await hrPage.check('#codesAck');await hrPage.click('#codesDone');await hrPage.waitForSelector('#refreshDashboard');
 for(const name of ['dipendenti','documenti_hr','gruppo','paghe'])assert.equal(await hrPage.locator('[data-tab='+name+']').count(),1);
 for(const name of ['utenti','carico'])assert.equal(await hrPage.locator('[data-tab='+name+']').count(),0);
 await hrPage.click('[data-tab=documenti_hr]');await hrPage.waitForSelector('[data-central-person]');assert.equal((await hrPage.request.get(documentURL)).status(),200);
 assert.equal((await hrPage.request.get('/api/backup_policy')).status(),403);
 await hrPage.click('[data-tab=presenze]');await hrPage.waitForSelector('.monthly-grid');await hrPage.locator('[data-day]').first().click();await hrPage.waitForSelector('#saveEntry');assert.equal(await hrPage.locator('#saveEntry').isDisabled(),true);assert.equal(await hrPage.locator('#entryCode').isDisabled(),true);await hrPage.locator('#modal [data-close]').first().click();
 await hrPage.click('[data-tab=esportazioni]');await hrPage.waitForSelector('#exportKind');assert.equal(await hrPage.locator('#backupNow').count(),0);assert.equal(await hrPage.locator('#backupPolicyEnabled').count(),0);
 await hrPage.screenshot({path:outputDir+'/v09-hr-centrale-permessi.png',fullPage:true});await context.close();
 console.log('V0.9 attività, decorrenze, documenti centrali, paghe in bozza, NAS disattivato, guide/video/tutorial, 390/320 px e ruolo HR OK');
};
