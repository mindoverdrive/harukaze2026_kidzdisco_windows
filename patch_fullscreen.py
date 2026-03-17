"""
patch_fullscreen.py
全シーンスクリプトを一括でセカンドモニター全画面表示に対応させるパッチスクリプト。
3種類のウィンドウシステムに対応:
  1. OpenCV (cv2.namedWindow)
  2. Pygame (pygame.display.set_mode)
  3. RenderCanvas (pygfx/wgpu)
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IGNORE_FILES = {
    "manager.py", "display_utils.py", "patch_fullscreen.py",
    "replace_caps.py", "patch.py", "test_gfx_transparency.py",
}

def patch_file(filepath):
    """ファイルを読み込み、セカンドモニター全画面表示に対応させる"""
    filename = os.path.basename(filepath)
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    changes = []
    
    # ===== 1. OpenCV パッチ =====
    # cv2.namedWindow('name', ...) → display_utils.setup_cv2_fullscreen('name')
    cv2_pattern = re.compile(
        r"cv2\.namedWindow\(\s*(['\"][^'\"]+['\"])\s*,\s*[^)]*\)"
    )
    if cv2_pattern.search(content):
        # import を追加
        if "import display_utils" not in content and "from display_utils" not in content:
            # import cv2 の後に追加
            content = re.sub(
                r"(import cv2\s*\n)",
                r"\1import display_utils\n",
                content, count=1
            )
        
        # namedWindow を setup_cv2_fullscreen に置換
        def replace_cv2_named(match):
            window_name = match.group(1)
            return f"display_utils.setup_cv2_fullscreen({window_name})"
        
        content = cv2_pattern.sub(replace_cv2_named, content)
        
        # setWindowProperty FULLSCREEN の既存設定を削除（重複防止）
        content = re.sub(
            r"\s*cv2\.setWindowProperty\([^)]*WND_PROP_FULLSCREEN[^)]*\)\s*\n",
            "\n",
            content
        )
        # moveWindow の既存設定を削除
        content = re.sub(
            r"\s*cv2\.moveWindow\([^)]*\)\s*\n",
            "\n",
            content
        )
        
        changes.append("cv2.namedWindow → display_utils.setup_cv2_fullscreen")
    
    # ===== 2. Pygame パッチ =====
    # pygame.display.set_mode((0, 0), pygame.FULLSCREEN) → display_utils.setup_pygame_fullscreen()
    # pygame.display.set_mode((W, H), pygame.FULLSCREEN | ...) → display_utils.setup_pygame_fullscreen()
    pygame_setmode_pattern = re.compile(
        r"(\w[\w.]*)\s*=\s*pygame\.display\.set_mode\(\s*\([^)]*\)\s*(?:,\s*[^)]+)?\)"
    )
    
    if "pygame.display.set_mode" in content and "import pygame" in content:
        # import を追加
        if "import display_utils" not in content and "from display_utils" not in content:
            content = re.sub(
                r"(import pygame\s*\n)",
                r"\1import display_utils\n",
                content, count=1
            )
        
        # set_mode を setup_pygame_fullscreen に置換（最初の1つだけ）
        # パターン: var = pygame.display.set_mode(...)
        def replace_pygame_setmode(match):
            var_name = match.group(1)
            return f"{var_name}, _pg_size = display_utils.setup_pygame_fullscreen()"
        
        content = pygame_setmode_pattern.sub(replace_pygame_setmode, content, count=1)
        
        # pygame.display.Info() の直前での解像度取得を調整
        # 多くのスクリプトが info = pygame.display.Info() で W,H を取得しているが、
        # setup_pygame_fullscreen() が正しいサイズを返すのでそのまま動く
        
        changes.append("pygame.display.set_mode → display_utils.setup_pygame_fullscreen")
    
    # ===== 3. RenderCanvas パッチ =====
    # RenderCanvas(size=(W, H), ...) のサイズをセカンドモニターサイズに変更
    rendercanvas_pattern = re.compile(
        r"RenderCanvas\(\s*size\s*=\s*\([^)]+\)"
    )
    
    if "RenderCanvas" in content and "rendercanvas" in content:
        # import を追加
        if "import display_utils" not in content and "from display_utils" not in content:
            # from rendercanvas の前に追加
            content = re.sub(
                r"(from rendercanvas[^\n]*\n)",
                r"import display_utils\n\1",
                content, count=1
            )
        
        # WINDOW_WIDTH, WINDOW_HEIGHT の定義を置換
        # パターン: WINDOW_WIDTH = 1920 etc.
        ww_pattern = re.compile(r"WINDOW_WIDTH\s*=\s*\d+")
        wh_pattern = re.compile(r"WINDOW_HEIGHT\s*=\s*\d+")
        
        if ww_pattern.search(content) and wh_pattern.search(content):
            # WINDOW_WIDTH/HEIGHT 定義の前に display_utils のサイズ取得を追加
            # ただし既に置換済みの場合はスキップ
            if "display_utils.get_second_monitor_size()" not in content:
                content = ww_pattern.sub(
                    "_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()\nWINDOW_WIDTH = _DU_W",
                    content, count=1
                )
                content = wh_pattern.sub("WINDOW_HEIGHT = _DU_H", content, count=1)
        else:
            # WIDTH / HEIGHT パターン
            w_pattern = re.compile(r"^(WIDTH)\s*=\s*\d+", re.MULTILINE)
            h_pattern = re.compile(r"^(HEIGHT)\s*=\s*\d+", re.MULTILINE)
            if w_pattern.search(content) and h_pattern.search(content):
                if "display_utils.get_second_monitor_size()" not in content:
                    content = w_pattern.sub(
                        "_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()\nWIDTH = _DU_W",
                        content, count=1
                    )
                    content = h_pattern.sub("HEIGHT = _DU_H", content, count=1)
        
        changes.append("RenderCanvas size → second monitor size")
    
    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return changes
    return None


def main():
    count = 0
    for filename in sorted(os.listdir(BASE_DIR)):
        if filename.endswith(".py") and filename not in IGNORE_FILES:
            filepath = os.path.join(BASE_DIR, filename)
            try:
                changes = patch_file(filepath)
                if changes:
                    count += 1
                    print(f"  OK {filename}: {', '.join(changes)}")
            except Exception as e:
                print(f"  NG {filename}: Error - {e}")
    
    print(f"\nTotal files patched: {count}")


if __name__ == "__main__":
    main()
