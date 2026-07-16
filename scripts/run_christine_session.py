"""Execute a Christine Session Metadata Package against the portal (Phase B runner)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from cs_tickets.session_md import (  # noqa: E402
    append_execution_log,
    append_runner_log,
    create_session_md,
    suggested_session_filename,
    summarize_for_results_section,
    DEFAULT_SESSIONS_DIR,
)
from cs_tickets.session_metadata import (  # noqa: E402
    DEFAULT_ROSETTA_FOCUS,
    SessionMetadataError,
    SessionMetadataPackage,
    build_rosetta_package,
    parse_package,
)
from cs_tickets.session_profile import (  # noqa: E402
    SessionProfile,
    SweepSummary,
    compute_no_op,
)


@dataclass
class RunnerState:
    base_url: str
    run_id: str | None
    last_rule: dict[str, Any] | None = None
    last_preview: dict[str, Any] | None = None
    last_compile: dict[str, Any] | None = None
    reclassify_soft_fail: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url.rstrip("/") + path


@dataclass(frozen=True)
class RunnerResult:
    ok: bool
    stopped_reason: str
    state: RunnerState
    steps_run: int
    exit_code: int


def _require_ok(r: requests.Response) -> None:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.reason}: {r.text[:2000]}")


def _print_json(title: str, payload: Any, *, limit: int = 4000) -> None:
    s = json.dumps(payload, indent=2, ensure_ascii=False)
    if len(s) > limit:
        s = s[: limit - 20] + "\n... (truncated) ..."
    print(f"\n== {title} ==\n{s}")


def _extract_run_id_from_html(html: str) -> str:
    m = re.search(r"/run/([0-9a-f\\-]{36})/results", html)
    if not m:
        m = re.search(r"/run/([0-9a-f\\-]{36})/category_audit", html)
    if not m:
        raise RuntimeError("Could not extract run_id from /run HTML response.")
    return m.group(1)


def upload_export(base_url: str, export_path: Path) -> str:
    r = requests.get(base_url.rstrip("/") + "/health", timeout=15)
    _require_ok(r)
    if (r.text or "").strip().lower() != "ok":
        raise RuntimeError(f"/health did not return ok: {r.text!r}")

    files = {"export": (export_path.name, export_path.read_bytes(), "application/x-ndjson")}
    resp = requests.post(
        base_url.rstrip("/") + "/run",
        files=files,
        data={"bad_satisfaction_only": "false"},
        allow_redirects=True,
        timeout=60,
    )
    _require_ok(resp)
    return _extract_run_id_from_html(resp.text)


def profile_via_http(*, base_url: str, run_id: str, focus_nl: str) -> SessionProfile:
    """Profile a portal run via parse_focus + sweeps (no LLM required for profile itself)."""
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
    summaries = tuple(
        SweepSummary(
            sweep_id=str(s.get("id") or ""),
            match_count=int(s.get("match_count") or 0),
            sample_ids=tuple(list(s.get("matched_ids") or [])[:5]),
        )
        for s in sweeps_payload.get("sweeps") or []
    )
    no_op = compute_no_op(slice_count=slice_count, sweep_summaries=summaries)
    return SessionProfile(
        focus_nl=focus_nl.strip(),
        audit_filter=audit_filter,
        slice_count=slice_count,
        tbc_count=0,
        sweep_summaries=summaries,
        no_op=no_op,
        parse_ok=bool(parsed.get("ok")),
        parse_source=str(parsed.get("source") or "http"),
        parse_errors=tuple(str(e) for e in (parsed.get("errors") or [])),
    )


def execute_package(
    package: SessionMetadataPackage,
    *,
    base_url: str,
    dry_run: bool = False,
    stop_before_confirm: bool | None = None,
) -> RunnerResult:
    """
    Walk the orchestration queue and call portal endpoints.

    Returns early (exit 3) when the package is not actionable (terminal clarify).
    """
    ok_gate, gate_msg = package.runner_gate()
    state = RunnerState(base_url=base_url, run_id=package.run_id)
    if not ok_gate:
        print(f"CLARIFY / STOP: {gate_msg}", file=sys.stderr)
        return RunnerResult(
            ok=False,
            stopped_reason=gate_msg,
            state=state,
            steps_run=0,
            exit_code=3,
        )

    if stop_before_confirm is None:
        stop_before_confirm = package.user_persona == "ANALYST"

    if dry_run:
        _print_json("Dry-run queue", package.as_dict())
        return RunnerResult(
            ok=True,
            stopped_reason="dry_run",
            state=state,
            steps_run=0,
            exit_code=0,
        )

    steps = 0
    for item in package.orchestration_queue:
        action = item.action
        params = dict(item.params)

        if action == "QUEUE_FOR_CONFIRMATION":
            entry = {"action": action, "status": "paused", "params": params}
            state.log.append(entry)
            _print_json(
                "QUEUE_FOR_CONFIRMATION (human gate)",
                {
                    "preview": state.last_preview,
                    "rule": state.last_rule,
                    "auto_confirm": params.get("auto_confirm", False),
                },
            )
            steps += 1
            if stop_before_confirm:
                return RunnerResult(
                    ok=True,
                    stopped_reason="queued_for_confirmation",
                    state=state,
                    steps_run=steps,
                    exit_code=0,
                )
            continue

        if action == "CONFIRM_RULE" and stop_before_confirm:
            print("STOP: analyst mode - skipping CONFIRM_RULE")
            return RunnerResult(
                ok=True,
                stopped_reason="analyst_skip_confirm",
                state=state,
                steps_run=steps,
                exit_code=0,
            )

        try:
            _dispatch(state, action, params)
        except RuntimeError as exc:
            state.log.append({"action": action, "status": "error", "error": str(exc)})
            print(f"ERROR on {action}: {exc}", file=sys.stderr)
            return RunnerResult(
                ok=False,
                stopped_reason=f"{action}_failed",
                state=state,
                steps_run=steps,
                exit_code=1,
            )
        steps += 1
        state.log.append({"action": action, "status": "ok"})

    return RunnerResult(
        ok=True,
        stopped_reason="queue_complete",
        state=state,
        steps_run=steps,
        exit_code=0,
    )


def _dispatch(state: RunnerState, action: str, params: dict[str, Any]) -> None:
    if action == "ATTACH_RUN":
        path = Path(str(params.get("export_path") or ""))
        if not path.is_file():
            raise RuntimeError(f"ATTACH_RUN requires export_path file: {path}")
        state.run_id = upload_export(state.base_url, path)
        print(f"ATTACH_RUN -> run_id={state.run_id}")
        return

    if action == "PARSE_FOCUS":
        if not state.run_id:
            raise RuntimeError("PARSE_FOCUS requires run_id")
        text = str(params.get("text") or "").strip()
        if not text:
            raise RuntimeError("PARSE_FOCUS requires params.text")
        mode = str(params.get("mode") or "category_audit")
        path = (
            f"/run/{state.run_id}/tbc_parse_focus"
            if mode == "tbc"
            else f"/run/{state.run_id}/category_audit_parse_focus"
        )
        r = requests.post(state.url(path), json={"text": text}, timeout=30)
        _require_ok(r)
        _print_json("PARSE_FOCUS", r.json())
        return

    if action == "EXECUTE_SWEEP":
        if not state.run_id:
            raise RuntimeError("EXECUTE_SWEEP requires run_id")
        sweep_id = str(params.get("sweep_id") or "").strip()
        profile = params.get("filter") or {}
        qparams: dict[str, str] = {}
        for key in ("tier1", "categories", "q", "tier4", "include_tbc"):
            val = params.get(key, profile.get(key) if isinstance(profile, dict) else None)
            if val is None or val == "" or val is False:
                continue
            if key == "categories" and isinstance(val, list):
                qparams[key] = ",".join(str(c) for c in val)
            else:
                qparams[key] = str(val)
        if "tier1" not in qparams:
            qparams["tier1"] = "B2C"
        r = requests.get(
            state.url(f"/run/{state.run_id}/category_audit/sweeps"),
            params=qparams,
            timeout=30,
        )
        _require_ok(r)
        payload = r.json()
        if sweep_id:
            matches = [
                s for s in (payload.get("sweeps") or []) if str(s.get("id") or "") == sweep_id
            ]
            _print_json(
                f"EXECUTE_SWEEP {sweep_id}",
                {
                    "filter": payload.get("filter"),
                    "stats": payload.get("stats"),
                    "sweep": matches[0] if matches else None,
                    "match_found": bool(matches),
                },
            )
        else:
            _print_json("EXECUTE_SWEEP (all)", payload)
        return

    if action == "COMPILE_RULE_DRAFT":
        prefill = str(params.get("rule_prefill") or params.get("message") or "").strip()
        if not prefill:
            raise RuntimeError("COMPILE_RULE_DRAFT requires params.rule_prefill")
        r = requests.post(
            state.url("/rules/compile"),
            json={"messages": [{"role": "user", "content": prefill}]},
            timeout=60,
        )
        _require_ok(r)
        compiled = r.json()
        state.last_compile = compiled
        rule = compiled.get("rule")
        if isinstance(rule, dict):
            state.last_rule = rule
        _print_json("COMPILE_RULE_DRAFT", compiled)
        return

    if action == "PREVIEW_RULE":
        rule = params.get("rule") if isinstance(params.get("rule"), dict) else state.last_rule
        if not isinstance(rule, dict):
            raise RuntimeError("PREVIEW_RULE requires a compiled rule (run COMPILE first)")
        if not state.run_id:
            raise RuntimeError("PREVIEW_RULE requires run_id")
        r = requests.post(
            state.url("/rules/preview"),
            json={"run_id": state.run_id, "rule": rule},
            timeout=60,
        )
        _require_ok(r)
        state.last_preview = r.json()
        _print_json("PREVIEW_RULE", state.last_preview)
        return

    if action == "CONFIRM_RULE":
        rule = params.get("rule") if isinstance(params.get("rule"), dict) else state.last_rule
        if not isinstance(rule, dict):
            raise RuntimeError("CONFIRM_RULE requires a rule object")
        # D.1 — require living run + fresh preview when run_id was part of this session
        if state.run_id:
            probe = requests.get(state.url(f"/run/{state.run_id}/results"), timeout=15)
            if probe.status_code == 404:
                raise RuntimeError(
                    "PREVIEW_STALE: run_id expired — re-attach the same upload and re-preview "
                    "before Confirm (do not switch datasets)."
                )
            if state.last_preview is None:
                raise RuntimeError(
                    "PREVIEW_STALE: no successful PREVIEW_RULE in this session — preview first."
                )
        r = requests.post(state.url("/rules/confirm"), json={"rule": rule}, timeout=60)
        _require_ok(r)
        payload = r.json()
        state.last_compile = {**(state.last_compile or {}), "confirm": payload}
        _print_json("CONFIRM_RULE", payload)
        return

    if action == "RECLASSIFY_RUN":
        if not state.run_id:
            print("WARN: RECLASSIFY_RUN skipped - no run_id")
            return
        body = {k: v for k, v in params.items() if k != "action"}
        r = requests.post(
            state.url(f"/run/{state.run_id}/reclassify"),
            json=body,
            timeout=60,
        )
        if r.status_code == 404:
            state.reclassify_soft_fail = True
            print("WARN: RECLASSIFY_RUN soft-fail - run expired (live promote still ok)")
            return
        _require_ok(r)
        _print_json("RECLASSIFY_RUN", r.json())
        return

    raise RuntimeError(f"Unsupported action: {action}")


def _load_package_file(path: Path) -> SessionMetadataPackage:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SessionMetadataError("Package file must contain a JSON object")
    return parse_package(raw)


def _synthetic_rosetta_profile(focus_nl: str) -> SessionProfile:
    return SessionProfile(
        focus_nl=focus_nl,
        audit_filter={
            "q": "",
            "tier1": "B2C",
            "categories": [],
            "tier4": "",
            "include_tbc": False,
            "active": True,
        },
        slice_count=7,
        tbc_count=0,
        sweep_summaries=(SweepSummary("rosetta_system_email", 1, ("170002",)),),
        no_op=False,
        parse_ok=True,
        parse_source="deterministic",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a Christine Session Metadata Package against the portal."
    )
    parser.add_argument("--package", type=Path, help="Path to Session Metadata Package JSON")
    parser.add_argument(
        "--demo",
        choices=("rosetta",),
        help="Build+run a built-in demo package (uploads fixture unless --run-id set)",
    )
    parser.add_argument("--run-id", help="Existing portal run_id")
    parser.add_argument(
        "--focus",
        default=DEFAULT_ROSETTA_FOCUS,
        help="Focus text when building a package from profile",
    )
    parser.add_argument(
        "--persona",
        choices=("ANALYST", "LEAD"),
        default="ANALYST",
        help="ANALYST stops before Confirm",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=_REPO_ROOT / "tests" / "fixtures" / "christine_category_audit_fixture.ndjson",
        help="NDJSON export for demo upload",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:8777"),
        help="Portal base URL",
    )
    parser.add_argument(
        "--write-package",
        type=Path,
        help="Write the built package JSON to this path before running",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate package and print queue; do not call portal APIs",
    )
    parser.add_argument(
        "--session-md",
        type=Path,
        help="Append runner execution log to this session requirements MD",
    )
    parser.add_argument(
        "--init-session-md",
        action="store_true",
        help="Create session MD from template (uses --session-md path or docs/sessions/YYYY-MM-DD-*.md)",
    )
    args = parser.parse_args(argv)
    base_url = args.base_url.strip()

    try:
        if args.package:
            package = _load_package_file(args.package)
            if args.run_id and not package.run_id:
                package = parse_package({**package.as_dict(), "run_id": args.run_id})
        elif args.demo == "rosetta":
            run_id = args.run_id
            if args.dry_run and not run_id:
                profile = _synthetic_rosetta_profile(args.focus)
            else:
                if not run_id:
                    if not args.export.is_file():
                        print(f"ERROR: export not found: {args.export}", file=sys.stderr)
                        return 2
                    print(f"Uploading {args.export} -> {base_url}")
                    run_id = upload_export(base_url, args.export)
                    print(f"run_id={run_id}")
                profile = profile_via_http(
                    base_url=base_url,
                    run_id=run_id,
                    focus_nl=args.focus,
                )
            package = build_rosetta_package(
                profile,
                run_id=run_id,
                user_persona=args.persona,
            )
        else:
            print("ERROR: provide --package or --demo rosetta", file=sys.stderr)
            return 2
    except (SessionMetadataError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    session_md_path: Path | None = args.session_md
    if args.init_session_md:
        if session_md_path is None:
            session_md_path = DEFAULT_SESSIONS_DIR / suggested_session_filename(batch="christine")
        create_session_md(
            session_md_path,
            batch_name="Christine session",
            run_id=package.run_id,
            portal_base=base_url,
            export_file=str(args.export) if args.demo else "",
            persona=package.user_persona.lower(),
            loop="category_audit" if package.run_mode == "CATEGORY_AUDIT" else "tbc_queue",
            taxonomy_version=package.taxonomy_version,
            focus_nl=str((package.profile or {}).get("focus_nl") or args.focus),
            goals="Christine orchestration session (auto-created by runner).",
        )
        print(f"Init session MD -> {session_md_path}")

    if args.write_package:
        args.write_package.parent.mkdir(parents=True, exist_ok=True)
        args.write_package.write_text(
            json.dumps(package.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote package -> {args.write_package}")

    result = execute_package(package, base_url=base_url, dry_run=args.dry_run)

    if session_md_path is not None and not args.dry_run:
        if not session_md_path.is_file():
            create_session_md(
                session_md_path,
                batch_name="Christine session",
                run_id=result.state.run_id or package.run_id,
                portal_base=base_url,
                persona=package.user_persona.lower(),
                taxonomy_version=package.taxonomy_version,
                focus_nl=str((package.profile or {}).get("focus_nl") or ""),
            )
        pkg_dict = package.as_dict()
        rule_id = None
        if isinstance(result.state.last_rule, dict):
            rule_id = result.state.last_rule.get("id")
            pkg_dict["_last_rule_id"] = rule_id
        append_runner_log(
            session_md_path,
            package=pkg_dict,
            log_entries=list(result.state.log),
            stopped_reason=result.stopped_reason,
            run_id=result.state.run_id or package.run_id,
        )
        matched = None
        if isinstance(result.state.last_preview, dict):
            rows = result.state.last_preview.get("results") or []
            if isinstance(rows, list):
                matched = sum(1 for r in rows if isinstance(r, dict) and r.get("matched"))
            summary = result.state.last_preview.get("summary")
            if isinstance(summary, dict) and summary.get("headline"):
                append_execution_log(
                    session_md_path,
                    action="PREVIEW_SUMMARY",
                    result=str(summary.get("headline")),
                )
        confirm_payload = None
        if isinstance(result.state.last_compile, dict):
            confirm_payload = result.state.last_compile.get("confirm")
        if isinstance(confirm_payload, dict) and confirm_payload.get("config_version_after") is not None:
            append_execution_log(
                session_md_path,
                action="CONFIG_VERSION",
                result=f"config_version_after = {confirm_payload.get('config_version_after')}",
            )
        if result.state.reclassify_soft_fail:
            append_execution_log(
                session_md_path,
                action="RECLASSIFY_RUN",
                result="soft-fail: run_id expired (live promote still ok)",
            )
        summarize_for_results_section(
            session_md_path,
            rule_id=str(rule_id) if rule_id else None,
            preview_matched=matched,
            note=f"stop={result.stopped_reason}",
        )
        print(f"Updated session MD -> {session_md_path}")

    print(f"\nDone: {result.stopped_reason} (steps={result.steps_run}, exit={result.exit_code})")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
