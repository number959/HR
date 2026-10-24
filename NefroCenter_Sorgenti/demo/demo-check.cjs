const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const dir=path.join(__dirname,'dist'),seed=JSON.parse(fs.readFileSync(path.join(dir,'demo_seed.json')));
function setup(role){
 const values=new Map([['nefrocenter-public-demo-v011-role',role]]),storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const ctx={console,URL,Response,structuredClone,crypto:require('node:crypto').webcrypto,TextEncoder,TextDecoder,Buffer,Uint8Array,Date,Promise,Map,Set,Math,JSON,Object,Array,String,Number,Boolean,RegExp,Error,Intl,encodeURIComponent,decodeURIComponent,btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),queueMicrotask,setTimeout,clearTimeout,sessionStorage:storage,localStorage:storage,month:'',workforceOn:'',toast:()=>{},location:{href:'https://demo.test/',origin:'https://demo.test',pathname:'/'},navigator:{},document:{readyState:'loading',addEventListener:()=>{},getElementById:id=>id==='demoBanner'?{querySelector:()=>true}:null}};
 ctx.window=ctx;ctx.nativeRequests=0;ctx.fetch=async input=>{ctx.nativeRequests++;const p=path.join(dir,new URL(String(input),'https://demo.test').pathname);return fs.existsSync(p)?new Response(fs.readFileSync(p),{headers:{'Content-Type':p.endsWith('.json')?'application/json':'application/octet-stream'}}):new Response('missing',{status:404})};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(dir,'demo.js'),'utf8'),ctx);return ctx;
}
async function call(ctx,url,body,expected=200){const r=await ctx.fetch('/api/'+url,body?{method:'POST',body:JSON.stringify(body)}:{});const out=await r.json();assert.equal(r.status,expected,JSON.stringify({url,out}));return out}
(async()=>{
 for(const role of ['admin','hr','manager','operator','viewer']){
  const c=setup(role);await c.Demo.ready;const auth=await call(c,'auth');assert.equal(auth.user.role,role);assert.equal(c.month,'2026-10');
  const cid=auth.centers[0].id,s=await call(c,'state?cid='+cid+'&month=2026-10');assert.equal(s.center.id,cid);
  const overview=await call(c,'overview?month=2026-10');assert.equal(overview.centers.length,auth.centers.length);
  const stats=await call(c,'statistics?from=2026-10&to=2026-10&cid='+cid);assert.equal(stats.summary.work_shifts,s.summary.reduce((a,p)=>a+p.shifts,0));
  await call(c,'tasks?month=2026-10');await call(c,'security');
  const hr=['admin','hr','manager'].includes(role);
  const comm=await call(c,'communications',undefined,['admin','hr'].includes(role)?200:403);
  if(['admin','hr'].includes(role)){
   assert.equal(comm.settings.simulation,true);assert.equal(comm.settings.demo_simulated,true);
   const template=comm.templates.find(t=>t.id==='seed-benvenuto'),list=comm.lists.find(l=>l.recipient_type==='employees');
   const payload={template_id:template.id,list_id:list.id},preview=await call(c,'communication_preview',payload);assert.equal(preview.counts.valid,9);assert.equal(preview.can_create,true);assert.equal(preview.recipients[0].subject.includes('{{'),false);
   const saved=await call(c,'communication_template_save',{...template,subject:'Benvenuto aggiornato in {{struttura}}'});assert.equal(saved.version,template.version+1);
   await call(c,'communication_campaign_create',{...payload,fingerprint:preview.fingerprint},400);
   const fresh=await call(c,'communication_preview',payload),campaign=await call(c,'communication_campaign_create',{...payload,fingerprint:fresh.fingerprint});
   assert.equal(campaign.counts.pending,9);await call(c,'communication_send',{id:campaign.id,confirmation_token:campaign.confirmation_token,confirm:false},400);
   const before=c.nativeRequests,sent=await call(c,'communication_send',{id:campaign.id,confirmation_token:campaign.confirmation_token,confirm:true,retry_failed:false});
   assert.equal(c.nativeRequests,before,'La simulazione non deve effettuare richieste esterne');assert.equal(sent.counts.simulated,9);assert.equal(sent.counts.accepted,0);assert.equal(sent.status,'simulated');assert.ok(sent.recipients.every(r=>r.status==='simulated'&&r.attempts.length===1));
   await call(c,'communication_send',{id:campaign.id,confirmation_token:campaign.confirmation_token,confirm:true,retry_failed:false},400);
   await call(c,'communication_config_save',{host:'smtp.example.invalid'},400);
   const filtered=await call(c,'communication_list_save',{...list,exclude_emails:[fresh.recipients[0].email]});
   const excluded=await call(c,'communication_preview',payload);assert.equal(excluded.counts.excluded,1);assert.equal(excluded.counts.valid,8);assert.equal(filtered.version,list.version+1);
   const structureList=comm.lists.find(l=>l.recipient_type==='structures'),structurePreview=await call(c,'communication_preview',{template_id:'seed-sede',list_id:structureList.id});assert.equal(structurePreview.counts.valid,3);assert.ok(structurePreview.recipients.every(r=>r.email.startsWith('hr.sede')));
  }
  await call(c,'hr_documents',undefined,hr?200:403);await call(c,'workforce',undefined,hr?200:403);await call(c,'payroll_config?cid='+cid,undefined,hr?200:403);
  const structures=await call(c,'structures?cid=all',undefined,hr?200:403);
  if(hr){
   assert.equal(structures.structures.length,auth.centers.length);
   const detail=await call(c,'structures?cid='+cid),oldVersion=detail.structure.version;
   const changed=await call(c,'structure_save',{cid,version:oldVersion,fields:{...detail.structure.fields,contact_name:'Referente modificato demo'}});
   assert.equal(changed.structure.version,oldVersion+1);
   await call(c,'structure_save',{cid,version:oldVersion,fields:detail.structure.fields},400);
   const listing=await call(c,'hr?cid='+cid),person=await call(c,'hr?cid='+cid+'&pid='+listing.employees[0].id);
   assert.equal(person.structure.fields.contact_name,'Referente modificato demo');
   if(role==='manager')await call(c,'structures?cid='+seed.centers.find(x=>x.id!==cid).id,undefined,403);
  }
  if(hr){const list=await call(c,'hr?cid='+cid);await call(c,'hr?cid='+cid+'&pid='+list.employees[0].id);await call(c,'payroll_preview?cid='+cid+'&from=2026-10&to=2026-10');}
  if(role==='admin'){
   const current=await call(c,'state?cid='+cid+'&month=2026-10'),pid=current.people[0].id,old=current.entries.length;
   await call(c,'entry',{cid,month:'2026-10',revision:current.center.revision,entry:{person_id:pid,day:'2026-10-26',slot:'m',code:'m',layer:'actual',start:'07:00',end:'13:00',pause:0,overnight:false,holiday:false,work_site:s.center.name,note:'Prova fittizia'}});
   const changed=await call(c,'state?cid='+cid+'&month=2026-10');assert.equal(changed.entries.length,old+1);
   const st=await call(c,'statistics?from=2026-10&to=2026-10&cid='+cid);assert.equal(st.summary.work_shifts,stats.summary.work_shifts+1);
   await call(c,'backup_policy');const x=await c.fetch('/api/export_xlsx?kind=presenze_centro&cid='+cid);assert.equal(x.status,200);assert.equal(Buffer.from(await x.arrayBuffer()).subarray(0,2).toString(),'PK');
  }
  console.log('PASS demo adapter '+role);
 }
 const clean=setup('admin');await clean.Demo.ready;const a=await call(clean,'auth'),s=await call(clean,'state?cid='+a.centers[0].id+'&month=2026-10');assert.equal(s.entries.length,seed.snapshots[a.centers[0].id].entries.length);
 console.log('PASS isolamento nuova sessione; verifiche API senza browser e senza rete');
})().catch(e=>{console.error(e);process.exit(1)});
