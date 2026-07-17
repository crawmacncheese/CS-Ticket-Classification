(function () {
  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function tierPath(tier) {
    if (!tier || !tier.length) return "—";
    return tier.slice(0, 4).map(escHtml).join(" → ");
  }

  function renderInlineTicketDetail(ticket, runId) {
    if (!ticket) return '<p class="meta">No ticket detail.</p>';
    var tags = "";
    if (ticket.tags) {
      tags = "<dt>Tags</dt><dd>" + escHtml(String(ticket.tags)) + "</dd>";
    }
    var requester = ticket.requester_email
      ? "<dt>Requester</dt><dd>" + escHtml(ticket.requester_email) + "</dd>"
      : "";
    var tier = Array.isArray(ticket.tier) ? tierPath(ticket.tier) : "";
    return (
      '<div class="tbc-preview-ticket-detail">' +
      "<dl class=\"ticket-preview-detail-dl\">" +
      "<dt>Ticket</dt><dd><strong>#" +
      escHtml(ticket.id) +
      "</strong></dd>" +
      "<dt>Subject</dt><dd>" +
      escHtml(ticket.subject) +
      "</dd>" +
      "<dt>Description</dt><dd class=\"ticket-preview-description\">" +
      escHtml(ticket.description) +
      "</dd>" +
      requester +
      tags +
      (tier ? "<dt>Category</dt><dd class=\"category-path-cell\">" + tier + "</dd>" : "") +
      "</dl>" +
      "<p class=\"links\">" +
      "<a class=\"btn btn-secondary btn-sm\" href=\"/rules/new?run_id=" +
      encodeURIComponent(runId) +
      "&ticket_id=" +
      encodeURIComponent(ticket.id) +
      "\">Propose rule</a> " +
      "<a class=\"btn btn-secondary btn-sm\" href=\"/run/" +
      encodeURIComponent(runId) +
      "/explain/" +
      encodeURIComponent(ticket.id) +
      "\">Explain</a>" +
      "</p>" +
      "</div>"
    );
  }

  function renderExplainHtml(data) {
    var assigned = tierPath(data.tier);
    var rules =
      data.evidence && data.evidence.length
        ? "<ul class=\"tbc-explain-rules\">" +
          data.evidence
            .map(function (ev) {
              return (
                "<li><code>" +
                escHtml(ev.rule_id) +
                "</code> — weight " +
                ev.weight +
                ", " +
                escHtml(ev.signal) +
                "</li>"
              );
            })
            .join("") +
          "</ul>"
        : "<p class=\"meta\">No rules fired on this ticket.</p>";
    var tbcBlock = "";
    if (data.tbc_reason_label || data.tbc_reason) {
      tbcBlock =
        "<p><strong>Why manual review:</strong> " +
        escHtml(data.tbc_reason_label || data.tbc_reason) +
        "</p>";
    }
    return (
      "<div class=\"tbc-explain-panel\">" +
      "<h4>Classifier</h4>" +
      "<p><strong>Assigned:</strong> " +
      assigned +
      (data.fallback_used ? " <span class=\"meta\">(fallback)</span>" : "") +
      "</p>" +
      tbcBlock +
      "<p><strong>Score:</strong> " +
      escHtml(String(data.score)) +
      "</p>" +
      rules +
      "</div>"
    );
  }

  function rejectionCauseLabel(cause) {
    if (cause === "typo_close_match") {
      return "Likely typo — close match exists";
    }
    if (cause === "taxonomy_not_allowlisted") {
      return "Known category, missing from allow-list";
    }
    if (cause === "hallucinated") {
      return "Not in taxonomy";
    }
    return "Allow-list mismatch";
  }

  function renderAllowlistRejectionBlock(data, ticketId, canAddAllowlist) {
    var rej = data && data.allowlist_rejection;
    if (!rej) return "";
    var html =
      "<p class=\"meta\"><strong>" +
      escHtml(rejectionCauseLabel(rej.cause)) +
      ":</strong> " +
      escHtml(rej.message || "") +
      "</p>";
    if (rej.close_match_path) {
      html +=
        "<p class=\"meta\">Closest allow-list path: <strong>" +
        escHtml(rej.close_match_path) +
        "</strong></p>";
    }
    if (rej.can_add_to_allowlist && rej.rejected_tier) {
      if (canAddAllowlist) {
        html +=
          '<div class="tbc-allowlist-actions">' +
          '<button type="button" class="btn btn-secondary btn-sm tbc-add-allowlist-btn">Add to allow-list</button> ' +
          '<span class="meta tbc-add-allowlist-status" hidden></span>' +
          "</div>";
      } else {
        html +=
          '<p class="meta">Team lead can add this category to the allow-list from the review panel.</p>';
      }
    }
    return html;
  }

  function renderSuggestHtml(data, ticketId, canAddAllowlist) {
    var rejectionBlock = renderAllowlistRejectionBlock(data, ticketId, canAddAllowlist);
    if (!data || !data.ok) {
      return (
        "<div class=\"tbc-suggest-panel\">" +
        "<h4>AI category suggestion</h4>" +
        (rejectionBlock ||
          "<p class=\"meta\">" +
          escHtml((data && data.errors && data.errors[0]) || "No suggestion available.") +
          "</p>") +
        (data && data.classifier_hint
          ? "<p class=\"meta\">Classifier hint: " + escHtml(data.classifier_hint) + "</p>"
          : "") +
        "</div>"
      );
    }
    var src =
      data.source === "llm"
        ? "AI"
        : data.source === "classifier"
          ? "Classifier"
          : "—";
    var applyBtn = "";
    if (data.tier && Array.isArray(data.tier) && data.tier.length === 5) {
      applyBtn =
        '<div class="tbc-suggest-actions">' +
        '<button type="button" class="btn btn-primary btn-sm tbc-apply-suggest-btn">Classify as suggested</button> ' +
        '<span class="meta tbc-apply-suggest-status" hidden></span>' +
        "</div>";
    }
    return (
      "<div class=\"tbc-suggest-panel\">" +
      "<h4>Category suggestion <span class=\"meta\">(" + escHtml(src) + ")</span></h4>" +
      "<p><strong>" +
      escHtml(data.tier_path || "—") +
      "</strong>" +
      (data.confidence ? " · " + escHtml(data.confidence) + " confidence" : "") +
      "</p>" +
      (data.rationale ? "<p class=\"meta\">" + escHtml(data.rationale) + "</p>" : "") +
      rejectionBlock +
      applyBtn +
      "</div>"
    );
  }

  function renderRulePanelHtml(ticketId, prefill, canConfirm, compiledRule) {
    var confirmBtn = canConfirm
      ? '<button type="button" class="btn btn-primary btn-sm tbc-rule-confirm"' +
        (compiledRule ? "" : " disabled") +
        ">Confirm live</button>"
      : '<span class="meta">Team lead confirms live rules.</span>';
    var compiledNote = compiledRule
      ? '<p class="meta tbc-rule-compiled-note">Rule compiled — ready to confirm or include in batch save.</p>'
      : "";
    return (
      "<div class=\"tbc-rule-panel\" data-ticket-id=\"" +
      escHtml(ticketId) +
      "\">" +
      "<h4>Propose routing rule</h4>" +
      "<textarea class=\"tbc-rule-input\" rows=\"4\">" +
      escHtml(prefill || "") +
      "</textarea>" +
      "<div class=\"tbc-rule-actions\">" +
      '<button type="button" class="btn btn-secondary btn-sm tbc-rule-compile">Compile</button> ' +
      '<button type="button" class="btn btn-secondary btn-sm tbc-rule-preview"' +
      (compiledRule ? "" : " disabled") +
      ">Preview</button> " +
      confirmBtn +
      "</div>" +
      compiledNote +
      "<div class=\"tbc-rule-review meta\" hidden></div>" +
      "<div class=\"tbc-rule-preview-results\" hidden></div>" +
      "</div>"
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    var app = document.getElementById("tbc-queue-app");
    if (!app) return;

    var runId = app.getAttribute("data-run-id");
    var autoSuggest = app.getAttribute("data-auto-suggest") === "true";
    var llmAvailable = app.getAttribute("data-llm-available") === "true";
    var canConfirm = app.getAttribute("data-can-confirm") === "true";
    var canAddAllowlist = app.getAttribute("data-can-add-allowlist") === "true";
    var tableWrap = document.getElementById("tbc-queue-table-wrap");
    var completionPanel = document.getElementById("tbc-completion-panel");
    var progressEl = document.getElementById("tbc-queue-progress");
    var chunkSizeEl = document.getElementById("tbc-chunk-size");
    var prevBtn = document.getElementById("tbc-prev-chunk");
    var nextBtn = document.getElementById("tbc-next-chunk");
    var ackBtn = document.getElementById("tbc-ack-chunk");
    var reclassifyBtn = document.getElementById("tbc-reclassify-btn");
    var batchCompileBtn = document.getElementById("tbc-batch-compile");
    var batchConfirmBtn = document.getElementById("tbc-batch-confirm");
    var batchStatusEl = document.getElementById("tbc-batch-status");
    var filterQEl = document.getElementById("tbc-filter-q");
    var filterTier1El = document.getElementById("tbc-filter-tier1");
    var filterCategoriesEl = document.getElementById("tbc-filter-categories");
    var filterClearBtn = document.getElementById("tbc-filter-clear");
    var filterDraftRuleBtn = document.getElementById("tbc-filter-draft-rule");
    var filterRulePanel = document.getElementById("tbc-filter-rule-panel");
    var filterRuleText = document.getElementById("tbc-filter-rule-text");
    var filterRuleCompileBtn = document.getElementById("tbc-filter-rule-compile");
    var filterRulePreviewBtn = document.getElementById("tbc-filter-rule-preview");
    var filterRuleConfirmBtn = document.getElementById("tbc-filter-rule-confirm");
    var filterRuleReviewEl = document.getElementById("tbc-filter-rule-review");
    var filterRulePreviewEl = document.getElementById("tbc-filter-rule-preview-results");

    var sessionKey = "tbc-review-" + runId;
    var filterDebounceTimer = null;

    function loadSession() {
      try {
        var raw = sessionStorage.getItem(sessionKey);
        if (!raw) return {};
        return JSON.parse(raw);
      } catch (_e) {
        return {};
      }
    }

    function saveSession() {
      try {
        sessionStorage.setItem(
          sessionKey,
          JSON.stringify({
            suggest: suggestCache,
            explain: explainCache,
            compiled: compiledRules,
            drafts: ruleDrafts,
            filters: getFilterState(),
            ruleTarget: ruleTargetHint,
            filterRuleDraft: filterRuleDraft,
            filterBatchRule: filterBatchRule,
          })
        );
      } catch (_e) {
        /* quota or private mode */
      }
    }

    var stored = loadSession();
    var offset = 0;
    var currentPayload = null;
    var openPanelId = null;
    var suggestCache = stored.suggest || {};
    var explainCache = stored.explain || {};
    var compiledRules = stored.compiled || {};
    var ruleDrafts = stored.drafts || {};
    var ruleTargetHint = stored.ruleTarget || "";
    var filterRuleDraft = stored.filterRuleDraft || "";
    var filterBatchRule = stored.filterBatchRule || null;
    var filterTbcReason = (stored.filters && stored.filters.tbc_reason) || "";
    var filterReasonMetaEl = null;

    function ensureFilterReasonMeta() {
      if (filterReasonMetaEl) return filterReasonMetaEl;
      var bar = document.getElementById("tbc-filter-bar");
      if (!bar || !bar.parentNode) return null;
      filterReasonMetaEl = document.createElement("p");
      filterReasonMetaEl.id = "tbc-filter-reason-meta";
      filterReasonMetaEl.className = "meta";
      filterReasonMetaEl.hidden = true;
      bar.parentNode.insertBefore(filterReasonMetaEl, bar.nextSibling);
      return filterReasonMetaEl;
    }

    function updateFilterReasonMeta() {
      var el = ensureFilterReasonMeta();
      if (!el) return;
      if (!filterTbcReason) {
        el.hidden = true;
        el.textContent = "";
        return;
      }
      el.hidden = false;
      el.textContent = filterTbcReason.startsWith("!")
        ? "TBC reason filter: not " + filterTbcReason.slice(1)
        : "TBC reason filter: " + filterTbcReason;
    }

    function getFilterState() {
      return {
        q: filterQEl ? (filterQEl.value || "").trim() : "",
        tier1: filterTier1El ? filterTier1El.value || "" : "",
        categories: filterCategoriesEl ? (filterCategoriesEl.value || "").trim() : "",
        tbc_reason: filterTbcReason || "",
      };
    }

    function setFilterInputs(state) {
      state = state || {};
      if (filterQEl) filterQEl.value = state.q || "";
      if (filterTier1El) filterTier1El.value = state.tier1 || "";
      if (filterCategoriesEl) filterCategoriesEl.value = state.categories || "";
      if (Object.prototype.hasOwnProperty.call(state, "tbc_reason")) {
        filterTbcReason = state.tbc_reason || "";
      }
      updateFilterReasonMeta();
    }

    function filterQueryString(extra) {
      var params = new URLSearchParams();
      var f = getFilterState();
      if (f.q) params.set("q", f.q);
      if (f.tier1) params.set("tier1", f.tier1);
      if (f.categories) params.set("categories", f.categories);
      if (f.tbc_reason) params.set("tbc_reason", f.tbc_reason);
      if (extra) {
        Object.keys(extra).forEach(function (k) {
          if (extra[k] != null && extra[k] !== "") params.set(k, String(extra[k]));
        });
      }
      var qs = params.toString();
      return qs ? "?" + qs : "";
    }

    function scheduleFilterReload() {
      if (filterDebounceTimer) clearTimeout(filterDebounceTimer);
      filterDebounceTimer = setTimeout(function () {
        offset = 0;
        saveSession();
        updateFilterDraftButton();
        loadChunk();
      }, 280);
    }

    setFilterInputs(stored.filters || {});
    if (filterRuleText && filterRuleDraft) {
      filterRuleText.value = filterRuleDraft;
    }

    function updateFilterDraftButton() {
      var active = getFilterState();
      var isActive = !!(active.q || active.tier1 || active.categories || active.tbc_reason);
      if (filterDraftRuleBtn) filterDraftRuleBtn.hidden = !isActive;
    }

    updateFilterDraftButton();
    updateFilterReasonMeta();

    function chunkLimit() {
      return parseInt(chunkSizeEl.value, 10) || 10;
    }

    function closePanelRows() {
      tableWrap.querySelectorAll(".tbc-panel-row").forEach(function (el) {
        el.remove();
      });
      openPanelId = null;
    }

    function setSuggestCell(ticketId, html) {
      var cell = tableWrap.querySelector(
        'tr[data-ticket-id="' + CSS.escape(ticketId) + '"] .tbc-suggest-cell'
      );
      if (cell) cell.innerHTML = html;
    }

    function suggestCellHtml(data) {
      if (data.ok && data.tier_path) {
        var src = data.source === "llm" ? "AI" : "Classifier";
        return (
          escHtml(data.tier_path) +
          ' <span class="meta">(' +
          escHtml(src) +
          ")</span>"
        );
      }
      var shortMsg =
        (data.errors && data.errors[0]) ||
        (data.allowlist_rejection && data.allowlist_rejection.message) ||
        data.classifier_hint ||
        "—";
      return '<span class="meta">' + escHtml(shortMsg) + "</span>";
    }

    function applySuggestCellFromCache(ticketId) {
      if (!suggestCache[ticketId]) return;
      setSuggestCell(ticketId, suggestCellHtml(suggestCache[ticketId]));
    }

    function chunkTicketIds() {
      if (!currentPayload || !currentPayload.rows) return [];
      return currentPayload.rows.map(function (r) {
        return r.ticket_id;
      });
    }

    function updateBatchConfirmButton() {
      if (!batchConfirmBtn) return;
      var ids = chunkTicketIds();
      var ready = ids.filter(function (tid) {
        return compiledRules[tid];
      });
      batchConfirmBtn.textContent = "Confirm all compiled (" + ready.length + ")";
      batchConfirmBtn.disabled = !canConfirm || ready.length === 0;
    }

    function fetchSuggest(ticketId, options) {
      options = options || {};
      if (!options.force && suggestCache[ticketId]) {
        applySuggestCellFromCache(ticketId);
        return Promise.resolve(suggestCache[ticketId]);
      }
      setSuggestCell(ticketId, '<span class="meta">Suggesting…</span>');
      return fetch(
        "/run/" +
          encodeURIComponent(runId) +
          "/suggest_category/" +
          encodeURIComponent(ticketId),
        { method: "POST" }
      )
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          suggestCache[ticketId] = data;
          saveSession();
          setSuggestCell(ticketId, suggestCellHtml(data));
          return data;
        })
        .catch(function (err) {
          setSuggestCell(ticketId, '<span class="meta">Suggest failed</span>');
          throw err;
        });
    }

    function autoSuggestChunk(rows) {
      if (!autoSuggest || !llmAvailable || !rows || !rows.length) return Promise.resolve();
      var queue = rows.filter(function (row) {
        return !suggestCache[row.ticket_id];
      });
      queue.forEach(function (row) {
        applySuggestCellFromCache(row.ticket_id);
      });
      if (!queue.length) return Promise.resolve();
      var concurrency = 3;
      var active = 0;
      var idx = 0;
      return new Promise(function (resolve) {
        function next() {
          if (idx >= queue.length && active === 0) {
            resolve();
            return;
          }
          while (active < concurrency && idx < queue.length) {
            var tid = queue[idx++].ticket_id;
            active++;
            fetchSuggest(tid)
              .catch(function () {})
              .finally(function () {
                active--;
                next();
              });
          }
        }
        next();
      });
    }

    function showCompletionPanel(data) {
      if (!completionPanel) return;
      var acked = data && data.acked ? data.acked : 0;
      var pending = data && data.total_pending != null ? data.total_pending : 0;
      completionPanel.hidden = false;
      var lead =
        pending === 0
          ? "<p>All manual-review tickets in this run have been reviewed" +
            (acked ? " (last chunk: " + acked + " skipped without new rules)." : ".") +
            "</p>"
          : "<p>Chunk skipped" +
            (acked ? " (" + acked + " tickets)." : ".") +
            " " +
            pending +
            " ticket(s) still in the queue.</p>";
      completionPanel.innerHTML =
        '<div class="tbc-completion-card run-summary" role="status">' +
        "<h2>Review complete</h2>" +
        lead +
        '<p class="links">' +
        '<a href="/run/' +
        escHtml(runId) +
        '/results" class="btn btn-primary">View run results</a> ' +
        '<button type="button" class="btn btn-secondary" id="tbc-completion-reclassify">Re-classify run</button>' +
        "</p></div>";
      tableWrap.innerHTML = "";
      closePanelRows();
      var btn = document.getElementById("tbc-completion-reclassify");
      if (btn) {
        btn.addEventListener("click", function () {
          if (reclassifyBtn) reclassifyBtn.click();
        });
      }
      if (progressEl) {
        progressEl.textContent = "Queue complete";
      }
      if (ackBtn) ackBtn.disabled = true;
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
    }

    function loadChunk() {
      closePanelRows();
      if (completionPanel) completionPanel.hidden = true;
      var limit = chunkLimit();
      var qs = filterQueryString({
        offset: offset,
        limit: limit,
      });
      fetch("/run/" + encodeURIComponent(runId) + "/tbc_queue" + qs)
        .then(function (r) {
          if (!r.ok) throw new Error("Failed to load queue");
          return r.json();
        })
        .then(function (data) {
          currentPayload = data;
          if (data.total_pending === 0 && data.total_pending_unfiltered === 0) {
            showCompletionPanel({ total_pending: 0 });
            updateBatchConfirmButton();
            return;
          }
          if (data.total_pending === 0 && data.filter && data.filter.active) {
            tableWrap.innerHTML =
              '<p class="meta">No tickets match the current filter. Try broader keywords or clear filters.</p>';
            updateNav(data);
            updateBatchConfirmButton();
            return;
          }
          renderTable(data);
          updateNav(data);
          updateBatchConfirmButton();
          updateFilterDraftButton();
          return autoSuggestChunk(data.rows);
        })
        .catch(function (err) {
          tableWrap.innerHTML =
            '<p class="meta" role="alert">Could not load queue: ' + escHtml(err.message) + "</p>";
        });
    }

    function renderTable(data) {
      if (!data.rows || !data.rows.length) {
        tableWrap.innerHTML =
          '<p class="meta">No tickets in this chunk. Try the next chunk or finish review.</p>';
        return;
      }
      var rows = data.rows
        .map(function (row) {
          var cached = suggestCache[row.ticket_id];
          var suggestCell = llmAvailable
            ? cached
              ? suggestCellHtml(cached)
              : '<span class="meta">…</span>'
            : escHtml(row.suggested_tier);
          var compiledMark = compiledRules[row.ticket_id]
            ? ' <span class="meta">(rule ready)</span>'
            : "";
          return (
            "<tr data-ticket-id=\"" +
            escHtml(row.ticket_id) +
            "\">" +
            '<td><code>#' +
            escHtml(row.ticket_id) +
            "</code></td>" +
            '<td class="tbc-queue-quote">' +
            escHtml(row.quote) +
            "</td>" +
            "<td>" +
            escHtml(row.why_tbc) +
            "</td>" +
            '<td class="tbc-suggest-cell category-path-cell">' +
            suggestCell +
            compiledMark +
            "</td>" +
            '<td class="tbc-queue-actions">' +
            '<button type="button" class="btn btn-secondary btn-sm tbc-review-btn">Review</button>' +
            "</td></tr>"
          );
        })
        .join("");
      tableWrap.innerHTML =
        '<table class="stats-table tbc-queue-table">' +
        "<thead><tr>" +
        "<th>Ticket ID</th><th>Context / quote</th><th>Why TBC</th><th>Suggested classification</th><th></th>" +
        "</tr></thead><tbody>" +
        rows +
        "</tbody></table>";
      if (!llmAvailable && data.rows) {
        data.rows.forEach(function (row) {
          setSuggestCell(row.ticket_id, escHtml(row.suggested_tier));
        });
      }
    }

    function updateNav(data) {
      var filtered = data.total_pending;
      var total = data.total_pending_unfiltered != null ? data.total_pending_unfiltered : filtered;
      var filterNote =
        data.filter && data.filter.active && filtered !== total
          ? filtered + " in focus · " + total + " total · "
          : filtered + " awaiting review · ";
      progressEl.textContent =
        filterNote +
        "chunk " +
        data.chunk_index +
        " of " +
        data.chunk_total;
      prevBtn.disabled = !data.has_prev;
      nextBtn.disabled = !data.has_next;
      ackBtn.disabled = !data.rows || !data.rows.length;
    }

    function fetchExplain(ticketId) {
      if (explainCache[ticketId]) {
        return Promise.resolve(explainCache[ticketId]);
      }
      return fetch(
        "/run/" +
          encodeURIComponent(runId) +
          "/explain/" +
          encodeURIComponent(ticketId) +
          "?format=json"
      )
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          explainCache[ticketId] = data;
          saveSession();
          return data;
        });
    }

    function compileRuleForTicket(ticketId, text) {
      return fetch("/rules/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: text }],
          run_id: runId,
          exemplar_ticket_id: ticketId,
          prior_rule: compiledRules[ticketId] || null,
        }),
      }).then(function (r) {
        return r.json();
      });
    }

    function wireSuggestPanel(panelRow, ticketId, suggest) {
      var applyBtn = panelRow.querySelector(".tbc-apply-suggest-btn");
      var applyStatus = panelRow.querySelector(".tbc-apply-suggest-status");
      if (
        applyBtn &&
        suggest &&
        suggest.ok &&
        suggest.tier &&
        Array.isArray(suggest.tier) &&
        suggest.tier.length === 5
      ) {
        applyBtn.addEventListener("click", function () {
          applyBtn.disabled = true;
          if (applyStatus) {
            applyStatus.hidden = false;
            applyStatus.textContent = "Saving…";
          }
          fetch(
            "/run/" +
              encodeURIComponent(runId) +
              "/override/" +
              encodeURIComponent(ticketId),
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ tier: suggest.tier, note: "Applied suggested category from TBC queue." }),
            }
          )
            .then(function (r) {
              return r.json().then(function (data) {
                if (!r.ok) {
                  throw new Error(data.detail || "HTTP " + r.status);
                }
                return data;
              });
            })
            .then(function () {
              if (applyStatus) applyStatus.textContent = "Classified.";
              closePanelRows();
              loadChunk();
            })
            .catch(function (err) {
              applyBtn.disabled = false;
              if (applyStatus) applyStatus.textContent = err.message || "Save failed.";
            });
        });
      }
      var btn = panelRow.querySelector(".tbc-add-allowlist-btn");
      if (!btn || !suggest || !suggest.allowlist_rejection || !suggest.allowlist_rejection.rejected_tier) {
        return;
      }
      var tier = suggest.allowlist_rejection.rejected_tier;
      var statusEl = panelRow.querySelector(".tbc-add-allowlist-status");
      btn.addEventListener("click", function () {
        btn.disabled = true;
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = "Adding…";
        }
        fetch(
          "/run/" +
            encodeURIComponent(runId) +
            "/add_allowlist_tuple/" +
            encodeURIComponent(ticketId),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tier: tier }),
          }
        )
          .then(function (r) {
            return r.json().then(function (data) {
              if (!r.ok) {
                throw new Error(data.detail || "HTTP " + r.status);
              }
              return data;
            });
          })
          .then(function (data) {
            if (statusEl) {
              statusEl.textContent = data.message || "Added to allow-list.";
            }
            delete suggestCache[ticketId];
            saveSession();
            fetchSuggest(ticketId, { force: true }).catch(function () {});
          })
          .catch(function (err) {
            btn.disabled = false;
            if (statusEl) {
              statusEl.textContent = err.message || "Add failed.";
            }
          });
      });
    }

    function wireRulePanel(panelRow, ticketId, prefill) {
      var panel = panelRow.querySelector(".tbc-rule-panel");
      if (!panel) return;
      var input = panel.querySelector(".tbc-rule-input");
      var compileBtn = panel.querySelector(".tbc-rule-compile");
      var previewBtn = panel.querySelector(".tbc-rule-preview");
      var confirmBtn = panel.querySelector(".tbc-rule-confirm");
      var reviewEl = panel.querySelector(".tbc-rule-review");
      var previewEl = panel.querySelector(".tbc-rule-preview-results");
      var draft = ruleDrafts[ticketId] || prefill || "";
      if (input) input.value = draft;

      input.addEventListener("input", function () {
        ruleDrafts[ticketId] = input.value;
        saveSession();
      });

      if (compiledRules[ticketId]) {
        reviewEl.hidden = false;
        reviewEl.innerHTML =
          "<p><strong>Category:</strong> " + tierPath(compiledRules[ticketId].tier) + "</p>";
        previewBtn.disabled = false;
        if (confirmBtn) confirmBtn.disabled = false;
      }

      compileBtn.addEventListener("click", function () {
        var text = (input.value || "").trim();
        if (!text) return;
        reviewEl.hidden = false;
        reviewEl.textContent = "Compiling…";
        compileRuleForTicket(ticketId, text)
          .then(function (data) {
            if (!data.ok) {
              reviewEl.textContent = (data.errors || []).join(" ") || "Compile failed.";
              previewBtn.disabled = true;
              if (confirmBtn) confirmBtn.disabled = true;
              return;
            }
            compiledRules[ticketId] = data.rule;
            ruleDrafts[ticketId] = text;
            saveSession();
            reviewEl.innerHTML =
              "<p>" +
              escHtml(data.rationale || "") +
              "</p><p><strong>Category:</strong> " +
              tierPath(data.rule.tier) +
              "</p>";
            previewBtn.disabled = false;
            if (confirmBtn) confirmBtn.disabled = false;
            updateBatchConfirmButton();
            applySuggestCellFromCache(ticketId);
            var row = tableWrap.querySelector('tr[data-ticket-id="' + CSS.escape(ticketId) + '"]');
            if (row && !row.querySelector(".tbc-rule-compiled-note")) {
              var cell = row.querySelector(".tbc-suggest-cell");
              if (cell && cell.innerHTML.indexOf("rule ready") === -1) {
                cell.innerHTML += ' <span class="meta">(rule ready)</span>';
              }
            }
          });
      });

      previewBtn.addEventListener("click", function () {
        var rule = compiledRules[ticketId];
        if (!rule) return;
        fetch("/rules/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule: rule, run_id: runId, ticket_ids: [ticketId] }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!data.ok) {
              alert((data.errors || []).join("\n"));
              return;
            }
            previewEl.hidden = false;
            previewEl.innerHTML =
              "<table class=\"stats-table\"><tr><th>Before</th><th>After</th></tr>" +
              (data.results || [])
                .map(function (row) {
                  return (
                    "<tr><td>" +
                    tierPath(row.before) +
                    "</td><td>" +
                    tierPath(row.after) +
                    "</td></tr>"
                  );
                })
                .join("") +
              "</table>";
          });
      });

      if (confirmBtn) {
        confirmBtn.addEventListener("click", function () {
          var rule = compiledRules[ticketId];
          if (!rule || !window.confirm("Confirm this rule to live config?")) return;
          var confirmDefaultLabel = confirmBtn.textContent;
          confirmBtn.disabled = true;
          confirmBtn.textContent = "Confirming…";
          confirmBtn.setAttribute("aria-busy", "true");
          fetch("/rules/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rule: rule }),
          })
            .then(function (r) {
              if (r.status === 403) throw new Error("Confirm not allowed for your role.");
              return r.json();
            })
            .then(function (data) {
              if (!data.ok) {
                alert((data.errors || []).join("\n"));
                return;
              }
              delete compiledRules[ticketId];
              saveSession();
              confirmBtn.textContent = "Reclassifying run…";
              return fetch("/run/" + encodeURIComponent(runId) + "/reclassify", {
                method: "POST",
              });
            })
            .then(function () {
              offset = 0;
              loadChunk();
            })
            .catch(function (err) {
              alert(err.message || "Confirm failed.");
            })
            .finally(function () {
              confirmBtn.textContent = confirmDefaultLabel;
              confirmBtn.removeAttribute("aria-busy");
              confirmBtn.disabled = false;
            });
        });
      }
    }

    function openReviewPanel(ticketId, rowEl) {
      if (openPanelId === ticketId) {
        closePanelRows();
        return;
      }
      closePanelRows();
      openPanelId = ticketId;
      var tr = document.createElement("tr");
      tr.className = "tbc-panel-row";
      tr.innerHTML =
        '<td colspan="5"><div class="tbc-panel-inline"><p class="meta">Loading review…</p></div></td>';
      rowEl.after(tr);
      tr.scrollIntoView({ behavior: "smooth", block: "nearest" });
      var inline = tr.querySelector(".tbc-panel-inline");

      Promise.all([
        fetchExplain(ticketId),
        suggestCache[ticketId]
          ? Promise.resolve(suggestCache[ticketId])
          : fetchSuggest(ticketId).catch(function () { return null; }),
      ])
        .then(function (parts) {
          var explain = parts[0];
          var suggest = parts[1];
          var prefill =
            ruleDrafts[ticketId] ||
            (suggest && suggest.prefill) ||
            "Update: Map tickets like #" + ticketId + " to [target category].";
          if (suggest && suggest.ok && suggest.tier_path && !ruleDrafts[ticketId]) {
            prefill = prefill + "\n\nSuggested category: " + suggest.tier_path + ".";
          }
          inline.innerHTML =
            renderExplainHtml(explain) +
            renderSuggestHtml(suggest, ticketId, canAddAllowlist) +
            renderRulePanelHtml(ticketId, prefill, canConfirm, compiledRules[ticketId]);
          wireSuggestPanel(tr, ticketId, suggest);
          wireRulePanel(tr, ticketId, prefill);
        })
        .catch(function () {
          inline.innerHTML = '<p class="meta" role="alert">Could not load review panel.</p>';
        });
    }

    if (batchCompileBtn) {
      batchCompileBtn.addEventListener("click", function () {
        if (!currentPayload || !currentPayload.rows || !currentPayload.rows.length) return;
        var rows = currentPayload.rows.slice();
        var pending = rows.filter(function (row) {
          return !compiledRules[row.ticket_id];
        });
        if (!pending.length) {
          if (batchStatusEl) batchStatusEl.textContent = "All tickets in chunk already compiled.";
          return;
        }
        batchCompileBtn.disabled = true;
        if (batchStatusEl) batchStatusEl.textContent = "Compiling 0 / " + pending.length + "…";
        var done = 0;
        var failed = 0;
        function compileNext() {
          if (!pending.length) {
            batchCompileBtn.disabled = false;
            if (batchStatusEl) {
              batchStatusEl.textContent =
                "Compiled " + (done - failed) + " of " + done + " draft rules.";
            }
            updateBatchConfirmButton();
            loadChunk();
            return;
          }
          var row = pending.shift();
          var tid = row.ticket_id;
          var text = (
            ruleDrafts[tid] ||
            (suggestCache[tid] && suggestCache[tid].prefill) ||
            ""
          ).trim();
          if (!text) {
            done++;
            compileNext();
            return;
          }
          if (batchStatusEl) {
            batchStatusEl.textContent = "Compiling " + done + " / " + (done + pending.length + 1) + "…";
          }
          compileRuleForTicket(tid, text)
            .then(function (data) {
              done++;
              if (data.ok && data.rule) {
                compiledRules[tid] = data.rule;
                ruleDrafts[tid] = text;
                saveSession();
              } else {
                failed++;
              }
            })
            .catch(function () {
              done++;
              failed++;
            })
            .finally(compileNext);
        }
        compileNext();
      });
    }

    if (batchConfirmBtn) {
      batchConfirmBtn.addEventListener("click", function () {
        var ids = chunkTicketIds().filter(function (tid) {
          return compiledRules[tid];
        });
        if (!ids.length) return;
        if (
          !window.confirm(
            "Confirm " + ids.length + " compiled rule(s) to live config?"
          )
        ) {
          return;
        }
        var rules = ids.map(function (tid) {
          return compiledRules[tid];
        });
        batchConfirmBtn.disabled = true;
        if (batchStatusEl) batchStatusEl.textContent = "Confirming…";
        fetch("/rules/confirm_batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rules: rules }),
        })
          .then(function (r) {
            if (r.status === 403) throw new Error("Confirm not allowed for your role.");
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) {
              throw new Error((data.errors || []).join("\n") || "Batch confirm failed.");
            }
            ids.forEach(function (tid) {
              delete compiledRules[tid];
            });
            saveSession();
            if (batchStatusEl) {
              batchStatusEl.textContent =
                "Confirmed " + (data.rules_added || rules.length) + " rule(s). Re-classifying…";
            }
            return fetch("/run/" + encodeURIComponent(runId) + "/reclassify", {
              method: "POST",
            });
          })
          .then(function () {
            offset = 0;
            loadChunk();
          })
          .catch(function (err) {
            batchConfirmBtn.disabled = false;
            updateBatchConfirmButton();
            alert(err.message || "Batch confirm failed.");
          });
      });
    }

    tableWrap.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".tbc-review-btn");
      if (!btn) return;
      ev.preventDefault();
      var rowEl = btn.closest("tr");
      if (!rowEl) return;
      var ticketId = rowEl.getAttribute("data-ticket-id");
      if (ticketId) openReviewPanel(ticketId, rowEl);
    });

    prevBtn.addEventListener("click", function () {
      if (currentPayload && currentPayload.has_prev) {
        offset = currentPayload.prev_offset;
        loadChunk();
      }
    });

    nextBtn.addEventListener("click", function () {
      if (currentPayload && currentPayload.has_next) {
        offset = currentPayload.next_offset;
        loadChunk();
      }
    });

    chunkSizeEl.addEventListener("change", function () {
      offset = 0;
      loadChunk();
    });

    ackBtn.addEventListener("click", function () {
      if (!currentPayload || !currentPayload.rows || !currentPayload.rows.length) return;
      var ids = currentPayload.rows.map(function (r) { return r.ticket_id; });
      var f = getFilterState();
      fetch("/run/" + encodeURIComponent(runId) + "/tbc_chunk/ack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_ids: ids,
          offset: offset,
          limit: chunkLimit(),
          q: f.q,
          tier1: f.tier1,
          categories: f.categories,
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok) {
            alert("Could not skip chunk.");
            return;
          }
          if (data.queue_complete) {
            showCompletionPanel(data);
            return;
          }
          offset = data.next_offset != null ? data.next_offset : offset;
          loadChunk();
        });
    });

    if (reclassifyBtn) {
      reclassifyBtn.addEventListener("click", function () {
        reclassifyBtn.disabled = true;
        fetch("/run/" + encodeURIComponent(runId) + "/reclassify", { method: "POST" })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            reclassifyBtn.disabled = false;
            if (!data.ok) {
              alert("Re-classify failed.");
              return;
            }
            var banner = document.getElementById("tbc-reclassify-banner");
            if (banner) {
              banner.textContent =
                "Re-classified: manual review " + data.tbc_before + " → " + data.tbc_after + ".";
              banner.hidden = false;
            }
            if (completionPanel) completionPanel.hidden = true;
            offset = 0;
            loadChunk();
          })
          .catch(function () {
            reclassifyBtn.disabled = false;
          });
      });
    }

    if (filterQEl) {
      filterQEl.addEventListener("input", scheduleFilterReload);
    }
    if (filterCategoriesEl) {
      filterCategoriesEl.addEventListener("input", scheduleFilterReload);
    }
    if (filterTier1El) {
      filterTier1El.addEventListener("change", function () {
        offset = 0;
        saveSession();
        updateFilterDraftButton();
        loadChunk();
      });
    }
    if (filterClearBtn) {
      filterClearBtn.addEventListener("click", function () {
        setFilterInputs({ q: "", tier1: "", categories: "", tbc_reason: "" });
        ruleTargetHint = "";
        if (filterRulePanel) filterRulePanel.hidden = true;
        offset = 0;
        saveSession();
        updateFilterDraftButton();
        loadChunk();
      });
    }

    if (filterDraftRuleBtn) {
      filterDraftRuleBtn.addEventListener("click", function () {
        var f = getFilterState();
        if (!f.q && !f.tier1 && !f.categories) return;
        filterDraftRuleBtn.disabled = true;
        fetch("/run/" + encodeURIComponent(runId) + "/tbc_draft_rule_for_filter", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            q: f.q,
            tier1: f.tier1,
            categories: f.categories,
            rule_target: ruleTargetHint,
          }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            filterDraftRuleBtn.disabled = false;
            if (!data.ok) {
              alert((data.errors && data.errors[0]) || "Could not draft rule.");
              return;
            }
            filterRuleDraft = data.prefill || "";
            if (filterRuleText) filterRuleText.value = filterRuleDraft;
            if (filterRulePanel) filterRulePanel.hidden = false;
            filterBatchRule = null;
            if (filterRulePreviewBtn) filterRulePreviewBtn.disabled = true;
            if (filterRuleConfirmBtn) filterRuleConfirmBtn.disabled = true;
            if (filterRuleReviewEl) filterRuleReviewEl.hidden = true;
            if (filterRulePreviewEl) filterRulePreviewEl.hidden = true;
            saveSession();
            filterRulePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
          })
          .catch(function () {
            filterDraftRuleBtn.disabled = false;
          });
      });
    }

    if (filterRuleText) {
      filterRuleText.addEventListener("input", function () {
        filterRuleDraft = filterRuleText.value;
        saveSession();
      });
    }

    if (filterRuleCompileBtn && filterRuleText) {
      filterRuleCompileBtn.addEventListener("click", function () {
        var text = (filterRuleText.value || "").trim();
        if (!text) return;
        var exemplarId = chunkTicketIds()[0] || "";
        if (filterRuleReviewEl) {
          filterRuleReviewEl.hidden = false;
          filterRuleReviewEl.textContent = "Compiling…";
        }
        fetch("/rules/compile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: [{ role: "user", content: text }],
            run_id: runId,
            exemplar_ticket_id: exemplarId || null,
            prior_rule: filterBatchRule,
          }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!data.ok) {
              if (filterRuleReviewEl) {
                filterRuleReviewEl.textContent = (data.errors || []).join(" ") || "Compile failed.";
              }
              if (filterRulePreviewBtn) filterRulePreviewBtn.disabled = true;
              if (filterRuleConfirmBtn) filterRuleConfirmBtn.disabled = true;
              return;
            }
            filterBatchRule = data.rule;
            saveSession();
            if (filterRuleReviewEl) {
              filterRuleReviewEl.innerHTML =
                "<p>" + escHtml(data.rationale || "") + "</p><p><strong>Category:</strong> " +
                tierPath(data.rule.tier) + "</p>";
            }
            if (filterRulePreviewBtn) filterRulePreviewBtn.disabled = false;
            if (filterRuleConfirmBtn) filterRuleConfirmBtn.disabled = false;
          });
      });
    }

    if (filterRulePreviewBtn) {
      filterRulePreviewBtn.addEventListener("click", function () {
        if (!filterBatchRule) return;
        var ids = chunkTicketIds();
        if (filterRulePreviewEl) {
          filterRulePreviewEl.hidden = false;
          filterRulePreviewEl.innerHTML =
            '<p class="meta">Previewing… (tickets in current chunk: ' +
            ids.length +
            ')</p>';
        }
        fetch("/rules/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            rule: filterBatchRule,
            run_id: runId,
            ticket_ids: ids,
          }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!data.ok) {
              alert((data.errors || []).join("\n"));
              return;
            }
            if (filterRulePreviewEl) {
              filterRulePreviewEl.hidden = false;
              filterRulePreviewEl.innerHTML =
                "<table class=\"stats-table\"><tr><th>Ticket</th><th>Before</th><th>After</th><th></th></tr>" +
                (data.results || [])
                  .map(function (row) {
                    return (
                      "<tr data-ticket-id=\"" + escHtml(row.ticket_id || "") + "\">" +
                      "<td><code>#" + escHtml(row.ticket_id || "") + "</code><br><span class=\"meta\">" +
                      escHtml(row.subject || "") + "</span></td><td>" +
                      tierPath(row.before) + "</td><td>" + tierPath(row.after) + "</td>" +
                      "<td><button type=\"button\" class=\"btn btn-secondary btn-sm tbc-preview-detail-btn\">Details</button></td>" +
                      "</tr>" +
                      "<tr class=\"tbc-preview-detail-row\" data-ticket-id=\"" + escHtml(row.ticket_id || "") + "\" hidden>" +
                      "<td colspan=\"4\"><p class=\"meta\">Loading…</p></td></tr>"
                    );
                  })
                  .join("") +
                "</table>";

              filterRulePreviewEl.querySelectorAll(".tbc-preview-detail-btn").forEach(function (btn) {
                btn.addEventListener("click", function () {
                  var tr = btn.closest("tr");
                  var tid = tr ? tr.getAttribute("data-ticket-id") : "";
                  if (!tid) return;
                  var detailRow = filterRulePreviewEl.querySelector(
                    '.tbc-preview-detail-row[data-ticket-id="' + CSS.escape(tid) + '"]'
                  );
                  if (!detailRow) return;
                  if (!detailRow.hidden && detailRow.dataset.loaded === "1") {
                    detailRow.hidden = true;
                    return;
                  }
                  detailRow.hidden = false;
                  detailRow.querySelector("td").innerHTML = '<p class="meta">Loading…</p>';
                  fetch(
                    "/run/" +
                      encodeURIComponent(runId) +
                      "/ticket/" +
                      encodeURIComponent(tid)
                  )
                    .then(function (r) {
                      return r.json();
                    })
                    .then(function (payload) {
                      if (!payload || !payload.ok) {
                        throw new Error((payload && payload.detail) || "Detail failed.");
                      }
                      detailRow.querySelector("td").innerHTML = renderInlineTicketDetail(
                        payload.ticket,
                        runId
                      );
                      detailRow.dataset.loaded = "1";
                    })
                    .catch(function (err) {
                      detailRow.querySelector("td").innerHTML =
                        '<p class="meta" role="alert">' + escHtml(err.message || "Detail failed.") + "</p>";
                    });
                });
              });
            }
          })
          .catch(function (err) {
            if (filterRulePreviewEl) {
              filterRulePreviewEl.innerHTML =
                '<p class="meta" role="alert">Preview failed: ' +
                escHtml(err.message || String(err)) +
                "</p>";
            } else {
              alert("Preview failed: " + (err.message || String(err)));
            }
          });
      });
    }

    if (filterRuleConfirmBtn) {
      filterRuleConfirmBtn.addEventListener("click", function () {
        if (!filterBatchRule || !window.confirm("Confirm this batch rule to live config?")) return;
        var confirmDefaultLabel = filterRuleConfirmBtn.textContent;
        filterRuleConfirmBtn.disabled = true;
        filterRuleConfirmBtn.textContent = "Confirming…";
        filterRuleConfirmBtn.setAttribute("aria-busy", "true");
        fetch("/rules/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule: filterBatchRule }),
        })
          .then(function (r) {
            if (r.status === 403) throw new Error("Confirm not allowed for your role.");
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) {
              alert((data.errors || []).join("\n"));
              return;
            }
            filterBatchRule = null;
            saveSession();
            filterRuleConfirmBtn.textContent = "Reclassifying run…";
            return fetch("/run/" + encodeURIComponent(runId) + "/reclassify", { method: "POST" });
          })
          .then(function () {
            offset = 0;
            loadChunk();
          })
          .catch(function (err) {
            alert(err.message || "Confirm failed.");
          })
          .finally(function () {
            filterRuleConfirmBtn.textContent = confirmDefaultLabel;
            filterRuleConfirmBtn.removeAttribute("aria-busy");
            filterRuleConfirmBtn.disabled = false;
          });
      });
    }

    window.addEventListener("cs-tickets:apply-review-focus", function (ev) {
      var detail = (ev && ev.detail) || {};
      var f = detail.filter || detail.workbench_filter || {};
      if (detail.clear || f.active === false) {
        setFilterInputs({ q: "", tier1: "", categories: "", tbc_reason: "" });
        ruleTargetHint = "";
        offset = 0;
        saveSession();
        updateFilterDraftButton();
        loadChunk();
        if (typeof detail._markApplied === "function") detail._markApplied("tbc");
        return;
      }
      var cats = f.categories || [];
      if (!Array.isArray(cats)) cats = [];
      var tbcReason = f.tbc_reason || "";
      if (!(f.q || f.tier1 || cats.length || tbcReason || f.active)) return;
      setFilterInputs({
        q: f.q || "",
        tier1: f.tier1 || "",
        categories: cats.join(", "),
        tbc_reason: tbcReason,
      });
      ruleTargetHint = detail.rule_target || f.rule_target || "";
      offset = 0;
      saveSession();
      updateFilterDraftButton();
      loadChunk();
      if (typeof detail._markApplied === "function") detail._markApplied("tbc");
      if (app && app.scrollIntoView) {
        app.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    window.addEventListener("cs-tickets:clear-review-focus", function (ev) {
      var detail = (ev && ev.detail) || {};
      setFilterInputs({ q: "", tier1: "", categories: "", tbc_reason: "" });
      ruleTargetHint = "";
      offset = 0;
      saveSession();
      updateFilterDraftButton();
      loadChunk();
      if (typeof detail._markApplied === "function") detail._markApplied("tbc");
    });

    loadChunk();
  });
})();
