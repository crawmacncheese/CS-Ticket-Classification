(function () {
  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function tierPath(tup) {
    if (!tup || !tup.length) return "";
    return tup.slice(0, 4).map(escHtml).join(" → ");
  }

  function looksLikeCompile(text) {
    var t = String(text || "").toLowerCase();
    return (
      /\bmap\b/.test(t) ||
      /\bmark\s+as\b/.test(t) ||
      /\broute\s+to\b/.test(t) ||
      /\bupdate:\s*/.test(t) ||
      /\bcompile\b/.test(t) ||
      /\bdraft\s+(a\s+)?rule\b/.test(t) ||
      /\bpropose\s+(a\s+)?rule\b/.test(t) ||
      /\bnot\s+cancellation\b/.test(t) ||
      (t.includes('"') && /\bto\b/.test(t))
    );
  }

  // Explicit TBC *queue handoff* only — reason focuses ("show contested") go to profile.
  function looksLikeTbcHandoff(text) {
    var t = String(text || "").toLowerCase().trim();
    if (looksLikeCompile(t)) return false;
    if (/\b(tbc|manual\s*review)\s+queue\b/.test(t)) return true;
    if (/\b(show|list|open)\s+all\s+(tbc|manual\s*review)\b/.test(t)) return true;
    if (/\b(open|go\s+to)\b.{0,40}\b(tbc|manual\s*review)\b/.test(t)) return true;
    if (
      /\b(show|list|open)\b.{0,24}\b(tbc|manual\s*review)\b/.test(t) &&
      !/\b(contested|weak|threshold|rules|zero|blocked|allow[\s-]?list|lost\s*margin|reason)\b/.test(t)
    ) {
      return true;
    }
    return false;
  }

  // Reset workbench filters from chat ("clear focus", "show all", …).
  function looksLikeClearFocus(text) {
    var t = String(text || "").toLowerCase().trim();
    if (!t) return false;
    if (looksLikeCompile(t) || looksLikeTbcHandoff(t)) return false;
    if (/^(clear|reset|remove)\b/.test(t) && /\b(focus|filter|filters)\b/.test(t)) return true;
    if (/^clear\s*(it|this|all)?\s*$/.test(t)) return true;
    if (/^show\s+all(\s+tickets)?\s*$/.test(t)) return true;
    if (/^(remove|drop)\s+(the\s+)?(focus|filter)\b/.test(t)) return true;
    if (/\b(clear|reset)\s+(the\s+)?(table\s+)?(focus|filter)\b/.test(t)) return true;
    return false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("rules-app");
    // /rules list page uses this file too (filter bar + Review chat dock).

    if (!root) return;

    var chatLog = document.getElementById("rules-chat-log");
    var execLog = document.getElementById("rules-exec-log");
    var chatForm = document.getElementById("rules-chat-form");
    var chatInput = document.getElementById("rules-chat-input");
    var reviewPanel = document.getElementById("rules-review-panel");
    var reviewSummary = document.getElementById("rules-review-summary");
    var advancedJson = document.getElementById("rules-advanced-json");
    var confirmBtn = document.getElementById("rules-confirm-btn");
    var previewResults = document.getElementById("rules-preview-results");
    var uploadFileEl = document.getElementById("rules-upload-preview-file");
    var previewUploadBtn = document.getElementById("rules-preview-upload-btn");
    var uploadWrap = document.getElementById("rules-upload-preview-wrap");
    var runIdEl = document.getElementById("rules-run-id");
    var ticketIdEl = document.getElementById("rules-ticket-id");
    var orchBadge = document.getElementById("rules-orch-badge");
    var orchMode = root.getAttribute("data-orchestration") === "true";
    var previewOk = false;
    var activeFocusEl = null;
    var activeFocusNl = "";

    function ensureActiveFocusBar() {
      if (activeFocusEl || !chatLog || !chatLog.parentNode) return activeFocusEl;
      activeFocusEl = document.createElement("div");
      activeFocusEl.id = "rules-active-focus";
      activeFocusEl.className = "rules-active-focus meta";
      activeFocusEl.hidden = true;
      chatLog.parentNode.insertBefore(activeFocusEl, chatLog);
      return activeFocusEl;
    }

    function setActiveFocusLabel(focusNl) {
      activeFocusNl = (focusNl || "").trim();
      var el = ensureActiveFocusBar();
      if (!el) return;
      if (!activeFocusNl) {
        el.hidden = true;
        el.innerHTML = "";
        return;
      }
      el.hidden = false;
      el.innerHTML =
        '<span><strong>Active focus:</strong> ' +
        escHtml(activeFocusNl) +
        "</span> " +
        '<button type="button" class="btn btn-secondary btn-sm" id="rules-clear-focus-btn">Clear</button>';
      var btn = document.getElementById("rules-clear-focus-btn");
      if (btn) {
        btn.addEventListener("click", function () {
          doClearFocus("clear focus");
        });
      }
    }

    function clearWorkbenchFocus() {
      var clearedBy = [];
      var detail = {
        clear: true,
        filter: { q: "", tier1: "", categories: [], tbc_reason: "", active: false },
        _markApplied: function (who) {
          if (who && clearedBy.indexOf(who) === -1) clearedBy.push(who);
        },
      };
      window.dispatchEvent(
        new CustomEvent("cs-tickets:clear-review-focus", { detail: detail })
      );
      // Also send empty apply so older listeners can react if needed
      window.dispatchEvent(
        new CustomEvent("cs-tickets:apply-review-focus", { detail: detail })
      );
      setActiveFocusLabel("");
      return clearedBy;
    }

    function doClearFocus(text) {
      setMode("Audit");
      var clearedBy = clearWorkbenchFocus();
      appendChat(
        "assistant",
        clearedBy.length
          ? "Cleared the review table focus."
          : "Cleared active focus (no table filter was attached)."
      );
      appendExec("CLEAR_FOCUS", text.slice(0, 80) || "ok");
      var rulesList = document.querySelector(".rules-list-table");
      if (
        rulesList &&
        window.location.pathname === "/rules" &&
        window.location.search
      ) {
        window.location.href = "/rules";
      }
    }

    try {
      var storedPrefill = sessionStorage.getItem("cs_tickets_rule_prefill");
      if (storedPrefill && chatInput && !chatInput.value.trim()) {
        chatInput.value = storedPrefill;
        sessionStorage.removeItem("cs_tickets_rule_prefill");
      }
    } catch (e) {
      /* ignore */
    }

    // Auto-fill run context for preview when editor opened from rules list.
    try {
      if (runIdEl && !String(runIdEl.value || "").trim()) {
        var lastRun = sessionStorage.getItem("cs_tickets_last_run_id");
        if (lastRun) runIdEl.value = lastRun;
      }
    } catch (e) {
      /* ignore */
    }

    var messages = [];
    var currentRule = null;
    var initialEl = document.getElementById("rules-initial-rule");
    if (initialEl && initialEl.textContent) {
      try {
        var parsed = JSON.parse(initialEl.textContent);
        if (parsed && parsed.id) currentRule = parsed;
      } catch (e) {
        /* ignore */
      }
    }

    function setMode(mode) {
      if (!orchBadge) return;
      orchBadge.textContent = mode;
      orchBadge.setAttribute("data-mode", String(mode).toLowerCase());
    }

    function setPreviewOk(ok) {
      previewOk = Boolean(ok);
      root.setAttribute("data-preview-ok", previewOk ? "true" : "false");
      syncConfirmEnabled();
    }

    function syncConfirmEnabled() {
      var canConfirm = root.getAttribute("data-can-confirm") === "true";
      if (!canConfirm || confirmBtn.hasAttribute("hidden")) {
        confirmBtn.disabled = true;
        return;
      }
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      // With a run: require successful preview this session (D.1 parity).
      if (runId && orchMode) {
        confirmBtn.disabled = !(currentRule && previewOk);
      } else {
        confirmBtn.disabled = !currentRule;
      }
    }

    function appendExec(action, result) {
      if (!execLog) return;
      execLog.hidden = false;
      var line = document.createElement("div");
      line.textContent = action + ": " + result;
      execLog.appendChild(line);
    }

    function appendChat(role, text) {
      var div = document.createElement("div");
      div.className = "rules-chat-msg rules-chat-msg-" + role;
      div.innerHTML = "<strong>" + (role === "user" ? "You" : "Assistant") + ":</strong> " + escHtml(text);
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    function appendCard(card) {
      var wrap = document.createElement("div");
      wrap.className = "rules-chat-card rules-chat-card-" + escHtml(card.type || "generic");
      if (card.type === "profile_summary") {
        var parseBlock = card.parse_summary
          ? "<pre class=\"rules-parse-summary meta\">" + escHtml(card.parse_summary) + "</pre>"
          : "";
        wrap.innerHTML =
          "<div class=\"rules-chat-card-title\">Profile</div>" +
          "<p>" +
          escHtml(
            "You said “" +
              (card.focus_nl || "") +
              "”: " +
              String(card.slice_count || 0) +
              " in slice, " +
              String(card.tbc_count || 0) +
              " TBC in run."
          ) +
          "</p>" +
          parseBlock;
      } else if (card.type === "sweep") {
        var samples = (card.sample_ids || []).slice(0, 5).map(escHtml).join(", ");
        var phraseAttr = escHtml(card.compile_phrase || "");
        wrap.innerHTML =
          "<div class=\"rules-chat-card-title\">Sweep: " +
          escHtml(card.sweep_id || "") +
          "</div>" +
          "<p><strong>" +
          escHtml(String(card.match_count || 0)) +
          "</strong> match(es)" +
          (samples ? " — sample ids: " + samples : "") +
          "</p>" +
          (card.compile_phrase
            ? "<p class=\"meta\">" + escHtml(card.compile_phrase) + "</p>" +
              "<button type=\"button\" class=\"btn btn-secondary btn-sm rules-draft-from-sweep\" data-phrase=\"" +
              phraseAttr +
              "\">Draft from this</button>"
            : "");
      } else if (card.type === "clarify") {
        wrap.innerHTML =
          "<div class=\"rules-chat-card-title\">Clarify</div>" +
          "<p>" +
          escHtml(card.message || "") +
          "</p>";
      } else if (card.type === "tbc_handoff") {
        wrap.innerHTML =
          "<div class=\"rules-chat-card-title\">Manual review (TBC)</div>" +
          "<p>Review uncategorized tickets on the TBC queue for this run.</p>" +
          '<a class="btn btn-primary btn-sm" href="' +
          escHtml(card.href || "#") +
          '">Open TBC queue</a>';
      } else if (card.type === "preview") {
        wrap.innerHTML =
          "<div class=\"rules-chat-card-title\">Preview</div>" +
          "<p>" +
          escHtml(card.headline || "Preview complete.") +
          "</p>";
      } else {
        wrap.innerHTML = "<p>" + escHtml(JSON.stringify(card)) + "</p>";
      }
      chatLog.appendChild(wrap);
      chatLog.scrollTop = chatLog.scrollHeight;

      wrap.querySelectorAll(".rules-draft-from-sweep").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var phrase = btn.getAttribute("data-phrase") || "";
          if (!phrase) return;
          chatInput.value = phrase;
          doCompile(phrase);
        });
      });
    }

    function renderPreviewTable(rows) {
      return (
        "<table class=\"stats-table\"><thead><tr><th>Ticket</th><th>Before</th><th>After</th><th></th></tr></thead><tbody>" +
        rows
          .map(function (row) {
            var tid = row.ticket_id || "";
            return (
              "<tr data-ticket-id=\"" +
              escHtml(tid) +
              "\"><td>" +
              escHtml(tid) +
              "<br><span class=\"meta\">" +
              escHtml(row.subject || "") +
              "</span></td><td>" +
              tierPath(row.before) +
              "</td><td>" +
              tierPath(row.after) +
              "</td><td><button type=\"button\" class=\"btn btn-secondary btn-sm rules-preview-detail-btn\">Details</button></td></tr>" +
              "<tr class=\"rules-preview-detail-row\" data-ticket-id=\"" +
              escHtml(tid) +
              "\" hidden><td colspan=\"4\">" +
              "<dl class=\"ticket-preview-detail-dl\">" +
              "<dt>Requester</dt><dd>" +
              escHtml(row.requester_email || "") +
              "</dd>" +
              "<dt>Tags</dt><dd>" +
              escHtml(row.tags || "") +
              "</dd>" +
              "<dt>Description</dt><dd class=\"ticket-preview-description\">" +
              escHtml(row.description || "") +
              "</dd>" +
              "</dl></td></tr>"
            );
          })
          .join("") +
        "</tbody></table>"
      );
    }

    function wirePreviewDetailButtons(container) {
      container.querySelectorAll(".rules-preview-detail-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var tr = btn.closest("tr");
          var tid = tr ? tr.getAttribute("data-ticket-id") : "";
          if (!tid) return;
          var detailRow = container.querySelector(
            '.rules-preview-detail-row[data-ticket-id="' + CSS.escape(tid) + '"]'
          );
          if (!detailRow) return;
          detailRow.hidden = !detailRow.hidden;
        });
      });
    }

    function showPreviewResults(data) {
      var rows = data.results || [];
      var summary = data.summary || {};
      var headline = summary.headline
        ? "<p class=\"run-summary\" role=\"status\">" + escHtml(summary.headline) + "</p>"
        : "";
      if (summary.risk && summary.risk !== "ok") {
        headline +=
          "<p class=\"meta\">Preview risk: <code>" + escHtml(summary.risk) + "</code></p>";
      }
      previewResults.innerHTML = headline + renderPreviewTable(rows);
      previewResults.hidden = false;
      wirePreviewDetailButtons(previewResults);
      appendCard({ type: "preview", headline: summary.headline || "Preview complete." });
      appendExec("PREVIEW", summary.headline || "ok");
      setPreviewOk(true);
      if (uploadWrap && String(runIdEl && runIdEl.value || "").trim()) {
        uploadWrap.hidden = true;
      }
    }

    function previewOnRun(rule) {
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      if (!runId || !rule) return Promise.resolve(null);
      return fetch("/rules/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rule: rule, run_id: runId, limit: 25 }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok) {
            appendChat("assistant", (data.errors || []).join(" ") || "Run preview failed.");
            setPreviewOk(false);
            return data;
          }
          showPreviewResults(data);
          return data;
        })
        .catch(function (err) {
          appendChat("assistant", "Preview failed: " + err);
          setPreviewOk(false);
          return null;
        });
    }

    function renderReview(rule, rationale, warnings) {
      currentRule = rule;
      setMode("Config");
      setPreviewOk(false);
      reviewPanel.hidden = false;
      var warn =
        warnings && warnings.length
          ? "<ul class=\"rules-warnings\">" + warnings.map(function (w) { return "<li>" + escHtml(w) + "</li>"; }).join("") + "</ul>"
          : "";
      reviewSummary.innerHTML =
        "<p>" + escHtml(rationale || "") + "</p>" +
        "<dl class=\"rules-review-dl\">" +
        "<dt>Category</dt><dd>" + tierPath(rule.tier) + "</dd>" +
        "<dt>Rule id</dt><dd><code>" + escHtml(rule.id) + "</code></dd>" +
        "<dt>Override</dt><dd>" + (rule.override ? "yes — always when matched" : "no") + "</dd>" +
        "<dt>Weight</dt><dd>" + escHtml(String(rule.weight)) + "</dd>" +
        "</dl>" + warn;
      advancedJson.value = JSON.stringify(rule, null, 2);
      if (uploadWrap) uploadWrap.hidden = false;
      syncConfirmEnabled();
    }

    function doOpenTbc(text) {
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      if (!runId) {
        appendChat(
          "assistant",
          "Add a Run ID to open the manual-review (TBC) queue. " +
            "Or open a run’s Results page and use Review chat from there."
        );
        appendCard({
          type: "clarify",
          message:
            "TBC review needs a run. Set Run ID above, or start from Results → Review chat.",
        });
        return;
      }
      var href = "/run/" + encodeURIComponent(runId) + "/tbc";
      setMode("Audit");
      appendChat(
        "assistant",
        "Opening the manual-review (TBC) queue for this run. " +
          "Use that page to walk tickets, see why they are TBC, and apply suggestions. " +
          "Come back here only when you want to draft a routing rule."
      );
      appendCard({
        type: "tbc_handoff",
        message: text,
        href: href,
        run_id: runId,
      });
      appendExec("TBC_HANDOFF", href);
    }

    function doClarifyIntent(text) {
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      appendChat(
        "assistant",
        "I’m not sure what you need. This chat can: (1) profile a focus like “review B2C” or “show contested”, " +
          "(2) open the TBC queue (“show all TBC”), or (3) draft a rule when you use a compile phrase " +
          "(e.g. Map “…” to System Report)."
      );
      var msg =
        "Try one of: “review B2C”, “show contested”, “show all TBC”, or a Map/compile phrase.";
      if (runId) {
        msg += " TBC queue: /run/" + runId + "/tbc";
      }
      appendCard({ type: "clarify", message: msg });
      appendExec("ASK_CLARIFY", text.slice(0, 80));
    }

    function doProfile(text) {
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      if (!runId) {
        appendChat("assistant", "Add a Run ID to profile this focus against classified tickets.");
        return;
      }
      setMode("Audit");
      fetch("/run/" + encodeURIComponent(runId) + "/review_chat/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok && !(data.cards && data.cards.length)) {
            appendChat("assistant", (data.errors || []).join(" ") || "Profile failed.");
            appendExec("ASK_CLARIFY", text.slice(0, 80));
            return;
          }
          if (data.headline) {
            appendChat("assistant", data.headline);
            appendExec("PROFILE", data.headline);
          }
          (data.cards || []).forEach(appendCard);
          if (!data.ok || !data.workbench_filter) {
            appendExec("ASK_CLARIFY", text.slice(0, 80));
            return;
          }
          syncWorkbenchFocus(data);
        })
        .catch(function (err) {
          appendChat("assistant", "Profile failed: " + err);
        });
    }

    function syncWorkbenchFocus(data) {
      var profile = data.profile || {};
      if (profile.parse_ok === false) return;
      var filt =
        data.workbench_filter ||
        (data.cards || []).reduce(function (acc, card) {
          return acc || (card && card.type === "profile_summary" && card.workbench_filter);
        }, null) ||
        profile.audit_filter ||
        {};
      var cats = filt.categories || [];
      if (!Array.isArray(cats)) cats = [];
      var tbcReason = filt.tbc_reason || profile.tbc_reason || "";
      var active = !!(filt.active || filt.q || filt.tier1 || cats.length || tbcReason);
      if (!active) return;

      var appliedBy = [];
      var detail = {
        filter: {
          q: filt.q || "",
          tier1: filt.tier1 || "",
          categories: cats,
          tbc_reason: tbcReason,
          active: true,
        },
        rule_target: filt.rule_target || profile.rule_target || "",
        focus_nl: profile.focus_nl || "",
        _markApplied: function (who) {
          if (who && appliedBy.indexOf(who) === -1) appliedBy.push(who);
        },
      };

      var tbcApp = document.getElementById("tbc-queue-app");
      var auditApp = document.getElementById("category-audit-app");
      var previewRoot =
        document.querySelector(".ticket-preview-root") ||
        document.getElementById("ticket-preview");
      var rulesList = document.querySelector(".rules-list-table");

      if (auditApp && !tbcApp) {
        // Category audit is server-rendered; remember a one-line note across reload.
        try {
          sessionStorage.setItem(
            "cs-tickets:focus-applied",
            JSON.stringify({
              focus_nl: detail.focus_nl,
              tier1: detail.filter.tier1,
              categories: detail.filter.categories,
              tbc_reason: detail.filter.tbc_reason,
            })
          );
        } catch (_e) {
          /* ignore */
        }
      }

      window.dispatchEvent(
        new CustomEvent("cs-tickets:apply-review-focus", { detail: detail })
      );

      if (appliedBy.length) {
        setActiveFocusLabel(detail.focus_nl || detail.filter.tier1 || tbcReason || "focus");
        var parseHint =
          data.parse_summary ||
          (data.cards || []).reduce(function (acc, card) {
            return acc || (card && card.type === "profile_summary" && card.parse_summary);
          }, null) ||
          "";
        appendChat(
          "assistant",
          parseHint
            ? "Updated the review table.\n" + parseHint
            : "Updated the review table to this focus."
        );
        appendExec(
          "APPLY_FOCUS",
          (detail.focus_nl || detail.filter.tier1 || tbcReason || "ok") +
            " [" +
            appliedBy.join(",") +
            "]"
        );
        if (parseHint) {
          appendExec("PARSED_AS", parseHint.replace(/\n/g, " | ").slice(0, 200));
        }
      } else if (auditApp) {
        setActiveFocusLabel(detail.focus_nl || detail.filter.tier1 || tbcReason || "focus");
        var auditParse =
          data.parse_summary ||
          (data.cards || []).reduce(function (acc, card) {
            return acc || (card && card.type === "profile_summary" && card.parse_summary);
          }, null) ||
          "";
        appendChat(
          "assistant",
          auditParse
            ? "Refreshing the audit table.\n" + auditParse
            : "Refreshing the audit table with this focus…"
        );
        appendExec("APPLY_FOCUS", detail.focus_nl || detail.filter.tier1 || "ok");
      } else if (rulesList) {
        setActiveFocusLabel(detail.focus_nl || detail.filter.tier1 || tbcReason || "focus");
        var rulesParse =
          data.parse_summary ||
          (data.cards || []).reduce(function (acc, card) {
            return acc || (card && card.type === "profile_summary" && card.parse_summary);
          }, null) ||
          "";
        appendChat(
          "assistant",
          rulesParse
            ? "Filtering the rules list.\n" + rulesParse
            : "Filtering the rules list to this focus…"
        );
        appendExec("APPLY_FOCUS", detail.focus_nl || detail.filter.tier1 || "ok");
        var qParts = [];
        if (detail.filter.q) qParts.push(String(detail.filter.q));
        (detail.filter.categories || []).forEach(function (c) {
          if (c) qParts.push(String(c));
        });
        var params = new URLSearchParams();
        var qJoined = qParts.join(" ").trim();
        if (qJoined) params.set("q", qJoined);
        if (detail.filter.tier1) params.set("tier1", detail.filter.tier1);
        var qs = params.toString();
        window.location.href = qs ? "/rules?" + qs : "/rules";
      } else if (tbcApp || previewRoot) {
        appendChat(
          "assistant",
          "Parsed this focus, but the table did not pick it up. Try refreshing, or open the TBC queue / results preview."
        );
        appendExec("APPLY_FOCUS_MISSED", detail.focus_nl || tbcReason || "ok");
      }
    }

    function restoreFocusAppliedNote() {
      var raw;
      try {
        raw = sessionStorage.getItem("cs-tickets:focus-applied");
        if (!raw) return;
        sessionStorage.removeItem("cs-tickets:focus-applied");
      } catch (_e) {
        return;
      }
      var info;
      try {
        info = JSON.parse(raw);
      } catch (_e2) {
        return;
      }
      var parts = [];
      if (info.tier1) parts.push(info.tier1);
      if (info.categories && info.categories.length) parts.push(info.categories.join(", "));
      if (info.tbc_reason) parts.push(info.tbc_reason);
      var label = parts.length ? parts.join(" · ") : info.focus_nl || "focus";
      appendChat("assistant", "Audit table filtered to: " + label + ".");
    }

    function doCompile(text) {
      messages.push({ role: "user", content: text });
      confirmBtn.disabled = true;
      setPreviewOk(false);

      var body = {
        messages: messages,
        prior_rule: currentRule,
      };
      if (runIdEl) body.run_id = runIdEl.value;
      if (ticketIdEl) body.exemplar_ticket_id = ticketIdEl.value;

      fetch("/rules/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok) {
            var clarify = data.clarify_message || "";
            var err = clarify || (data.errors || []).join(" ") || "Compile failed.";
            appendChat("assistant", err);
            return;
          }
          var msg = data.rationale || "Compiled.";
          if (data.warnings && data.warnings.length) {
            msg += "\n\nWarnings: " + data.warnings.join(" ");
          }
          if (data.risk && data.risk !== "ok") {
            msg += "\n\nRisk: " + data.risk;
          }
          appendChat("assistant", msg);
          appendExec("COMPILE", data.rule && data.rule.id ? data.rule.id : "ok");
          renderReview(data.rule, data.rationale, data.warnings);
          var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
          if (runId) {
            return previewOnRun(data.rule);
          }
          syncConfirmEnabled();
        })
        .catch(function (err) {
          appendChat("assistant", "Request failed: " + err);
        });
    }

    chatForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = (chatInput.value || "").trim();
      if (!text) return;
      appendChat("user", text);
      chatInput.value = "";

      // Intent: compile / refine stay gated locally.
      // TBC queue handoff stays deterministic.
      // Clear focus is local + workbench event.
      // Everything else → server focus parse (LLM-first when configured + validated).
      if (looksLikeCompile(text)) {
        doCompile(text);
        return;
      }
      if (looksLikeClearFocus(text)) {
        doClearFocus(text);
        return;
      }
      if (looksLikeTbcHandoff(text)) {
        doOpenTbc(text);
        return;
      }
      if (currentRule && /\b(refine|change|update|fix|instead|weight|override)\b/i.test(text)) {
        doCompile(text);
        return;
      }
      doProfile(text);
    });

    if (previewUploadBtn) {
      if (uploadFileEl) {
        uploadFileEl.addEventListener("change", function () {
          previewUploadBtn.disabled = !uploadFileEl.files || uploadFileEl.files.length === 0;
        });
      }
      previewUploadBtn.disabled = true;

      previewUploadBtn.addEventListener("click", function () {
        if (!uploadFileEl || !uploadFileEl.files || !uploadFileEl.files[0]) {
          alert("Choose an export file first.");
          return;
        }
        if (!advancedJson || !(advancedJson.value || "").trim()) {
          alert("Compile a rule first, then preview on uploaded file.");
          return;
        }
        var rule;
        try {
          rule = JSON.parse(advancedJson.value);
        } catch (e) {
          alert("Invalid JSON in advanced edit.");
          return;
        }
        var file = uploadFileEl.files[0];
        var form = new FormData();
        form.append("export", file, file.name);
        form.append("rule", JSON.stringify(rule));
        form.append("limit", "200");

        previewResults.hidden = true;
        fetch("/rules/preview_upload", {
          method: "POST",
          body: form,
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) {
              alert((data.errors || []).join("\n") || "Upload preview failed.");
              return;
            }
            showPreviewResults(data);
          })
          .catch(function (err) {
            alert(err.message || "Upload preview failed.");
          });
      });
    }

    confirmBtn.addEventListener("click", function () {
      if (confirmBtn.hidden || confirmBtn.disabled) return;
      var rule;
      try {
        rule = JSON.parse(advancedJson.value);
      } catch (e) {
        alert("Invalid JSON.");
        return;
      }
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
      if (orchMode && runId && !previewOk) {
        alert("Preview this rule on the run before Confirm.");
        return;
      }
      if (!window.confirm("Confirm this rule to live config?")) return;
      fetch("/rules/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rule: rule }),
      })
        .then(function (r) {
          if (r.status === 403) {
            return r.json().then(function (d) {
              throw new Error(d.detail || "Confirm not allowed.");
            });
          }
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) {
            alert((data.errors || []).join("\n"));
            return;
          }
          appendExec(
            "CONFIRM",
            "config_version_after=" + String(data.config_version_after || "")
          );
          if (runId) {
            fetch("/run/" + encodeURIComponent(runId) + "/reclassify", { method: "POST" })
              .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
              })
              .then(function (re) {
                if (!re || !re.ok) throw new Error("reclassify_failed");
                var q =
                  "reclassified=1" +
                  "&tbc_before=" +
                  encodeURIComponent(String(re.tbc_before)) +
                  "&tbc_after=" +
                  encodeURIComponent(String(re.tbc_after));
                window.location.href = "/run/" + encodeURIComponent(runId) + "/tbc?" + q;
              })
              .catch(function () {
                window.location.href =
                  "/rules?confirmed=1&version=" +
                  encodeURIComponent(data.config_version_after || "");
              });
            return;
          }
          window.location.href =
            "/rules?confirmed=1&version=" +
            encodeURIComponent(data.config_version_after || "");
        })
        .catch(function (err) {
          alert(err.message || "Confirm failed.");
        });
    });

    document.querySelectorAll("form.rules-inline-form").forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        var lead = form.getAttribute("data-confirm-lead") || "Disable this rule?";
        if (!window.confirm(lead)) ev.preventDefault();
      });
    });

    if (orchMode && currentRule) setMode("Config");
    restoreFocusAppliedNote();
  });
})();
