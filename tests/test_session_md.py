"""Tests for session requirements MD writer (Phase A.2–A.3)."""

from __future__ import annotations

from pathlib import Path

from cs_tickets.session_md import (
    append_execution_log,
    append_runner_log,
    create_session_md,
    suggested_session_filename,
)


def test_suggested_session_filename() -> None:
    name = suggested_session_filename(batch="Rosetta / B2C")
    assert name.endswith("-requirements.md")
    assert "rosetta" in name


def test_create_and_append_execution_log(tmp_path: Path, repo_root: Path) -> None:
    template = repo_root / "docs" / "sessions" / "_template-session-requirements.md"
    if not template.is_file():
        return
    dest = tmp_path / "2026-07-14-test-requirements.md"
    create_session_md(
        dest,
        batch_name="Test batch",
        run_id="run-123",
        focus_nl="review B2C",
        persona="analyst",
        taxonomy_version=1,
        template_path=template,
    )
    text = dest.read_text(encoding="utf-8")
    assert "Test batch" in text
    assert "run-123" in text
    assert "review B2C" in text

    n1 = append_execution_log(dest, action="PARSE_FOCUS", result="ok")
    n2 = append_execution_log(dest, action="EXECUTE_SWEEP", result="rosetta match_count=1")
    assert n1 == 1
    assert n2 == 2
    body = dest.read_text(encoding="utf-8")
    assert "| 1 | PARSE_FOCUS | ok |" in body
    assert "| 2 | EXECUTE_SWEEP |" in body


def test_append_runner_log(tmp_path: Path, repo_root: Path) -> None:
    template = repo_root / "docs" / "sessions" / "_template-session-requirements.md"
    dest = tmp_path / "sess.md"
    create_session_md(dest, batch_name="X", template_path=template)
    append_runner_log(
        dest,
        package={"session_id": "sess_abc"},
        log_entries=[
            {"action": "COMPILE_RULE_DRAFT", "status": "ok"},
            {"action": "QUEUE_FOR_CONFIRMATION", "status": "paused"},
        ],
        stopped_reason="queued_for_confirmation",
        run_id="uuid-1",
    )
    body = dest.read_text(encoding="utf-8")
    assert "uuid-1" in body
    assert "COMPILE_RULE_DRAFT" in body
    assert "queued_for_confirmation" in body
