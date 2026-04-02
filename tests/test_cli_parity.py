#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import subprocess
import sys
from pathlib import Path


SKIP_EXIT_CODE = 77


def find_default_baseline(root: Path) -> Path | None:
    candidates = [
        root.parent / "EPANET" / "build" / "bin" / "runepanet",
        root.parent / "EPANET" / "bin" / "runepanet",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run_model(exe: Path, inp: Path, rpt: Path, out: Path) -> int:
    proc = subprocess.run([str(exe), str(inp), str(rpt), str(out)])
    return proc.returncode


def first_difference(a: Path, b: Path, chunk_size: int = 65536) -> tuple[int, int, int] | None:
    offset = 0
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ba = fa.read(chunk_size)
            bb = fb.read(chunk_size)
            if not ba and not bb:
                return None

            m = min(len(ba), len(bb))
            for i in range(m):
                if ba[i] != bb[i]:
                    return (offset + i, ba[i], bb[i])

            if len(ba) != len(bb):
                if len(ba) > len(bb):
                    return (offset + m, ba[m], -1)
                return (offset + m, -1, bb[m])

            offset += m


def main() -> int:
    p = argparse.ArgumentParser(description="CLI parity check: EPANETx vs base EPANET")
    p.add_argument("--epanetx-exe", required=True, help="Path to EPANETx executable")
    p.add_argument("--baseline-exe", default="", help="Path to baseline runepanet executable")
    p.add_argument("--fixture", required=True, help="Fixture INP file")
    p.add_argument("--workdir", required=True, help="Output folder for temporary parity files")
    args = p.parse_args()

    epanetx_exe = Path(args.epanetx_exe).resolve()
    fixture = Path(args.fixture).resolve()
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    if not epanetx_exe.exists():
        print(f"FAIL: EPANETx executable not found: {epanetx_exe}")
        return 2

    baseline_exe = Path(args.baseline_exe).resolve() if args.baseline_exe else find_default_baseline(Path(__file__).resolve().parents[1])
    if baseline_exe is None or not baseline_exe.exists():
        print("SKIP: baseline runepanet executable not found; parity check skipped")
        return SKIP_EXIT_CODE

    if not fixture.exists():
        print(f"FAIL: fixture not found: {fixture}")
        return 2

    nx_rpt = workdir / "epanetx.rpt"
    nx_out = workdir / "epanetx.out"
    base_rpt = workdir / "epanet.rpt"
    base_out = workdir / "epanet.out"

    rc_nx = run_model(epanetx_exe, fixture, nx_rpt, nx_out)
    rc_base = run_model(baseline_exe, fixture, base_rpt, base_out)

    if rc_nx != 0:
        print(f"FAIL: EPANETx run failed with exit code {rc_nx}")
        return 1
    if rc_base != 0:
        print(f"FAIL: baseline EPANET run failed with exit code {rc_base}")
        return 1

    if not nx_out.exists() or not base_out.exists():
        print("FAIL: one or both output files are missing")
        return 1

    same = filecmp.cmp(nx_out, base_out, shallow=False)
    if same:
        print("PASS: parity matched (.out files are identical)")
        return 0

    nx_size = nx_out.stat().st_size
    base_size = base_out.stat().st_size
    print("FAIL: parity mismatch (.out files differ)")
    print(f"  epanetx.out size: {nx_size}")
    print(f"  epanet.out size : {base_size}")
    diff = first_difference(nx_out, base_out)
    if diff is not None:
        off, xb, bb = diff
        x_txt = f"0x{xb:02x}" if xb >= 0 else "<eof>"
        b_txt = f"0x{bb:02x}" if bb >= 0 else "<eof>"
        print(f"  first diff @ byte {off}: epanetx={x_txt}, epanet={b_txt}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
