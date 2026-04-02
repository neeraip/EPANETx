#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/check_epanet_parity.sh [options] [-- <inp1> <inp2> ...]

Options:
  --epanet-bin <path>    EPANET reference binary (default: bin/runepanet-epanet-v2.3.5)
  --epanetx-bin <path>   EPANETx binary (default: bin/epanetx)
  --manifest <path>      File containing .inp paths (one per line, # for comments)
  --output-dir <path>    Directory for run artifacts (default: /tmp/epanet-parity)
  --keep-artifacts       Keep artifacts even if all comparisons pass
  -h, --help             Show this help message

Notes:
  - If no manifest or positional .inp files are provided, defaults are:
      example-networks/Net1.inp example-networks/Net2.inp example-networks/Net3.inp
  - Parity check is strict byte-for-byte comparison of .out files.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EPANET_BIN="$REPO_ROOT/bin/runepanet-epanet-v2.3.5"
EPANETX_BIN="$REPO_ROOT/bin/epanetx"
MANIFEST=""
OUTPUT_DIR="/tmp/epanet-parity"
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
    --output-dir)
      shift
      OUTPUT_DIR="$1"
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

if [[ -n "$MANIFEST" ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 2
  fi
  while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [[ -z "$line" ]] && continue
    INPUTS+=("$line")
  done < "$MANIFEST"
fi

if [[ ${#INPUTS[@]} -eq 0 ]]; then
  INPUTS=(
    "$REPO_ROOT/example-networks/Net1.inp"
    "$REPO_ROOT/example-networks/Net2.inp"
    "$REPO_ROOT/example-networks/Net3.inp"
  )
fi

if [[ ! -x "$EPANET_BIN" ]]; then
  echo "ERROR: EPANET reference binary is not executable: $EPANET_BIN" >&2
  exit 2
fi

if [[ ! -x "$EPANETX_BIN" ]]; then
  echo "ERROR: EPANETx binary is not executable: $EPANETX_BIN" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
run_dir="$OUTPUT_DIR/run-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run_dir"

echo "Running parity checks..."
echo "EPANET   : $EPANET_BIN"
echo "EPANETx  : $EPANETX_BIN"
echo "Artifacts: $run_dir"

pass_count=0
fail_count=0

for inp in "${INPUTS[@]}"; do
  if [[ ! -f "$inp" ]]; then
    echo "FAIL missing input: $inp"
    fail_count=$((fail_count + 1))
    continue
  fi

  base="$(basename "$inp" .inp)"
  ref_rpt="$run_dir/${base}.epanet.rpt"
  ref_out="$run_dir/${base}.epanet.out"
  x_rpt="$run_dir/${base}.epanetx.rpt"
  x_out="$run_dir/${base}.epanetx.out"

  if ! "$EPANET_BIN" "$inp" "$ref_rpt" "$ref_out" >/dev/null 2>&1; then
    echo "FAIL EPANET run failed: $inp"
    fail_count=$((fail_count + 1))
    continue
  fi

  if ! "$EPANETX_BIN" "$inp" "$x_rpt" "$x_out" >/dev/null 2>&1; then
    echo "FAIL EPANETx run failed: $inp"
    fail_count=$((fail_count + 1))
    continue
  fi

  if cmp -s "$ref_out" "$x_out"; then
    echo "PASS $inp"
    pass_count=$((pass_count + 1))
  else
    echo "FAIL .out mismatch: $inp"
    fail_count=$((fail_count + 1))
  fi
done

echo "Summary: pass=$pass_count fail=$fail_count"

if [[ $fail_count -eq 0 && $KEEP_ARTIFACTS -eq 0 ]]; then
  rm -rf "$run_dir"
  echo "Artifacts removed (all parity checks passed)."
else
  echo "Artifacts kept: $run_dir"
fi

if [[ $fail_count -ne 0 ]]; then
  exit 1
fi
