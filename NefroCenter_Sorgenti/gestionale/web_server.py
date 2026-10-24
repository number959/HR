"""Single-origin web application. Run behind HTTPS; HTTP is loopback-test only."""
import argparse, base64, csv, io, json, logging, os, re, secrets, sqlite3, sys, threading, time, zipfile
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs
import core, hr, agreements, analytics, excel_exports, backup_tools, backup_policy, workforce, payroll, tasks, structures, communications, approvals, document_reviews, reminders, staffing, departures
from web_auth import Auth, AuthError
from waitress import serve

BASE = Path(__file__).resolve().parent
LOG = logging.getLogger('presenze.web')
MAX_BODY = 18_000_000


class WebApp:
    def __init__(self, data_dir, key_file, origin, dev=False):
        url = urlsplit(origin)
        if url.path not in ('', '/') or url.query or url.fragment or url.username or url.password or not url.hostname:
            raise ValueError('Origin non valido: usare solo https://nome-server.')
        if url.scheme != 'https' and not (dev and url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('HTTPS obbligatorio. --dev-http è ammesso solo su loopback per il collaudo.')
        self.origin = origin.rstrip('/'); self.host = url.netloc.lower(); self.secure = url.scheme == 'https'
        self.cookie_name = '__Host-presenze' if self.secure else 'presenze_web_dev'
        core.DB = Path(data_dir).resolve()/'presenze.sqlite3'; core.init_db()
        with core.connect() as c: c.execute('PRAGMA journal_mode=WAL'); c.commit()
        self.auth = Auth(key_file)
        core.revoke = self.auth.revoke

    def cookie(self, raw):
        return self.cookie_name+'='+raw+'; HttpOnly; SameSite=Strict; Path=/'+('; Secure' if self.secure else '')

    def sid(self, env):
        cookies = SimpleCookie()
        try: cookies.load(env.get('HTTP_COOKIE', ''))
        except Exception: return ''
        return cookies[self.cookie_name].value if self.cookie_name in cookies else ''

    def overview(self, user, month):
        core.month_days(month)
        with core.connect() as c:
            user = core.fresh_user(c, user); centers = core.centers_for(c, user)
        result = []
        for center in centers:
            s = core.snapshot(user, center['id'], month)
            with core.connect() as c:
                last = c.execute('SELECT max(stamp) FROM audit WHERE cid=?', (center['id'],)).fetchone()[0]
            result.append(dict(id=center['id'],name=center['name'],code=center['code'],
                closed=s['period']['closed'],verified=s['period']['verified'],
                recorded=bool(s['entries']),people=sum(bool(p['active']) for p in s['people']),
                minutes=sum(x['minutes'] for x in s['summary']),shifts=sum(x['shifts'] for x in s['summary']),
                pending=sum(x['pending'] for x in s['summary']),missing=sum(x['missing'] for x in s['summary']),
                last_update=last))
        return {'month':month,'centers':result,'generated_at':core.now()}

    def group_csv(self, user, month):
        if user['role'] not in ('admin','hr','viewer'): raise PermissionError('Riepilogo del gruppo riservato alla Direzione.')
        data = self.overview(user, month); buf = io.StringIO(); w = csv.writer(buf, delimiter=';')
        def row(xs): w.writerow(["'"+str(x) if str(x).lstrip().startswith(('=','+','-','@')) else x for x in xs])
        row(['Centro','Codice','Mese','Stato','Presenze compilate','Persone attive','Minuti lavorati','Turni','Da consuntivare','Turni senza orari'])
        for c in data['centers']: row([c['name'],c['code'],month,'CHIUSO' if c['closed'] else 'APERTO','SI' if c['recorded'] else 'NO',c['people'],c['minutes'],c['shifts'],c['pending'],c['missing']])
        return ('\ufeff'+buf.getvalue()).encode()

    def route(self, env):
        method = env.get('REQUEST_METHOD', 'GET'); path = env.get('PATH_INFO', '/')
        query = parse_qs(env.get('QUERY_STRING', '')); cookie = None
        if env.get('HTTP_HOST', '').lower() != self.host: raise AuthError('Indirizzo del servizio non consentito.', 403)
        if env.get('HTTP_ORIGIN') not in (None, self.origin): raise AuthError('Origine della richiesta non consentita.', 403)
        if env.get('HTTP_SEC_FETCH_SITE') == 'cross-site': raise AuthError('Richiesta esterna non consentita.', 403)
        if method == 'GET' and path == '/': return (BASE/'ui.html').read_bytes(), 'text/html; charset=utf-8', None
        assets = {'guida_illustrata.pdf','approvals.js','approvals.css','reminders.js','reminders.css','staffing.js','staffing.css','departures.js','departures.css','structures.js','structures.css','communications.js','communications.css','statistics.js','statistics.css','exports.js','exports.css','themes.css','themes.js','brand.css','web.css','icons.js','hr_ui.js','app.js','web_ui.js','monthly.js','monthly.css','hr_complete.css','nefrocenter.png','roboto.woff2','backup_policy.js','backup_policy.css','hr_central.js','tasks.js','tasks.css','workforce.js','workforce.css','payroll.js','payroll.css','help.js','help.css','help_content.js','help_videos.js'}
        if method == 'GET' and path.startswith('/assets/') and path[8:] in assets:
            ext = path.rsplit('.',1)[-1]; types = {'css':'text/css; charset=utf-8','js':'application/javascript; charset=utf-8','png':'image/png','woff2':'font/woff2','pdf':'application/pdf'}
            return (BASE/path.lstrip('/')).read_bytes(), types[ext], None
        if method == 'GET' and re.fullmatch(r'/assets/guide_screens/[a-z0-9_-]+\.webp',path):
            target=BASE/path.lstrip('/')
            if not target.is_file():raise AuthError('Schermata non trovata.',404)
            return target.read_bytes(),'image/webp',None
        if method == 'GET' and re.fullmatch(r'/assets/guides/[a-z0-9_-]+\.(mp4|vtt|txt|jpg)',path):
            target=BASE/path.lstrip('/')
            if not target.is_file():raise AuthError('Guida non trovata.',404)
            types={'jpg':'image/jpeg','mp4':'video/mp4','vtt':'text/vtt; charset=utf-8','txt':'text/plain; charset=utf-8'}
            return target.read_bytes(),types[target.suffix[1:]],None
        if method == 'GET' and path == '/health': return {'product':'PresenzeWeb','version':'0.11'}, None, None
        if method not in ('GET','POST'): raise AuthError('Metodo non consentito.', 405)
        raw_sid = self.sid(env)
        if method == 'GET' and path == '/api/auth':
            self.auth.rate_check('browser:'+env.get('REMOTE_ADDR',''))
            session, cookie = self.auth.browser(raw_sid)
            if cookie: self.auth.rate_fail('browser:'+env.get('REMOTE_ADDR',''),120,60)
            return self.auth.state(session), None, cookie
        s = self.auth.session(raw_sid, touch=env.get('HTTP_X_BACKGROUND_REFRESH')!='1')
        body = {}
        if method == 'POST':
            if env.get('HTTP_ORIGIN') != self.origin: raise AuthError('Origine della richiesta obbligatoria.', 403)
            if not secrets.compare_digest(env.get('HTTP_X_PRESENZE_TOKEN',''), s['csrf']): raise AuthError('Sessione della pagina cambiata. Ricarica la pagina.', 403)
            if env.get('CONTENT_TYPE','').split(';')[0] != 'application/json': raise AuthError('Inviare dati JSON.', 415)
            length = int(env.get('CONTENT_LENGTH') or 0)
            if not 0 < length <= MAX_BODY: raise AuthError('Richiesta vuota o troppo grande.', 413)
            body = json.loads(env['wsgi.input'].read(length))
            if not isinstance(body, dict): raise ValueError('Dati non validi.')
        if method == 'POST' and path == '/api/login': out, cookie = self.auth.login(s, body, env.get('REMOTE_ADDR','')); return out, None, cookie
        if method == 'POST' and path == '/api/logout': out, cookie = self.auth.logout(s); return out, None, cookie
        if method == 'POST' and path == '/api/enroll/start': return self.auth.enroll_start(s, body), None, None
        if method == 'POST' and path == '/api/enroll/confirm': out, cookie = self.auth.enroll_confirm(s, body); return out, None, cookie
        if method == 'POST' and path == '/api/mfa': out, cookie = self.auth.verify(s, body); return out, None, cookie
        user = self.auth.user(s)
        if method == 'GET':
            if path == '/api/approvals': return approvals.read(core,user,query['cid'][0],query['month'][0]),None,None
            if path == '/api/reminders': return reminders.overview(core,user),None,None
            if path == '/api/staffing': return staffing.report(core,user,query['cid'][0],query['month'][0]),None,None
            if path == '/api/departures': return departures.overview(core,user,query.get('cid',['all'])[0]),None,None
            if path == '/api/departure_case': return departures.case_read(core,user,query['cid'][0],query['id'][0]),None,None
            if path == '/api/hr_document_review': return document_reviews.read(core,user,query['cid'][0],query['id'][0],query.get('offset',[0])[0],query.get('limit',[25])[0]),None,None
            if path == '/api/payroll_specification': return payroll.specification(core,user,query['cid'][0]),None,None
            if path == '/api/structures': return structures.read(core,user,query.get('cid',['all'])[0]),None,None
            if path == '/api/communications': return communications.overview(core,user),None,None
            if path == '/api/communication_campaign': return communications.campaign(core,user,query.get('id',[''])[0]),None,None
            if path in ('/api/statistics','/api/statistics_csv','/api/export_xlsx'):
                args = dict(first=query.get('from',[''])[0], last=query.get('to',[''])[0],
                            cid=query.get('cid',['all'])[0], role=query.get('role',[''])[0], person_id=query.get('person_id',[''])[0])
                if path == '/api/statistics': return analytics.report(core,user,**args),None,None
                if path == '/api/statistics_csv': return analytics.export_csv(core,user,**args),'text/csv; charset=utf-8',None
                kind=query.get('kind',[''])[0]
                if kind in excel_exports.PRIVATE:
                    if user['role'] not in ('admin','manager','hr'): raise PermissionError('Prospetto riservato ai ruoli HR autorizzati.')
                    self.auth.require_recent(s)
                result=excel_exports.export(core,user,kind=kind,layer=query.get('layer',['actual'])[0],**args)
                with core.connect() as c:
                    core.audit(c,user,'Esportazione Excel',args['cid'],after={'tipo':kind,'dal':args['first'],'al':args['last']});c.commit()
                return result,excel_exports.MIME,None
            if path == '/api/tasks': return tasks.report(core,user,query['month'][0],query.get('cid',['all'])[0]),None,None
            if path == '/api/workforce': return workforce.read(core,user,query.get('gid',[None])[0],query.get('on',[None])[0]),None,None
            if path == '/api/workforce_preview': return workforce.preview(core,user,query['cid'][0],query['pid'][0],query['month'][0]),None,None
            if path == '/api/payroll_config': return payroll.read(core,user,query['cid'][0]),None,None
            if path == '/api/payroll_preview': return payroll.preview(core,user,query['cid'][0],query['from'][0],query['to'][0]),None,None
            if path == '/api/payroll_download':
                self.auth.require_recent(s)
                fmt=query.get('format',['csv'])[0]
                return payroll.export(core,user,query['cid'][0],query['from'][0],query['to'][0],fmt,query.get('fingerprint',[''])[0]),excel_exports.MIME if fmt=='xlsx' else 'text/csv; charset=utf-8',None
            if path == '/api/backup_policy': return backup_policy.status(core,user),None,None
            if path == '/api/hr_documents': return hr.document_index(core,user,query.get('cid',['all'])[0],query.get('person',[''])[0],query.get('category',[''])[0],query.get('expiry',['all'])[0],query.get('review',['all'])[0]),None,None
            if path == '/api/hr_document_view':
                data,mime,name=hr.document_view(core,user,query['cid'][0],query['id'][0])
                return data,mime,None
            if path == '/api/backups': return backup_tools.listing(core,user),None,None
            if path == '/api/backup_download':
                core.require_admin(user);self.auth.require_recent(s)
                return backup_tools.download(core,user,query.get('filename',[''])[0]),'application/vnd.sqlite3',None
            if path == '/api/state':
                out = core.snapshot(user, query['cid'][0], query['month'][0])
                if user['role']=='admin':
                    with core.connect() as c:
                        statuses = {r['user_id']:bool(r['enabled']) for r in c.execute('SELECT user_id,enabled FROM web_security')}
                    for u in out['users']: u['mfa_enabled'] = statuses.get(u['id'], False)
                return out, None, None
            if path == '/api/hr': return hr.read(core,user,query['cid'][0],query.get('pid',[None])[0]), None, None
            if path == '/api/hr_document': return hr.document_read(core,user,query['cid'][0],query['id'][0]), None, None
            if path == '/api/export': return core.export_csv(user,query['cid'][0],query['month'][0],query.get('detail',['0'])[0]=='1'), 'text/csv; charset=utf-8', None
            if path == '/api/overview': return self.overview(user,query['month'][0]), None, None
            if path == '/api/group_export': return self.group_csv(user,query['month'][0]), 'text/csv; charset=utf-8', None
            if path == '/api/agreements': return agreements.report(core,user,query['cid'][0],query['month'][0]),None,None
            if path == '/api/security': return self.auth.status(s), None, None
            raise AuthError('Pagina non trovata.', 404)
        if path == '/api/security/stepup': return self.auth.stepup(s,body), None, None
        if path == '/api/security/recovery': return self.auth.recovery_new(s), None, None
        if path == '/api/security/rotate/start': return self.auth.rotate_start(s), None, None
        if path == '/api/security/rotate/confirm': out,cookie=self.auth.rotate_confirm(s,body);return out,None,cookie
        if path == '/api/security/sessions': return self.auth.other_sessions(s), None, None
        if path == '/api/security/reset_user':
            core.require_admin(user); self.auth.require_recent(s)
            if body.get('user_id') == user['id']: raise ValueError('Per il tuo account usa Cambia dispositivo.')
            reason = str(body.get('reason','')).strip()
            if len(reason)<8: raise ValueError('Indica la motivazione del ripristino, almeno 8 caratteri.')
            code = self.auth.activation(body['user_id'],user,reason)
            return {'activation_code':code,'expires_days':7}, None, None
        action = path.removeprefix('/api/')
        feature_handlers = {
            'approval_config_save': approvals.configure, 'approval_transition': approvals.transition,
            'hr_document_review': document_reviews.review,
            'reminder_preview': reminders.preview, 'reminder_config_save': reminders.configure,
            'payroll_spec_preview': payroll.spec_preview,
            'staffing_requirements_save': staffing.save_requirements, 'staffing_availability_save': staffing.save_availability,
            'staffing_propose': staffing.propose, 'staffing_decide': staffing.decide,
            'departure_case_save': departures.case_save, 'departure_task_save': departures.task_save,
            'departure_case_transition': departures.case_transition,
            'equipment_save': departures.equipment_save, 'equipment_return': departures.equipment_return,
        }
        if action in feature_handlers:
            if action in ('reminder_config_save','approval_config_save'):
                core.require_admin(user); self.auth.require_recent(s)
            return feature_handlers[action](core,user,body),None,None
        if action == 'structure_save': return structures.save(core,user,body),None,None
        if action.startswith('communication_'):
            handlers={'communication_template_save':communications.save_template,
                'communication_list_save':communications.save_list,'communication_preview':communications.preview,
                'communication_campaign_create':communications.create_campaign,'communication_send':communications.send_campaign,
                'communication_reconcile':communications.reconcile_campaign,
                'communication_config_save':communications.save_configuration}
            if action not in handlers:raise AuthError('Operazione non trovata.',404)
            if user['role'] not in ('admin','hr'):raise PermissionError('Comunicazioni riservate a HR centrale e amministratori.')
            if action=='communication_config_save':core.require_admin(user)
            if action in ('communication_send','communication_config_save'):self.auth.require_recent(s)
            return handlers[action](core,user,body),None,None
        if action in ('backup_policy_save','backup_policy_run'):
            core.require_admin(user);self.auth.require_recent(s)
            out=backup_policy.configure(core,body,user) if action=='backup_policy_save' else backup_policy.run_admin(core,user,probe=bool(body.get('probe',False)))
            return out,None,None
        if action in ('workforce_link','workforce_contract','workforce_economic','workforce_apply'):
            self.auth.require_recent(s)
            return workforce.mutate(core,user,action,body),None,None
        if action == 'payroll_save':
            self.auth.require_recent(s)
            return payroll.save(core,user,body),None,None
        if action in ('hr_save','hr_task','hr_settings','hr_document_add','hr_document_delete'):
            core.require_hr(user,body.get('cid',''))
        if action in ('user_save','center_create','backup','import_preview','import_confirm','simulate'):
            core.require_admin(user)
        if action in ('center_save','person','period_verify','close','reopen','patient','apply_rules','agreement_save'):
            core.require_manager(user,body.get('cid',''))
        if action in ('user_save','password','backup','import_preview','import_confirm','center_create','center_save','hr_settings','agreement_save'):
            self.auth.require_recent(s)
        if action in ('hr_save','hr_task','hr_settings','hr_document_add','hr_document_delete'):
            fn = {'hr_save':hr.save,'hr_task':hr.task_save,'hr_settings':hr.settings_save,'hr_document_add':hr.document_add,'hr_document_delete':hr.document_delete}[action]
            return fn(core,user,body), None, None
        if action == 'backup': return core.backup(user), None, None
        if action == 'import_preview':
            core.require_admin(user); model = core.read_model(base64.b64decode(body['content'],validate=True)); key=core.uid()
            with core.LOCK:
                if len(core.PENDING)>6: core.PENDING.pop(next(iter(core.PENDING)))
                core.PENDING[key] = {'owner':user['id'],'created':time.monotonic(),'model':model}
            return {'key':key,'center':model['center'],'month':model['month'],'people':len(model['people']),'entries':len(model['entries']),'warnings':model['warnings']},None,None
        if action == 'import_confirm': return core.import_confirm(user,body['key']), None, None
        if action == 'simulate':
            core.require_admin(user); snap=core.snapshot(user,body['cid'],body['month']); cfg=snap['period']['config']
            if body.get('person_id'):
                person=next((p for p in snap['people'] if p['id']==body['person_id']),None)
                if not person: raise ValueError('Persona non trovata.')
                cfg={**cfg,**(person.get('pay_override') or {})}
            out=core.simulate_legacy_pay(body['total'],snap['working_days'],body['festive'],body.get('ccnl_festive',0),cfg['weekday_rate'],cfg['holiday_rate'],cfg['fixed_deduction'],cfg['ccnl_rate'],cfg['pay_mode']=='all')
            out['parameters']={k:cfg[k] for k in ('weekday_rate','holiday_rate','fixed_deduction','ccnl_rate','pay_mode')};return out,None,None
        allowed={'user_save','password','center_create','center_save','person','period_verify','close','reopen','patient','apply_rules','entry','delete','agreement_save'}
        if action not in allowed: raise AuthError('Operazione non disponibile.',404)
        new_user = action=='user_save' and not body.get('user',{}).get('id')
        out=core.mutate(user,action,body)
        if new_user:
            with core.connect() as c: target=c.execute('SELECT id FROM users WHERE username=?',(body['user']['username'].strip().casefold(),)).fetchone()[0]
            out['activation_code']=self.auth.activation(target,user,'Creazione account');out['expires_days']=7
        return out,None,None

    def __call__(self,env,start_response):
        status=200; ctype=None; cookie=None
        try: data,ctype,cookie=self.route(env)
        except AuthError as ex: status=ex.status;data={'error':str(ex),'step_up':status==428}
        except core.AuthenticationError as ex: status=401;data={'error':str(ex)}
        except PermissionError as ex: status=403;data={'error':str(ex)}
        except sqlite3.IntegrityError: status=400;data={'error':'Nome utente, matricola o codice già utilizzato.'}
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,zipfile.BadZipFile) as ex:
            status=400;data={'error':str(ex) if isinstance(ex,ValueError) else 'Dati incompleti o non validi.'}
        except Exception:
            LOG.exception('Errore applicativo');status=500;data={'error':'Errore del servizio. Contatta l’amministratore.'}
        if isinstance(data,bytes): raw=data
        else: raw=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        extra=[]
        if status==200 and ctype=='video/mp4':
            extra.append(('Accept-Ranges','bytes'))
            requested=env.get('HTTP_RANGE','')
            if requested:
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                size=len(raw)
                if match and any(match.groups()):
                    first,last=match.groups()
                    start=int(first) if first else max(0,size-int(last))
                    end=min(size-1,int(last)) if first and last else size-1
                    if 0<=start<=end<size:
                        raw=raw[start:end+1];status=206;extra.append(('Content-Range',f'bytes {start}-{end}/{size}'))
                    else:status=416;raw=b'';extra.append(('Content-Range',f'bytes */{size}'))
        headers=[('Content-Type',ctype or 'application/json; charset=utf-8'),('Content-Length',str(len(raw))),
          ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
          ('X-Frame-Options','DENY'),('Permissions-Policy','camera=(), microphone=(), geolocation=()'),
          ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")]
        headers.extend(extra)
        if status==200 and env.get('PATH_INFO')=='/api/hr_document_view':
            headers=[h for h in headers if h[0]!='Content-Security-Policy']
            headers.extend([('Content-Disposition','inline'),('Content-Security-Policy',"sandbox; default-src 'none'; frame-ancestors 'none'; base-uri 'none'")])
        if self.secure: headers.append(('Strict-Transport-Security','max-age=31536000'))
        if cookie: headers.append(('Set-Cookie',self.cookie(cookie)))
        if ctype and ctype.startswith('text/csv'): headers.append(('Content-Disposition','attachment; filename=Presenze.csv'))
        if ctype == excel_exports.MIME: headers.append(('Content-Disposition','attachment; filename=Esportazione_Presenze.xlsx'))
        if ctype == 'application/vnd.sqlite3': headers.append(('Content-Disposition','attachment; filename=Backup_Presenze.sqlite3'))
        labels={206:'Partial Content',416:'Range Not Satisfiable',200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Content Too Large',415:'Unsupported Media Type',428:'Precondition Required',429:'Too Many Requests',500:'Internal Server Error'}
        start_response(str(status)+' '+labels.get(status,'Error'),headers);return [raw]


def main():
    p=argparse.ArgumentParser(description='Persone e Presenze Web 0.11')
    p.add_argument('--data-dir',type=Path,default=Path(os.environ.get('PRESENZE_DATA_DIR','data')))
    p.add_argument('--key-file',type=Path,default=Path(os.environ.get('PRESENZE_KEY_FILE','private/server.key')))
    p.add_argument('--origin',default=os.environ.get('PRESENZE_ORIGIN','https://presenze.example.it'))
    p.add_argument('--port',type=int,default=8080);p.add_argument('--dev-http',action='store_true')
    args=p.parse_args();application=WebApp(args.data_dir,args.key_file,args.origin,args.dev_http)
    def backups():
        while True:
            try:
                core.daily_backup()
            except Exception: LOG.exception('Backup giornaliero non riuscito')
            try: backup_policy.run(core)
            except Exception: LOG.exception('Copia NAS non riuscita')
            time.sleep(3600)
    threading.Thread(target=backups,daemon=True,name='Backup giornaliero').start()
    def scheduled_reminders():
        while True:
            try: reminders.run(core)
            except Exception: LOG.exception('Promemoria automatici non riusciti')
            time.sleep(300)
    threading.Thread(target=scheduled_reminders,daemon=True,name='Promemoria scadenze').start()
    print('Persone e Presenze Web 0.11 · '+application.origin,flush=True)
    serve(application,host='127.0.0.1',port=args.port,threads=8,max_request_body_size=MAX_BODY,
          trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-for','x-forwarded-proto'},clear_untrusted_proxy_headers=True)

if __name__=='__main__': main()
