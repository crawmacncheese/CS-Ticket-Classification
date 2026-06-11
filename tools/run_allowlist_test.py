"""Run allow-list test suites from a JSON spec or built-in profile.

Usage:
  python tools/run_allowlist_test.py --profile ci
  python tools/run_allowlist_test.py --spec .cursor/skills/batch-allowlist-test/specs/probe-commit.json
  python tools/run_allowlist_test.py --profile batch-ablation --output-dir reports/latest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

PROBE_TUPLE = "B2C,Service Task,Sales Leads,Rate or Renewal Inquiry,N/A"

PROFILES: dict[str, dict[str, Any]] = {
    "ci": {
        "description": "Layers 1-3 + batch (CI gate)",
        "pytest": [
            "tests/test_allowlist_session.py",
            "tests/test_allowlist_training.py",
            "tests/test_golden_classifier.py",
            "tests/test_batch_allowlist_analysis.py",
        ],
    },
    "layers-1-3": {
        "description": "Testing architecture layers 1-3 only",
        "pytest": [
            "tests/test_allowlist_session.py",
            "tests/test_allowlist_training.py",
            "tests/test_golden_classifier.py",
        ],
    },
    "batch": {
        "description": "Batch impact analysis pytest only",
        "pytest": ["tests/test_batch_allowlist_analysis.py"],
    },
    "probe": {
        "description": "Layer 2 probe mechanism (pytest + optional CLI)",
        "pytest": ["tests/test_golden_classifier.py::test_training_probe_resolves_tbc_when_tuple_missing"],
        "presteps": ["build_probe_upload"],
        "batch": {
            "ndjson": "tests/fixtures/training_tbc_probe.ndjson",
            "merge_tuples": [PROBE_TUPLE],
            "merge_tuples_from": "tests/fixtures/training_tbc_probe_upload.xlsx",
        },
        "assertions": {"min_net_tbc_improvement": 0},
    },
    "batch-commit": {
        "description": "Phase 1 commit simulation on probe fixture",
        "pytest": ["tests/test_batch_allowlist_analysis.py"],
        "presteps": ["build_probe_upload"],
        "batch": {
            "ndjson": "tests/fixtures/training_tbc_probe.ndjson",
            "merge_tuples": [PROBE_TUPLE],
            "merge_tuples_from": "tests/fixtures/training_tbc_probe_upload.xlsx",
            "with_rules": True,
        },
        "assertions": {"min_gap_fix_count": 0},
    },
    "batch-ablation": {
        "description": "Phase 2 ablation on probe fixture",
        "pytest": [
            "tests/test_batch_allowlist_analysis.py::test_ablation_probe_tuple_tbc_delta",
            "tests/test_batch_allowlist_analysis.py::test_ablation_negative_tuple_no_op",
        ],
        "presteps": ["build_probe_upload"],
        "batch": {
            "ndjson": "tests/fixtures/training_tbc_probe.ndjson",
            "merge_tuples": [PROBE_TUPLE],
            "merge_tuples_from": "tests/fixtures/training_tbc_probe_upload.xlsx",
            "with_rules": True,
            "ablation": True,
        },
    },
    "impact-analysis": {
        "description": "Full batch impact analysis — commit verdict + tuple risk (View A + B)",
        "presteps": ["build_probe_upload"],
        "batch": {
            "ndjson": "tests/fixtures/training_tbc_probe.ndjson",
            "merge_tuples": [PROBE_TUPLE],
            "merge_tuples_from": "tests/fixtures/training_tbc_probe_upload.xlsx",
            "with_rules": True,
            "ablation": True,
        },
    },
}


def _run(cmd: list[str], *, cwd: Path = ROOT) -> int:
    print(f"+ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _resolve(path: str | None) -> Path | None:
    if path is None:
        return None
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "profile" in data and data["profile"] in PROFILES:
        merged = dict(PROFILES[data["profile"]])
        for key, val in data.items():
            if key == "profile":
                continue
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **val}
            else:
                merged[key] = val
        return merged
    return data


def _build_probe_upload() -> int:
    out = ROOT / "tests" / "fixtures" / "training_tbc_probe_upload.xlsx"
    return _run([str(PYTHON), "tools/build_training_test_upload.py", "--out", str(out)])


def _run_presteps(steps: list[str]) -> int:
    for step in steps:
        if step == "build_probe_upload":
            code = _build_probe_upload()
            if code != 0:
                return code
        else:
            print(f"error: unknown prestep {step!r}", file=sys.stderr)
            return 1
    return 0


def _run_pytest(paths: list[str], *, extra: list[str] | None = None) -> int:
    cmd = [str(PYTHON), "-m", "pytest", *paths, "-q"]
    if extra:
        cmd.extend(extra)
    return _run(cmd)


def _run_batch(batch: dict[str, Any], output_dir: Path) -> int:
    cmd = [str(PYTHON), "tools/batch_allowlist_compare.py", "--output-dir", str(output_dir)]
    ndjson = _resolve(batch.get("ndjson"))
    ndjson_dir = _resolve(batch.get("ndjson_dir"))
    if ndjson is not None:
        cmd.extend(["--ndjson", str(ndjson)])
    elif ndjson_dir is not None:
        cmd.extend(["--ndjson-dir", str(ndjson_dir)])
    else:
        print("error: batch spec requires ndjson or ndjson_dir", file=sys.stderr)
        return 1

    merge_from = _resolve(batch.get("merge_tuples_from"))
    if merge_from is not None:
        cmd.extend(["--merge-tuples-from", str(merge_from)])
    for tup in batch.get("merge_tuples") or []:
        cmd.extend(["--merge-tuples", tup])
    sel_json = _resolve(batch.get("selected_tuples_json"))
    if sel_json is not None:
        cmd.extend(["--selected-tuples-json", str(sel_json)])
    if batch.get("with_rules"):
        cmd.append("--with-rules")
    if batch.get("ablation"):
        cmd.append("--ablation")
    if batch.get("compute_no_op"):
        cmd.append("--compute-no-op")
    if batch.get("limit") is not None:
        cmd.extend(["--limit", str(batch["limit"])])
    if batch.get("ablation_limit") is not None:
        cmd.extend(["--ablation-limit", str(batch["ablation_limit"])])
    tax = _resolve(batch.get("taxonomy"))
    wb = _resolve(batch.get("workbook"))
    if tax is not None:
        cmd.extend(["--taxonomy", str(tax)])
    if wb is not None:
        cmd.extend(["--workbook", str(wb)])
    return _run(cmd)


def _check_assertions(output_dir: Path, assertions: dict[str, Any]) -> int:
    verdict_path = output_dir / "commit_verdict.json"
    if not verdict_path.is_file():
        print(f"error: missing {verdict_path}", file=sys.stderr)
        return 1

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if "verdict_band" in assertions and verdict.get("verdict_band") != assertions["verdict_band"]:
        errors.append(
            f"verdict_band: expected {assertions['verdict_band']!r}, got {verdict.get('verdict_band')!r}"
        )

    net = verdict.get("net_tbc_improvement")
    if "min_net_tbc_improvement" in assertions and (net is None or net < assertions["min_net_tbc_improvement"]):
        errors.append(
            f"net_tbc_improvement: expected >= {assertions['min_net_tbc_improvement']}, got {net}"
        )

    gap_fix = (verdict.get("outcome_counts") or {}).get("gap_fix", 0)
    if "min_gap_fix_count" in assertions and gap_fix < assertions["min_gap_fix_count"]:
        errors.append(f"gap_fix_count: expected >= {assertions['min_gap_fix_count']}, got {gap_fix}")

    for outcome, expected in (assertions.get("outcome_counts") or {}).items():
        actual = (verdict.get("outcome_counts") or {}).get(outcome, 0)
        if actual != expected:
            errors.append(f"outcome_counts[{outcome}]: expected {expected}, got {actual}")

    if errors:
        print("ASSERTION FAILURES:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("Assertions passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-profiles", action="store_true", help="Print profiles and exit")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--profile", choices=sorted(PROFILES))
    group.add_argument("--spec", type=Path, help="JSON spec file (optional profile + overrides)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Batch report dir (default: reports/run-<timestamp> when batch runs)",
    )
    parser.add_argument("--pytest-only", action="store_true", help="Skip batch CLI even if spec includes batch")
    parser.add_argument("--batch-only", action="store_true", help="Skip pytest even if spec includes pytest")
    args = parser.parse_args()

    if args.list_profiles:
        for name, cfg in sorted(PROFILES.items()):
            print(f"{name}: {cfg.get('description', '')}")
        return 0

    if not args.profile and not args.spec:
        parser.error("one of --profile or --spec is required (or use --list-profiles)")

    if args.spec is not None:
        spec_path = args.spec if args.spec.is_absolute() else ROOT / args.spec
        spec = _load_spec(spec_path)
    else:
        spec = dict(PROFILES[args.profile or ""])

    print(f"=== allow-list test run: {spec.get('description') or args.profile or args.spec} ===")

    if spec.get("presteps") and not args.batch_only:
        code = _run_presteps(spec["presteps"])
        if code != 0:
            return code

    if spec.get("pytest") and not args.batch_only:
        code = _run_pytest(spec["pytest"])
        if code != 0:
            return code

    batch = spec.get("batch")
    if batch and not args.pytest_only:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_dir = args.output_dir or _resolve(batch.get("output_dir")) or (ROOT / "reports" / f"run-{ts}")
        output_dir.mkdir(parents=True, exist_ok=True)
        code = _run_batch(batch, output_dir)
        if code != 0:
            return code
        assertions = spec.get("assertions")
        if assertions:
            code = _check_assertions(output_dir, assertions)
            if code != 0:
                return code
        print(f"Reports: {output_dir}")

    print("=== PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
