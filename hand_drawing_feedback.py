"""Per-hand detected fingers; stabilized color/shape choices remain unchanged."""
import math
import cv2
import numpy as np
from hand_drawing_gestures import FINGER_COLORS_BGR
from transition_overlay import navigation_regions

DARK=(30,23,18)
WHITE=(239,244,248)
MUTED=(116,112,107)
FONT=cv2.FONT_HERSHEY_SIMPLEX

def _scale(size):
    return max(.5,min(1.5,size[0]/1280,size[1]/720))

def _overlap(a,b):
    return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]

def layout_badges(size,inputs,active_points=()):
    """Stable ownership and collision avoidance, including eight-hand layouts."""
    width,height=size
    scale=_scale(size)
    margin,gap=max(4,round(10*scale)),max(3,round(6*scale))
    bw,bh=round(100*scale),round(44*scale)
    top,bottom=round(height*.20)+margin,height-margin
    forbidden=[*navigation_regions(width,height).values()]
    radius=round(20*scale)
    markers=[(x-radius,y-radius,radius*2,radius*2) for x,y in active_points]
    used,placed=[],[]
    grid=[(x,y) for y in range(top,bottom-bh+1,bh+gap)
          for x in range(margin,width-margin-bw+1,bw+gap)]
    for hand in sorted(inputs,key=lambda item:item.track_id):
        x,y=hand.anchor
        preferred=[(x+round(22*scale),y+round(8*scale)),
                   (x-bw-round(22*scale),y+round(8*scale)),
                   (x-bw//2,y+round(25*scale)),(x-bw//2,y-bh-round(24*scale))]
        candidates=[(max(margin,min(width-margin-bw,int(cx))),
                     max(top,min(bottom-bh,int(cy))),bw,bh) for cx,cy in preferred+grid]
        available=[rect for rect in candidates
                   if not any(_overlap(rect,other) for other in forbidden+markers+used)]
        if not available:continue
        rect=min(available,key=lambda r:math.hypot(r[0]+r[2]/2-x,r[1]+r[3]/2-y))
        used.append(rect);placed.append((hand,rect))
    return tuple(placed)

def _round_rect(image,rect,color,radius):
    x,y,w,h=map(int,rect)
    r=max(1,min(int(radius),w//2,h//2))
    cv2.rectangle(image,(x+r,y),(x+w-r-1,y+h-1),color,-1)
    cv2.rectangle(image,(x,y+r),(x+w-1,y+h-r-1),color,-1)
    for cx,cy in ((x+r,y+r),(x+w-r-1,y+r),(x+r,y+h-r-1),(x+w-r-1,y+h-r-1)):
        cv2.circle(image,(cx,cy),r,color,-1,cv2.LINE_AA)

def _panel(image,rect,border):
    x,y,w,h=rect
    _round_rect(image,rect,border,max(3,h//5))
    _round_rect(image,(x+1,y+1,w-2,h-2),DARK,max(2,h//5-1))

def _hand_icon(image,origin,finger_mask,scale,color=WHITE,handedness=None):
    """Show detected thumb/index/middle/ring/pinky, mirrored like the camera."""
    if len(finger_mask) != 5:
        return
    x,y=origin
    pt=lambda a,b:(round(x+(40-a if handedness=='Left' else a)*scale),round(y+b*scale))
    thickness=max(2,round(4*scale))
    for i,(base,px,tip) in enumerate(((10,6,7),(18,16,1),(26,26,4),(34,36,11)),1):
        if finger_mask[i]:
            cv2.line(image,pt(base,24),pt(px,tip),color,thickness,cv2.LINE_AA)
            cv2.circle(image,pt(px,tip),max(1,thickness//2),color,-1,cv2.LINE_AA)
    palm_width=max(6,round(31*scale))
    left=pt(7,20)[0]-(palm_width-1 if handedness=='Left' else 0)
    _round_rect(image,(left,round(y+20*scale),palm_width,max(4,round(14*scale))),WHITE,max(2,round(5*scale)))
    for i,px in enumerate((10,18,26,34),1):
        if not finger_mask[i]:cv2.line(image,pt(px,22),pt(px,26),MUTED,max(1,round(scale)),cv2.LINE_AA)
    if finger_mask[0]:
        cv2.line(image,pt(10,29),pt(1,18),color,thickness,cv2.LINE_AA)
        cv2.circle(image,pt(1,18),max(1,thickness//2),color,-1,cv2.LINE_AA)
    else:
        cv2.line(image,pt(8,30),pt(5,26),WHITE,max(2,round(4*scale)),cv2.LINE_AA)

def _equation(image,origin,count,scale,outline=None,*,finger_mask=(),handedness=None):
    x,y=origin
    color=FINGER_COLORS_BGR[count]
    _hand_icon(image,(x+4*scale,y+3*scale),finger_mask,.95*scale,color,handedness)
    cv2.putText(image,str(count),(round(x+46*scale),round(y+27*scale)),FONT,.58*scale,WHITE,max(1,round(2*scale)),cv2.LINE_AA)
    center=(round(x+82*scale),round(y+21*scale))
    if outline is None:
        cv2.circle(image,center,max(3,round(14*scale)),color,-1,cv2.LINE_AA)
    else:
        points=np.rint([(center[0]+px*14*scale,center[1]-py*14*scale) for px,py in outline]).astype(np.int32)
        cv2.fillPoly(image,[points],tuple(round(d*.6+c*.4) for d,c in zip(DARK,color)),cv2.LINE_AA)
        cv2.polylines(image,[points],True,color,max(1,round(2.4*scale)),cv2.LINE_AA)
def _leader(image,anchor,rect,color,blocked,active_points,radius,scale):
    x,y,bw,bh=rect
    target=(max(x,min(x+bw-1,anchor[0])),max(y,min(y+bh-1,anchor[1])))
    dx,dy=target[0]-anchor[0],target[1]-anchor[1]
    length=math.hypot(dx,dy)
    if length<1:return
    # Start outside the protected palm square in the shape scene.
    inset=0.
    for px,py in active_points:
        if abs(anchor[0]-px)<=radius and abs(anchor[1]-py)<=radius:
            inset=max(inset,(radius+2)/max(abs(dx/length),abs(dy/length)))
    if inset>=length:return
    start=(round(anchor[0]+dx/length*inset),round(anchor[1]+dy/length*inset))
    if any(cv2.clipLine(tuple(map(int,area)),start,target)[0] for area in blocked):return
    cv2.line(image,start,target,DARK,max(3,round(4*scale)),cv2.LINE_AA)
    cv2.line(image,start,target,color,max(1,round(1.5*scale)),cv2.LINE_AA)
    cv2.circle(image,start,max(2,round(2.5*scale)),color,-1,cv2.LINE_AA)

def draw_color_guidance(image,inputs,active_points=(),*,shape_outlines=None):
    """Live fingers and chosen count/color come from the same tracked hand."""
    height,width=image.shape[:2]
    size,scale=(width,height),_scale((width,height))
    radius=round(20*scale)
    protected=[*navigation_regions(width,height).values()]
    protected.extend((x-radius,y-radius,2*radius,2*radius) for x,y in active_points)
    preserved=[]
    for x,y,w,h in protected:
        x0,y0=max(0,round(x)),max(0,round(y))
        x1,y1=min(width,round(x+w)),min(height,round(y+h))
        if x1>x0 and y1>y0:preserved.append((x0,y0,image[y0:y1,x0:x1].copy()))
    blocked=protected
    placed=layout_badges(size,inputs,active_points)
    # Leaders are behind every badge, so later hands never scribble across a label.
    for hand,rect in placed:
        color=FINGER_COLORS_BGR[hand.selected_count]
        anchor=(max(0,min(width-1,round(hand.anchor[0]))),max(0,min(height-1,round(hand.anchor[1]))))
        _leader(image,anchor,rect,color,blocked,active_points,radius,scale)
    for hand,rect in placed:
        color=FINGER_COLORS_BGR[hand.selected_count]
        _panel(image,rect,tuple(round(c*.55) for c in color))
        _equation(image,rect[:2],hand.selected_count,scale,
                  shape_outlines[hand.selected_count] if shape_outlines else None,
                  finger_mask=hand.finger_mask,handedness=hand.handedness)
    # Restore all active input/navigation pixels.
    for x,y,pixels in preserved:
        image[y:y+pixels.shape[0],x:x+pixels.shape[1]]=pixels
