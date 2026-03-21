import pygame
import random
import math
import sys
import time

# ==========================================
# CONFIG
# ==========================================
WIDTH, HEIGHT = 1360, 800
FPS = 60
TOTAL_DURATION = 5.0  # トランジション全体の秒数

# フェーズのタイミング設定
PHASE1_END = 1.5      # 画面が桜色で埋まり切る時間
PHASE2_END = 3.5      # 桜が吹き飛び始める時間

PARTICLE_COUNT = 800  # 画面を舞う花びらの数（RTX4060なら余裕ですが、多すぎるとCPUが詰まります）

# ==========================================
# 花びら生成・キャッシュ処理（高速化の要）
# ==========================================
def create_petal_surfaces():
    """1枚の花びらを描画し、様々な角度に回転させた画像をメモリにキャッシュする"""
    base_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
    # 桜の花びらを描画 (シンプルなピンクの楕円ベース)
    pygame.draw.ellipse(base_surface, (255, 183, 197, 255), (0, 5, 20, 10))
    pygame.draw.ellipse(base_surface, (255, 230, 235, 200), (5, 8, 10, 4)) # ハイライト

    petals = []
    for angle in range(0, 360, 15):
        rotated = pygame.transform.rotate(base_surface, angle)
        petals.append(rotated)
    return petals

# ==========================================
# パーティクルクラス
# ==========================================
class Petal:
    def __init__(self, petal_images):
        self.images = petal_images
        self.reset(initial_spawn=True)

    def reset(self, initial_spawn=False):
        self.x = random.uniform(-100, WIDTH + 100)
        # 初期スポーン時は画面全体に、それ以降は上または左から
        self.y = random.uniform(-100, HEIGHT) if initial_spawn else random.uniform(-100, -20)
        self.vx = random.uniform(-2, 2)
        self.vy = random.uniform(2, 6)
        self.angle_idx = random.randint(0, len(self.images) - 1)
        self.spin_speed = random.choice([-1, 1])
        self.scale = random.uniform(0.5, 1.5)
        self.wobble_offset = random.uniform(0, math.pi * 2)

    def update(self, phase_time):
        # フェーズ3（吹き飛び）の時は右への強風をかける
        if phase_time > PHASE2_END:
            self.vx += 0.5  # 右方向への加速度
            self.vy += 0.1
        else:
            # 通常のヒラヒラ落ちる動き（サイン波で揺らす）
            self.vx = math.sin(time.time() * 2 + self.wobble_offset) * 2

        self.x += self.vx
        self.y += self.vy

        # 回転の更新
        if random.random() < 0.3:
            self.angle_idx = (self.angle_idx + self.spin_speed) % len(self.images)

        # 画面外に出たらリセット（フェーズ3以外）
        if phase_time <= PHASE2_END and (self.y > HEIGHT + 50 or self.x > WIDTH + 50):
            self.reset()

    def draw(self, surface):
        img = self.images[self.angle_idx]
        if self.scale != 1.0:
            # 本当は毎フレームscaleすると重いですが、800個程度ならi7の力でゴリ押し可能です
            w, h = img.get_size()
            img = pygame.transform.scale(img, (int(w * self.scale), int(h * self.scale)))
        
        surface.blit(img, (int(self.x), int(self.y)))

# ==========================================
# メインループ
# ==========================================
def main():
    pygame.init()
    # 現場の拡張ディスプレイ用設定（必要に応じて os.environ で出力先を指定）
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME) # 枠なしウィンドウ
    clock = pygame.time.Clock()

    petal_images = create_petal_surfaces()
    particles = [Petal(petal_images) for _ in range(PARTICLE_COUNT)]

    start_time = time.time()
    running = True

    while running:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # 5秒経過でトランジション終了
        if elapsed > TOTAL_DURATION:
            running = False
            break

        # イベント処理（テスト用終了）
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
                sys.exit()

        # --- 背景の桜色レイヤーの不透明度（Alpha）計算 ---
        cover_alpha = 0
        if elapsed <= PHASE1_END:
            # 0〜1.5秒: 徐々にピンクに染まる
            cover_alpha = int((elapsed / PHASE1_END) * 255)
        elif elapsed <= PHASE2_END:
            # 1.5〜3.5秒: 完全なピンク（ここで裏側でシーンが切り替わる）
            cover_alpha = 255
        else:
            # 3.5〜5.0秒: ピンクが晴れていく
            fade_out_progress = (elapsed - PHASE2_END) / (TOTAL_DURATION - PHASE2_END)
            cover_alpha = int(255 - (fade_out_progress * 255))

        # 画面のクリア（本来はここでキャプチャした背景を描画するとさらにリアル）
        # ※テスト用として、暗いグレーを現在のシーンに見立てます
        screen.fill((30, 30, 30))

        # 桜色レイヤーの描画
        cover_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        cover_surface.fill((255, 200, 210, cover_alpha))
        screen.blit(cover_surface, (0, 0))

        # 花びらの更新と描画
        for p in particles:
            p.update(elapsed)
            p.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()