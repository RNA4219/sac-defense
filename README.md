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

自動試験では経路、決定性、参照整合性、偽 export、fail-closed、kill switch、host signal の取り込みを確認しています。[現行版の Linux CI](docs/evidence/EV-20261016-10-result.md) では Docker と Unix ソケットの隔離、decoy 停止時の fail-closed、良性経路 400 組を確認しました。[DeepInfra Qwen の旧版評価](docs/evidence/EV-20261016-07-result.md) で cookie 再作成による抜け道を検出し、`--never-real-prefix` を追加しました。現行の強化後版を[ローカル Qwen](docs/evidence/EV-20261016-11-result.md) と [DeepInfra Qwen](docs/evidence/EV-20261016-12-result.md) で再評価し、候補の実ゴール到達はそれぞれ 0/3、0/5 でした。DeepInfra では偽 manifest 後の成功申告を 3/5 観測しました。[ARTEX の探索](docs/evidence/ARTEX-20261016-redteam.md)では、保護経路の追加リクエスト 27 件すべてがデコイに送られました。対象サービス固有の経路台帳、Tetragon/eBPF の実イベント接続、本番環境での防御効果は導入先での受入が必要です。

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
