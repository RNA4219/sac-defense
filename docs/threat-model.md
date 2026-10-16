# 脅威モデル

## 保護対象

実アプリ・実DB・実credential と、正常利用者の到達経路を保護する。デコイ SQLite と token は偽資産であり、実アプリから参照しない。

## 攻撃者と境界

主対象は HTTP の応答を LLM コンテキストへ取り込み、次の行動を決める自律型探索エージェント。固定 scanner や exploit-only automation には通常の WAF/IPS が別途必要。攻撃者は path、query、header、body、cookie を制御できる。router の固定 origin、deployment key、host event file、kill switch は運用者だけが制御する。

## 主要な失敗

1. decoy へ触れた後も real 側を再探索する。署名済み sticky session、`--never-real-prefix` で指定した機密経路の上流到達禁止、`--allow-real-prefix` による real 経路の明示、独立した real 側の防御を使い、lab で再探索率を測る。
2. decoy の顧客・注文・件数に矛盾が出る。データ生成はコードと SQLite に固定し、外部キーと CSV hash を試験する。
3. decoy 停止時に real 側へ流れる。router は 503/403 へ閉じる。
4. decoy が router の HTTP 入口を経由して real の許可経路へ戻る。隔離 Compose では router と decoy の Docker network を共有せず、router から decoy への呼出しだけを共有 Unix ソケットへ限定する。decoy から router への TCP 到達失敗を受入試験で確認する。
5. decoy を踏み台にする。ネットワーク、volume、権限を分離し、Internet egress を閉じる。
6. 良性利用者が誤誘導される。sentinel と decoy token、署名済み session、信頼された host signal のみを route 判定に使う。誤誘導率は lab で測る。

## 信頼の限界

署名 cookie は同一 client 内の sticky route 用であり、攻撃者個人の識別ではない。[EV-20261016-07](evidence/EV-20261016-07-result.md) で cookie と token の削除により新 session から実ゴールへ到達した。現行版では未登録経路を block し、`--never-real-prefix` は指定経路を cookie に依存せずデコイへ送る。正規の認証済みリクエストも機密経路ではデコイへ行くため、許可経路と保護経路の台帳が必要。導入先では実アプリの認証・WAF/IPS・host policy を独立して維持する。host event は信頼された外部相関器が session cookie と対応付けた場合だけ取り込める。eBPF event 単体から HTTP session ID を確実に特定できるとは主張しない。
