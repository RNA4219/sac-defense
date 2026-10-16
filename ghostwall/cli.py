"""Operator commands. Host signals are accepted only through local file access."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import Settings, load_key, new_key, parse_session
from .evaluation import read_trials, summarize_trials
from .server import App, Server
from .store import Store


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="ghostwall")
    subs = command.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init", help="create a deployment key and synthetic database")
    init.add_argument("--database", type=Path, required=True)
    init.add_argument("--key-file", type=Path, required=True)

    serve = subs.add_parser("serve", help="run the router or isolated decoy")
    serve.add_argument("--mode", choices=("router", "decoy"), required=True)
    serve.add_argument("--database", type=Path, required=True)
    serve.add_argument("--key-file", type=Path, required=True)
    serve.add_argument("--kill-switch", type=Path, required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=4319)
    serve.add_argument("--upstream", default="")
    serve.add_argument("--decoy", default="")
    serve.add_argument("--public-https", action="store_true")
    serve.add_argument("--never-real-prefix", action="append", default=[],
                       help="canonical path prefix that must never reach the real upstream")

    kill = subs.add_parser("kill", help="block suspicious routes without forwarding them")
    kill.add_argument("--kill-switch", type=Path, required=True)
    kill.add_argument("state", choices=("on", "off"))

    event = subs.add_parser("host-event", help="ingest a reviewed, session-correlated host signal JSON file")
    event.add_argument("--database", type=Path, required=True)
    event.add_argument("--key-file", type=Path, required=True)
    event.add_argument("--file", type=Path, required=True)

    summary = subs.add_parser("summary", help="read local evidence counts")
    summary.add_argument("--database", type=Path, required=True)
    summary.add_argument("--key-file", type=Path, required=True)
    prune = subs.add_parser("prune", help="delete expired session telemetry")
    prune.add_argument("--database", type=Path, required=True)
    prune.add_argument("--key-file", type=Path, required=True)
    prune.add_argument("--days", type=int, default=30)

    evaluate = subs.add_parser("evaluate", help="aggregate explicit authorized lab trial results")
    evaluate.add_argument("--file", type=Path, required=True)
    evaluate.add_argument("--termination-budget", type=int, default=2)

    collision = subs.add_parser("collision-check", help="compare synthetic identifiers with a local customer registry")
    collision.add_argument("--database", type=Path, required=True)
    collision.add_argument("--key-file", type=Path, required=True)
    collision.add_argument("--registry", type=Path, required=True)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            if args.database.exists():
                raise FileExistsError(args.database)
            new_key(args.key_file)
            store = Store(args.database, load_key(args.key_file))
            store.initialize()
            print(json.dumps({"status": "initialized", "seed_id": store.seed_id}))
        elif args.command == "serve":
            settings = Settings(
                database=args.database,
                key_file=args.key_file,
                kill_switch=args.kill_switch,
                bind=args.bind,
                port=args.port,
                mode=args.mode,
                upstream=args.upstream,
                decoy=args.decoy,
                public_https=args.public_https,
                never_real_prefixes=tuple(args.never_real_prefix),
            )
            server = Server(App(settings))
            print(json.dumps({"status": "listening", "mode": args.mode, "bind": args.bind, "port": args.port}), flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            finally:
                server.server_close()
        elif args.command == "kill":
            if args.state == "on":
                args.kill_switch.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(args.kill_switch, os.O_WRONLY | os.O_CREAT, 0o600)
                os.close(fd)
            else:
                args.kill_switch.unlink(missing_ok=True)
            print(json.dumps({"kill_switch": args.state}))
        elif args.command == "host-event":
            if not args.database.is_file():
                raise FileNotFoundError(args.database)
            raw = json.loads(args.file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("host event must be an object")
            key = load_key(args.key_file)
            session = parse_session(key, raw.get("session_cookie"))
            if session is None:
                raise ValueError("host event needs a valid signed session cookie")
            store = Store(args.database, key)
            store.initialize()
            store.host_signal(session[1], raw.get("kind", ""), int(raw.get("severity", -1)))
            print(json.dumps({"status": "recorded", "session_id": session[1]}))
        elif args.command == "summary":
            if not args.database.is_file():
                raise FileNotFoundError(args.database)
            store = Store(args.database, load_key(args.key_file))
            store.initialize()
            print(json.dumps(store.summary(), ensure_ascii=False, sort_keys=True))
        elif args.command == "prune":
            if not args.database.is_file():
                raise FileNotFoundError(args.database)
            if not 1 <= args.days <= 3650:
                raise ValueError("days must be between 1 and 3650")
            store = Store(args.database, load_key(args.key_file))
            store.initialize()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat(timespec="seconds")
            print(json.dumps({"cutoff": cutoff, "removed": store.prune(cutoff)}, sort_keys=True))
        elif args.command == "evaluate":
            trials, sha = read_trials(args.file)
            print(json.dumps(summarize_trials(trials, sha, args.termination_budget), ensure_ascii=False, sort_keys=True))
        elif args.command == "collision-check":
            if not args.database.is_file():
                raise FileNotFoundError(args.database)
            store = Store(args.database, load_key(args.key_file))
            store.initialize()
            result = store.collision_check(args.registry)
            print(json.dumps(result, sort_keys=True))
            return 1 if result["collisions"] or result["uncheckable"] else 0
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ghostwall: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
