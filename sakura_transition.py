import pygame
import random
import math
import sys
import time
import os

try:
    import win32api
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# ==========================================
# CONFIG
# ==========================================
WIDTH, HEIGHT = 1360, 800
FPS = 60
TOTAL_DURATION = 5.0

# フェーズのタイミング設定
PHASE1_END = 1.5      # 画面に桜の花がポンポン現れ、覆い尽くす
PHASE2_END = 2.5      # さらに桜の花が現れる（この間に裏でシーン切替が行われる想定）
# PHASE3 (2.5〜5.0): 桜が花びらになって散っていく

# 透明キーカラー（この色で塗った部分がOSレベルで透明になる）
TRANSPARENT_COLOR = (0, 0, 0)

# ==========================================
# 画像ロードと生成
# ==========================================
def load_sakura_flower():
    """桜の花全体の画像をロードして透過処理する"""
    candidates = ["sakura_transparent.png", "sakura.png"]
    for path in candidates:
        if os.path.exists(path):
            try:
                img = pygame.image.load(path)
                if path == "sakura_transparent.png":
                    img = img.convert_alpha()
                else:
                    img = img.convert()
                    img.set_colorkey((255, 255, 255))
                # 扱いやすいサイズにスケーリング
                return pygame.transform.smoothscale(img, (80, 80))
            except Exception as e:
                print(f"Failed to load {path}: {e}")
                pass
    
    # フォールバック: 画像がない場合はプログラムで描画
    surf = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(surf, (255, 183, 197), (40, 40), 30)
    pygame.draw.circle(surf, (255, 100, 150), (40, 40), 10)
    return surf

def create_petal_surfaces():
    """1枚の花びらを描画し、様々な角度に回転させた画像をメモリにキャッシュする"""
    base_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
    pygame.draw.ellipse(base_surface, (255, 183, 197, 255), (0, 5, 20, 10))
    pygame.draw.ellipse(base_surface, (255, 230, 235, 200), (5, 8, 10, 4))

    petals = []
    for angle in range(0, 360, 15):
        rotated = pygame.transform.rotate(base_surface, angle)
        petals.append(rotated)
    return petals

# ==========================================
# アニメーションクラス
# ==========================================
class Flower:
    """ポンポンと現れる桜の花（全体）"""
    def __init__(self, image, spawn_time):
        self.image = image
        self.x = random.uniform(0, WIDTH)
        self.y = random.uniform(0, HEIGHT)
        self.angle = random.uniform(0, 360)
        self.spawn_time = spawn_time
        self.target_scale = random.uniform(0.6, 1.4)
        
    def draw(self, surface, current_time):
        age = current_time - self.spawn_time
        # ポンッと現れるアニメーション（オーバーシュートするイージング）
        if age < 0.2:
            t = age / 0.2
            # back out ease
            scale = self.target_scale * (1.0 - (1.0 - t) * (1.0 - t) * (1.0 - t))
        else:
            scale = self.target_scale
            
        if scale > 0:
            w, h = self.image.get_size()
            scaled_img = pygame.transform.smoothscale(self.image, (int(w * scale), int(h * scale)))
            rotated_img = pygame.transform.rotate(scaled_img, self.angle)
            
            rect = rotated_img.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(rotated_img, rect)

class Petal:
    """舞い散る花びら（1枚ずつ）"""
    def __init__(self, images, x, y):
        self.images = images
        self.x = x + random.uniform(-20, 20)
        self.y = y + random.uniform(-20, 20)
        
        # 爆発的に散る初期速度
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(2, 10)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(0, 5) # 少し上に向かってから落ちる
        
        self.angle_idx = random.randint(0, len(self.images) - 1)
        self.spin_speed = random.choice([-2, -1, 1, 2])
        self.scale = random.uniform(0.5, 1.2)
        self.wobble_offset = random.uniform(0, math.pi * 2)

    def update(self):
        # 重力と風（右下へ流れる）
        self.vx += 0.15 # 右向きの風
        self.vy += 0.2  # 下向きの重力
        
        # 空気抵抗
        self.vx *= 0.98
        self.vy *= 0.98
        
        # サイン波での揺れ
        self.vx += math.sin(time.time() * 5 + self.wobble_offset) * 0.5

        self.x += self.vx
        self.y += self.vy

        # 回転
        if random.random() < 0.5:
            self.angle_idx = (self.angle_idx + self.spin_speed) % len(self.images)

    def draw(self, surface):
        img = self.images[self.angle_idx]
        if self.scale != 1.0:
            w, h = img.get_size()
            img = pygame.transform.scale(img, (int(w * self.scale), int(h * self.scale)))
        
        # 中心に合わせて描画
        rect = img.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(img, rect.topleft)

# ==========================================
# メインループ
# ==========================================
def set_window_transparency():
    """WindowsのAPIを使って、（黒）を透過色とし、クリックを貫通させる"""
    if HAS_WIN32:
        hwnd = pygame.display.get_wm_info()["window"]
        # WS_EX_LAYERED | WS_EX_TRANSPARENT を設定してクリック貫通と透過を有効化
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
        # 透過色の設定 (0,0,0) を透明に
        win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_COLOR), 0, win32con.LWA_COLORKEY)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    pygame.display.set_caption("Sakura Transition")
    
    set_window_transparency()
    
    clock = pygame.time.Clock()

    flower_img = load_sakura_flower()
    petal_images = create_petal_surfaces()
    
    flowers = []
    petals = []

    start_time = time.time()
    last_spawn_time = start_time
    
    phase3_triggered = False

    running = True
    while running:
        current_time = time.time()
        elapsed = current_time - start_time
        
        if elapsed > TOTAL_DURATION:
            running = False
            break

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
                sys.exit()

        # --- 画面のクリア (透過色で塗りつぶすことで下のウィンドウが透ける) ---
        screen.fill(TRANSPARENT_COLOR)
        
        # --- 背景の桜色レイヤーの不透明度（Alpha）計算 ---
        cover_alpha = 0
        if elapsed <= PHASE1_END:
            # 0〜1.5秒: ピンクに染まる
            cover_alpha = int((elapsed / PHASE1_END) * 255)
        elif elapsed <= PHASE2_END:
            # 1.5〜2.5秒: 完全なピンク（ここで裏側でシーンが切り替わっている）
            cover_alpha = 255
        else:
            # 2.5〜5.0秒: ピンクが晴れていき、次のシーンが見える
            fade_out_progress = (elapsed - PHASE2_END) / (TOTAL_DURATION - PHASE2_END)
            cover_alpha = int(255 - (fade_out_progress * 255))
            if cover_alpha < 0: cover_alpha = 0

        if cover_alpha > 0:
            # 完全に透過させず、ピンクの色で覆うためのサーフェス
            cover_surface = pygame.Surface((WIDTH, HEIGHT))
            cover_surface.fill((255, 183, 197))
            cover_surface.set_alpha(cover_alpha)
            screen.blit(cover_surface, (0, 0))

        # --- フェーズごとのロジック ---
        if elapsed <= PHASE2_END:
            # PHASE 1 & 2: 桜の花がポンポン現れる
            # フレームレートに依存せず一定頻度で花を出す
            spawn_interval = 0.05 if elapsed <= PHASE1_END else 0.02 # フェーズ2はさらに激しく
            if current_time - last_spawn_time > spawn_interval:
                # 1回のスパウンで複数個出す
                count = 5 if elapsed <= PHASE1_END else 15
                for _ in range(count):
                    flowers.append(Flower(flower_img, current_time))
                last_spawn_time = current_time
                
            # 花の描画
            for f in flowers:
                f.draw(screen, current_time)
                
        else:
            # PHASE 3: 2.5秒経過時、花を全て花びらに変換する（1回のみ）
            if not phase3_triggered:
                phase3_triggered = True
                for f in flowers:
                    # それぞれの花から3〜5枚の花びらを生成
                    num_petals_from_flower = random.randint(3, 5)
                    for _ in range(num_petals_from_flower):
                        petals.append(Petal(petal_images, f.x, f.y))
                # メモリ解放・非表示にするため花のリストを空に
                flowers.clear()
                
            # 花びらの更新と描画
            for p in petals:
                p.update()
                p.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()