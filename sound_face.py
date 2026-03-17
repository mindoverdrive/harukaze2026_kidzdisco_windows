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
# =========================
# AV Face-to-Chord Controller (macOS / M1)
# MediaPipeで顔検出 -> IAC仮想MIDI経由でAbleton Liveへ和音を送出
# 依存: pip install opencv-python mediapipe mido python-rtmidi numpy python-osc
# =========================

import cv2
import display_utils
import numpy as np
import time
import math
from dataclasses import dataclass
import mediapipe as mp
from mido import Message, MidiFile, MidiTrack, MetaMessage
import mido
from pythonosc import udp_client  # TouchDesigner用(任意)
import sys

# ====== 設定 ======
MIDI_PORT_NAME = "IAC Driver from_python Bus 1"   # Audio MIDI 設定で作成したIACポート名
MIDI_CHANNEL = 0              # 0-15
BASE_ROOT = 60                # C4 (MIDIノート)
SEMITONE_RANGE = 5            # X位置で±この半音数まで転調
STABILITY_FRAMES = 5          # 判定安定化のため同一状態が何フレーム続いたら確定か
VELOCITY_MIN, VELOCITY_MAX = 30, 110  # 顔Y位置→Velocityにマッピング
CAM_INDEX = 2                 # カメラ番号

# TouchDesignerへOSC送信（使わないならFalse）
USE_OSC = False
TD_OSC_TARGET = ("127.0.0.1", 7000)

# コード定義: ルートからの半音インターバル
CHORD_LIBRARY = {
    "REST": [],
    "Cmaj": [0, 4, 7],
    "Am":   [0, 3, 7],
    "Fmaj": [0, 4, 7],   # 後でrootをFに変える
    "G7":   [0, 4, 7, 10],
    "Dm":   [0, 3, 7],
}

# 口の開き具合(0~3) -> (コード名, ルートオフセット半音)
# 0=閉(休符), 1=少し開く(C), 2=開く(Am), 3=大きく開く(F)
MOUTH_TO_CHORD = {
    0: ("REST", 0),
    1: ("Cmaj", 0),           # C
    2: ("Am",   9),           # A (Cから+9)
    3: ("Fmaj", -5),          # F (Cから-5)
    # 必要に応じて追加
}

# ====== ユーティリティ ======
def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))

@dataclass
class ChordState:
    name: str = "REST"
    notes: tuple = ()
    root: int = BASE_ROOT
    velocity: int = 80

# 顔のランドマーク定義 (MediaPipe Face Mesh)
# 鼻の頭: 1
# 上唇(下端): 13
# 下唇(上端): 14
NOSE_TIP = 1
UPPER_LIP = 13
LOWER_LIP = 14

def get_mouth_openness(landmarks, img_h, img_w):
    # landmarks: normalized [0..1]
    # 上唇と下唇の距離を計算し、顔の大きさ(鼻と顎など)で正規化するのが理想だが、
    # 簡易的に絶対距離または相対距離で判定する
    
    # 座標取得
    upper = landmarks[UPPER_LIP]
    lower = landmarks[LOWER_LIP]
    
    # Y座標の差分 (normalized)
    # yは下に増えるので lower.y - upper.y が正の値になるはず
    diff_y = lower.y - upper.y
    
    # 閾値設定 (個人差やカメラ距離による調整が必要かもしれない)
    # 0.01未満: 閉じてる
    # 0.01 ~ 0.03: 少し
    # 0.03 ~ 0.06: 開いてる
    # 0.06以上: 大きく
    
    # ※実際の値はカメラ距離によるので、動作確認しながら調整推奨
    # ここでは一般的なWebカメラ距離を想定
    
    if diff_y < 0.01:
        return 0 # Closed
    elif diff_y < 0.04:
        return 1 # Small
    elif diff_y < 0.08:
        return 2 # Medium
    else:
        return 3 # Large

def map_x_to_semitone(x_norm):
    # x_norm: 0..1, 0=左,1=右 -> -SEMITONE_RANGE..+SEMITONE_RANGE
    # 画面左(0)が低音、右(1)が高音とする
    v = int(round(lerp(-SEMITONE_RANGE, SEMITONE_RANGE, x_norm)))
    return v

def map_y_to_velocity(y_norm):
    # y_norm: 0..1, 0=上,1=下 -> 強く(上)〜弱く(下)にするなら反転
    v = int(round(lerp(VELOCITY_MAX, VELOCITY_MIN, y_norm)))
    return clamp(v, VELOCITY_MIN, VELOCITY_MAX)

def build_chord_notes(chord_name, root_midi):
    intervals = CHORD_LIBRARY.get(chord_name, [])
    return tuple(root_midi + i for i in intervals)

# ====== MIDI 出力 ======
def open_midi_out(port_name_pref):
    outs = mido.get_output_names()
    target = None
    for n in outs:
        if port_name_pref in n:
            target = n
            break
    if target is None:
        print("利用可能なMIDI出力ポート:", outs)
        raise RuntimeError(f"MIDIポート '{port_name_pref}' が見つかりません")
    return mido.open_output(target)

def send_notes_off(port, notes):
    for n in notes:
        port.send(Message('note_off', note=n, velocity=0, channel=MIDI_CHANNEL))

def send_chord(port, notes, velocity):
    for n in notes:
        port.send(Message('note_on', note=n, velocity=velocity, channel=MIDI_CHANNEL))

# ====== メイン ======
def main():
    # MIDI
    try:
        midi_out = open_midi_out(MIDI_PORT_NAME)
        print(f"MIDI Port Opened: {midi_out.name}")
    except Exception as e:
        print("MIDI出力初期化に失敗:", e)
        sys.exit(1)

    # OSC（任意）
    if USE_OSC:
        osc_cli = udp_client.SimpleUDPClient(TD_OSC_TARGET[0], TD_OSC_TARGET[1])
    else:
        osc_cli = None

    # カメラ
    cap = cv2.VideoCapture(3)
    display_utils.setup_cv2_fullscreen('Face→Chord Controller')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # MediaPipe Face Mesh
    mp_face_mesh = mp.solutions.face_mesh
    mp_draw = mp.solutions.drawing_utils
    draw_spec = mp_draw.DrawingSpec(thickness=1, circle_radius=1)

    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True, # 唇や目の周りが詳細になる
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )

    last_confirmed = None
    same_counter = 0
    prev_notes = ()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)  # ミラー
            h, w = frame.shape[:2]

            # 推論
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = face_mesh.process(rgb)

            # デフォルト（顔が無い時は休符）
            target_name = "REST"
            target_root = BASE_ROOT
            target_velocity = 80
            
            # 表示用
            info_text = "REST"
            mouth_val = 0

            if res.multi_face_landmarks:
                faceLms = res.multi_face_landmarks[0] # 1人だけ対象

                # 口の開き具合
                mouth_val = get_mouth_openness(faceLms.landmark, h, w)

                # 顔の中心（鼻の頭）を計算
                nose = faceLms.landmark[NOSE_TIP]
                cx, cy = nose.x, nose.y

                # マッピング
                semitone = map_x_to_semitone(cx)
                velocity = map_y_to_velocity(cy)

                # 口開き具合→コード
                chord_name, root_offset = MOUTH_TO_CHORD.get(mouth_val, ("REST", 0))
                
                # ルート = BASE_ROOT + root_offset + X位置転調
                target_root = BASE_ROOT + root_offset + semitone
                target_name = chord_name
                target_velocity = velocity

                # 画面描画
                mp_draw.draw_landmarks(
                    frame, faceLms, mp_face_mesh.FACEMESH_TESSELATION,
                    draw_spec, draw_spec
                )
                
                # 口の状態を表示
                mouth_status_str = ["Closed", "Small", "Medium", "Large"][mouth_val]
                info_text = f"Mouth={mouth_status_str}({mouth_val}) | chord={target_name} | root={target_root} | vel={target_velocity}"

            # 安定化：同一ターゲットが続いたら確定
            candidate = (target_name, target_root, target_velocity)
            if candidate == last_confirmed:
                same_counter += 1
            else:
                same_counter = 1
                last_confirmed = candidate

            if same_counter >= STABILITY_FRAMES:
                # 確定：必要ならノート切替
                chord_name, root_midi, vel = candidate
                new_notes = build_chord_notes(chord_name, root_midi)

                if new_notes != prev_notes:
                    # NoteOff（前）
                    send_notes_off(midi_out, prev_notes)
                    # NoteOn（新）
                    if new_notes:
                        send_chord(midi_out, new_notes, vel)
                    prev_notes = new_notes

                    # TouchDesignerへOSC（任意）
                    if osc_cli:
                        osc_cli.send_message("/chord", [chord_name, int(root_midi), int(vel)])

            # 画面表示
            cv2.putText(frame, info_text, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("Face→Chord Controller", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    finally:
        # 終了処理
        send_notes_off(midi_out, prev_notes)
        midi_out.close()
        face_mesh.close()
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
