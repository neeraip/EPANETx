#!/usr/bin/env python3
"""Generate a diverse suite of complex EPANET benchmark networks.

This script wraps scripts/generate_realistic_inp.py, then rewrites key sections
per scenario to vary modeling options and runtime behavior.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    district_rows: int
    district_cols: int
    district_size: int
    spacing: float
    trunk_step: int
    zones: int
    options: List[str]
    times: List[str]
    report: List[str]
    energy: List[str]
    reactions: List[str]
    quality: List[str]
    sources: List[str]
    status_closed_stride: int
    emitter_stride: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a complex EPANET network suite")
    parser.add_argument(
        "--out-dir",
        default="benchmarks/networks/complex_suite",
        help="Output directory for generated .inp files",
    )
    parser.add_argument(
        "--manifest",
        default="benchmarks/networks/complex_suite/manifest.json",
        help="Path for scenario manifest JSON",
    )
    parser.add_argument(
        "--include-huge",
        action="store_true",
        help="Include two very large scenarios for stress testing",
    )
    return parser.parse_args()


def sectionize(text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().upper()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def assemble(sections: Dict[str, List[str]]) -> str:
    order = [
        "TITLE",
        "JUNCTIONS",
        "RESERVOIRS",
        "TANKS",
        "PIPES",
        "PUMPS",
        "VALVES",
        "PATTERNS",
        "CURVES",
        "CONTROLS",
        "RULES",
        "DEMANDS",
        "STATUS",
        "EMITTERS",
        "QUALITY",
        "SOURCES",
        "REACTIONS",
        "ENERGY",
        "MIXING",
        "TIMES",
        "REPORT",
        "OPTIONS",
        "COORDINATES",
        "VERTICES",
        "LABELS",
        "BACKDROP",
        "END",
    ]

    lines: List[str] = []
    for name in order:
        if name not in sections:
            continue
        lines.append(f"[{name}]")
        lines.extend(sections[name])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def collect_ids(section_lines: List[str]) -> List[str]:
    ids: List[str] = []
    for line in section_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        ids.append(stripped.split()[0])
    return ids


def build_status_section(pipe_ids: List[str], stride: int) -> List[str]:
    if stride <= 0:
        return [";ID\tStatus/Setting"]

    lines = [";ID\tStatus/Setting"]
    for idx, pipe_id in enumerate(pipe_ids):
        if idx > 0 and idx % stride == 0:
            lines.append(f"{pipe_id}\tCLOSED")
    return lines


def build_emitters_section(junction_ids: List[str], stride: int) -> List[str]:
    lines = [";Junction\tCoefficient"]
    if stride <= 0:
        return lines

    for idx, junction_id in enumerate(junction_ids):
        if idx > 0 and idx % stride == 0:
            coeff = 0.10 + (idx % 7) * 0.04
            lines.append(f"{junction_id}\t{coeff:.3f}")
    return lines


def normalize_pipes_for_dw_us_units(pipe_lines: List[str]) -> List[str]:
    """Adjust DW roughness to practical values for US customary flow-unit cases."""
    normalized: List[str] = []
    for line in pipe_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            normalized.append(line)
            continue

        parts = stripped.split()
        # Expected: ID Node1 Node2 Length Diameter Roughness MinorLoss Status
        if len(parts) < 8:
            normalized.append(line)
            continue

        try:
            diameter = float(parts[4])
        except ValueError:
            normalized.append(line)
            continue

        if diameter >= 20.0:
            roughness = 0.0050
        elif diameter >= 12.0:
            roughness = 0.0030
        else:
            roughness = 0.0015

        parts[5] = f"{roughness:.4f}"
        normalized.append("\t".join(parts))

    return normalized


def add_reservoir_bypass_pipe(
    pipe_lines: List[str],
    junction_ids: List[str],
    options_lines: List[str],
) -> List[str]:
    """Append an always-open reservoir bypass so controls cannot isolate all sources."""
    if not junction_ids:
        return pipe_lines

    max_pid = 0
    for line in pipe_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        pid = stripped.split()[0]
        if pid.startswith("P") and pid[1:].isdigit():
            max_pid = max(max_pid, int(pid[1:]))

    new_pid = f"P{max_pid + 1}"
    target_junction = junction_ids[len(junction_ids) // 2]

    options_upper = "\n".join(options_lines).upper()
    if "HEADLOSS\tD-W" in options_upper and "UNITS\tGPM" in options_upper:
        roughness = "0.0030"
    else:
        roughness = "120.0"

    bypass_line = f"{new_pid}\tR1\t{target_junction}\t1200.00\t300.0\t{roughness}\t0.0000\tOpen"
    return pipe_lines + [bypass_line]


def enrich(base_inp: Path, out_inp: Path, scenario: Scenario) -> Dict[str, int]:
    sections = sectionize(base_inp.read_text(encoding="utf-8"))

    junction_ids = collect_ids(sections.get("JUNCTIONS", []))
    pipe_ids = collect_ids(sections.get("PIPES", []))

    quality_lines = list(scenario.quality)
    if "QUALITY TRACE" in " ".join(scenario.options).upper() and junction_ids:
        trace_node = junction_ids[min(10, len(junction_ids) - 1)]
        quality_lines = [f";Node\tInitQual", f"{trace_node}\t100.0"]
        scenario_options = []
        for opt in scenario.options:
            if opt.upper().startswith("QUALITY TRACE"):
                scenario_options.append(f"QUALITY\tTRACE {trace_node}")
            else:
                scenario_options.append(opt)
        options_lines = scenario_options
    else:
        options_lines = list(scenario.options)

    if "STATUS" not in sections:
        sections["STATUS"] = []
    if "EMITTERS" not in sections:
        sections["EMITTERS"] = []
    if "QUALITY" not in sections:
        sections["QUALITY"] = []
    if "SOURCES" not in sections:
        sections["SOURCES"] = []
    if "REACTIONS" not in sections:
        sections["REACTIONS"] = []
    if "ENERGY" not in sections:
        sections["ENERGY"] = []
    if "MIXING" not in sections:
        sections["MIXING"] = []
    if "RULES" not in sections:
        sections["RULES"] = []
    if "VALVES" not in sections:
        sections["VALVES"] = []

    sections["TITLE"] = [
        f"Complex Suite Scenario: {scenario.name}",
        f"seed={scenario.seed} districts={scenario.district_rows}x{scenario.district_cols} size={scenario.district_size}",
    ]

    sections["PIPES"] = add_reservoir_bypass_pipe(
        sections.get("PIPES", []),
        junction_ids,
        options_lines,
    )

    options_upper = "\n".join(options_lines).upper()
    if "HEADLOSS\tD-W" in options_upper and "UNITS\tGPM" in options_upper:
        sections["PIPES"] = normalize_pipes_for_dw_us_units(sections.get("PIPES", []))

    sections["OPTIONS"] = options_lines
    sections["TIMES"] = list(scenario.times)
    sections["REPORT"] = list(scenario.report)
    sections["ENERGY"] = list(scenario.energy)
    sections["REACTIONS"] = list(scenario.reactions)
    sections["QUALITY"] = quality_lines
    sections["SOURCES"] = list(scenario.sources)
    sections["STATUS"] = build_status_section(pipe_ids, scenario.status_closed_stride)
    sections["EMITTERS"] = build_emitters_section(junction_ids, scenario.emitter_stride)

    if sections.get("VALVES") == []:
        sections["VALVES"] = [";ID\tNode1\tNode2\tDiameter\tType\tSetting\tMinorLoss"]

    if sections.get("RULES") == []:
        sections["RULES"] = ["; Intentionally left minimal; controls section remains active"]

    out_inp.write_text(assemble(sections), encoding="utf-8")

    return {
        "junctions": len(junction_ids),
        "pipes": len(pipe_ids),
    }


def scenarios(include_huge: bool) -> List[Scenario]:
    base = [
        Scenario(
            name="hw_lps_chlorine_dense",
            seed=101,
            district_rows=3,
            district_cols=3,
            district_size=22,
            spacing=130.0,
            trunk_step=8,
            zones=4,
            options=[
                "UNITS\tLPS",
                "HEADLOSS\tH-W",
                "TRIALS\t80",
                "ACCURACY\t0.0005",
                "CHECKFREQ\t2",
                "MAXCHECK\t20",
                "UNBALANCED\tCONTINUE 10",
                "DEMAND MULTIPLIER\t1.10",
                "EMITTER EXPONENT\t0.50",
                "QUALITY\tChlorine mg/L",
                "TOLERANCE\t0.001",
            ],
            times=[
                "DURATION\t24:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:15",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tYES", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t78", "GLOBAL PRICE\t0.09", "DEMAND CHARGE\t0.0"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t-0.30", "GLOBAL WALL\t-0.90"],
            quality=[";Node\tInitQual", "R1\t1.20"],
            sources=[";Node\tType\tQuality\tPattern", "R1\tCONCEN\t1.2"],
            status_closed_stride=180,
            emitter_stride=220,
        ),
        Scenario(
            name="dw_gpm_age_mixed",
            seed=202,
            district_rows=3,
            district_cols=2,
            district_size=26,
            spacing=150.0,
            trunk_step=10,
            zones=3,
            options=[
                "UNITS\tGPM",
                "HEADLOSS\tH-W",
                "SPECIFIC GRAVITY\t1.02",
                "VISCOSITY\t1.15",
                "TRIALS\t100",
                "ACCURACY\t0.001",
                "UNBALANCED\tCONTINUE 20",
                "DEMAND MULTIPLIER\t0.95",
                "QUALITY\tAGE",
            ],
            times=[
                "DURATION\t24:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:30",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tNO", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t75", "GLOBAL PRICE\t0.12", "DEMAND CHARGE\t2.0"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t0.00", "GLOBAL WALL\t0.00"],
            quality=[";Node\tInitQual"],
            sources=[";Node\tType\tQuality\tPattern"],
            status_closed_stride=0,
            emitter_stride=0,
        ),
        Scenario(
            name="cm_cmd_trace_pressure",
            seed=303,
            district_rows=2,
            district_cols=3,
            district_size=28,
            spacing=120.0,
            trunk_step=9,
            zones=5,
            options=[
                "UNITS\tCMD",
                "HEADLOSS\tC-M",
                "TRIALS\t120",
                "ACCURACY\t0.0008",
                "CHECKFREQ\t1",
                "MAXCHECK\t40",
                "UNBALANCED\tCONTINUE 30",
                "DEMAND MULTIPLIER\t1.25",
                "DEMAND MODEL\tPDA",
                "MINIMUM PRESSURE\t5",
                "REQUIRED PRESSURE\t30",
                "PRESSURE EXPONENT\t0.5",
                "QUALITY\tTRACE J1_1",
            ],
            times=[
                "DURATION\t18:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:15",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tYES", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t81", "GLOBAL PRICE\t0.15", "DEMAND CHARGE\t3.5"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t-0.15", "GLOBAL WALL\t-0.55"],
            quality=[";Node\tInitQual"],
            sources=[";Node\tType\tQuality\tPattern"],
            status_closed_stride=210,
            emitter_stride=260,
        ),
        Scenario(
            name="hw_lpm_none_highloss",
            seed=404,
            district_rows=4,
            district_cols=2,
            district_size=22,
            spacing=160.0,
            trunk_step=11,
            zones=4,
            options=[
                "UNITS\tLPM",
                "HEADLOSS\tH-W",
                "TRIALS\t90",
                "ACCURACY\t0.001",
                "DAMPLIMIT\t0",
                "UNBALANCED\tCONTINUE 15",
                "DEMAND MULTIPLIER\t0.85",
                "QUALITY\tNONE",
            ],
            times=[
                "DURATION\t12:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:30",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tNO", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t70", "GLOBAL PRICE\t0.20", "DEMAND CHARGE\t4.2"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t0.00", "GLOBAL WALL\t0.00"],
            quality=[";Node\tInitQual"],
            sources=[";Node\tType\tQuality\tPattern"],
            status_closed_stride=150,
            emitter_stride=180,
        ),
        Scenario(
            name="dw_cmh_chlorine_long",
            seed=505,
            district_rows=3,
            district_cols=3,
            district_size=24,
            spacing=145.0,
            trunk_step=10,
            zones=4,
            options=[
                "UNITS\tCMH",
                "HEADLOSS\tD-W",
                "SPECIFIC GRAVITY\t1.00",
                "VISCOSITY\t1.05",
                "TRIALS\t110",
                "ACCURACY\t0.0007",
                "UNBALANCED\tCONTINUE 25",
                "DEMAND MULTIPLIER\t1.05",
                "QUALITY\tChlorine mg/L",
                "TOLERANCE\t0.002",
            ],
            times=[
                "DURATION\t24:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:30",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tNO", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t80", "GLOBAL PRICE\t0.11", "DEMAND CHARGE\t1.5"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t-0.22", "GLOBAL WALL\t-0.75"],
            quality=[";Node\tInitQual", "R1\t0.80"],
            sources=[";Node\tType\tQuality\tPattern", "R1\tCONCEN\t0.8"],
            status_closed_stride=275,
            emitter_stride=300,
        ),
        Scenario(
            name="cm_mld_age_faststep",
            seed=606,
            district_rows=2,
            district_cols=4,
            district_size=24,
            spacing=110.0,
            trunk_step=7,
            zones=3,
            options=[
                "UNITS\tMLD",
                "HEADLOSS\tC-M",
                "TRIALS\t130",
                "ACCURACY\t0.001",
                "CHECKFREQ\t1",
                "MAXCHECK\t50",
                "UNBALANCED\tCONTINUE 30",
                "DEMAND MULTIPLIER\t1.35",
                "DEMAND MODEL\tPDA",
                "MINIMUM PRESSURE\t3",
                "REQUIRED PRESSURE\t28",
                "PRESSURE EXPONENT\t0.5",
                "QUALITY\tAGE",
            ],
            times=[
                "DURATION\t12:00",
                "HYDRAULIC TIMESTEP\t1:00",
                "QUALITY TIMESTEP\t0:30",
                "PATTERN TIMESTEP\t1:00",
                "REPORT TIMESTEP\t1:00",
            ],
            report=["STATUS\tYES", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
            energy=["GLOBAL EFFICIENCY\t76", "GLOBAL PRICE\t0.18", "DEMAND CHARGE\t3.0"],
            reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t0.00", "GLOBAL WALL\t0.00"],
            quality=[";Node\tInitQual"],
            sources=[";Node\tType\tQuality\tPattern"],
            status_closed_stride=130,
            emitter_stride=160,
        ),
    ]

    if include_huge:
        base.extend(
            [
                Scenario(
                    name="huge_hw_lps_chlorine_140x140",
                    seed=707,
                    district_rows=2,
                    district_cols=2,
                    district_size=34,
                    spacing=140.0,
                    trunk_step=12,
                    zones=5,
                    options=[
                        "UNITS\tLPS",
                        "HEADLOSS\tH-W",
                        "TRIALS\t120",
                        "ACCURACY\t0.001",
                        "UNBALANCED\tCONTINUE 40",
                        "DEMAND MULTIPLIER\t1.0",
                        "QUALITY\tChlorine mg/L",
                    ],
                    times=[
                        "DURATION\t24:00",
                        "HYDRAULIC TIMESTEP\t1:00",
                        "QUALITY TIMESTEP\t0:30",
                        "PATTERN TIMESTEP\t1:00",
                        "REPORT TIMESTEP\t1:00",
                    ],
                    report=["STATUS\tNO", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
                    energy=["GLOBAL EFFICIENCY\t79", "GLOBAL PRICE\t0.10", "DEMAND CHARGE\t2.5"],
                    reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t-0.2", "GLOBAL WALL\t-0.6"],
                    quality=[";Node\tInitQual", "R1\t1.0"],
                    sources=[";Node\tType\tQuality\tPattern", "R1\tCONCEN\t1.0"],
                    status_closed_stride=350,
                    emitter_stride=420,
                ),
                Scenario(
                    name="huge_dw_gpm_trace_160x120",
                    seed=808,
                    district_rows=2,
                    district_cols=2,
                    district_size=32,
                    spacing=135.0,
                    trunk_step=10,
                    zones=6,
                    options=[
                        "UNITS\tGPM",
                        "HEADLOSS\tD-W",
                        "TRIALS\t140",
                        "ACCURACY\t0.001",
                        "UNBALANCED\tCONTINUE 50",
                        "DEMAND MODEL\tPDA",
                        "MINIMUM PRESSURE\t5",
                        "REQUIRED PRESSURE\t32",
                        "PRESSURE EXPONENT\t0.5",
                        "QUALITY\tTRACE J1_1",
                    ],
                    times=[
                        "DURATION\t24:00",
                        "HYDRAULIC TIMESTEP\t1:00",
                        "QUALITY TIMESTEP\t0:30",
                        "PATTERN TIMESTEP\t1:00",
                        "REPORT TIMESTEP\t1:00",
                    ],
                    report=["STATUS\tYES", "SUMMARY\tYES", "NODES\tNONE", "LINKS\tNONE"],
                    energy=["GLOBAL EFFICIENCY\t82", "GLOBAL PRICE\t0.14", "DEMAND CHARGE\t4.0"],
                    reactions=["ORDER BULK\t1", "ORDER TANK\t1", "ORDER WALL\t1", "GLOBAL BULK\t-0.1", "GLOBAL WALL\t-0.4"],
                    quality=[";Node\tInitQual"],
                    sources=[";Node\tType\tQuality\tPattern"],
                    status_closed_stride=420,
                    emitter_stride=500,
                ),
            ]
        )

    return base


def run_base_generator(repo_root: Path, scenario: Scenario, base_out: Path) -> None:
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "generate_realistic_inp.py"),
        "--out",
        str(base_out),
        "--seed",
        str(scenario.seed),
        "--district-rows",
        str(scenario.district_rows),
        "--district-cols",
        str(scenario.district_cols),
        "--district-size",
        str(scenario.district_size),
        "--spacing",
        str(scenario.spacing),
        "--trunk-step",
        str(scenario.trunk_step),
        "--zones",
        str(scenario.zones),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = out_dir / ".tmp_base"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    scenario_list = scenarios(args.include_huge)
    manifest = []

    for s in scenario_list:
        base_file = tmp_dir / f"{s.name}.base.inp"
        out_file = out_dir / f"{s.name}.inp"

        run_base_generator(repo_root, s, base_file)
        stats = enrich(base_file, out_file, s)

        manifest.append(
            {
                "name": s.name,
                "file": str(out_file.relative_to(repo_root)),
                "seed": s.seed,
                "district_rows": s.district_rows,
                "district_cols": s.district_cols,
                "district_size": s.district_size,
                "spacing": s.spacing,
                "trunk_step": s.trunk_step,
                "zones": s.zones,
                "junctions": stats["junctions"],
                "pipes": stats["pipes"],
            }
        )

    manifest_path = (repo_root / args.manifest).resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Keep temporary bases for traceability of transformations.
    print(f"Wrote {len(manifest)} scenarios to {out_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
