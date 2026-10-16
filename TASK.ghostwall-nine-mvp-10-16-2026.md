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
```

## Dependencies

- [Deep Research レポート](https://chatgpt.com/share/6ad169ad-10a4-83ee-8c09-50b950bf2132)
- `../workflow-cookbook/HUB.codex.md`
- Linux の隔離 lab と、認可済み agent / real backend の評価設定（実環境受入のみ）

## Acceptance

- [AC-20261016-01](docs/acceptance/AC-20261016-01.md)
