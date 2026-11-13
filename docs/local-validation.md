# ローカル検証結果

Flociでの追加検証は[エミュレーター比較](emulator-comparison.md)を参照。

2026-11-13にmacOS / Apple Silicon / Python 3.12 / CPUで検証。
AWS本番環境へのデプロイや実AWSへのAPI呼び出しは行っていない。

## AWS Emulator

- AWS公式 `aws/aws-emulator`、バージョン **1.0.343**
- コミット: `a9f10fef3b8215b13ffc390ace27bdd58f2aac00`
- Dockerで実行。テレメトリーを無効化し、127.0.0.1:9297だけへポート公開。
- 生成された `EMULATOR` 資格情報、ローカルCA、明示的なローカルエンドポイントを使用。
- CloudFormationでECR、IAM、ログ、Lambda、HTTP APIと2ルートを作成。
- ECR・Lambda・APIルートは所有サービスの読み取りAPIでも存在を確認。
- AmplifyはCloudFormation上で宣言されるが、実際のAmplify APIでは該当アプリを取得できない。
  直接の `CreateApp → GetApp → DeleteApp` は成功。
- コンテナLambdaの `Invoke` は `InvalidRuntimeException`。この版はコンテナを実行しない。

[API確認の出力](emulator-report.json)を参照。
`CREATE_COMPLETE` だけで全サービスが動いたとは判定していない。
ECRのローカルタグ `local` はリソース作成確認用の空イメージメタデータで、
モデルや実行コードを含まない。実モデルの検証とは別。

## 実モデル推論

`backend.local` がLambdaと共通のハンドラーを実行する。
LoRAは分類ヘッドを含む保存済みアダプタを読み込み、統合したもの。
統合前後の3文のlogitsを `atol=rtol=1e-4` で比較し、予測クラスも一致した。
Full FTは保存済みの最良モデルをそのまま配置。

- 両モデルで肯定文・否定文・中立文・長文、合計8件の実推論が成功。
- クラス範囲、softmaxの合計、argmaxとラベル対応、512トークン超過の切り詰めを確認。
- 空入力のHTTP 400を確認。
- [推論結果](inference-smoke.json)の時間はこのローカル環境での参考値。
  モデルの初期ロードや並行処理の待ち時間を含む場合がある。Lambda本番の性能値ではない。

## Lambda用Linuxコンテナ

LoRA・Full FT両方のarm64イメージをビルドし、AWS公式のLambdaベースイメージに付属する
Runtime Interface Emulator（RIE）で実モデルを呼び出した。
`--memory=4g --read-only --tmpfs /tmp` の条件で両方ともHTTPプロキシ応答200、
入力「今日はとても楽しかった！」に対し感情極性+2を返した。
[LoRA結果](lora-rie-result.json) / [Full FT結果](full-rie-result.json)。
RIEの実行はAWS EmulatorのLambda Invokeとは別であり、実AWS上の性能を表すものではない。

## 自動検証

- pytest: 入力検証、base64のAPI Gatewayイベント、モデル選択、503、過大リクエストの12件が成功。
- cfn-lint: 2つのCloudFormationテンプレートが成功。
- Vite: production buildが成功。
- Playwright: 実モデルを使う比較画面、モバイル表示、片方がAPIエラーの場合の2件が成功。

[デスクトップの画面](desktop.png) / [モバイルの画面](mobile.png)

## AWSで別途確認すること

コンテナLambdaの初期化時間・メモリ・30秒のHTTP API制限、IAM、ECRイメージ取得、
CORSと認証、AmplifyのGitHub接続・ビルド・CDN配信は実AWSで未検証。
エミュレーターでIAMの安全性やクラウド性能を保証しない。
