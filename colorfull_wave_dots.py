import display_utils
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
import pygame, math, cv2, mediapipe as mp

# MediaPipeの初期化
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, max_num_hands=5, min_detection_confidence=0.7, min_tracking_confidence=0.5)
cap = display_utils.open_camera() # カメラIDは環境に合わせて調整（通常は0or1）

pygame.init()
screen, _pg_size = display_utils.setup_pygame_fullscreen()
W, H = screen.get_size()
clock = pygame.time.Clock()

# パーティクルの生成（画面全体にグリッド配置）
spacing = 15
particles = []
for x in range(0, W, spacing):
    for y in range(0, H, spacing):
        particles.append({'x': x, 'y': y, 'ox': x, 'oy': y, 'vx': 0, 'vy': 0, 'pinch_effect': 0.0})

mx, my = W // 2, H // 2
m_down = False
running = True
while running:
    # カメラ映像の取得と人差し指の検出
    ret, frame = cap.read()
    active_hands = []
    if ret:
        frame = cv2.flip(frame, 1)
        results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # 人差し指の先端 (ID: 8)
                index_tip = hand_landmarks.landmark[8]
                hx, hy = int(index_tip.x * W), int(index_tip.y * H)
                # 親指の先端 (ID: 4) との距離でクリックをシミュレート
                thumb_tip = hand_landmarks.landmark[4]
                dist_click = math.hypot(index_tip.x - thumb_tip.x, index_tip.y - thumb_tip.y)
                h_down = dist_click < 0.05 # 距離が近い場合にTrue
                active_hands.append({'x': hx, 'y': hy, 'down': h_down})

    screen.fill((0, 0, 0))
    for p in particles:
        vx_add, vy_add = 0, 0
        for h in active_hands:
            dx, dy = h['x'] - p['x'], h['y'] - p['y']
            dist = math.hypot(dx, dy)
            
            # 影響範囲を150から75に半減
            if dist < 75:
                angle = math.atan2(dy, dx)
                force = (75 - dist) * 0.4 # 力の強さを維持するため係数を調整
                if h['down']: 
                    force *= 5
                    p['pinch_effect'] = 1.0  # ピンチの影響を受けたパーティクルにエフェクトを付与
                vx_add -= math.cos(angle) * force
                vy_add -= math.sin(angle) * force
        
        p['vx'] += vx_add
        p['vy'] += vy_add

        p['vx'] += (p['ox'] - p['x']) * 0.05
        p['vy'] += (p['oy'] - p['y']) * 0.05
        p['vx'] *= 0.92
        p['vy'] *= 0.92
        p['x'] += p['vx']
        p['y'] += p['vy']

        # エフェクトを時間経過で減衰 (0.05 なら 1秒弱で消える速さ)
        if p['pinch_effect'] > 0:
            p['pinch_effect'] -= 0.05
            if p['pinch_effect'] < 0:
                p['pinch_effect'] = 0.0

        # 元の場所からの移動距離を計算
        dist_from_orig = math.hypot(p['x'] - p['ox'], p['y'] - p['oy'])
        
        # 移動距離とアクション状態に応じて色を変化させる
        dist_factor = min(1.0, dist_from_orig / 100.0)
        
        # 基本のホバー時の色 (オレンジ〜ゴールド)
        base_hue = 20 + (30 * (1.0 - dist_factor))
        base_sat = 70 + (30 * dist_factor)
        base_bright = 90 + (10 * (1.0 - dist_factor))
        
        # ピンチ時の色 (濃い青)
        pinch_hue = 240 - (30 * (1.0 - dist_factor))
        pinch_sat = 80 + (20 * dist_factor)
        pinch_bright = 40 + (50 * (1.0 - dist_factor))

        # 静止時は低彩度シアン
        if dist_from_orig < 5:
            base_hue = 180
            base_sat = 20
            base_bright = 60

        # エフェクトの強度による色のブレンド (1.0 = ピンチ色, 0.0 = ベース色)
        effect = p['pinch_effect']
        hue = base_hue * (1.0 - effect) + pinch_hue * effect
        sat = base_sat * (1.0 - effect) + pinch_sat * effect
        bright = base_bright * (1.0 - effect) + pinch_bright * effect
        
        color = pygame.Color(0)
        color.hsva = (int(hue) % 360, int(sat), int(bright), 100)

        # 弾けたときの派手なエフェクト描画
        if p['pinch_effect'] > 0:
            effect_val = p['pinch_effect']
            ease_val = effect_val ** 0.5 # 変化を滑らかに強調
            
            center = (int(p['x']), int(p['y']))
            
            # 中心部のコアは一時的に白っぽく明るく発光させる（暗い色でも目立たせるため）
            core_color = pygame.Color(0)
            c_sat = max(0, int(sat - 70 * ease_val))
            c_bri = min(100, int(bright + 60 * ease_val))
            core_color.hsva = (int(hue) % 360, c_sat, c_bri, 100)
            
            # 広がるオーラ（指定された濃い青色などを強調する外輪）
            outer_radius = int(2 + ease_val * 12)
            if outer_radius > 2:
                pygame.draw.circle(screen, color, center, outer_radius, max(1, int(effect_val * 3)))
            
            # 中心部
            core_radius = int(2 + ease_val * 4)
            pygame.draw.circle(screen, core_color, center, core_radius)
            
            # 光の筋（スパークエフェクト）
            if effect_val > 0.4:
                line_len = ease_val * 16
                pygame.draw.line(screen, core_color, (int(center[0] - line_len), center[1]), (int(center[0] + line_len), center[1]), 2)
                pygame.draw.line(screen, core_color, (center[0], int(center[1] - line_len)), (center[0], int(center[1] + line_len)), 2)
                
                # 斜めの筋も追加して星型のキラキラに
                diag_len = line_len * 0.7
                pygame.draw.line(screen, core_color, (int(center[0] - diag_len), int(center[1] - diag_len)), (int(center[0] + diag_len), int(center[1] + diag_len)), 1)
                pygame.draw.line(screen, core_color, (int(center[0] - diag_len), int(center[1] + diag_len)), (int(center[0] + diag_len), int(center[1] - diag_len)), 1)
        else:
            pygame.draw.rect(screen, color, (int(p['x']), int(p['y']), 2, 2))

    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: running = False

    pygame.display.flip()
    clock.tick(60)

    hands.close()
    cap.release()
    pygame.quit()
