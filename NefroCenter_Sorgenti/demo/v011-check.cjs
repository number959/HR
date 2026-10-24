const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const dir=path.join(__dirname,'dist'),seed=JSON.parse(fs.readFileSync(path.join(dir,'demo_seed.json')));
function setup(role,values=new Map()){
 values.set('nefrocenter-public-demo-v011-role',role);const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const ctx={console,URL,Response,structuredClone,crypto:require('node:crypto').webcrypto,TextEncoder,TextDecoder,Buffer,Uint8Array,Date,Promise,Map,Set,Math,JSON,Object,Array,String,Number,Boolean,RegExp,Error,Intl,encodeURIComponent,decodeURIComponent,btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),queueMicrotask,setTimeout,clearTimeout,sessionStorage:storage,localStorage:storage,month:'',workforceOn:'',toast:()=>{},location:{href:'https://demo.test/',origin:'https://demo.test',pathname:'/'},navigator:{},document:{readyState:'loading',addEventListener:()=>{},getElementById:id=>id==='demoBanner'?{querySelector:()=>true}:null}};
 ctx.window=ctx;ctx.nativeRequests=0;ctx.fetch=async input=>{ctx.nativeRequests++;const p=path.join(dir,new URL(String(input),'https://demo.test').pathname);return fs.existsSync(p)?new Response(fs.readFileSync(p),{headers:{'Content-Type':p.endsWith('.json')?'application/json':'application/octet-stream'}}):new Response('missing',{status:404})};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(dir,'demo.js'),'utf8'),ctx);return ctx;
}
async function call(ctx,url,body,expected=200){const r=await ctx.fetch('/api/'+url,body?{method:'POST',body:JSON.stringify(body)}:{});const out=await r.json();assert.equal(r.status,expected,JSON.stringify({url,out}));return out}
(async()=>{
 const values=new Map();let c=setup('admin',values);await c.Demo.ready;let auth=await call(c,'auth');const cid=auth.centers[0].id,other=auth.centers[1].id,month='2026-11';
 let s=await call(c,'state?cid='+cid+'&month='+month),pid=s.people[0].id;
 await call(c,'entry',{cid,month,revision:s.center.revision,entry:{person_id:pid,day:month+'-02',slot:'m',code:'m',layer:'actual',start:'07:00',end:'13:00',pause:0,overnight:false,holiday:false,work_site:s.center.name,note:'Percorso approvazione demo'}});
 async function as(role){c=setup(role,values);await c.Demo.ready;await call(c,'auth')}
 async function workflow(action,extra={}){const d=await call(c,`approvals?cid=${cid}&month=${month}`);return call(c,'approval_transition',{cid,month,version:d.workflow.version,fingerprint:d.fingerprint,action,note:'Controllo dimostrativo completo',...extra})}
 await as('operator');let submitted=await workflow('submit');assert.equal(submitted.workflow.status,'submitted');
 await call(c,'period_verify',{cid,month,verified:true},400);
 await as('manager');
 const managerApproval=await call(c,`approvals?cid=${cid}&month=${month}`);assert.equal(managerApproval.can_configure,false);
 await call(c,'approval_config_save',{cid,month,...managerApproval.policy},403);
 assert.deepEqual((await call(c,`approvals?cid=${cid}&month=${month}`)).policy,managerApproval.policy);
 const verified=await workflow('manager_approve',{calendar_checked:true});assert.equal(verified.workflow.status,'manager_approved');
 await call(c,'approval_transition',{cid,month,version:verified.workflow.version,fingerprint:verified.fingerprint,action:'hr_approve'},403);
 await as('hr');const approved=await workflow('hr_approve');assert.equal(approved.workflow.status,'hr_approved');assert.equal((await call(c,`state?cid=${cid}&month=${month}`)).period.closed,true);
 const reopened=await workflow('reopen');assert.equal(reopened.workflow.status,'draft');assert.equal(reopened.history.length,4);
 await as('admin');await call(c,'close',{cid,month},400);
 // Documents are visible centrally; manager resubmits but cannot validate.
 const listing=await call(c,'hr?cid='+cid),person=listing.employees[0].id;
 const upload=await call(c,'hr_document_add',{cid,pid:person,demoSample:true,category:'Contratto',expiry:'2027-12-31'});
 let review=await call(c,`hr_document_review?cid=${cid}&id=${upload.id}`);assert.equal(review.review.status,'received');
 await as('hr');review=await call(c,'hr_document_review',{cid,id:upload.id,version:review.review.version,status:'needs_correction',note:'Verificare la firma dimostrativa'});assert.equal(review.review.status,'needs_correction');
 await as('manager');await call(c,'hr_document_review',{cid,id:upload.id,version:review.review.version,status:'verified',note:''},403);
 review=await call(c,'hr_document_review',{cid,id:upload.id,version:review.review.version,status:'received',note:'Correzione verificata dalla sede'});assert.equal(review.review.status,'received');
 await as('hr');review=await call(c,'hr_document_review',{cid,id:upload.id,version:review.review.version,status:'verified',note:'Firma verificata'});assert.equal(review.history_total,4);
 await call(c,'hr_document_review',{cid,id:upload.id,version:1,status:'verified'},400);
 const filtered=await call(c,'hr_documents?review=verified');assert.ok(filtered.documents.some(d=>d.id===upload.id));
 assert.equal((await call(c,`hr_document_review?cid=${cid}&id=${upload.id}&offset=2&limit=1`)).history.length,1);
 // Departure blocker enforces both tasks and equipment, leaving employee unchanged.
 const before=await call(c,`hr?cid=${cid}&pid=${person}`);
 const asset=await call(c,'equipment_save',{cid,pid:person,version:0,kind:'badge',inventory_code:'DEMO BADGE 19',label:'Badge fittizio',delivery_date:'2026-10-01',due_date:'2026-10-19',note:''});
 let departure=await call(c,'departure_case_save',{cid,pid:person,version:0,kind:'termination',destination_cid:'',effective_date:'2026-10-19',responsible:'Referente fittizio',reason:'Cessazione simulata per collaudo'});
 await call(c,'departure_case_transition',{cid,id:departure.id,version:departure.version,status:'completed',note:'Verifiche conclusive completate',confirm:true},400);
 for(const task of departure.tasks){departure=await call(c,'departure_task_save',{cid,id:departure.id,version:departure.version,task_id:task.id,status:'done',owner:task.owner,due:task.due,note:'Completato per dimostrazione'})}
 assert.equal(departure.can_complete,false);
 await call(c,'equipment_return',{cid,id:asset.asset.id,version:asset.asset.version,return_date:'2026-10-19',condition:'good',note:''});
 departure=await call(c,'departure_case_transition',{cid,id:departure.id,version:departure.version,status:'completed',note:'Verifiche conclusive completate',confirm:true});assert.equal(departure.status,'completed');
 assert.deepEqual((await call(c,`hr?cid=${cid}&pid=${person}`)).person,before.person);
 // Coverage, explicit linked identity, proposal requires destination manager.
 await as('admin');let staffing=await call(c,`staffing?cid=${cid}&month=2026-10`);assert.ok(staffing.summary.configured>0);const candidate=staffing.candidates[0];assert.ok(candidate);
 const proposal=await call(c,'staffing_propose',{cid,pid:candidate.pid,origin_cid:candidate.origin_cid,origin_pid:candidate.origin_pid,day:'2026-10-28',slot:'m',code:'m',note:'Sostituzione dimostrativa autorizzata'});
 await as('hr');await call(c,'staffing_decide',{id:proposal.id,version:1,decision:'accept',note:'Controllo completo della proposta'},403);
 await as('admin');const accepted=await call(c,'staffing_decide',{id:proposal.id,version:1,decision:'accept',note:'Controllo completo della proposta'});assert.equal(accepted.status,'accepted');
 const planned=(await call(c,`state?cid=${cid}&month=2026-10`)).entries.filter(e=>e.id===accepted.entry_id);assert.equal(planned.length,1);assert.equal(planned[0].layer,'planned');
 await call(c,'staffing_decide',{id:proposal.id,version:1,decision:'accept',note:'Replay della stessa proposta'},400);
 const availability=await call(c,'staffing_availability_save',{cid,pid:candidate.pid,version:0,from:'2026-10-29',to:'2026-10-29',status:'unavailable',note:'Indicazione riservata fittizia',active:true});assert.equal(availability.availability.version,1);
 await call(c,'staffing_propose',{cid,pid:candidate.pid,origin_cid:candidate.origin_cid,origin_pid:candidate.origin_pid,day:'2026-10-29',slot:'m',code:'m',note:'Proposta in conflitto con indisponibilità'},400);
 // Reminder preview/configuration never performs network requests and deduplicates events.
 let reminders=await call(c,'reminders'),config={...reminders.config,enabled:true};const preview=await call(c,'reminder_preview',config);assert.ok(preview.can_enable);const nativeBefore=c.nativeRequests;
 reminders=await call(c,'reminder_config_save',{...config,fingerprint:preview.fingerprint,confirmed:true});assert.equal(c.nativeRequests,nativeBefore);assert.ok(reminders.history.every(h=>h.status==='simulated'));const count=reminders.history.length;
 const next=await call(c,'reminder_preview',reminders.config);reminders=await call(c,'reminder_config_save',{...reminders.config,fingerprint:next.fingerprint,confirmed:true});assert.equal(reminders.history.length,count);
 assert.ok(reminders.history.every(h=>!h.body.includes('Anna Rossi')&&!h.body.includes('Marco Bianchi')));
 // Provider-free mapping preview rejects employee rows and unknown formats.
 const spec=await call(c,'payroll_spec_preview',{cid,kind:'csv_header',text:'registration;day;payroll_code',delimiter:';'});assert.equal(spec.unmapped,0);assert.equal(spec.stored,false);
 await call(c,'payroll_spec_preview',{cid,kind:'csv_header',text:'registration;day;payroll_code\nA;2026-10-19;L',delimiter:';'},400);
 const cfg=await call(c,'payroll_config?cid='+cid);await call(c,'payroll_save',{cid,expected_version:cfg.version,confirm_connector:true,config:{...cfg.config,status:'confirmed',confirmation_note:'Conferma tracciato fittizio',columns:spec.columns,connector:spec.connector}},400);
 const exported=await call(c,'payroll_specification?cid='+cid);assert.equal(exported.schema,'nefrocenter.payroll-spec.v1');assert.ok(!JSON.stringify(exported).includes('Anna Rossi'));
 for(const role of ['operator','viewer']){await as(role);for(const route of ['departures','reminders','hr_document_review?cid='+cid+'&id='+upload.id])await call(c,route,undefined,403);const aggregate=await call(c,`staffing?cid=${cid}&month=2026-10`);assert.equal(aggregate.availability.length,0);assert.equal(aggregate.candidates.length,0);assert.equal(aggregate.permissions.configure,false);}
 await as('manager');await call(c,'staffing?cid='+other+'&month=2026-10',undefined,403);
 console.log('PASS v0.11 demo: six feature workflows, five roles, scoped data, concurrency guards, reminder deduplication and no real email');
})().catch(e=>{console.error(e);process.exit(1)});
