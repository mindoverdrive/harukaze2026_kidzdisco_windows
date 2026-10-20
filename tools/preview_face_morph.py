"""Synthetic five-person preview using the actual scene controller/renderer."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import math
from types import SimpleNamespace
import av
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import display_utils
from face_morph_field import FaceMorphField,face_from_landmarks,FORMS
from face_morph_app import draw_meshes


def main():
    out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
    width,height,fps,seconds=1280,720,24,30
    layout=display_utils.get_uniform_layout(width,height,width,height)
    model=FaceMorphField(seed=20261020)
    font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',23)
    banner=Image.new('RGB',(width,100),(12,20,33));pen=ImageDraw.Draw(banner)
    pen.text((30,10),'5人の顔メッシュ変身 / 合成入力・実カメラ検証ではない',font=font,fill=(235,242,255))
    pen.text((30,47),'安定して閉じる → 1回開くと別の形へ（完全無音）',font=font,fill=(168,211,232))
    banner_bgr=cv2.cvtColor(np.array(banner),cv2.COLOR_RGB2BGR)
    video=out/'face_mesh_five_synthetic_30s.mp4'
    container=av.open(str(video),'w',options={'movflags':'+faststart'})
    stream=container.add_stream('libx264',rate=fps)
    stream.width=width;stream.height=height;stream.pix_fmt='yuv420p'
    stream.options={'crf':'20','preset':'fast'}
    stills=[];peak_tracks=peak_reservations=0;last_shapes={};per_slot_changes={i:0 for i in range(5)}
    try:
        for frame in range(fps*seconds):
            now=frame/fps
            image=np.full((height,width,3),(33,23,16),dtype=np.uint8)
            observations=[]
            for i in range(5):
                x=.12+i*.19+.007*math.sin(now*.7+i)
                y=.52+.03*math.sin(now*.9+i)
                opening=1. if (now+i*.17)%1.55<.72 else 0.
                # Mock landmarks, not recorded faces or detector output.
                landmarks=[SimpleNamespace(x=x+.048*math.cos(j*math.tau/468),
                                           y=y+.125*math.sin(j*math.tau/468)) for j in range(468)]
                landmarks[1]=SimpleNamespace(x=x,y=y)
                landmarks[168]=SimpleNamespace(x=x,y=y-.015)
                landmarks[10]=SimpleNamespace(x=x,y=y-.125)
                landmarks[152]=SimpleNamespace(x=x,y=y+.125)
                gap=.25*(.02+opening*.13)
                landmarks[13]=SimpleNamespace(x=x,y=y+.035-gap/2)
                landmarks[14]=SimpleNamespace(x=x,y=y+.035+gap/2)
                observations.append(face_from_landmarks(landmarks,width,height))
                center=(round(x*width),round(y*height))
                cv2.ellipse(image,center,(60,90),0,0,360,(55,48,44),-1)
                cv2.ellipse(image,(center[0],center[1]+25),(16,3+round(opening*18)),0,0,360,(18,17,15),-1)
            model.step(list(reversed(observations)) if frame%2 else observations,now)
            draw_meshes(image,model,now,layout)
            for slot,t in model.tracks.items():
                if slot in last_shapes and last_shapes[slot]!=t.shape:per_slot_changes[slot]+=1
                last_shapes[slot]=t.shape
                px=round(t.face.x*width)
                cv2.putText(image,f'{slot+1}: {FORMS[t.shape]}',(px-75,560),cv2.FONT_HERSHEY_SIMPLEX,.5,(220,235,240),1,cv2.LINE_AA)
                cv2.putText(image,f'changes {t.changes}',(px-60,590),cv2.FONT_HERSHEY_SIMPLEX,.45,(170,195,210),1,cv2.LINE_AA)
            image[:100]=banner_bgr
            cv2.putText(image,f'SYNTHETIC INPUT / NO CAMERA VALIDATION    {now:04.1f}s    changes: {model.changes}',
                        (30,680),cv2.FONT_HERSHEY_SIMPLEX,.6,(210,220,235),1,cv2.LINE_AA)
            peak_tracks=max(peak_tracks,len(model.tracks));peak_reservations=max(peak_reservations,len(model.reserved()))
            if frame in (24,240,480,690):
                p=out/f'frame_{frame:03}.png';cv2.imwrite(str(p),image);stills.append(Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)))
            vf=av.VideoFrame.from_ndarray(image,format='bgr24');vf.pts=frame
            for packet in stream.encode(vf):container.mux(packet)
            if frame%240==0:print(frame,flush=True)
        for packet in stream.encode():container.mux(packet)
    finally:container.close();model.close()
    contact=Image.new('RGB',(1280,720))
    for i,still in enumerate(stills):contact.paste(still.resize((640,360)),((i%2)*640,(i//2)*360))
    contact.save(out/'contact.jpg')
    with av.open(str(video)) as reader:
        assert not reader.streams.audio
        frames=sum(1 for _ in reader.decode(video=0))
    evidence=dict(synthetic=True,real_camera_validated=False,frames=frames,seconds=seconds,
                  encoded_fps=fps,peak_tracks=peak_tracks,peak_reservations=peak_reservations,
                  per_slot_changes=per_slot_changes,vertices_per_face=193,triangles_per_face=336,audio_streams=0)
    (out/'preview-evidence.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':main()
