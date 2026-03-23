import cv2
import numpy as np
import os

def remove_white_background(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"Error: Failed to load {input_path}.")
        return

    # 既にアルファチャンネルがある場合でも強制的に白マスクで抜くか、
    # 有効なアルファがあればそのまま利用するかを判定。
    has_alpha = img.shape[2] == 4
    if has_alpha:
        b, g, r, a = cv2.split(img)
        # アルファチャンネルが全て255（不透明）の場合は自分で抜く
        if np.mean(a) < 250:
            print("Image already has valid alpha channel. Generating scaled version just in case.")
            cv2.imwrite(output_path, img)
            return
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) # 一旦BGRに戻す

    # 白背景を抜く処理 (Flood Fill)
    mask = np.zeros((img.shape[0]+2, img.shape[1]+2), np.uint8)
    
    # 許容誤差。アンチエイリアス境界も少し含めるために値を設定。
    loDiff = (15, 15, 15)
    upDiff = (15, 15, 15)

    img_copy = img.copy()
    # 四隅から白背景を探索してマスク
    corners = [(0,0), (0, img.shape[0]-1), (img.shape[1]-1, 0), (img.shape[1]-1, img.shape[0]-1)]
    for pt in corners:
        cv2.floodFill(img_copy, mask, pt, (0, 0, 0), loDiff, upDiff, cv2.FLOODFILL_MASK_ONLY)

    # 実際のマスク
    real_mask = mask[1:-1, 1:-1]

    # BGR -> BGRA
    img_bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    
    # 背景としてマークされた部分を透明にする
    img_bgra[real_mask == 1, 3] = 0

    # フリンジ（境界の白いゴミ）をなじませるため、
    # エッジ部分のピクセルにおいて、白色度合いに応じてアルファを調整する
    kernel = np.ones((3,3), np.uint8)
    # フリンジ領域の特定: 背景(alpha=0)の少し内側
    bg_mask = (real_mask == 1).astype(np.uint8) * 255
    dilated_bg = cv2.dilate(bg_mask, kernel, iterations=1)
    fringe_mask = cv2.bitwise_xor(dilated_bg, bg_mask)

    # フリンジ領域のピクセルについてアルファをグラデーションにする（仮設）
    for y in range(img.shape[0]):
        for x in range(img.shape[1]):
            if fringe_mask[y, x] > 0 and img_bgra[y, x, 3] > 0:
                # 明るさ(白さ)を評価
                b_val, g_val, r_val = img_bgra[y, x, :3]
                gray = int(0.114*b_val + 0.587*g_val + 0.299*r_val)
                if gray > 200:
                    # 白に近いほど透明度を上げる
                    alpha = max(0, int(255 - (gray - 200) * 4.6))
                    img_bgra[y, x, 3] = alpha

    cv2.imwrite(output_path, img_bgra)
    print(f"Successfully processed and saved to {output_path}")

if __name__ == "__main__":
    remove_white_background("sakura.png", "sakura_transparent.png")
