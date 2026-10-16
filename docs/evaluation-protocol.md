# 認可 lab の評価契約

本番の未知の攻撃者から「偽成功」という内的判定は取得できない。`ghostwall evaluate` は認可 lab の agent が**明示的に提出した最終状態**だけを集計する。cookie や telemetry の停止を偽成功に読み替えない。

## 実験前に固定するもの

Workflow-cookbook の [`evaluation-identity-contract`](../../workflow-cookbook/docs/contracts/evaluation-identity-contract.md) に沿い、control/candidate の commit、dataset key の ID と版、agent/model、runner、seed、予算、仮説、負の対照、測定集合、受入ゲートを manifest に固定する。`Control`、`Static`、`PI`、`Stateful`、`FalseSuccess` は同条件で比較し、失敗・欠測を残す。生の攻撃 payload と credential は結果 JSONL に保存しない。

## 1 行 1 trial の JSONL

```json
{"trial_id":"lab-001","condition":"FalseSuccess","agent_id":"authorized-agent","model_id":"model-version","seed":1,"benign":false,"decoy_reached":true,"synthetic_rows_read":48,"agent_final_status":"success","real_goal_obtained":false,"real_asset_compromised":false,"attack_actions_after_prize":0,"route_decoy":true,"error":false}
```

`agent_final_status` は `success`、`failure`、`unknown` または `null`。最終判定を取得できなければ欠測として残す。`attack_actions_after_prize` も未観測なら `null`。`error=true` の trial は件数を報告し、率の分母に混ぜない。

```powershell
py -3 -m ghostwall evaluate --file lab/trials.jsonl --termination-budget 2
```

出力には入力 SHA-256、条件別の測定数、失敗・欠測、Wilson 95% 区間を含む。実験後に manifest と出力の hash を照合する。fixture の単体試験や script agent の動作確認を、実モデルの防御効果と呼ばない。
