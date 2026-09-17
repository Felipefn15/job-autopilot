#!/usr/bin/env bash
set -uo pipefail

mkdir -p "${DATA_DIR:-/data}"

args=(
  python main.py
  --once
  --location "${JOB_LOCATION:-Latam}"
  --max-applications "${MAX_APPLICATIONS:-5}"
  --min-score "${MIN_SCORE:-0.3}"
)

if [[ -n "${JOB_QUERY_SEARCH:-}" ]]; then
  args+=(--query-search "${JOB_QUERY_SEARCH}")
fi

if [[ -n "${BLOCKED_KEYS:-}" ]]; then
  read -r -a blocked_keys <<< "${BLOCKED_KEYS}"
  args+=(--blocked-keys "${blocked_keys[@]}")
fi

status=0
"${args[@]}" || status=$?

finished_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
printf '{"finished_at":"%s","exit_code":%d}\n' "$finished_at" "$status" > "${DATA_DIR:-/data}/last_run.json"

exit "$status"

