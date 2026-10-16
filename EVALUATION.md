---
intent_id: INT-GWN-001
owner: ghostwall-nine
status: active
last_reviewed_at: 2026-10-16
---

# Evaluation

## 受入ケース

| Case | 操作 | 期待結果 | 現在の証拠 |
|---|---|---|---|
| TC-A | 良性 client が `/home` | real demo へ route、decoy read なし | `test_full_decoy_trajectory_and_sticky_isolation` |
| TC-B | `/.env` を探索 | decoy token のみ取得 | 同上 |
| TC-C | token で顧客 API | 合成 record だけ | 同上 |
| TC-D | 同一顧客を 100 回照会 | 全 field 一致 | 同上 |
| TC-E | 顧客→注文→support | FK と時系列整合 | 同上、`PRAGMA foreign_key_check` |
| TC-F | export→manifest→download | count と SHA-256 一致 | 同上 |
| TC-G | decoy から real DB / Internet 接続 | OS/network policy で失敗 | GitHub CI の Compose smoke で real-demo、外部 TCP、外部 DNS への到達失敗、専用 mount と単一 network を確認。実 DB 側は導入先で確認 |
| TC-H | 悪意ある入力を defender へ投入 | shell/tool/外部 LLM 実行なし | export body と path の悪意ある文字列を統合試験で拒否。Linux lab の追加負例は未実施 |
| TC-I | kill switch / decoy 停止 | suspicious flow が 403/503、real へ流れない | `test_kill_and_decoy_failure_never_fall_through` |
| TC-J | 同 seed の replay | 同じ合成 dataset と応答 | `test_synthetic_dataset_is_non_routable_and_reproducible` と `test_same_session_trajectory_replays_identical_responses`。固定 session で customer→order→support→export→manifest→download の body 一致を確認 |
| TC-K | 内部顧客 registry との照合 | 一致 0 件 | 導入先で実施 |
| TC-L | controlled agent で end-to-end | false-success、終了、real 保護を直接集計 | [EV-20261016-04](docs/evidence/EV-20261016-04-result.md) で manifest 読取後の成功・2 行動以内の終了を各 2 試行で観測。一般化は未判定 |
| TC-M | cookie / token を捨てて機密経路へ再接続 | `--never-real-prefix` 指定経路は通常上流へ到達しない | [EV-20261016-07](docs/evidence/EV-20261016-07-result.md) で旧版の抜け道を実測。`test_never_real_prefix_survives_cookie_reset` と [EV-20261016-08](docs/evidence/EV-20261016-08-result.md) で修正版を確認 |

## 暫定ゲート

- NFR-A: 追加 p95 ≤30 ms。
- NFR-B: 期待 event の記録率 ≥99%。
- NFR-C: 良性誤誘導率 <1%。
- NFR-D: 同一条件 replay の応答一致 100%。
- NFR-E/F: decoy egress、実鍵 mount とも 0。
- Lab では false-success 構成が static 構成より探索終了率を改善し、control 比で実資産攻撃成功率を下げる。測定数、信頼区間、失敗を併記する。

上記はレポートの暫定値。[Windows の限定測定 EV-20261016-05](docs/evidence/EV-20261016-05-result.md) では NFR-A の追加 p95 が 38.59 ms で未達。[Ubuntu CI 計測 EV-20261016-06](docs/evidence/EV-20261016-06-result.md) では 2.462 ms、[修正版の CI](https://github.com/RNA4219/ghostwall-nine/actions/runs/38833574418) では 1.748 ms。修正版の route event 記録・良性誤誘導は 400/400・0/400。対象 production host と同時負荷へは外挿しない。

## 検証コマンド

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q ghostwall
```

Linux 受入では `bash tests/compose_smoke.sh` で decoy 内から real-demo と外部アドレスへの接続試験、decoy 停止時の fail-closed を確認する。production secret mount と Tetragon 実イベント相関は導入先の受入で確認する。結果は [acceptance record](docs/acceptance/AC-20261016-01.md) に保存する。
