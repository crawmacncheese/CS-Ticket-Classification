document.addEventListener("DOMContentLoaded", () => {
  const checkboxes = document.querySelectorAll(".tuple-checkbox");
  const commitBtn = document.getElementById("training-commit-btn");
  const previewBtn = document.getElementById("training-preview-btn");
  const selectAll = document.getElementById("select-all-tuples");
  const selectNone = document.getElementById("select-none-tuples");
  const previewForm = document.getElementById("training-preview-form");
  const previewSelected = document.getElementById("training-preview-selected-tuples");

  function selectedCheckboxes() {
    return [...document.querySelectorAll(".tuple-checkbox:checked")];
  }

  function updateActionButtons() {
    const hasSelection = selectedCheckboxes().length > 0;
    if (commitBtn) {
      commitBtn.disabled = !hasSelection;
    }
    if (previewBtn) {
      previewBtn.disabled = !hasSelection;
    }
  }

  checkboxes.forEach((cb) => {
    cb.addEventListener("change", updateActionButtons);
  });

  if (selectAll) {
    selectAll.addEventListener("click", () => {
      checkboxes.forEach((cb) => {
        cb.checked = true;
      });
      updateActionButtons();
    });
  }

  if (selectNone) {
    selectNone.addEventListener("click", () => {
      checkboxes.forEach((cb) => {
        cb.checked = false;
      });
      updateActionButtons();
    });
  }

  if (previewForm && previewSelected) {
    previewForm.addEventListener("submit", (event) => {
      previewSelected.innerHTML = "";
      const selected = selectedCheckboxes();
      if (selected.length === 0) {
        event.preventDefault();
        return;
      }
      selected.forEach((cb) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "selected_tuple";
        input.value = cb.value;
        previewSelected.appendChild(input);
      });
    });
  }

  updateActionButtons();

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
