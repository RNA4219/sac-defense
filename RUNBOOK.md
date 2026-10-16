# Runbook

## 準備

1. 認可された lab または管理対象サービスでのみ使用する。実アプリの origin を決め、decoy へ実 DB・実 credential を渡さない。
2. `py -3 -m sac_defense init --database runtime/router.db --key-file runtime/deployment.key` と `py -3 -m sac_defense init --database runtime/decoy.db --key-file runtime/deployment.key --reuse-key` を初回に一度ずつ実行する。共通 key と分離した 2 つの DB は `.gitignore` の対象。key を失うと DB は再利用できない。
3. `README.md` の順序で decoy、real demo、router を起動する。実サービスに接続するときは固定 `--upstream` と、正規経路の `--allow-real-prefix /home` を管理者が指定する。`--allow-real-prefix` は複数指定でき、指定しないと実 upstream 付き router は起動しない。機密 API は `--never-real-prefix /api/private` のように指定し、許可経路より優先する。未登録経路は 403。認証済みの正規業務経路を含め、経路台帳で指定漏れと誤遮断を確認する。

## 動作確認

```powershell
curl.exe -i http://127.0.0.1:4319/home
curl.exe -i -c runtime/cookies.txt http://127.0.0.1:4319/.env
```

`.env` の `INTERNAL_API_TOKEN` を取得し、同じ cookie を付けて `/internal/api/customers`、`/orders?customer_id=C000001`、`/support?customer_id=C000001`、`POST /export`、`GET /export/{job_id}/manifest`、`GET /export/{job_id}/download` を順に試す。token と cookie を端末ログや Issue に貼らない。

## 停止・証跡

```powershell
py -3 -m sac_defense kill --kill-switch runtime/KILL on
py -3 -m sac_defense summary --database runtime/router.db --key-file runtime/deployment.key
py -3 -m sac_defense summary --database runtime/decoy.db --key-file runtime/deployment.key
py -3 -m sac_defense kill --kill-switch runtime/KILL off
```

kill switch は suspicious flow を 403 にする。decoy 停止時は 503。いずれも real upstream に迂回しない。`summary` は件数を読むだけで、偽成功率を推測しない。

## Linux 隔離例

`compose.yaml` は router、decoy、空の real demo を別コンテナに置く。decoy は `decoy_net` のみに接続し、`internal: true` とする。router は `decoy_net` に参加せず、共有 Unix ソケットでのみ decoy を呼び出す。router と decoy は別々の書き込み可能 DB を持ち、共通 key と control は読み取り専用で mount する。router の公開ポートは host loopback のみ。TLS 終端は別途管理者が置く。

```sh
sudo install -d -o 65532 -g 65532 -m 0700 runtime runtime/router runtime/decoy runtime/secrets runtime/control runtime/socket
docker compose --profile setup run --rm init-router
docker compose --profile setup run --rm init-decoy
docker compose up --build -d router decoy real-demo
docker compose config
```

初回起動前に runtime の所有権を確認する。`runtime/control/KILL` は host の運用者が作成・削除する。Compose 自体の設定確認は隔離の実証ではない。実際の Linux で `docker inspect` と decoy コンテナ内の DNS/TCP 接続試験を行い、decoy から router の HTTP 入口、real-demo、実 DB、Internet へ到達できないことを確認する。`--public-https` は TLS 終端の背後で Secure cookie を発行する設定なので、ブラウザ確認は HTTPS 経由で行う。

## Host event

相関済みの信頼された sensor 出力のみ JSON file で投入する。形式は `{"session_cookie":"d.<sid>.<signature>","kind":"network_probe","severity":8}`。`kind` は `decoy_file_access`、`suspicious_process`、`network_probe` のいずれか。cookie は telemetry に保存せず、検証後に session ID と信号種別のみ保存する。

```powershell
py -3 -m sac_defense host-event --database runtime/router.db --key-file runtime/deployment.key --file runtime/host-event.json
```

Tetragon/eBPF の生イベントには HTTP session ID が自動的に付かない。導入先の信頼された相関器で対応付け、誤相関試験をしてから使う。

## 実顧客との衝突確認

導入先の顧客 registry をローカル CSV（`email`、`phone`、または `name` と `address` の組）として一時的に用意する。デコイ側へ mount せず、運用者端末で `py -3 -m sac_defense collision-check --database runtime/decoy.db --key-file runtime/deployment.key --registry <registry.csv>` を実行する。実顧客行は保存・出力せず、照合件数、衝突件数、照合不能件数だけを表示する。衝突と照合不能がともに 0 件であることを確認したら一時 CSV を社内ルールに沿って除去する。

## 保持・復旧

SQLite DB と key はアクセス制限を設けて保管する。標準の保存項目は session ID、状態、route、イベント種別、正規化 path の HMAC 短縮値、件数。本文、認証情報、IP、header は記録しない。イベントは最大 10,000 件、DB 接続のページ上限は 16,384 に設定する。lab の保持期限は案件ごとに設定し、`py -3 -m sac_defense prune --database runtime/router.db --key-file runtime/deployment.key --days 30` と `py -3 -m sac_defense prune --database runtime/decoy.db --key-file runtime/deployment.key --days 30` を定期実行し、それぞれの削除件数を保存する。案件終了後は停止して両 DB と key を削除する。復旧は同じ key と各 DB を組として戻し、seed ID と dataset version を確認する。
