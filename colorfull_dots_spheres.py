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
import pygame
import display_utils
import math
import cv2
import mediapipe as mp
import random

# MediaPipe Hands の初期化
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, 
    max_num_hands=6,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Webcam の初期化
cap = display_utils.open_camera()

def get_fibonacci_sphere_points(samples=300):
    """球体上に均等に点を配置する（フィボナッチ球アルゴリズム）"""
    points = []
    phi = math.pi * (3. - math.sqrt(5.))
    for i in range(samples):
        y = 1 - (i / float(samples - 1)) * 2
        radius = math.sqrt(1 - y * y)
        theta = phi * i
        x = math.cos(theta) * radius
        z = math.sin(theta) * radius
        points.append((x, y, z))
    return points

def rotate_3d(x, y, z, ax, ay, az):
    """3D空間でのXYZ軸ごとの回転"""
    cos_x, sin_x = math.cos(ax), math.sin(ax)
    y1 = y * cos_x - z * sin_x
    z1 = y * sin_x + z * cos_x
    cos_y, sin_y = math.cos(ay), math.sin(ay)
    x2 = x * cos_y + z1 * sin_y
    z2 = -x * sin_y + z1 * cos_y
    cos_z, sin_z = math.cos(az), math.sin(az)
    x3 = x2 * cos_z - y1 * sin_z
    y3 = x2 * sin_z + y1 * cos_z
    return x3, y3, z2

def main():
    pygame.init()
    info = pygame.display.Info()
    w, h = info.current_w, info.current_h
    screen, _pg_size = display_utils.setup_pygame_fullscreen()
    pygame.display.set_caption("Colorful Dots Spheres")
    clock = pygame.time.Clock()

    # 8つの球体（大きい順: 白→赤→青→黄 を2回繰り返し）
    spheres_info = [
        {"radius": 360.0, "color": (255, 255, 255)},
        {"radius": 357.5, "color": (255,  50,  50)},
        {"radius": 355.0, "color": ( 50, 150, 255)},
        {"radius": 352.5, "color": (255, 255,  50)},
        {"radius": 350.0, "color": (255, 255, 255)},
        {"radius": 347.5, "color": (255,  50,  50)},
        {"radius": 345.0, "color": ( 50, 150, 255)},
        {"radius": 342.5, "color": (255, 255,  50)},
    ]
    num_spheres = len(spheres_info)

    base_points = get_fibonacci_sphere_points(300)

    fov = min(w, h) * 0.8
    viewer_distance = 800.0

    # 同期ロジック: 30秒 × 60fps = 1800フレームで全球体が同じ向きに戻る
    SYNC_FRAMES = 1800
    BASE = (2.0 * math.pi) / SYNC_FRAMES

    # 10パターンの回転定義（各球体に独立した回転方向）
    ROTATION_PATTERNS = [
        [( 1, 0, 0), ( 0, 1, 0), ( 0, 0, 1), (-1, 0, 0), ( 0,-1, 0), ( 0, 0,-1), ( 1, 1, 0), (-1,-1, 0)],
        [( 1, 1, 0), (-1, 1, 0), ( 1,-1, 0), (-1,-1, 0), ( 0, 1, 1), ( 0,-1, 1), ( 0, 1,-1), ( 0,-1,-1)],
        [( 1, 0, 1), ( 0, 1,-1), (-1, 0, 1), ( 0,-1,-1), ( 1, 1, 1), (-1,-1,-1), ( 1,-1, 1), (-1, 1,-1)],
        [( 2, 0, 0), ( 0, 2, 0), ( 0, 0, 2), ( 1, 1, 0), ( 1, 2, 0), ( 2, 1, 0), ( 0, 1, 1), ( 0,-1,-1)],
        [( 1, 1, 1), (-1, 1,-1), ( 1,-1,-1), (-1,-1, 1), ( 2, 0,-1), (-2, 0, 1), ( 0, 2,-1), ( 0,-2, 1)],
        [( 2, 1, 0), ( 0, 2, 1), ( 1, 0, 2), (-1,-2, 0), (-1, 0,-2), ( 0,-2,-1), ( 1, 1,-1), (-1,-1, 1)],
        [( 1, 2, 0), (-1,-2, 0), ( 2, 0, 1), (-2, 0,-1), ( 0, 1, 2), ( 0,-1,-2), ( 1, 0,-2), (-1, 0, 2)],
        [( 1, 0,-1), ( 0, 1, 1), (-1, 1, 0), ( 1,-1, 0), ( 2,-1, 0), (-2, 1, 0), ( 0, 2, 1), ( 0,-2,-1)],
        [( 2,-1, 0), (-1, 0, 2), ( 0, 2,-1), ( 1,-1, 1), (-2, 1, 0), ( 1, 0,-2), ( 0,-2, 1), (-1, 1,-1)],
        [( 1, 2,-1), (-2, 1, 1), ( 1,-1, 2), (-1, 1,-2), ( 2,-1, 1), (-1, 2,-1), ( 1, 1,-2), (-1,-1, 2)],
    ]
    NUM_PATTERNS = len(ROTATION_PATTERNS)

    auto_angles = [[0.0, 0.0, 0.0] for _ in range(num_spheres)]
    current_pattern = 0
    frame_in_cycle = 0

    # 同期時のフラッシュ
    sync_flash_timer = 0
    SYNC_FLASH_DURATION = 50

    # 人差し指によるプルプルエフェクト
    finger_positions = []
    INTERACTION_RADIUS = 70.0

    cam_surface = pygame.Surface((w, h)).convert_alpha()

    running = True
    while running:
        clock.tick(60)
        screen.fill((0, 0, 0))
        finger_positions = []

        # ── カメラ映像と指の位置検出 ──
        ret, frame = cap.read()
        finger_detected = False
        if ret:
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    # 人差し指の先端座標をスクリーンに合わせてスケーリング
                    index_tip = hand_landmarks.landmark[8]
                    finger_positions.append((int(index_tip.x * w), int(index_tip.y * h)))
                finger_detected = True

            # カメラ映像を薄く背景表示
            frame_resized = cv2.resize(rgb_frame, (w, h))
            frame_transposed = frame_resized.transpose([1, 0, 2])
            pygame.surfarray.blit_array(cam_surface, frame_transposed)
            cam_surface.set_alpha(70)
            screen.blit(cam_surface, (0, 0))

        if not finger_detected:
            finger_positions = []

        # ── アニメーション更新 ──
        frame_in_cycle += 1
        if frame_in_cycle >= SYNC_FRAMES:
            frame_in_cycle = 0
            auto_angles = [[0.0, 0.0, 0.0] for _ in range(num_spheres)]
            current_pattern = (current_pattern + 1) % NUM_PATTERNS
            sync_flash_timer = SYNC_FLASH_DURATION

        pattern = ROTATION_PATTERNS[current_pattern]
        for i in range(num_spheres):
            mx, my, mz = pattern[i]
            auto_angles[i][0] += BASE * mx
            auto_angles[i][1] += BASE * my
            auto_angles[i][2] += BASE * mz

        # フラッシュの減衰
        flash_intensity = 0.0
        if sync_flash_timer > 0:
            flash_intensity = sync_flash_timer / float(SYNC_FLASH_DURATION)
            sync_flash_timer -= 1

        # ── 3Dドット計算 ──
        dots_to_draw = []
        for px, py, pz in base_points:
            for idx, layer in enumerate(spheres_info):
                r = layer["radius"]
                base_color = layer["color"]

                ax, ay, az = auto_angles[idx]
                frx, fry, frz = rotate_3d(px, py, pz, ax, ay, az)

                if frz > 0:
                    continue  # 前面のみ表示

                # 奥行きによるシェーディング（前面ほど濃く/明るくする）
                # frzは 0.0(側面) から -1.0(最も前面) の値をとるため、abs(frz)を明るさ係数に利用
                brightness = 0.2 + 0.8 * abs(frz)
                depth_color = (
                    int(base_color[0] * brightness),
                    int(base_color[1] * brightness),
                    int(base_color[2] * brightness)
                )

                # 同期発光: 色を白に近づける
                if flash_intensity > 0:
                    color = (
                        int(depth_color[0] + (255 - depth_color[0]) * flash_intensity),
                        int(depth_color[1] + (255 - depth_color[1]) * flash_intensity),
                        int(depth_color[2] + (255 - depth_color[2]) * flash_intensity),
                    )
                else:
                    color = depth_color

                # 3D → 2D 投影
                vz = frz * r + viewer_distance
                if vz > 0.1:
                    factor = fov / vz
                    sx = int(frx * r * factor + w / 2)
                    sy = int(-fry * r * factor + h / 2)
                    dot_size = int(max(1, 3.5 * (viewer_distance / vz)))

                    # プルプルエフェクト: 検出されたすべての指に対して判定
                    jitter_x = 0
                    jitter_y = 0
                    if finger_detected:
                        for f_x, f_y in finger_positions:
                            dist = math.hypot(sx - f_x, sy - f_y)
                            if dist < INTERACTION_RADIUS:
                                j = (1.0 - dist / INTERACTION_RADIUS) * 8.0
                                jitter_x += random.uniform(-j, j)
                                jitter_y += random.uniform(-j, j)

                    dots_to_draw.append((
                        vz,
                        int(sx + jitter_x),
                        int(sy + jitter_y),
                        dot_size,
                        color,
                    ))

        # ── Zソートして奥から描画 ──
        dots_to_draw.sort(key=lambda d: d[0], reverse=True)
        for _, sx, sy, dot_size, color in dots_to_draw:
            if 0 <= sx < w and 0 <= sy < h:
                pygame.draw.circle(screen, color, (sx, sy), dot_size)

        # ── イベント処理 ──
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
        pygame.display.flip()

    cap.release()
    pygame.quit()

if __name__ == "__main__":
    main()
