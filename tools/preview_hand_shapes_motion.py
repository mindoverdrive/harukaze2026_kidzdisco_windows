"""30-second deterministic synthetic-input preview of the actual shape controller.

Uses existing PyAV/Pillow; does not open a camera, run inference or create a GUI.
Video timestamps are synthetic and are not a measurement of production FPS.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import av
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import display_utils
import hand_shapes_app as shapes
from hand_drawing_effects import FadingInk
from test_hand_shapes_app import hand, result, add_strokes

CONNECTIONS = ((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
               (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
               (13,17),(0,17),(17,18),(18,19),(19,20))


def observations(now):
    if now < 12:
        count = min(5, 1 + max(0, int((now-2)/2)))
        title = '1〜5本：形が変わる' if now >= 2 else '指の本数で、手を覆う形が変わる'
        specs = [(count,.30,.49,'Left',1.),(count,.70,.49,'Right',1.)]
    elif now < 17:
        count = (1,5,2,4,3)[int((now-12)/.55)%5]
        title = '急な切替：180ms安定してから、ぷるん'
        specs = [(count,.30,.49,'Left',1.),(6-count,.70,.49,'Right',1.)]
    else:
        title = '最大8手：交差・短い遮蔽・再出現'
        specs=[]
        for i in range(8):
            column, row = i%4, i//4
            x = .15+column*.233
            if 20 <= now < 24:
                x += (.233 if column%2==0 else -.233)*(.5-.5*math.cos((now-20)/4*math.tau))
            if 24 <= now < 24.4 and i in (1,6):
                continue
            count = 0 if now >= 26.4 else (i+int((now-17)/1.1))%5+1
            specs.append((count,x,.35+row*.34,'Left' if i%2 else 'Right',.48))
        if now >= 26.4:
            title='握る→手ごとに違う消え方（割り当てを維持）'
    samples=[hand(count,x=x,y=y,side=side,scale=size,angle=.09*math.sin(now*1.7+i))
             for i,(count,x,y,side,size) in enumerate(specs)]
    return samples,[s[3] for s in specs],title


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT.parent/'artifacts'/'hand-shapes-motion'/'hand_shapes_30s_synthetic.mp4')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    width,height,fps=1280,720,30
    layout=display_utils.get_uniform_layout(960,540,width,height)
    controller=shapes.ShapeInput(width,height,rng=random.Random(20261020))
    ink=FadingInk(width,height,0,3,max_segments=1920)
    font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',22)
    peaks={'hands':0,'morphs':0,'history':0}
    stills=[]
    samples_at={75,135,195,255,315,390,535,655,740,870,899}
    container=av.open(str(args.output),'w',options={'movflags':'+faststart'})
    stream=container.add_stream('libx264',rate=fps)
    stream.width,stream.height,stream.pix_fmt=width,height,'yuv420p'
    stream.options={'crf':'22','preset':'fast'}
    try:
        for index in range(30*fps):
            now=index/fps
            hands,sides,title=observations(now)
            stage=np.full((height,width,3),(39,33,28),np.uint8)
            for sample,side in zip(hands,sides):
                points=[tuple(map(round,display_utils.normalized_to_stage(p.x,p.y,layout))) for p in sample.landmark]
                for a,b in CONNECTIONS:
                    cv2.line(stage,points[a],points[b],(220,205,185),3,cv2.LINE_AA)
                for point in points:
                    cv2.circle(stage,point,4,(240,230,210),-1,cv2.LINE_AA)
            frame=controller.update(result(*hands,sides=sides),layout,now)
            add_strokes(ink,frame,now)
            image=shapes.render_frame(stage,ink,frame,layout,now)
            # Preview-only explanatory labels, outside reserved NEXT/BACK areas.
            pil=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
            draw=ImageDraw.Draw(pil)
            draw.rounded_rectangle((320,12,960,106),radius=12,fill=(16,22,31))
            draw.text((640,17),'合成入力 / SYNTHETIC INPUT',font=font,fill=(255,214,132),anchor='mt')
            draw.text((640,48),title,font=font,fill=(235,245,255),anchor='mt')
            draw.text((640,78),f'{now:04.1f}s  |  実カメラ・認識精度・実FPSの検証ではありません',font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',15),fill=(167,183,200),anchor='mt')
            image=cv2.cvtColor(np.asarray(pil),cv2.COLOR_RGB2BGR)
            peaks['hands']=max(peaks['hands'],len(frame.shapes))
            peaks['morphs']=max(peaks['morphs'],len(controller.morphs))
            peaks['history']=max(peaks['history'],len(ink.segments))
            if index in samples_at:
                path=args.output.parent/f'frame_{index:04d}.png'
                cv2.imwrite(str(path),image)
                stills.append((index,image.copy()))
            video=av.VideoFrame.from_ndarray(image,format='bgr24')
            video.pts=index
            for packet in stream.encode(video):
                container.mux(packet)
            if index%150==0:
                print(f'preview {index}/900',flush=True)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
        controller.close()
    sheet=Image.new('RGB',(1280,720),(16,22,31))
    for cell,(index,frame) in enumerate(stills[:9]):
        thumb=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).resize((426,240))
        sheet.paste(thumb,((cell%3)*426,(cell//3)*240))
    sheet.save(args.output.parent/'hand_shapes_contact_sheet.jpg',quality=92)
    decoded=0
    with av.open(str(args.output)) as verify:
        for frame in verify.decode(video=0):
            decoded+=1
    assert decoded==900,decoded
    evidence={'synthetic_input':True,'camera_opened':False,'inference_run':False,'gui_opened':False,
              'duration_seconds':30,'encoded_fps':fps,'frames_decoded':decoded,'size':[width,height],
              'peaks':peaks,'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}
    (args.output.parent/'preview-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':
    main()
