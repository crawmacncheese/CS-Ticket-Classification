"""Cursor-style side-panel Review chat dock beside workbench pages."""

from __future__ import annotations

from cs_tickets.portal_copy import REVIEW_CHAT_BUTTON
from cs_tickets.portal_rules import rules_editor_html


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wrap_workbench_with_review_dock(
    main_html: str,
    *,
    run_id: str = "",
    can_confirm: bool,
) -> str:
    """Wrap primary workbench HTML with a collapsible Review chat side panel.

    ``run_id`` may be empty (e.g. Routing Rules list). The editor then uses
    optional run context / sessionStorage last-run for profile and preview.
    """
    rid = _esc(run_id)
    editor = rules_editor_html(
        run_id=run_id,
        can_confirm=can_confirm,
        orchestration=True,
        dock=True,
    )
    if run_id:
        popout = f"/run/{rid}/review_chat"
    else:
        popout = "/rules/new"
    return f"""
<div class="workbench-layout" id="workbench-layout" data-dock-collapsed="true">
  <div class="workbench-main">
    {main_html}
  </div>
  <aside class="review-dock" id="review-dock" aria-label="{_esc(REVIEW_CHAT_BUTTON)}">
    <div class="review-dock-resize-handle" id="review-dock-resize" role="separator"
      aria-orientation="vertical" aria-label="Resize Review chat panel" tabindex="0"></div>
    <header class="review-dock-header">
      <h2 class="review-dock-title">{_esc(REVIEW_CHAT_BUTTON)}</h2>
      <div class="review-dock-header-actions">
        <a href="{popout}" class="btn btn-secondary btn-sm review-dock-popout"
           title="Open full-page chat">Pop out</a>
        <button type="button" class="btn btn-secondary btn-sm" id="review-dock-collapse"
          aria-controls="review-dock" aria-expanded="false">Hide</button>
      </div>
    </header>
    <div class="review-dock-body">
      {editor}
    </div>
  </aside>
</div>
<button type="button" class="btn btn-primary review-dock-fab" id="review-dock-expand"
  aria-controls="review-dock" aria-expanded="true">{_esc(REVIEW_CHAT_BUTTON)}</button>
""".strip()
