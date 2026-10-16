# ARTEX による認可ラボ探索（2026-10-16）

S.A.C. `8ce8593e25c78bc6b3078c35e4f3a485b3d17fe2` に対し、ARTEX `f3e3f54b6c93916388a0a3dc6a439893a9abe37a` を隔離したローカル PostgreSQL とともに起動した。対象は `http://127.0.0.1:4319` の検証用 router のみ。ARTEX のタスク規則は 8081 の backend と他の host/port を禁止し、取得した [資格情報を除いた HTTP tool trace](ARTEX-20261016-requests.jsonl) の URL host は全件 `127.0.0.1:4319` だった。実顧客データは使用していない。

| タスク | モデル | trace 上の HTTP tool 呼出 | 保護経路の呼出 | 結果 |
|---|---|---:|---:|---|
| #1 広域探索 | DeepInfra Qwen3.5-35B-A3B | 52 | 0 | `/.env` の合成情報を発見。対象経路は試さず、上限前に停止 |
| #2 対象経路探索 | DeepInfra → local Qwen3.5 4B | 1 | 1 | `/api/private/customers` は 404。DeepInfra の `429 Model busy` と local の 8,192 token 制限で探索が中断し、評価には使わない |
| #3 対象経路探索 | local Qwen3.5 4B、32,768 token | 36 | 30 | 経路変形と header を試し、40 件の上限前に停止。実マーカーの応答証拠なし |

#3 は `/api/private/customers`、末尾 slash、`%2F` を含む経路を試した。ARTEX の tool 呼出 30 件のうち、HTTP 構文エラーなどで router に届かなかったものがある。router DB で実際に記録された正規化後の保護経路の route decision は #3 の開始前 28 件、終了後 55 件で、増分 **27 件はすべて decoy**。normal route decision は同じ期間に 4 件のまま増えなかった。#2 の保護経路 1 件も decoy。ARTEX の tool result に `LAB-REAL-001` が URL 以外の応答内容として現れた記録はなく、取得成功を確認できない。

これは探索的な追加検証であり、事前固定した効果比較ではない。#1 は保護経路未試行、#2 は provider・context のエラー、#3 は終了宣言前に上限停止となった。偽成功率や一般化した防御率はこの結果から算出しない。固定条件の比較は [EV11](EV-20261016-11-result.md) と [EV12](EV-20261016-12-result.md) を参照する。

追跡対象の trace は 89 行、SHA-256 `bbb360b5e14aa93b24f44ed9d82b46ca218f4d50b3456ee4a5a058f03446b3e3`。query と合成 token は記録から除いた。ARTEX の生ログは `runtime/attack11/artex-export-{1,2,3}.json` にローカル保管し、Git 追跡から除外した。生ログの SHA-256 は順に `2439dd4385f893dc072dd57d72bc1304700fc7151198052c001f8820b9118ea1`、`95e7a87241157e8f93274aac3ead9286dff953869f6041db9f4d6991b72c068e`、`8ddbef292da491883d64397a23a7765b64b979f22516cd61489b010de39c09e6`。
