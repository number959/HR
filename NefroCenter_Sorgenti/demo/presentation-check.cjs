const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE||'/usr/bin/chromium',args:process.env.QA_CHROMIUM_NO_SANDBOX==='1'?['--no-sandbox']:[]});
 const context=await browser.newContext({baseURL:process.env.DEMO_URL||'http://127.0.0.1:8765',viewport:{width:1400,height:1000},locale:'it-IT'}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)errors.push('HTTP '+r.status()+' '+r.url())});
 await page.goto('/');await page.waitForSelector('#demoWatch');
 for(const width of [1400,390,320]){
  await page.setViewportSize({width,height:1000});await page.click('#demoWatch');await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo')?.readyState>=1);
  const video=page.locator('#demoPresentationVideo');assert.equal(Math.round(await video.evaluate(v=>v.duration)),157);
  await video.evaluate(async v=>{v.textTracks[0].mode='hidden';await v.play()});
  await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo').currentTime>1.2);
  await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo').textTracks[0].cues?.length>0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Overflow at '+width);
  if(width===1400){const output=process.env.QA_OUTPUT_DIR||'/workspace/sites/demo-v010-output';fs.mkdirSync(output,{recursive:true});await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo').getVideoPlaybackQuality().totalVideoFrames>10);await video.evaluate(v=>v.pause());await page.screenshot({path:output+'/presentazione-audio.png'});}
  await page.click('#demoPresentationClose');assert.equal(await video.evaluate(v=>v.paused),true);
 }
 for(const href of ['/presentation/presentazione-con-audio.mp4','/presentation/presentazione.mp4','/presentation/trascrizione.txt'])assert.equal((await context.request.get(href)).status(),200);
 await page.setViewportSize({width:1400,height:1000});await page.click('[data-demo-role="hr"]');await page.waitForSelector('#refreshDashboard');await page.click('#demoInfo');await page.click('#demoInfoWatch');await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo')?.readyState>=1);await page.keyboard.press('Escape');assert.equal(await page.locator('#demoPresentationDialog').evaluate(d=>d.open),false);
 await page.click('#demoInfo');await page.click('#demoInfoWatch');await page.waitForFunction(()=>document.querySelector('#demoPresentationVideo')?.readyState>=1);await page.click('.demo-video-chapters summary');assert.equal(await page.locator('[data-presentation-chapter]').count(),11);await page.click('[data-presentation-chapter="142"]');await page.waitForFunction(()=>Math.abs(document.querySelector('#demoPresentationVideo').currentTime-142)<0.5);await page.click('#demoPresentationClose');assert.deepEqual(errors,[]);await browser.close();console.log('PRESENTATION BROWSER PASS: 157s; video/audio playback, Italian captions, downloads, 1400/390/320px, HR info and close/pause.');
})().catch(e=>{console.error(e);process.exit(1)});
