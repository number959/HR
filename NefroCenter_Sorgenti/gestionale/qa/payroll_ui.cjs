/* UI interaction smoke: run with node qa/payroll_ui.cjs after installing Playwright. */
const {chromium}=require('playwright');
const path=require('path');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{}),headless:true,args:process.env.QA_CHROMIUM_NO_SANDBOX==='1'?['--no-sandbox']:[]});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<div class="actions"><input id="monthPick"></div><div id="content"></div>');
  await page.evaluate(()=>{
   window.$=s=>document.querySelector(s);window.esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
   window.auth={user:{id:'hr1',role:'hr'}};window.cid='center1';window.month='2026-10';window.tab='paghe';window.notifications=[];window.toast=t=>notifications.push(t);
   const fields=[['template_version','Versione',true],['center_code','Centro',true],['registration','Matricola',true],['day','Data',true],['payroll_code','Causale',true],['person_name','Nome',false]];
   window.fixture={version:0,center:'Centro demo',fields:fields.map(([id,label,required])=>({id,label,required,type:'text'})),people:[{id:'person1',name:'Mario Rossi',registration:'001'}],causes:[{id:'m',label:'Mattina',kind:'work'}],history:[],config:{name:'Modello da concordare',status:'draft',confirmation_note:'',delimiter:';',decimal_separator:',',columns:fields.slice(0,5).map(([field,label])=>({field,label})),causes:{m:''},registrations:{}}};
   window.calls=[];window.api=async(route,body)=>{
    calls.push({route,body});
    if(route.startsWith('payroll_config'))return structuredClone(fixture);
    if(route==='payroll_spec_preview'){
     const columns=body.text.split(';').map(label=>({field:'',label}));
     return {connector:{mode:'consultant',provider:'',format_name:'',format_version:'',specification_reference:'',expected_columns:columns.map(c=>({header:c.label,type:'text',required:true,max_length:null})),date_format:'YYYY-MM-DD',encoding:'utf-8-sig'},columns,delimiter:';',decimal_separator:',',unmapped:columns.length,notice:'Specifica letta in bozza.'};
    }
    if(route==='payroll_save'){fixture.config=structuredClone(body.config);fixture.version++;return {ok:true,version:fixture.version}}
    if(route.startsWith('payroll_preview'))return {cid,center_code:'DEMO',first:'2026-10',last:'2026-10',version:fixture.version,template_name:fixture.config.name,status:fixture.config.status,columns:fixture.config.columns,rows:[[fixture.version,'DEMO','001','2026-10-15','ORD']],shown_rows:1,issues:[],shown_issues:0,summary:{rows:1,people:1,known_minutes:360,blocking_issues:0,warnings:0},can_download:true,fingerprint:'a'.repeat(64)};
    throw Error('Unexpected route '+route)
   };
   window.downloads=[];window.downloadFile=async(...args)=>downloads.push(args);
  });
  await page.addScriptTag({path:path.join(__dirname,'../assets/payroll.js')});
  await page.evaluate(()=>renderPayroll());
  assert.equal(await page.locator('#payrollStatus').inputValue(),'draft');
  await page.locator('#payrollName').fill('Modello verificato');
  await page.locator('#payrollPreviewLoad').click();
  await page.locator('#payrollPreviewResult .error').waitFor();
  assert.match(await page.locator('#payrollPreviewResult').innerText(),/Salva le modifiche/);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.startsWith('payroll_preview')).length),0);
  await page.locator('#payrollAddColumn').click();
  assert.equal(await page.locator('[data-payroll-label]').count(),6);
  await page.locator('[data-payroll-up="5"]').click();
  assert.equal(await page.locator('[data-payroll-label="4"]').inputValue(),'Nome');
  await page.locator('[data-payroll-remove="4"]').click();
  await page.locator('[data-payroll-cause="0"]').fill('ORD');
  await page.getByText('Matricole paghe delle persone (1)',{exact:true}).click();
  await page.locator('[data-payroll-registration="0"]').fill('00077');
  await page.locator('#payrollStatus').selectOption('confirmed');
  await page.locator('#payrollConfirmation').fill('Specifiche del consulente verificate');
  await page.locator('#payrollSave').click();
  await page.waitForFunction(()=>document.querySelector('#payrollSaveState')?.textContent==='Modello salvato · verificato');
  assert.equal(await page.evaluate(()=>fixture.config.causes.m),'ORD');
  assert.equal(await page.evaluate(()=>fixture.config.registrations.person1),'00077');
  assert.equal(await page.evaluate(()=>fixture.config.columns.length),5);
  await page.locator('#payrollPreviewLoad').click();
  await page.locator('[data-payroll-download="csv"]').waitFor();
  await page.locator('[data-payroll-download="csv"]').click();
  const download=await page.evaluate(()=>downloads[0]);
  assert.match(download[0],/fingerprint=a{64}/);
  assert.match(download[0],/from=2026-10&to=2026-10/);
  await page.locator('#payrollName').fill('Bozza non salvata di HR1');
  assert.equal(await page.locator('[data-payroll-download]').count(),0);
  await page.evaluate(()=>renderPayroll());
  assert.equal(await page.locator('#payrollName').inputValue(),'Bozza non salvata di HR1');
  await page.evaluate(()=>{auth.user={id:'hr2',role:'hr'};return renderPayroll()});
  assert.equal(await page.locator('#payrollName').inputValue(),'Modello verificato');
  await page.locator('#payrollConnectorMode').selectOption('consultant');
  assert.equal(await page.locator('#payrollStatus').inputValue(),'draft');
  await page.getByText('Leggi le intestazioni o un file di specifiche',{exact:true}).click();
  await page.locator('#payrollSpecText').fill('MATR;GIORNO;CAUSALE');
  await page.locator('#payrollSpecRead').click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-payroll-map]').length===3);
  assert.equal(await page.locator('[data-payroll-map="0"]').inputValue(),'');
  for(const [i,field] of ['registration','day','payroll_code'].entries())await page.locator(`[data-payroll-map="${i}"]`).selectOption(field);
  await page.locator('[data-payroll-type="1"]').selectOption('date');
  await page.locator('[data-payroll-max="0"]').fill('12');
  await page.locator('#payrollProvider').fill('Gestionale test');
  await page.locator('#payrollFormatName').fill('Presenze');
  await page.locator('#payrollFormatVersion').fill('2026');
  await page.locator('#payrollSpecificationReference').fill('Specifica test');
  await page.locator('#payrollDateFormat').selectOption('DD/MM/YYYY');
  await page.locator('#payrollEncoding').selectOption('cp1252');
  await page.locator('#payrollStatus').selectOption('confirmed');
  await page.locator('#payrollConfirmation').fill('Consulente ha verificato la versione');
  await page.locator('#payrollSave').click();
  assert.match(await page.locator('#payrollConfigError').innerText(),/Conferma di aver verificato/);
  await page.locator('#payrollConnectorConfirm').check();
  await page.locator('#payrollProvider').fill('Gestionale test aggiornato');
  assert.equal(await page.locator('#payrollConnectorConfirm').isChecked(),false);
  await page.locator('#payrollConnectorConfirm').check();
  await page.locator('#payrollSave').click();
  await page.waitForFunction(()=>document.querySelector('#payrollSaveState')?.textContent==='Modello salvato · verificato');
  const saved=await page.evaluate(()=>calls.filter(c=>c.route==='payroll_save').at(-1).body);
  assert.equal(saved.confirm_connector,true);
  assert.deepEqual(saved.config.columns.map(c=>c.label),['MATR','GIORNO','CAUSALE']);
  assert.equal(saved.config.connector.expected_columns[1].type,'date');
  assert.equal(saved.config.connector.encoding,'cp1252');
  assert.equal(saved.config.connector.date_format,'DD/MM/YYYY');
  assert.deepEqual(errors,[]);
  console.log('Payroll UI: configuration, ordering, dirty state, preview, download, user isolation, consultant spec import/mapping and explicit version confirmation passed.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
