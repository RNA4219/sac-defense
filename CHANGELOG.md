# Changelog

## Unreleased - 2026-10-16

- Qwen3.5 4B の限定比較を Workflow-cookbook の事前・事後 manifest で記録。合成 manifest 後の成功申告と終了を観測。
- Windows / Ubuntu CI の良性経路400組を比較し、CI に p95 遅延・経路 event・誤誘導 gate を追加。
- Linux Compose で外部 DNS/TCP、real-demo、専用 mount、権限、fail-closed の受入を実行。
- 固定 session の顧客→export trajectory 応答再現テストを追加。

## 0.1.1 - 2026-10-16

- GitHub CI で Docker の分離・fail-closed を実行する smoke test を追加。
- loopback 限定の実モデル探索ハーネスと架空の比較用 backend を追加。

## 0.1.0 - 2026-10-16

- Deep Research の FR-A〜J を要件・受入ケースへ展開。
- Python の router、synthetic SQLite、stateful decoy API、kill switch、minimal telemetry、lab 評価集計を追加。
- Docker Compose の分離例、Workflow-cookbook Tier 2 文書、Task Seed と acceptance record を追加。
- Linux isolation と controlled-agent 効果測定は受入待ちとして記録。
