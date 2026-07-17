/**
 * Collapse / expand Cursor-style Review chat side dock.
 * Collapsed by default; width draggable on the inner edge; prefs in localStorage.
 */
document.addEventListener("DOMContentLoaded", function () {
  var layout = document.getElementById("workbench-layout");
  var collapseBtn = document.getElementById("review-dock-collapse");
  var expandBtn = document.getElementById("review-dock-expand");
  var resizeHandle = document.getElementById("review-dock-resize");
  if (!layout || !collapseBtn || !expandBtn) return;

  var COLLAPSED_KEY = "review-dock-collapsed";
  var WIDTH_KEY = "review-dock-width";
  var DEFAULT_WIDTH = 264;
  var MIN_WIDTH = 240;
  var MAX_WIDTH = 720;
  var KEYBOARD_STEP = 16;

  function defaultWidthForViewport() {
    if (window.innerWidth <= 640) return 216;
    if (window.innerWidth <= 900) return 240;
    return DEFAULT_WIDTH;
  }

  function readStoredCollapsed() {
    try {
      var stored = localStorage.getItem(COLLAPSED_KEY);
      if (stored === "true") return true;
      if (stored === "false") return false;
    } catch (_) {
      /* ignore */
    }
    return true;
  }

  function storeCollapsed(collapsed) {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "true" : "false");
    } catch (_) {
      /* ignore */
    }
  }

  function readStoredWidth() {
    try {
      var n = parseInt(localStorage.getItem(WIDTH_KEY), 10);
      if (!isNaN(n) && n >= MIN_WIDTH && n <= MAX_WIDTH) return n;
    } catch (_) {
      /* ignore */
    }
    return defaultWidthForViewport();
  }

  function storeWidth(px) {
    try {
      localStorage.setItem(WIDTH_KEY, String(Math.round(px)));
    } catch (_) {
      /* ignore */
    }
  }

  function currentDockWidth() {
    var dock = document.getElementById("review-dock");
    return dock ? dock.getBoundingClientRect().width : DEFAULT_WIDTH;
  }

  function setDockWidth(px, persist) {
    var next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, px));
    layout.style.setProperty("--review-dock-width", next + "px");
    layout.setAttribute("data-dock-custom-width", "true");
    if (persist !== false) {
      storeWidth(next);
    }
    return next;
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

  setDockWidth(readStoredWidth(), false);

  collapseBtn.addEventListener("click", function () {
    setCollapsed(true);
  });
  expandBtn.addEventListener("click", function () {
    setCollapsed(false);
  });

  document.querySelectorAll("[data-review-dock-open], a[href='#review-dock']").forEach(function (el) {
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      setCollapsed(false);
      var input = document.getElementById("rules-chat-input");
      if (input) input.focus();
    });
  });

  setCollapsed(readStoredCollapsed(), false);

  document.querySelectorAll(".review-dock-popout").forEach(function (a) {
    var href = a.getAttribute("href") || "";
    if (!href.startsWith("/run/") || href.indexOf("/review_chat") === -1) return;
    var here = window.location.pathname + window.location.search;
    var sep = href.indexOf("?") >= 0 ? "&" : "?";
    a.setAttribute(
      "href",
      href + sep + "return_to=" + encodeURIComponent(here)
    );
    a.addEventListener("click", function () {
      if (typeof window.persistReviewChatSession === "function") {
        window.persistReviewChatSession();
      }
    });
  });

  window.addEventListener("cs-tickets:propose-rule-from-ticket", function () {
    setCollapsed(false);
    var input = document.getElementById("rules-chat-input");
    if (input) input.focus();
  });

  if (!resizeHandle) return;

  var dragging = false;
  var startX = 0;
  var startWidth = 0;

  function endDrag() {
    if (!dragging) return;
    dragging = false;
    layout.removeAttribute("data-dock-resizing");
    setDockWidth(currentDockWidth(), true);
    document.body.style.cursor = "";
  }

  function onPointerMove(ev) {
    if (!dragging) return;
    var delta = startX - ev.clientX;
    setDockWidth(startWidth + delta, false);
  }

  resizeHandle.addEventListener("pointerdown", function (ev) {
    if (layout.getAttribute("data-dock-collapsed") === "true") return;
    if (ev.button !== 0 && ev.pointerType === "mouse") return;
    ev.preventDefault();
    dragging = true;
    startX = ev.clientX;
    startWidth = currentDockWidth();
    layout.setAttribute("data-dock-resizing", "true");
    document.body.style.cursor = "col-resize";
    try {
      resizeHandle.setPointerCapture(ev.pointerId);
    } catch (_) {
      /* ignore */
    }
  });

  resizeHandle.addEventListener("pointermove", onPointerMove);
  resizeHandle.addEventListener("pointerup", endDrag);
  resizeHandle.addEventListener("pointercancel", endDrag);

  resizeHandle.addEventListener("keydown", function (ev) {
    if (layout.getAttribute("data-dock-collapsed") === "true") return;
    var w = currentDockWidth();
    if (ev.key === "ArrowLeft") {
      setDockWidth(w + KEYBOARD_STEP, true);
      ev.preventDefault();
    } else if (ev.key === "ArrowRight") {
      setDockWidth(w - KEYBOARD_STEP, true);
      ev.preventDefault();
    }
  });
});
