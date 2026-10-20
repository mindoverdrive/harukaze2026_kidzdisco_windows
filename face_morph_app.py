"""Standalone review candidate. Not registered in rotation or staff UI."""
from contextlib import ExitStack
import colorsys
import math
import os
import time
import numpy as np
from face_morph_field import FaceMorphField, face_from_landmarks, stage_mesh, FORMS


def draw_meshes(image, field, now, layout):
    """Shared CPU renderer used by the live adapter and synthetic preview."""
    import cv2
    h,w=image.shape[:2]
    nav_h,nav_w=min(130,int(h*.2)),min(230,int(w*.24))
    left,right=image[:nav_h,:nav_w].copy(),image[:nav_h,w-nav_w:].copy()
    fill=image.copy()
    meshes=[]
    for key,t in field.tracks.items():
        if not t.visible:continue
        points,indices=stage_mesh(t,now,layout,field.settings.morph_seconds)
        # Give nearby faces disjoint envelopes without enlarging a mesh.
        center=np.array([layout['offset_x']+t.face.x*(layout['scaled_width']-1),
                         layout['offset_y']+t.face.y*(layout['scaled_height']-1)])
        distances=[math.hypot((t.face.x-other.face.x)*layout['scaled_width'],
                              (t.face.y-other.face.y)*layout['scaled_height'])
                   for other in field.tracks.values() if other is not t and other.visible]
        if distances:
            delta=points-center;length=np.linalg.norm(delta,axis=1)
            points=(center+delta*np.minimum(1.,min(distances)*.46/np.maximum(length,1.))[:,None]).astype(np.int32)
        # Crop, rather than stretch, triangles near NEXT/BACK corner regions.
        w,h=layout['stage_width'],layout['stage_height']
        protected=(points[:,1]<min(130,h*.2)) & ((points[:,0]<min(230,w*.24)) | (points[:,0]>w-min(230,w*.24)))
        indices=indices[~protected[indices].any(axis=1)]
        rgb=colorsys.hsv_to_rgb((key*.19+.04)%1,.48,.95)
        color=tuple(round(c*255) for c in rgb[::-1])
        for index,triangle in enumerate(indices):
            shade=.40+.23*(index%4)/3
            cv2.fillConvexPoly(fill,points[triangle],tuple(int(c*shade) for c in color))
        meshes.append((points,indices,color))
    cv2.addWeighted(fill,.48,image,.52,0,dst=image)
    for points,indices,color in meshes:
        cv2.polylines(image,[points[triangle] for triangle in indices],True,color,1,cv2.LINE_AA)
    image[:nav_h,:nav_w]=left
    image[:nav_h,w-nav_w:]=right
    return image


def main():
    import cv2
    import pygame
    import display_utils
    from shared_camera import ENV_REQUIRED
    from scene_control import notify_first_frame
    if os.environ.get(ENV_REQUIRED,'').lower() not in {'1','true','yes','on'}:
        raise RuntimeError('Face morph requires Manager shared camera; physical fallback prohibited')
    if os.environ.get('MATAHARI_FACE_CHECK') == '1' and os.environ.get('MATAHARI_FACE_CHECK_WINDOWED') == '1':
        from stage_display import configure_audience_dpi
        configure_audience_dpi()
    with ExitStack() as resources:
        pygame.init();resources.callback(pygame.quit)
        if os.environ.get('MATAHARI_FACE_CHECK') == '1' and os.environ.get('MATAHARI_FACE_CHECK_WINDOWED') == '1':
            os.environ['SDL_VIDEO_WINDOW_POS']=','.join(os.environ.get('KIDZDISCO_DISPLAY_'+key,'40') for key in ('X','Y'))
            size=tuple(int(os.environ.get('KIDZDISCO_DISPLAY_'+key,default)) for key,default in (('WIDTH','960'),('HEIGHT','640')))
            screen=pygame.display.set_mode(size,pygame.RESIZABLE)
            pygame.display.set_caption('MATAHARI 口mesh確認 — ESCで終了')
        else:
            screen,_=display_utils.setup_pygame_fullscreen()
        cap=display_utils.open_camera()
        if cap is None:raise RuntimeError('Face morph: shared camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():raise RuntimeError('Face morph: shared camera closed')
        if os.environ.get('MATAHARI_FACE_INPUT') == 'synthetic_landmarks':
            if os.environ.get('MATAHARI_FACE_CHECK') != '1':
                raise RuntimeError('Synthetic landmarks require isolated verification mode')
            from face_morph_test_input import SyntheticLandmarkDetector
            detector_factory=SyntheticLandmarkDetector
        else:
            import mediapipe as mp
            detector_factory=mp.solutions.face_mesh.FaceMesh
        detector=resources.enter_context(detector_factory(
            max_num_faces=5,refine_landmarks=False,
            min_detection_confidence=.5,min_tracking_confidence=.5))
        field=FaceMorphField();resources.callback(field.close)
        diagnostics=None
        if os.environ.get('MATAHARI_FACE_CHECK') == '1':
            from face_morph_diagnostics import FaceCheckDiagnostics
            diagnostics=FaceCheckDiagnostics(pygame)
        clock=pygame.time.Clock()
        previous_id=0;fresh=time.monotonic()
        while True:
            if any(e.type==pygame.QUIT or (e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE)
                   for e in pygame.event.get()):return
            now=time.monotonic();ok,frame=cap.read()
            frame_id=getattr(cap,'last_read_frame_id',0)
            if not ok or frame is None or frame_id<=previous_id:
                if now-fresh>3.:raise RuntimeError('Face morph: shared input stalled')
                clock.tick(30);continue
            fresh=now;previous_id=frame_id
            width,height=screen.get_size()
            camera,stage,layout=display_utils.prepare_camera_frame(frame,width,height)
            detection_start=time.perf_counter() if diagnostics else 0.
            result=detector.process(cv2.cvtColor(camera,cv2.COLOR_BGR2RGB))
            if diagnostics:
                detection_end=time.monotonic()
                diagnostics.detected(detection_end,time.perf_counter()-detection_start,getattr(detector,'phase','実検出器'))
            observations=[face_from_landmarks(f.landmark,camera.shape[1],camera.shape[0])
                          for f in (result.multi_face_landmarks or ())[:5]]
            field.step(observations,now)
            draw_start=time.perf_counter() if diagnostics else 0.
            draw_meshes(stage,field,now,layout)
            if diagnostics:diagnostics.draw_ms=(time.perf_counter()-draw_start)*1000
            rgb=cv2.cvtColor(stage,cv2.COLOR_BGR2RGB)
            screen.blit(pygame.image.frombuffer(rgb.tobytes(),(width,height),'RGB'),(0,0))
            if diagnostics:diagnostics.draw(screen,field,time.monotonic())
            pygame.display.flip()
            if diagnostics:diagnostics.presented(field)
            notify_first_frame(cap,frame_processed=True)
            clock.tick(30)


if __name__=='__main__':main()
