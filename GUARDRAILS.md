# Guardrails

- 自組織が管理・許可されたサービスと lab だけで使う。外部の攻撃元へ接続・認証・実行しない。
- production の DB、鍵、ボリューム、ネットワークを decoy に共有しない。合成データを実顧客データから作らない。
- suspicious route は障害時と kill switch 時に block する。normal route へ fail-open しない。
- 正規経路は `--allow-real-prefix` で明示し、未登録経路は block する。機密経路は `--never-real-prefix` で指定し、許可経路より優先する。導入先の経路台帳で両方を確認する。
- decoy への転送では実 Authorization、body、不要な query を渡さない。router と decoy の書き込み可能 DB を分け、key と kill switch は読み取り専用で mount する。
- attacker 入力をプロンプトやコマンドとして実行しない。hot path に外部 LLM を置かない。
- 本番公開前に Linux ネットワーク分離、egress、誤誘導、保持・削除、法務・セキュリティを受入記録で確認する。
- 資格情報、リクエスト本文、IP、header を telemetry に保存しない。key と runtime DB を Git に追加しない。
- Workflow-cookbook の原文を正本とし、完了と未検証を分けて記録する。比較実験では入力、runner、モデル、seed、仮説、対照群、実測値を事前固定する。
