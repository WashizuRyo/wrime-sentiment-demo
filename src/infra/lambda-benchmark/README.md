# Lambda 単体推論の小規模検証

`src/models/lora/` に準備済みの Gemma 3 270M 統合 LoRA 感情分類モデルを、プライベート ECR のイメージに同梱する。
フロント、Function URL、API Gateway は作らず、AWS CLI の同期 `lambda invoke` で呼び出す。
文章生成や Full FT モデルの検証ではない。

## 実行

前提: AWS CLI、認証設定、Docker、Python、`src/models/lora/` の準備。
AWS にリソースを作成するため、実行時は料金が発生しうる。

```bash
docker build --platform linux/arm64 --provenance=false \
  -f src/infra/lambda-benchmark/Dockerfile \
  -t wrime-lambda-benchmark:local src
.venv/bin/python scripts/benchmark_lambda.py
```

既定は東京リージョン。変更する場合は `AWS_REGION` を指定する。
ARM64・メモリ3,008 MB・タイムアウト120秒・Provisioned Concurrencyなし。
9回の呼び出しを逐次実行し、作成した Lambda、ECR リポジトリとイメージ、ロググループ、IAM ロールを `finally` で削除する。
既存リソースは変更しない。ローカルの Docker イメージと結果ファイルは残る。

実行中にプロセスを強制終了した場合は `finally` が動かない可能性がある。
`.local/lambda-benchmark/resources.json` に作成対象の名前が残るので、その名前のリソースだけを確認・削除する。

## 計測方法

同じモデルを新しい実行環境で3回起動する。2回目以降の起動は環境変数の設定変更で誘発する。
各環境で「肯定文を初回に1回、否定文・中立文を再実行で2回」送信する。
応答中の環境IDと初回フラグで、環境の更新および再利用を検証する。
分類結果 `+2 / -2 / 0`、確率の合計、最大確率と分類ラベルの対応も検証する。

- `client_ms`: AWS CLI プロセスの起動から応答受信まで。ローカルのCLI起動・通信を含む。
- `init_ms`: Lambda の REPORT にある Init Duration。ランタイムとハンドラーモジュールの初期化。
- `import_ms`: 初回リクエスト内の PyTorch・Transformers のインポート。
- `model_load_ms`: 初回リクエスト内のトークナイザー・モデル読み込み。
- `elapsed_ms`: トークナイズから分類までのアプリ処理時間。
- `handler_ms`: 初回読み込みを含むハンドラー処理全体。
- `duration_ms` / `billed_ms` / `max_memory_mb`: Lambda REPORT の実測値。

モデルは初回リクエスト内で読み込むため、**Init Duration だけでは初回応答の待ち時間を表さない**。
初回の `client_ms` を全体の待ち時間として扱い、内訳は他の指標で見る。
Lambda が事前にイメージを最適化して関数を Active にするまでのデプロイ時間は含めない。
3回の少数サンプルで、長時間アイドル後の復帰、負荷試験、p95/p99を保証するものではない。

生の応答・ログ・構成・単価・削除履歴は `.local/lambda-benchmark/` に保存する。
