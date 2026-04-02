#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_validation_gates.sh [options] [-- <inp1> <inp2> ...]

Options:
  --epanet-bin <path>           EPANET reference binary (default: bin/runepanet-epanet-v2.3.5)
  --epanetx-bin <path>          EPANETx binary (default: bin/epanetx)
  --manifest <path>             File containing .inp paths (one per line, # for comments)
  --runs <n>                    Timed runs per binary/input pair for benchmark gate (default: 5)
  --max-regression-pct <pct>    Maximum allowed EPANETx slowdown vs EPANET, percent (default: 0)
  --parity-output-dir <path>    Parity artifact directory root (default: /tmp/epanet-parity)
  --bench-output-dir <path>     Benchmark artifact directory root (default: /tmp/epanet-bench)
  --keep-artifacts              Keep all artifacts from parity and benchmark scripts
  -h, --help                    Show this help message

Behavior:
  1. Runs strict .out parity checks (fails fast on mismatch)
  2. Runs benchmark and reads summary CSV
  3. Fails if any input exceeds max regression percent threshold
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EPANET_BIN="$REPO_ROOT/bin/runepanet-epanet-v2.3.5"
EPANETX_BIN="$REPO_ROOT/bin/epanetx"
MANIFEST=""
RUNS=5
MAX_REGRESSION_PCT=0
PARITY_OUTPUT_DIR="/tmp/epanet-parity"
BENCH_OUTPUT_DIR="/tmp/epanet-bench"
KEEP_ARTIFACTS=0

INPUTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --epanet-bin)
      shift
      EPANET_BIN="$1"
      ;;
    --epanetx-bin)
      shift
      EPANETX_BIN="$1"
      ;;
    --manifest)
      shift
      MANIFEST="$1"
      ;;
    --runs)
      shift
      RUNS="$1"
      ;;
    --max-regression-pct)
      shift
      MAX_REGRESSION_PCT="$1"
      ;;
    --parity-output-dir)
      shift
      PARITY_OUTPUT_DIR="$1"
      ;;
    --bench-output-dir)
      shift
      BENCH_OUTPUT_DIR="$1"
      ;;
    --keep-artifacts)
      KEEP_ARTIFACTS=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        INPUTS+=("$1")
        shift
      done
      break
      ;;
    *)
      INPUTS+=("$1")
      ;;
  esac
  shift
done

echo "[gate] Running parity gate..."
parity_cmd=(
  "$REPO_ROOT/scripts/check_epanet_parity.sh"
  --epanet-bin "$EPANET_BIN"
  --epanetx-bin "$EPANETX_BIN"
  --output-dir "$PARITY_OUTPUT_DIR"
)
if [[ -n "$MANIFEST" ]]; then
  parity_cmd+=(--manifest "$MANIFEST")
fi
if [[ ${#INPUTS[@]} -gt 0 ]]; then
  parity_cmd+=(-- "${INPUTS[@]}")
fi
if [[ $KEEP_ARTIFACTS -eq 1 ]]; then
  parity_cmd+=(--keep-artifacts)
fi
"${parity_cmd[@]}"

echo "[gate] Running benchmark gate..."
bench_cmd=(
  "$REPO_ROOT/scripts/benchmark_epanet_vs_epanetx.sh"
  --epanet-bin "$EPANET_BIN"
  --epanetx-bin "$EPANETX_BIN"
  --runs "$RUNS"
  --output-dir "$BENCH_OUTPUT_DIR"
)
if [[ -n "$MANIFEST" ]]; then
  bench_cmd+=(--manifest "$MANIFEST")
fi
if [[ ${#INPUTS[@]} -gt 0 ]]; then
  bench_cmd+=(-- "${INPUTS[@]}")
fi
if [[ $KEEP_ARTIFACTS -eq 1 ]]; then
  bench_cmd+=(--keep-artifacts)
fi
"${bench_cmd[@]}"

latest_run_dir="$(ls -1dt "$BENCH_OUTPUT_DIR"/run-* 2>/dev/null | head -n 1 || true)"
if [[ -z "$latest_run_dir" ]]; then
  echo "ERROR: could not locate benchmark run directory under $BENCH_OUTPUT_DIR" >&2
  exit 1
fi
summary_csv="$latest_run_dir/summary.csv"
if [[ ! -f "$summary_csv" ]]; then
  echo "ERROR: benchmark summary not found: $summary_csv" >&2
  exit 1
fi

echo "[gate] Evaluating benchmark threshold (max regression: ${MAX_REGRESSION_PCT}%)"
python3 - "$summary_csv" "$MAX_REGRESSION_PCT" <<'PY'
import csv
import sys

summary_csv = sys.argv[1]
max_regression_pct = float(sys.argv[2])

failed = False
checked = 0

with open(summary_csv, "r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        status = row.get("status", "")
        inp = row.get("input", "")
        if status != "ok":
            print(f"FAIL {inp}: benchmark status={status}")
            failed = True
            continue
        checked += 1
        pct = float(row["epanetx_vs_epanet_pct"])
        if pct > max_regression_pct:
            print(f"FAIL {inp}: regression {pct:.2f}% > allowed {max_regression_pct:.2f}%")
            failed = True
        else:
            print(f"PASS {inp}: regression {pct:.2f}% <= allowed {max_regression_pct:.2f}%")

if checked == 0:
    print("FAIL no benchmark rows evaluated")
    failed = True

sys.exit(1 if failed else 0)
PY

echo "[gate] All validation gates passed."
