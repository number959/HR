"""Audit packaged tutorial media against the approved catalog (requires ffprobe)."""
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def seconds(value):
    h,m,s=value.split(':')
    return int(h)*3600+int(m)*60+float(s)


def validate():
    assets=ROOT/'assets/guides'
    catalog=json.loads((ROOT/'docs/help_catalog.json').read_text())
    manifest=json.loads((assets/'manifest.json').read_text())
    topics={t['id']:t for t in catalog['topics']}
    errors=[]

    def inspect(entry):
        key=entry['id'];path=assets/(key+'.mp4')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
        videos=[s for s in probe['streams'] if s['codec_type']=='video']
        audio=[s for s in probe['streams'] if s['codec_type']=='audio']
        duration=float(probe['format']['duration'])
        result=dict(id=key,width=videos[0]['width'],height=videos[0]['height'],fps=videos[0]['avg_frame_rate'],duration=duration,audio_streams=len(audio),bytes=path.stat().st_size)
        if (result['width'],result['height'],result['fps'])!=(1920,1080,'30/1') or audio or abs(duration-entry['duration'])>0.04 or entry['bytes']!=path.stat().st_size:
            errors.append('Video metadata: '+key)
        if Image.open(assets/(key+'.jpg')).size!=(1920,1080):
            errors.append('Poster dimensions: '+key)
        vtt=(assets/(key+'.vtt')).read_text()
        cues=re.findall(r'(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})\n([^\n]+(?:\n[^\n]+)?)',vtt)
        previous=0;max_line=0;min_cue=100;captions=[]
        for start,end,text in cues:
            a,b=seconds(start),seconds(end)
            max_line=max(max_line,max(map(len,text.splitlines())));min_cue=min(min_cue,b-a)
            if abs(a-previous)>0.002 or b-a<1.999 or len(text.splitlines())>2 or max(map(len,text.splitlines()))>44:
                errors.append('Caption layout/timing: '+key)
            previous=b;captions.append(text)
        if abs(previous-duration)>0.04:
            errors.append('Caption/video duration: '+key)
        topic=topics[key];transcript=(assets/(key+'.txt')).read_text()
        full_caption=' '.join(' '.join(captions).split())
        for text in topic['steps']+[topic['goal'],topic['result']]:
            if text not in transcript or ' '.join(text.split()) not in full_caption:
                errors.append('Missing approved instruction: '+key)
        starts=[c['start'] for c in entry['chapters']]
        if starts[0]!=0 or starts!=sorted(set(starts)) or starts[-1]>=duration:
            errors.append('Chapter timing: '+key)
        result.update(caption_cues=len(cues),max_caption_line=max_line,minimum_cue_duration=round(min_cue,3))
        layout=ROOT/'qa/guide_frames/quality'/key/'layout-check.json'
        if layout.exists():
            stats=json.loads(layout.read_text())
            result.update(instruction_font_min=min(s['body']['font_size'] for s in stats['text']),cards=stats['cards'])
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(inspect,manifest))
    portable=ROOT/'assets/guide_screens';sources=json.loads((portable/'manifest.json').read_text());source_count=0
    for kind in ('topics','details'):
        for key,row in sources[kind].items():
            path=Path(row['path']);image=portable/path
            if path.is_absolute() or not image.is_file():
                errors.append('Non-portable screenshot: '+key);continue
            if Image.open(image).size!=(row['width'],row['height']):
                errors.append('Screenshot dimensions: '+key)
            source_count+=1
    if set(topics)!={m['id'] for m in manifest} or len(manifest)!=34:
        errors.append('Catalog/manifest IDs')
    if source_count!=46:
        errors.append('Screenshot count')
    report=dict(status='PASS' if not errors else 'FAIL',errors=errors,video_count=len(manifest),cards=sum(r.get('cards',0) for r in results),total_duration=sum(r['duration'] for r in results),total_video_bytes=sum(r['bytes'] for r in results),portable_sources=source_count,minimum_instruction_font=min((r['instruction_font_min'] for r in results if 'instruction_font_min' in r),default=None),maximum_caption_line=max(r['max_caption_line'] for r in results),minimum_caption_cue=min(r['minimum_cue_duration'] for r in results),videos=results)
    (ROOT/'qa/guide_quality_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='videos'},indent=2))
    return not errors


if __name__=='__main__':
    raise SystemExit(0 if validate() else 1)
