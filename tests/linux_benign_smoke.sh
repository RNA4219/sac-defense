#!/usr/bin/env bash
set -euo pipefail

output=${1:?pass an output JSON path}
scratch=$(mktemp -d)
backend_pid=''
decoy_pid=''
router_pid=''
cleanup() {
  for pid in "$router_pid" "$decoy_pid" "$backend_pid"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

python -m ghostwall init --database "$scratch/state.db" --key-file "$scratch/deployment.key" >/dev/null
python -m ghostwall.lab_backend --port 8081 >"$scratch/backend.log" 2>&1 &
backend_pid=$!
python -m ghostwall serve --mode decoy --database "$scratch/state.db" --key-file "$scratch/deployment.key" --kill-switch "$scratch/KILL" --port 4320 >"$scratch/decoy.log" 2>&1 &
decoy_pid=$!
python -m ghostwall serve --mode router --database "$scratch/state.db" --key-file "$scratch/deployment.key" --kill-switch "$scratch/KILL" --port 4319 --upstream http://127.0.0.1:8081 --decoy http://127.0.0.1:4320 >"$scratch/router.log" 2>&1 &
router_pid=$!

ready=0
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:8081/home >/dev/null && \
     curl --fail --silent --max-time 2 http://127.0.0.1:4319/home >/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  tail -n 30 "$scratch/backend.log" "$scratch/decoy.log" "$scratch/router.log"
  exit 1
fi

python tools/measure_benign.py --direct http://127.0.0.1:8081 --router http://127.0.0.1:4319 --database "$scratch/state.db" --pairs 400 --output "$output"
