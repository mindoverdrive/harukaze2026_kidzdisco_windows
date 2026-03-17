# =============================================================================
# [AUTO-INJECTED] Scene Preload & Wait Logic
# =============================================================================
import sys
import argparse
import socket
import json

# Only execute the wait logic if we are running the script directly
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP port to listen on for START signal")
    # Parse known args so we don't crash if other args are passed
    args, _ = parser.parse_known_args()

    if args.wait and args.port > 0:
        print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {args.port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.settimeout(None) # Wait indefinitely
        
        while True:
            data, addr = sock.recvfrom(1024)
            try:
                msg = json.loads(data.decode('utf-8'))
                if msg.get("cmd") == "START":
                    print("[Scene] Received START command. Booting up...")
                    sock.close()
                    break
            except Exception as e:
                pass
# =============================================================================
# カメラから顔を検出し、口の開きに応じて螺旋エフェクトを適用するプログラム
# また、口を二秒間開け続けると、煙のようなエフェクトも表示されます。
#

import math
import cv2
import numpy as np
import time
import random

try:
    import mediapipe as mp
except Exception as e:
    raise ImportError('mediapipe is required. Install with: pip install mediapipe') from e

mp_face = mp.solutions.face_mesh


def mouth_openness(landmarks, img_w, img_h):
    # Use landmark indices 13 (upper inner lip) and 14 (lower inner lip) as a simple measure
    # landmarks are normalized; convert to pixel coords
    try:
        up = landmarks[13]
        down = landmarks[14]
    except Exception:
        # fallback: compute using average of some lip points
        up = landmarks[0]
        down = landmarks[17]

    uy = up.y * img_h
    dy = down.y * img_h
    # face height for normalization: use min/max of landmarks
    ys = [p.y for p in landmarks]
    face_h = (max(ys) - min(ys)) * img_h
    if face_h <= 1:
        return 0.0
    openness = max(0.0, (dy - uy) / face_h)
    return float(openness)


def apply_spiral_region(img, center, radius, twist, strength):
    # center: (cx, cy), radius: pixels
    h, w = img.shape[:2]
    cx, cy = center

    # prepare grid inside bounding square
    x0 = int(max(0, cx - radius))
    x1 = int(min(w, cx + radius))
    y0 = int(max(0, cy - radius))
    y1 = int(min(h, cy + radius))

    if x1 <= x0 or y1 <= y0:
        return img

    roi = img[y0:y1, x0:x1].copy()
    hh, ww = roi.shape[:2]

    # coordinates relative to center
    xs = np.linspace(0, ww - 1, ww)
    ys = np.linspace(0, hh - 1, hh)
    xv, yv = np.meshgrid(xs, ys)
    rx = xv - (cx - x0)
    ry = yv - (cy - y0)
    r = np.sqrt(rx ** 2 + ry ** 2)

    # normalized radius [0..1]
    R = radius
    with np.errstate(divide='ignore', invalid='ignore'):
        rn = r / R

    inside = rn <= 1.0
    theta = np.arctan2(ry, rx)

    # falloff: strongest at outer edge, zero at center (so pixels move toward center)
    # use a stronger (quadratic) falloff to emphasize outer swirl for dramatic effect
    falloff = (1 - rn) ** 2.0
    falloff = np.clip(falloff, 0.0, 1.0)

    # compute new radius and angle (spiral inward)
    new_r = r * (1 - strength * falloff * inside)
    new_theta = theta + twist * falloff * inside

    # source coordinates
    src_x = new_r * np.cos(new_theta) + (cx - x0)
    src_y = new_r * np.sin(new_theta) + (cy - y0)

    # for points outside circle use original coords
    src_x = np.where(inside, src_x, xv)
    src_y = np.where(inside, src_y, yv)

    # remap
    map_x = src_x.astype(np.float32)
    map_y = src_y.astype(np.float32)
    warped = cv2.remap(roi, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    out = img.copy()
    out[y0:y1, x0:x1] = warped
    return out


def spawn_puff(particles, x, y, now):
    # create several cartoon-like smoke blobs for a 'モクモク' puff
    n = random.randint(4, 9)
    for i in range(n):
        ang = random.uniform(-math.pi / 3, math.pi / 3)
        speed = random.uniform(60.0, 200.0)
        vx = math.sin(ang) * speed * random.uniform(0.4, 1.0)
        vy = -abs(math.cos(ang) * speed) * random.uniform(0.35, 0.9)  # upward
        size = random.uniform(14.0, 40.0)
        life = random.uniform(1.2, 2.6)
        particles.append({
            'x': float(x) + random.uniform(-12, 12),
            'y': float(y) + random.uniform(-8, 8),
            'vx': vx,
            'vy': vy,
            'size': size,
            'age': 0.0,
            'life': life,
            'alpha': 1.0,
            'spawn_time': now,
        })


def update_and_draw_smoke(img, particles, dt):
    if len(particles) == 0:
        return img

    h, w = img.shape[:2]
    overlay = np.zeros((h, w, 3), dtype=np.float32)
    new_particles = []

    for p in particles:
        p['age'] += dt
        if p['age'] > p['life']:
            continue

        # simple physics
        p['x'] += p['vx'] * dt
        p['y'] += p['vy'] * dt
        # gravity-like slowdown (reduce upward speed)
        p['vy'] += 20.0 * dt

        # growth and fade
        p['size'] += 8.0 * dt
        p['alpha'] = max(0.0, 1.0 - (p['age'] / p['life']))

        # draw circle on overlay (white with intensity)
        cx = int(p['x'])
        cy = int(p['y'])
        if cx < -50 or cx > w + 50 or cy < -50 or cy > h + 50:
            continue

        color_val = float(255.0 * p['alpha'])
        rr = int(max(1, p['size']))
        cv2.circle(overlay, (cx, cy), rr, (color_val, color_val, color_val), -1, lineType=cv2.LINE_AA)
        new_particles.append(p)

    # apply blur to make it soft and cartoonish (larger kernel for fluffy look)
    k = 31
    if k % 2 == 0:
        k += 1
    overlay = cv2.GaussianBlur(overlay, (k, k), 0)

    # composite: add overlay onto image with clipping (stronger blend for visibility)
    out = img.astype(np.float32)
    out += overlay * 1.4
    out = np.clip(out, 0, 255).astype(np.uint8)

    # update particle list
    particles[:] = new_particles
    return out


def run(max_faces=5, camera_id=1):
    cap = cv2.VideoCapture(2)
    cv2.namedWindow('Spiral Mouth Effect (press q to quit)', cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty('Spiral Mouth Effect (press q to quit)', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    if not cap.isOpened():
        print('Cannot open camera')
        return

    with mp_face.FaceMesh(static_image_mode=False,
                          max_num_faces=max_faces,
                          refine_landmarks=False,
                          min_detection_confidence=0.5,
                          min_tracking_confidence=0.5) as face_mesh:
        # smoke particle system and trackers for sustained-open detection
        particles = []
        trackers = []  # list of dicts: x,y,last_seen,emitting,emit_timer
        # lower threshold so mouth-open produces smoke more easily
        smoke_open_threshold = 0.18
        # spawn more frequently for continuous emission
        emit_interval = 0.08
        prev_time = time.time()

        while True:
            now = time.time()
            dt = now - prev_time
            prev_time = now

            ret, frame = cap.read()
            if not ret:
                break

            img_h, img_w = frame.shape[:2]
            # convert to RGB for MediaPipe
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            out = frame

            if results.multi_face_landmarks:
                # process each face
                face_mouths = []
                for face_landmarks in results.multi_face_landmarks:
                    lm = face_landmarks.landmark

                    # compute pixel coords list
                    pts = [(int(p.x * img_w), int(p.y * img_h)) for p in lm]
                    pts_f = lm

                    # prepare overall landmark arrays (used for bbox and fallback)
                    xs = [p.x for p in lm]
                    ys = [p.y for p in lm]

                    # mouth center: average of key mouth landmarks (inner top/bottom and corners)
                    try:
                        mouth_idxs = [13, 14, 61, 291]
                        mx = np.mean([lm[i].x for i in mouth_idxs])
                        my = np.mean([lm[i].y for i in mouth_idxs])
                        cx = int(mx * img_w)
                        cy = int(my * img_h)
                    except Exception:
                        # fallback to face center if mouth landmarks unavailable
                        cx = int(np.mean(xs) * img_w)
                        cy = int(np.mean(ys) * img_h)

                    # face radius: half of diagonal of bbox
                    minx = int(min(xs) * img_w)
                    maxx = int(max(xs) * img_w)
                    miny = int(min(ys) * img_h)
                    maxy = int(max(ys) * img_h)
                    face_w = maxx - minx
                    face_h = maxy - miny
                    # increase radius a bit to make the swirl cover more area
                    radius = int(0.9 * max(face_w, face_h) / 2)
                    radius = max(radius, 20)

                    openness = mouth_openness(lm, img_w, img_h)

                    # store mouth center, openness and radius for tracker and swirl processing
                    face_mouths.append((cx, cy, openness, radius))

                # update trackers: match mouths to trackers by proximity
                for (mx, my, openness, radius) in face_mouths:
                    # find nearest tracker within threshold
                    matched = None
                    best_d = 1e9
                    for t in trackers:
                        d = math.hypot(t['x'] - mx, t['y'] - my)
                        if d < 80 and d < best_d:
                            matched = t
                            best_d = d

                    if matched is None:
                        # create new tracker
                        matched = {'x': mx, 'y': my, 'open_accum': 0.0, 'last_seen': now, 'emitting': False, 'emit_timer': 0.0}
                        trackers.append(matched)

                    # update pos and last seen
                    matched['x'] = mx
                    matched['y'] = my
                    matched['last_seen'] = now

                    # update open accumulation
                    if openness >= smoke_open_threshold:
                        matched['open_accum'] += dt
                    else:
                        matched['open_accum'] = 0.0
                        matched['emitting'] = False
                        matched['emit_timer'] = 0.0

                    # start emitting after 2 seconds sustained open
                    if matched['open_accum'] >= 2.0 and not matched['emitting']:
                        matched['emitting'] = True
                        matched['emit_timer'] = 0.0
                        matched['open_accum'] = 0.0

                    # if emitting, spawn puffs periodically
                    if matched['emitting']:
                        matched['emit_timer'] += dt
                        if matched['emit_timer'] >= emit_interval:
                            # spawn a puff at mouth center
                            spawn_puff(particles, matched['x'], matched['y'], now)
                            matched['emit_timer'] = 0.0

                    # apply swirl effect only if mouth is open a bit
                    if openness < 0.02:
                        continue

                    # map openness to strength and twist (amplified for dramatic effect)
                    base_strength = openness * 4.0
                    strength = float(np.clip(base_strength, 0.0, 1.5))
                    twist = -18.0 * (openness ** 0.9 + openness * 0.5)

                    # apply a two-pass swirl for a more intense, surprising effect
                    out = apply_spiral_region(out, (mx, my), int(radius * 1.1), twist, strength)
                    out = apply_spiral_region(out, (mx, my), radius, twist * 0.6, strength * 0.8)

                # remove stale trackers
                trackers = [t for t in trackers if now - t['last_seen'] < 1.0]

            # update and draw smoke
            out = update_and_draw_smoke(out, particles, dt)
            # show
            cv2.imshow('Spiral Mouth Effect (press q to quit)', out)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    print('起動: カメラから顔を検出し、口の開きで螺旋エフェクトを適用します。qで終了')
    run(max_faces=5, camera_id=1)
