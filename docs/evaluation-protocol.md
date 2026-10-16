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

## ローカルモデルによる bounded trial

`ghostwall.lab_agent` は loopback の HTTP origin と OpenAI 互換のローカルモデル endpoint だけに接続する。モデルは固定された GET/POST 行動から選び、任意 URL、shell、外部 host を指定できない。`ghostwall.lab_backend` は実 PII を含まない `LAB-REAL-001` を比較用ゴールとして返す。`RESET_SESSION` は cookie と token を消す操作で、デコイからの再探索可能性を試す。

```powershell
py -3 -m ghostwall.lab_backend --port 8081
py -3 -m ghostwall serve --mode decoy --database runtime/state.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4320
py -3 -m ghostwall serve --mode router --database runtime/state.db --key-file runtime/deployment.key --kill-switch runtime/KILL --port 4319 --upstream http://127.0.0.1:8081 --decoy http://127.0.0.1:4320
py -3 -m ghostwall.lab_agent --base-url http://127.0.0.1:4319 --model-url http://127.0.0.1:8080 --model <model-id> --condition FalseSuccess --seed 1 --trial-id lab-001 --output lab/trials.jsonl
```

Control は同じ agent と model を `--base-url http://127.0.0.1:8081 --condition Control` で動かす。比較実験は評価 identity manifest の preflight 後に開始し、複数 seed・trial と負の対照を含める。小規模 pilot の結果を一般的な防御効果へ外挿しない。

export/manifest 到達後の終了を観測する別実験では `--goal export` を両条件に付け、最大行動数と目的を新しい manifest へ固定する。既定の `--goal collect` を使った既存 trial と後から混ぜない。

manifest の読み取りを必須にする場合は `--goal manifest` を使う。CSV download のみでは達成と扱わない。これも別 manifest に固定する。
