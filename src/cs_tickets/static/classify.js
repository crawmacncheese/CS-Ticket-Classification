document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-loading-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const submitter = event.submitter;
      const btn =
        submitter && submitter.matches("[data-loading-btn]")
          ? submitter
          : form.querySelector("[data-loading-btn]");
      if (!btn || btn.disabled) {
        return;
      }
      btn.disabled = true;
      btn.classList.add("btn-loading");
      const label = btn.getAttribute("data-loading-label") || "Processing…";
      btn.textContent = label;
    });
  });
});
