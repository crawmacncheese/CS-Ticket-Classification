"""Session requirements MD helpers for Christine orchestration (Phase A.2–A.3)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = _REPO_ROOT / "docs" / "sessions" / "_template-session-requirements.md"
DEFAULT_SESSIONS_DIR = _REPO_ROOT / "docs" / "sessions"

_EXEC_LOG_HEADER = "| Step | Action | Result |"
_EXEC_LOG_SEP = "|------|--------|--------|"


def load_template(template_path: Path | None = None) -> str:
    path = template_path or DEFAULT_TEMPLATE
    return path.read_text(encoding="utf-8")


def suggested_session_filename(*, batch: str = "christine", day: date | None = None) -> str:
    d = day or date.today()
    safe = re.sub(r"[^\w.-]+", "-", batch.strip()).strip("-").lower() or "christine"
    return f"{d.isoformat()}-{safe}-requirements.md"


def create_session_md(
    dest: Path,
    *,
    batch_name: str = "Christine session",
    run_id: str | None = None,
    portal_base: str = "http://127.0.0.1:8777",
    export_file: str = "",
    persona: str = "analyst",
    loop: str = "category_audit",
    taxonomy_version: int = 1,
    focus_nl: str = "",
    goals: str = "",
    template_path: Path | None = None,
) -> Path:
    """Copy template to dest and fill header fields."""
    text = load_template(template_path)
    day = date.today().isoformat()
    text = text.replace("# Session: [BATCH NAME] — [YYYY-MM-DD]", f"# Session: {batch_name} — {day}")
    text = _replace_field(text, "run_id", run_id or "(fill after POST /run)")
    text = _replace_field(text, "portal_base", portal_base)
    text = _replace_field(text, "export_file", export_file or "(path or filename)")
    text = _replace_field(text, "persona", persona.lower())
    text = _replace_field(text, "loop", loop)
    text = re.sub(
        r"\*\*taxonomy_version:\*\*.*",
        f"**taxonomy_version:** {taxonomy_version} (from taxonomy-requirements.md `protocol_version`)",
        text,
        count=1,
    )
    if goals.strip():
        text = re.sub(
            r"(## Goals\n\n)What the analyst wants.*?\n\nExample:.*?\n",
            rf"\1{goals.strip()}\n\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    if focus_nl.strip():
        focus = focus_nl.strip()

        def _focus_sub(match: re.Match[str]) -> str:
            return f"{match.group(1)} {focus}"

        text = re.sub(r"(- \*\*focus_nl:\*\*).*", _focus_sub, text, count=1)

    text = clear_execution_log_examples(text)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def _replace_field(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(\*\*{re.escape(key)}:\*\*).*")

    def _sub(match: re.Match[str]) -> str:
        return f"{match.group(1)} {value}"

    return pattern.sub(_sub, text, count=1)


def _next_log_step_number(text: str) -> int:
    exec_idx = text.find("## Execution log")
    if exec_idx < 0:
        return 1
    section = text[exec_idx:]
    end = section.find("\n## ", 3)
    section = section if end < 0 else section[:end]
    # Ignore template placeholder examples (Upload export / Parse focus / Sweeps)
    placeholder = ("Upload export", "Parse focus", "Sweeps")
    nums: list[int] = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*([^|]+)\|", section, flags=re.MULTILINE):
        action = m.group(2).strip()
        if any(p in action for p in placeholder):
            continue
        nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def clear_execution_log_examples(text: str) -> str:
    """Leave Execution log header + separator; drop template example rows."""
    return re.sub(
        r"(## Execution log\n\n\| Step \| Action \| Result \|\n\|------\|--------\|--------\|\n)(?:\|.*\|\n)+",
        r"\1",
        text,
        count=1,
    )


def append_execution_log(
    path: Path,
    *,
    action: str,
    result: str,
    step: int | None = None,
) -> int:
    """Append one Execution log row. Returns the step number used."""
    text = path.read_text(encoding="utf-8")
    step_n = step if step is not None else _next_log_step_number(text)
    safe_action = action.replace("|", "/").replace("\n", " ").strip()
    safe_result = result.replace("|", "/").replace("\n", " ").strip()
    new_row = f"| {step_n} | {safe_action} | {safe_result} |"

    if _EXEC_LOG_HEADER not in text:
        # Create section at end
        text = text.rstrip() + (
            f"\n\n## Execution log\n\n{_EXEC_LOG_HEADER}\n{_EXEC_LOG_SEP}\n{new_row}\n"
        )
        path.write_text(text, encoding="utf-8")
        return step_n

    # Insert after separator line (or after last table row under Execution log)
    exec_idx = text.find("## Execution log")
    section = text[exec_idx:]
    next_h = re.search(r"\n## ", section[3:])
    if next_h:
        section_end = exec_idx + 3 + next_h.start()
        before = text[:section_end]
        after = text[section_end:]
    else:
        before = text
        after = ""

    # Keep markdown HR (`---`) with the following section, not inside the table
    hr = re.search(r"\n---\s*\n\s*$", before)
    if hr:
        after = before[hr.start() :] + after
        before = before[: hr.start()]

    if _EXEC_LOG_SEP in before[exec_idx:]:
        before = before.rstrip() + f"\n{new_row}\n"
    else:
        before = before.rstrip() + f"\n\n{_EXEC_LOG_HEADER}\n{_EXEC_LOG_SEP}\n{new_row}\n"

    path.write_text(before + after, encoding="utf-8")
    return step_n


def append_runner_log(
    path: Path,
    *,
    package: dict[str, Any],
    log_entries: list[dict[str, Any]],
    stopped_reason: str,
    run_id: str | None,
) -> None:
    """Append runner log entries and patch run_id / results hints."""
    if run_id:
        text = path.read_text(encoding="utf-8")
        text = _replace_field(text, "run_id", run_id)
        path.write_text(text, encoding="utf-8")
        append_execution_log(path, action="ATTACH_RUN / bind", result=f"run_id = {run_id}")

    session_id = str(package.get("session_id") or "")
    if session_id:
        append_execution_log(path, action="SESSION", result=f"session_id = {session_id}")

    for entry in log_entries:
        action = str(entry.get("action") or "STEP")
        status = str(entry.get("status") or "")
        err = entry.get("error")
        if err:
            result = f"{status}: {err}"
        else:
            result = status or "ok"
        append_execution_log(path, action=action, result=result)

    append_execution_log(path, action="RUNNER_STOP", result=stopped_reason)

    # Patch Results rule id if present in last compile-ish log isn't available —
    # callers may pass rule via package optional; skip if unknown.
    rule_drafts = package.get("_last_rule_id")
    if rule_drafts:
        append_execution_log(path, action="RULE", result=f"compiled id = {rule_drafts}")


def summarize_for_results_section(
    path: Path,
    *,
    rule_id: str | None = None,
    preview_matched: int | None = None,
    note: str = "",
) -> None:
    """Best-effort update of Results bullets."""
    text = path.read_text(encoding="utf-8")
    if rule_id:
        text = re.sub(
            r"(- \*\*Rules compiled:\*\*).*",
            rf"\1 {rule_id}",
            text,
            count=1,
        )
    if preview_matched is not None:
        text = re.sub(
            r"(- \*\*Slice counts:\*\*).*",
            rf"\1 preview matched ~ {preview_matched} ticket(s). {note}".rstrip(),
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")
