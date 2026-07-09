document.addEventListener("DOMContentLoaded", () => {
  const app = document.getElementById("category-audit-app");
  if (!app) return;

  const runId = app.dataset.runId || "";
  const sweepsUrl = app.dataset.sweepsUrl || "";
  const nlInput = document.getElementById("category-audit-filter-nl");
  const nlApply = document.getElementById("category-audit-filter-nl-apply");
  const nlStatus = document.getElementById("category-audit-filter-nl-status");
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

  function showNlStatus(message, isError) {
    if (!nlStatus) return;
    nlStatus.hidden = false;
    nlStatus.textContent = message;
    nlStatus.classList.toggle("tbc-filter-nl-status--error", Boolean(isError));
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

  function applyNlFocus() {
    const text = ((nlInput && nlInput.value) || "").trim();
    if (!text) {
      showNlStatus("Enter a review focus phrase.", true);
      return;
    }
    if (nlApply) nlApply.disabled = true;
    showNlStatus("Parsing focus…", false);
    fetch(`/run/${encodeURIComponent(runId)}/category_audit_parse_focus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        include_tbc: app.dataset.filterIncludeTbc === "true",
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (nlApply) nlApply.disabled = false;
        if (!data.ok) {
          showNlStatus((data.errors && data.errors[0]) || "Could not parse focus.", true);
          return;
        }
        const parsed = data.audit_filter || data.filter || {};
        const params = new URLSearchParams();
        if (parsed.q) params.set("q", parsed.q);
        if (parsed.tier1) params.set("tier1", parsed.tier1);
        if (parsed.categories && parsed.categories.length) {
          params.set("categories", parsed.categories.join(","));
        }
        if (parsed.tier4) params.set("tier4", parsed.tier4);
        if (parsed.include_tbc) params.set("include_tbc", "1");
        const qs = params.toString();
        window.location.href = qs
          ? `/run/${encodeURIComponent(runId)}/category_audit?${qs}`
          : `/run/${encodeURIComponent(runId)}/category_audit`;
      })
      .catch(() => {
        if (nlApply) nlApply.disabled = false;
        showNlStatus("Failed to parse focus.", true);
      });
  }

  if (nlApply) nlApply.addEventListener("click", applyNlFocus);
  if (nlInput) {
    nlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        applyNlFocus();
      }
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
          showNlStatus("Re-classify failed.", true);
        });
    });
  }

  loadSweeps();
  bindExplainButtons();
});
