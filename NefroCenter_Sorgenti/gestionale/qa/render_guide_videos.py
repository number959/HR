"""Full HD illustrated guides from the verified help catalog and real demo captures.

No simulated mouse actions: every image is explicitly a reference screenshot.
The still composition is authored at 1920×1080 from double-density browser
captures, with measured text boxes, short timed captions and 30 fps H.264.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
FPS = 30
RENDER_VERSION = 'full-hd-illustrated-2026-10-23'
INK = '#17344c'
NAVY = '#163a5b'
TEAL = '#197d80'
PALE = '#eef4f7'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def wrap(draw, text, face, width):
    """Wrap without discarding words; explicit paragraph breaks are preserved."""
    lines = []
    for paragraph in str(text).splitlines():
        line = ''
        for word in paragraph.split():
            test = (line + ' ' + word).strip()
            if draw.textlength(test, font=face) <= width:
                line = test
            else:
                if line:
                    lines.append(line)
                # An unusual long token (e.g. field name) still must not overflow.
                while draw.textlength(word, font=face) > width:
                    n = len(word)
                    while n > 1 and draw.textlength(word[:n]+'‑', font=face) > width:
                        n -= 1
                    lines.append(word[:n]+'‑'); word = word[n:]
                line = word
        lines.append(line)
    return lines or ['']


def text_box(draw, text, box, preferred=36, minimum=28, bold=False, fill=INK, leading=1.38):
    x, y, w, h = box
    for size in range(preferred, minimum-1, -1):
        face = font(size, bold)
        lines = wrap(draw, text, face, w)
        line_height = math.ceil(size*leading)
        if len(lines)*line_height <= h:
            for i, line in enumerate(lines):
                draw.text((x, y+i*line_height), line, font=face, fill=fill)
            return dict(font_size=size, lines=len(lines), height=len(lines)*line_height, box=box)
    raise ValueError('Text does not fit its authored box: '+str(text)[:140])


def stamp(seconds):
    ms = round(seconds*1000)
    return f'{ms//3600000:02}:{ms%3600000//60000:02}:{ms%60000//1000:02}.{ms%1000:03}'


def _metadata(screenshots):
    root = Path(screenshots) if screenshots else ROOT/'assets/guide_screens'
    paths = [root/'manifest.json', root.parent/'manifest.json']
    for path in paths:
        if path.is_file():
            return root, json.loads(path.read_text())
    return root, {'topics': {}}


def screenshot(topic, screenshots, detail=None):
    root, manifest = _metadata(screenshots)
    row = manifest.get('details' if detail else 'topics', {}).get(detail or topic['id'], {})
    path = Path(row.get('path', (detail or topic['id'])+'.webp'))
    if not path.is_absolute():
        path = root/path
    if not path.is_file():
        # Keep reconstruction portable when absolute original captures moved.
        path = next((root/((detail or topic['id'])+ext) for ext in ('.webp','.png')
                     if (root/((detail or topic['id'])+ext)).is_file()), path)
    if not path.is_file():
        raise ValueError('A real reference capture is required: '+topic['id'])
    image = Image.open(path).convert('RGB')
    focus = row.get('focus_pixels') or row.get('focus')
    if focus:
        scale = row.get('viewport', manifest.get('viewport', {})).get('deviceScaleFactor', 1) if focus.get('units') == 'css_pixels' else 1
        x, y, w, h = (round(float(focus[k])*scale) for k in ('x', 'y', 'width', 'height'))
        if w <= 0 or h <= 0:
            raise ValueError('Invalid capture focus: '+topic['id'])
        # Normal content captures began mid-heading in the original manifest.
        # Include the complete page heading, retaining the same lower boundary.
        if image.width == 3200 and image.height == 2000 and x == 430 and y == 310:
            y=220; h+=90
        image = image.crop((max(0,x), max(0,y), min(image.width,x+w), min(image.height,y+h)))
    return image, row.get('caption', topic['title']), path


def _chapters(topic):
    before = topic.get('before', [])
    intro = topic['goal']
    if before:
        intro += '\n\n' + str(before[0])
    result = [('Prima di iniziare', intro, 'INTRODUZIONE')]
    result += [(f'Passo {i} di {len(topic["steps"])}', text, f'PASSO {i:02}') for i,text in enumerate(topic['steps'], 1)]
    result.append(('Controlla il risultato', topic['result'], 'VERIFICA'))
    if topic.get('errors'):
        result.append(('Se qualcosa non funziona', topic['errors'][0], 'AIUTO'))
    return result


def render_frame(topic, heading, body, badge, index, count, source, output, detail=False):
    im = Image.new('RGB', SIZE, PALE); d = ImageDraw.Draw(im)
    # Large type and restrained contrast; no cropped titles or text below frame.
    d.rectangle((0,0,1920,142), fill=NAVY)
    d.text((56,25), 'NEFROCENTER  /  GUIDA OPERATIVA', font=font(23, True), fill='#a6ded7')
    d.text((1575,25), 'FULL HD  ·  30 FPS', font=font(22), fill='#c9dce7')
    title_stats = text_box(d,topic['title'],(56,67,1810,67),preferred=43,minimum=33,bold=True,fill='white',leading=1.1)
    # Instruction card: the full approved text is retained and measured.
    d.rounded_rectangle((48,172,626,960), radius=24, fill='white', outline='#d9e5eb', width=2)
    d.rounded_rectangle((78,204,264,250), radius=12, fill='#e2f3ef')
    d.text((95,214),badge,font=font(22,True),fill=TEAL)
    heading_stats = text_box(d,heading,(78,284,515,96),preferred=35,minimum=29,bold=True,leading=1.18)
    body_stats = text_box(d,body,(78,406,515,493),preferred=34,minimum=27,leading=1.38)
    # Reference screenshot: only the explicit capture focus is used. Always fit,
    # never arbitrary centre-crop to fill a video rectangle.
    d.rounded_rectangle((650,172,1872,960), radius=24, fill='white', outline='#d9e5eb', width=2)
    d.text((680,195),'SCHERMATA DI RIFERIMENTO',font=font(21,True),fill='#58758b')
    if detail and source.height > source.width*1.3:
        # A tall real dialog is shown in two contiguous columns with a small
        # overlap so no line is lost at the fold. This is a labelled reading
        # layout, not a simulation of two different application screens.
        midpoint=source.height//2
        d.text((680,242),'Parte superiore → parte inferiore',font=font(21),fill='#58758b')
        parts=[source.crop((0,0,source.width,midpoint+24)),source.crop((0,midpoint-24,source.width,source.height))]
        for n,part in enumerate(parts):
            shot=ImageOps.contain(part,(568,628),Image.Resampling.LANCZOS)
            im.paste(shot,(680+n*592+(568-shot.width)//2,282+(628-shot.height)//2))
    else:
        shot = ImageOps.contain(source, (1178, 682), Image.Resampling.LANCZOS)
        im.paste(shot,(672+(1178-shot.width)//2,242+(682-shot.height)//2))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((56,992,1864,1001),radius=4,fill='#d4e0e7')
    d.rounded_rectangle((56,992,56+round(1808*(index+1)/count),1001),radius=4,fill=TEAL)
    d.text((56,1021),'Videoguida illustrata senza audio · Dati dimostrativi · Metti in pausa per leggere',font=font(23),fill='#526c80')
    label=f'{index+1:02} / {count:02}'
    d.text((1864-d.textlength(label,font=font(23,True)),1021),label,font=font(23,True),fill=TEAL)
    im.save(output, optimize=False)
    return dict(title=title_stats, heading=heading_stats, body=body_stats)


def _caption_chunks(text):
    # Native captions contain at most two short lines. They supplement the
    # complete instruction card without covering half the screen.
    words = re.sub(r'\s+', ' ', text).strip().split()
    def lines(words):
        return textwrap.wrap(' '.join(words),width=44,break_long_words=False,break_on_hyphens=False)
    chunks, current = [], []
    for word in words:
        candidate = current+[word]
        if len(lines(candidate)) > 2 and current:
            chunks.append(current); current=[word]
        else:
            current=candidate
    if current:
        chunks.append(current)
    # Balance the final pair instead of flashing a one-word remainder.
    if len(chunks)>1 and len(' '.join(chunks[-1]))<35:
        pair=chunks[-2]+chunks[-1]; choices=[]
        for i in range(1,len(pair)):
            left,right=pair[:i],pair[i:]
            if len(lines(left))<=2 and len(lines(right))<=2:
                choices.append((abs(len(' '.join(left))-len(' '.join(right))),left,right))
        if choices:
            _,chunks[-2],chunks[-1]=min(choices,key=lambda value:value[0])
    return ['\n'.join(lines(chunk)) for chunk in chunks]


def _caption_timings(chunks, duration):
    weights=[max(1,len(c.replace('\n',' ').split())) for c in chunks]
    base=min(2.0,duration/len(chunks)); remaining=duration-base*len(chunks)
    return [base+remaining*weight/sum(weights) for weight in weights]


def refresh_captions(catalog, output_dir=None):
    """Improve accessibility text without re-encoding an unchanged video."""
    output_dir=Path(output_dir) if output_dir else ROOT/'assets/guides'
    for topic in catalog['topics']:
        elapsed=0;cue=0;vtt=['WEBVTT','']
        for heading,body,badge in _chapters(topic):
            duration=max(10,math.ceil(len(body.split())/2.4)+4)
            chunks=_caption_chunks(body);current=float(elapsed)
            for n,(chunk,length) in enumerate(zip(chunks,_caption_timings(chunks,duration))):
                end=elapsed+duration if n==len(chunks)-1 else current+length
                cue+=1;vtt += [str(cue),f'{stamp(current)} --> {stamp(end)}',chunk,''];current=end
            elapsed+=duration
        (output_dir/(topic['id']+'.vtt')).write_text('\n'.join(vtt))



def chapter_detail(topic_id, text):
    text=text.casefold()
    if topic_id=='copertura' and 'fabbisogni' in text:
        return 'copertura_fabbisogni'
    if topic_id in ('documenti','hrcentrale') and any(k in text for k in ('da correggere','verificato','nuova verifica')):
        return 'document_review'
    if topic_id=='approvazioni' and any(k in text for k in ('hr approva','hr centrale','approva e chiudi','restituisc')):
        return 'approval_actions'
    if topic_id=='comunicazioni' and 'anteprima' in text:
        return 'email_preview'
    if topic_id=='promemoria' and 'anteprima' in text:
        return 'promemoria_anteprima'
    if topic_id=='uscite' and any(k in text for k in ('attività','checklist','completa percorso')):
        return 'uscita_detail'
    if topic_id=='uscite' and any(k in text for k in ('dotazioni','restituzione','consegna')):
        return 'uscite_dotazioni'
    return None


def input_fingerprint(topic, screenshots):
    """Identify approved text and every source used by a resumable topic."""
    digest=hashlib.sha256()
    digest.update(RENDER_VERSION.encode())
    digest.update(json.dumps(topic,ensure_ascii=False,sort_keys=True).encode())
    details={None}
    for _,body,_ in _chapters(topic)[1:-2]:
        details.add(chapter_detail(topic['id'],body))
    for detail in sorted(details,key=lambda value:value or ''):
        capture,caption,path=screenshot(topic,screenshots,detail)
        digest.update(str((detail,capture.size,caption)).encode())
        _,manifest=_metadata(screenshots)
        row=manifest.get('details' if detail else 'topics',{}).get(detail or topic['id'],{})
        digest.update(json.dumps({k:v for k,v in row.items() if k!='path'},sort_keys=True).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()

def render_topic(topic, screenshots, frames, output_dir, encode=True):
    topic_dir=frames/topic['id'];topic_dir.mkdir(parents=True,exist_ok=True)
    source,caption,path=screenshot(topic,screenshots)
    chapters=_chapters(topic); concat=[]; elapsed=0; metadata=[]; text_stats=[]
    vtt=['WEBVTT','']; transcript=[topic['title'],'Videoguida illustrata Full HD, senza audio.','Le schermate sono riferimenti reali della demo con dati fittizi.', 'Profilo: '+topic['audience'],'']; cue=0
    for index,(heading,body,badge) in enumerate(chapters):
        # Pace follows the full card at ~140 wpm, plus time to inspect the image.
        duration=max(10, math.ceil(len(body.split())/2.4)+4)
        image_path=topic_dir/f'{index:02}.png'
        detail=chapter_detail(topic['id'],body) if 0<index<len(chapters)-2 else None
        shown=screenshot(topic,screenshots,detail)[0] if detail else source
        text_stats.append(render_frame(topic,heading,body,badge,index,len(chapters),shown,image_path,bool(detail)))
        concat.append((image_path,duration));metadata.append(dict(start=elapsed,title=heading))
        chunks=_caption_chunks(body); current=float(elapsed)
        for n,(chunk,length) in enumerate(zip(chunks,_caption_timings(chunks,duration))):
            end=elapsed+duration if n==len(chunks)-1 else current+length
            cue+=1;vtt += [str(cue),f'{stamp(current)} --> {stamp(end)}',chunk,''];current=end
        transcript += [f'[{stamp(elapsed)}] {heading}',body,''];elapsed+=duration
    output_dir.mkdir(parents=True,exist_ok=True)
    Image.open(concat[0][0]).save(output_dir/(topic['id']+'.jpg'),quality=92,subsampling=0,optimize=True)
    if encode:
        script=topic_dir/'frames.ffconcat'
        script.write_text('ffconcat version 1.0\n'+''.join(f"file '{p.as_posix()}'\nduration {duration}\n" for p,duration in concat)+f"file '{concat[-1][0].as_posix()}'\n")
        target=output_dir/(topic['id']+'.mp4');temp=output_dir/(topic['id']+'.tmp.mp4')
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(script),'-vf',f'fps={FPS},format=yuv420p','-c:v','libx264','-preset','veryfast','-tune','stillimage','-crf','20','-threads','2','-movflags','+faststart','-t',str(elapsed),str(temp)],check=True)
        temp.replace(target)
        (output_dir/(topic['id']+'.vtt')).write_text('\n'.join(vtt))
        (output_dir/(topic['id']+'.txt')).write_text('\n'.join(transcript))
    entry=dict(id=topic['id'],duration=elapsed,chapters=metadata,bytes=(output_dir/(topic['id']+'.mp4')).stat().st_size if encode else 0,kind='Videoguida illustrata Full HD senza audio',width=1920,height=1080,fps=FPS,quality='Full HD · 30 fps',poster='/assets/guides/'+topic['id']+'.jpg',source='Schermate reali della demo con dati fittizi',caption=caption)
    (topic_dir/'layout-check.json').write_text(json.dumps(dict(topic=topic['id'],source=str(path),cards=len(chapters),text=text_stats),ensure_ascii=False,indent=2)+'\n')
    if encode:
        (topic_dir/'render-complete.json').write_text(json.dumps(dict(fingerprint=input_fingerprint(topic,screenshots),entry=entry),ensure_ascii=False,indent=2)+'\n')
    return entry


def build_videos(catalog, screenshots=None, only_topics=None):
    """Drop-in replacement for qa.generate_guides.build_videos."""
    output=ROOT/'assets/guides'; frames=ROOT/'qa/guide_frames/quality';frames.mkdir(parents=True,exist_ok=True)
    previous=json.loads((output/'manifest.json').read_text()) if (output/'manifest.json').exists() else []
    entries={v['id']:v for v in previous}
    topics=[t for t in catalog['topics'] if not only_topics or t['id'] in only_topics]
    # Validate all source captures before changing any existing video.
    for t in topics:
        screenshot(t,screenshots)
    pending_topics=[]
    for t in topics:
        checkpoint=frames/t['id']/'render-complete.json'
        if checkpoint.is_file():
            saved=json.loads(checkpoint.read_text()); entry=saved['entry']; mp4=output/(t['id']+'.mp4')
            companions=all((output/(t['id']+ext)).is_file() for ext in ('.vtt','.txt','.jpg'))
            accepted=saved.get('equivalent_fingerprints',[saved['fingerprint']])
            if input_fingerprint(t,screenshots) in accepted and mp4.is_file() and mp4.stat().st_size==entry['bytes'] and companions:
                entries[t['id']]=entry
                print(t['id']+': verified completed render reused',flush=True)
                continue
        pending_topics.append(t)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(render_topic,t,screenshots,frames,output):t['id'] for t in pending_topics}
        for job in as_completed(pending):
            entry=job.result();entries[entry['id']]=entry
            print(f"{entry['id']}: {entry['duration']}s · 1920×1080/{FPS} fps · {entry['bytes']//1024} KiB",flush=True)
    manifest=[entries[t['id']] for t in catalog['topics'] if t['id'] in entries]
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'assets/help_videos.js').write_text('window.NefroHelpVideos = '+json.dumps(manifest,ensure_ascii=False)+';\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',type=Path,default=ROOT/'docs/help_catalog.json')
    p.add_argument('--screenshots',type=Path,default=ROOT/'assets/guide_screens')
    p.add_argument('--only-topic',action='append')
    p.add_argument('--sample',help='Render one topic as PNG cards only, no installed videos changed')
    a=p.parse_args();catalog=json.loads(a.catalog.read_text())
    if a.sample:
        t=next(t for t in catalog['topics'] if t['id']==a.sample)
        target=ROOT/'qa/guide_frames/quality-sample'
        result=render_topic(t,a.screenshots,target,target,encode=False)
        print(json.dumps(result,ensure_ascii=False))
    else:
        build_videos(catalog,a.screenshots,a.only_topic)
