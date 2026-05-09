#!/usr/bin/env bash
# Convenience script: POST every snapshot fixture to /analyse_risk.
#
# Usage:  ./tests/fixtures/snapshots/post_all.sh [BASE_URL]
# Default BASE_URL is http://127.0.0.1:5050.

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5050}"
DIR="$(cd "$(dirname "$0")" && pwd)"

for f in clean_account latency_arbitrage scalping swap_arbitrage bonus_abuse; do
  echo "=============================================================="
  echo "POST $BASE_URL/analyse_risk  ←  ${f}.json"
  echo "=============================================================="
  curl -sS -X POST "$BASE_URL/analyse_risk" \
       -H 'Content-Type: application/json' \
       --data @"$DIR/${f}.json" | python -m json.tool
  echo
done
