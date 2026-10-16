# 要件定義

出典: [攻性防壁の Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)（2026-10-16 確認）。レポートの数値は研究用の暫定 go/no-go 値であり、実システムの SLO に合わせて受入前に固定する。

| ID | 要件 | 実装・受入 |
|---|---|---|
| FR-A | sentinel / risk に基づく real / decoy routing | `sac_defense/server.py`。署名 cookie・token・host signal・`/.env` と `--never-real-prefix` で判定。実 upstream は `--allow-real-prefix` で明示した経路のみ。TC-A/B/I/M |
| FR-B | 実 credential を含まない発見用 `.env` | `sac_defense/core.py`, `server.py`。decoy 専用 token。TC-B |
| FR-C | production 非由来の PII 風データ | `sac_defense/store.py`。ゼロから生成、`.invalid` と 555。`collision-check` を内部顧客 registry で実行して TC-K |
| FR-D | 同 seed / version の決定論 | HMAC と固定 schema。TC-D/J |
| FR-E | customer → order → support の参照整合 | SQLite FK と時系列。TC-E |
| FR-F | session ごとの状態付き欺瞞 | `sessions` と署名 cookie。TC-C〜F |
| FR-G | export と manifest の偽完了 | CSV hash、count、job ID。TC-F |
| FR-H | request / route / state / host event の session 相関 | SQLite `events`, `host_signals`。host source の相関は導入先で実証 |
| FR-I | 即時 kill switch | file 有無を request ごとに検査。TC-I |
| FR-J | decoy 隔離 | `compose.yaml` の分離 network、Unix ソケット連携、router/decoy 別 DB、読み取り専用 key/control mount。decoy→router HTTP 入口の迂回も Linux 実環境で TC-G |

## 非機能要件

| ID | 暫定基準 | 判定方法 |
|---|---|---|
| NFR-A | 非 LLM route 追加 p95 ≤30 ms | 同じ lab backend の control と比較 |
| NFR-B | 期待 event の 99% 以上 | request ID / session ID ごとの欠測を確認 |
| NFR-C | 良性誤誘導率 <1% | 固定 benign suite を複数条件で実行 |
| NFR-D | 同一 request sequence の replay 100% | dataset key / version / DB を固定して応答比較 |
| NFR-E | decoy から許可外 Internet egress 0 | Linux namespace 内の DNS・TCP 接続試験 |
| NFR-F | production credential の decoy mount 0 | Compose・container inspect・権限を確認 |

## 効果測定の条件

認可 lab で control、static、stateful、false-success を同じ agent/model/seed/budget で比較し、synthetic 取得、agent の明示的最終判定、探索終了、real asset 到達、良性誤誘導を session 単位で保存する。実環境では未知の攻撃者の内心や final status を観測できないため、export 後の行動 proxy として別集計する。実験前に評価 identity と負の対照を固定し、失敗・欠測をゼロに埋めない。

## 完了判定

FR-A〜I のコード上の振る舞いは自動統合試験で確認する。FR-J、host 実イベント、NFR-A〜F、controlled agent による偽成功・探索終了は Linux の隔離 lab で判定する。全体の「防御効果実証済み」は実測まで使用しない。
