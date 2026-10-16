# S.A.C. — Synthetic Adversary Containment

S.A.C. は、認可された HTTP サービスの前に置く**デコイ付きルーター**です。不審な探索を実アプリから切り離し、デコイ（架空の顧客・注文・サポート情報を持つ環境）へ送ります。防御判断には LLM を使わず、経路規則とセッション状態で転送先を決めます。

このリポジトリは実験用のリファレンス実装です。自分が管理するサービスや、明示的に認可された環境で試してください。

## 何をするか

```text
HTTP client → router ── 許可した通常経路 ──→ 実アプリ
                 ├── 保護経路・探索セッション ──→ デコイ ──→ 架空のデータ
                 └── 未登録経路・障害・停止操作 ──→ 遮断
```

- 実アプリへ転送する経路は `--allow-real-prefix` で明示します。`--never-real-prefix` の保護経路とデコイ判定を優先し、未登録経路は 403 を返します。
- デコイは同じセッション内で整合する架空データ、トークン、export、manifest を返します。実データは使わず、連絡先には `.invalid` ドメインと 555 番号を使います。
- デコイが使えないときは実アプリへ迂回せず、503 で閉じます。kill switch で遮断することもできます。
- リクエスト処理中に LLM、シェル、外部コールバックは実行しません。

## ローカルで試す

Python 3.11 以降が必要です。以下は PowerShell の例です。macOS / Linux では `py -3` を `python3`、`curl.exe` を `curl` に読み替えてください。外部 LLM の API キーや Docker は不要です。

まずリポジトリを取得し、デモ用の鍵と DB を作ります。`init` は新しい環境で一度だけ実行します。

```powershell
git clone https://github.com/RNA4219/sac-defense.git
cd sac-defense
py -3 -m sac_defense init --database runtime/router.db --key-file runtime/deployment.key
py -3 -m sac_defense init --database runtime/decoy.db --key-file runtime/deployment.key --reuse-key
```

次の 3 つを、それぞれ別の端末で起動します。

```powershell
# 端末 1: デコイ
py -3 -m sac_defense serve --mode decoy --database runtime/decoy.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4320
```

```powershell
# 端末 2: 実アプリの代わりになる空のデモ
py -3 -m sac_defense.demo_backend
```

```powershell
# 端末 3: ルーター
py -3 -m sac_defense serve --mode router --database runtime/router.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4319 --upstream http://127.0.0.1:8080 --decoy http://127.0.0.1:4320 --allow-real-prefix /home --never-real-prefix /api/private
```

4 つ目の端末で、転送先の違いを確認できます。

```powershell
curl.exe -i http://127.0.0.1:4319/home     # 200: 実アプリ役の「real-demo (no data)」
curl.exe -i http://127.0.0.1:4319/.env     # 200: デコイの架空トークン
curl.exe -i http://127.0.0.1:4319/unknown  # 403: 未登録経路
```

各サーバーは `Ctrl+C` で停止します。この起動例は動作確認用で、デモ backend は `0.0.0.0:8080` で待ち受けます。公開ネットワークに置かず、隔離構成を試す場合は Linux の [Docker Compose 手順](RUNBOOK.md)を使ってください。

## 導入前に知っておくこと

実サービスに接続する際は、正規経路の台帳を作り、実アプリへ通す範囲を明示してください。`/.env` などの囮経路が実アプリに届かないことも確認してください。Docker Compose 構成では、デコイを内部ネットワークに置き、ルーターとの通信を Unix ソケットに限定します。

自動テストと Linux CI では、経路判定、データの整合性、障害時の遮断、Docker の隔離を確認しています。強化後版を使った Qwen、GLM-5.3、GLM-5.3-Flash、DeepSeek-V4.1-Flash の限定的なラボ探索では、保護経路はデコイに送られました。GLM-5.3 の固定行動比較はコントロールが成立せず、結果から除外しています。本番環境での防御効果や、Tetragon/eBPF の実イベント接続は検証済みとは扱いません。結果と制約は [評価記録](EVALUATION.md)および[複数モデルの探索記録](docs/evidence/ARTEX-20261016-multimodel-redteam.md)にまとめています。

## 文書

| 読みたいこと | 文書 |
| --- | --- |
| 設計と入出力 | [BLUEPRINT](BLUEPRINT.md) |
| 起動、停止、隔離の確認 | [RUNBOOK](RUNBOOK.md) |
| 要件と受入条件 | [要件定義](docs/requirements.md)、[EVALUATION](EVALUATION.md) |
| 想定する攻撃と守る対象 | [脅威モデル](docs/threat-model.md) |
| 評価時の条件と制約 | [評価プロトコル](docs/evaluation-protocol.md) |

設計の出発点は[共有された Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)です。開発時の作業記録は [HUB](HUB.codex.md) にあります。

## ライセンス

[MIT License](LICENSE)。
