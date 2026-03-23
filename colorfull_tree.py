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
import atexit
import pygame
import display_utils
import math
import cv2
import mediapipe as mp

# MediaPipe Hands の初期化
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, 
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Webcam の初期化 (環境に合わせて 0, 1, 2 などを調整してください)
cap = display_utils.open_camera()
def _cleanup():
    try:
        hands.close()
    except Exception:
        pass
    try:
        cap.release()
    except Exception:
        pass
    try:
        pygame.quit()
    except Exception:
        pass


atexit.register(_cleanup)


pygame.init()
screen, _pg_size = display_utils.setup_pygame_fullscreen()
w, h = screen.get_size()
clock = pygame.time.Clock()


# ─── 指の本数を検出するヘルパー関数 ───
def count_raised_fingers(hand_landmarks):
    """MediaPipeのランドマークから立っている指の本数を返す（1〜5）"""
    tips = [4, 8, 12, 16, 20]       # 各指の先端
    pips = [3, 6, 10, 14, 18]       # 各指の第二関節（親指はIP）

    count = 0

    # 1. 親指の判定をより厳密に
    # 親指先端(4)と人差し指の付け根(5)のx距離が離れていれば立っているとみなす（簡易版より精度UP）
    thumb_tip = hand_landmarks.landmark[4]
    index_mcp = hand_landmarks.landmark[5]
    wrist = hand_landmarks.landmark[0]
    middle_mcp = hand_landmarks.landmark[9]
    
    # 手の向き（手のひら側か甲側か）
    hand_dir_x = middle_mcp.x - wrist.x
    
    if hand_dir_x > 0: # 右手系
        # しきい値を下げて、少しでも開いていれば（立っていれば）検出するように
        if thumb_tip.x > index_mcp.x + 0.01: count += 1
    else: # 左手系
        if thumb_tip.x < index_mcp.x - 0.01: count += 1

    # 2. 人差し指〜小指: tip が pip より上（y が小さい）なら立っている
    for i in range(1, 5):
        if hand_landmarks.landmark[tips[i]].y < hand_landmarks.landmark[pips[i]].y:
            count += 1

    # 本数を0〜5本に制限
    return max(0, min(5, count))

def get_raised_fingers_dict(hand_landmarks, w, h):
    """MediaPipeのランドマークから立っている指の辞書 {インデックス: (x, y)} を返す"""
    tips = [4, 8, 12, 16, 20]
    pips = [3, 6, 10, 14, 18]
    wrist = hand_landmarks.landmark[0]
    middle_mcp = hand_landmarks.landmark[9]
    hand_dir_x = middle_mcp.x - wrist.x
    
    raised = {}
    
    # 1. 親指
    thumb_tip = hand_landmarks.landmark[4]
    index_mcp = hand_landmarks.landmark[5]
    
    if hand_dir_x > 0: # 右手系
        if thumb_tip.x > index_mcp.x + 0.01:
            raised[0] = (int(thumb_tip.x * w), int(thumb_tip.y * h))
    else: # 左手系
        if thumb_tip.x < index_mcp.x - 0.01:
            raised[0] = (int(thumb_tip.x * w), int(thumb_tip.y * h))
            
    # 人差し指 (1 = tips[1])
    if hand_landmarks.landmark[tips[1]].y < hand_landmarks.landmark[pips[1]].y:
        tip = hand_landmarks.landmark[tips[1]]
        raised[1] = (int(tip.x * w), int(tip.y * h))
            
    return raised



# ─── 指の本数ごとのパラメータ定義 ───
# (spread_multiplier, branch_ratio, max_depth)
# 1本目での広がり（spread_multiplier）は一定にし、深さ（max_depth）のみを変化させる
# 本数が増えるほど細かく（depthが深く）なる
FINGER_PARAMS = {
    0: (0.7, 0.75, 7),    
    1: (0.7, 0.75, 8),    
    2: (0.7, 0.75, 9),   
    3: (0.7, 0.75, 10),   
    4: (0.7, 0.75, 11),   
    5: (0.7, 0.75, 12),
}


# ─── スムーズ補間用の現在値 ───
current_spread_mult = 0.55   # 初期値（2本相当）
current_branch_ratio = 0.76
current_max_depth = 10.0
LERP_SPEED = 3.0   # 補間の速さ（大きいほど速く追従）


def lerp(current, target, speed, dt):
    """線形補間（なだらかなアニメーション）"""
    diff = target - current
    step = speed * dt
    if abs(diff) < 0.001:
        return target
    return current + diff * min(step, 1.0)

def lerp2d(current_pos, target_pos, speed, dt):
    """2D座標用の線形補間"""
    x = lerp(current_pos[0], target_pos[0], speed, dt)
    y = lerp(current_pos[1], target_pos[1], speed, dt)
    return (int(x), int(y))


def draw_tree(x, y, angle, depth, length, color_hue, base_spread_angle, branch_ratio, path, finger_targets, primary_side=""):
    if depth <= 0:
        return

    # 通常の次の角度（指定がなければこれを中心に広がる）
    current_angle = angle
    # このノードの動的な広がり角へのスケール値
    spread_scale = 1.0

    target_pos = finger_targets.get(path)
    
    if target_pos:
        tx, ty = target_pos
        dx = tx - x
        dy = -(ty - y) # Y軸下向きを反転
        dist = math.hypot(dx, dy)
        
        if dist > 0.1:
            # 枝の先端を指の位置(tx, ty)に完全に一致させる
            current_angle = math.atan2(dy, dx)
            
            # 元々の想定長さ（length）と比較して、どれだけ引き伸ばされたか
            # この比率を使って、その先の子枝の広がり幅や長さを調整する
            spread_scale = max(0.2, dist / (length + 1e-6))
            length = dist # 指先に完全に追随

    x2 = x + math.cos(current_angle) * length
    y2 = y - math.sin(current_angle) * length

    color = pygame.Color(0)
    # 左右の色を反転（パスの最初がLかRかで色味を変える）
    final_hue = color_hue
    if path.startswith("L"):
        final_hue = (color_hue + 180) % 360
    
    color.hsva = (final_hue % 360, 100, 100, 100)

    thickness = max(1, int(depth * 1.2))
    pygame.draw.line(screen, color, (x, y), (x2, y2), thickness)

    # 割り当てられた指先の視覚的表現（完全な白点）
    # 鏡写しになった方（非操作側）のドットは表示しない
    if target_pos and path.startswith(primary_side):
        pygame.draw.circle(screen, (255, 255, 255), target_pos, 8, 0)

    new_len = length * branch_ratio
    
    # 実際の広がり角（距離に応じたスケーリングを反映）
    actual_spread = base_spread_angle * spread_scale
    
    # ターゲットに向けて曲がった角度(current_angle)を基準にして、次の枝を広げる。
    # 増分を全体的に小さくしてグラデーションをなだらかにし、左右の増分差を広げてズレを大きくする
    draw_tree(x2, y2, current_angle - actual_spread, depth - 1, new_len, color_hue + 2, base_spread_angle, branch_ratio, path + "L", finger_targets, primary_side)
    draw_tree(x2, y2, current_angle + actual_spread, depth - 1, new_len, color_hue + 18, base_spread_angle, branch_ratio, path + "R", finger_targets, primary_side)


running = True

# 初期位置
mx, my = w // 2, h // 2
detected_fingers = 2  # 初期値

# ─── ターゲット座標のなだらかな補間用状態保持 ───
smooth_targets = {}
TARGET_LERP_SPEED = 5.0

while running:
    dt = clock.get_time() / 1000.0  # 前フレームからの経過秒数
    screen.fill((0, 0, 0))
    
    finger_targets = {}
    base_path = "" # 手2がいない場合のデフォルト

    # 初期値
    target_spread, target_ratio, target_depth = FINGER_PARAMS[2]

    # カメラから映像を取得
    ret, frame = cap.read()

    if ret:
        # 鏡面効果のために水平反転し、RGBに変換
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # MediaPipeで手を処理
        results = hands.process(rgb_frame)

        if results.multi_hand_landmarks:
            hands_list = list(results.multi_hand_landmarks)
            
            # 手をX座標でソート（常に左側にある手がインデックス0、右側がインデックス1になるように）
            hands_list.sort(key=lambda hand: hand.landmark[0].x)
            
            # 左側の手（画面左）を木の基本制御（手1）とする
            hand1 = hands_list[0]
            detected_fingers = count_raised_fingers(hand1)
            target_spread, target_ratio, target_depth = FINGER_PARAMS[detected_fingers]

            # 2本目の手（枝先の操作制御）
            if len(hands_list) > 1:
                hand2 = hands_list[1]
                hand2_raised = get_raised_fingers_dict(hand2, w, h)
                
                # 手首もターゲットとして扱う
                wrist = hand2.landmark[0]
                hand2_raised[-1] = (int(wrist.x * w), int(wrist.y * h))
                
                # 1本目の手と比べて左右どちらにいるかで判定する
                is_right_side = (wrist.x > hand1.landmark[0].x)
                
                if is_right_side:
                    base_path = "R"
                    mirror_path = "L"
                else:
                    base_path = "L"
                    mirror_path = "R"
                
                # 今回は手首(-1)と親指(0)、人差し指(1)のみを使用する
                FINGER_PATH_MAPPING = {
                    -1: base_path,        # 手首 -> 2番目の枝分かれ ("R" or "L")
                    0:  base_path + "L",  # 親指 -> R(L)の左
                    1:  base_path + "R"   # 人差し指 -> R(L)の右
                }
                
                for f_idx, pos in hand2_raised.items():
                    if f_idx in FINGER_PATH_MAPPING:
                        primary_path = FINGER_PATH_MAPPING[f_idx]
                        finger_targets[primary_path] = pos
                        
                        # ミラー座標の計算 (画面中央 w/2 を軸に反転)
                        mx = w - pos[0]
                        my = pos[1]
                        
                        # パスの文字 'R' と 'L' を反転させてミラーパスを作成
                        mirrored_path_str = ""
                        for char in primary_path:
                            if char == 'R': mirrored_path_str += 'L'
                            elif char == 'L': mirrored_path_str += 'R'
                        
                        finger_targets[mirrored_path_str] = (mx, my)

    # ─── ターゲット座標のなだらか補間処理 ───
    # 現在の辞書(smooth_targets)を、今回取得したターゲット(finger_targets)に向けて補間
    # フェードアウト処理を廃止したため、見失ったターゲットは永遠にそのままの座標を保持し続ける
    current_paths = list(smooth_targets.keys())
    for path in current_paths:
        if path in finger_targets:
            # 継続して検出されている場合は目標へなだらかに移動
            smooth_targets[path] = lerp2d(smooth_targets[path], finger_targets[path], TARGET_LERP_SPEED, dt)
                
    # 新規に検出されたターゲットを登録
    for path, pos in finger_targets.items():
        if path not in smooth_targets:
            smooth_targets[path] = pos  # 初回は直接代入

    # ─── なだらかに補間（アニメーション） ───
    current_spread_mult = lerp(current_spread_mult, target_spread, LERP_SPEED, dt)
    current_branch_ratio = lerp(current_branch_ratio, target_ratio, LERP_SPEED, dt)
    current_max_depth = lerp(current_max_depth, float(target_depth), LERP_SPEED, dt)

    # 基本の広がりを計算
    base_spread = (math.pi / 2) * current_spread_mult
    time_ticks = pygame.time.get_ticks()
    start_hue = (time_ticks / 20) % 360  # 時間経過で色が回転
    start_len = h / 4.5

    draw_tree(w // 2, h, math.pi / 2, int(current_max_depth), start_len,
              start_hue, base_spread, current_branch_ratio, "", smooth_targets, base_path)

    # ─── 画面表示: 現在の指の本数 ───
    font = pygame.font.SysFont(None, 48)
    # 本数を 1-5 の表記で表示
    display_count = detected_fingers
    text_surface = font.render(f"FINGERS = <{display_count}>", True, (255, 255, 255))
    screen.blit(text_surface, (30, 30))

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False

    pygame.display.flip()
    clock.tick(60)

