# WRIME Sentiment Demo

日本語の文章を5段階の感情極性に分類するローカルWebアプリ。
WRIME Ver.2で追加学習したGemma 3 270MのLoRA・Full FTを比較する。

```text
ブラウザ → React + Vite → FastAPI → 学習済みモデル
```

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

macOSでXcodeライセンスのエラーが出る場合、インストール済みのCommand Line Toolsを指定して
`DEVELOPER_DIR=/Library/Developer/CommandLineTools make api` のように実行する。

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

感情極性は `-2, -1, 0, +1, +2`。softmaxの最大値に対応するクラスを返す。
確率は正答率を保証する値ではない。

- 空入力・不正JSON・10,000文字超過: 400
- 不明なモデル: 404
- 64KiB超のリクエスト本文: 413
- モデル未準備: 503

入力は特殊トークン込み512トークンに切り詰め、発生時は `truncated: true` を返す。
入力文章はアプリのログに保存しない。`GET /health` でAPIの起動を確認できる。

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

AWS Lambda + ECRで統合LoRAモデルの推論を検証済み。
AWS公開時はS3 + CloudFrontで画面を配信し、ブラウザからLambda Function URLを呼び出す。
公開版はLoRAのみ。ローカル版はLoRA・Full FTの比較に対応する。
初回応答は約14〜67秒、起動済み環境では約0.57〜0.77秒だった。
インフラはTypeScriptのAWS CDKで定義している。`make infra-check` で型とCloudFormationテンプレートを確認できる。
デプロイ・呼び出し・削除の手順は以下を参照。

```bash
make bootstrap # 初回のみ（上記の依存をインストール後）
make deploy   # フロントのビルド・配置、推論Lambdaのビルド・配置
make invoke   # 推論結果を確認
make destroy  # CloudFront・フロントS3（中身含む）・Lambda・アセットを削除
```

`make deploy` の出力 `FrontendUrl` をブラウザで開く。APIのURLはデプロイ時に `config.json` へ自動設定される。
Function URLは認証なしの公開APIで、CORSはCloudFrontの画面だけを許可する（CORSは認証ではない）。
使い終わったら `make destroy` を実行する。CloudFrontの削除には時間がかかる場合がある。

Dockerの起動・モデルの準備・AWS認証が必要。モデル入りイメージはCDK共用ECRに保存する。`make destroy` でこのアプリの接頭辞付きECRタグ・S3オブジェクトの全バージョンも削除する（変更前の接頭辞なしデータは対象外）。
