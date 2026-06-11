# Allowlist Training Fixes — Implementation Plan

> **For implementer:** When you execute this plan, document your steps, process, and final design decisions in a separate markdown file (e.g. `docs/plans/2026-06-08-allowlist-training-fixes-notes.md`) so the requester can review rationale, catch bugs early, and understand the code. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** Fix four bugs in the allowlist Training flow: tighten file-format restrictions on upload and preview controls, split B2B and B2C TBC metrics in preview, and parse analyst classified workbooks without requiring the reference sheet name `SCMP_Tickets_Master_Categorized`.

**Architecture:** Add upload-specific sheet resolution in `taxonomy.py` (new functions; leave reference-workbook loading unchanged). Extend `allowlist_compare.py` with segment-keyed TBC counters. Tighten `accept` attributes and add server-side extension checks in `portal_app.py`, `portal_training.py`, and `training.js`.

**Tech stack:** Python 3.11, FastAPI, openpyxl, pytest.

**Source brief:** [`errornotes.md`](../../errornotes.md)

---

## Context

### Bugs to fix

| # | Symptom | Root cause |
|---|---------|------------|
| 1 | Preview accepts `.xlsx`, `.txt`, and the Step 1 workbook checkbox | `training_preview_controls_html()` and `training_preview()` allow multiple input modes |
| 2 | Training upload may accept non-`.xlsx` if `accept` is bypassed | No server-side extension check in `training_upload()` |
| 3 | Preview shows one combined TBC count | `_is_tbc()` buckets all TBC rows together; `compare_result_html()` renders a single row |
| 4 | Analyst uploads fail unless sheet is `SCMP_Tickets_Master_Categorized` | `extract_workbook_five_tuples()` / `iter_workbook_master_rows()` default to the reference sheet name |

### How file restrictions work today

| Control | Location | Current `accept` | Server check |
|---------|----------|------------------|--------------|
| Run classification | `portal_app.index()` → `/run` | `.json,.ndjson,.txt` | None (relies on `iter_master_rows` parse failure) |
| Training upload (Step 1) | `portal_app.training_index()` → `/training/upload` | `.xlsx` | None |
| Preview changes (Step 3) | `portal_training.training_preview_controls_html()` → `/training/preview` | `.json,.ndjson,.txt,.xlsx` + Step 1 workbook checkbox | Branches on checkbox / suffix |

**Target behavior** (mirror the Run button's JSON-only pattern):

| Control | Client `accept` | Server validation |
|---------|-----------------|-------------------|
| Run classification | `.json,.ndjson` (drop `.txt`) | Reject non-JSON extensions |
| Training upload | `.xlsx` | Reject non-`.xlsx` |
| Preview changes | `.json,.ndjson` | Reject non-JSON; remove Step 1 workbook checkbox path |

### B2B vs B2C TBC today

The classifier has two distinct fallback tuples in `schema.py`:

| Segment | Tuple |
|---------|-------|
| B2B TBC | `("B2B", "Service Task", "General Support", "TBC (Manual Review)", "N/A")` |
| B2C TBC | `("B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A")` |

`classify_row_with_explanation()` picks between them based on B2B print-context hints. Preview uses audit-style TBC detection:

```python
decision.fallback_used or "tbc" in decision.tier[3].lower()
```

Both segments count toward the same `tbc_old` / `tbc_new` fields. Analysts need them shown separately.

### Classified upload sheet naming

| Workbook type | Typical sheet name | Parser used today |
|---------------|-------------------|-------------------|
| Reference (`doc/CS_ticket_new_categorizations.xlsx`) | `SCMP_Tickets_Master_Categorized` | `_load_workbook_tuples()` — **keep unchanged** |
| Portal run download | `Tickets` | Same hardcoded default — **fails** |
| Analyst export (renamed sheet) | varies | Same hardcoded default — **fails** |

Training `create_session()` calls `extract_workbook_five_tuples(dest)` which defaults to `SCMP_Tickets_Master_Categorized`. This is correct for the reference workbook loader but wrong for analyst uploads.

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Code preservation | Prefer **new functions** over modifying shared paths; justify any edits to `_load_workbook_tuples`, `iter_workbook_master_rows`, or `extract_workbook_five_tuples` defaults | Requester wants minimal churn to working reference-workbook code (see `CONTEXT.md`) |
| Reference workbook load | Keep `_load_workbook_tuples()` default sheet = `SCMP_Tickets_Master_Categorized` | Unchanged behavior for `load_allowlist()` |
| Classified upload parse | New `resolve_classified_upload_sheet()` + thin wrappers (`extract_classified_workbook_five_tuples`, etc.) | Isolates upload logic from reference loading |
| Sheet resolution order | 1) `SCMP_Tickets_Master_Categorized` if present; 2) `Tickets` if present; 3) sheet with most rows that have required tier columns + `id` | Covers reference-style, portal-download, and analyst-renamed sheets without first-sheet fallback |
| Merge target sheet | `merge_tuples_into_workbook()` **target** stays `SCMP_Tickets_Master_Categorized`; **source** uses resolved upload sheet | Commit always writes to the reference workbook layout |
| Preview input | JSON/NDJSON file upload only; remove "Use classified workbook from Step 1" checkbox | Matches Run button pattern; preview validates classifier impact on a fixed export, not the upload workbook |
| TBC split | Bucket by `decision.tier[0]` (`"B2B"` vs `"B2C"`) when `_is_tbc()` is true; keep combined total as optional third row | Segment-specific signal without removing the existing audit-style total |
| `compare_allowlists_on_workbook` | Keep function; remove from Training preview route only | May be useful elsewhere; preview no longer calls it |

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-F1 | Run classification file input: `accept=".json,.ndjson"`; server rejects other extensions with HTTP 400 |
| FR-F2 | Training upload file input: `accept=".xlsx"`; server rejects non-`.xlsx` with HTTP 400 |
| FR-F3 | Preview file input: `accept=".json,.ndjson"` only; remove Step 1 workbook checkbox and `.xlsx`/`.txt` paths |
| FR-F4 | Preview results table shows **B2B TBC count**, **B2C TBC count**, and **combined TBC count** (with % where applicable) for old vs new allow-list |
| FR-F5 | Classified upload parsing resolves sheet automatically; reference `load_allowlist()` behavior unchanged |
| FR-F6 | `create_session()` and `merge_tuples_into_workbook()` source reads use classified upload resolver |
| FR-F7 | Existing tests updated; new tests cover sheet resolution, format rejection, and B2B/B2C TBC split |

---

## Implementation tasks

### Task 1 — Classified upload sheet resolver (`taxonomy.py`)

**Files:** `src/cs_tickets/taxonomy.py`, `tests/test_allowlist_training.py`

**Add** (do not change `_load_workbook_tuples` signature or default):

```python
_REFERENCE_SHEET = "SCMP_Tickets_Master_Categorized"
_PORTAL_SHEET = "Tickets"

def resolve_classified_upload_sheet(xlsx: Path) -> str:
    """Pick the ticket sheet in an analyst classified upload."""
    wb = load_workbook(xlsx, read_only=True, data_only=True)
    try:
        names = wb.sheetnames
        if _REFERENCE_SHEET in names:
            return _REFERENCE_SHEET
        if _PORTAL_SHEET in names:
            return _PORTAL_SHEET
        best_name, best_count = "", -1
        for name in names:
            try:
                idx = _validate_workbook_sheet(xlsx, name)  # or inline header check
                count = _count_ticket_rows(wb[name], idx)
            except ValueError:
                continue
            if count > best_count:
                best_name, best_count = name, count
        if best_count <= 0:
            raise ValueError(f"No sheet with ticket rows and tier columns in {xlsx.name}")
        return best_name
    finally:
        wb.close()

def extract_classified_workbook_five_tuples(xlsx: Path) -> frozenset[...]:
    sheet = resolve_classified_upload_sheet(xlsx)
    return extract_workbook_five_tuples(xlsx, sheet=sheet)

def count_classified_tickets_per_tuple(xlsx: Path) -> dict[...]:
    sheet = resolve_classified_upload_sheet(xlsx)
    return count_tickets_per_tuple(xlsx, sheet=sheet)

def iter_classified_workbook_rows(xlsx: Path) -> Iterator[dict[str, str]]:
    sheet = resolve_classified_upload_sheet(xlsx)
    yield from iter_workbook_master_rows(xlsx, sheet=sheet)
```

**Wire** in `allowlist_training.create_session()`:

```python
upload_tuples = extract_classified_workbook_five_tuples(dest)
counts = count_classified_tickets_per_tuple(dest)
```

**Wire** in `merge_tuples_into_workbook()` for **source** reads only:

```python
source_sheet = resolve_classified_upload_sheet(source_xlsx)
for row in iter_workbook_master_rows(source_xlsx, sheet=source_sheet):
    ...
```

**Tests** (`tests/test_allowlist_training.py`):

- `test_resolve_prefers_scmp_sheet_when_present` — workbook with both `SCMP_Tickets_Master_Categorized` and `Tickets` picks SCMP
- `test_resolve_accepts_portal_tickets_sheet` — workbook with only `Tickets` sheet parses tuples
- `test_resolve_prefers_largest_valid_sheet` — two analyst-named sheets; picks the one with more ticket rows
- `test_resolve_raises_when_no_valid_sheet` — empty or metadata-only workbook returns clear `ValueError`
- Existing `test_extract_skips_incomplete_rows` etc. continue to pass (SCMP sheet fixtures unchanged)

**Implementation notes sub-bullets:**

- Extract `_count_ticket_rows(ws, idx)` as a small helper if `_validate_workbook_sheet` re-opens the workbook; avoid triple `load_workbook` calls — open once in resolver and pass `ws` + `idx` to counter
- If modifying `extract_workbook_five_tuples` default is tempting, **don't** — call it with explicit `sheet=` from the new wrappers only

---

### Task 2 — B2B / B2C TBC split (`allowlist_compare.py`)

**Files:** `src/cs_tickets/allowlist_compare.py`, `tests/test_allowlist_session.py`

**Extend** `AllowlistCompareResult`:

```python
@dataclass(frozen=True)
class AllowlistCompareResult:
    ...
    tbc_b2b_old: int = 0
    tbc_b2b_new: int = 0
    tbc_b2c_old: int = 0
    tbc_b2c_new: int = 0
```

**Add** segment bucketing helper:

```python
def _tbc_segment(decision) -> str | None:
    if not _is_tbc(decision):
        return None
    seg = (decision.tier[0] or "").strip().upper()
    if seg == "B2B":
        return "b2b"
    if seg == "B2C":
        return "b2c"
    return "other"  # count toward combined only, or add an "Other TBC" row if non-zero
```

**Update** `_compare_row()` to accept and return `tbc_b2b_old/new`, `tbc_b2c_old/new` counters alongside existing totals.

**Update** `compare_result_html()` rows:

| Metric | Old | New | Delta |
|--------|-----|-----|-------|
| B2B TBC count | … | … | … |
| B2B TBC % | … | … | |
| B2C TBC count | … | … | … |
| B2C TBC % | … | … | |
| TBC count (combined, audit-style) | … | … | … |
| TBC % (combined) | … | … | |

Keep the combined row so analysts can compare against prior preview runs and `tools/audit_classifier.py`. Update footnote to mention B2B/B2C split by `Tier1_Segment`.

**Tests:**

- Unit test with mocked or fixture rows where old allow-list yields B2B TBC and new yields B2C TBC (or counts shift per segment)
- `test_compare_allowlists_on_ndjson` still passes; assert `tbc_b2b_old + tbc_b2c_old <= tbc_old` (other-segment TBC may explain any gap)

**Non-goal:** Do not change `run_metadata.count_tbc_rows()` on the main Run page.

---

### Task 3 — File format restrictions (portal + JS)

**Files:**

- `src/cs_tickets/portal_app.py` — `index()`, `run_upload()`, `training_upload()`, `training_preview()`
- `src/cs_tickets/portal_training.py` — `training_preview_controls_html()`
- `src/cs_tickets/static/training.js`
- `tests/test_portal.py`

**Add** shared helper (new file or `portal_app.py`):

```python
_JSON_EXTENSIONS = {".json", ".ndjson"}

def _require_extension(filename: str | None, allowed: set[str], label: str) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be one of: {', '.join(sorted(allowed))}",
        )
```

**Run classification (`index` + `run_upload`):**

- Change `accept=".json,.ndjson,.txt"` → `accept=".json,.ndjson"`
- In `run_upload()`: `_require_extension(export.filename, _JSON_EXTENSIONS, "Export file")`

**Training upload (`training_upload`):**

- Keep `accept=".xlsx"`
- Add: `_require_extension(workbook.filename, {".xlsx"}, "Classified workbook")`

**Preview (`training_preview_controls_html` + `training_preview` + `training.js`):**

- Remove checkbox:

```html
<!-- DELETE -->
<label class="training-preview-option">
    <input type="checkbox" name="use_training_upload" ...>
    Use classified workbook from Step 1
</label>
```

- Replace help copy: "Upload a Zendesk JSON/NDJSON export to preview classification impact."
- Change `accept=".json,.ndjson,.txt,.xlsx"` → `accept=".json,.ndjson"`
- Make preview file `required`
- In `training_preview()`:
  - Remove `use_training_upload` form parameter
  - Require `preview_file` with JSON extension
  - Always call `compare_allowlists_on_ndjson()` (delete workbook branch)
- In `training.js`:
  - Remove `useTrainingUpload` / `updatePreviewFileState()` logic
  - Preview button stays disabled until at least one tuple is selected (unchanged)

**Tests** (`tests/test_portal.py`):

- POST `/training/upload` with `.csv` → 400
- POST `/training/preview` without file → 400
- POST `/training/preview` with `.xlsx` → 400
- POST `/run` with `.txt` → 400

---

### Task 4 — Documentation

**Files:** `CONTEXT.md`, `docs/plans/2026-06-08-allowlist-training-fixes-notes.md` (created during implementation)

- Add code-preservation guidance to `CONTEXT.md` (see below)
- Implementer notes file per task, listing any justified deviations from "new functions only"

---

## Non-goals

- Taxonomy.csv auto-sync
- Changing classifier fallback selection logic in `classify.py`
- B2B/B2C TBC split on the main Run page metadata sheet
- Preview against the Step 1 classified workbook (removed intentionally)
- Hosted Training deployment changes

---

## Acceptance criteria

- [ ] Analyst `.xlsx` with `Tickets` sheet (portal download format) parses new tuples in Training Step 1
- [ ] Analyst `.xlsx` with a custom sheet name (most ticket rows) parses correctly
- [ ] Reference `load_allowlist()` still requires `SCMP_Tickets_Master_Categorized` in `doc/CS_ticket_new_categorizations.xlsx`
- [ ] Training upload rejects non-`.xlsx` files (client and server)
- [ ] Preview rejects `.xlsx` and `.txt`; accepts `.json` / `.ndjson` only
- [ ] Preview results show B2B TBC and B2C TBC as separate rows with counts and %
- [ ] Combined TBC row still present and matches audit-style logic
- [ ] Step 1 workbook checkbox removed from preview UI
- [ ] `pytest -q` passes
- [ ] Implementer notes markdown exists

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Wrong sheet picked when multiple valid sheets exist | Prefer named sheets (`SCMP_…`, `Tickets`) before row-count heuristic; require tier columns + `id` |
| Breaking reference allow-list load | Do not change `_load_workbook_tuples()` default; classified resolver used only from Training paths |
| B2B + B2C counts don't sum to combined TBC | Document "other segment" TBC in footnote; only show Other row if non-zero |
| Analysts relied on Step 1 workbook preview | Update Step 3 copy: export NDJSON from Zendesk for preview; upload xlsx is for tuple discovery only |
| Removing `.txt` from Run breaks existing workflow | `.txt` was NDJSON with wrong extension; server now enforces `.json`/`.ndjson` — note in implementer notes |

---

## Task checklist (implementation order)

1. [ ] Task 1 — classified upload sheet resolver + tests
2. [ ] Task 2 — B2B/B2C TBC split in compare + tests
3. [ ] Task 3 — file format restrictions (portal + JS + tests)
4. [ ] Task 4 — CONTEXT.md note + implementer notes

---

## Reference: key existing code

| Concern | Location |
|---------|----------|
| Training session create | `allowlist_training.create_session()` |
| Workbook tuple extract (reference) | `taxonomy._load_workbook_tuples()` |
| Workbook tuple extract (upload) | `taxonomy.extract_workbook_five_tuples()` — to be wrapped |
| Combined TBC today | `allowlist_compare._is_tbc()` |
| TBC result HTML | `allowlist_compare.compare_result_html()` |
| B2B/B2C fallbacks | `schema.TIER_FALLBACK_DEFAULT_TBC`, `TIER_FALLBACK_B2C_TBC` |
| Preview route | `portal_app.training_preview()` |
| Preview controls HTML | `portal_training.training_preview_controls_html()` |
| Preview JS | `static/training.js` |
| Prior Training plan | `docs/plans/2026-06-06-allowlist-training-feature.md` |
