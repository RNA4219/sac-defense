"""Measure local benign routing latency and event completeness."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit


def request(origin: str) -> tuple[float, int, bytes, str]:
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or parsed.path not in {"", "/"}:
        raise ValueError("benchmark origins must be explicit IPv4 loopback HTTP ports")
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    start = time.perf_counter_ns()
    try:
        connection.request("GET", "/home")
        response = connection.getresponse()
        body = response.read()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return elapsed_ms, response.status, body, response.getheader("Set-Cookie", "")
    finally:
        connection.close()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def event_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT COUNT(*) FROM events WHERE kind='route_decision'").fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", required=True)
    parser.add_argument("--router", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=400)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 1 or args.output.exists() or not args.database.is_file():
        raise ValueError("invalid pair count, output already exists, or database missing")
    for origin in (args.direct, args.router):
        request(origin)
    before = event_count(args.database)
    direct: list[float] = []
    routed: list[float] = []
    mismatched = decoy = 0
    for index in range(args.pairs):
        if index % 2:
            routed_sample = request(args.router)
            direct_sample = request(args.direct)
        else:
            direct_sample = request(args.direct)
            routed_sample = request(args.router)
        direct.append(direct_sample[0])
        routed.append(routed_sample[0])
        if direct_sample[1:3] != routed_sample[1:3] or direct_sample[1] != 200:
            mismatched += 1
        if "gw_sid=d." in routed_sample[3]:
            decoy += 1
    recorded = event_count(args.database) - before
    result = {
        "pairs": args.pairs,
        "path": "/home",
        "direct_latency_ms": direct,
        "router_latency_ms": routed,
        "direct_p95_ms": percentile(direct, 0.95),
        "router_p95_ms": percentile(routed, 0.95),
        "added_p95_ms": percentile([a - b for a, b in zip(routed, direct)], 0.95),
        "negative_control_mismatches": mismatched,
        "decoy_routes": decoy,
        "recorded_route_events": recorded,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if not key.endswith("latency_ms")}, sort_keys=True))
    return 0 if mismatched == 0 and decoy == 0 and recorded == args.pairs else 1


if __name__ == "__main__":
    raise SystemExit(main())
