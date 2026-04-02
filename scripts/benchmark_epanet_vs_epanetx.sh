#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/benchmark_epanet_vs_epanetx.sh [options] [-- <inp1> <inp2> ...]

Options:
  --epanet-bin <path>    EPANET reference binary (default: bin/runepanet-epanet-v2.3.5)
  --epanetx-bin <path>   EPANETx binary (default: bin/epanetx)
  --manifest <path>      File containing .inp paths (one per line, # for comments)
  --runs <n>             Timed runs per binary/input pair (default: 5)
  --min-effect-pct <pct> Minimum absolute percent difference to flag as meaningful (default: 0)
  --cache-epanet         Reuse cached EPANET timing runs when binary/input/runs match (default: enabled)
  --no-cache-epanet      Disable EPANET timing cache and always rerun EPANET
  --cache-dir <path>     Cache directory for EPANET timing runs (default: .cache/epanet-bench)
  --output-dir <path>    Directory for benchmark artifacts (default: /tmp/epanet-bench)
  --keep-artifacts       Keep artifacts after completion
  -h, --help             Show this help message

Notes:
  - If no manifest or positional .inp files are provided, defaults are:
      example-networks/Net1.inp example-networks/Net2.inp example-networks/Net3.inp
  - Runs one warmup execution per binary/input before timed runs.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EPANET_BIN="$REPO_ROOT/bin/runepanet-epanet-v2.3.5"
EPANETX_BIN="$REPO_ROOT/bin/epanetx"
MANIFEST=""
RUNS=5
MIN_EFFECT_PCT=0
EPANET_CACHE=1
CACHE_DIR="$REPO_ROOT/.cache/epanet-bench"
OUTPUT_DIR="/tmp/epanet-bench"
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
    --min-effect-pct)
      shift
      MIN_EFFECT_PCT="$1"
      ;;
    --cache-epanet)
      EPANET_CACHE=1
      ;;
    --no-cache-epanet)
      EPANET_CACHE=0
      ;;
    --cache-dir)
      shift
      CACHE_DIR="$1"
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

if ! [[ "$RUNS" =~ ^[0-9]+$ ]] || [[ "$RUNS" -lt 1 ]]; then
  echo "ERROR: --runs must be an integer >= 1" >&2
  exit 2
fi

if ! [[ "$MIN_EFFECT_PCT" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: --min-effect-pct must be numeric" >&2
  exit 2
fi

if python3 - "$MIN_EFFECT_PCT" <<'PY'
import sys
v = float(sys.argv[1])
sys.exit(0 if v >= 0.0 else 1)
PY
then
  :
else
  echo "ERROR: --min-effect-pct must be >= 0" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
run_dir="$OUTPUT_DIR/run-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run_dir"
if [[ "$EPANET_CACHE" -eq 1 ]]; then
  mkdir -p "$CACHE_DIR"
fi

inputs_file="$run_dir/inputs.txt"
printf '%s\n' "${INPUTS[@]}" > "$inputs_file"

summary_csv="$run_dir/summary.csv"

python3 - "$EPANET_BIN" "$EPANETX_BIN" "$RUNS" "$MIN_EFFECT_PCT" "$run_dir" "$inputs_file" "$summary_csv" "$EPANET_CACHE" "$CACHE_DIR" <<'PY'
import csv
import hashlib
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

epanet_bin = sys.argv[1]
epanetx_bin = sys.argv[2]
runs = int(sys.argv[3])
min_effect_pct = float(sys.argv[4])
run_dir = pathlib.Path(sys.argv[5])
inputs_file = pathlib.Path(sys.argv[6])
summary_csv = pathlib.Path(sys.argv[7])
epanet_cache_enabled = bool(int(sys.argv[8]))
cache_dir = pathlib.Path(sys.argv[9])

def p95(values):
  vals = sorted(values)
  if not vals:
    return float("nan")
  idx = max(0, min(len(vals) - 1, int(0.95 * len(vals) + 0.999999) - 1))
  return vals[idx]

def stdev_or_zero(values):
  return statistics.stdev(values) if len(values) > 1 else 0.0

def run_once(exe: str, inp: pathlib.Path, rpt: pathlib.Path, out: pathlib.Path) -> float:
    t0 = time.perf_counter()
    cp = subprocess.run([exe, str(inp), str(rpt), str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if cp.returncode != 0:
        raise RuntimeError(f"run failed: {exe} {inp}")
    return time.perf_counter() - t0

rows = []

def cache_key(epanet_exe: str, inp: pathlib.Path, runs: int) -> str:
  exe_path = pathlib.Path(epanet_exe).resolve()
  st = exe_path.stat()
  key = "|".join([
    str(exe_path),
    str(st.st_size),
    str(st.st_mtime_ns),
    str(inp.resolve()),
    str(runs),
  ])
  return hashlib.sha256(key.encode("utf-8")).hexdigest()

with inputs_file.open("r", encoding="utf-8") as f:
    inputs = [pathlib.Path(line.strip()) for line in f if line.strip()]

for inp in inputs:
    if not inp.exists():
        rows.append({
            "input": str(inp),
            "status": "missing-input",
            "epanet_avg_s": "",
          "epanet_median_s": "",
          "epanet_p95_s": "",
          "epanet_stdev_s": "",
            "epanetx_avg_s": "",
          "epanetx_median_s": "",
          "epanetx_p95_s": "",
          "epanetx_stdev_s": "",
            "epanetx_vs_epanet_pct": "",
          "epanetx_vs_epanet_median_pct": "",
            "epanetx_speedup_x": "",
          "epanetx_speedup_median_x": "",
          "effect_min_pct": f"{min_effect_pct:.2f}",
          "effect_flag": "n/a",
        })
        continue

    base = inp.stem

    # Warmup
    epanet_cache_hit = False
    epanet_cache_path = cache_dir / f"{cache_key(epanet_bin, inp, runs)}.json"

    epanet_times = []
    if epanet_cache_enabled and epanet_cache_path.exists():
      try:
        payload = json.loads(epanet_cache_path.read_text(encoding="utf-8"))
        cached_runs = payload.get("runs")
        cached_times = payload.get("epanet_times", [])
        if cached_runs == runs and isinstance(cached_times, list) and len(cached_times) == runs:
          epanet_times = [float(x) for x in cached_times]
          epanet_cache_hit = True
      except Exception:
        epanet_times = []

    if not epanet_cache_hit:
      run_once(epanet_bin, inp, run_dir / f"{base}.epanet.warmup.rpt", run_dir / f"{base}.epanet.warmup.out")
    run_once(epanetx_bin, inp, run_dir / f"{base}.epanetx.warmup.rpt", run_dir / f"{base}.epanetx.warmup.out")

    epanetx_times = []

    if not epanet_cache_hit:
      for i in range(1, runs + 1):
        epanet_times.append(run_once(epanet_bin, inp, run_dir / f"{base}.epanet.{i}.rpt", run_dir / f"{base}.epanet.{i}.out"))
      if epanet_cache_enabled:
        payload = {
          "epanet_bin": str(pathlib.Path(epanet_bin).resolve()),
          "input": str(inp.resolve()),
          "runs": runs,
          "epanet_times": epanet_times,
        }
        epanet_cache_path.write_text(json.dumps(payload), encoding="utf-8")

    for i in range(1, runs + 1):
        epanetx_times.append(run_once(epanetx_bin, inp, run_dir / f"{base}.epanetx.{i}.rpt", run_dir / f"{base}.epanetx.{i}.out"))

    e_avg = statistics.mean(epanet_times)
    e_median = statistics.median(epanet_times)
    e_p95 = p95(epanet_times)
    e_stdev = stdev_or_zero(epanet_times)

    x_avg = statistics.mean(epanetx_times)
    x_median = statistics.median(epanetx_times)
    x_p95 = p95(epanetx_times)
    x_stdev = stdev_or_zero(epanetx_times)

    pct = ((x_avg - e_avg) / e_avg * 100.0) if e_avg > 0 else float("inf")
    pct_median = ((x_median - e_median) / e_median * 100.0) if e_median > 0 else float("inf")
    speedup = (e_avg / x_avg) if x_avg > 0 else float("inf")
    speedup_median = (e_median / x_median) if x_median > 0 else float("inf")

    effect_flag = "meaningful" if abs(pct) >= min_effect_pct else "below-threshold"

    rows.append({
        "input": str(inp),
        "status": "ok",
        "epanet_avg_s": f"{e_avg:.6f}",
      "epanet_median_s": f"{e_median:.6f}",
      "epanet_p95_s": f"{e_p95:.6f}",
      "epanet_stdev_s": f"{e_stdev:.6f}",
        "epanetx_avg_s": f"{x_avg:.6f}",
      "epanetx_median_s": f"{x_median:.6f}",
      "epanetx_p95_s": f"{x_p95:.6f}",
      "epanetx_stdev_s": f"{x_stdev:.6f}",
        "epanetx_vs_epanet_pct": f"{pct:.2f}",
      "epanetx_vs_epanet_median_pct": f"{pct_median:.2f}",
        "epanetx_speedup_x": f"{speedup:.3f}",
      "epanetx_speedup_median_x": f"{speedup_median:.3f}",
      "effect_min_pct": f"{min_effect_pct:.2f}",
      "effect_flag": effect_flag,
      "epanet_cache": "hit" if epanet_cache_hit else "miss",
    })

with summary_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "input",
            "status",
            "epanet_avg_s",
          "epanet_median_s",
          "epanet_p95_s",
          "epanet_stdev_s",
            "epanetx_avg_s",
          "epanetx_median_s",
          "epanetx_p95_s",
          "epanetx_stdev_s",
            "epanetx_vs_epanet_pct",
          "epanetx_vs_epanet_median_pct",
            "epanetx_speedup_x",
          "epanetx_speedup_median_x",
          "effect_min_pct",
          "effect_flag",
          "epanet_cache",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"Benchmark summary CSV: {summary_csv}")
print("input,status,epanet_avg_s,epanet_median_s,epanet_p95_s,epanet_stdev_s,epanetx_avg_s,epanetx_median_s,epanetx_p95_s,epanetx_stdev_s,epanetx_vs_epanet_pct,epanetx_vs_epanet_median_pct,epanetx_speedup_x,epanetx_speedup_median_x,effect_min_pct,effect_flag,epanet_cache")
for row in rows:
    print(",".join([
        row["input"],
        row["status"],
        row["epanet_avg_s"],
        row["epanet_median_s"],
        row["epanet_p95_s"],
        row["epanet_stdev_s"],
        row["epanetx_avg_s"],
        row["epanetx_median_s"],
        row["epanetx_p95_s"],
        row["epanetx_stdev_s"],
        row["epanetx_vs_epanet_pct"],
        row["epanetx_vs_epanet_median_pct"],
        row["epanetx_speedup_x"],
        row["epanetx_speedup_median_x"],
        row["effect_min_pct"],
        row["effect_flag"],
        row["epanet_cache"],
    ]))
PY

if [[ $KEEP_ARTIFACTS -eq 0 ]]; then
  find "$run_dir" -type f \( -name '*.rpt' -o -name '*.out' \) -delete
  echo "Retained compact artifacts: $run_dir (summary CSV + inputs list)"
else
  echo "Artifacts kept: $run_dir"
fi
