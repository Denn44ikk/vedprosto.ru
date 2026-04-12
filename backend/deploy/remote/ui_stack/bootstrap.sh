#!/usr/bin/env bash
set -euo pipefail

mkdir -p ./data/runtime
docker compose up -d --build
