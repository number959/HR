/* User journeys through the illustrated help, including small screens and media. */
const {chromium}=require('playwright'), assert=require('node:assert/strict'), fs=require('node:fs'),path=require('node:path');
(async()=>{
  const out=process.env.QA_OUTPUT_DIR||path.join(__dirname,'qa-output');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{}),args:process.env.QA_CHROMIUM_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const page=await browser.newPage({baseURL:process.env.DEMO_URL||'http://127.0.0.1:8765',viewport:{width:1400,height:1000},locale:'it-IT'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)errors.push('HTTP '+r.status()+' '+r.url())});
  await page.goto('/');await page.click('[data-demo-role=hr]');await page.waitForSelector('#refreshDashboard');
  await page.click('[data-tab=guida]');await page.waitForSelector('#nfHelpPath');
  assert.equal(await page.locator('#nfHelpPath option').count(),8);
  assert.equal(await page.locator('.nf-help-index [data-help-topic]').count(),34);
  const paths=await page.evaluate(()=>NefroHelp.quickstarts.map(p=>({id:p.id,topics:p.topics})));
  for(const item of paths){
    await page.selectOption('#nfHelpPath',item.id);
    assert.deepEqual(await page.locator('.nf-help-index [data-help-topic]').evaluateAll(b=>b.map(x=>x.dataset.helpTopic)),item.topics);
    assert.equal(await page.locator('.nf-help-index [aria-current=true]').getAttribute('data-help-topic'),item.topics[0]);
    if(item.topics.length>1){
      await page.click('[data-help-page="'+item.topics[1]+'"]');
      assert.equal(await page.locator('.nf-help-index [aria-current=true]').getAttribute('data-help-topic'),item.topics[1]);
      await page.click('[data-help-page="'+item.topics[0]+'"]');
    }
  }
  await page.selectOption('#nfHelpPath','');await page.click('[data-help-mode=settings]');
  assert.equal(await page.locator('.nf-help-reference-item').count(),323);
  await page.fill('#nfHelpSearch','NAS');assert.ok(await page.locator('.nf-help-reference-item').count()>0);
  assert.match(await page.locator('.nf-help-reference').innerText(),/NAS|destinazione/i);
  await page.fill('#nfHelpSearch','nessunrisultato012345');assert.equal(await page.locator('.nf-help-reference-item').count(),0);
  assert.match(await page.locator('.nf-help-reference').innerText(),/Nessuna impostazione/);
  await page.fill('#nfHelpSearch','');await page.click('[data-help-mode=topics]');
  await page.click('[data-help-topic=presenze]');
  await page.locator('.nf-help-figure img').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('.nf-help-figure img').naturalWidth>=1920);
  assert.ok(await page.locator('.nf-help-before li').count()>=1);
  assert.ok(await page.locator('.nf-help-steps li').count()>=4);
  assert.ok((await page.locator('.nf-help-worked-example').innerText()).length>50);
  await page.locator('.nf-help-errors summary').first().click();assert.equal(await page.locator('.nf-help-errors details').first().getAttribute('open'),'');
  const pdf=await page.request.get(await page.locator('.nf-help-download').getAttribute('href'));
  assert.equal(pdf.status(),200);assert.equal((await pdf.body()).subarray(0,5).toString(),'%PDF-');
  assert.match(await page.locator('.nf-help-video-badge').innerText(),/FULL HD/);
  const video=page.locator('.nf-help-video');assert.match(await video.getAttribute('poster'),/presenze\.jpg$/);
  assert.equal(await page.locator('.nf-help-video-chapters').getAttribute('open'),null);
  await page.locator('.nf-help-video-chapters summary').click();
  const chapter=page.locator('[data-help-chapter]').last(),start=Number(await chapter.getAttribute('data-help-chapter'));
  await chapter.click();await page.waitForFunction(s=>document.querySelector('.nf-help-video').currentTime>=s,start);
  assert.equal(await video.evaluate(v=>v.videoWidth),1920);assert.equal(await video.evaluate(v=>v.videoHeight),1080);
  await video.evaluate(v=>{v.pause();v.textTracks[0].mode='hidden'});
  await page.waitForFunction(()=>document.querySelector('.nf-help-video').textTracks[0].cues?.length>0);
  for(const width of [1400,390,320]){
    await page.setViewportSize({width,height:1000});await page.selectOption('#nfHelpPath','hr');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Help overflow '+width);
    await page.screenshot({path:out+'/help-quality-'+width+'.png',fullPage:true});
    await page.click('[data-help-mode=settings]');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Settings overflow '+width);
  }
  assert.deepEqual(errors,[]);await browser.close();
  console.log('HELP QUALITY PASS: 7 ordered role paths, 34 procedures, 323 settings, search, navigation, example/FAQ, PDF and real images, Full HD playback/chapters/captions, 1400/390/320 px.');
})().catch(e=>{console.error(e);process.exit(1)});
