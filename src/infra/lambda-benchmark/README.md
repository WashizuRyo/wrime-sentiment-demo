# Lambda + CDK共用ECR

標準CDKの `WrimeInference` スタックで、推論Lambda・実行ロール・CloudWatch Logsを管理する。
`DockerImageCode.fromImageAsset()` により、CDKがDockerのビルド・ECRへのpush・Lambdaへの反映を行う。
専用ECRスタック・独自のSynthesizer・デプロイスクリプトは使わない。

イメージの保存先は、同じAWSアカウント・リージョンのCDKアプリが使うプライベート共用ECR。
ほかのAWSアカウントと共有したり公開したりする意味ではない。
アプリ専用S3や後片付け用Lambda、公開URL、API Gateway、VPCは作らない。

## 準備

Node.js 22.12以上、npm、起動済みのDocker、AWS認証が必要。呼び出しにはAWS CLIも必要。
`src/models/lora/` に統合LoRAモデルを用意する。
モデルはGit管理外だが、Dockerイメージに含めて共用ECRへ送信する。
`src/.dockerignore` で推論コード・Dockerfile・LoRAモデルだけをアセットに含める。

リポジトリのルートで実行する。

```bash
export AWS_REGION=ap-northeast-1
# 必要なら export AWS_PROFILE=使用するプロファイル名
npm --prefix src/infra ci
make bootstrap # アカウント・リージョンごとに初回のみ
```

macOSでXcodeライセンス確認に止まる場合は、各makeコマンドの前に
`DEVELOPER_DIR=/Library/Developer/CommandLineTools` を付ける。

## デプロイ・呼び出し

```bash
make deploy
make invoke
TEXT='最悪な一日だった' make invoke
```

`make deploy` は `npm --prefix src/infra run cdk -- deploy` を実行する。
CDKがARM64イメージをビルドし、共用ECRへpushした後にLambdaを作成・更新する。
コードやモデルが変わるとアセットのハッシュが変わり、`make deploy` で更新できる。
手動のDocker login・push、イメージタグの管理は不要。
標準 `DefaultStackSynthesizer` の `dockerTagPrefix` により、タグを `wrime-sentiment-demo-<ハッシュ>` にする。

初回の呼び出しはモデル読み込みに時間がかかる。同じ実行環境ではモデルを再利用する。
リクエスト・応答・メタデータは `.local/lambda-*.json` に保存する。
`benchmark.first_request_in_environment` と `environment_id` で初回か再利用かを確認できる。
`import_ms`、`model_load_ms`、`handler_ms` は読み込み等の内訳、`elapsed_ms` は分類処理の時間。
ARM64、メモリ3,008 MB、タイムアウト120秒。

## 削除

```bash
make destroy
```

まずCDKでLambda・実行ロール・ログを削除する。ログ保持期間は1日で、スタック削除時にも削除する。
続いて `scripts/delete-images.mjs` が以下を実行する。

1. `WrimeInference` スタックが存在しないことを確認（キャンセル時や確認失敗時はイメージを消さない）
2. `CDKToolkit` の出力から共用ECR名を取得
3. ECRから `wrime-sentiment-demo-` で始まるタグを全件取得し、100件ずつ削除

更新前の同じ接頭辞のタグも対象になり、ローカルでの履歴保存は不要。
同じ接頭辞を別アプリや別環境に流用しない。
ダイジェスト指定での削除は行わない。同じイメージに別アプリのタグがある場合、そのタグは残る。
最後のタグが削除されるとイメージ自体も削除される。共用ECR自体は削除しない。
途中で失敗した場合は再度 `make destroy` を実行できる。
`cdk destroy` を直接実行した場合はイメージ削除を行わないので、削除には `make destroy` を使う。

この変更前にpushした、接頭辞のない古いイメージは自動削除対象外。必要なら個別に確認して削除する。

`CDKToolkit`・共用S3・ECR・IAMも残る。S3内のデプロイ用テンプレート等は別途保存料金の対象となる。
手元のDockerイメージ・ビルドキャッシュも自動削除しない。

以前の専用ECR構成をデプロイしている場合、その `WrimeImages` スタックは新構成の `make destroy` では消えない。
共用ECRを使うLambdaへの更新が成功し、旧ECRを参照しなくなってから旧スタックを別途削除する。

## 定義の確認

```bash
make infra-check
```

型チェック・CloudFormationテンプレート生成を実行する。CIも同じ確認を行う。
Dockerの起動とAWS認証は不要。モデルのない環境でも生成は可能だが、実際のビルドにはモデルが必要。
生成先 `src/infra/cdk.out/` にはテンプレートとビルド用ファイルが保存される。
