#!/usr/bin/env python3
"""Italian synthetic voice and word-aligned captions; HTTPS proxy and CA preserved."""
from pathlib import Path
import asyncio,json,os,ssl,subprocess,math,wave,textwrap
ROOT=Path(__file__).resolve().parent
AUDIO=ROOT/'audio'; AUDIO.mkdir(exist_ok=True)
OUT=ROOT/'output';OUT.mkdir(exist_ok=True);NAME='Presentazione_NefroCenter_v0.11_qualita'
VOICE='it-IT-ElsaNeural'
SCENES=json.loads((ROOT/'scenes.json').read_text())
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(p)]))
def stamp(s):
 ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02}.{ms:03}'
async def speech():
 import edge_tts
 edge_tts.communicate._SSL_CTX=ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE'))
 for scene in SCENES:
  path=AUDIO/(scene['id']+'.mp3');cache=AUDIO/(scene['id']+'.json')
  if path.exists() and cache.exists() and json.loads(cache.read_text()).get('text')==scene['narration']:continue
  events=[]
  with path.open('wb') as f:
   async for e in edge_tts.Communicate(scene['narration'],VOICE,rate='-3%',boundary='WordBoundary',proxy=os.environ.get('HTTPS_PROXY'),connect_timeout=20,receive_timeout=45).stream():
    if e['type']=='audio':f.write(e['data'])
    elif e['type']=='WordBoundary':events.append({k:e[k] for k in ('offset','duration','text')})
  cache.write_text(json.dumps(dict(text=scene['narration'],voice=VOICE,events=events),ensure_ascii=False,indent=2))
  print('Speech ready',scene['id'],flush=True)
def main():
 asyncio.run(speech());elapsed=0;vtt=['WEBVTT',''];transcript=['NEFROCENTER — PRESENTAZIONE AGGIORNATA v0.11','Voce sintetica italiana: ElsaNeural. Dati esclusivamente fittizi.',''];timeline=[];clips=[]
 for scene in SCENES:
  ident=scene['id'];source=AUDIO/(ident+'.mp3');raw=float(probe(source)['format']['duration']);duration=max(scene['seconds'],math.ceil(raw+1.1));clip=AUDIO/(ident+'.wav')
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-af','afade=t=in:d=0.02,afade=t=out:st='+str(max(0,raw-.04))+':d=0.04','-ar','48000','-ac','1','-c:a','pcm_s16le',str(clip)],check=True)
  with wave.open(str(clip),'rb') as f:pcm=f.readframes(f.getnframes())
  pcm=bytes(round(.45*48000)*2)+pcm
  assert len(pcm)<=duration*48000*2
  with wave.open(str(clip),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(pcm+bytes(duration*48000*2-len(pcm)))
  events=json.loads((AUDIO/(ident+'.json')).read_text())['events'];groups=[];group=[]
  # WordBoundary text omits punctuation; retain the original editorial wording.
  words=scene['narration'].split()
  assert len(words)==len(events), 'Review word alignment before generating captions'
  for e,word in zip(events,words):
   e={**e,'text':word}
   if group and len(' '.join(x['text'] for x in group)+' '+word)>74:
    groups.append(group);group=[]
   group.append(e)
   length=len(' '.join(x['text'] for x in group))
   if word.endswith(('.',':',';','?')) or (word.endswith(',') and length>=36):
    groups.append(group);group=[]
  if group:groups.append(group)
  for group in groups:
   start=elapsed+.45+group[0]['offset']/1e7;end=elapsed+.45+(group[-1]['offset']+group[-1]['duration'])/1e7
   caption=' '.join(x['text'] for x in group);lines=textwrap.wrap(caption,width=42)
   assert len(lines)<=2
   vtt.extend([f'{stamp(start)} --> {stamp(end)}','\n'.join(lines),''])
  timeline.append({**scene,'start':elapsed,'end':elapsed+duration,'seconds':duration,'raw_audio_seconds':raw,'voice_start':elapsed+.45,'voice_end':elapsed+.45+raw})
  transcript.extend([f'{stamp(elapsed)[:8]} · {scene["chapter"]}',scene['narration'],'']);elapsed+=duration;clips.append(clip)
 concat=AUDIO/'concat.txt';concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in clips));full=AUDIO/'narration.wav'
 subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-af','loudnorm=I=-16:LRA=7:TP=-1.5','-ar','48000','-ac','1',str(full)],check=True)
 subprocess.run(['ffmpeg','-v','error','-y','-i',str(full),'-c:a','libmp3lame','-b:a','192k',str(OUT/(NAME+'_voce.mp3'))],check=True)
 (ROOT/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2));(OUT/(NAME+'.vtt')).write_text('\n'.join(vtt));(OUT/(NAME+'_con_audio.vtt')).write_text('\n'.join(vtt));(OUT/(NAME+'_trascrizione.txt')).write_text('\n'.join(transcript));(OUT/(NAME+'_con_audio_trascrizione.txt')).write_text('\n'.join(transcript));print('TIMELINE',elapsed,'seconds',flush=True)
if __name__=='__main__':main()
