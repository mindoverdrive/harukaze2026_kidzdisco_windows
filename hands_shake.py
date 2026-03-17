import cv2
import mediapipe as mp
import pygame
import display_utils
import numpy as np
import argparse
import socket
import json
import math
import random
import time

# --- コマンドライン引数と通信設定 ---
parser = argparse.ArgumentParser()
parser.add_argument("--wait", action="store_true", help="managerからのSTART信号を待つ")
parser.add_argument("--port", type=int, default=0, help="managerからの通信ポート")
args = parser.parse_args()

# --- 初期設定 ---
pygame.init()
info = pygame.display.Info()
screen_width, screen_height = info.current_w, info.current_h
screen, _pg_size = display_utils.setup_pygame_fullscreen()
pygame.display.set_caption("Harukaze 2026 - Hands Shake")
clock = pygame.time.Clock()

sock = None

# 通信待ち（manager.pyと連携するため）
if args.wait and args.port > 0:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.setblocking(False)
    print(f"[hands_shake] Waiting for START command on port {args.port}...")
    waiting = True
    while waiting:
        # Pygameイベント処理
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                exit()
        try:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode('utf-8'))
            if msg.get("cmd") == "START":
                print("[hands_shake] START Received!")
                waiting = False
        except BlockingIOError:
            pass
        except Exception as e:
            pass
        
        screen.fill((0, 0, 0))
        pygame.display.flip()
        pygame.time.wait(10)

# MediaPipe Hand Landmarkerの準備
mp_hands = mp.solutions.hands
# max_num_handsを10(5人の両手)に設定
hands = mp_hands.Hands(
    max_num_hands=10,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 描画色リスト（検出された手それぞれに割り当てる）
COLORS = [
    (255,   0,   0), # 赤
    (  0, 255,   0), # 緑
    (  0,   0, 255), # 青
    (255, 255,   0), # イエロー
    (255,   0, 255), # マゼンタ
    (  0, 255, 255), # シアン
    (255, 128,   0), # オレンジ
    (128,   0, 255), # パープル
    (  0, 255, 128), # ライム
    (255,   0, 128)  # ローズ
]

# OpenCVカメラの準備
cap = cv2.VideoCapture(3)
if not cap.isOpened():
    print("Cannot open camera")
    exit()

# UDP 受信準備 (managerからSTOPが来る用)
if sock and args.port > 0:
    sock.setblocking(False)
elif not sock and args.port > 0:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.setblocking(False)

# トラッキング用の状態変数 (ID管理)
# [{'track_id': int, 'cx': int, 'cy': int, 'last_seen': time, 'color': (R,G,B)}, ...]
active_hands_tracking = []
next_track_id = 0
TRACK_TIMEOUT = 1.0 # 手を見失っても1秒間は記憶を保持
TRACK_MAX_DIST = 150 # このピクセル距離以内なら同じ手とみなす

# 広がり続ける永続グロー背景用の変数
global_glow_color = (0, 0, 0)
global_glow_alpha = 0.0

# メインループ
running = True
while running:
    current_time = time.time()

    # イベント処理
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    # managerからのSTOP信号処理など
    if sock and args.port > 0:
        try:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode('utf-8'))
            if msg.get("cmd") == "STOP":
                running = False
        except BlockingIOError:
            pass
        except Exception:
            pass

    # カメラからフレームを取得
    success, image = cap.read()
    if not success:
        print("Ignoring empty camera frame.")
        continue

    # 画像を左右反転し、色をBGRからRGBに変換
    image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)

    # MediaPipeで処理
    image.flags.writeable = False
    results = hands.process(image)
    image.flags.writeable = True

    # --- 手のランドマーク座標の抽出とペア判定 ---
    current_frame_hands = []
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            wrist = hand_landmarks.landmark[0]
            cx, cy = int(wrist.x * screen_width), int(wrist.y * screen_height)
            
            # MediaPipeの二重検出（同じ物理的な手を2つとして誤認する現象）を排除する
            # すでに追加された手と極端に近い（100px以内）場合は、同じ手とみなして無視する
            is_duplicate = False
            for existing_hand in current_frame_hands:
                dist = np.sqrt((cx - existing_hand['cx'])**2 + (cy - existing_hand['cy'])**2)
                if dist < 100:
                    is_duplicate = True
                    break
                    
            if not is_duplicate:
                current_frame_hands.append({
                    'cx': cx, 'cy': cy, 'landmarks': hand_landmarks
                })

    # 1. 既存のトラッキング情報とのマッチング処理
    new_tracking = []
    
    # 距離ベースで現在の手と過去のトラックを紐付け
    # 最近まで見えていたトラックを優先的にマッチング
    active_hands_tracking = [t for t in active_hands_tracking if current_time - t['last_seen'] < TRACK_TIMEOUT]
    
    # 今回のフレームで既に使われたトラックIDを記録
    used_track_ids = set()

    for curr_hand in current_frame_hands:
        best_match = None
        best_dist = float('inf')
        
        for track in active_hands_tracking:
            if track['track_id'] in used_track_ids:
                continue
            dist = np.sqrt((curr_hand['cx'] - track['cx'])**2 + (curr_hand['cy'] - track['cy'])**2)
            if dist < best_dist and dist < TRACK_MAX_DIST:
                best_dist = dist
                best_match = track
                
        if best_match:
            best_match['cx'] = curr_hand['cx']
            best_match['cy'] = curr_hand['cy']
            best_match['last_seen'] = current_time
            best_match['frames_seen'] += 1
            used_track_ids.add(best_match['track_id'])
            
            new_tracking.append({
                'track_id': best_match['track_id'],
                'cx': curr_hand['cx'],
                'cy': curr_hand['cy'],
                'landmarks': curr_hand['landmarks'],
                'color': best_match['color'],
                'frames_seen': best_match['frames_seen']
            })
        else:
            color = COLORS[next_track_id % len(COLORS)]
            new_track = {
                'track_id': next_track_id,
                'cx': curr_hand['cx'],
                'cy': curr_hand['cy'],
                'last_seen': current_time,
                'color': color,
                'frames_seen': 1
            }
            active_hands_tracking.append(new_track)
            used_track_ids.add(next_track_id)
            
            new_tracking.append({
                'track_id': next_track_id,
                'cx': curr_hand['cx'],
                'cy': curr_hand['cy'],
                'landmarks': curr_hand['landmarks'],
                'color': color,
                'frames_seen': 1
            })
            next_track_id += 1

    hand_positions = new_tracking

    # === 空間ベースの握手判定 ===
    # ゴースト（見失った手）での自己衝突を防ぐため、物理的に見えている hand_positions 同士でのみ判定
    SHAKE_THRESHOLD = 200 # 少し広く。完全に重なって見失うより「少し手前」で発動判定させる
    current_overlapping_centers = []

    for i in range(len(hand_positions)):
        for j in range(i + 1, len(hand_positions)):
            h1 = hand_positions[i]
            h2 = hand_positions[j]
            dist = np.sqrt((h1['cx'] - h2['cx'])**2 + (h1['cy'] - h2['cy'])**2)
            
            if dist < SHAKE_THRESHOLD:
                if h1['frames_seen'] > 5 and h2['frames_seen'] > 5:
                    center_x = (h1['cx'] + h2['cx']) / 2
                    center_y = (h1['cy'] + h2['cy']) / 2
                    current_overlapping_centers.append({
                        'h1': h1, 'h2': h2, 'cx': center_x, 'cy': center_y, 'dist': dist
                    })

    hearts_to_draw = []

    # 新しく見つかった重なりごとの処理
    for overlap in current_overlapping_centers:
        cx = overlap['cx']
        cy = overlap['cy']
        
        # 既存のアニメーション中（再生中のハート）のエリアかチェック
        matched_anim = False
        if hasattr(hands, 'heart_animations'):
            for key, anim in hands.heart_animations.items():
                anim_cx, anim_cy = anim['center']
                area_dist = np.sqrt((cx - anim_cx)**2 + (cy - anim_cy)**2)
                # 現在アニメーション中の場所なら新規発動をブロックする（エリア維持）
                if area_dist < SHAKE_THRESHOLD:
                    matched_anim = True
                    break
                
        if not matched_anim:
            # どのアニメーションにも属さない完全新規の握手！
            hearts_to_draw.append(overlap)

    # OpenCVの画像をPygameのサーフェスに変換 (背景として使う)
    image = np.rot90(image)
    image = pygame.surfarray.make_surface(image)
    image = pygame.transform.flip(image, True, False)

    # カメラ映像をフルスクリーンサイズに合わせる
    image = pygame.transform.scale(image, (screen_width, screen_height))

    # 背景にカメラ映像を毎回上書き
    screen.blit(image, (0, 0))

    # --- 永続グロー効果のブレンド背景描画 ---
    # アニメーション進行に合わせて広がり、画面全体に残る
    if global_glow_alpha > 0.0:
        bg_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
        bg_surface.fill((*global_glow_color, int(min(255, max(0, global_glow_alpha)))))
        screen.blit(bg_surface, (0, 0))

    # --- 描画処理 (Pygame上で行う) ---
    
    # アニメーション状態の管理 (ループ外に定義するか、辞書で簡易管理)
    if not hasattr(hands, 'heart_animations'):
        hands.heart_animations = {}
        hands.anim_counter = 0

    # 新規アニメーションの登録
    for heart in hearts_to_draw:
        hands.anim_counter += 1
        str_key = str(hands.anim_counter)
        mixed = tuple(int((heart['h1']['color'][c] + heart['h2']['color'][c])/2) for c in range(3))
        
        hands.heart_animations[str_key] = {
            'start_time': current_time,
            'center': (heart['cx'], heart['cy']),
            'h1_color': heart['h1']['color'],
            'h2_color': heart['h2']['color'],
            'mixed_color': mixed
        }

    # 1. 骨格の描画 (独立手は元の色、合体エリア内は白で描画)
    for h in hand_positions:
        draw_color = h['color']
        
        # この手が現在アクティブなハートアニメーションのどれかに含まれているか確認
        in_active_anim = False
        if hasattr(hands, 'heart_animations'):
            for key, anim in hands.heart_animations.items():
                anim_cx, anim_cy = anim['center']
                dist = np.sqrt((h['cx'] - anim_cx)**2 + (h['cy'] - anim_cy)**2)
                # アニメーションの中心から一定距離内にあれば白くする
                if dist < SHAKE_THRESHOLD:
                    in_active_anim = True
                    break
                
        if in_active_anim:
            draw_color = (255, 255, 255) # エフェクト発動エリア内の骨格が白く輝く
                
        # OpenCVイメージ上で描画する代わりにPygameで直接描画
        for lm in h['landmarks'].landmark:
            px, py = int(lm.x * screen_width), int(lm.y * screen_height)
            pygame.draw.circle(screen, draw_color, (px, py), 5)
        # ボーンの描画
        for connection in mp_hands.HAND_CONNECTIONS:
            start_idx, end_idx = connection
            lm_start = h['landmarks'].landmark[start_idx]
            lm_end = h['landmarks'].landmark[end_idx]
            px1, py1 = int(lm_start.x * screen_width), int(lm_start.y * screen_height)
            px2, py2 = int(lm_end.x * screen_width), int(lm_end.y * screen_height)
            pygame.draw.line(screen, draw_color, (px1, py1), (px2, py2), 3)

    # アニメーションの描画と消去処理
    keys_to_remove = []
    
    # 現在アクティブな全アニメーションの最大進行度(0.0~1.0)を見つける
    # これを使ってグロー背景を滑らかに広げる
    max_active_progress = 0.0
    target_glow_color = global_glow_color
    
    for pair_key_str, anim_data in hands.heart_animations.items():
        # ペアが物理的に離れても、アニメーション自体は2秒間完走させる
        elapsed = current_time - anim_data['start_time']
        
        if elapsed > 2.0:
            keys_to_remove.append(pair_key_str)
            continue

        progress = min(1.0, elapsed / 2.0) # 0.0(開始) -> 1.0(終了)
        if progress > max_active_progress:
            max_active_progress = progress
            target_glow_color = anim_data['mixed_color']

        cx, cy = anim_data['center']
        h1_color = anim_data['h1_color']
        h2_color = anim_data['h2_color']
        
        mixed_color = tuple(int((h1_color[c] + h2_color[c])/2) for c in range(3))
        
        # --- ここからリッチなハートの描画 ---
        # 最初の0.3秒で枠線(周縁)を素早くグルッと描画し、その後脈動を開始
        border_duration = 0.3
        is_drawing_border = elapsed <= border_duration
        
        if is_drawing_border:
            # 枠線を描いている間は脈動させず、サイズも固定
            heartbeat = 0
            current_base = 12.0
        else:
            # 枠線を描き終えたらドクンドクンの脈動を開始し、徐々に全体が広がる
            heartbeat = math.sin((elapsed - border_duration) * 15) * 0.15
            current_base = 12.0 + ((elapsed - border_duration) * 8.0)
            
        final_scale = current_base + (current_base * heartbeat)
        
        # アルファフェード (0秒~2秒)
        alpha = int(max(0, 255 * (1.0 - (elapsed / 2.0))))
        if alpha == 0:
            continue
            
        heart_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
        
        # ハートの色を「もっと濃く」目立たせるための独自の強い色変換
        def make_dense_color(c):
            # 色味が潰れないように明るさ(RGB値)を少し底上げする
            return (min(255, int(c[0] * 1.5)), min(255, int(c[1] * 1.5)), min(255, int(c[2] * 1.5)))
            
        h1_dense = make_dense_color(h1_color)
        h2_dense = make_dense_color(h2_color)
        mixed_dense = make_dense_color(mixed_color)
        
        # 1. 輪郭と内部のポイント計算
        num_border_points = 180
        num_inner_points = 350 # 中身の点数も増やして濃さを出す
        points_to_draw = []
        
        # 輪郭ポイント (時間経過とともに描画する点の数を増やし、グルッと１周させる)
        draw_ratio = min(1.0, elapsed / border_duration)
        border_draw_count = int(num_border_points * draw_ratio)
        
        for i in range(border_draw_count):
            t = (i / num_border_points) * math.pi * 2
            hx = 16 * math.sin(t)**3
            hy = 13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)
            
            wobble_x = math.sin(t * 10 + current_time * 15) * 2
            wobble_y = math.cos(t * 10 + current_time * 15) * 2
            
            target_x = cx + hx * final_scale + wobble_x
            target_y = cy - hy * final_scale + wobble_y
            
            color = h2_dense if hx >= 0 else h1_dense
            points_to_draw.append((int(target_x), int(target_y), color, 8, 1.0))
            
        # 内部ポイント（枠線を描画し終えてから出現）
        if not is_drawing_border:
            # 内部は0.2秒かけてフワッとフェードインする
            inner_alpha_ratio = min(1.0, (elapsed - border_duration) / 0.2)
            for _ in range(num_inner_points):
                t = random.uniform(0, math.pi * 2)
                r = math.sqrt(random.uniform(0.1, 0.9)) 
                hx = 16 * math.sin(t)**3 * r
                hy = (13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)) * r
                target_x = cx + hx * final_scale
                target_y = cy - hy * final_scale
                color = h2_dense if hx >= 0 else h1_dense
                points_to_draw.append((int(target_x), int(target_y), color, 5, inner_alpha_ratio))

        # グローバルな光彩 (ハート中心の大きな後光。これも枠の後に現れる)
        if not is_drawing_border:
            pygame.draw.circle(heart_surface, (*mixed_dense, int(alpha * 0.15)), (int(cx), int(cy - 20*final_scale)), int(25 * final_scale), 0)

        # 全ポイントを描画 (アルファを少し高めに保って濃く見せる)
        for px, py, color, radius_size, inner_alpha_ratio in points_to_draw:
            point_alpha = int(alpha * inner_alpha_ratio)
            # 濃くするためメインの点をはっきりと描画
            pygame.draw.circle(heart_surface, (*color, point_alpha), (px, py), radius_size)
            # 周りが霞みすぎないように少し不透明度を高めにしてぼんやり描画
            pygame.draw.circle(heart_surface, (*color, int(point_alpha * 0.5)), (px, py), int(radius_size * 1.5))
            
        # キラキラパーティクル (枠線を描き終えてから一緒に飛び出す)
        if not is_drawing_border:
            inner_alpha_ratio = min(1.0, (elapsed - border_duration) / 0.2)
            for _ in range(30):
                t = random.uniform(0, math.pi * 2)
                r = math.sqrt(random.uniform(0.0, 1.2))
                hx = 16 * math.sin(t)**3 * r
                hy = (13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)) * r
                target_x = int(cx + hx * final_scale)
                target_y = int(cy - hy * final_scale)
                pygame.draw.circle(heart_surface, (255, 255, 255, int(alpha * inner_alpha_ratio)), (target_x, target_y), 3)

        screen.blit(heart_surface, (0, 0))

    # 全画面背景グローのアニメーション更新
    if max_active_progress > 0.0:
        # 新しい色が来たら徐々に色を変える
        global_glow_color = (
            int(global_glow_color[0] + (target_glow_color[0] - global_glow_color[0]) * 0.02),
            int(global_glow_color[1] + (target_glow_color[1] - global_glow_color[1]) * 0.02),
            int(global_glow_color[2] + (target_glow_color[2] - global_glow_color[2]) * 0.02)
        )
        # 広がり（アルファ）は最大進行度に合わせて上昇させ、最大で100(半透明)くらいで固定
        target_alpha = max_active_progress * 130 
        if target_alpha > global_glow_alpha:
            global_glow_alpha = target_alpha

    # 終了したアニメーションを削除
    for k in keys_to_remove:
        del hands.heart_animations[k]

    pygame.display.flip()

    # フレームレートの設定
    clock.tick(60)

# 終了処理
cap.release()
hands.close()
pygame.quit()
