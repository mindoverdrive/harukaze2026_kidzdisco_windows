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
import colorsys
import sys
import cv2
import mediapipe as mp

# Type 0: Classic Branch (標準的な枝分かれフラクタル)
def draw_fractal_classic(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist):
    if depth == 0 or length < 2:
        return
        
    hue = (hue_base + (max_depth - depth) * 0.08 + twist * 0.1) % 1.0
    color = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.9, 1.0)]
    
    end_x = x + math.cos(angle) * length
    end_y = y + math.sin(angle) * length
    width = max(1, depth - 1)
    
    pygame.draw.line(surface, color, (int(x), int(y)), (int(end_x), int(end_y)), width)
    if depth < max_depth - 1:
        pygame.draw.circle(surface, (255, 255, 255), (int(end_x), int(end_y)), 1)
    
    spread = (math.pi / 3) * math.sin(time_val * 1.5 + depth * 0.5) + twist * 0.3
    shrink = 0.72

    draw_fractal_classic(surface, end_x, end_y, length * shrink, angle - spread, depth - 1, max_depth, hue_base, time_val, twist)
    draw_fractal_classic(surface, end_x, end_y, length * shrink, angle + spread, depth - 1, max_depth, hue_base, time_val, twist)

# Type 1: Spiro-Star (星型・多角形が連なるフラクタル)
def draw_fractal_spiro(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist):
    if depth == 0 or length < 3:
        return
        
    hue = (hue_base + (max_depth - depth) * 0.15 - twist * 0.2) % 1.0
    color = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.8, 1.0)]
    
    # 線の代わりに多角形を描画してスピログラフのような見た目に
    points = []
    sides = 4 + (depth % 3) # 深さによって四角形〜六角形に変化
    for j in range(sides):
        p_angle = angle + (j * 2 * math.pi / sides) + (time_val * 2)
        px = x + math.cos(p_angle) * (length * 0.5)
        py = y + math.sin(p_angle) * (length * 0.5)
        points.append((int(px), int(py)))
        
    if len(points) >= 3:
        # 中を塗らずに線分で描画して重なりを美しく見せる
        pygame.draw.polygon(surface, color, points, max(1, depth // 2))
    
    end_x = x + math.cos(angle) * length
    end_y = y + math.sin(angle) * length
    
    # 拡散の仕方もクラシックとは少し変え、回転を強めにする
    spread = (math.pi / 2.5) + math.sin(time_val * 3) * 0.2 + twist * 0.5
    shrink = 0.65
    
    draw_fractal_spiro(surface, end_x, end_y, length * shrink, angle - spread, depth - 1, max_depth, hue_base, time_val, twist)
    draw_fractal_spiro(surface, end_x, end_y, length * shrink, angle + spread, depth - 1, max_depth, hue_base, time_val, twist)

# Type 2: Jagged Lightning (稲妻のような鋭角で細かく別れるフラクタル)
def draw_fractal_lightning(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist):
    if depth == 0 or length < 1.5:
        return
        
    hue = (hue_base + (max_depth - depth) * 0.05 + twist * 0.3 + 0.5) % 1.0
    color = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
    
    end_x = x + math.cos(angle) * length
    end_y = y + math.sin(angle) * length
    
    # 稲妻のように細い線
    width = max(1, depth // 2)
    pygame.draw.line(surface, color, (int(x), int(y)), (int(end_x), int(end_y)), width)
    
    # 時折閃光のように白く光る
    if depth % 2 == 0:
        pygame.draw.line(surface, (255, 255, 255), (int(x), int(y)), (int(end_x), int(end_y)), 1)
    
    # 角度が鋭角にパキパキと折れ曲がる
    spread1 = (math.pi / 6) + twist * 0.4
    spread2 = (math.pi / 4) - twist * 0.2
    
    shrink = 0.8
    # 確率的に3方向に分岐させたりして不安定さを出す(深さによる固定条件で擬似ランダム)
    draw_fractal_lightning(surface, end_x, end_y, length * shrink * 0.9, angle - spread1, depth - 1, max_depth, hue_base, time_val, twist)
    draw_fractal_lightning(surface, end_x, end_y, length * shrink, angle + spread2, depth - 1, max_depth, hue_base, time_val, twist)
    
    if depth % 3 == 0:
        draw_fractal_lightning(surface, end_x, end_y, length * shrink * 0.6, angle + spread1 * 1.5, depth - 1, max_depth, hue_base, time_val, twist)

# Type 3: Circle Ribbon (連なる円で構成されるリボン状のフラクタル)
def draw_fractal_ribbon(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist):
    if depth == 0 or length < 2:
        return
        
    hue = (hue_base - (max_depth - depth) * 0.1 + twist * 0.1) % 1.0
    color = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.7, 1.0)]
    
    # 線の代わりに円を描画し続ける
    radius = max(2, int(length * 0.4))
    
    # メインの円
    pygame.draw.circle(surface, color, (int(x), int(y)), radius, 2)
    
    # 内側にハイライトの小さな円
    pygame.draw.circle(surface, (200, 255, 255), (int(x), int(y)), max(1, radius // 3))
    
    end_x = x + math.cos(angle) * length
    end_y = y + math.sin(angle) * length
    
    # うねるように左右に広がる
    spread = math.sin(time_val + depth) * 0.5 + twist * 0.4
    shrink = 0.8
    
    # 1本のリボンがうねりながら時々2手に別れる
    draw_fractal_ribbon(surface, end_x, end_y, length * shrink, angle + spread, depth - 1, max_depth, hue_base, time_val, twist)
    
    if depth % 4 == 0: # 時々大きく枝分かれ
        draw_fractal_ribbon(surface, end_x, end_y, length * shrink * 0.8, angle - (math.pi / 4), depth - 1, max_depth, hue_base, time_val, twist)


# フラクタル描画のディスパッチャ
def draw_fractal(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist, fractal_type):
    if fractal_type == 0:
        draw_fractal_classic(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist)
    elif fractal_type == 1:
        draw_fractal_spiro(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist)
    elif fractal_type == 2:
        draw_fractal_lightning(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist)
    elif fractal_type == 3:
        draw_fractal_ribbon(surface, x, y, length, angle, depth, max_depth, hue_base, time_val, twist)

class Pointer:
    def __init__(self, x, y, f_type):
        self.current_x = x
        self.current_y = y
        self.target_x = x
        self.target_y = y
        self.prev_x = x
        self.prev_y = y
        self.has_target = False
        self.move_angle = 0.0
        self.twist_factor = 0.0
        self.is_new = True
        
        # 弾ける動き（衝突時）の速度ベクトルを管理
        self.vx = 0.0
        self.vy = 0.0
        
        # 固有のフラクタルタイプ(0~3)を割り当て
        self.fractal_type = f_type

def main():
    pygame.init()
    
    # 画面サイズの設定
    infoObject = pygame.display.Info()
    WIDTH, HEIGHT = infoObject.current_w * 4 // 5, infoObject.current_h * 4 // 5
    screen, _pg_size = display_utils.setup_pygame_fullscreen()
    pygame.display.set_caption("4 Distinct Fractal Trails (Camera Control)")
    
    # マウスカーソルを非表示
    pygame.mouse.set_visible(False)
    
    clock = pygame.time.Clock()
    
    # 残像（トレイル）エフェクト用のサーフェス
    fade_surface = pygame.Surface((WIDTH, HEIGHT))
    fade_surface.set_alpha(10)  
    fade_surface.fill((0, 0, 0))
    
    screen.fill((0, 0, 0))
    
    # --- MediaPipe カメラ設定 ---
    cap = cv2.VideoCapture(3)
    mp_hands = mp.solutions.hands
    # 検出する手を最大4本に変更
    hands = mp_hands.Hands(
        max_num_hands=4,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5
    )
    
    # 4本指分のポインターを準備（それぞれに0~3の異なるフラクタルタイプを割り当てる）
    max_pointers = 4
    pointers = [Pointer(WIDTH // 2, HEIGHT // 2, i) for i in range(max_pointers)]
    
    time_step = 0
    running = True
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    running = False
            elif event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = event.w, event.h
                fade_surface = pygame.Surface((WIDTH, HEIGHT))
                fade_surface.set_alpha(10)
                fade_surface.fill((0, 0, 0))
                
        # カメラ映像の取得と処理
        ret, frame = cap.read()
        target_points = []
        if ret:
            # 鏡のように表示するため左右反転し、RGBに変換
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)
            
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    tx = index_tip.x * WIDTH
                    ty = index_tip.y * HEIGHT
                    target_points.append((tx, ty))
        
        # 軌跡を徐々に消していくためのフェード処理
        screen.blit(fade_surface, (0, 0))
        
        # 検出した指先の数だけポインターに割り当てる (距離が近いもの同士を優先)
        for p in pointers:
            p.has_target = False
            
        for tx, ty in target_points:
            best_p = None
            best_dist = float('inf')
            for p in pointers:
                if not p.has_target:
                    dist = math.hypot(p.current_x - tx, p.current_y - ty)
                    if dist < best_dist:
                        best_dist = dist
                        best_p = p
            
            if best_p is not None:
                best_p.has_target = True
                # 新規の指や、途切れてから復帰した時はワープさせる
                if best_p.is_new or best_dist > 300:
                    best_p.current_x = tx
                    best_p.current_y = ty
                    best_p.vx = 0.0
                    best_p.vy = 0.0
                    best_p.is_new = False
                best_p.target_x = tx
                best_p.target_y = ty

        # 割り当てられなかったポインターは新規扱いとする
        for p in pointers:
            if not p.has_target:
                p.is_new = True
                
        # --- N本同士の衝突判定と弾ける動きの計算 ---
        # アクティブなポインター間で総当り判定を行う (O(N^2)ループ)
        collision_radius = 80
        for i in range(max_pointers):
            p1 = pointers[i]
            if not p1.has_target:
                continue
                
            for j in range(i + 1, max_pointers):
                p2 = pointers[j]
                if not p2.has_target:
                    continue
                    
                dist_x = p2.current_x - p1.current_x
                dist_y = p2.current_y - p1.current_y
                dist = math.hypot(dist_x, dist_y)
                
                if dist < collision_radius and dist > 0:
                    # 重なっている場合、互いに反発力を与える
                    speed1 = math.hypot(p1.current_x - p1.prev_x, p1.current_y - p1.prev_y)
                    speed2 = math.hypot(p2.current_x - p2.prev_x, p2.current_y - p2.prev_y)
                    
                    repel_force = (collision_radius - dist) * 0.5 + (speed1 + speed2) * 0.8
                    
                    nx = dist_x / dist
                    ny = dist_y / dist
                    
                    p1.vx -= nx * repel_force
                    p1.vy -= ny * repel_force
                    p2.vx += nx * repel_force
                    p2.vy += ny * repel_force
                    
                    p1.twist_factor += repel_force * 0.05
                    p2.twist_factor -= repel_force * 0.05
        
        time_step += 1
        time_val = time_step * 0.02
        hue_base = (time_step * 0.003) % 1.0
        
        # 各指先ごとにそのポインター固有のフラクタルを描画
        for p in pointers:
            if p.has_target:
                p.prev_x = p.current_x
                p.prev_y = p.current_y
                
                # 弾かれた速度(vx, vy)を適用
                p.current_x += p.vx
                p.current_y += p.vy
                
                # 弾かれた速度は摩擦で徐々に減衰する
                p.vx *= 0.8
                p.vy *= 0.8
                
                # ターゲットへの滑らかな追従処理
                p.current_x += (p.target_x - p.current_x) * 0.15
                p.current_y += (p.target_y - p.current_y) * 0.15
                
                dx = p.current_x - p.prev_x
                dy = p.current_y - p.prev_y
                speed = math.hypot(dx, dy)
                
                if speed > 0.5:
                    target_angle = math.atan2(dy, dx)
                    diff = (target_angle - p.move_angle + math.pi) % (2 * math.pi) - math.pi
                    p.move_angle += diff * 0.2
                    p.twist_factor = p.twist_factor * 0.8 + (diff * speed * 0.1) * 0.2
                else:
                    p.move_angle += 0.02
                    p.twist_factor *= 0.9  
                
                pulse = math.sin(time_val * 2)
                base_length = 30 + pulse * 10 
                length = base_length + min(speed * 0.8, 40)
                
                # 種類によって最適な分岐数・深さが違うので微調整
                branches = 4
                depth = 6
                if p.fractal_type == 2: # 稲妻は分岐を少し控えめにする代わりに深く
                    branches = 3
                    depth = 7
                elif p.fractal_type == 3: # リボンは1本道ベースなので分岐数を減らす
                    branches = 2
                    depth = 9
                
                for i in range(branches):
                    angle = p.move_angle + (i * 2 * math.pi / branches) + p.twist_factor
                    draw_fractal(screen, p.current_x, p.current_y, length, angle, depth, depth, hue_base, time_val, p.twist_factor, p.fractal_type)
            
        pygame.display.flip()
        clock.tick(60)

    cap.release()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
