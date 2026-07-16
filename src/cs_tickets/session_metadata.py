"""Session Metadata Package schema for Christine orchestration (Phase B)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from cs_tickets.session_profile import SessionProfile

# Taxonomy MD sweep_id → portal category_audit_sweeps id
SWEEP_ID_ALIASES: dict[str, str] = {
    "rosetta_footer": "rosetta_system_email",
    "refund_precedence": "refund_cancel_combo",
    "account_deletion": "delete_account_gdpr",
}

TERMINAL_BLOCKERS = frozenset({"ZERO_MATCHES"})
SOFT_BLOCKERS = frozenset({"NEEDS_LEAD_CONFIRM", "PREVIEW_STALE", "COMPILE_CLARIFY"})
KNOWN_BLOCKERS = TERMINAL_BLOCKERS | SOFT_BLOCKERS

RUN_MODES = frozenset({"TBC_REVIEW", "CATEGORY_AUDIT", "COMPILE_ONLY"})
USER_PERSONAS = frozenset({"ANALYST", "LEAD"})

QUEUE_ACTIONS = frozenset(
    {
        "ATTACH_RUN",
        "PARSE_FOCUS",
        "EXECUTE_SWEEP",
        "COMPILE_RULE_DRAFT",
        "PREVIEW_RULE",
        "QUEUE_FOR_CONFIRMATION",
        "CONFIRM_RULE",
        "RECLASSIFY_RUN",
    }
)

ROSETTA_COMPILE_PHRASE = (
    'If it contains "Thanks. Rosetta System Email", that is system email - NOT '
    "cancellation request. Update: Map those tickets to Billing & Admin > System Report."
)

DEFAULT_ROSETTA_FOCUS = "review B2C"


class SessionMetadataError(ValueError):
    """Invalid Session Metadata Package."""


def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex}"


def resolve_sweep_id(sweep_id: str) -> str:
    key = (sweep_id or "").strip()
    return SWEEP_ID_ALIASES.get(key, key)


@dataclass(frozen=True)
class QueueAction:
    action: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"action": self.action}
        if self.params:
            out["params"] = dict(self.params)
        return out


@dataclass(frozen=True)
class SessionMetadataPackage:
    session_id: str
    run_id: str | None
    run_mode: str
    user_persona: str
    taxonomy_version: int
    profile: dict[str, Any]
    orchestration_queue: tuple[QueueAction, ...]
    blockers: tuple[str, ...]
    clarify_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "run_mode": self.run_mode,
            "user_persona": self.user_persona,
            "taxonomy_version": self.taxonomy_version,
            "profile": dict(self.profile),
            "orchestration_queue": [a.as_dict() for a in self.orchestration_queue],
            "blockers": list(self.blockers),
            "clarify_message": self.clarify_message,
        }

    @property
    def has_terminal_blockers(self) -> bool:
        return bool(TERMINAL_BLOCKERS.intersection(self.blockers))

    @property
    def is_actionable(self) -> bool:
        """Runner may execute only when queue is non-empty and no terminal blockers."""
        return bool(self.orchestration_queue) and not self.has_terminal_blockers

    def runner_gate(self) -> tuple[bool, str]:
        """Return (ok_to_run, message). Message is clarify text when blocked."""
        if self.has_terminal_blockers:
            return False, self.clarify_message or f"Terminal blockers: {list(self.blockers)}"
        if not self.orchestration_queue:
            return False, "orchestration_queue is empty — nothing to run"
        return True, ""


def _parse_queue_item(raw: Any, *, index: int) -> QueueAction:
    if not isinstance(raw, dict):
        raise SessionMetadataError(f"orchestration_queue[{index}] must be an object")
    action = str(raw.get("action") or "").strip()
    if action not in QUEUE_ACTIONS:
        raise SessionMetadataError(
            f"orchestration_queue[{index}].action must be one of {sorted(QUEUE_ACTIONS)}"
        )
    params = raw.get("params")
    if params is None:
        # Allow flat keys at top level for ergonomic JSON
        params = {k: v for k, v in raw.items() if k != "action"}
    if not isinstance(params, dict):
        raise SessionMetadataError(f"orchestration_queue[{index}].params must be an object")
    return QueueAction(action=action, params=dict(params))


def validate_package_dict(raw: dict[str, Any]) -> list[str]:
    """Return validation errors (empty = ok). Does not raise."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["package must be an object"]

    session_id = str(raw.get("session_id") or "").strip()
    if not session_id:
        errors.append("session_id is required")

    run_mode = str(raw.get("run_mode") or "").strip()
    if run_mode not in RUN_MODES:
        errors.append(f"run_mode must be one of {sorted(RUN_MODES)}")

    persona = str(raw.get("user_persona") or "").strip()
    if persona not in USER_PERSONAS:
        errors.append(f"user_persona must be one of {sorted(USER_PERSONAS)}")

    tax = raw.get("taxonomy_version")
    if not isinstance(tax, int) or isinstance(tax, bool):
        errors.append("taxonomy_version must be an int")

    if not isinstance(raw.get("profile"), dict):
        errors.append("profile must be an object")

    queue = raw.get("orchestration_queue")
    if not isinstance(queue, list):
        errors.append("orchestration_queue must be an array")
    else:
        for i, item in enumerate(queue):
            try:
                _parse_queue_item(item, index=i)
            except SessionMetadataError as exc:
                errors.append(str(exc))

    blockers = raw.get("blockers")
    if not isinstance(blockers, list):
        errors.append("blockers must be an array")
    else:
        for b in blockers:
            if str(b) not in KNOWN_BLOCKERS:
                errors.append(f"unknown blocker: {b}")

    clarify = raw.get("clarify_message")
    if clarify is not None and not isinstance(clarify, str):
        errors.append("clarify_message must be a string or null")

    # Terminal invariant: ZERO_MATCHES ⇒ empty queue
    if isinstance(blockers, list) and isinstance(queue, list):
        if "ZERO_MATCHES" in [str(b) for b in blockers] and len(queue) > 0:
            errors.append("ZERO_MATCHES requires an empty orchestration_queue")

    return errors


def parse_package(raw: dict[str, Any]) -> SessionMetadataPackage:
    errors = validate_package_dict(raw)
    if errors:
        raise SessionMetadataError("; ".join(errors))

    queue = tuple(
        _parse_queue_item(item, index=i)
        for i, item in enumerate(raw.get("orchestration_queue") or [])
    )
    blockers = tuple(str(b) for b in (raw.get("blockers") or []))
    run_id = raw.get("run_id")
    if run_id is not None:
        run_id = str(run_id).strip() or None

    return SessionMetadataPackage(
        session_id=str(raw["session_id"]).strip(),
        run_id=run_id,
        run_mode=str(raw["run_mode"]).strip(),
        user_persona=str(raw["user_persona"]).strip(),
        taxonomy_version=int(raw["taxonomy_version"]),
        profile=dict(raw["profile"]),
        orchestration_queue=queue,
        blockers=blockers,
        clarify_message=raw.get("clarify_message"),
    )


def build_audit_queue(
    *,
    focus_nl: str,
    audit_filter: dict[str, Any],
    sweep_ids: tuple[str, ...] | None,
    rule_prefill: str | None,
    user_persona: str,
) -> tuple[QueueAction, ...]:
    """Build a default category-audit action queue (stops before Confirm for ANALYST)."""
    actions: list[QueueAction] = [
        QueueAction("PARSE_FOCUS", {"text": focus_nl, "mode": "category_audit"}),
    ]
    for sid in sweep_ids or ():
        resolved = resolve_sweep_id(sid)
        if resolved:
            actions.append(QueueAction("EXECUTE_SWEEP", {"sweep_id": resolved}))

    if rule_prefill:
        actions.append(QueueAction("COMPILE_RULE_DRAFT", {"rule_prefill": rule_prefill}))
        actions.append(QueueAction("PREVIEW_RULE", {}))
        actions.append(QueueAction("QUEUE_FOR_CONFIRMATION", {"auto_confirm": False}))
        if user_persona == "LEAD":
            actions.append(QueueAction("CONFIRM_RULE", {}))
            reclass_params: dict[str, Any] = {"snapshot_audit": True}
            if audit_filter.get("tier1"):
                reclass_params["tier1"] = audit_filter["tier1"]
            cats = audit_filter.get("categories") or []
            if cats:
                reclass_params["categories"] = list(cats)
            actions.append(QueueAction("RECLASSIFY_RUN", reclass_params))
    return tuple(actions)


def package_from_profile(
    profile: SessionProfile,
    *,
    run_id: str | None = None,
    run_mode: str = "CATEGORY_AUDIT",
    user_persona: str = "ANALYST",
    taxonomy_version: int = 1,
    session_id: str | None = None,
    rule_prefill: str | None = None,
    sweep_ids: tuple[str, ...] | None = None,
) -> SessionMetadataPackage:
    """Build a Session Metadata Package from a Phase A profile."""
    if run_mode not in RUN_MODES:
        raise SessionMetadataError(f"run_mode must be one of {sorted(RUN_MODES)}")
    if user_persona not in USER_PERSONAS:
        raise SessionMetadataError(f"user_persona must be one of {sorted(USER_PERSONAS)}")

    blockers = list(profile.blockers)
    clarify = profile.clarify_message

    if profile.no_op or "ZERO_MATCHES" in blockers:
        return SessionMetadataPackage(
            session_id=session_id or new_session_id(),
            run_id=run_id,
            run_mode=run_mode,
            user_persona=user_persona,
            taxonomy_version=taxonomy_version,
            profile=profile.as_dict(),
            orchestration_queue=(),
            blockers=tuple(dict.fromkeys(blockers + ["ZERO_MATCHES"])),
            clarify_message=clarify
            or (
                "No tickets match this focus and no slice checks found matches. "
                "Try narrowing or broadening scope."
            ),
        )

    if sweep_ids is None:
        # Default: run portal sweeps that already matched in the profile
        sweep_ids = tuple(
            s.sweep_id for s in profile.sweep_summaries if s.match_count > 0
        )

    queue = build_audit_queue(
        focus_nl=profile.focus_nl,
        audit_filter=profile.audit_filter,
        sweep_ids=sweep_ids,
        rule_prefill=rule_prefill,
        user_persona=user_persona,
    )
    soft: list[str] = []
    if user_persona == "ANALYST" and rule_prefill:
        soft.append("NEEDS_LEAD_CONFIRM")

    return SessionMetadataPackage(
        session_id=session_id or new_session_id(),
        run_id=run_id,
        run_mode=run_mode,
        user_persona=user_persona,
        taxonomy_version=taxonomy_version,
        profile=profile.as_dict(),
        orchestration_queue=queue,
        blockers=tuple(soft),
        clarify_message=None,
    )


def build_rosetta_package(
    profile: SessionProfile,
    *,
    run_id: str | None = None,
    user_persona: str = "ANALYST",
    taxonomy_version: int = 1,
) -> SessionMetadataPackage:
    """Rosetta footer demo package (compile + preview; analyst stops before Confirm)."""
    return package_from_profile(
        profile,
        run_id=run_id,
        run_mode="CATEGORY_AUDIT",
        user_persona=user_persona,
        taxonomy_version=taxonomy_version,
        rule_prefill=ROSETTA_COMPILE_PHRASE,
        sweep_ids=("rosetta_system_email",),
    )
