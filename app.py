import streamlit as st
import os
import json
import time

# 統計送信をオフにする（オフライン環境向け）
os.environ["STREAMLIT_SERVER_GATHER_USAGE_STATS"] = "false"

# 設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = BASE_DIR
IGNORE_FILES = {"manager.py", "hand_tracker.py", "app.py"}

def get_scenes():
    """ディレクトリ内の対象シーン(.py)を一覧取得"""
    scenes = []
    if os.path.exists(CONFIG_DIR):
        for f in os.listdir(CONFIG_DIR):
            if f.endswith(".py") and f not in IGNORE_FILES and not f.startswith("test_"):
                scenes.append(f)
    return sorted(scenes)

def write_control_file(scene_name):
    """manager.pyが監視しているJSONファイルに書き込む"""
    control_file = os.path.join(CONFIG_DIR, "scene_control.json")
    data = {
        "target_scene": scene_name,
        "timestamp": time.time()
    }
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
    st.success(f"シーン「{scene_name}」に切り替え信号を送信しました。")

# ページ基本設定
st.set_page_config(page_title="Harukaze 2026 Controller", page_icon="🎨", layout="wide")

# タイトル
st.title("🎨 Harukaze 2026 Scene Controller")
st.write("ボタンを押して、メインディスプレイの表示シーン（Pygfx/OpenCVウィンドウ）を切り替えます。")

# シーン一覧の取得
scenes = get_scenes()

if not scenes:
    st.warning(f"ディレクトリ `{CONFIG_DIR}` に対象シーンが見つかりません。")
else:
    st.markdown("### 利用可能なシーン")
    
    # 3列でボタンを配置
    cols = st.columns(3)
    for i, scene in enumerate(scenes):
        with cols[i % 3]:
            # 見やすい表示名を作成（一部の拡張子やアンダースコアを除去）
            display_name = scene.replace('.py', '').replace('_', ' ').title()
            
            # ボタンが押された時の処理
            if st.button(f"▶ {display_name}", key=scene, use_container_width=True):
                write_control_file(scene)

st.markdown("---")
st.caption("Developed for Harukaze2026pj - Local Web Remote Panel powered by Streamlit")
