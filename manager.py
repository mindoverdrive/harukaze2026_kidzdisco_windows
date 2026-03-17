#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import math
import json
import random
import subprocess
import threading
import cv2
import mediapipe as mp

# =============================================================================
# [CONFIG] 現場調整用パラメータ（ここを書き換えて迅速に対応）
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "CAMERA_INDEX": 3,                 # USB Webカメラのインデックス
    "SCENE_DIR": ".",                  # カレントフォルダ（この manager.py があるフォルダ）

    # ジェスチャー（拍手）判定用
    "CLAP_DIST_THRESHOLD": 0.15,       # 拍手とみなす両手の距離
    "CLAP_COOLDOWN": 1.0,              # ダブルクラップの受付時間（秒）

    # 描画負荷
    "TARGET_FPS": 30,                  # MediaPipeの解析FPS上限
}


def load_config(path=CONFIG_PATH):
    """config.json を読み込み、DEFAULT_CONFIG で足りないものを補完する。"""
    cfg = dict(DEFAULT_CONFIG)

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

    cfg["SCENE_DIR"] = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(cfg["SCENE_DIR"]):
        cfg["SCENE_DIR"] = os.path.abspath(os.path.join(BASE_DIR, cfg["SCENE_DIR"]))

    return cfg


CONFIG = load_config()

# =============================================================================
# Gesture & Tracking Logic (頭の上で二回拍手)
# =============================================================================
class GestureInterpreter:
    def __init__(self):
        self.last_clap_time = 0
        self.clap_count = 0
        self.hands_were_apart = True  # 手が離れていた状態を追跡

    def check_head_clap(self, left_hand, right_hand, nose):
        """
        頭の上での2回拍手を判定する。
        MediaPipe座標系: x, y (0.0~1.0, 左上が原点)
        """
        if not (left_hand and right_hand and nose):
            return False

        # 1. 高さ判定: 両手が鼻より高い位置（yが小さい）にあるか
        if left_hand.y > nose.y + 0.1 or right_hand.y > nose.y + 0.1:
            return False

        # 2. 距離計算
        dist = math.sqrt((left_hand.x - right_hand.x)**2 + (left_hand.y - right_hand.y)**2)
        current_time = time.time()

        # 3. 手が離れている状態を検出（拍手のリリース）
        if dist > CONFIG["CLAP_DIST_THRESHOLD"] * 1.5:
            self.hands_were_apart = True
            return False

        # 4. 手が近づいた＝拍手（前に手が離れていた場合のみカウント）
        if dist < CONFIG["CLAP_DIST_THRESHOLD"] and self.hands_were_apart:
            self.hands_were_apart = False
            time_diff = current_time - self.last_clap_time

            if time_diff < CONFIG["CLAP_COOLDOWN"]:
                # 前の拍手から短い時間内 → 2回目の拍手！
                self.clap_count += 1
            else:
                # タイムアウト → 1回目としてカウントし直し
                self.clap_count = 1

            self.last_clap_time = current_time

            # 2回検知でトリガー
            if self.clap_count >= 2:
                self.clap_count = 0
                return True

        return False

# =============================================================================
# Scene Manager (シンプル版 - 直接subprocess起動)
# =============================================================================
class SceneManager:
    def __init__(self):
        self.running_process = None
        self.current_scene_name = "None"
        self.scene_index = 0
        self.all_scenes = self._scan_and_shuffle_scenes()
        print(f"[Manager] Found {len(self.all_scenes)} scenes")

    def _scan_and_shuffle_scenes(self):
        """フォルダ内のシーンをスキャンしてリスト化。"""
        scenes = []
        scene_dir = CONFIG["SCENE_DIR"]

        if not os.path.exists(scene_dir):
            os.makedirs(scene_dir, exist_ok=True)
            return scenes

        # 除外するファイル（マネージャ自身やユーティリティ系）
        IGNORE_FILES = {
            "manager.py", "hand_tracker.py", "replace_caps.py",
            "patch.py", "test_setup.py", "test_mp.py",
            "test_mp_debug.py", "test_run.py", "app.py",
            "test_gfx_transparency.py",
        }

        for f in os.listdir(scene_dir):
            if f.endswith(".py") and f not in IGNORE_FILES:
                scenes.append(os.path.join(scene_dir, f))

        random.shuffle(scenes)

        # 最初はearth.pyから始める
        earth_path = os.path.join(scene_dir, "earth.py")
        if earth_path in scenes:
            scenes.remove(earth_path)
            scenes.insert(0, earth_path)

        return scenes

    def kill_current(self):
        """現在実行中のシーンを終了する"""
        if self.running_process and self.running_process.poll() is None:
            print(f"[Manager] Killing scene: {self.current_scene_name}")
            self.running_process.terminate()
            try:
                self.running_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.running_process.kill()
                self.running_process.wait()
            self.running_process = None

    def launch_scene(self, scene_path):
        """シーンをsubprocessとして起動"""
        self.current_scene_name = os.path.basename(scene_path)
        print(f"\n[Manager] >>> LAUNCHING: {self.current_scene_name} <<<\n")

        self.running_process = subprocess.Popen(
            [sys.executable, scene_path],
            cwd=os.path.dirname(scene_path)
        )

    def switch_scene(self):
        """次のシーンに切り替え"""
        if not self.all_scenes:
            print("[Manager] No scenes available.")
            return

        # 現在のシーンを停止
        self.kill_current()

        # 次のシーンを取得（リストを循環）
        scene_path = self.all_scenes[self.scene_index % len(self.all_scenes)]
        self.scene_index += 1

        # 少し待ってからカメラを解放する時間を確保
        time.sleep(0.3)

        # シーンを起動
        self.launch_scene(scene_path)

    def is_scene_running(self):
        """現在のシーンがまだ実行中かチェック"""
        if self.running_process is None:
            return False
        return self.running_process.poll() is None

    def cleanup(self):
        """全プロセスをクリーンアップ"""
        self.kill_current()

# =============================================================================
# Head Clap Monitor (バックグラウンドでカメラを使って拍手検知)
# =============================================================================
class HeadClapMonitor:
    """
    別スレッドでカメラを開き、頭上での二回拍手を監視する。
    シーンが起動中はカメラを開けない可能性があるため、
    リトライしながら監視を続ける。
    """
    def __init__(self, camera_index=3):
        self.camera_index = camera_index
        self.clap_detected = False
        self.running = True
        self.interpreter = GestureInterpreter()
        self.thread = None
        self.cap = None
        self.status = "idle"

    def start(self):
        """監視スレッドを開始"""
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """監視を停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def consume_clap(self):
        """拍手フラグを消費して返す"""
        if self.clap_detected:
            self.clap_detected = False
            return True
        return False

    def _try_open_camera(self):
        """カメラを開く試み"""
        if self.cap and self.cap.isOpened():
            return True

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            cap.set(cv2.CAP_PROP_FPS, 15)
            self.cap = cap
            self.status = "monitoring"
            return True
        else:
            cap.release()
            # デフォルトバックエンドも試す
            cap = cv2.VideoCapture(self.camera_index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                cap.set(cv2.CAP_PROP_FPS, 15)
                self.cap = cap
                self.status = "monitoring"
                return True
            cap.release()
            self.status = "camera_busy"
            return False

    def _monitor_loop(self):
        """メインの監視ループ（別スレッドで実行）"""
        mp_holistic = mp.solutions.holistic
        holistic = mp_holistic.Holistic(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )

        while self.running:
            # カメラが開けない場合はリトライ
            if not self._try_open_camera():
                time.sleep(1.0)
                continue

            ret, frame = self.cap.read()
            if not ret:
                # フレーム取得失敗 → カメラを閉じてリトライ
                self.cap.release()
                self.cap = None
                self.status = "camera_lost"
                time.sleep(0.5)
                continue

            # MediaPipe処理
            image = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = holistic.process(image)

            # ランドマーク取得
            left_hand = None
            right_hand = None
            nose = None

            if results.pose_landmarks:
                nose = results.pose_landmarks.landmark[mp_holistic.PoseLandmark.NOSE]
            if results.left_hand_landmarks:
                left_hand = results.left_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]
            if results.right_hand_landmarks:
                right_hand = results.right_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]

            # 拍手判定
            if self.interpreter.check_head_clap(left_hand, right_hand, nose):
                print("[Monitor] ★★★ HEAD CLAP DETECTED! ★★★")
                self.clap_detected = True

            # CPU負荷軽減
            time.sleep(1.0 / CONFIG["TARGET_FPS"])

        holistic.close()
        if self.cap and self.cap.isOpened():
            self.cap.release()

# =============================================================================
# Main Loop
# =============================================================================
def main():
    manager = SceneManager()

    if not manager.all_scenes:
        print("[Manager] Error: No scene files found.")
        return

    # 頭上拍手モニターを開始（バックグラウンドスレッド）
    monitor = HeadClapMonitor(camera_index=CONFIG.get("CAMERA_INDEX", 3))
    monitor.start()

    # 最初のシーンを起動
    manager.switch_scene()

    # デバッグ用の小さいウィンドウ
    cv2.namedWindow('Manager Control', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Manager Control', 400, 100)

    # コントロール用の黒い画像
    control_img = None

    print("[Manager] ======================================")
    print("[Manager] System Ready!")
    print("[Manager]   頭の上で二回拍手 → シーン切り替え")
    print("[Manager]   'n' キー → 次のシーン")
    print("[Manager]   'q' キー → 終了")
    print("[Manager] ======================================")

    try:
        while True:
            # 1. 拍手検知チェック
            if monitor.consume_clap():
                print("[Manager] Head Clap → Switching Scene!")
                manager.switch_scene()

            # 2. シーンが自分で終了した場合、次のシーンを自動起動
            if not manager.is_scene_running():
                print(f"[Manager] Scene '{manager.current_scene_name}' exited. Launching next...")
                time.sleep(0.5)
                manager.switch_scene()

            # 3. コントロールウィンドウ更新（ステータス表示）
            import numpy as np
            control_img = np.zeros((100, 400, 3), dtype=np.uint8)
            scene_text = f"Scene: {manager.current_scene_name}"
            monitor_text = f"Clap Monitor: {monitor.status}"
            cv2.putText(control_img, scene_text, (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.putText(control_img, monitor_text, (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
            cv2.putText(control_img, "n=Next  q=Quit  Clap=Switch", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            cv2.imshow("Manager Control", control_img)

            # 4. キーボード入力
            key = cv2.waitKey(100) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('n'):
                print("[Manager] Keyboard → Next Scene")
                manager.switch_scene()

    except KeyboardInterrupt:
        print("\n[Manager] Interrupted by user.")

    # クリーンアップ
    print("[Manager] Shutting down...")
    monitor.stop()
    manager.cleanup()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()