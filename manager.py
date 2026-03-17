#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import math
import json
import socket
import random
import subprocess
import collections
import cv2
import mediapipe as mp

# =============================================================================
# [CONFIG] 現場調整用パラメータ（ここを書き換えて迅速に対応）
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "CAMERA_INDICES": [2, 0, 1],       # 優先順位: 2(Mac内蔵), 0(iPhone等), 1(仮想カメラ)
    "UDP_IP": "127.0.0.1",
    "UDP_PORT": 5005,                  # デフォルトUDPポート（もうあまり使わない）
    "SCENE_DIR": ".",                 # カレントフォルダ（この manager.py があるフォルダ）
    "PRELOAD_COUNT": 3,                # 待機させるプロセス数

    # ノイズ除去・誤検知防止フィルタ
    "MIN_HAND_SIZE": 0.05,             # 画面に対する手の面積比率（小さすぎる＝遠くの人は無視）
    "MAX_USERS": 3,                    # 同時に処理する最大人数

    # ジェスチャー（拍手）判定用
    "CLAP_DIST_THRESHOLD": 0.15,       # 拍手とみなす両手の距離 (0.08 -> 0.15 に大きく緩和)
    "CLAP_COOLDOWN": 0.5,              # ダブルクラップの受付時間（秒）

    # 描画負荷
    "TARGET_FPS": 30,                  # MediaPipeの解析FPS上限（描画はクライアント側で60FPS等で行う）

    # 動的に調整したいパラメータ（config.json などから書き換え可能）
    "BRIGHTNESS": 1.0,                 # デバッグプレビューの明るさ調整（1.0 = そのまま）
}


def load_config(path=CONFIG_PATH):
    """config.json を読み込み、DEFAULT_CONFIG で足りないものを補完する。"""
    cfg = dict(DEFAULT_CONFIG)

    # 既定のSCENE_DIRは相対指定（このスクリプトのあるフォルダ内）
    cfg["SCENE_DIR"] = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(cfg["SCENE_DIR"]):
        cfg["SCENE_DIR"] = os.path.abspath(os.path.join(BASE_DIR, cfg["SCENE_DIR"]))

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except Exception as e:
            print(f"[Manager] Warning: Failed to read config file {path}: {e}")

    # SCENE_DIR が相対指定の場合、base_dir からの相対とみなす
    cfg["SCENE_DIR"] = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(cfg["SCENE_DIR"]):
        cfg["SCENE_DIR"] = os.path.abspath(os.path.join(BASE_DIR, cfg["SCENE_DIR"]))

    return cfg


CONFIG = load_config()

# =============================================================================
# Gesture & Tracking Logic
# =============================================================================
class GestureInterpreter:
    def __init__(self):
        self.last_clap_time = 0
        self.clap_count = 0

    def check_head_clap(self, left_hand, right_hand, nose):
        """
        頭の上での2回拍手を判定する。
        MediaPipe座標系: x, y (0.0~1.0, 左上が原点)
        """
        if not (left_hand and right_hand and nose):
            return False

        # 1. 高さ判定: 両手が鼻〜口より高い位置（yが小さい）にあるか (nose.y + 0.1 にして緩和)
        if left_hand.y > nose.y + 0.1 or right_hand.y > nose.y + 0.1:
            return False

        # 2. 距離計算 (ユークリッド距離 x/yアスペクト比考慮せずに単純な距離)
        dist = math.sqrt((left_hand.x - right_hand.x)**2 + (left_hand.y - right_hand.y)**2)
        current_time = time.time()

        # 3. 接触判定
        if dist < CONFIG["CLAP_DIST_THRESHOLD"]:
            time_diff = current_time - self.last_clap_time
            # チャタリング防止: 0.2秒以上の間隔で次の拍手を受け付ける
            if 0.2 < time_diff < CONFIG["CLAP_COOLDOWN"]:
                self.clap_count += 1
                self.last_clap_time = current_time
            elif time_diff >= CONFIG["CLAP_COOLDOWN"]:
                self.clap_count = 1  # タイムアウトしたら1回目からやり直し
                self.last_clap_time = current_time

            # 2回検知でフラグを立て、カウントリセット
            if self.clap_count >= 2:
                self.clap_count = 0
                return True
                
        return False

# =============================================================================
# Process Manager
# =============================================================================
class SceneManager:
    def __init__(self):
        self.running_process = None
        self.active_port = None
        self.next_port = 6000
        self.preloaded_queue = collections.deque()
        self.all_scenes = self._scan_and_shuffle_scenes()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
    def _scan_and_shuffle_scenes(self):
        """
        フォルダ内のシーンをスキャンしてリスト化。
        ※ ここに「カテゴリ別に1つずつ取る」などの循環ロジックを後日追加可能。
        """
        scenes = []
        if not os.path.exists(CONFIG["SCENE_DIR"]):
            os.makedirs(CONFIG["SCENE_DIR"], exist_ok=True)
            print(f"Warning: Created empty directory at {CONFIG['SCENE_DIR']}")
            return scenes
            
        IGNORE_FILES = {"manager.py", "hand_tracker.py"}
            
        for f in os.listdir(CONFIG["SCENE_DIR"]):
            if f.endswith(".py") and f not in IGNORE_FILES:
                scenes.append(os.path.join(CONFIG["SCENE_DIR"], f))
                
        random.shuffle(scenes)
        
        # 最初はearth.pyから始める
        earth_path = os.path.join(CONFIG["SCENE_DIR"], "earth.py")
        if earth_path in scenes:
            scenes.remove(earth_path)
            scenes.insert(0, earth_path)
            
        return scenes

    def preload_next(self):
        """裏で次のプロセスを立ち上げておく（--wait引数を想定）"""
        if not self.all_scenes:
            return

        while len(self.preloaded_queue) < CONFIG["PRELOAD_COUNT"]:
            next_scene = self.all_scenes.pop(0)
            self.all_scenes.append(next_scene) # リストの末尾に戻して無限ループ化
            
            port = self.next_port
            self.next_port += 1
            if self.next_port > 65000:
                self.next_port = 6000
            
            print(f"[Manager] Preloading: {next_scene} on port {port}")
            # クライアント側は argparse で --wait と --port を受け取り、START信号を待つように書く
            p = subprocess.Popen([sys.executable, next_scene, "--wait", "--port", str(port)]) 
            self.preloaded_queue.append({"path": next_scene, "process": p, "port": port})

    def switch_scene(self, direction="next"):
        """現在のシーンを終了し、プリロード済みの次のシーンをアクティブにする"""
        if not self.preloaded_queue:
            print("[Manager] No scenes available to switch.")
            return

        # 前のシーンを確実に殺す
        if self.running_process:
            self.running_process.terminate()
            self.running_process.wait() # ゾンビプロセス化を防ぐ

        # 次のシーンをキューから取り出す
        target = self.preloaded_queue.popleft()
        self.running_process = target["process"]
        self.active_port = target["port"]
        
        print(f"\n[Manager] >>> ACTIVE SCENE: {os.path.basename(target['path'])} (Port: {self.active_port}) <<<\n")
        
        # 新しいシーンに起動コマンドを送信
        self.send_cmd("START", port=self.active_port)
        
        # 減った分をプリロード
        self.preload_next()

    def send_cmd(self, cmd_string, port=None):
        """UDPでシステムコマンドのみを送信"""
        if port is None:
            port = self.active_port
        if port is None:
            return
        packet = {"cmd": cmd_string, "hands": []}
        self.sock.sendto(json.dumps(packet).encode('utf-8'), (CONFIG["UDP_IP"], port))

    def broadcast_data(self, hands_data):
        """UDPで解析済みの座標データを送信"""
        if self.active_port is None:
            return
        packet = {"cmd": "UPDATE", "hands": hands_data}
        self.sock.sendto(json.dumps(packet).encode('utf-8'), (CONFIG["UDP_IP"], self.active_port))

    def check_scene_control(self):
        """scene_control.jsonを監視し、更新があればシーンを切り替える"""
        control_file = os.path.join(CONFIG["SCENE_DIR"], "scene_control.json")
        if not os.path.exists(control_file):
            return

        try:
            mtime = os.path.getmtime(control_file)
            if not hasattr(self, "last_control_mtime") or mtime > self.last_control_mtime:
                self.last_control_mtime = mtime
                with open(control_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                target_scene = data.get("target_scene")
                if target_scene:
                    self.switch_to(target_scene)
        except Exception as e:
            print(f"[Manager] Error reading scene_control.json: {e}")

    def check_config_update(self):
        """config.json の変更を監視し、変更があれば再読み込みする"""
        if not os.path.exists(CONFIG_PATH):
            return

        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if not hasattr(self, "last_config_mtime") or mtime > self.last_config_mtime:
                self.last_config_mtime = mtime
                global CONFIG
                CONFIG = load_config(CONFIG_PATH)
                print(f"[Manager] Reloaded config from {CONFIG_PATH}")
        except Exception as e:
            print(f"[Manager] Error reading config.json: {e}")

    def switch_to(self, target_filename):
        """Streamlitからの指定シーン起動要求を処理する"""
        target_path = os.path.join(CONFIG["SCENE_DIR"], target_filename)
        
        if not os.path.exists(target_path):
            print(f"[Manager] Cannot find target scene: {target_path}")
            return

        print(f"\n[Manager] Forcing switch to: {target_filename}\n")

        # 現在のキュー内のプロセスを全キル
        for item in self.preloaded_queue:
            item["process"].terminate()
            item["process"].wait()
        self.preloaded_queue.clear()

        # all_scenes リストにない場合は追加、ある場合は一旦削除して先頭へ
        if target_path in self.all_scenes:
            self.all_scenes.remove(target_path)
        self.all_scenes.insert(0, target_path)

        # 対象シーンを先頭に1個含む形でプリロード
        self.preload_next()
        
        # 起動が完了するまで少し待つ
        time.sleep(0.5)
        
        # switch_sceneを実行してアクティブにする
        self.switch_scene()

# =============================================================================
# Main Loop
# =============================================================================
def main():
    manager = SceneManager()
    interpreter = GestureInterpreter()
    
    # 起動時の初期化
    manager.preload_next()
    manager.switch_scene()

    # カメラの初期化（複数のインデックスを試行）
    cap = None
    for idx in CONFIG["CAMERA_INDICES"]:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            print(f"[Manager] Camera started with index {idx}")
            break
    
    if cap is None or not cap.isOpened():
        print("[Manager] Error: Could not open any camera.")
        return

    cv2.namedWindow('Manager View (Debug)', cv2.WINDOW_NORMAL) # 通常ウィンドウに戻す

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Holisticモデル（顔・姿勢・手を一括取得）の初期化
    mp_holistic = mp.solutions.holistic
    holistic = mp_holistic.Holistic(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

    print("[Manager] System Ready. Press 'q' to quit.")
    
    clock = time.time() - 1.0 # Force the first frame to process
    results = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_time = time.time()
        # FPS制限（MediaPipeを回しすぎない）
        if current_time - clock < 1.0 / CONFIG["TARGET_FPS"]:
            pass # スキップする場合でも画面表示とキーボード入力処理は止めない
        else:
            clock = current_time
            
            # Mediapipeでの処理
            image = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = holistic.process(image)
            image.flags.writeable = True
            
            # ジェスチャー（頭の上で拍手）判定のための座標取得
            left_hand = None
            right_hand = None
            nose = None
            
            if results.pose_landmarks:
                nose = results.pose_landmarks.landmark[mp_holistic.PoseLandmark.NOSE]
                
            if results.left_hand_landmarks:
                left_hand = results.left_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]
                
            if results.right_hand_landmarks:
                right_hand = results.right_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]
            
            # 判定処理とシーン切り替え実行
            if interpreter.check_head_clap(left_hand, right_hand, nose):
                print("[Manager] Head Clap Detected! Switching Scene...")
                manager.switch_scene()
                
            # 他のクライアントへの座標データ同報送信（現在はプレースホルダーとして空配列）
            hands_data = []
            
            # クライアントへ座標データをブロードキャスト
            manager.broadcast_data(hands_data[:CONFIG["MAX_USERS"]])

        # Managerのコントロール状態をチェックして、必要ならシーン切替
        manager.check_scene_control()
        manager.check_config_update()

        # デバッグ用プレビュー画面（本番では外部ディスプレイの邪魔にならないよう最小化か非表示）
        brightness = CONFIG.get("BRIGHTNESS", 1.0)
        if abs(brightness - 1.0) > 1e-3:
            frame = cv2.convertScaleAbs(frame, alpha=brightness, beta=0)

        cv2.putText(frame, f"Active: {manager.running_process.pid if manager.running_process else 'None'}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Manager View (Debug)", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('n'):
            print("[Manager] Keyboard Input: Next Scene")
            manager.switch_scene()
        elif key == ord('p'):
            print("[Manager] Keyboard Input: Previous Scene")
            manager.switch_scene("prev")

    # クリーンアップ
    if manager.running_process:
        manager.send_cmd("STOP")
        manager.running_process.terminate()
    cap.release()
    cv2.destroyAllWindows()
    holistic.close()

if __name__ == "__main__":
    import sys
    main()