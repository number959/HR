/* v0.10: exercise real storage and permissions; SMTP remains disabled. */
module.exports=async function({page,outputDir,firstCenter,annaId}){
 const assert=require('node:assert/strict');
 await page.click('[data-tab=strutture]');await page.waitForSelector('#structureSearch');
 await page.click('[data-structure-open="'+firstCenter+'"]');await page.fill('#structure_legal_name','Società demo QA');
 await page.fill('#structure_hr_email','hr-qa@example.invalid');await page.fill('#structure_contact_name','Referente QA');
 await page.click('#structureSave');await page.waitForFunction(()=>!document.querySelector('#modal').open);
 await page.click('[data-tab=dipendenti]');await page.waitForSelector('#hr_display_name,[data-hr="'+annaId+'"]',{state:'attached'});if(await page.locator('[data-hr="'+annaId+'"]').count())await page.locator('[data-hr="'+annaId+'"]').click();
 await page.click('[data-hr-section=struttura]');assert.match(await page.textContent('#hrStructure'),/hr-qa@example.invalid/);
 await page.click('#pageHelp');await page.waitForSelector('#nfHelpDialog[open]');assert.match(await page.textContent('#nfHelpArticleTitle'),/struttur/i);await page.click('#nfHelpDialog [data-help-close]');
 await page.screenshot({path:outputDir+'/v010-struttura-fascicolo.png',fullPage:true});
 await page.click('[data-tab=comunicazioni]');await page.waitForSelector('#commComposeForm');
 await page.click('[data-comm-section=lists]');await page.fill('#commListName','Personale QA');
 await page.locator('[data-comm-list=stages]:checked').uncheck();await page.locator('[data-comm-list=cids][value="'+firstCenter+'"]').check();
 await page.click('#commListSave');await page.waitForFunction(()=>communicationsList.version===1);
 await page.click('[data-comm-section=compose]');await page.selectOption('#commComposeList',{label:'Personale QA · v1'});
 await page.fill('#commComposeBody','Gentile {{nome}}, contatta {{email_hr}} presso {{struttura}}.');
 await page.click('#pageHelp');await page.waitForSelector('#nfHelpDialog[open]');await page.click('#nfHelpDialog [data-help-close]');
 assert.match(await page.inputValue('#commComposeBody'),/contatta/);
 await page.click('#commPreview');await page.waitForSelector('#commDraftCreate');
 assert.equal(await page.locator('#commPreviewRecipient option').count(),1);
 assert.match(await page.textContent('#commPreviewMessage'),/Anna Rossi/);assert.match(await page.textContent('#commPreviewMessage'),/hr-qa@example.invalid/);
 assert.match(await page.textContent('#commPreviewResult'),/email mancante/);
 await page.click('#commDraftCreate');await page.waitForSelector('#commSendOpen');assert.equal(await page.locator('#commSendOpen').isDisabled(),true);
 assert.equal(await page.evaluate(()=>communicationsCampaign.counts.pending),1);
 await page.screenshot({path:outputDir+'/v010-comunicazioni-bozza.png',fullPage:true});
 for(const width of [390,320]){
  await page.setViewportSize({width,height:1000});
  for(const section of ['compose','templates','lists','settings']){
   await page.click('[data-comm-section='+section+']');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Comunicazioni overflow '+section+' '+width);
   if(width===390)await page.screenshot({path:outputDir+'/v010-email-'+section+'-mobile.png',fullPage:true});
  }
  await page.click('[data-tab=strutture]');await page.waitForSelector('#structureSearch');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Strutture overflow '+width);
  await page.click('[data-structure-open="'+firstCenter+'"]');await page.waitForSelector('#structureForm');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Scheda struttura overflow '+width);
  await page.locator('#modal [data-close]').first().click();
  await page.click('[data-tab=comunicazioni]');await page.waitForSelector('#commComposeForm, #commSettingsForm');
 }
 await page.setViewportSize({width:1400,height:1000});
 console.log('V0.10 rubrica condivisa nel fascicolo, liste email, anteprima personalizzata, bozze senza invio, guide e 390/320 px OK');
};
