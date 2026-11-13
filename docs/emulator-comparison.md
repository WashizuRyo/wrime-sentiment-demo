# エミュレーター比較

2026-11-13、macOS / Apple Silicon / Colima上で比較した。
AWS本番へのデプロイやAPI呼び出しは行っていない。

| 検証項目 | AWS Emulator 1.0.343 | Floci 2.4.0 |
| --- | --- | --- |
| CloudFormationでECR・Lambda・HTTP APIを作成 | 成功 | 成功 |
| コンテナLambdaのInvoke | InvalidRuntimeException | 両モデルの実推論が成功 |
| HTTP APIからコンテナLambdaを実行 | コンテナ実行が未対応のため未検証 | 両モデルで成功 |
| 画面 → エミュレーターHTTP API → Lambda | 未検証。ローカルPython APIで代用 | ブラウザE2E 2件が成功 |
| ECRへの実モデルpush/pull | 未検証（空イメージのメタデータのみ） | 両モデルで成功。重み全量のSHA256照合も成功 |
| AmplifyのCloudFormation作成 | 宣言だけで実体なし | 厳格モードでCREATE_FAILED |
| Amplifyの直接API | CreateApp/GetApp/DeleteAppが成功 | ListAppsがUnknownOperationException |
| Amplifyのビルド・CDN配信 | 未検証 | 未検証 |

LocalStackの現行版は公式資料上で起動に認証トークンが必要なため、今回は実行していない。
無料で登録なしに動かせるFlociを実際の比較対象にした。

## Flociで成功した経路

```text
ブラウザ（React）
  → ViteのHTTPプロキシ
  → FlociのAPI Gateway v2 HTTP API
  → Dockerコンテナで動くLambdaハンドラー
  → 保存済みLoRA統合モデル / Full FTモデル
```

ローカルPython APIを停止し、ポート8000に接続できない状態でブラウザテストを実行した。
通常の `make frontend` と異なり、`make frontend-floci` はFlociのHTTP APIをプロキシ先に設定する。
推論を直接Pythonへ迂回させてはいない。画面自体の配信はViteのまま。

- CloudFormationでレジストリ用・アプリ用の2スタックを作成。
- LambdaのPackageTypeがImageであることを所有サービスAPIで確認。
- Lambda Invokeで両モデルのHTTPプロキシ応答200とJSONデコードを確認。
- HTTP API経由で、各モデルに肯定・否定・中立・長文の4件、合計8件を入力。
- クラス番号、確率の合計、argmax、512トークンでの切り詰めを検証。
- 空入力の400、片方のAPIが503の場合に他方の結果を残す画面を確認。
- スタック削除とCompose停止で、Lambda子コンテナ・レジストリ・Flociが停止することを確認。

[実測出力](floci-report.json)。応答時間はローカル環境の参考値で、実AWSの性能を表さない。

## 成功扱いにしない部分

`FLOCI_SERVICES_CLOUDFORMATION_ALLOW_STUB_UNSUPPORTED_RESOURCE_TYPES=false` を設定した。
Amplifyを含むテンプレートは実際に `CREATE_FAILED` / `ROLLBACK_COMPLETE` となる。
[Amplify単体スタックの結果](floci-amplify-probe.json)も記録した。

本番用テンプレートに `EnableHosting` パラメータを追加し、Flociではfalseを渡している。
既定値はtrueなので、本番や従来のAWS EmulatorではAmplifyの宣言を維持する。

モデル入りイメージは、`wrime-lora:local` / `wrime-full:local` をFlociのECRへ実際にpushする。
Docker pull、モデルレイヤー全量のダウンロード、重みファイルのSHA256照合を実施した。
Lambda起動前にレジストリURIのローカルタグを削除し、Flociログのpullと、その後の実推論を確認した。
詳細は[ECRの検証結果](ecr-roundtrip.md)を参照。
AmplifyのCDN、IAMの本番相当の制御、実AWSでのコールドスタートも未検証。

## 再実行

READMEの「FlociでAPI GatewayとLambdaまで通す」の手順を参照。
AWS Emulatorのポート9297とFlociの4566は別で、両方を同時に起動できる。
実AWSの資格情報は読み込まず、接続先はローカルに固定している。

## 根拠資料

- [Floci 2.4.0 Lambdaのローカルイメージ利用](https://github.com/floci-io/floci/blob/2.4.0/docs/services/lambda.md#locally-built-images)
- [Floci 2.4.0 CloudFormationの未対応タイプ](https://github.com/floci-io/floci/blob/2.4.0/docs/services/cloudformation.md)
- [Floci 2.4.0 ECRの実装範囲](https://github.com/floci-io/floci/blob/2.4.0/docs/services/ecr.md)
- [LocalStackの認証トークン](https://docs.localstack.cloud/aws/getting-started/auth-token/)
