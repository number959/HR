from pathlib import Path
import json,re,subprocess,hashlib
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output';OUT.mkdir(exist_ok=True);NAME='Presentazione_NefroCenter_v0.11_qualita'
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-show_chapters','-of','json',str(p)]))
def sec(t):
 h,m,s=t.split(':');return int(h)*3600+int(m)*60+float(s)
meta=json.loads((OUT/(NAME+'_manifest.json')).read_text());result={'checks':[],'duration':meta['duration'],'chapters':len(meta['chapters'])}
for suffix,needs_audio in [('.mp4',False),('_con_audio.mp4',True)]:
 path=OUT/(NAME+suffix);info=probe(path);video=[s for s in info['streams'] if s['codec_type']=='video'];audio=[s for s in info['streams'] if s['codec_type']=='audio'];assert len(video)==1
 v=video[0];assert (v['width'],v['height'],v['avg_frame_rate'])==(1920,1080,'30/1');assert v['codec_name']=='h264';assert int(v['nb_frames'])==157*30
 assert len(audio)==int(needs_audio)
 if needs_audio:assert audio[0]['codec_name']=='aac' and audio[0]['sample_rate']=='48000' and audio[0]['tags']['language']=='ita'
 assert abs(float(info['format']['duration'])-157)<.1;assert len(info['chapters'])==11
 subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True)
 result['checks'].append({'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'frames':v['nb_frames'],'decode':'passed','audio':bool(audio)})
 (ROOT/(path.stem+'-ffprobe.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2))
last=0;captions=0
for block in (OUT/(NAME+'_con_audio.vtt')).read_text().split('\n\n'):
 if '-->' not in block:continue
 lines=block.splitlines();a,b=lines[0].split(' --> ');start,end=sec(a),sec(b);assert start>=last and start<end<=157;last=end;assert len(lines[1:])<=2 and max(map(len,lines[1:]))<=42;captions+=1
result['caption_cues']=captions;result['captions']='word aligned, original punctuation, at most two lines / 42 characters'
volume=subprocess.run(['ffmpeg','-hide_banner','-i',str(OUT/(NAME+'_con_audio.mp4')),'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
(ROOT/'loudness.log').write_text(volume.stderr);metrics=json.JSONDecoder().raw_decode(volume.stderr[volume.stderr.rfind('{'):])[0];assert -18<float(metrics['input_i'])<-14;assert float(metrics['input_tp'])<0
result['audio_loudness']=metrics;result['status']='passed';(ROOT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
