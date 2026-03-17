#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import cv2
import pygame
import random
import math
import mediapipe as mp

# ===============================
# 定数
# ===============================
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

# 日本語フォント設定
def get_japanese_font(size=30):
    """macOS用の日本語フォント取得"""
    font_paths = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Hiragino Sans W3.ttc",
    ]
    for font_path in font_paths:
        try:
            return pygame.font.Font(font_path, size)
        except:
            continue
    # フォントが見つからない場合
    return pygame.font.Font(None, size)

class Snake:
    def __init__(self):
        self.body = [(100, SCREEN_HEIGHT - 100)]
        self.speed = 3.0
        self.base_speed = 3.0
        self.current_level = 1  # スピードレベル（表記用）
        self.max_speed = 12.0
        self.time_counter = 0  # For wavy movement
        self.max_length = 150  # より長い蛇
        self.powerup_time = 0  # パワーアップエフェクト用

    
    def update(self, target_pos, obstacles, elapsed_time):
        # 10秒ごとにレベルアップ（初期表記は1）
        level = int(elapsed_time // 10) + 1
        if level > self.current_level:
            self.current_level = level
            self.powerup_time = 30  # パワーアップエフェクト期間
            self.speed = self.base_speed + (self.current_level - 1)  # 3 + (level-1)
        else:
            self.speed = self.base_speed + (self.current_level - 1)
        
        head_x, head_y = self.body[0]
        
        # ターゲットに向かうベクトル
        dx = target_pos[0] - head_x
        dy = target_pos[1] - head_y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance > 0:
            dx = dx / distance
            dy = dy / distance
        
        # うねり動作 (Sine wave)
        self.time_counter += 1
        wavy_strength = 25  # より強いうねり
        wavy_speed = 0.15   # 速さ
        
        # 進行方向に対して垂直なベクトルを計算
        perp_dx = -dy
        perp_dy = dx
        
        # サイン波オフセット
        wave_offset = math.sin(self.time_counter * wavy_speed) * wavy_strength
        
        # 基本移動ベクトル + うねり
        next_x = head_x + dx * self.speed + perp_dx * wave_offset * 0.1
        next_y = head_y + dy * self.speed + perp_dy * wave_offset * 0.1
        
        new_head = (int(next_x), int(next_y))
        
        # 画面外を許容
        new_head = (
            max(-500, min(SCREEN_WIDTH + 500, new_head[0])),
            max(-500, min(SCREEN_HEIGHT + 500, new_head[1]))
        )
        
        self.body.insert(0, new_head)
        if len(self.body) > self.max_length:
            self.body.pop()
    
    def check_collision_self(self):
        # 自分の体との衝突（頭が体の一部に触れる）
        # 完全に重なると即死するので、ある程度進んでから判定
        if len(self.body) < 20: 
            return False
            
        head = self.body[0]
        # 頭に近い部分は除外
        for segment in self.body[20:]:
            dist = math.sqrt((head[0] - segment[0])**2 + (head[1] - segment[1])**2)
            if dist < 10:
                return True
        return False
    
    def draw(self, surface):
        # パワーアップ中は蛇の形を大胆に変える
        is_powerup = self.powerup_time > 0
        
        for i, (x, y) in enumerate(self.body):
            # Rainbow/Neon colors using HSV
            if is_powerup:
                # パワーアップ中は高速で色が変わる虹色
                hue = (self.time_counter * 5 + i * 10) % 360
            else:
                hue = (self.time_counter * 2 + i * 5) % 360
            
            color = pygame.Color(0)
            color.hsva = (hue, 100, 100, 100)
            
            # パワーアップ中は大きくなったり形が変わる
            if is_powerup:
                # サイズが変動
                pulse = math.sin(self.powerup_time * 0.3) * 3 + 3
                radius = 8 + pulse
            else:
                radius = 8
            
            # Head is larger
            if i == 0:
                if is_powerup:
                    radius = 15 + math.sin(self.powerup_time * 0.3) * 4
                else:
                    radius = 12
            
            # パワーアップ中はスター形状
            if is_powerup and i < len(self.body) // 3:
                # スター形状を描画
                self._draw_star(surface, (x, y), int(radius), color)
            else:
                pygame.draw.circle(surface, color, (x, y), int(radius))
        
        if len(self.body) > 0:
            eye_x, eye_y = self.body[0]
            pygame.draw.circle(surface, (255, 255, 255), (eye_x - 4, eye_y - 4), 4)
            pygame.draw.circle(surface, (255, 255, 255), (eye_x + 4, eye_y - 4), 4)
    
    def _draw_star(self, surface, center, size, color):
        """スター形状を描画"""
        cx, cy = center
        points = []
        for i in range(10):
            angle = i * math.pi / 5
            if i % 2 == 0:
                r = size
            else:
                r = size * 0.4
            x = cx + r * math.sin(angle)
            y = cy - r * math.cos(angle)
            points.append((x, y))
        if len(points) >= 3:
            pygame.draw.polygon(surface, color, points)


class FloatingText:
    def __init__(self, x, y, text, color=(255, 255, 100)):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = 60
        self.y_speed = -2
        self.size = 40
    
    def update(self):
        self.y += self.y_speed
        self.life -= 1
        return self.life > 0
    
    def draw(self, surface, font):
        # Bounce/Pop effect
        scale = 1.0
        if self.life > 50:
            scale = 1.0 + (60 - self.life) * 0.1
        
        # Alpha fade
        alpha = min(255, self.life * 5)
        
        # Render text
        text_surf = font.render(self.text, True, self.color)
        text_surf.set_alpha(alpha)
        
        # Scale
        if scale != 1.0:
            w = int(text_surf.get_width() * scale)
            h = int(text_surf.get_height() * scale)
            text_surf = pygame.transform.scale(text_surf, (w, h))
            
        rect = text_surf.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(text_surf, rect)

class Spark:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(2, 6)
        self.life = 255
        self.decay = random.uniform(5, 15)
        self.color = color
        self.size = random.uniform(2, 5)

    def update(self):
        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed
        self.life -= self.decay
        return self.life > 0

    def draw(self, surface):
        if self.life > 0:
            alpha_color = (*self.color, int(self.life))
            s = pygame.Surface((int(self.size*2), int(self.size*2)), pygame.SRCALPHA)
            pygame.draw.circle(s, alpha_color, (int(self.size), int(self.size)), int(self.size))
            surface.blit(s, (int(self.x - self.size), int(self.y - self.size)))

class Obstacle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = random.randint(15, 30)
        self.type = random.choice(['circle', 'rect', 'triangle', 'capsule', 'curve'])  # 形状ランダム
        self.color = (random.randint(150, 255), random.randint(50, 150), random.randint(50, 150))
        self.alpha = 0  # フェードイン用
        self.rotation = random.uniform(0, 360)
        self.rot_speed = random.uniform(-2, 2)
    
    def update(self):
        if self.alpha < 255:
            self.alpha = min(255, self.alpha + 5)
        self.rotation += self.rot_speed

    def collides(self, point):
        # 簡易的に円として判定（形状に関わらず）
        dist = math.sqrt((point[0] - self.x)**2 + (point[1] - self.y)**2)
        return dist < self.radius + 8
    
    def draw(self, surface):
        # アルファ合成のためにSurfaceを作成
        s = pygame.Surface((self.radius * 3, self.radius * 3), pygame.SRCALPHA)
        center = (self.radius * 1.5, self.radius * 1.5)
        
        # 色（アルファ適用）
        draw_color = (*self.color, int(self.alpha))
        border_color = (255, 200, 200, int(self.alpha))
        
        if self.type == 'circle':
            pygame.draw.circle(s, draw_color, center, self.radius)
            pygame.draw.circle(s, border_color, center, self.radius, 3)
        
        elif self.type == 'rect':
            rect = pygame.Rect(center[0] - self.radius, center[1] - self.radius, 
                               self.radius * 2, self.radius * 2)
            # 回転させるために少し工夫が必要だが、ここでは簡易的に
            pygame.draw.rect(s, draw_color, rect)
            pygame.draw.rect(s, border_color, rect, 3)
            
        elif self.type == 'triangle':
            points = [
                (center[0], center[1] - self.radius),
                (center[0] - self.radius, center[1] + self.radius),
                (center[0] + self.radius, center[1] + self.radius)
            ]
            pygame.draw.polygon(s, draw_color, points)
            pygame.draw.polygon(s, border_color, points, 3)
            
        elif self.type == 'capsule':
            # Pill shape
            rect = pygame.Rect(center[0] - self.radius, center[1] - self.radius * 0.5, 
                               self.radius * 2, self.radius)
            pygame.draw.rect(s, draw_color, rect, border_radius=int(self.radius*0.5))
            pygame.draw.rect(s, border_color, rect, 3, border_radius=int(self.radius*0.5))
            
        elif self.type == 'curve':
            # Arc shape (draw a few overlapping circles)
            for _ in range(3):
                offset = (_ - 1) * (self.radius * 0.5)
                c_pos = (center[0] + offset, center[1] + abs(offset)*0.5)
                pygame.draw.circle(s, draw_color, c_pos, self.radius * 0.6)
                pygame.draw.circle(s, border_color, c_pos, self.radius * 0.6, 2)
            
        # 回転後のSurfaceを描画
        rotated_s = pygame.transform.rotate(s, self.rotation)
        new_rect = rotated_s.get_rect(center=(self.x, self.y))
        surface.blit(rotated_s, new_rect.topleft)

# Helper function for line-circle collision
def get_line_circle_intersection(p1, p2, circle_center, radius):
    # p1: (x1, y1), p2: (x2, y2)
    x1, y1 = p1
    x2, y2 = p2
    cx, cy = circle_center
    
    dx = x2 - x1
    dy = y2 - y1
    
    # Vector from p1 to center
    fx = x1 - cx
    fy = y1 - cy
    
    # Quadratic equation: a*t^2 + b*t + c = 0
    a = dx*dx + dy*dy
    b = 2 * (fx*dx + fy*dy)
    c = (fx*fx + fy*fy) - radius*radius
    
    discriminant = b*b - 4*a*c
    
    if discriminant < 0:
        return None
    
    # Check for intersections
    discriminant = math.sqrt(discriminant)
    t1 = (-b - discriminant) / (2*a) if a != 0 else -1
    t2 = (-b + discriminant) / (2*a) if a != 0 else -1
    
    # We want the first intersection within 0 <= t <= 1
    # Prefer t1 since it's "entry" point usually
    if 0 <= t1 <= 1:
        return (int(x1 + t1*dx), int(y1 + t1*dy))
    if 0 <= t2 <= 1:
        return (int(x1 + t2*dx), int(y1 + t2*dy))
        
    return None


class VortexEffect:
    def __init__(self):
        self.radius = 0
        self.max_radius = math.sqrt(SCREEN_WIDTH**2 + SCREEN_HEIGHT**2)
        self.points = []
        self.colors = []
        for _ in range(100):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0, 1) # Normalized distance
            self.points.append({"angle": angle, "dist": dist, "speed": random.uniform(0.05, 0.1)})
            self.colors.append((random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)))
        self.animation_speed = 15
        self.active = False
        self.timer = 0
    
    def start(self):
        self.active = True
        self.radius = self.max_radius
        self.timer = 0
        
    def update(self):
        if not self.active:
            return False
            
        self.radius -= self.animation_speed
        self.timer += 1
        return self.radius > 0

    def draw(self, surface):
        if not self.active:
            return
            
        # 画面全体を徐々に塗りつぶす渦
        center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        
        # 背景を暗くする
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 10))
        surface.blit(overlay, (0, 0))
        
        current_radius = max(0, int(self.radius))
        pygame.draw.circle(surface, (0, 0, 0), center, current_radius)
        
        # 渦巻き粒子の描画 (装飾)
        for i, p in enumerate(self.points):
            p["angle"] += p["speed"]
            r = self.radius + p["dist"] * 500
            x = center[0] + math.cos(p["angle"]) * r
            y = center[1] + math.sin(p["angle"]) * r
            pygame.draw.circle(surface, self.colors[i], (int(x), int(y)), random.randint(2, 5))


class Button:
    def __init__(self, x, y, width, height, text):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
    
    def contains(self, point):
        px, py = point
        return (self.x <= px <= self.x + self.width and
                self.y <= py <= self.y + self.height)
    
    def draw(self, surface, font, is_hover=False):
        color = (150, 255, 150) if is_hover else (100, 200, 100)
        pygame.draw.rect(surface, color, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, (255, 255, 255), (self.x, self.y, self.width, self.height), 2)
        
        text_surface = font.render(self.text, True, (0, 0, 0))
        text_rect = text_surface.get_rect(
            center=(self.x + self.width // 2, self.y + self.height // 2)
        )
        surface.blit(text_surface, text_rect)


class SnakeGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Snake Finger Game")
        self.clock = pygame.time.Clock()
        
        # 日本語フォント設定
        self.font_large = get_japanese_font(80)
        self.font_medium = get_japanese_font(40)
        self.font_small = get_japanese_font(30)
        
        # MediaPipe初期化
        try:
            self.hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5
            )
        except Exception as e:
            print(f"MediaPipe初期化エラー: {e}")
            self.hands = None
        
        # カメラ初期化
        self.cap = cv2.VideoCapture(2)
        if not self.cap.isOpened():
            print("カメラが開けません")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, SCREEN_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SCREEN_HEIGHT)
        
        # ゲーム状態
        self.state = "MENU"  # MENU, PLAYING, GAME_OVER_EFFECT, GAME_OVER
        self.snake = None
        self.obstacles = []
        self.sparks = []  # 火花エフェクトリスト
        self.texts = []   # フローティングテキスト
        self.vortex = VortexEffect()
        self.score = 0
        self.display_score = 0  # アニメーション用表示スコア
        self.start_time = 0
        self.elapsed_time = 0
        self.finger_pos = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        self.prev_finger_pos = self.finger_pos # Previous frame position for collision
        self.last_spawn_time = 0
        self.button_touch_cooldown = 0
        self.game_start_cooldown = 0  # ゲーム開始直後の無敵時間
        self.game_over_start_tick = 0
        self.scroll_y = 0
        self.is_scrolling = False
        self.last_score = 0
        self.current_frame = None  # カメラフレーム保存用
        self.hand_landmarks = None  # 手の骨格情報保存用
        self.camera_area = None  # カメラ領域（衝突判定用）
        
        # ボタン
        self.start_button = Button(SCREEN_WIDTH - 150, 20, 130, 60, "START")
        self.restart_button = Button(SCREEN_WIDTH // 2 - 65, SCREEN_HEIGHT // 2 + 100, 130, 60, "RESTART")
    
    def detect_finger(self, frame):
        """指を検出"""
        if self.hands is None:
            self.hand_landmarks = None
            return (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(frame_rgb)
            
            finger_pos = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            self.hand_landmarks = None
            
            if results.multi_hand_landmarks:
                hand = results.multi_hand_landmarks[0]
                # 骨格情報を保存
                self.hand_landmarks = hand
                
                # 立っている指を検出
                fingers = [0] * 5
                
                # 親指
                if hand.landmark[4].x < hand.landmark[3].x:
                    fingers[0] = 1
                
                # その他の指
                for i in range(1, 5):
                    if hand.landmark[i * 4].y < hand.landmark[i * 4 - 2].y:
                        fingers[i] = 1
                
                # 最初に立っている指を取得
                for i, is_up in enumerate(fingers):
                    if is_up:
                        tip = hand.landmark[i * 4]
                        # 画面座標に変換
                        finger_pos = (
                            int(tip.x * SCREEN_WIDTH),
                            int(tip.y * SCREEN_HEIGHT)
                        )
                        break
            
            return finger_pos
        except Exception as e:
            self.hand_landmarks = None
            return None  # 検出失敗時はNoneを返す
    
    def spawn_obstacle(self, avoid_pos=None):
        """障害物を生成（避ける位置を指定可能）"""
        while True:
            x = random.randint(100, SCREEN_WIDTH - 100)
            y = random.randint(100, SCREEN_HEIGHT - 100)
            
            # 蛇の初期位置から十分離れているか確認
            if avoid_pos:
                dist = math.sqrt((x - avoid_pos[0])**2 + (y - avoid_pos[1])**2)
                if dist > 200:  # 200ピクセル以上離れていることを確認
                    break
            else:
                break
        
        self.obstacles.append(Obstacle(x, y))
    
    def start_game(self):
        self.state = "PLAYING"
        self.snake = Snake()
        self.obstacles = []
        self.sparks = []
        self.texts = []
        self.score = 0
        self.display_score = 0
        self.start_time = pygame.time.get_ticks()
        self.elapsed_time = 0
        self.last_spawn_time = 0
        self.button_touch_cooldown = 0
        self.game_start_cooldown = 60  # 60フレーム無敵（衝突判定なし）
        
        # 蛇から遠い位置に初期障害物を生成
        snake_init_pos = (100, SCREEN_HEIGHT - 100)
        for _ in range(3):
            self.spawn_obstacle(snake_init_pos)
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            # qキーで終了
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    return False
            
            # マウスクリック（デバッグ用）
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()
                
                if self.state == "MENU" and self.start_button.contains(mouse_pos):
                    self.button_touch_cooldown = 30
                    self.start_game()
                elif self.state == "GAME_OVER" and self.restart_button.contains(mouse_pos):
                    self.button_touch_cooldown = 30
                    self.start_game()
        
        # クールダウン処理（ボタン操作）
        if self.button_touch_cooldown > 0:
            self.button_touch_cooldown -= 1
            return True
        
        # 指でボタンをタッチ検出（クールダウン中は無視）
        if self.game_start_cooldown <= 0:
            if self.state == "MENU":
                if self.start_button.contains(self.finger_pos):
                    self.button_touch_cooldown = 30
                    self.start_game()
            elif self.state == "GAME_OVER":
                if self.restart_button.contains(self.finger_pos):
                    self.button_touch_cooldown = 30
                    self.start_game()
        
        return True
    
    def update(self):
        ret, frame = self.cap.read()
        if not ret:
            return
        
        frame = cv2.flip(frame, 1)
        # フレームをメンバー変数に保存（描画用）
        self.current_frame = frame
        
        # 指検出
        new_finger_pos = self.detect_finger(frame)
        if new_finger_pos is not None:
            self.prev_finger_pos = self.finger_pos
            self.finger_pos = new_finger_pos
        # Noneの場合は前回の self.finger_pos を維持
        
        if self.state == "PLAYING":
            # カメラ領域の初期化（初回）
            if self.camera_area is None:
                scale = 0.125
                frame_width = int(SCREEN_WIDTH * scale)
                frame_height = int(SCREEN_HEIGHT * scale)
                margin = 10
                self.camera_area = pygame.Rect(margin - 5, margin - 5, frame_width + 10, frame_height + 10)
            
            # 指がカメラ領域に入った場合、領域外に出す
            if self.camera_area.collidepoint(self.finger_pos):
                # 領域の右下に指を移動
                self.finger_pos = (self.camera_area.right + 10, self.camera_area.bottom + 10)
            
            # 指の物理衝突判定 (障害物を通れないようにする)
            # 現在位置と前回の位置を結ぶ線分が障害物(円と仮定)と交差するかチェック
            for obs in self.obstacles:
                intersect = get_line_circle_intersection(self.prev_finger_pos, self.finger_pos, (obs.x, obs.y), obs.radius + 10)
                if intersect:
                    # 衝突した場合、その位置で止める
                    self.finger_pos = intersect
                    # 補正後の位置を次のprevにするために少し戻す必要はないが、
                    # 連続衝突を防ぐためにわずかに押し戻すなどの処理も考えられる
                    # ここでは単純に交点にする
                    break

            # ゲーム開始クールダウンを減らす
            if self.game_start_cooldown > 0:
                self.game_start_cooldown -= 1
            
            self.elapsed_time = (pygame.time.get_ticks() - self.start_time) / 1000.0
            
            # 蛇更新
            self.snake.update(self.finger_pos, self.obstacles, self.elapsed_time)
            
            # スコア計算（基本スコアはすでに初期化済み、障害物加算は別途）
            self.score = max(self.score, int(self.elapsed_time * 10))
            
            # 障害物更新
            for obs in self.obstacles:
                obs.update()

            # 火花更新
            self.sparks = [s for s in self.sparks if s.update()]

            # テキスト更新
            self.texts = [t for t in self.texts if t.update()]

            # クールダウン中は衝突判定をスキップ
            if self.game_start_cooldown <= 0:
                # 指が蛇に触ったら終了
                for segment in self.snake.body[1:]:  # 頭以外の体をチェック
                    dx = self.finger_pos[0] - segment[0]
                    dy = self.finger_pos[1] - segment[1]
                    dist = math.sqrt(dx*dx + dy*dy)
                    if dist < 12:  # 指のサイズと蛇のセグメント
                        self.state = "GAME_OVER_EFFECT"
                        self.vortex.start()
                        return
                
                # 自分自身の衝突
                if self.snake.check_collision_self():
                    self.state = "GAME_OVER_EFFECT"
                    self.vortex.start()
                    return
                
                # 障害物との衝突 (スコアアップ & エフェクト)
                for obs in self.obstacles:
                    if obs.collides(self.snake.body[0]):
                        # 既知の衝突時間をチェックして連続ヒットを防ぐならここで処理が必要だが
                        # 今回はシンプルに毎回ヒットとして、派手にする
                        # ただし、フレームごとにヒットすると凄まじいので、障害物にクールダウンを持たせるか
                        # Snake側で無敵時間を持つか。
                        # ここでは簡易的に「障害物が消える」等の処理はしていないため、
                        # 連続ヒットしてスコアが爆増する可能性がある。
                        # ユーザー要望は「派手に」「スコアが上がる」なので、あえて連続ヒットさせるか、
                        # 1回ヒットしたら少しのインターバルを設ける。
                        # ここでは、エフェクトを派手にするため、確率は低くするがヒットはさせる。
                        pass # 実際のヒット処理は下に記述、本来はここですべき
                
                # 障害物判定（上記ループでまとめると多重ループになるので分けるか、
                # あるいは衝突した瞬間に何かする）
                head = self.snake.body[0]
                hit_obs_indices = []
                for i, obs in enumerate(self.obstacles):
                    if obs.collides(head):
                        # ヒット！障害物1個につき30ポイント
                        bonus = 30
                        self.score += bonus
                        
                        # テキスト
                        self.texts.append(FloatingText(head[0], head[1], f"+{bonus}"))
                        
                        # 火花発生
                        for _ in range(8):
                            self.sparks.append(Spark(obs.x, obs.y, (255, 200, 100)))
                        
                        # 障害物を再配置（消して新しいのを出すことで連続ヒット防ぐ）
                        hit_obs_indices.append(i)
                
                # ヒットした障害物を削除して新しく生成
                for i in sorted(hit_obs_indices, reverse=True):
                    self.obstacles.pop(i)
                    self.spawn_obstacle()
            
            # スコアアニメーション更新
            if self.display_score < self.score:
                diff = self.score - self.display_score
                self.display_score += max(1, diff // 10)
            
            # 障害物追加（時間に応じて）
            if int(self.elapsed_time) >= self.last_spawn_time + 3:
                if random.random() < 0.6:  # 少し出現頻度上げる
                    self.spawn_obstacle()
                    self.last_spawn_time = int(self.elapsed_time)
        
        elif self.state == "GAME_OVER_EFFECT":
            if not self.vortex.update():
                self.state = "GAME_OVER"
                self.game_over_start_tick = pygame.time.get_ticks()
                self.last_score = self.score
        
        elif self.state == "GAME_OVER":
            # 3秒待機してからスクロール開始
            now = pygame.time.get_ticks()
            if not self.is_scrolling and now - self.game_over_start_tick > 3000:
                self.is_scrolling = True
                self.scroll_y = 0
            
            if self.is_scrolling:
                self.scroll_y += 15 # スクロール速度
                if self.scroll_y >= SCREEN_HEIGHT:
                    self.state = "MENU"
                    self.is_scrolling = False
                    self.scroll_y = 0
    
    def draw_menu(self):
        title = self.font_large.render("Snake Finger Game", True, (255, 200, 100))
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 4))
        self.screen.blit(title, title_rect)
        
        # ルール表示（全てひらがな）
        instructions = [
            "〜 ゲーム ルール 〜",
            "ゆびを たてて、へびを うごかそう！",
            "じぶんの からだに あたったら おわり。",
            "しょうがいぶつに あたると、ぶつかって えっぷぷ。",
            "ながく いきのこって、スコアを かせごう！"
        ]
        
        y = SCREEN_HEIGHT // 2 - 20
        for instruction in instructions:
            color = (255, 255, 255) if "〜" in instruction else (200, 200, 200)
            text = self.font_small.render(instruction, True, color)
            text_rect = text.get_rect(center=(SCREEN_WIDTH // 2, y))
            self.screen.blit(text, text_rect)
            y += 40
        
        # 前回のスコア表示
        if self.last_score > 0:
            ls_text = self.font_medium.render(f"まえの スコア: {self.last_score}  Last Score: {self.last_score}", True, (100, 255, 255))
            ls_rect = ls_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 150))
            self.screen.blit(ls_text, ls_rect)
        
        # 指がボタンに触れているかで判定
        is_hover = self.start_button.contains(self.finger_pos)
        self.start_button.draw(self.screen, self.font_medium, is_hover)
        
        # 指の位置を表示
        pygame.draw.circle(self.screen, (100, 200, 255), self.finger_pos, 15, 2)
    
    def draw_game(self):
        # 障害物
        for obs in self.obstacles:
            obs.draw(self.screen)
            
        # 火花
        for spark in self.sparks:
            spark.draw(self.screen)
            
        # テキスト
        for text in self.texts:
            text.draw(self.screen, self.font_medium)
        
        # 蛇
        if self.snake:
            self.snake.draw(self.screen)
        
        # 指を目立つように囲む（大きく、複数の円で強調）
        # 外側の大きな円
        pygame.draw.circle(self.screen, (255, 100, 100), self.finger_pos, 25, 3)
        # 中間の円
        pygame.draw.circle(self.screen, (255, 150, 150), self.finger_pos, 18, 2)
        # 内側の円
        pygame.draw.circle(self.screen, (255, 200, 200), self.finger_pos, 12, 2)
        # 指先の中心を強調
        pygame.draw.circle(self.screen, (255, 50, 50), self.finger_pos, 8)
        # 十字マーク
        pygame.draw.line(self.screen, (255, 255, 0), (self.finger_pos[0] - 15, self.finger_pos[1]), (self.finger_pos[0] + 15, self.finger_pos[1]), 2)
        pygame.draw.line(self.screen, (255, 255, 0), (self.finger_pos[0], self.finger_pos[1] - 15), (self.finger_pos[0], self.finger_pos[1] + 15), 2)
        
        # スコア表示（日本語 + 英語）
        # 合計スコアをアニメーション的に表示
        score_text = self.font_medium.render(f"スコア: {self.display_score}  Score: {self.display_score}", True, (255, 255, 100))
        self.screen.blit(score_text, (20, 20))
        
        # 速度表示（日本語 + 英語）
        if self.snake:
            speed_text = self.font_small.render(f"はやさ: Lv.{self.snake.current_level}  Speed: Lv.{self.snake.current_level}", True, (100, 200, 255))
            self.screen.blit(speed_text, (20, 70))
    
    def draw_gameover(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(150)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        gameover = self.font_large.render("やったね!!", True, (255, 200, 100))
        gameover_rect = gameover.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3 - 30))
        self.screen.blit(gameover, gameover_rect)
        
        gameover_en = self.font_medium.render("Good Game!!", True, (200, 150, 255))
        gameover_en_rect = gameover_en.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3 + 30))
        self.screen.blit(gameover_en, gameover_en_rect)
        
        score_text = self.font_medium.render(f"スコア Score: {self.display_score}", True, (255, 255, 100))
        score_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        self.screen.blit(score_text, score_rect)
        
        time_text = self.font_small.render(
            f"いきのこり Time: {self.elapsed_time:.1f} びょう sec",
            True,
            (200, 200, 200)
        )
        time_rect = time_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 60))
        self.screen.blit(time_text, time_rect)
        
        # 3秒待機のメッセージ
        now = pygame.time.get_ticks()
        wait_time = max(0, 3 - (now - self.game_over_start_tick) // 1000)
        if wait_time > 0 and not self.is_scrolling:
            wait_text = self.font_small.render(f"あと {wait_time} びょうで もどるよ...", True, (150, 150, 150))
            wait_rect = wait_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 100))
            self.screen.blit(wait_text, wait_rect)

    def draw(self):
        # スクロール中またはGAME_OVER状態でメニューへの遷移がある場合、
        # 二つの画面を描画する必要がある
        if self.is_scrolling:
            # メニュー画面を上に、ゲームオーバー画面を下に配置してスクロール
            # (上にスクロール = 画面全体が上に移動していく)
            
            # テンポラリサーフェスに描画して合成
            temp_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT * 2))
            
            # 下(y=SCREEN_HEIGHT)にゲームオーバー描画
            self.screen.fill((30, 30, 30))
            self.draw_gameover()
            temp_surface.blit(self.screen, (0, SCREEN_HEIGHT))
            
            # 上(y=0)にメニュー描画
            self.screen.fill((30, 30, 30))
            self.draw_menu()
            temp_surface.blit(self.screen, (0, 0))
            
            # 切り出し
            # scroll_y が 0 の時、Game Over (y=SCREEN_HEIGHT) が見える
            # scroll_y が SCREEN_HEIGHT の時、Menu (y=0) が見える
            self.screen.blit(temp_surface, (0, 0), (0, SCREEN_HEIGHT - self.scroll_y, SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            self.screen.fill((30, 30, 30))
            
            if self.state == "MENU":
                self.draw_menu()
            elif self.state == "PLAYING":
                self.draw_game()
            elif self.state == "GAME_OVER_EFFECT":
                self.draw_game()
                self.vortex.draw(self.screen)
            elif self.state == "GAME_OVER":
                self.draw_gameover()
        
        # カメラフレームを画面右上に1/8サイズで常に表示
        self.draw_camera_frame()
        
        pygame.display.flip()
    
    def draw_camera_frame(self):
        """カメラフレームを画面左上に1/8サイズで表示、骨格を白線で表示"""
        if self.current_frame is None:
            return
        
        # フレームサイズを1/8に（1/8 = 0.125）
        scale = 0.1875
        frame_width = int(SCREEN_WIDTH * scale)
        frame_height = int(SCREEN_HEIGHT * scale)
        
        # フレームをBGRからRGBに変換
        frame_rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        # フレームをリサイズ
        frame_resized = cv2.resize(frame_rgb, (frame_width, frame_height))
        
        # 骨格情報を描画
        if self.hand_landmarks is not None:
            # 手の接続関係（MediaPipeの定義）
            HAND_CONNECTIONS = [
                (0, 1), (1, 2), (2, 3), (3, 4),  # 親指
                (0, 5), (5, 6), (6, 7), (7, 8),  # 人差し指
                (0, 9), (9, 10), (10, 11), (11, 12),  # 中指
                (0, 13), (13, 14), (14, 15), (15, 16),  # 薬指
                (0, 17), (17, 18), (18, 19), (19, 20),  # 小指
                (5, 9), (9, 13), (13, 17)  # 指の根元を繋ぐ
            ]
            
            # フレーム座標系での骨格点を計算
            landmarks_in_frame = []
            for landmark in self.hand_landmarks.landmark:
                x = int(landmark.x * frame_width)
                y = int(landmark.y * frame_height)
                landmarks_in_frame.append((x, y))
            
            # 骨格の接続線を描画（白色）
            for connection in HAND_CONNECTIONS:
                start_idx, end_idx = connection
                start = landmarks_in_frame[start_idx]
                end = landmarks_in_frame[end_idx]
                cv2.line(frame_resized, start, end, (255, 255, 255), 1)
            
            # 骨格の点を描画
            for i, landmark_pos in enumerate(landmarks_in_frame):
                # 指先のランドマーク（親指、人差し指、中指、薬指、小指の先端）
                tips = [4, 8, 12, 16, 20]
                if i in tips:
                    # 派手な演出（多重円 + パルス）
                    t = pygame.time.get_ticks() / 1000.0
                    pulse = math.sin(t * 10) * 2 + 2 # 0〜4の変動
                    
                    # 外側のぼんやりした発光（ネオン風）
                    color_neon = (0, 255, 255) # シアン
                    if i == 4: color_neon = (255, 100, 255) # 親指はマゼンタ
                    elif i == 8: color_neon = (100, 255, 100) # 人差し指はグリーン
                    
                    cv2.circle(frame_resized, landmark_pos, int(8 + pulse), color_neon, 1)
                    cv2.circle(frame_resized, landmark_pos, int(5 + pulse/2), (255, 255, 255), -1)
                else:
                    # 通常の関節点
                    cv2.circle(frame_resized, landmark_pos, 2, (180, 180, 180), -1)
        
        # PyGameで使用するために配列を回転
        frame_pygame = pygame.image.fromstring(
            frame_resized.tobytes(),
            (frame_width, frame_height),
            'RGB'
        )
        
        # 画面右端の中央に配置（少し余白を持たせる）
        margin = 10
        pos_x = SCREEN_WIDTH - frame_width - margin
        pos_y = (SCREEN_HEIGHT - frame_height) // 2
        
        # フレームを描画
        self.screen.blit(frame_pygame, (pos_x, pos_y))
        
        # フレームの周囲に枠線を描画
        rect = pygame.Rect(pos_x, pos_y, frame_width, frame_height)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, 2)
        
        # カメラ領域情報を保存（衝突判定に使用）
        self.camera_area = pygame.Rect(pos_x - 5, pos_y - 5, frame_width + 10, frame_height + 10)
    
    def run(self):
        running = True
        try:
            while running:
                running = self.handle_events()
                self.update()
                self.draw()
                self.clock.tick(FPS)
        finally:
            self.cap.release()
            pygame.quit()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        game = SnakeGame()
        game.run()
    except KeyboardInterrupt:
        print("\nゲームを終了しています...")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        pygame.quit()
        cv2.destroyAllWindows()
