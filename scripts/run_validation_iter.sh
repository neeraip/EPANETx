#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/benchmarks/networks/complex_suite/manifest_iter.txt"

RUNS=4
MAX_REGRESSION_PCT=0

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: iteration manifest not found: $MANIFEST" >&2
  exit 1
fi

"$REPO_ROOT/scripts/run_validation_gates.sh" \
  --runs "$RUNS" \
  --max-regression-pct "$MAX_REGRESSION_PCT" \
  --manifest "$MANIFEST" \
  "$@"
