# WRIME CDK infrastructure

標準CDKの `DockerImageCode.fromImageAsset()` で、Dockerのビルド・共用ECRへのpush・Lambda更新を行う。

- `bin/infra.ts`: Appの作成・AWS環境の設定
- `lib/inference-stack.ts`: 推論Lambda・実行ロール・ログ（WrimeInference）
- `lambda-benchmark/`: Dockerfile・ハンドラー・実行手順
- `../.dockerignore`: DockerビルドとCDKアセットに含めるファイル
- `../../scripts/delete-assets.mjs`: このアプリのECRタグとS3オブジェクトを削除

```bash
npm ci
npm run build
npm run synth
```

リポジトリのルートで実行する。

```bash
make bootstrap # アカウント・リージョンごとに初回のみ
make deploy
make invoke
make destroy
```

デプロイにはDocker・モデル・AWS認証が必要。呼び出しとECR・S3の後片付けにはAWS CLIも必要。
型チェック・テンプレート生成にはDockerの起動とAWS認証は不要。
`make destroy` はLambda・実行ロール・ログを削除した後、共用ECRの `wrime-sentiment-demo-` で始まるタグを削除する。
共用S3の `wrime-sentiment-demo/` 以下も、全バージョン・削除マーカーを削除する。
更新前の同じ接頭辞のデータも対象。ローカルの記録ファイルは不要。共用ECR・S3自体や別アプリのデータは削除しない。
この変更前の接頭辞なしデータは対象外。S3の保存先変更は次回 `make deploy` から反映される。
詳しくは [構成と再実行手順](lambda-benchmark/README.md) を参照。
