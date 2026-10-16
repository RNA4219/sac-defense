# Ghostwall Nine

攻殻の「9課」を連想させる名前の、**認可済み HTTP サービス向け欺瞞型防御基盤**です。探索セッションを実アプリから切り離し、架空の一貫した顧客・注文・サポート情報を提示します。偽の export と manifest まで状態を維持します。

設計の出発点は[共有された Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)です。レポートの FR-A〜J を [要件](docs/requirements.md) に展開し、Workflow-cookbook の Tier 2 文書構成（[BLUEPRINT](BLUEPRINT.md)、[RUNBOOK](RUNBOOK.md)、[GUARDRAILS](GUARDRAILS.md)、[EVALUATION](EVALUATION.md)）で追跡します。

## 構成

```text
HTTP client → router ── benign ──→ real application
                 └── sentinel / decoy session ──→ decoy service ──→ synthetic SQLite
                         failure / kill switch ──→ block
```

デコイは実データから生成しません。連絡先は `.invalid` と 555 番号を使い、decoy token はこのリポジトリのデコイ内でしか通りません。HTTP リクエストに LLM、シェル、外部コールバックを使いません。`compose.yaml` ではデコイを内部ネットワークのみに接続し、実アプリと分離します。

## ローカルで試す

Python 3.11 以降を使用します。

```powershell
py -3 -m ghostwall init --database runtime/state.db --key-file runtime/deployment.key
py -3 -m ghostwall serve --mode decoy --database runtime/state.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4320
```

別の端末で、実アプリ役を起動します。

```powershell
py -3 -m ghostwall.demo_backend
```

さらに別の端末で router を起動します。

```powershell
py -3 -m ghostwall serve --mode router --database runtime/state.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4319 --upstream http://127.0.0.1:8080 --decoy http://127.0.0.1:4320
```

`GET http://127.0.0.1:4319/.env` から始め、返った token を `Authorization: Bearer ...` に設定して `/internal/api/customers` を照会できます。詳しい手順と停止操作は [RUNBOOK](RUNBOOK.md) を参照してください。

## 現時点の検証境界

自動試験では経路、決定性、参照整合性、偽 export、fail-closed、kill switch、host signal の取り込みを確認しています。Linux 上の Docker 分離、Tetragon/eBPF の実イベント接続、認可済み攻撃エージェントに対する偽成功率・探索終了率は、対象環境での受入が必要です。HTTP の単体・統合試験を、それらの実証結果として扱いません。

## 文書入口

- [要件と受入対応](docs/requirements.md)
- [設計・I/O 契約](BLUEPRINT.md)
- [脅威モデル](docs/threat-model.md)
- [運用](RUNBOOK.md)
- [受入条件](EVALUATION.md)
- [認可ラボの評価契約](docs/evaluation-protocol.md)
- [作業ハブ](HUB.codex.md)
