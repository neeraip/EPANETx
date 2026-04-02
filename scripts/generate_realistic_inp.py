#!/usr/bin/env python3
"""
Generate a large, realistic-style EPANET INP file.

The generator is topology-aware (district grids + trunk mains), terrain-aware
(elevation field), and demand-aware (land-use classes with diurnal patterns).

Example:
  python3 scripts/generate_realistic_inp.py \
                --out benchmarks/networks/realistic_city_180x180.inp \
    --district-rows 3 --district-cols 3 --district-size 60 --seed 42
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class Junction:
    jid: str
    elev: float
    demand: float
    pattern: str
    x: float
    y: float
    zone: int


@dataclass
class Tank:
    tid: str
    elev: float
    init_level: float
    min_level: float
    max_level: float
    diameter: float
    min_vol: float
    x: float
    y: float


@dataclass
class Pipe:
    pid: str
    n1: str
    n2: str
    length: float
    diameter_mm: float
    roughness: float
    minor_loss: float
    status: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate realistic large-scale EPANET INP")
    p.add_argument("--out", required=True, help="Output .inp path")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--district-rows", type=int, default=3)
    p.add_argument("--district-cols", type=int, default=3)
    p.add_argument("--district-size", type=int, default=60, help="Junction rows/cols per district")
    p.add_argument("--spacing", type=float, default=140.0, help="Pipe segment length in meters")
    p.add_argument("--trunk-step", type=int, default=12, help="Every N rows/cols becomes a trunk")
    p.add_argument("--base-elev", type=float, default=180.0)
    p.add_argument("--elev-grad-x", type=float, default=0.045, help="Elevation rise per meter in x")
    p.add_argument("--elev-grad-y", type=float, default=-0.012, help="Elevation rise per meter in y")
    p.add_argument("--daily-mult", type=float, default=1.0, help="Global demand multiplier")
    p.add_argument("--zones", type=int, default=3, help="Pressure-zone count")
    return p.parse_args()


def pattern_defs() -> Dict[str, List[float]]:
    return {
        "P_RES": [0.55, 0.48, 0.43, 0.41, 0.45, 0.62, 0.84, 1.05, 1.02, 0.94, 0.90, 0.92,
                  0.95, 0.97, 1.00, 1.05, 1.18, 1.32, 1.38, 1.30, 1.12, 0.93, 0.76, 0.63],
        "P_COM": [0.16, 0.14, 0.12, 0.11, 0.14, 0.24, 0.48, 0.86, 1.12, 1.20, 1.22, 1.21,
                  1.18, 1.16, 1.14, 1.17, 1.13, 1.05, 0.84, 0.60, 0.44, 0.33, 0.25, 0.19],
        "P_IND": [0.82, 0.80, 0.78, 0.78, 0.80, 0.88, 0.96, 1.03, 1.07, 1.10, 1.12, 1.10,
                  1.08, 1.06, 1.08, 1.09, 1.08, 1.05, 1.00, 0.95, 0.92, 0.90, 0.87, 0.84],
    }


def land_use(rng: random.Random) -> Tuple[str, float]:
    # (pattern, base-demand m3/s)
    r = rng.random()
    if r < 0.68:
        # Residential demand centered around moderate values.
        return "P_RES", max(0.00015, rng.lognormvariate(math.log(0.0013), 0.45))
    if r < 0.90:
        return "P_COM", max(0.00020, rng.lognormvariate(math.log(0.0022), 0.40))
    return "P_IND", max(0.00030, rng.lognormvariate(math.log(0.0030), 0.35))


def pipe_attrs(is_trunk: bool, rng: random.Random) -> Tuple[float, float, float]:
    # diameter mm, roughness HW C, minor loss
    if is_trunk:
        diam = rng.choice([300, 350, 400, 450, 500, 600])
        c_hw = rng.choice([130, 125, 120])
        km = rng.uniform(0.0, 0.05)
    else:
        diam = rng.choice([100, 150, 200, 250, 300])
        c_hw = rng.choice([140, 135, 130, 125])
        km = rng.uniform(0.0, 0.15)
    return float(diam), float(c_hw), round(km, 4)


def build_network(args: argparse.Namespace):
    rng = random.Random(args.seed)

    rows = args.district_rows * args.district_size
    cols = args.district_cols * args.district_size
    spacing = args.spacing

    junctions: List[Junction] = []
    pipes: List[Pipe] = []

    elev_values: List[float] = []

    for r in range(rows):
        for c in range(cols):
            x = c * spacing
            y = r * spacing
            # Terrain model: gradient + broad undulation + local noise
            und = 8.0 * math.sin(x / 3500.0) + 5.0 * math.cos(y / 2900.0)
            noise = rng.uniform(-1.2, 1.2)
            elev = args.base_elev + args.elev_grad_x * x + args.elev_grad_y * y + und + noise
            patt, dem = land_use(rng)
            jid = f"J{r+1}_{c+1}"
            junctions.append(Junction(jid, round(elev, 3), dem * args.daily_mult, patt, x, y, zone=0))
            elev_values.append(elev)

    # Elevation-based pressure zones.
    elev_sorted = sorted(elev_values)
    cuts = []
    for i in range(1, args.zones):
        idx = int(i * len(elev_sorted) / args.zones)
        cuts.append(elev_sorted[idx])

    def zone_for_elev(e: float) -> int:
        z = 1
        for cut in cuts:
            if e > cut:
                z += 1
        return z

    for j in junctions:
        j.zone = zone_for_elev(j.elev)

    # Utility map for indexing neighbors.
    idx_map: Dict[Tuple[int, int], Junction] = {}
    for j in junctions:
        rr, cc = j.jid[1:].split("_")
        idx_map[(int(rr) - 1, int(cc) - 1)] = j

    def is_trunk(rc: int) -> bool:
        return rc % args.trunk_step == 0

    pcount = 0
    for r in range(rows):
        for c in range(cols):
            j = idx_map[(r, c)]
            if c + 1 < cols:
                k = idx_map[(r, c + 1)]
                pcount += 1
                trunk = is_trunk(r) or is_trunk(c)
                diam, rough, km = pipe_attrs(trunk, rng)
                pipes.append(Pipe(f"P{pcount}", j.jid, k.jid, spacing, diam, rough, km, "Open"))
            if r + 1 < rows:
                k = idx_map[(r + 1, c)]
                pcount += 1
                trunk = is_trunk(r) or is_trunk(c)
                diam, rough, km = pipe_attrs(trunk, rng)
                pipes.append(Pipe(f"P{pcount}", j.jid, k.jid, spacing, diam, rough, km, "Open"))

    # Tanks: one per pressure zone near geometric center of zone nodes.
    tanks: List[Tank] = []
    for z in range(1, args.zones + 1):
        members = [j for j in junctions if j.zone == z]
        if not members:
            continue
        cx = sum(j.x for j in members) / len(members)
        cy = sum(j.y for j in members) / len(members)
        ce = sum(j.elev for j in members) / len(members)
        tanks.append(Tank(
            tid=f"T{z}",
            elev=round(ce + 18.0, 3),
            init_level=10.0,
            min_level=4.0,
            max_level=16.0,
            diameter=55.0 + 6.0 * z,
            min_vol=0.0,
            x=cx,
            y=cy,
        ))

    # Reservoir and pump station at lower-left edge.
    reservoir = ("R1", args.base_elev + 60.0, -spacing * 2.0, -spacing * 2.0)

    # Connect each tank to nearest junction in same zone with a large pipe.
    for t in tanks:
        nearest = min(
            (j for j in junctions if j.zone == int(t.tid[1:])),
            key=lambda j: (j.x - t.x) ** 2 + (j.y - t.y) ** 2,
        )
        pcount += 1
        pipes.append(Pipe(f"P{pcount}", t.tid, nearest.jid, spacing * 1.2, 500.0, 120.0, 0.02, "Open"))

    return rows, cols, junctions, pipes, tanks, reservoir


def write_inp(args: argparse.Namespace) -> None:
    rows, cols, junctions, pipes, tanks, reservoir = build_network(args)
    patterns = pattern_defs()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("[TITLE]")
    lines.append("Realistic large-scale synthetic distribution system")
    lines.append(f"rows={rows} cols={cols} seed={args.seed}")
    lines.append("")

    lines.append("[JUNCTIONS]")
    lines.append(";ID\tElev\tDemand\tPattern")
    for j in junctions:
        lines.append(f"{j.jid}\t{j.elev:.3f}\t{j.demand:.7f}\t{j.pattern}")
    lines.append("")

    lines.append("[RESERVOIRS]")
    lines.append(";ID\tHead\tPattern")
    lines.append(f"{reservoir[0]}\t{reservoir[1]:.3f}")
    lines.append("")

    lines.append("[TANKS]")
    lines.append(";ID\tElev\tInitLevel\tMinLevel\tMaxLevel\tDiameter\tMinVol\tVolCurve")
    for t in tanks:
        lines.append(
            f"{t.tid}\t{t.elev:.3f}\t{t.init_level:.3f}\t{t.min_level:.3f}\t"
            f"{t.max_level:.3f}\t{t.diameter:.3f}\t{t.min_vol:.3f}"
        )
    lines.append("")

    lines.append("[PIPES]")
    lines.append(";ID\tNode1\tNode2\tLength\tDiameter\tRoughness\tMinorLoss\tStatus")
    for p in pipes:
        lines.append(
            f"{p.pid}\t{p.n1}\t{p.n2}\t{p.length:.2f}\t{p.diameter_mm:.1f}\t"
            f"{p.roughness:.1f}\t{p.minor_loss:.4f}\t{p.status}"
        )
    lines.append("")

    lines.append("[PUMPS]")
    lines.append(";ID\tNode1\tNode2\tParameters")
    if tanks:
        lines.append(f"PU1\t{reservoir[0]}\t{tanks[0].tid}\tHEAD\tH_PUMP_MAIN")
    lines.append("")

    lines.append("[CURVES]")
    lines.append(";ID\tX-Value\tY-Value")
    lines.append("H_PUMP_MAIN\t0\t85")
    lines.append("H_PUMP_MAIN\t0.8\t72")
    lines.append("H_PUMP_MAIN\t1.6\t56")
    lines.append("H_PUMP_MAIN\t2.4\t35")
    lines.append("")

    lines.append("[PATTERNS]")
    lines.append(";ID\tMultipliers")
    for pid, mults in patterns.items():
        chunk = [f"{m:.3f}" for m in mults]
        lines.append(f"{pid}\t" + "\t".join(chunk))
    lines.append("")

    lines.append("[CONTROLS]")
    if tanks:
        lines.append(f"LINK PU1 OPEN IF TANK {tanks[0].tid} BELOW {tanks[0].min_level + 0.5:.3f}")
        lines.append(f"LINK PU1 CLOSED IF TANK {tanks[0].tid} ABOVE {tanks[0].max_level - 0.5:.3f}")
    lines.append("")

    lines.append("[COORDINATES]")
    lines.append(";Node\tX-Coord\tY-Coord")
    lines.append(f"{reservoir[0]}\t{reservoir[2]:.2f}\t{reservoir[3]:.2f}")
    for j in junctions:
        lines.append(f"{j.jid}\t{j.x:.2f}\t{j.y:.2f}")
    for t in tanks:
        lines.append(f"{t.tid}\t{t.x:.2f}\t{t.y:.2f}")
    lines.append("")

    lines.append("[OPTIONS]")
    lines.append("UNITS\tLPS")
    lines.append("HEADLOSS\tH-W")
    lines.append("SPECIFIC GRAVITY\t1.0")
    lines.append("VISCOSITY\t1.0")
    lines.append("TRIALS\t60")
    lines.append("ACCURACY\t0.001")
    lines.append("CHECKFREQ\t2")
    lines.append("MAXCHECK\t20")
    lines.append("DAMPLIMIT\t0")
    lines.append("")

    lines.append("[TIMES]")
    lines.append("DURATION\t24:00")
    lines.append("HYDRAULIC TIMESTEP\t1:00")
    lines.append("QUALITY TIMESTEP\t0:05")
    lines.append("PATTERN TIMESTEP\t1:00")
    lines.append("PATTERN START\t0:00")
    lines.append("REPORT TIMESTEP\t1:00")
    lines.append("REPORT START\t0:00")
    lines.append("START CLOCKTIME\t12 am")
    lines.append("STATISTIC\tNONE")
    lines.append("")

    lines.append("[REPORT]")
    lines.append("STATUS\tNO")
    lines.append("SUMMARY\tYES")
    lines.append("NODES\tNONE")
    lines.append("LINKS\tNONE")
    lines.append("")

    lines.append("[END]")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {out}")
    print(f"junctions={len(junctions)} pipes={len(pipes)} tanks={len(tanks)}")
    print(f"rows={rows} cols={cols} seed={args.seed}")


if __name__ == "__main__":
    write_inp(parse_args())
