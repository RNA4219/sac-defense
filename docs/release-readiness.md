# MIT 公開準備

現在の GitHub repository は **private**。MIT ライセンスは [LICENSE](../LICENSE) に明記し、Python 配布名は `sac-defense`、import 名は `sac_defense` とする。S.A.C. は **Synthetic Adversary Containment** の略称。

## 公開前の確認

| 項目 | 判定 |
|---|---|
| MIT 本文と配布メタデータ | 完了。`LICENSE` と `pyproject.toml` を照合 |
| real upstream の明示的許可経路、decoy 優先、異常時 fail-closed | 自動試験で確認。導入先の経路台帳は別途必要 |
| decoy への資格情報・本文の遮断 | 自動試験で確認。実配置の reverse proxy も確認する |
| Docker build context から runtime/key/DB を除外 | `.dockerignore` の whitelist と [Linux CI](evidence/EV-20261016-09-result.md) の image build・mount 検査で確認 |
| 追跡ファイルと Git 履歴の secret 混入 | 追跡中の `.env`/key/DB は 0 件、履歴の代表的な secret 形式は 0 件。公開直前に専門 scanner で再検査し、結果を受入記録へ残す |
| 新 Compose 構成の network/volume 分離 | router 経由の迂回を防ぐ Unix ソケット構成を次の Linux CI で確認。導入先でも `docker inspect` を実施 |
| 強化後の良性 p95、誤誘導 | [Linux CI](evidence/EV-20261016-09-result.md) で暫定ゲート合格 |
| 強化後の agent 評価 | 再評価待ち。旧 trial は現行版の効果証明に流用しない |
| 名称と公開導線 | `S.A.C.` の表記、リポジトリ名、配布名、第三者との識別を公開前に最終確認 |

実サービスへの適用には、許可経路と機密経路の台帳、実アプリ側の認証、TLS 終端、保持期限、実 DB と credential の非共有を受入条件として固定する。公開前の試験だけで本番防御効果を断定しない。
