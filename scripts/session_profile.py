"""CLI: build Christine session profile JSON from a portal run or local classified rows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from cs_tickets.session_profile import SessionProfile, SweepSummary, compute_no_op  # noqa: E402


def _require_ok(r: requests.Response) -> None:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.reason}: {r.text[:2000]}")


def profile_via_http(*, base_url: str, run_id: str, focus_nl: str) -> SessionProfile:
    """Profile by calling portal parse_focus + sweeps endpoints (no LLM on profile path)."""
    base = base_url.rstrip("/")
    parse_resp = requests.post(
        f"{base}/run/{run_id}/category_audit_parse_focus",
        json={"text": focus_nl},
        timeout=30,
    )
    _require_ok(parse_resp)
    parsed = parse_resp.json()
    audit_filter = parsed.get("audit_filter") or {}
    params: dict[str, str] = {}
    if audit_filter.get("tier1"):
        params["tier1"] = str(audit_filter["tier1"])
    cats = audit_filter.get("categories") or []
    if cats:
        params["categories"] = ",".join(str(c) for c in cats)
    if audit_filter.get("q"):
        params["q"] = str(audit_filter["q"])

    sweeps_resp = requests.get(
        f"{base}/run/{run_id}/category_audit/sweeps",
        params=params,
        timeout=30,
    )
    _require_ok(sweeps_resp)
    sweeps_payload = sweeps_resp.json()
    stats = sweeps_payload.get("stats") or {}
    slice_count = int(stats.get("total_in_slice") or 0)
    sweep_summaries = tuple(
        {
            "sweep_id": str(s.get("id") or ""),
            "match_count": int(s.get("match_count") or 0),
            "sample_ids": list(s.get("matched_ids") or [])[:5],
        }
        for s in sweeps_payload.get("sweeps") or []
    )
    summaries = tuple(
        SweepSummary(
            sweep_id=s["sweep_id"],
            match_count=s["match_count"],
            sample_ids=tuple(s["sample_ids"]),
        )
        for s in sweep_summaries
    )
    no_op = compute_no_op(slice_count=slice_count, sweep_summaries=summaries)
    parse_ok = bool(parsed.get("ok"))
    parse_errors = tuple(str(e) for e in (parsed.get("errors") or []))
    return SessionProfile(
        focus_nl=focus_nl.strip(),
        audit_filter=audit_filter,
        slice_count=slice_count,
        tbc_count=0,
        sweep_summaries=summaries,
        no_op=no_op,
        parse_ok=parse_ok,
        parse_source=str(parsed.get("source") or "http"),
        parse_errors=parse_errors,
    )


def _print_profile(profile: SessionProfile, *, as_json: bool) -> None:
    payload: dict[str, Any] = profile.as_dict()
    payload["blockers"] = list(profile.blockers)
    payload["clarify_message"] = profile.clarify_message
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"Focus: {profile.focus_nl}")
    print(f"Slice: {profile.slice_count} | TBC in run: {profile.tbc_count}")
    print(f"no_op: {profile.no_op} | blockers: {list(profile.blockers)}")
    for sweep in profile.sweep_summaries:
        if sweep.match_count:
            print(
                f"  sweep {sweep.sweep_id}: {sweep.match_count} "
                f"(samples: {', '.join(sweep.sample_ids) or '—'})"
            )
    if profile.clarify_message:
        print(f"Clarify: {profile.clarify_message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Christine session profile JSON.")
    parser.add_argument("--focus", required=True, help="Natural-language review focus")
    parser.add_argument("--run-id", help="Existing portal run_id (HTTP mode)")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:8777"),
        help="Portal base URL when using --run-id",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full profile JSON (includes blockers + clarify_message)",
    )
    args = parser.parse_args(argv)

    if not args.run_id:
        print("ERROR: --run-id is required (local row mode is for tests only).", file=sys.stderr)
        return 2

    try:
        profile = profile_via_http(
            base_url=args.base_url.strip(),
            run_id=args.run_id.strip(),
            focus_nl=args.focus,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_profile(profile, as_json=args.json)
    return 3 if profile.no_op else 0


if __name__ == "__main__":
    raise SystemExit(main())
