#!/usr/bin/env python3
"""Render a polished 1080p30 feature presentation from real synthetic-data screenshots.

The title stays still while a wide readable UI panel pans gently. Modal close-ups
use their own layout. Rendered screenshots are copied so later QA cannot alter the
film. No new UI/data is fabricated. Requires Python/Pillow, FFmpeg and ffprobe.
"""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import json,subprocess,shutil,hashlib,math,argparse
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output';OUT.mkdir(exist_ok=True);SRC=ROOT/'source';RENDER=ROOT/'render'
NAME='Presentazione_NefroCenter_v0.11_qualita';SIZE=(1920,1080);FPS=30
NAVY='#102E50';MUTED='#AFC8DC';TEAL='#66DACB';WHITE='#F7FAFD'
FONT=Path('/usr/share/fonts/truetype/liberation')
SCENES=json.loads((ROOT/'timeline.json').read_text())
SHOTS=SRC
MODALS={'documenti':('document_review',(0,445,1120,1260),['Apri il documento','Registra esito e nota','Ritrova ogni passaggio']),
 'comunicazioni':('email_preview',(0,100,1309,1350),['Scegli modello e lista','Controlla l’anteprima','Conferma i destinatari']),
 'uscite':('uscita_detail',(0,510,1120,1480),['Assegna le attività','Registra le restituzioni','Completa le verifiche'])}
MAPPING={'intro':'roleswelcome','dashboard':'dashboard','presenze':'presenze','fascicolo':'fascicolo','documenti':'document_review','approvazioni':'approvazioni_in_attesa','copertura':'copertura','comunicazioni':'email_preview','paghe':'paghe','uscite':'uscita_detail','guide':'guida'}
def run(args):subprocess.run(args,check=True)
def font(n,bold=False):return ImageFont.truetype(str(FONT/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),n)
def text(draw,xy,value,size,color=WHITE,bold=False,maxwidth=None):
 face=font(size,bold)
 while maxwidth and draw.textlength(value,font=face)>maxwidth:face=font(face.size-1,bold)
 draw.text(xy,value,font=face,fill=color)
 return face.size

def logo(canvas):
 mark=Image.open(SRC/'nefrocenter.png').convert('RGBA');mark.thumbnail((244,64),Image.Resampling.LANCZOS)
 d=ImageDraw.Draw(canvas);d.rounded_rectangle((1552,28,1840,99),radius=12,fill='white');canvas.paste(mark,(1574,37),mark)

def base(scene,index):
 im=Image.new('RGB',SIZE,NAVY);d=ImageDraw.Draw(im)
 for y in range(1080):
  t=y/1080;d.line((0,y,1920,y),fill=(16+round(4*t),46+round(6*t),80+round(8*t)))
 d.ellipse((1420,-660,2340,260),outline='#204362',width=2);d.ellipse((1540,-540,2220,140),outline='#234762',width=2)
 text(d,(80,48),f'{index+1:02} / {len(SCENES):02}    {scene["chapter"].upper()}',21,TEAL,True,maxwidth=1390)
 text(d,(80,108),scene['title'],57,WHITE,True,maxwidth=1760)
 text(d,(80,181),scene['line'],29,MUTED,maxwidth=1760)
 logo(im)
 # One short footer indicates provenance, while the progress rail indicates chapter.
 text(d,(80,996),'NEFROCENTER · PERSONE E PRESENZE',18,MUTED,True)
 text(d,(1275,996),'SCHERMATE DIMOSTRATIVE · DATI FITTIZI',17,MUTED,True)
 gap=8;width=(1760-gap*(len(SCENES)-1))/len(SCENES)
 for n in range(len(SCENES)):
  left=round(80+n*(width+gap));d.rounded_rectangle((left,1047,round(left+width),1053),radius=3,fill=TEAL if n<=index else '#355572')
 return im

def shadow(im,box):
 layer=Image.new('RGBA',SIZE);d=ImageDraw.Draw(layer);x,y,w,h=box;d.rounded_rectangle((x-4,y+8,x+w+4,y+h+18),radius=17,fill=(0,0,0,80));layer=layer.filter(ImageFilter.GaussianBlur(15));im.paste(layer,(0,0),layer);ImageDraw.Draw(im).rounded_rectangle((x-2,y-2,x+w+2,y+h+2),radius=6,fill='#D5E3EE')

def prepare(scene,index):
 ident=scene['id'];background=base(scene,index);d=ImageDraw.Draw(background);shot=Image.open(SRC/(MAPPING[ident]+'.png')).convert('RGB')
 if ident in MODALS:
  name,crop,steps=MODALS[ident];shot=shot.crop(crop);box=(766,251,1074,704)
  text(d,(80,292),'UN PERCORSO TRACCIATO',22,TEAL,True)
  for n,label in enumerate(steps):
   y=365+n*135;d.ellipse((80,y,128,y+48),fill='#254F70');text(d,(96,y+9),str(n+1),27,TEAL,True);text(d,(151,y+10),label,31,WHITE,True,maxwidth=540)
  note={'documenti':'La decisione resta nello storico.','comunicazioni':'Nella demo: nessun invio reale.','uscite':'Ogni restituzione viene registrata.'}[ident]
  text(d,(80,866),note,26,MUTED,maxwidth=630)
 else:
  box=(80,251,1760,704)
  if ident=='intro':
   # A clean brand card; real welcome screen remains prominent below it.
   shot=shot.crop((200,220,3000,1780))
  elif ident=='dashboard':shot=shot.crop((466,430,3140,1960))
  elif ident=='presenze':shot=shot.crop((466,450,3140,1950))
  elif ident=='fascicolo':shot=shot.crop((466,400,3140,1960))
  elif ident=='approvazioni':shot=shot.crop((466,800,3140,1940))
  elif ident=='copertura':shot=shot.crop((466,980,3140,1980))
  elif ident=='paghe':shot=shot.crop((466,900,3140,1980))
  elif ident=='guide':shot=shot.crop((466,430,3140,1950))
 shadow(background,box)
 x,y,w,h=box
 # Scale the source to the output width. Never stretch aspect ratio. If the
 # frame is taller, keep all content and center it on a white matte.
 sw,sh=shot.size;scale=w/sw;newh=round(sh*scale)
 shot=shot.resize((w,newh),Image.Resampling.LANCZOS)
 if newh<h:
  padded=Image.new('RGB',(w,h),'white');padded.paste(shot,(0,(h-newh)//2));shot=padded
 shot.save(RENDER/(ident+'-shot.png'));background.save(RENDER/(ident+'-base.png'))
 return box,shot.height

def encode(scene,index,force=False):
 ident=scene['id'];path=RENDER/(ident+'.mp4');box,sourceh=prepare(scene,index);x,y,w,h=box;duration=scene['seconds'];pan=max(0,min(sourceh-h,330))
 signature=hashlib.sha256((ROOT/'build_video.py').read_bytes()+json.dumps(scene,sort_keys=True).encode()+(SRC/(MAPPING[ident]+'.png')).read_bytes()).hexdigest();sigfile=RENDER/(ident+'.sha256')
 if not force and path.exists() and sigfile.exists() and sigfile.read_text()==signature:return path
 # Smoothstep pan starts/ends at rest, with exact 30 fps timing. Overlay keeps
 # the typography still and avoids zooming the title into a soft image.
 progress=f'min(1,max(0,(t-1)/{max(1,duration-2)}))';smooth=f'({progress})*({progress})*(3-2*({progress}))'
 filt=f"[1:v]crop={w}:{h}:0:'{pan}*{smooth}',setsar=1[shot];[0:v][shot]overlay={x}:{y}:shortest=1,fade=t=in:st=0:d=0.35:color=0x102E50,fade=t=out:st={duration-.35}:d=0.35:color=0x102E50,format=yuv420p[v]"
 run(['ffmpeg','-v','error','-y','-loop','1','-framerate',str(FPS),'-i',str(RENDER/(ident+'-base.png')),'-loop','1','-framerate',str(FPS),'-i',str(RENDER/(ident+'-shot.png')),'-filter_complex_threads','2','-filter_complex',filt,'-map','[v]','-t',str(duration),'-r',str(FPS),'-c:v','libx264','-preset','fast','-crf','18','-threads','2','-profile:v','high','-level:v','4.2','-pix_fmt','yuv420p','-movflags','+faststart',str(path)])
 sigfile.write_text(signature);print('Rendered',ident,duration,'seconds',flush=True);return path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');parser.add_argument('--only');args=parser.parse_args();SRC.mkdir(exist_ok=True);RENDER.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
 for name in set(MAPPING.values()):
  assert (SRC/(name+'.png')).exists(), 'Missing screenshot: '+name
 clips=[]
 for i,scene in enumerate(SCENES):
  if args.only and args.only!=scene['id']:continue
  clips.append(encode(scene,i,args.force))
 if args.only:return
 concat=RENDER/'video-concat.txt';concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in clips));silent=OUT/(NAME+'.mp4');audio=OUT/(NAME+'_con_audio.mp4')
 metadata=ROOT/'chapters.ffmeta';lines=[';FFMETADATA1','title=NefroCenter — Persone e Presenze v0.11','comment=Schermate reali del software con dati fittizi. Presentazione aggiornata.']
 for s in SCENES:lines += ['[CHAPTER]','TIMEBASE=1/1000',f'START={round(s["start"]*1000)}',f'END={round(s["end"]*1000)}','title='+s['chapter']]
 metadata.write_text('\n'.join(lines)+'\n')
 run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-i',str(metadata),'-map','0:v:0','-map_metadata','1','-map_chapters','1','-c','copy','-movflags','+faststart',str(silent)])
 run(['ffmpeg','-v','error','-y','-i',str(silent),'-i',str(ROOT/'audio/narration.wav'),'-map','0:v:0','-map','1:a:0','-map_metadata','0','-map_chapters','0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-metadata:s:a:0','language=ita','-metadata','comment=Voce sintetica italiana ElsaNeural; schermate del software con soli dati fittizi.','-t',str(SCENES[-1]['end']),'-movflags','+faststart',str(audio)])
 run(['ffmpeg','-v','error','-y','-ss','19','-i',str(audio),'-frames:v','1','-q:v','2',str(OUT/(NAME+'_poster.jpg'))])
 chapters=[dict(id=s['id'],title=s['chapter'],start=s['start'],end=s['end']) for s in SCENES]
 meta=dict(version='0.11',quality_revision='2026-10-23',duration=SCENES[-1]['end'],width=1920,height=1080,fps=30,voice='Italian synthetic ElsaNeural',audio_codec='AAC',audio_bitrate=192000,chapters=chapters,video=audio.name,silent_video=silent.name,subtitles=NAME+'_con_audio.vtt',transcript=NAME+'_con_audio_trascrizione.txt',poster=NAME+'_poster.jpg')
 (OUT/(NAME+'_manifest.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n');print(json.dumps(meta,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
