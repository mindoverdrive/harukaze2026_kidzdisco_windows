"""Bounded five-face spatial tracking and twelve silent mesh forms."""
from dataclasses import dataclass
import math
import random
import numpy as np
from polygon_face_field import mouth_openness

FORMS = ('flower','crystal','water','ribbon','star','feather','leaf','coral',
         'gear','origami','tentacle','spiral')
SEGMENTS, RINGS = 48, 4
OPEN_EXPANSION_GAIN = 1.72  # Closed 1.0; maximum 2.72, twice the previous 1.36.
EXPANSION_RESPONSE_RATE = 10.  # ~230 ms to reach 90%; independent of mouth detection.
MAX_VIEWPORT_RADIUS_FRACTION = .30


@dataclass(frozen=True)
class Settings:
    max_faces: int = 5
    morph_seconds: float = .45
    lost_seconds: float = 1.5
    stable_seconds: float = .12
    open_threshold: float = .28
    close_threshold: float = .14

    def __post_init__(self):
        if not 1 <= self.max_faces <= 5:
            raise ValueError('invalid face limit')
        values=(self.morph_seconds,self.lost_seconds,self.stable_seconds)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('timings must be finite and positive')
        if not 0 <= self.close_threshold < self.open_threshold <= 1:
            raise ValueError('invalid mouth hysteresis')


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    width: float
    height: float
    opening: float
    angle: float = 0.


def face_from_landmarks(points, image_width, image_height):
    """Reuse existing mouth ratio in pixel-isotropic coordinates, not index IDs."""
    from types import SimpleNamespace
    if len(points) < 468 or image_width <= 0 or image_height <= 0:
        raise ValueError('invalid face input')
    aspect = image_width/image_height
    scaled=[SimpleNamespace(x=p.x*aspect,y=p.y) for p in points]
    opening=mouth_openness(scaled)
    xs=[p.x for p in points];ys=[p.y for p in points]
    angle=math.atan2((points[152].y-points[10].y)*image_height,
                     (points[152].x-points[10].x)*image_width)-math.pi/2
    return Face((points[1].x+points[168].x)/2,(min(ys)+max(ys))/2,
                max(xs)-min(xs),max(ys)-min(ys),opening,angle)


@dataclass
class Track:
    face: Face
    shape: int
    seen: float
    last_change: float
    previous_shape: int | None = None
    morph_start: float = 0.
    opening: float = 0.
    expansion: float = 0.
    opened: bool = False
    candidate: bool = False
    candidate_since: float = 0.
    armed: bool = False
    closed_since: float | None = None
    pending_open: bool = False
    visible: bool = True
    uncertain: bool = False
    changes: int = 0


class FaceMorphField:
    def __init__(self, seed=20261020, settings=None):
        self.settings=settings or Settings()
        self.rng=random.Random(seed)
        self.tracks={}
        self.previous_time=None
        self.changes=0
        self.last_observation_count=0
        self.last_ambiguous_count=0
        self.last_suppressed_count=0

    def reserved(self):
        return {s for t in self.tracks.values() for s in (t.shape,t.previous_shape) if s is not None}

    def step(self, observations, now):
        if not math.isfinite(now):raise ValueError('nonfinite time')
        now=max(now,self.previous_time if self.previous_time is not None else now)
        elapsed=0 if self.previous_time is None else now-self.previous_time
        dt=min(elapsed,.1)
        self.previous_time=now
        cfg=self.settings
        self.tracks={k:t for k,t in self.tracks.items() if now-t.seen < cfg.lost_seconds}
        was_visible={k:t.visible for k,t in self.tracks.items()}
        for t in self.tracks.values():
            t.visible=False
            if t.previous_shape is not None and now-t.morph_start >= cfg.morph_seconds:
                t.previous_shape=None
        obs=[o for o in observations if all(math.isfinite(v) for v in
             (o.x,o.y,o.width,o.height,o.opening,o.angle)) and o.width>0 and o.height>0][:cfg.max_faces]
        self.last_observation_count=len(obs)
        # Quarantine detections whose mouths/faces are too close to distinguish.
        ambiguous={i for i,a in enumerate(obs) for j,b in enumerate(obs) if i!=j and
                   math.hypot(a.x-b.x,a.y-b.y)<.65*max(a.width,b.width)}
        costs={i:sorted((math.hypot(o.x-t.face.x,o.y-t.face.y),k)
                       for k,t in self.tracks.items()) for i,o in enumerate(obs)}
        def gate(index, key):
            return max(.04,min(.18,1.1*max(obs[index].width,self.tracks[key].face.width)))
        # Distant slots are not possible identities for a newly arriving face.
        # Compare ambiguity and assign only among candidates inside their gates.
        matches={i:[(distance,key) for distance,key in candidates if distance<gate(i,key)]
                 for i,candidates in costs.items()}
        for i, candidates in matches.items():
            if len(candidates)>1 and candidates[1][0]-candidates[0][0]<.035:
                ambiguous.add(i)
        # Competing detections for one old slot also remain quiet.
        nearest={}
        for i,candidates in matches.items():
            if i not in ambiguous and candidates:
                nearest.setdefault(candidates[0][1],[]).append(i)
        for indices in nearest.values():
            if len(indices)>1:ambiguous.update(indices)
        self.last_ambiguous_count=len(ambiguous)
        # Appearance-free tracking cannot resolve two identical crossing faces.
        # Reserve but silence those old slots until expiry rather than guessing.
        for i in ambiguous:
            for distance,key in costs[i]:
                if distance<gate(i,key)*2:
                    self.tracks[key].uncertain=True
        used=set()
        for i,o in enumerate(obs):
            if i in ambiguous:continue
            candidates=matches[i]
            if candidates and self.tracks[candidates[0][1]].uncertain:
                continue
            key=candidates[0][1] if candidates else None
            if key in used:continue
            if key is None:
                # Do not spawn a new identity next to a reserved/lost track.
                if any(distance<gate(i,other_key)*1.25 for distance,other_key in costs[i]):continue
                key=next((k for k in range(cfg.max_faces) if k not in self.tracks),None)
                available=sorted(set(range(len(FORMS)))-self.reserved())
                if key is None or not available:continue
                self.tracks[key]=Track(o,self.rng.choice(available),now,now,candidate_since=now)
            t=self.tracks[key];used.add(key)
            gap=now-t.seen
            # A return must establish a fresh stable closed mouth before opening.
            if gap>.15 or elapsed>.25 or not was_visible.get(key,True):
                t.armed=False;t.closed_since=None;t.pending_open=False;t.candidate_since=now
            t.face=o;t.seen=now;t.visible=True
            raw_opening=min(1.,max(0.,o.opening))
            t.opening+=(raw_opening-t.opening)*(-math.expm1(-dt*18))
            t.expansion+=(raw_opening-t.expansion)*(-math.expm1(-dt*EXPANSION_RESPONSE_RATE))
            # Initial smoothing at zero is not evidence that a newly seen face
            # was closed. Require both observed and smoothed closure for rearming.
            if raw_opening<=cfg.close_threshold and t.opening<=cfg.close_threshold:
                if t.closed_since is None:t.closed_since=now
                if now-t.closed_since>=cfg.stable_seconds:t.armed=True
            else:
                t.closed_since=None
            wanted=t.opening>(cfg.close_threshold if t.opened else cfg.open_threshold)
            if wanted!=t.candidate:
                t.candidate=wanted;t.candidate_since=now
            if wanted!=t.opened and now-t.candidate_since>=cfg.stable_seconds:
                t.opened=wanted
                if wanted:
                    t.pending_open=t.armed
                    t.armed=False
                else:
                    t.pending_open=False
            # One opening can wait for an in-flight morph, never an unbounded
            # queue. Stable closure/loss cancels any obsolete pending event.
            if t.pending_open and t.opened and t.previous_shape is None:
                available=sorted(set(range(len(FORMS)))-self.reserved())
                if available:
                    t.previous_shape=t.shape;t.shape=self.rng.choice(available)
                    t.morph_start=t.last_change=now;t.pending_open=False;t.changes+=1;self.changes+=1
        # Suppressed includes ambiguous input and any observation that could not
        # receive a safe slot; it is separate from the number of retained tracks.
        self.last_suppressed_count=len(obs)-len(used)

    def close(self):
        self.tracks.clear();self.previous_time=None
        self.last_observation_count=self.last_ambiguous_count=self.last_suppressed_count=0


def local_mesh(shape, opening, now):
    """Same fixed topology for all forms: 193 vertices, 336 triangles."""
    a=np.arange(SEGMENTS)*math.tau/SEGMENTS
    pulse=min(1.,max(0.,opening))
    # Different topology silhouettes/motion, rather than twelve recolorings.
    profiles=[
        .77+.20*np.cos(6*a),
        .72+.25*np.abs(np.cos(3*a))**5,
        .87+.08*np.sin(3*a-now*2),
        .52+.43*np.abs(np.cos(a))**2,
        .60+.36*np.maximum(0,np.cos(5*a))**2,
        .55+.40*np.abs(np.sin(a))+.08*np.sin(12*a),
        .51+.43*np.abs(np.sin(a))**.6,
        .70+.16*np.sin(7*a)+.10*np.cos(11*a),
        .73+.22*(np.cos(12*a)>.1),
        .68+.25*np.abs(np.cos(2*a+.3)),
        .63+.29*np.maximum(0,np.sin(8*a+now*2))**3,
        .72+.22*np.sin(3*a+now*1.4)]
    radius=np.clip(profiles[shape],.25,1.)
    verts=[(0.,0.)]
    for ring in range(1,RINGS+1):
        fraction=ring/RINGS
        twist=(.20*pulse*fraction*np.sin(now*2+ring+shape))
        if shape==11:twist+=fraction*(.6+pulse*.7)
        if shape==3:twist+=.35*np.sin(now*2+fraction*4)*pulse
        radial=radius*fraction*(1+.12*pulse*np.sin(4*a-now*3+fraction*4))
        verts.extend(zip(radial*np.cos(a+twist),radial*np.sin(a+twist)))
    vertices=np.asarray(verts,dtype=float)
    lengths=np.linalg.norm(vertices,axis=1)
    vertices/=np.maximum(1.,lengths)[:,None]
    triangles=[]
    for j in range(SEGMENTS):triangles.append((0,1+j,1+(j+1)%SEGMENTS))
    for ring in range(1,RINGS):
        inner=1+(ring-1)*SEGMENTS;outer=1+ring*SEGMENTS
        for j in range(SEGMENTS):
            k=(j+1)%SEGMENTS
            triangles.extend([(inner+j,outer+j,outer+k),(inner+j,outer+k,inner+k)])
    return vertices,np.asarray(triangles,dtype=np.int32)


def stage_mesh(track, now, layout, morph_seconds=.45):
    from display_utils import normalized_to_stage
    verts,triangles=local_mesh(track.shape,track.opening,now)
    if track.previous_shape is not None:
        old,_=local_mesh(track.previous_shape,track.opening,now)
        p=min(1.,max(0.,(now-track.morph_start)/morph_seconds));p=p*p*(3-2*p)
        verts=old*(1-p)+verts*p
    f=track.face
    center=normalized_to_stage(f.x,f.y,layout)
    expansion=min(1.,max(0.,track.expansion))
    rx=f.width*layout['scaled_width']*.62*(1+OPEN_EXPANSION_GAIN*expansion)
    ry=f.height*layout['scaled_height']*.60*(1+OPEN_EXPANSION_GAIN*expansion)
    # Preserve aspect and rotation while keeping even a very close face from
    # covering the screen. Neighbour and navigation limits remain in the renderer.
    radius_limit=min(layout['stage_width'],layout['stage_height'])*MAX_VIEWPORT_RADIUS_FRACTION
    shrink=min(1.,radius_limit/max(rx,ry))
    rx*=shrink;ry*=shrink
    points=verts*np.array([rx,ry])
    c,s=math.cos(f.angle),math.sin(f.angle)
    points=points@np.array([[c,s],[-s,c]])
    points+=center
    w,h=layout['stage_width'],layout['stage_height']
    points[:,0]=np.clip(points[:,0],0,w-1)
    points[:,1]=np.clip(points[:,1],0,h-1)
    return points.astype(np.int32),triangles
