# Harukaze 2026 Scene Controller

このディレクトリ(`test`)には、展示・体験用の様々なインタラクティブアート（Pygfx, OpenCV等）のシーン用Pythonスクリプトが含まれています。
また、これらのシーンをブラウザからリモートコントロールするためのStreamlitアプリケーション(`app.py`)が用意されています。

## 前提条件

- Python 3.10以上推奨
- カメラ（Webカメラ、またはiPhone等の外部カメラ）が接続されていること
- 必要なライブラリがインストールされていること

```bash
# 仮想環境を使用する場合（推奨）
python -m venv .venv
source .venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

## 起動方法

Streamlitを使用してWebブラウザからシーンを切り替えるには、**2つのプロセス**を同時に実行する必要があります。

### 手順1: Manager（メインシステム）の起動

`manager.py`はカメラ映像を解析（MediaPipe）し、実際の描画（Pygfxウィンドウ等）を行う裏方です。
ターミナルを1つ開き、以下を実行します。

```bash
cd test/
python manager.py
```
*※起動すると、メインディスプレイ側に初期シーンのウィンドウが表示されます。*

### 手順2: Streamlit Controller（Webリモコン）の起動

別のターミナル（タブ）を開き、同じディレクトリでStreamlitアプリを起動します。

```bash
cd test/
streamlit run app.py
```
*※実行すると自動的にブラウザが立ち上がり、「Harukaze 2026 Scene Controller」の画面が開きます。*

## 遊び方

1. ブラウザのStreamlit画面に、実行可能なシーンの一覧がボタンとして表示されています。
2. 好きなシーンの「▶」ボタンをクリックします。
3. 手順1で起動したメインディスプレイ側の映像が、即座に選んだシーンに切り替わります。

## 新しいシーンの追加方法

このリモコンシステムは、`test/` ディレクトリ内にある `*.py` ファイルを自動的にスキャンしてボタン化します。
（※ `manager.py`, `app.py`, `hand_tracker.py`, および `test_` で始まるファイルは除外されます）

新しいシーンを作成した場合は、このフォルダ内に `.py` ファイルを配置するだけで、自動的にStreamlitの画面にボタンが追加されます。

## 動作の仕組み

1. Streamlit(`app.py`)のボタンが押されると、対象のシーン名が `scene_control.json` に書き込まれます。
2. 背景で動いている `manager.py` は毎フレーム `scene_control.json` の更新日時を監視しています。
3. ファイルが更新されたことを検知すると、`manager.py`は現在表示中のシーンプロセスをキルし、ただちにお手元のJSONに書かれた新しいシーンプロセスを起動します。
