/**
 * Collapse / expand Cursor-style Review chat side dock.
 * Collapsed by default; preference stored in localStorage.
 */
document.addEventListener("DOMContentLoaded", function () {
  var layout = document.getElementById("workbench-layout");
  var collapseBtn = document.getElementById("review-dock-collapse");
  var expandBtn = document.getElementById("review-dock-expand");
  if (!layout || !collapseBtn || !expandBtn) return;

  var STORAGE_KEY = "review-dock-collapsed";

  function readStoredCollapsed() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "true") return true;
      if (stored === "false") return false;
    } catch (_) {
      /* ignore */
    }
    return true;
  }

  function storeCollapsed(collapsed) {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "true" : "false");
    } catch (_) {
      /* ignore */
    }
  }

  function setCollapsed(collapsed, persist) {
    layout.setAttribute("data-dock-collapsed", collapsed ? "true" : "false");
    collapseBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    expandBtn.setAttribute("aria-expanded", collapsed ? "true" : "false");
    expandBtn.hidden = !collapsed;
    if (persist !== false) {
      storeCollapsed(collapsed);
    }
  }

  collapseBtn.addEventListener("click", function () {
    setCollapsed(true);
  });
  expandBtn.addEventListener("click", function () {
    setCollapsed(false);
  });

  // Deep links / CTA: button.review-dock-open-btn or a[href^="#review-dock"]
  document.querySelectorAll("[data-review-dock-open], a[href='#review-dock']").forEach(function (el) {
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      setCollapsed(false);
      var input = document.getElementById("rules-chat-input");
      if (input) input.focus();
    });
  });

  setCollapsed(readStoredCollapsed(), false);
});
