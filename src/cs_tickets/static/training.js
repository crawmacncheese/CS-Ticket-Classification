document.addEventListener("DOMContentLoaded", () => {
  const checkboxes = document.querySelectorAll(".tuple-checkbox");
  const commitBtn = document.getElementById("training-commit-btn");
  const previewBtn = document.getElementById("training-preview-btn");
  const selectAll = document.getElementById("select-all-tuples");
  const selectNone = document.getElementById("select-none-tuples");
  const deselectNoOp = document.getElementById("deselect-no-op-tuples");
  const previewForm = document.getElementById("training-preview-form");
  const previewSelected = document.getElementById("training-preview-selected-tuples");
  const mainForm = document.getElementById("training-main-form");
  const showDetails = document.getElementById("show-changed-details");

  function selectedCheckboxes() {
    return [...document.querySelectorAll(".tuple-checkbox:checked")];
  }

  function updateLearnPreviewBtn() {
    const btn = document.getElementById("learn-preview-btn");
    if (!btn) return;
    const any =
      document.querySelectorAll("#learn-confirm-form input.learn-row-chk:checked").length > 0;
    btn.disabled = !any;
  }

  function updateActionButtons() {
    const hasSelection = selectedCheckboxes().length > 0;
    if (commitBtn) {
      commitBtn.disabled = !hasSelection;
    }
    if (previewBtn) {
      previewBtn.disabled = !hasSelection;
    }
    updateLearnPreviewBtn();
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

  if (deselectNoOp) {
    deselectNoOp.addEventListener("click", () => {
      document.querySelectorAll("tr.tuple-row--no-op .tuple-checkbox").forEach((cb) => {
        cb.checked = false;
      });
      updateActionButtons();
    });
  }

  document.querySelectorAll(".learn-deselect-no-op-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.getAttribute("data-checkbox-name");
      if (!name) {
        return;
      }
      document
        .querySelectorAll(`tr.learn-row--no-op input.learn-row-chk[name="${name}"]`)
        .forEach((cb) => {
          cb.checked = false;
        });
      updateActionButtons();
    });
  });

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

  if (mainForm && commitBtn) {
    mainForm.addEventListener("submit", (event) => {
      const submitter = event.submitter;
      if (!submitter || submitter.id !== "training-commit-btn") {
        return;
      }
      const n = selectedCheckboxes().length;
      const noun = n === 1 ? "category" : "categories";
      const message =
        `Save ${n} ${noun} to the reference workbook? ` +
        "This updates files in doc/ until you undo.";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  if (showDetails) {
    const table = document.querySelector(".training-changed-table");
    const setExpanded = (expanded) => {
      if (table) {
        table.classList.toggle("training-changed-table--expanded", expanded);
      }
    };
    setExpanded(showDetails.checked);
    showDetails.addEventListener("change", () => {
      setExpanded(showDetails.checked);
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
