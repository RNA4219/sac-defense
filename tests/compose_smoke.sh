#!/usr/bin/env bash
set -euo pipefail

sudo install -d -o 65532 -g 65532 -m 0700 runtime runtime/router runtime/decoy runtime/secrets runtime/control runtime/socket
trap 'docker compose down --remove-orphans >/dev/null 2>&1 || true' EXIT

docker compose --profile setup run --rm init-router
docker compose --profile setup run --rm init-decoy
docker compose up --build -d router decoy real-demo

ready=0
for _ in $(seq 1 30); do
  if curl --fail --silent --output /dev/null http://127.0.0.1:4319/_sac/health; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" -eq 1

test "$(curl --fail --silent http://127.0.0.1:4319/home)" = "real-demo (no data)"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:4319/unknown)" = "403"
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:4319/.env

docker compose exec -T decoy python -c 'print("decoy alive")' >/dev/null
decoy_id=$(docker compose ps -q decoy)
docker inspect "$decoy_id" | python -c '
import json, sys
container = json.load(sys.stdin)[0]
host = container["HostConfig"]
mounts = container["Mounts"]
networks = container["NetworkSettings"]["Networks"]
assert host["ReadonlyRootfs"] and not host["Privileged"]
assert "ALL" in host["CapDrop"]
assert sorted(mount["Destination"] for mount in mounts) == ["/control", "/secrets/deployment.key", "/socket", "/state"]
assert all(mount["RW"] is False for mount in mounts if mount["Destination"] not in {"/state", "/socket"})
assert len(networks) == 1 and next(iter(networks)).endswith("_decoy_net")
'
router_id=$(docker compose ps -q router)
docker inspect "$router_id" "$decoy_id" | python -c '
import json, sys
router, decoy = json.load(sys.stdin)
def state_source(container):
    return next(mount["Source"] for mount in container["Mounts"] if mount["Destination"] == "/state")
assert state_source(router) != state_source(decoy)
assert not (set(router["NetworkSettings"]["Networks"]) & set(decoy["NetworkSettings"]["Networks"]))
assert next(m for m in router["Mounts"] if m["Destination"] == "/socket")["RW"] is False
'
if docker compose exec -T decoy python -c 'import socket; socket.create_connection(("real-demo", 8080), timeout=2)' >/dev/null 2>&1; then
  echo "decoy reached real-demo" >&2
  exit 1
fi
if docker compose exec -T decoy python -c 'import socket; socket.create_connection(("router", 4319), timeout=2)' >/dev/null 2>&1; then
  echo "decoy reached router HTTP listener" >&2
  exit 1
fi
if docker compose exec -T decoy python -c 'import socket; socket.getaddrinfo("example.com", 443)' >/dev/null 2>&1; then
  echo "decoy resolved an external DNS name" >&2
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
