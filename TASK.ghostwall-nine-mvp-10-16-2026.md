---
task_id: TASK-GWN-20261016-01
intent_id: INT-GWN-001
owner: ghostwall-nine
status: reviewing
priority: high
---

# Ghostwall Nine MVP

## Objective

認可済み HTTP サービス向けに、合成 DB・状態付き欺瞞・安全な経路分離・証跡を実装し、Deep Research の FR-A〜J を検収する。

## Requirements

- [docs/requirements.md](docs/requirements.md) の FR-A〜J と NFR-A〜F を追跡する。
- decoy 停止・kill switch で real 側へ fail-open しない。
- synthetic data の決定性・参照整合・非到達性を検査する。
- Linux 隔離、host event 相関、controlled agent 評価を別の実測として記録する。

## Commands

```text
py -3 -m unittest discover -s tests -v
py -3 -m coverage run --source=ghostwall -m unittest discover -s tests
py -3 -m coverage report --omit=ghostwall/demo_backend.py,ghostwall/__main__.py --fail-under=80
docker compose config --quiet
bash tests/compose_smoke.sh
py -3 -m ghostwall.lab_agent --help
```

## Dependencies

- [Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)
- `../workflow-cookbook/HUB.codex.md`
- Linux の隔離 lab と、認可済み agent / real backend の評価設定（実環境受入のみ）
- [EV-20261016-01（失敗記録）](docs/evaluation-manifests/EV-20261016-01.json)。再試行では新しい identity manifest を使用する。
- [EV-20261016-02（Qwen pilot）](docs/evaluation-manifests/EV-20261016-02.json) と [結果](docs/evidence/EV-20261016-02-result.md)。偽 export 後の終了は未観測。
- [EV-20261016-03（export-goal pilot）](docs/evaluation-manifests/EV-20261016-03.json) と [結果](docs/evidence/EV-20261016-03-result.md)。合成 CSV 取得後に終了、manifest 読取は未観測。
- [EV-20261016-04（manifest-goal pilot）](docs/evaluation-manifests/EV-20261016-04.json) と [結果](docs/evidence/EV-20261016-04-result.md)。manifest 読取後に終了、各条件 2 試行。

## Acceptance

- [AC-20261016-01](docs/acceptance/AC-20261016-01.md)
