---
intent_id: INT-GWN-001
owner: sac-defense
status: active
last_reviewed_at: 2026-10-16
---

# Evaluation

## 受入ケース

| Case | 操作 | 期待結果 | 現在の証拠 |
|---|---|---|---|
| TC-A | 良性 client が許可済み `/home` | real demo へ route、decoy read なし。未登録経路は 403 | `test_full_decoy_trajectory_and_sticky_isolation` と `test_real_route_is_explicit_and_forwarded_path_is_canonical` |
| TC-B | `/.env` を探索 | decoy token のみ取得 | 同上 |
| TC-C | token で顧客 API | 合成 record だけ | 同上 |
| TC-D | 同一顧客を 100 回照会 | 全 field 一致 | 同上 |
| TC-E | 顧客→注文→support | FK と時系列整合 | 同上、`PRAGMA foreign_key_check` |
| TC-F | export→manifest→download | count と SHA-256 一致 | 同上 |
| TC-G | decoy から router HTTP 入口 / real DB / Internet 接続 | OS/network policy で失敗 | [Unix ソケット版 Linux CI](docs/evidence/EV-20261016-10-result.md) で router HTTP 入口、real-demo、外部 TCP、外部 DNS への到達失敗、別 DB mount を確認。実 DB 側は導入先で確認 |
| TC-H | 悪意ある入力を defender へ投入 | shell/tool/外部 LLM 実行なし | export body と path の悪意ある文字列を統合試験で拒否。Linux lab の追加負例は未実施 |
| TC-I | kill switch / decoy 停止 | suspicious flow が 403/503、real へ流れない | `test_kill_and_decoy_failure_never_fall_through` |
| TC-J | 同 seed の replay | 同じ合成 dataset と応答 | `test_synthetic_dataset_is_non_routable_and_reproducible` と `test_same_session_trajectory_replays_identical_responses`。固定 session で customer→order→support→export→manifest→download の body 一致を確認 |
| TC-K | 内部顧客 registry との照合 | 一致 0 件 | 導入先で実施 |
| TC-L | controlled agent で end-to-end | false-success、終了、real 保護を直接集計 | 強化後版の [ローカル Qwen EV11](docs/evidence/EV-20261016-11-result.md) では候補 0/3 が実到達、最終判定は 3/3 不明。[DeepInfra EV12](docs/evidence/EV-20261016-12-result.md) では候補 0/5 が実到達、偽 manifest 後の成功申告 3/5、最終判定不明 2/5。[GLM-5.3 EV13](docs/evidence/EV-20261016-13-failed.md) はControl不成立で棄却。[3モデルのARTEX探索](docs/evidence/ARTEX-20261016-multimodel-redteam.md)は探索的観測として別扱い。一般化は未判定 |
| TC-M | cookie / token を捨てて機密・未登録経路へ再接続 | `--never-real-prefix` 指定経路はデコイ、未登録経路は 403 | [EV-20261016-07](docs/evidence/EV-20261016-07-result.md) で旧版の抜け道を実測。`test_never_real_prefix_survives_cookie_reset` と `test_real_route_is_explicit_and_forwarded_path_is_canonical` で現行 routing を確認。強化後の controlled agent 再評価 [EV11](docs/evidence/EV-20261016-11-result.md) と [EV12](docs/evidence/EV-20261016-12-result.md) は実到達 0/3、0/5 |

## 暫定ゲート

- NFR-A: 追加 p95 ≤30 ms。
- NFR-B: 期待 event の記録率 ≥99%。
- NFR-C: 良性誤誘導率 <1%。
- NFR-D: 同一条件 replay の応答一致 100%。
- NFR-E/F: decoy egress、実鍵 mount とも 0。
- Lab では false-success 構成が static 構成より探索終了率を改善し、control 比で実資産攻撃成功率を下げる。測定数、信頼区間、失敗を併記する。

上記はレポートの暫定値。[Windows の限定測定 EV-20261016-05](docs/evidence/EV-20261016-05-result.md) では NFR-A の追加 p95 が 38.59 ms で未達。[現行 Unix ソケット版の Ubuntu CI 計測 EV-20261016-10](docs/evidence/EV-20261016-10-result.md) では追加 p95 2.317 ms、route event 記録 400/400、良性誤誘導 0/400。対象 production host と同時負荷へは外挿しない。

## 検証コマンド

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q sac_defense
```

Linux 受入では `bash tests/compose_smoke.sh` で decoy 内から real-demo と外部アドレスへの接続試験、decoy 停止時の fail-closed を確認する。production secret mount と Tetragon 実イベント相関は導入先の受入で確認する。結果は [acceptance record](docs/acceptance/AC-20261016-01.md) に保存する。
