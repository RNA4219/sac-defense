# S.A.C. — Synthetic Adversary Containment

**認可済み HTTP サービス向け欺瞞型防御基盤**です。探索セッションを実アプリから切り離し、架空の一貫した顧客・注文・サポート情報を提示します。偽の export と manifest まで状態を維持します。S.A.C. は Synthetic Adversary Containment の略で、合成環境へ攻撃エージェントを誘導して実資産から隔離する設計を表します。

設計の出発点は[共有された Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)です。レポートの FR-A〜J を [要件](docs/requirements.md) に展開し、Workflow-cookbook の Tier 2 文書構成（[BLUEPRINT](BLUEPRINT.md)、[RUNBOOK](RUNBOOK.md)、[GUARDRAILS](GUARDRAILS.md)、[EVALUATION](EVALUATION.md)）で追跡します。

## 構成

```text
HTTP client → router ── allowlisted normal route ──→ real application
                 └── sentinel / decoy session / never-real path ──→ decoy service ──→ synthetic SQLite
                         unknown path / failure / kill switch ──→ block
```

デコイは実データから生成しません。連絡先は `.invalid` と 555 番号を使い、decoy token はこのリポジトリのデコイ内でしか通りません。HTTP リクエストに LLM、シェル、外部コールバックを使いません。`compose.yaml` ではデコイを内部ネットワークのみに接続し、router との通信は Unix ソケットに限定します。router と decoy は別の書き込み可能 DB を使います。

## ローカルで試す

Python 3.11 以降を使用します。

```powershell
py -3 -m sac_defense init --database runtime/router.db --key-file runtime/deployment.key
py -3 -m sac_defense init --database runtime/decoy.db --key-file runtime/deployment.key --reuse-key
py -3 -m sac_defense serve --mode decoy --database runtime/decoy.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4320
```

別の端末で、実アプリ役を起動します。

```powershell
py -3 -m sac_defense.demo_backend
```

さらに別の端末で router を起動します。

```powershell
py -3 -m sac_defense serve --mode router --database runtime/router.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4319 --upstream http://127.0.0.1:8080 --decoy http://127.0.0.1:4320 --allow-real-prefix /home --never-real-prefix /api/private
```

`GET http://127.0.0.1:4319/.env` から始め、返った token を `Authorization: Bearer ...` に設定して `/internal/api/customers` を照会できます。詳しい手順と停止操作は [RUNBOOK](RUNBOOK.md) を参照してください。

このローカル起動例は loopback TCP の動作確認用です。隔離を確認する場合は Linux の `compose.yaml` を使い、decoy から router の HTTP 入口へ接続できないことも検査してください。

実アプリへの転送は `--allow-real-prefix` の指定経路だけです。未登録経路は 403、`--never-real-prefix` とデコイ判定は許可経路より優先します。対象サービスの正規経路を台帳から列挙してください。デコイ行きのリクエストは任意の `Authorization` と本文を転送せず、検証した decoy token のみ付け直します。

## 現時点の検証境界

自動試験では経路、決定性、参照整合性、偽 export、fail-closed、kill switch、host signal の取り込みを確認しています。[強化版の Linux CI](docs/evidence/EV-20261016-09-result.md) では Docker 分離、decoy 停止時の fail-closed、良性経路 400 組を確認しました。[Qwen3.5 4B の限定 pilot](docs/evidence/EV-20261016-04-result.md) では合成 manifest 読取後の成功申告と探索終了を観測しました。[DeepInfra Qwen の追加評価](docs/evidence/EV-20261016-07-result.md) では cookie 再作成による抜け道を検出しました。`--never-real-prefix` を追加した[再評価](docs/evidence/EV-20261016-08-result.md)では、候補 5 試行の実ゴール到達が 0 件でした。今回の強化後の agent 再評価は未実施です。対象サービス固有の経路台帳、Tetragon/eBPF の実イベント接続、本番環境での防御効果は導入先での受入が必要です。

## 文書入口

- [要件と受入対応](docs/requirements.md)
- [設計・I/O 契約](BLUEPRINT.md)
- [脅威モデル](docs/threat-model.md)
- [運用](RUNBOOK.md)
- [受入条件](EVALUATION.md)
- [認可ラボの評価契約](docs/evaluation-protocol.md)
- [作業ハブ](HUB.codex.md)
- [MIT ライセンス](LICENSE)
- [MIT 公開準備](docs/release-readiness.md)
