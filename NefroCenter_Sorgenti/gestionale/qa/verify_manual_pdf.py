"""Verify generated PDFs with pypdf; no network calls."""
from pathlib import Path
import json, os
from pypdf import PdfReader
out=Path(os.environ.get('NEFRO_MANUAL_OUT','/workspace/consegna'))
work=Path(os.environ.get('NEFRO_MANUAL_WORK',str(Path(__file__).resolve().parent)))
report=[]
for name,expected in [('Guida_NefroCenter_v0.11_illustrata',42),('Presentazione_HR_NefroCenter_v0.11_illustrata',11)]:
    path=out/(name+'.pdf');r=PdfReader(path);texts=[p.extract_text() for p in r.pages]
    links=[]
    for p in r.pages:
        for ref in p.get('/Annots',[]):
            a=ref.get_object().get('/A',{})
            if a.get('/URI'):links.append(str(a['/URI']))
    assert len(r.pages)==expected,(name,len(r.pages),expected)
    assert min(len(t.strip()) for t in texts)>200,(name,'unexpected short page')
    assert not any('127.0.0.1' in u or 'localhost' in u for u in links),(name,'temporary URL')
    assert len(r.outline)>0,(name,'missing outline')
    assert r.trailer['/Root'].get('/MarkInfo',{}).get('/Marked'),(name,'missing tagged document structure')
    item={'file':path.name,'pages':len(r.pages),'bytes':path.stat().st_size,'minimum_page_characters':min(len(t.strip()) for t in texts),'outline_entries_top_level':len(r.outline),'link_annotations':len(links),'no_temporary_links':True,'tagged':True}
    report.append(item)
(work/'manual-pdf-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
