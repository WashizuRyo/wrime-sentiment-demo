# WRIME Sentiment Demo

日本語の文章を5段階の感情極性に分類するローカルWebアプリ。
WRIME Ver.2で追加学習したGemma 3 270MのLoRA・Full FTを比較する。

## 起動

前提: Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22.12以降。

```bash
make setup
npm --prefix src/frontend ci
npm --prefix src/infra ci
```

Pythonの依存定義（`requirements.txt`・`requirements.lock`）と仮想環境（`.venv/`）は `src/backend/` に配置する。

モデル準備済みなら、ターミナルを2つ使って起動する。

```bash
# ターミナル1: 推論API
make api
```

```bash
# ターミナル2: 画面
make frontend
```

画面: **http://127.0.0.1:5173**
API: **http://127.0.0.1:8000**

ログインは不要。Viteが `/predict/*` をFastAPIへ転送する。
初回の分析はモデルの読み込みに時間がかかる。停止は各ターミナルでCtrl+C。

## モデルの準備

以下を別途ローカルに用意する。

- 卒論リポジトリの `thesis/experiments/full_finetuning/models/best_model`
- 同 `thesis/experiments/lora/models/best_adapter`
- 元の `google/gemma-3-270m` のローカルスナップショット（重み・設定）

```bash
src/backend/.venv/bin/python scripts/prepare_models.py \
  --thesis-root /path/to/sentimental \
  --base-model /path/to/local/gemma-3-270m-snapshot
```

LoRAは分類ヘッドを含むアダプタを統合し、統合前後のlogitsを比較する。
`src/models/lora` と `src/models/full` に推論用ファイルを作る。保存には約2.1GB必要。
既存の出力は上書きしない。準備スクリプトの保存先は `--output` で変更できるが、APIの読み込み先は `src/models/` に固定している。
モデルは起動後に初めて使う際に読み込み、以降はメモリ上で再利用する。
モデルはローカルに保持し、`src/models/` と重みファイルはGitの管理対象から除外する。

## API

`POST /predict/lora` または `POST /predict/full`

```bash
curl http://127.0.0.1:8000/predict/lora \
  -H 'Content-Type: application/json' \
  -d '{"text":"今日はとても楽しかった！"}'
```

応答例（数値は説明用）:

```json
{
  "model": "lora",
  "model_version": "7d55d679e1c3",
  "sentiment": 2,
  "probabilities": {"-2": 0.01, "-1": 0.02, "0": 0.07, "1": 0.25, "2": 0.65},
  "truncated": false,
  "elapsed_ms": 30.0
}
```

## ビルド

```bash
make build
```

GitHub Actionsではフロントの型チェック（`npm --prefix src/frontend run check`）とビルドを実行する。

## ファイル構成

```text
src/
  backend/   FastAPI・モデルの推論処理
  frontend/  Reactの画面・Vite設定
  infra/     TypeScriptのCDK定義・Lambda用コンテナ・実行手順
  models/    LoRA・Full FTの推論用モデル（Git管理外）
scripts/     モデル準備
```

AWS版もLoRA・Full FT・両方の比較に対応する。S3 + CloudFrontで画面を配信し、
Lambdaコンテナに両モデルを同梱する。ブラウザは画面と同じCloudFrontドメインの
`POST /predict/lora` または `POST /predict/full` を呼び出す。
CloudFrontはOACでリクエストを署名し、IAM認証付きのLambda Function URLへ転送する。
AWS版の画面はPOST本文のSHA-256を `x-amz-content-sha256` ヘッダーに付ける。
Lambdaのメモリは3008MBを割り当てる。Dockerの起動・両モデルの準備・AWS認証が必要。

```bash
make bootstrap # 初回のみ（上記の依存をインストール後）
make deploy   # フロントのビルド・配置、推論Lambdaのビルド・配置
make invoke   # 推論結果を確認
MODEL=full make invoke # Full FTの推論結果を確認（省略時はLoRA）
make destroy  # CloudFront・フロントS3（中身含む）・Lambda・アセットを削除
```

`make deploy` の出力 `FrontendUrl` を開くと、画面でモデルを選択できる。
Lambdaの直接呼び出しでは `{"text":"今日は楽しかった！","model":"full"}` のように指定する。
