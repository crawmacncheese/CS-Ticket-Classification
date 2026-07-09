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

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("rules-app");
    // /rules list page uses this file too (no #rules-app).
    var nlInput = document.getElementById("rules-filter-nl");
    var nlApply = document.getElementById("rules-filter-nl-apply");
    var nlStatus = document.getElementById("rules-filter-nl-status");

    function showNlStatus(message, isError) {
      if (!nlStatus) return;
      nlStatus.hidden = false;
      nlStatus.textContent = message;
      nlStatus.classList.toggle("tbc-filter-nl-status--error", Boolean(isError));
    }

    function applyRulesFocus() {
      var text = ((nlInput && nlInput.value) || "").trim();
      if (!text) {
        showNlStatus("Enter a search focus phrase.", true);
        return;
      }
      if (nlApply) nlApply.disabled = true;
      showNlStatus("Parsing focus…", false);
      fetch("/rules/parse_focus", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (nlApply) nlApply.disabled = false;
          if (!data || !data.ok) {
            var msg = (data && data.errors && data.errors[0]) || "Could not parse focus.";
            showNlStatus(msg, true);
            return;
          }
          window.location.href = data.rules_url || "/rules";
        })
        .catch(function () {
          if (nlApply) nlApply.disabled = false;
          showNlStatus("Failed to parse focus.", true);
        });
    }

    if (nlApply) nlApply.addEventListener("click", applyRulesFocus);
    if (nlInput) {
      nlInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          applyRulesFocus();
        }
      });
    }

    if (!root) return;

    var chatLog = document.getElementById("rules-chat-log");
    var chatForm = document.getElementById("rules-chat-form");
    var chatInput = document.getElementById("rules-chat-input");
    var reviewPanel = document.getElementById("rules-review-panel");
    var reviewSummary = document.getElementById("rules-review-summary");
    var advancedJson = document.getElementById("rules-advanced-json");
    var confirmBtn = document.getElementById("rules-confirm-btn");
    var previewResults = document.getElementById("rules-preview-results");
    var uploadFileEl = document.getElementById("rules-upload-preview-file");
    var previewUploadBtn = document.getElementById("rules-preview-upload-btn");
    var runIdEl = document.getElementById("rules-run-id");
    var ticketIdEl = document.getElementById("rules-ticket-id");

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

    function appendChat(role, text) {
      var div = document.createElement("div");
      div.className = "rules-chat-msg rules-chat-msg-" + role;
      div.innerHTML = "<strong>" + (role === "user" ? "You" : "Assistant") + ":</strong> " + escHtml(text);
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    function renderReview(rule, rationale, warnings) {
      currentRule = rule;
      reviewPanel.hidden = false;
      var canConfirm = root.getAttribute("data-can-confirm") === "true";
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
      if (canConfirm && !confirmBtn.hasAttribute("hidden")) {
        confirmBtn.disabled = false;
      }
      previewResults.hidden = true;
    }

    chatForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = (chatInput.value || "").trim();
      if (!text) return;
      appendChat("user", text);
      messages.push({ role: "user", content: text });
      chatInput.value = "";
      confirmBtn.disabled = true;

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
            var err = (data.errors || []).join(" ") || "Compile failed.";
            appendChat("assistant", err);
            return;
          }
          appendChat("assistant", data.rationale || "Compiled.");
          renderReview(data.rule, data.rationale, data.warnings);
        })
        .catch(function (err) {
          appendChat("assistant", "Request failed: " + err);
        });
    });

    function renderUploadedPreviewTable(rows) {
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
        // Keep preview responsive; server will cap if needed.
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
            var rows = data.results || [];
            previewResults.innerHTML = renderUploadedPreviewTable(rows);
            previewResults.hidden = false;
            previewResults.querySelectorAll(".rules-preview-detail-btn").forEach(function (btn) {
              btn.addEventListener("click", function () {
                var tr = btn.closest("tr");
                var tid = tr ? tr.getAttribute("data-ticket-id") : "";
                if (!tid) return;
                var detailRow = previewResults.querySelector(
                  '.rules-preview-detail-row[data-ticket-id=\"' + CSS.escape(tid) + '\"]'
                );
                if (!detailRow) return;
                detailRow.hidden = !detailRow.hidden;
              });
            });
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
      if (!window.confirm("Confirm this rule to live config?")) return;
      var runId = runIdEl ? String(runIdEl.value || "").trim() : "";
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
          // If a run context is present, try to reclassify + redirect there.
          // If that run is stale/expired, fall back to the rules list success banner.
          if (runId) {
            fetch("/run/" + encodeURIComponent(runId) + "/reclassify", { method: "POST" })
              .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
              })
              .then(function (re) {
                if (!re || !re.ok) throw new Error("reclassify_failed");
                var q = "reclassified=1" +
                  "&tbc_before=" + encodeURIComponent(String(re.tbc_before)) +
                  "&tbc_after=" + encodeURIComponent(String(re.tbc_after));
                window.location.href = "/run/" + encodeURIComponent(runId) + "/tbc?" + q;
              })
              .catch(function () {
                window.location.href = "/rules?confirmed=1&version=" + encodeURIComponent(data.config_version_after || "");
              });
            return;
          }
          window.location.href = "/rules?confirmed=1&version=" + encodeURIComponent(data.config_version_after || "");
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
  });
})();
