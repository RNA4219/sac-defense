#!/usr/bin/env bash
set -euo pipefail

sudo install -d -o 65532 -g 65532 -m 0700 runtime
trap 'docker compose down --remove-orphans >/dev/null 2>&1 || true' EXIT

docker compose --profile setup run --rm init
docker compose up --build -d router decoy real-demo

ready=0
for _ in $(seq 1 30); do
  if curl --fail --silent --output /dev/null http://127.0.0.1:4319/_ghostwall/health; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" -eq 1

test "$(curl --fail --silent http://127.0.0.1:4319/home)" = "real-demo (no data)"
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:4319/.env

docker compose exec -T decoy python -c 'print("decoy alive")' >/dev/null
if docker compose exec -T decoy python -c 'import socket; socket.create_connection(("real-demo", 8080), timeout=2)' >/dev/null 2>&1; then
  echo "decoy reached real-demo" >&2
  exit 1
fi
if docker compose exec -T decoy python -c 'import socket; socket.create_connection(("1.1.1.1", 443), timeout=2)' >/dev/null 2>&1; then
  echo "decoy reached the Internet" >&2
  exit 1
fi

docker compose stop decoy >/dev/null
status=$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:4319/.env)
test "$status" = "503"

echo "compose isolation and fail-closed smoke passed"
