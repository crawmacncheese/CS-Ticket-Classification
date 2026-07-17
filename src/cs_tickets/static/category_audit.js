document.addEventListener("DOMContentLoaded", () => {
  const app = document.getElementById("category-audit-app");
  if (!app) return;

  const runId = app.dataset.runId || "";
  const sweepsUrl = app.dataset.sweepsUrl || "";
  const statusEl = document.getElementById("category-audit-status");
  const reclassifyBtn = document.getElementById("category-audit-reclassify-btn");
  const sweepsPanel = document.getElementById("category-audit-sweeps-panel");

  function currentFilterBody() {
    return {
      q: app.dataset.filterQ || "",
      tier1: app.dataset.filterTier1 || "",
      tier4: app.dataset.filterTier4 || "",
      categories: (app.dataset.filterCategories || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      include_tbc: app.dataset.filterIncludeTbc === "true",
    };
  }

  function buildFilterQuery(extra) {
    const params = new URLSearchParams();
    const f = currentFilterBody();
    if (f.q) params.set("q", f.q);
    if (f.tier1) params.set("tier1", f.tier1);
    if (f.categories.length) params.set("categories", f.categories.join(","));
    if (f.tier4) params.set("tier4", f.tier4);
    if (f.include_tbc) params.set("include_tbc", "1");
    if (extra) {
      Object.keys(extra).forEach((k) => params.set(k, extra[k]));
    }
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }

  function showStatus(message, isError) {
    if (!statusEl) return;
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("tbc-filter-nl-status--error", Boolean(isError));
  }

  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderSweeps(sweeps) {
    if (!sweepsPanel) return;
    if (!sweeps || !sweeps.length) {
      sweepsPanel.innerHTML = '<p class="meta">No checks available.</p>';
      return;
    }
    sweepsPanel.innerHTML = sweeps
      .map((s) => {
        const warn = s.match_count > 0 ? " category-audit-sweep-row--warn" : "";
        const groupList =
          s.matched_groups && s.matched_groups.length
            ? `<ul class="category-audit-sweep-groups">${s.matched_groups
                .map(
                  (g) =>
                    `<li>${g.map((id) => `#${escHtml(id)}`).join(", ")}</li>`
                )
                .join("")}</ul>`
            : "";
        const ids =
          !groupList && s.matched_ids && s.matched_ids.length
            ? `<ul class="category-audit-sweep-ids">${s.matched_ids
                .map((id) => `<li>#${escHtml(id)}</li>`)
                .join("")}</ul>`
            : "";
        return `
<div class="category-audit-sweep-row${warn}">
  <div class="category-audit-sweep-head">
    <strong>${escHtml(s.label)}</strong>
    <span class="category-audit-sweep-count">${s.match_count} match${s.match_count === 1 ? "" : "es"}</span>
  </div>
  <p class="meta">${escHtml(s.description)}</p>
  ${groupList}
  ${ids}
</div>`;
      })
      .join("");
  }

  function loadSweeps() {
    if (!sweepsUrl || !sweepsPanel) return;
    fetch(sweepsUrl)
      .then((r) => r.json())
      .then((data) => renderSweeps(data.sweeps || []))
      .catch(() => {
        sweepsPanel.innerHTML =
          '<p class="meta tbc-filter-nl-status--error">Could not load slice checks.</p>';
      });
  }

  function reclassifyWithSnapshot() {
    return fetch(`/run/${encodeURIComponent(runId)}/reclassify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot_audit: true, ...currentFilterBody() }),
    }).then((r) => r.json());
  }

  function redirectAfterReclassify() {
    const qs = buildFilterQuery({ reclassified: "1" });
    window.location.href = `/run/${encodeURIComponent(runId)}/category_audit${qs}`;
  }

  function bindExplainButtons() {
    document.querySelectorAll(".category-audit-explain-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest(".category-audit-card");
        const panel = card?.querySelector(".category-audit-explain-panel");
        const ticketId = btn.dataset.ticketId || "";
        if (!panel || !ticketId) return;
        if (!panel.hidden && panel.dataset.loaded === "1") {
          panel.hidden = true;
          return;
        }
        panel.hidden = false;
        panel.textContent = "Loading…";
        fetch(
          `/run/${encodeURIComponent(runId)}/explain/${encodeURIComponent(ticketId)}?format=json`
        )
          .then((r) => r.json())
          .then((data) => {
            const tier = (data.tier || []).join(" → ");
            const rules = (data.evidence || [])
              .map((e) => `${e.rule_id} (${e.weight})`)
              .join(", ");
            panel.innerHTML = `<strong>${escHtml(tier)}</strong><br><span class="meta">Rules: ${escHtml(rules || "none")}</span>`;
            panel.dataset.loaded = "1";
          })
          .catch(() => {
            panel.textContent = "Explain failed.";
          });
      });
    });
  }

  function bindProposeRuleButtons() {
    document.querySelectorAll(".category-audit-propose-rule-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ticketId = btn.dataset.ticketId || "";
        if (!ticketId) return;
        window.dispatchEvent(
          new CustomEvent("cs-tickets:propose-rule-from-ticket", {
            detail: { ticketId, runId },
          })
        );
      });
    });
  }

  if (reclassifyBtn) {
    reclassifyBtn.addEventListener("click", () => {
      reclassifyBtn.disabled = true;
      reclassifyWithSnapshot()
        .then((data) => {
          if (data && data.ok) redirectAfterReclassify();
          else reclassifyBtn.disabled = false;
        })
        .catch(() => {
          reclassifyBtn.disabled = false;
          showStatus("Re-classify failed.", true);
        });
    });
  }

  window.addEventListener("cs-tickets:apply-review-focus", (ev) => {
    const detail = (ev && ev.detail) || {};
    const f = detail.filter || detail.workbench_filter || {};
    const cats = Array.isArray(f.categories) ? f.categories : [];
    // TBC-reason focuses belong on results/TBC queue, not category audit.
    if (f.tbc_reason && !f.q && !f.tier1 && !cats.length) return;
    if (!(f.q || f.tier1 || cats.length || f.active)) return;
    const form = document.getElementById("category-audit-filter-form");
    if (!form) return;
    const qEl = form.querySelector('input[name="q"]');
    const tier1El = form.querySelector('select[name="tier1"]');
    const catsEl = form.querySelector('input[name="categories"]');
    if (qEl) qEl.value = f.q || "";
    if (tier1El) tier1El.value = f.tier1 || "";
    if (catsEl) catsEl.value = cats.join(", ");
    if (typeof detail._markApplied === "function") detail._markApplied("audit");
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.submit();
  });

  loadSweeps();
  bindExplainButtons();
  bindProposeRuleButtons();
});
