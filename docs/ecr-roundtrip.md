# ECRのpush/pull検証

2026-11-13、Floci 2.4.0 / macOS / Apple Silicon / Colimaで実施。
実AWSではなく、ローカルECRエミュレーターへの転送を検証した。

```text
モデル入りDockerイメージ
  → docker push
  → Floci ECRのレジストリ
  → docker pull・マニフェスト照合
  → レジストリURIのローカルタグを削除
  → LambdaがECRからpull
  → API Gateway経由で感情分析
```

| 確認項目 | LoRA | Full FT |
| --- | --- | --- |
| Docker push / pull | 成功 | 成功 |
| ECR経由で転送・照合した圧縮モデルレイヤー | 514,124,904 bytes | 697,303,472 bytes |
| 展開後にSHA256照合した重み | 1,072,432,144 bytes | 1,072,432,144 bytes |
| pullしたイメージのマニフェスト一致 | 成功 | 成功 |
| Lambdaによるレジストリからの取得ログ | 確認 | 確認 |
| 取得後のLambda直接Invoke・HTTP API経由の実推論 | 成功 | 成功 |

[実測データとハッシュ](ecr-roundtrip.json) / [取得後の推論結果](floci-report.json)

## キャッシュとの区別

Docker pullでは既存レイヤーがキャッシュされる場合がある。
そのため、pullの成功だけではモデル全量のダウンロードを証明した扱いにしていない。

別途 `GetDownloadUrlForLayer` でモデルを含むレイヤーを取得し、ストリーミングで全量を読み取った。
圧縮レイヤーのサイズとSHA256をマニフェストに照合し、tarをメモリ上で順に展開して
`model.safetensors` のサイズとSHA256も元のモデルに照合した。
展開ファイルをディスクへ書き出してはいない。

`FLOCI_SERVICES_ECR_PREFER_LOCAL_IMAGES=false` を設定し、Lambda起動前には
レジストリURIのタグを削除する。Lambdaのコールドスタート時に
`Pulling image: localhost:4566/...` が出たことをログから確認する。
元の `wrime-lora:local` / `wrime-full:local` は消さない。

## 再実行

モデルとLambdaイメージを準備後、READMEの `make floci-up` を実行する。
`scripts/ecr_images.py` がpush、ダウンロード、照合、pullを行い、
`scripts/floci.py` がCloudFormationでLambdaを作成して推論を検証する。
結果は `.local/ecr-roundtrip.json` と `.local/floci-report.json` に保存される。
進捗は `.local/ecr-*-push.log` / `.local/ecr-*-pull.log` で確認できる。

再実行する場合は先に `make floci-down` し、スタックとレジストリを作り直す。
タグはIMMUTABLEなので、同じタグへの再pushで上書きしない。
途中で失敗した場合はアプリ用スタックが未作成のことがあり、その場合も
作成済みのレジストリ用スタックを削除してから再実行する。

## 本番と異なる部分

- ローカルHTTPのパス形式URIを使う。AWS本番ECRのHTTPSは未検証。
- GetAuthorizationTokenとdocker loginは実行するが、レジストリのDocker認証は本番相当には強制されない。ECR管理APIのIAM・署名評価は[追加検証](security-local.md)で確認。
- Dockerのログイン情報は `.local/floci-docker` に隔離し、通常のDocker設定は変更しない。
- Dockerレジストリやモデルのディスク容量は追加で必要。実AWSの保存料金は発生しない。
- Amplify/CDNそのものは未対応。画面は[追加実装](security-local.md)でビルド済みファイルをHTTPS配信できる。

[Floci ECRの公式資料](https://github.com/floci-io/floci/blob/2.4.0/docs/services/ecr.md)
