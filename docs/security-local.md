# HTTPS・認証・CORS・IAM・静的配信

2026-11-14、Floci 2.4.0 / Caddy 2.11.9 / macOS / Colimaで検証。
AWS本番には接続せず、ローカルだけで動作させた。

```text
GitHub push/PR → GitHub Actions → frontend-dist
                                      ↓ 取得
ブラウザ → HTTPS localhost:8443（静的ファイル・公開設定）
    ├─ ログイン → 同一オリジンの /auth → Floci Cognito
    └─ Bearer JWT → HTTPS localhost:9443
                      → Floci HTTP API / JWT Authorizer
                      → コンテナLambda → 実モデル
```

## 確認したこと

| 対象 | 結果 |
| --- | --- |
| ローカルCAを指定したHTTPS接続 | 200、証明書検証を有効のまま確認 |
| CAを信頼しない接続・異なるホスト名 | 証明書エラーで拒否 |
| `app.wrime.test` の証明書SAN | 接続成功。ブラウザのプロセス内だけで名前解決を指定 |
| HTMLと公開設定 | HTMLはno-cache + ETag 304、config.jsonはno-store |
| ハッシュ付きJS/CSS | 長期キャッシュ・immutable |
| 正しいCognitoアクセストークン | API 200、両モデルを実行 |
| 認証なし・改ざん・異なるaudience・期限切れ | 401 |
| IDトークン（必要なscopeなし） | 403 |
| 許可オリジンのプリフライト | 204、許可Originを返す |
| 不許可オリジンのプリフライト | 許可Originを返さず、実ブラウザで読み取りが失敗 |
| IAMユーザーに権限なし | AccessDeniedException |
| ecr:DescribeRepositoriesを許可 | 200 |
| 許可していないecr:ListImages | AccessDeniedException |
| Allowと明示的Denyが両方ある | Denyを優先 |
| 登録したIAMキーの署名が不正 | InvalidSignatureException |

[機械検証の結果](security-report.json)。ユーザーパスワード・JWT・アクセスキーは記録しない。
IAMテストは `test` の特権バイパスではなく、新規登録したユーザーとキーで実行し、最後に削除する。
署名検証とIAM評価を明示的に有効化している。

ブラウザテストでは、ログイン失敗と成功、別オリジンの実推論、ログアウト、再読み込み時のトークン破棄、
モバイル表示、ポート8445と別ホスト名からのCORS拒否を確認する。
ローカルPython推論APIは使用しない。

## 起動

READMEのモデル準備、`make setup`、`make floci-images` を済ませる。
古いFloci設定が動いている場合は `make floci-down` してから起動する。

```bash
make floci-up
make security-up
make security-check
make security-browser
```

ログインは `.local/dev-user.json` に生成したユーザー名とパスワードを使う。
画面に必要なラベルだけを追加し、パスワードは公開設定やビルド成果物へ埋め込まない。
アクセストークンはlocalStorage/sessionStorageへ保存しない。有効期間は5分で、切れたら再ログインする。
期限切れテスト時だけローカルのCognito設定で1秒のトークンを発行し、直後に5分の設定へ戻す。

`make security-browser` は専用Chromiumプロセスで対象の証明書公開鍵だけを信頼する。
OSや通常ブラウザの信頼ストアは変更しない。通常ブラウザではローカル証明書の警告が出る。
証明書の期限は7日。更新はHTTPSサーバーを停止して `.local/security/certs` を削除し、再度 `make security-up` を実行する。

## GitHub連携とローカル自動配信

Checksワークフローはpush/PRでビルドし、`frontend-dist` 成果物を保存する。
成果物にはモデルやローカルの秘密情報を含めない。APIのURLと公開クライアントIDは配信時のconfig.jsonに分離する。

```bash
# 最新の成功ビルドを取得し、HTTPSサイトへ配置
make security-ci-deploy
# または特定の成功runを指定
.venv/bin/python scripts/deploy_ci.py --run-id RUN_ID
# 新しい成功ビルドを30秒おきに確認して自動配信
make security-ci-watch
```

取得先はこのGitHubリポジトリのChecksワークフローに限定する。
ダウンロードした成果物のスクリプトやnpmフックは実行せず、静的ファイルだけを配置する。
配信したHTMLと成果物の一致を確認し、run ID・コミット・SHA256を `.local/security/deployment.json` へ記録する。
AmplifyのGitHubアプリやWebhook自体を動かす実装ではない。

## 終了

監視プロセスはCtrl+C、HTTPSだけ停止する場合は `make security-down`。
全体を終了する場合は `make floci-down`。
ローカル証明書・ログイン情報は `.local` に残るがGitには含めない。

## 残る差

- Amplify/CloudFrontのサービス本体、世界各地のエッジ、公開DNS・ACMの運用は未再現。
- Cognito issuer/JWKS取得はFloci内部のHTTPループバックを許可している。本番AWSのissuerはHTTPS。
- ローカルの許可・拒否テストはAWSの全IAM仕様・サービス間ポリシーとの一致を保証しない。
- Floci ECRのDockerレジストリ認証は本番同等に強制されない。今回のIAM評価は管理APIでの確認。
- 画面とAPIの公開部分はHTTPS、Docker内のCaddy→FlociはHTTP。
- `make api` は単体開発用の認証なし推論アダプター。認証付き検証では起動しない。
