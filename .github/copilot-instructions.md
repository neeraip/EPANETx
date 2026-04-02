# EPANETx Copilot Instructions

## Mission
EPANETx is a performance-focused replacement fork of EPANET.

All development work must preserve EPANET behavior while improving runtime and/or resource efficiency.

## Canonical Truth and Acceptance Criteria

### Source of Truth
- EPANET is the canonical behavior reference implementation.
- Canonical upstream reference tag for this fork lineage: https://github.com/OpenWaterAnalytics/EPANET/tree/v2.3.5
- EPANET may be available as a sibling folder (for example, `../EPANET`), but this is not required.
- If EPANET is not present in the local development environment, use a configured EPANET executable and/or reference artifact set from a known-good EPANET build.
- For the same input `.inp`, if EPANETx and EPANET produce different `.out` results, EPANETx is incorrect.

### Workspace Portability
- Do not assume EPANET and EPANETx are both open in the same editor, IDE, or multi-root workspace.
- Treat EPANET reference locations (repo path, binaries, and test input corpus) as configurable environment inputs.
- When paths are unknown, request or discover them before running parity and performance checks.

### Reference Bootstrap (No Local EPANET Checkout)
- If EPANET source is not available locally, use `scripts/build_epanet_binary.sh` to bootstrap a known-good reference binary from the upstream `v2.3.5` tag.
- Default output is `bin/runepanet-epanet-v2.3.5` inside EPANETx.
- Example:
	- `scripts/build_epanet_binary.sh`
	- `scripts/build_epanet_binary.sh --output-name runepanet-epanet-ref`
- After bootstrap, use the produced binary as the EPANET reference executable for parity checks.

### Local Binary Setup (EPANETx)
- Build/install the local EPANETx binary with `scripts/build_epanetx_binary.sh`.
- Default output is `bin/epanetx`.

### Validation Scripts (Recommended)
- Parity script: `scripts/check_epanet_parity.sh`
	- Default behavior compares `bin/runepanet-epanet-v2.3.5` vs `bin/epanetx` on `example-networks/Net1.inp`, `Net2.inp`, and `Net3.inp`.
	- Example: `scripts/check_epanet_parity.sh`
	- Example: `scripts/check_epanet_parity.sh --manifest manifest.txt`
- Benchmark script: `scripts/benchmark_epanet_vs_epanetx.sh`
	- Default behavior benchmarks `bin/runepanet-epanet-v2.3.5` vs `bin/epanetx` over the same representative networks with repeated runs.
	- Example: `scripts/benchmark_epanet_vs_epanetx.sh --runs 5`
	- Example: `scripts/benchmark_epanet_vs_epanetx.sh --runs 5 --manifest manifest.txt`
- Combined gate script: `scripts/run_validation_gates.sh`
	- Runs parity first, then benchmark threshold checks.
	- Example: `scripts/run_validation_gates.sh --runs 5 --max-regression-pct 0`
	- Example: `scripts/run_validation_gates.sh --runs 5 --max-regression-pct 3 --manifest manifest.txt`

### Correctness Priority (Non-Negotiable)
1. Absolute `.out` parity with EPANET is mandatory.
2. `.rpt` parity is strongly preferred and should be maintained whenever practical.
3. If `.rpt` and `.out` priorities conflict during iteration, preserve `.out` parity first, then repair `.rpt` formatting/ordering differences.

### Performance Priority (Also Required)
- EPANETx should benchmark faster (or use fewer resources) than EPANET for representative workloads.
- Any optimization that causes no measurable benefit or causes regression should be reverted.
- Correctness wins over speed: never keep a faster change that breaks `.out` parity.

## Development Rules for Copilot

### Behavior Preservation
- Keep public toolkit behavior, APIs, and file formats compatible with EPANET unless explicitly requested otherwise.
- Avoid algorithmic rewrites that alter numeric behavior unless parity validation proves equivalence.
- Treat floating-point operation ordering as sensitive; tiny numerical drifts can break parity.

### Change Scope Discipline
- Prefer small, focused changes to hot paths.
- Do not mix refactors with optimizations in the same patch unless required.
- Avoid unrelated formatting churn in performance-sensitive C files.
- Preserve existing comments, conventions, and coding style unless a style issue blocks maintainability.

### Validation Workflow (Required)
For any non-trivial change in hydraulic, matrix, solver, status, or output code:
1. Build EPANETx cleanly.
2. Run local tests relevant to modified code.
3. Run parity checks against the configured EPANET reference using representative networks (prefer `scripts/check_epanet_parity.sh`).
4. Run performance benchmarks on representative networks (prefer `scripts/benchmark_epanet_vs_epanetx.sh`).
5. Keep the change only if parity passes and performance is non-regressive.

If either parity or performance checks fail, diagnose and fix immediately, or revert the change.

## Parity Verification Guidance
- Prefer direct EPANET vs EPANETx `.out` comparisons on the same `.inp` inputs, regardless of where EPANET is installed.
- Use multiple network sizes (small + medium + large) to avoid overfitting.
- When parity fails, bisect recent edits quickly and isolate the smallest culprit.
- Assume EPANETx is wrong until proven otherwise.

## Performance Verification Guidance
- Benchmark with repeated runs and report averages (and spread if possible).
- Use stable benchmark conditions (same machine, similar background load, same build mode).
- Focus optimization work on measured hotspots, not intuition.
- Report before/after timings and percentage deltas for each accepted optimization.

## Decision Policy for Changes
A change is acceptable only when all are true:
- `.out` parity with EPANET is preserved.
- Existing tests pass.
- Performance is improved or at least not regressed on target workloads.
- The implementation remains maintainable and readable.

A change must be rejected/reverted when any of the following occur:
- `.out` mismatch with EPANET.
- Net performance regression without compensating benefit.
- Increased complexity without measured value.

## Expected Copilot Output Style During This Project
- Always state parity impact explicitly when proposing or landing changes.
- Always state performance impact with measured numbers when available.
- Prefer concise diffs and clear rollback paths.
- If uncertain, choose safer behavior-preserving implementations first.

## Practical Guardrails
- Do not claim success without showing parity and benchmark evidence.
- Do not treat generated build artifacts as meaningful source changes.
- Do not keep speculative micro-optimizations that cannot be validated.
- If a test fails after an optimization, assume regression until disproven.

## Summary Principle
EPANETx exists to be a faster EPANET, not a different EPANET.

Correctness is defined by EPANET `.out` parity.
Performance improvements are only real when measured and reproducible.
