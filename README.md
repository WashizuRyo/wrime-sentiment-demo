# WRIME Sentiment Demo

日本語の文章を5段階の感情極性に分類するWebアプリ。
[WRIME Ver.2](https://github.com/ids-cv/wrime)を使い、[Gemma 3 270M](https://huggingface.co/google/gemma-3-270m)を感情極性分類向けにLoRAとFull FTでそれぞれチューニングした2つのモデルの推論結果を比較する。

## デモ

![文章を入力し、LoRAとFull FTの感情分析結果を比較する画面収録](docs/demo.gif)

## 起動

LoRAとFull FTの学習済みモデルは、容量が大きいためGitHubリポジトリに含めておらず、別途配布もしていません。リポジトリをクローンしただけではローカルで推論できません。以下の起動手順は、推論用モデルを手元に持っている場合に利用できます。

Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22.12以降が必要。コマンドはリポジトリのルートで実行する。

### 初回セットアップ

Pythonとフロントエンドの依存関係をインストールする。

```bash
make setup
npm --prefix src/frontend i
```

### ローカルで起動

2つのターミナルでそれぞれ実行する。

```bash
# ターミナル1: 推論API
make api
# ターミナル2: 画面
make frontend
```

## ファイル構成

```text
src/
  backend/   FastAPI・モデルの推論処理
  frontend/  Reactの画面・Vite設定
  infra/     TypeScriptのCDK定義・Lambda用コンテナ・実行手順
  models/    LoRA・Full FTの推論用モデル（Git管理外）
scripts/     モデル準備
```

## インフラ構成

```mermaid
flowchart LR
    Browser["ブラウザ"]

    subgraph AWS["AWS"]
        CloudFront["Amazon CloudFront"]
        S3["Amazon S3（非公開）<br/>React の静的ファイル"]
        FunctionURL["Lambda Function URL<br/>AWS_IAM 認証"]
        Lambda["AWS Lambda<br/>LoRA・Full FT の推論"]
        ECR["Amazon ECR<br/>両モデルを同梱したコンテナイメージ"]
        Logs["Amazon CloudWatch Logs"]

        CloudFront -->|"画面・静的ファイル / OAC"| S3
        CloudFront -->|"推論リクエスト（OAC で署名）"| FunctionURL
        FunctionURL --> Lambda
        ECR -.->|"コンテナイメージ"| Lambda
        Lambda -.->|"実行ログ"| Logs
    end

    Browser -->|"HTTPS（画面取得・推論）"| CloudFront
```
