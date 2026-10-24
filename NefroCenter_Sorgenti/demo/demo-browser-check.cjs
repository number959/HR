const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.QA_OUTPUT_DIR||require('node:path').join(__dirname,'qa-output');fs.mkdirSync(root,{recursive:true});
const url=process.env.DEMO_URL||'http://127.0.0.1:8765';
(async()=>{
 const launch={};if(process.env.CHROMIUM_EXECUTABLE)launch.executablePath=process.env.CHROMIUM_EXECUTABLE;if(process.env.QA_CHROMIUM_NO_SANDBOX==='1')launch.args=['--no-sandbox'];
 const browser=await chromium.launch(launch);
 const errors=[];
 const ready={approvazioni:'#approvalRefresh',copertura:'#staffingRows',promemoria:'#reminderPreview',uscite:'#departureNew',dashboard:'#refreshDashboard',attivita:'.tasks-summary',statistiche:'.stats-metric',presenze:'.monthly-grid',dipendenti:'#hrNew',strutture:'#structureSearch',comunicazioni:'#commComposeForm',gruppo:'#workforceSearch',documenti_hr:'#hrDocApply',accordi:'.agreement-table',paghe:'#payrollStatus',riepilogo:'#exportSummary',controlli:'.alert-item',parametri:'.configtabs',centri:'.center-list',esportazioni:'#exportKind',utenti:'#newUser',carico:'#patDay',guida:'#nfHelpSearch'};
 for(const role of ['admin','hr','manager','operator','viewer']){
  const context=await browser.newContext({baseURL:url,viewport:{width:1400,height:1000},locale:'it-IT'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(role+': '+e.message));
  page.on('response',r=>{if(r.status()>=400)errors.push(role+': HTTP '+r.status()+' '+r.url())});
  await page.goto(url);await page.waitForSelector('[data-demo-role]');
  if(role==='admin')await page.screenshot({path:root+'/ingresso.png',fullPage:true});
  await page.click('[data-demo-role='+role+']');await page.waitForSelector('#refreshDashboard');
  const tabs=await page.locator('[data-tab]').evaluateAll(els=>els.map(e=>e.dataset.tab));
  assert.equal(tabs.includes('documenti_hr'),['admin','hr','manager'].includes(role));
  assert.equal(tabs.includes('strutture'),['admin','hr','manager'].includes(role));
  assert.equal(tabs.includes('comunicazioni'),['admin','hr'].includes(role));
  for(const width of [1400,390]){
   await page.setViewportSize({width,height:1000});
   for(const tab of tabs){
    await page.click('[data-tab='+tab+']');await page.waitForSelector(ready[tab],{timeout:10000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,role+' overflow '+tab+' '+width);
    if(role==='admin'&&['dashboard','documenti_hr','guida'].includes(tab))await page.screenshot({path:root+'/'+tab+'-'+width+'.png',fullPage:true});
   }
  }
  if(['admin','hr','manager'].includes(role)){
   await page.click('[data-tab=strutture]');await page.waitForSelector('[data-structure-open]');await page.locator('[data-structure-open]').first().click();await page.fill('#structure_contact_name','Referente demo aggiornato');await page.click('#structureSave');await page.waitForFunction(()=>!document.querySelector('#modal').open);
   assert.match(await page.textContent('#structureCards'),/Referente demo aggiornato/);
   await page.click('[data-tab=documenti_hr]');await page.waitForSelector('#hrCentralRows a');
   const href=await page.locator('#hrCentralRows a').first().getAttribute('href');assert.match(href,/\/samples\/contratto-demo\.pdf$/);
   const pdf=await context.request.get(href);assert.equal(pdf.status(),200);assert.equal((await pdf.body()).subarray(0,5).toString(),'%PDF-');
  }
  if(['admin','hr'].includes(role)){
   await page.click('[data-tab=comunicazioni]');await page.waitForSelector('#commComposeForm');
   await page.selectOption('#commComposeTemplate','seed-benvenuto');
   const list=await page.locator('#commComposeList option').evaluateAll(els=>els.find(e=>e.textContent.includes('Dipendenti attivi')).value);await page.selectOption('#commComposeList',list);
   await page.click('#commPreview');await page.waitForSelector('#commDraftCreate');assert.equal(await page.locator('#commDraftCreate').isDisabled(),false);
   await page.click('#commDraftCreate');await page.waitForSelector('#commSendOpen');assert.match(await page.textContent('#commSendOpen'),/Simula invio/);
   await page.click('#commSendOpen');await page.waitForSelector('#commSendConfirm');assert.equal(await page.locator('#commSendConfirm').isDisabled(),true);
   await page.check('#commSendAcknowledge');await page.click('#commSendConfirm');await page.waitForFunction(()=>!document.querySelector('#modal').open);
   await page.waitForFunction(()=>document.querySelector('#commSendOpen')?.disabled);assert.match(await page.textContent('#commCampaignDetail'),/Simulato|Simulati/);assert.match(await page.textContent('#commCampaignDetail'),/Nessuna email/);
   await page.screenshot({path:root+'/comunicazioni-'+role+'.png',fullPage:true});
   for(const section of ['templates','lists',...(role==='admin'?['settings']:[])]){await page.click('[data-comm-section='+section+']');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,role+' comunicazioni '+section+' overflow');}
  }
  await page.click('[data-tab=guida]');await page.waitForSelector('#nfHelpSearch');await page.click('[data-help-topic="presenze"]');
  await page.locator('.nf-help-video').evaluate(v=>v.load());await page.waitForFunction(()=>document.querySelector('.nf-help-video').readyState>=1);assert.ok(await page.locator('.nf-help-video').evaluate(v=>v.duration)>0);
  await page.click('[data-tab=presenze]');await page.locator('[data-day]').first().click();await page.waitForSelector('#saveEntry');
  assert.equal(await page.locator('#saveEntry').isDisabled(),['hr','viewer'].includes(role));
  console.log(role+': '+tabs.length+' pagine, 1400/390 px, permessi, documenti e video OK');await context.close();
 }
 assert.deepEqual(errors,[]);await browser.close();console.log('DEMO BROWSER PASS');
})().catch(e=>{console.error(e);process.exit(1)});
