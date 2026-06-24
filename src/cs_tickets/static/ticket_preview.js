document.addEventListener("DOMContentLoaded", () => {
  const roots = document.querySelectorAll(".ticket-preview-root");
  roots.forEach((root) => initTicketPreview(root));
});

function initTicketPreview(root) {
  const tableId = root.dataset.tableId || "classify-ticket-preview";
  const table = root.querySelector(`#${CSS.escape(tableId)}`) || root.querySelector(".ticket-preview-table");
  const dataEl = root.querySelector(`#${CSS.escape(tableId)}-data`) || root.querySelector('script[type="application/json"]');
  if (!table || !dataEl) return;

  let payload;
  try {
    payload = JSON.parse(dataEl.textContent || "{}");
  } catch {
    return;
  }

  const rowsById = new Map((payload.rows || []).map((r) => [String(r.id), r]));
  const showDetails = root.querySelector(".show-ticket-preview-details");
  const showTbcOnly = root.querySelector(".show-ticket-preview-tbc-only");
  const tbcMeta = root.querySelector(".ticket-preview-tbc-meta");
  const detailPane = root.querySelector("#ticket-preview-detail");
  const detailPlaceholder = detailPane?.querySelector(".ticket-preview-detail-placeholder");
  const detailContent = detailPane?.querySelector(".ticket-preview-detail-content");
  const limit = payload.limit || 200;
  const tbcInSlice = Number(tbcMeta?.dataset.tbcInSlice || 0);

  const setExpanded = (expanded) => {
    table.classList.toggle("ticket-preview-table--expanded", expanded);
    table.querySelectorAll(".preview-col-detail").forEach((el) => {
      el.hidden = !expanded;
    });
  };

  if (showDetails) {
    setExpanded(showDetails.checked);
    showDetails.addEventListener("change", () => setExpanded(showDetails.checked));
  }

  function applyTbcFilter() {
    const tbcOnly = showTbcOnly?.checked || false;
    let visible = 0;
    table.querySelectorAll(".ticket-preview-row").forEach((tr) => {
      const isTbc = tr.dataset.isTbc === "true";
      const show = !tbcOnly || isTbc;
      tr.hidden = !show;
      if (show && isTbc) visible += 1;
    });
    if (tbcMeta) {
      if (tbcOnly && tbcInSlice > 0) {
        tbcMeta.hidden = false;
        tbcMeta.textContent = `Showing ${visible} of ${tbcInSlice} manual review tickets in this preview (first ${limit} rows of export).`;
      } else {
        tbcMeta.hidden = true;
        tbcMeta.textContent = "";
      }
    }
  }

  if (showTbcOnly) {
    showTbcOnly.addEventListener("change", applyTbcFilter);
  }

  function reasonLabel(code) {
    return (payload.labels && payload.labels[code]) || code;
  }

  function reasonExplanation(code) {
    return (payload.explanations && payload.explanations[code]) || "";
  }

  function formatTags(tags) {
    if (!tags) return "";
    if (typeof tags === "string") {
      try {
        const parsed = JSON.parse(tags);
        if (Array.isArray(parsed)) return parsed.join(", ");
      } catch {
        return tags;
      }
      return tags;
    }
    if (Array.isArray(tags)) return tags.join(", ");
    return String(tags);
  }

  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function tuplePathHtml(tup) {
    if (!tup || tup.length < 4) return "";
    const main = tup.slice(0, 4).map(escHtml).join(" &rarr; ");
    const granular = tup[4];
    if (granular && granular !== "N/A") {
      return `<span class="category-path-main">${main}</span><span class="category-path-granular">${escHtml(granular)}</span>`;
    }
    return `<span class="category-path-main">${main}</span>`;
  }

  function renderClassifyDetail(row) {
    const tierPath = Array.isArray(row.tier_path) ? row.tier_path : [];
    let tbcBlock = "";
    if (row.tbc_reason && row.tbc_reason !== "not_tbc") {
      tbcBlock = `<dt>TBC reason</dt><dd><strong>${escHtml(reasonLabel(row.tbc_reason))}</strong> <span class="meta">(${escHtml(row.tbc_reason)})</span><br>${escHtml(reasonExplanation(row.tbc_reason))}</dd>`;
    }
    return `
      <dl class="ticket-preview-detail-dl">
        <dt>Subject</dt><dd>${escHtml(row.subject)}</dd>
        <dt>Description</dt><dd class="ticket-preview-description">${escHtml(row.description)}</dd>
        <dt>Tags</dt><dd>${escHtml(formatTags(row.tags))}</dd>
        <dt>Category path</dt><dd class="category-path-cell">${tuplePathHtml(tierPath)}</dd>
        ${tbcBlock}
      </dl>`;
  }

  function renderChangedDetail(row) {
    let tbcBlock = "";
    if (row.old_tbc && row.old_tbc_reason) {
      tbcBlock += `<dt>Old TBC reason</dt><dd><strong>${escHtml(reasonLabel(row.old_tbc_reason))}</strong> — ${escHtml(reasonExplanation(row.old_tbc_reason))}</dd>`;
    }
    if (row.new_tbc && row.new_tbc_reason) {
      tbcBlock += `<dt>New TBC reason</dt><dd><strong>${escHtml(reasonLabel(row.new_tbc_reason))}</strong> — ${escHtml(reasonExplanation(row.new_tbc_reason))}</dd>`;
    }
    let outcomeBlock = "";
    if (row.outcome_type) {
      outcomeBlock = `<dt>Outcome</dt><dd>${escHtml(row.outcome_type)}${row.gap_fix_mechanism ? ` (${escHtml(row.gap_fix_mechanism)})` : ""}</dd>`;
    }
    const oldPath = row.old_tuple ? tuplePathHtml(row.old_tuple) : escHtml(row.old_tier4);
    const newPath = row.new_tuple ? tuplePathHtml(row.new_tuple) : escHtml(row.new_tier4);
    return `
      <dl class="ticket-preview-detail-dl">
        <dt>Subject</dt><dd>${escHtml(row.subject)}</dd>
        <dt>Description</dt><dd class="ticket-preview-description">${escHtml(row.description)}</dd>
        <dt>Tags</dt><dd>${escHtml(formatTags(row.tags))}</dd>
        <dt>Category change</dt><dd>${oldPath} &rarr; ${newPath}</dd>
        ${outcomeBlock}
        ${tbcBlock}
      </dl>`;
  }

  function selectRow(tr) {
    table.querySelectorAll(".ticket-preview-row--selected").forEach((el) => {
      el.classList.remove("ticket-preview-row--selected");
    });
    tr.classList.add("ticket-preview-row--selected");
    const row = rowsById.get(String(tr.dataset.ticketId || ""));
    if (!row || !detailContent || !detailPlaceholder) return;
    detailPlaceholder.hidden = true;
    detailContent.hidden = false;
    detailContent.innerHTML =
      payload.mode === "changed" ? renderChangedDetail(row) : renderClassifyDetail(row);
  }

  table.querySelectorAll(".ticket-preview-row").forEach((tr) => {
    tr.addEventListener("click", () => selectRow(tr));
  });

  applyTbcFilter();
}
