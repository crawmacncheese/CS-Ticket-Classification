from pathlib import Path
from types import SimpleNamespace

from cs_tickets.allowlist_training import _TrainingSession, selection_hash
from cs_tickets.portal_training import training_checklist_html
from cs_tickets.taxonomy import AllowList


def test_no_op_rows_marked_for_deselect_button() -> None:
    tup = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
    selected = frozenset({tup})
    session = _TrainingSession(
        session_id="test",
        temp_dir=Path("/tmp"),
        upload_path=Path("/tmp/upload.xlsx"),
        upload_tuples=selected,
        new_tuples=selected,
        selected_tuples=selected,
        ticket_counts={tup: 1},
        preview_batch_result=SimpleNamespace(),
        preview_no_op_tuples=selected,
        preview_selection_hash=selection_hash(selected),
        preview_compute_no_op=True,
    )
    html = training_checklist_html(session, selected, allow=AllowList(tuples=frozenset()))
    assert "deselect-no-op-tuples" in html
    assert 'class="tuple-row tuple-row--no-op"' in html


def test_impact_column_marks_no_op_and_impactful_rows() -> None:
    no_op = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
    impactful = ("B2B", "Other Stream", "Other Cat", "Other Type", "N/A")
    selected = frozenset({no_op, impactful})
    session = _TrainingSession(
        session_id="test",
        temp_dir=Path("/tmp"),
        upload_path=Path("/tmp/upload.xlsx"),
        upload_tuples=selected,
        new_tuples=selected,
        selected_tuples=selected,
        ticket_counts={no_op: 1, impactful: 2},
        preview_batch_result=SimpleNamespace(),
        preview_no_op_tuples=frozenset({no_op}),
        preview_selection_hash=selection_hash(selected),
        preview_compute_no_op=True,
    )
    html = training_checklist_html(session, selected, allow=AllowList(tuples=frozenset()))
    assert "Impact on export" in html
    assert "Would change tickets" in html
    assert "No impact" in html
    assert "1 would change tickets, 1 have no impact" in html
