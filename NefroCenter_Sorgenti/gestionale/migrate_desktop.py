"""Import completed desktop backups into the web archive, without importing accounts."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
import core

def import_backup(source):
    source=Path(source).resolve()
    if not source.is_file() or source==core.DB.resolve():raise ValueError('Selezionare un backup distinto dall’archivio web.')
    checksum=hashlib.sha256(source.read_bytes()).hexdigest()
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);src.row_factory=sqlite3.Row
    try:
        if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or src.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Backup non integro.')
        if src.execute('PRAGMA user_version').fetchone()[0] not in (4,5):raise ValueError('Serve un backup della versione 0.4 o 0.5.')
        tables={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required={'centers','people','entries','patients','periods','hr_profiles','hr_settings','hr_documents','hr_history','audit','imports'}
        if not required<=tables:raise ValueError('Backup incompleto o non riconosciuto.')
        with core.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS web_imported_backups(hash TEXT PRIMARY KEY,filename TEXT,stamp TEXT,centers INTEGER)');c.commit()
            if c.execute('SELECT 1 FROM web_imported_backups WHERE hash=?',(checksum,)).fetchone():raise ValueError('Questo backup è già stato importato.')
        core._backup()
        with core.connect() as c:
            c.execute('BEGIN IMMEDIATE');center_map={};person_map={};counts={'centers':0,'people':0,'entries':0,'documents':0}
            for row in src.execute('SELECT * FROM centers'):
                config=core.validate_config(json.loads(row['config']));cid=core.uid();center_map[row['id']]=cid;code=row['code'];suffix=1
                while c.execute('SELECT 1 FROM centers WHERE code=?',(code,)).fetchone():suffix+=1;code=row['code'][:24]+'_'+str(suffix)
                c.execute('INSERT INTO centers VALUES(?,?,?,?,?,?)',(cid,row['name'],code,core.dump(config),row['version'],row['revision']));counts['centers']+=1
            for row in src.execute('SELECT * FROM people'):
                pid=core.uid();person_map[(row['cid'],row['id'])]=pid;obj=json.loads(row['data']);obj['id']=pid
                core.put(c,'people',center_map[row['cid']],obj);counts['people']+=1
            for row in src.execute('SELECT * FROM entries'):
                obj=json.loads(row['data']);obj['id']=core.uid();obj['person_id']=person_map[(row['cid'],obj['person_id'])]
                core.put(c,'entries',center_map[row['cid']],obj);counts['entries']+=1
            for row in src.execute('SELECT * FROM patients'):core.put(c,'patients',center_map[row['cid']],json.loads(row['data']))
            for row in src.execute('SELECT * FROM periods'):
                period=json.loads(row['data'])
                if 'agreements' in period:
                    period['agreements']={person_map[(row['cid'],pid)]:agreement for pid,agreement in period['agreements'].items()}
                core.put_period(c,center_map[row['cid']],row['month'],period)
            for row in src.execute('SELECT * FROM hr_settings'):c.execute('INSERT INTO hr_settings VALUES(?,?,?)',(center_map[row['cid']],row['version'],row['data']))
            for row in src.execute('SELECT * FROM hr_profiles'):c.execute('INSERT INTO hr_profiles VALUES(?,?,?,?)',(center_map[row['cid']],person_map[(row['cid'],row['pid'])],row['version'],row['data']))
            for row in src.execute('SELECT * FROM hr_documents'):
                if len(row['content'])>6*1024*1024 or hashlib.sha256(row['content']).hexdigest()!=row['sha256']:raise ValueError('Documento troppo grande o impronta non corrispondente.')
                c.execute('INSERT INTO hr_documents VALUES(?,?,?,?,?,?,?,?,?,?)',(core.uid(),center_map[row['cid']],person_map[(row['cid'],row['pid'])],row['name'],row['category'],row['expiry'],row['uploaded_at'],row['uploaded_by'],row['sha256'],row['content']));counts['documents']+=1
            for row in src.execute('SELECT * FROM hr_history'):c.execute('INSERT INTO hr_history VALUES(?,?,?,?,?,?)',(center_map[row['cid']],person_map[(row['cid'],row['pid'])],row['version'],row['stamp'],row['actor'],row['data']))
            for row in src.execute('SELECT * FROM audit'):
                if row['cid'] in center_map:c.execute('INSERT INTO audit(cid,stamp,username,action,before_data,after_data) VALUES(?,?,?,?,?,?)',(center_map[row['cid']],row['stamp'],row['username'],'Storico sede · '+row['action'],row['before_data'],row['after_data']))
            for row in src.execute('SELECT * FROM imports'):
                if row['cid'] in center_map:c.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?)',(row['hash'],center_map[row['cid']],row['month']))
            if checksum!=hashlib.sha256(source.read_bytes()).hexdigest():raise ValueError('Il backup sorgente è cambiato durante l’importazione.')
            c.execute('INSERT INTO web_imported_backups VALUES(?,?,?,?)',(checksum,source.name,core.now(),counts['centers']))
            core.audit(c,{'username':'console'},'Importazione backup sedi','',after={'filename':source.name,'sha256':checksum,**counts});c.commit()
        return counts
    finally:src.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('backup',type=Path);p.add_argument('--data-dir',required=True,type=Path);a=p.parse_args()
    core.DB=a.data_dir.resolve()/'presenze.sqlite3'
    if not core.DB.is_file():raise SystemExit('Prima inizializzare l’archivio web con manage.py init.')
    core.init_db()
    print(json.dumps(import_backup(a.backup),ensure_ascii=False,indent=2))
