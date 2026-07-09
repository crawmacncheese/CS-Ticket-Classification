from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class RunSession:
    base_url: str
    run_id: str

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url.rstrip("/") + path


def _print_json(title: str, payload: Any, *, limit: int = 4000) -> None:
    s = json.dumps(payload, indent=2, ensure_ascii=False)
    if len(s) > limit:
        s = s[: limit - 20] + "\n... (truncated) ..."
    print(f"\n== {title} ==\n{s}")


def _require_ok(r: requests.Response) -> None:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.reason}: {r.text[:2000]}")


def _extract_run_id_from_html(html: str) -> str:
    m = re.search(r"/run/([0-9a-f\\-]{36})/results", html)
    if not m:
        m = re.search(r"/run/([0-9a-f\\-]{36})/category_audit", html)
    if not m:
        raise RuntimeError("Could not extract run_id from /run HTML response.")
    return m.group(1)


def upload_export(base_url: str, export_path: Path) -> RunSession:
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
    run_id = _extract_run_id_from_html(resp.text)
    return RunSession(base_url=base_url, run_id=run_id)


def category_audit_parse_focus(session: RunSession, text: str) -> dict[str, Any]:
    r = requests.post(
        session.url(f"/run/{session.run_id}/category_audit_parse_focus"),
        json={"text": text},
        timeout=30,
    )
    _require_ok(r)
    return r.json()


def category_audit_sweeps(session: RunSession, *, tier1: str = "B2C", categories: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {"tier1": tier1}
    if categories:
        params["categories"] = categories
    r = requests.get(session.url(f"/run/{session.run_id}/category_audit/sweeps"), params=params, timeout=30)
    _require_ok(r)
    return r.json()


def compile_rule(session: RunSession, message: str) -> dict[str, Any]:
    body = {"messages": [{"role": "user", "content": message}]}
    r = requests.post(session.url("/rules/compile"), json=body, timeout=60)
    _require_ok(r)
    return r.json()


def preview_rule(session: RunSession, rule_obj: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        session.url("/rules/preview"),
        json={"run_id": session.run_id, "rule": rule_obj},
        timeout=60,
    )
    _require_ok(r)
    return r.json()


def main() -> int:
    base_url = os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:8777").strip()
    export_path = Path(
        os.environ.get(
            "EXPORT_PATH",
            str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "christine_category_audit_fixture.ndjson"),
        )
    )
    if not export_path.is_file():
        print(f"ERROR: export fixture not found at {export_path}", file=sys.stderr)
        return 2

    print(f"Portal: {base_url}")
    print(f"Export: {export_path}")

    session = upload_export(base_url, export_path)
    print(f"\nCreated run_id: {session.run_id}")
    print(f"Category audit page: {session.url(f'/run/{session.run_id}/category_audit')}")

    # Christine Step 1 — Pick segment + categories (numbered list)
    focus = "review B2C categories: 1. Access Loop and Bug 2. Cancellation 3. Refund 4. UI/UX Enquiry"
    parsed = category_audit_parse_focus(session, focus)
    _print_json("Parse focus (Christine Step 1)", parsed)

    # Sweeps (Christine Step 4 style validation checks)
    sweeps = category_audit_sweeps(session, tier1="B2C")
    _print_json("Category audit sweeps (B2C slice)", sweeps)

    # Draft + preview rules in the exact “Update: Map …” style.
    # These do not confirm live rules; they verify the compiler + preview plumbing.
    rule_messages = [
        (
            "Rosetta footer rule",
            'If it contains "Thanks. Rosetta System Email", that is system email — NOT cancellation request. '
            "Update: Map those tickets to Billing & Admin > System Report.",
        ),
        (
            "Invoice request rule",
            'Update: Map tickets mentioning "invoice" or "发票" or "PO" to Billing & Admin > Invoices and PO request.',
        ),
        (
            "GDPR delete-account rule",
            'Update: Map tickets mentioning "GDPR", "delete my account", or "data erasure" to Account Management > Request to delete account.',
        ),
        (
            "Posties/Young Post → B2B segment",
            'Update: If it contains "Posties" or "Young Post", route to B2B segment (any mention).',
        ),
        (
            "Refund precedence",
            'Refund precedence: if the ticket contains both "refund" and "cancel", update mapping to Refund Request (not Cancellation).',
        ),
        (
            "ESP print → B2B",
            'Update: If it contains "ESP-OPP" or "ESP-INV" or Print distribution context, route to B2B segment / Print.',
        ),
    ]

    for title, msg in rule_messages:
        compiled = compile_rule(session, msg)
        _print_json(f"Compile rule — {title}", compiled)
        rule_obj = compiled.get("rule")
        if isinstance(rule_obj, dict):
            preview = preview_rule(session, rule_obj)
            _print_json(f"Preview on run — {title}", preview)
        else:
            print(f"\nWARN: compiler did not return a rule object for {title}")

    print("\nDone. If you want to actually apply these changes, set PORTAL_ALLOW_CONFIRM=1 and use the portal UI to Confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

