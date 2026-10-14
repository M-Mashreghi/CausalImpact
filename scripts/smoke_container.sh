#!/usr/bin/env bash
# Build the image, start the stack, wait for health, exercise the API, tear down.
set -euo pipefail
docker compose build
docker compose up -d
trap 'docker compose down -v' EXIT
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8501/_stcore/health >/dev/null; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8501/_stcore/health
echo "container smoke test passed"
