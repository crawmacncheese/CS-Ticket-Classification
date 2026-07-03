document.addEventListener("DOMContentLoaded", () => {
  const roots = document.querySelectorAll(".ticket-preview-root");
  roots.forEach((root) => initTicketPreview(root));
  initTierStatsDrillDown();
});

function escapeCssIdent(value) {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function showPreviewError(root, message) {
  const el = root.querySelector(".ticket-preview-error");
  if (!el) return;
  el.hidden = false;
  el.textContent = message;
}

function initTierStatsDrillDown() {
  document.querySelectorAll(".tier-stats-row--selectable").forEach((tr) => {
    const activate = () => selectTierStatsRow(tr);
    tr.addEventListener("click", activate);
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activate();
      }
    });
  });
}

function selectTierStatsRow(tr) {
  const tier4 = tr.dataset.tier4 || "";
  if (!tier4) return;

  document.querySelectorAll(".tier-stats-row--active").forEach((el) => {
    el.classList.remove("tier-stats-row--active");
  });
  tr.classList.add("tier-stats-row--active");

  const preview = document.getElementById("ticket-preview");
  const categorySelect = preview?.querySelector(".ticket-preview-category-filter");
  if (categorySelect) {
    categorySelect.value = tier4;
    categorySelect.dispatchEvent(new Event("change", { bubbles: true }));
  }

  preview?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function initTicketPreview(root) {
  const tableId = root.dataset.tableId || "classify-ticket-preview";
  const table =
    root.querySelector(`#${escapeCssIdent(tableId)}`) ||
    root.querySelector(".ticket-preview-table");
  const dataEl =
    root.querySelector(`#${escapeCssIdent(tableId)}-data`) ||
    root.querySelector('script[type="application/json"]');
  if (!table || !dataEl) {
    showPreviewError(root, "Ticket preview could not load (missing table or data).");
    return;
  }

  let payload;
  try {
    payload = JSON.parse(dataEl.textContent || "{}");
  } catch (err) {
    showPreviewError(
      root,
      "Ticket preview could not load ticket data. Try refreshing the page."
    );
    console.error("ticket_preview: JSON parse failed", err);
    return;
  }

  const rowsById = new Map();
  function indexRows(arr) {
    (arr || []).forEach((r) => rowsById.set(String(r.id), r));
  }
  indexRows(payload.rows);
  indexRows(payload.tbc_rows);
  if (payload.category_rows) {
    Object.values(payload.category_rows).forEach(indexRows);
  }
  const showDetails = root.querySelector(".show-ticket-preview-details");
  const showTbcOnly = root.querySelector(".show-ticket-preview-tbc-only");
  const categorySelect = root.querySelector(".ticket-preview-category-filter");
  const subjectInput = root.querySelector(".ticket-preview-subject-filter");
  const tagInput = root.querySelector(".ticket-preview-tag-filter");
  const categoryMeta = root.querySelector(".ticket-preview-category-meta");
  const tbcMeta = root.querySelector(".ticket-preview-tbc-meta");
  const noMatchEl = root.querySelector(".ticket-preview-no-match");
  const detailPane =
    root.querySelector(`#${escapeCssIdent(tableId)}-detail`) ||
    root.querySelector(".ticket-preview-detail");
  const detailPlaceholder = detailPane?.querySelector(".ticket-preview-detail-placeholder");
  const detailContent = detailPane?.querySelector(".ticket-preview-detail-content");
  const limit = payload.limit || 200;
  const tbcInSlice = Number(tbcMeta?.dataset.tbcInSlice || 0);
  const tbcTotal = Number(tbcMeta?.dataset.tbcTotal || payload.tbc_total || 0);
  const runId = root.dataset.runId || "";
  let selectedRowId = null;
  let explainCache = new Map();

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

  function tbody() {
    return table.querySelector("tbody");
  }

  function attachRowHandlers() {
    table.querySelectorAll(".ticket-preview-row").forEach((tr) => {
      tr.addEventListener("click", () => selectRow(tr));
    });
  }

  function renderClassifyRowTr(row) {
    const reason = row.tbc_reason || "not_tbc";
    const isTbc = reason !== "not_tbc";
    const tags = formatTags(row.tags);
    const subject = String(row.subject || "");
    const subjectCell = escHtml(subject.length > 120 ? subject.slice(0, 119) + "…" : subject);
    const tier4 = row.tier4 || (Array.isArray(row.tier_path) ? row.tier_path[3] : "");
    const t1 = Array.isArray(row.tier_path) ? row.tier_path[0] : "";
    const t2 = Array.isArray(row.tier_path) ? row.tier_path[1] : "";
    const t3 = Array.isArray(row.tier_path) ? row.tier_path[2] : "";
    const granular = Array.isArray(row.tier_path) ? row.tier_path[4] : "";
    const reasonBadge =
      reason && reason !== "not_tbc"
        ? `<span class="tbc-reason-badge" title="${escHtml(reason)}">${escHtml(
            reasonLabel(reason)
          )}</span>`
        : "";
    const tagsCell = escHtml(tags.length > 80 ? tags.slice(0, 79) + "…" : tags);
    return `
      <tr class="ticket-preview-row" data-ticket-id="${escHtml(row.id)}" data-tbc-reason="${escHtml(
      reason
    )}" data-is-tbc="${String(isTbc)}">
        <td>${escHtml(row.id)}</td>
        <td class="preview-col-compact">${subjectCell}</td>
        <td class="preview-col-compact">${escHtml(tier4)}</td>
        <td class="preview-col-detail" hidden>${escHtml(t1)}</td>
        <td class="preview-col-detail" hidden>${escHtml(t2)}</td>
        <td class="preview-col-detail" hidden>${escHtml(t3)}</td>
        <td class="preview-col-detail" hidden>${escHtml(granular)}</td>
        <td class="preview-col-detail" hidden>${reasonBadge}</td>
        <td class="preview-col-detail" hidden>${tagsCell}</td>
        <td class="preview-col-detail" hidden>${escHtml(row.created_at || "")}</td>
      </tr>
    `.trim();
  }

  function renderChangedRowTr(row) {
    const reason = row.tbc_reason || "not_tbc";
    const isTbc = !!row.is_tbc;
    const oldBadge =
      row.old_tbc && row.old_tbc_reason
        ? `<span class="tbc-reason-badge" title="${escHtml(row.old_tbc_reason)}">${escHtml(
            reasonLabel(row.old_tbc_reason)
          )}</span>`
        : "";
    const newBadge =
      row.new_tbc && row.new_tbc_reason
        ? `<span class="tbc-reason-badge" title="${escHtml(row.new_tbc_reason)}">${escHtml(
            reasonLabel(row.new_tbc_reason)
          )}</span>`
        : "";
    return `
      <tr class="ticket-preview-row" data-ticket-id="${escHtml(row.id)}" data-tbc-reason="${escHtml(
      reason
    )}" data-is-tbc="${String(isTbc)}">
        <td>${escHtml(row.id)}</td>
        <td class="preview-col-compact">${escHtml(row.old_tier4 || "")}</td>
        <td class="preview-col-compact">${escHtml(row.new_tier4 || "")}</td>
        <td class="preview-col-detail" hidden>${escHtml(row.outcome_type || "")}</td>
        <td class="preview-col-detail" hidden>${escHtml(row.gap_fix_mechanism || "")}</td>
        <td class="preview-col-detail" hidden>${oldBadge}</td>
        <td class="preview-col-detail" hidden>${newBadge}</td>
      </tr>
    `.trim();
  }

  function parseTagsList(tags) {
    if (!tags) return [];
    if (Array.isArray(tags)) return tags.map(String);
    if (typeof tags === "string") {
      try {
        const parsed = JSON.parse(tags);
        if (Array.isArray(parsed)) return parsed.map(String);
      } catch {
        return tags ? [tags] : [];
      }
      return tags ? [tags] : [];
    }
    return [String(tags)];
  }

  function getBaseRows() {
    const category = categorySelect?.value || "";
    const tbcOnly = showTbcOnly?.checked || false;

    if (category && payload.category_rows?.[category]?.length) {
      return payload.category_rows[category];
    }
    if (tbcOnly && payload.tbc_rows?.length) {
      return payload.tbc_rows;
    }
    return payload.rows || [];
  }

  function usesFullCategoryExport(category) {
    return Boolean(category && payload.category_rows?.[category]?.length);
  }

  function matchesCategory(row) {
    const category = categorySelect?.value || "";
    if (!category) return true;
    const tier4 = row.tier4 || (Array.isArray(row.tier_path) ? row.tier_path[3] : "");
    return tier4 === category;
  }

  function matchesTbc(row) {
    const tbcOnly = showTbcOnly?.checked || false;
    if (!tbcOnly) return true;
    if (payload.tbc_rows?.length) return true;
    return row.is_tbc || row.tbc_reason !== "not_tbc";
  }

  function matchesSubject(row) {
    const q = (subjectInput?.value || "").trim().toLowerCase();
    if (!q) return true;
    return String(row.subject || "").toLowerCase().includes(q);
  }

  function matchesTag(row) {
    const q = (tagInput?.value || "").trim().toLowerCase();
    if (!q) return true;
    const tags = row.tags_list || parseTagsList(row.tags);
    return tags.some((t) => String(t).toLowerCase().includes(q));
  }

  function countInRun(category) {
    if (!category) return (payload.rows || []).length;
    return (payload.categories || [])
      .filter((c) => c.tier4 === category)
      .reduce((sum, c) => sum + (c.count || 0), 0);
  }

  function countInSlice(category, rows) {
    if (!category) return rows.length;
    return rows.filter((r) => {
      const tier4 = r.tier4 || (Array.isArray(r.tier_path) ? r.tier_path[3] : "");
      return tier4 === category;
    }).length;
  }

  function applyFilters() {
    const baseRows = getBaseRows();
    const category = categorySelect?.value || "";
    const filtered = baseRows.filter(
      (r) => matchesCategory(r) && matchesTbc(r) && matchesSubject(r) && matchesTag(r)
    );

    const tb = tbody();
    if (!tb) return;

    if (filtered.length) {
      tb.innerHTML = filtered
        .map((r) =>
          payload.mode === "changed" ? renderChangedRowTr(r) : renderClassifyRowTr(r)
        )
        .join("");
      attachRowHandlers();
      if (showDetails) setExpanded(showDetails.checked);
      if (noMatchEl) noMatchEl.hidden = true;
      table.hidden = false;

      if (selectedRowId) {
        const selected = table.querySelector(
          `.ticket-preview-row[data-ticket-id="${escapeCssIdent(selectedRowId)}"]`
        );
        if (selected) {
          selectRow(selected);
        } else {
          clearDetailPane();
        }
      }
    } else {
      tb.innerHTML = "";
      table.hidden = false;
      if (noMatchEl) noMatchEl.hidden = false;
      clearDetailPane();
    }

    updateMeta(filtered.length, category, baseRows);
  }

  function updateMeta(visible, category, baseRows) {
    const tbcOnly = showTbcOnly?.checked || false;
    const hasTextFilter =
      (subjectInput?.value || "").trim() || (tagInput?.value || "").trim();

    if (categoryMeta) {
      if (category && payload.filter_copy?.category_meta) {
        const matchedInSlice = countInSlice(category, payload.rows || []);
        const matchedTotal = countInRun(category);
        categoryMeta.hidden = false;
        if (usesFullCategoryExport(category)) {
          categoryMeta.textContent = (
            payload.filter_copy.category_meta_full || payload.filter_copy.category_meta
          )
            .replace("{visible}", String(visible))
            .replace("{matched_total}", String(matchedTotal))
            .replace("{category}", category);
        } else {
          categoryMeta.textContent = payload.filter_copy.category_meta
            .replace("{visible}", String(visible))
            .replace("{matched_in_slice}", String(matchedInSlice))
            .replace("{category}", category)
            .replace("{limit}", String(limit))
            .replace("{matched_total}", String(matchedTotal));
        }
      } else {
        categoryMeta.hidden = true;
        categoryMeta.textContent = "";
      }
    }

    if (tbcMeta) {
      if (tbcOnly && !category && !hasTextFilter) {
        let tbcVisible = 0;
        table.querySelectorAll(".ticket-preview-row").forEach((tr) => {
          if (!tr.hidden && tr.dataset.isTbc === "true") tbcVisible += 1;
        });
        tbcMeta.hidden = false;
        if (tbcTotal > tbcInSlice) {
          tbcMeta.textContent = `Showing ${tbcVisible} manual review tickets from the full export (${tbcTotal} total).`;
        } else {
          tbcMeta.textContent = `Showing ${tbcVisible} of ${tbcInSlice} manual review tickets in this preview (first ${limit} rows of export).`;
        }
      } else {
        tbcMeta.hidden = true;
        tbcMeta.textContent = "";
      }
    }
  }

  function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  if (showTbcOnly) {
    showTbcOnly.addEventListener("change", applyFilters);
  }
  if (categorySelect) {
    categorySelect.addEventListener("change", applyFilters);
  }
  if (subjectInput) {
    subjectInput.addEventListener("input", debounce(applyFilters, 200));
  }
  if (tagInput) {
    tagInput.addEventListener("input", debounce(applyFilters, 200));
  }

  function reasonLabel(code) {
    return (payload.labels && payload.labels[code]) || code;
  }

  function reasonExplanation(code) {
    return (payload.explanations && payload.explanations[code]) || "";
  }

  function formatTags(tags) {
    return parseTagsList(tags).join(", ");
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
    const explainBtn =
      runId && payload.mode === "classify"
        ? `<p class="ticket-preview-explain-wrap"><button type="button" class="ticket-preview-explain-btn">Show classification details</button></p><div class="ticket-preview-explain-panel" hidden></div>`
        : "";
    return `
      <dl class="ticket-preview-detail-dl">
        <dt>Subject</dt><dd>${escHtml(row.subject)}</dd>
        <dt>Description</dt><dd class="ticket-preview-description">${escHtml(row.description)}</dd>
        <dt>Tags</dt><dd>${escHtml(formatTags(row.tags))}</dd>
        <dt>Category path</dt><dd class="category-path-cell">${tuplePathHtml(tierPath)}</dd>
        ${tbcBlock}
      </dl>
      ${explainBtn}`;
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

  function renderExplainPanel(data) {
    const tierPath = tuplePathHtml(data.tier);
    let marginNote = "";
    if (
      data.candidates &&
      data.candidates.length >= 2 &&
      data.candidates[0].score - data.candidates[1].score < 2
    ) {
      marginNote = `<p class="meta classification-explain-margin">Top candidates were close; assignment may be marginal.</p>`;
    }
    const rules =
      data.evidence && data.evidence.length
        ? `<ul class="classification-explain-rules">${data.evidence
            .map(
              (ev) =>
                `<li><code>${escHtml(ev.rule_id)}</code> — weight ${ev.weight}, ${escHtml(ev.signal)}</li>`
            )
            .join("")}</ul>`
        : "<p class=\"meta\">No rules fired.</p>";
    let candidatesBlock = "";
    if (data.candidates && data.candidates.length > 1) {
      candidatesBlock = `<details class="classification-explain-candidates"><summary>Other candidates</summary><ul>${data.candidates
        .slice(1)
        .map(
          (c) =>
            `<li>${tuplePathHtml(c.tier)} — score ${c.score}</li>`
        )
        .join("")}</ul></details>`;
    }
    let tbcBlock = "";
    if (data.tbc_reason) {
      tbcBlock = `<p><strong>TBC reason:</strong> ${escHtml(reasonLabel(data.tbc_reason))}</p>`;
    }
    return `
      <div class="classification-explain">
        <p><strong>Winning category:</strong> ${tierPath}</p>
        <p><strong>Score:</strong> ${data.score}${data.fallback_used ? " (fallback)" : ""}</p>
        ${marginNote}
        ${tbcBlock}
        <h4 class="classification-explain-heading">Rules that fired</h4>
        ${rules}
        ${candidatesBlock}
      </div>`;
  }

  async function loadExplain(ticketId, panel) {
    if (explainCache.has(ticketId)) {
      panel.innerHTML = renderExplainPanel(explainCache.get(ticketId));
      panel.hidden = false;
      return;
    }
    panel.hidden = false;
    panel.innerHTML = '<p class="meta">Loading classification details…</p>';
    try {
      const resp = await fetch(`/run/${encodeURIComponent(runId)}/explain/${encodeURIComponent(ticketId)}?format=json`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      explainCache.set(ticketId, data);
      panel.innerHTML = renderExplainPanel(data);
    } catch (err) {
      console.error("ticket_preview: explain failed", err);
      panel.innerHTML =
        '<p class="ticket-preview-error">Could not load classification details.</p>';
    }
  }

  function clearDetailPane() {
    selectedRowId = null;
    if (!detailContent || !detailPlaceholder) return;
    detailPlaceholder.hidden = false;
    detailContent.hidden = true;
    detailContent.innerHTML = "";
  }

  function selectRow(tr) {
    table.querySelectorAll(".ticket-preview-row--selected").forEach((el) => {
      el.classList.remove("ticket-preview-row--selected");
    });
    tr.classList.add("ticket-preview-row--selected");
    const row = rowsById.get(String(tr.dataset.ticketId || ""));
    if (!row || !detailContent || !detailPlaceholder) return;
    selectedRowId = String(row.id);
    detailPlaceholder.hidden = true;
    detailContent.hidden = false;
    detailContent.innerHTML =
      payload.mode === "changed" ? renderChangedDetail(row) : renderClassifyDetail(row);

    const explainBtn = detailContent.querySelector(".ticket-preview-explain-btn");
    const explainPanel = detailContent.querySelector(".ticket-preview-explain-panel");
    if (explainBtn && explainPanel) {
      explainBtn.addEventListener("click", () => loadExplain(row.id, explainPanel));
    }
  }

  attachRowHandlers();
  applyFilters();
}
