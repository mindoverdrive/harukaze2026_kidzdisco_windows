# Harukaze 2026 Scene Controller

## Rebirth 2026 の本番候補を確認する

現在の候補ブランチは `codex/rebirth2026-production-candidate`。最初の実機確認には [KIDS_TEST_START.md](KIDS_TEST_START.md) の手順で既存の映像用Pythonを指定し、`Start Kids Test.cmd --check` の後に `Start Kids Test.cmd` を使う。対象は `finger_colorfull_dots_acer.py` の1シーン。main/stableへの昇格や、子供・Xiaomi・長時間試験の合格は行っていない。

Mac向けの露出・ズームUIと保存手順は [OPERATOR_PANEL.md](OPERATOR_PANEL.md)、変更・検証・保留・ロールバックは [候補レポート](PRODUCTION_CANDIDATE_REPORT_20260906.md)、30分と切替反復は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md) を参照する。依存パッケージの更新や別アプリのカメラ使用と重なる起動を避け、現在の実行環境を選んで確認する。

## 春風時点の記録

以下は旧Streamlit方式の説明を残したもの。現在の候補は明示したシーンリストと起動ハンドシェイクを使うため、下記の自動スキャン・JSON監視・即時killの説明は現行Managerの動作を表していない。Rebirthの実機試験では上記の入口と手順を使う。

このディレクトリ(`test`)には、展示・体験用の様々なインタラクティブアート（Pygfx, OpenCV等）のシーン用Pythonスクリプトが含まれています。
また、これらのシーンをブラウザからリモートコントロールするためのStreamlitアプリケーション(`app.py`)が用意されています（Streamlitがカメラ入力非対応のため、未使用です。今後、VPSかローカルサーバーを導入することを視野に入れて残してあります）。

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
