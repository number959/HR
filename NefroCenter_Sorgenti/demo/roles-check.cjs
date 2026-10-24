const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{}),args:process.env.QA_CHROMIUM_NO_SANDBOX==='1'?['--no-sandbox']:[]});
 const page=await browser.newPage({baseURL:process.env.DEMO_URL||'http://127.0.0.1:8765',viewport:{width:1400,height:1000},locale:'it-IT'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await page.waitForSelector('[data-role-description]');assert.equal(await page.locator('[data-role-description]').count(),5);
 for(const role of ['hr','manager','operator','viewer','admin']){
  const card=page.locator('[data-role-description='+role+']');assert.ok(await card.locator('li').count()>=3);
  for(const phrase of ['Quali dati vede','Cosa può fare','Limiti del ruolo','Da provare nella demo'])assert.ok((await card.textContent()).includes(phrase));
  assert.equal(await card.locator('[data-demo-role='+role+']').count(),1);
 }
 assert.match(await page.locator('[data-role-description=hr]').innerText(),/Non modifica direttamente le presenze/);
 assert.match(await page.locator('[data-role-description=viewer]').innerText(),/Solo le strutture assegnate/);
 for(const width of [1400,768,390,320]){
  await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'role page overflow '+width);
  if([1400,390].includes(width)){const out=process.env.QA_OUTPUT_DIR||'/workspace/sites/demo-v010-output';fs.mkdirSync(out,{recursive:true});await page.screenshot({path:out+'/ruoli-spiegati-'+width+'.png',fullPage:true});}
 }
 const pdf=await page.request.get('/presentation/guida-ufficio-hr.pdf');assert.equal(pdf.status(),200);assert.equal((await pdf.body()).subarray(0,5).toString(),'%PDF-');
 for(const role of ['hr','manager','operator','viewer','admin']){
  await page.click('[data-demo-role='+role+']');await page.waitForSelector('#refreshDashboard');assert.equal(await page.evaluate(()=>Demo.role),role);
  await page.click('#demoChangeRole');await page.waitForSelector('[data-role-description]');
 }
 assert.deepEqual(errors,[]);await browser.close();console.log('ROLE WELCOME PASS: 5 role descriptions grounded in permissions, scopes/limits/examples, role login/switch, HR PDF, 1400/768/390/320px.');
})().catch(e=>{console.error(e);process.exit(1)});
