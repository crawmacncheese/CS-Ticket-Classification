# Test plan: Allowlist Training resolves prior TBCs

Related docs: [`allowlistupdatefeature.md`](./allowlistupdatefeature.md), [`errornotes.md`](./errornotes.md), [`docs/plans/2026-06-06-allowlist-training-feature.md`](./docs/plans/2026-06-06-allowlist-training-feature.md), [`docs/plans/2026-06-09-allowlist-testing-architecture.md`](./docs/plans/2026-06-09-allowlist-testing-architecture.md).

**Goal:** Verify that expanding the allow-list via Training can move tickets from **TBC (Manual Review)** to a specific tier when classifier rules already match the ticket but the target 5-tuple was missing from the allow-list.

---

## Important context (read first)

### Two different inputs

| Input | Purpose |
|-------|---------|
| Classified `.xlsx` (Step 1) | Supplies **new 5-tuples** to merge into the reference workbook |
| Zendesk `.ndjson` (Step 3 preview, or main Run page) | Supplies **raw tickets** that get classified |

Re-running the classified workbook does **not** test reclassification. Preview always classifies the **NDJSON export**.

### When allow-list expansion fixes TBC

All three must be true:

1. A classifier rule matches the ticket (tags / subject / description).
2. That rule's target 5-tuple is **not** in the current allow-list (scores are gated — no tuple in allow-list means no candidate score).
3. You add that exact 5-tuple via Training.

If rules never fire, adding a random analyst tuple will **not** reduce TBC.

### Current repo state (June 2026)

Analysis against `doc/` shows:

- **106** allow-list tuples
- **0** `classifier_rules.json` rule targets missing from the allow-list
- Example workbook `20260528_-_CS_ticket_new_categorizations.xlsx` has **0** tuples new vs current allow-list

So there is no “natural” new tuple in the repo today. To test the happy path you must use a **controlled setup** (below) that temporarily removes one workbook-only tuple, then adds it back through Training.

---

## Primary test case (concrete)

| Field | Value |
|-------|-------|
| **Rule** | `sales.new_subscriber.b2c` in `classifier_rules.json` |
| **Target 5-tuple** | `B2C \| Service Task \| Sales Leads \| Rate or Renewal Inquiry \| N/A` |
| **Ticket id** | `910001` |
| **Tags** | `["new_subscriber"]` |
| **Subject** | `Subscription pricing` |
| **Tuple source** | Reference workbook only (not in `doc/Taxonomy.csv`) |

**Expected behavior**

| Allow-list | Classification | TBC? | Candidates |
|------------|----------------|------|------------|
| Missing tuple | `… General Support \| TBC (Manual Review) \| N/A` | Yes | Empty `()` |
| Tuple present | `… Sales Leads \| Rate or Renewal Inquiry \| N/A` | No | Score `10.0` from `sales.new_subscriber.b2c` |

**Preview delta (1-row NDJSON):** `tbc_old=1`, `tbc_new=0`, ticket `910001` in changed-rows sample.

### Fixture files (in repo)

| File | Role |
|------|------|
| `tests/fixtures/training_tbc_probe.ndjson` | Single-ticket Zendesk export for preview / Run |
| `tests/fixtures/training_tbc_probe_upload.xlsx` | Classified upload (generate with script below) |

Generate or refresh the upload workbook:

```bash
.\.venv\Scripts\python.exe tools\build_training_test_upload.py
```

---

## Test A — Quick mechanism check (CLI, ~2 min)

Proves compare/preview logic without touching `doc/` or the portal.

```bash
.\.venv\Scripts\python.exe -c "
from pathlib import Path
import json
from cs_tickets.allowlist_compare import compare_allowlists_on_ndjson
from cs_tickets.classify import classify_row_with_explanation
from cs_tickets.flatten import flatten_ticket
from cs_tickets.taxonomy import AllowList, load_allowlist

novel = ('B2C', 'Service Task', 'Sales Leads', 'Rate or Renewal Inquiry', 'N/A')
allow_full = load_allowlist(Path('doc/Taxonomy.csv'), Path('doc/CS_ticket_new_categorizations.xlsx'))
allow_old = AllowList(tuples=frozenset(allow_full.tuples - {novel}))

ndjson = Path('tests/fixtures/training_tbc_probe.ndjson')
line = ndjson.read_text(encoding='utf-8').strip()
row = flatten_ticket(json.loads(line))

old = classify_row_with_explanation(row, allow_old)
new = classify_row_with_explanation(row, allow_full)
result = compare_allowlists_on_ndjson(ndjson, allow_old, allow_full)

assert 'tbc' in old.tier[3].lower() and old.fallback_used
assert old.candidates == ()
assert novel == new.tier
assert result.tbc_old == 1 and result.tbc_new == 0
assert result.changed_rows[0]['id'] == '910001'
print('PASS: TBC 1 -> 0, tier -> Rate or Renewal Inquiry')
"
```

**Pass criteria:** Script prints `PASS` with no assertion errors.

---

## Test B — Portal end-to-end (manual, ~15 min)

Because the probe tuple is already in the live allow-list, you must **temporarily remove it** from the reference workbook so Training sees it as “new”.

### B0. Prerequisites

- `doc/` and `doc/CS_ticket_new_categorizations.xlsx` are writable (local dev).
- Portal running: `uvicorn cs_tickets.portal_app:app --reload --port 8777`
- Fixtures generated (see above).

### B1. Backup and strip the probe tuple

```powershell
Copy-Item doc\CS_ticket_new_categorizations.xlsx doc\CS_ticket_new_categorizations.xlsx.bak
```

Remove every workbook row whose five tier columns equal:

`B2C | Service Task | Sales Leads | Rate or Renewal Inquiry | N/A`

(Excel filter or manual edit on sheet `SCMP_Tickets_Master_Categorized`.)

Verify the tuple is gone:

```bash
.\.venv\Scripts\python.exe -c "
from pathlib import Path
from cs_tickets.taxonomy import load_allowlist
novel = ('B2C', 'Service Task', 'Sales Leads', 'Rate or Renewal Inquiry', 'N/A')
allow = load_allowlist(Path('doc/Taxonomy.csv'), Path('doc/CS_ticket_new_categorizations.xlsx'))
print('tuple in allowlist:', novel in allow.tuples)  # must be False
"
```

### B2. Training flow

1. Open http://127.0.0.1:8777/training
2. **Step 1 — Upload** `tests/fixtures/training_tbc_probe_upload.xlsx`
3. **Step 2 — Select** the `Rate or Renewal Inquiry` row (should show **1 ticket in upload**)
4. **Step 3 — Preview** upload `tests/fixtures/training_tbc_probe.ndjson`
5. **Check preview table:**

| Metric | Old | New | Delta |
|--------|-----|-----|-------|
| TBC count (combined) | `1` | `0` | `-1` |
| Zero-candidate rows | `1` | `0` | `-1` |
| Changed tickets | id `910001` | old `TBC (Manual Review)` → new `Rate or Renewal Inquiry` | — |

6. **Commit** selected tuple (checkbox only — preview is optional; Commit does not require NDJSON).
7. **Optional confirm:** On the main classify page, run the same NDJSON — ticket `910001` should not be TBC.

### B3. Cleanup

Either:

- Click **Undo last update** in Training, or
- `Copy-Item doc\CS_ticket_new_categorizations.xlsx.bak doc\CS_ticket_new_categorizations.xlsx -Force`

---

## Test C — Real Zendesk export (when you have `data/`)

Use this after placing an export in `data/` (gitignored).

### C1. Find TBC tickets

```bash
.\.venv\Scripts\python.exe tools\audit_classifier.py --input data\your-export.ndjson
```

### C2. Diagnose each interesting TBC

```python
# Run in repo root with venv active
import json
from pathlib import Path
from cs_tickets.classify import classify_row_with_explanation
from cs_tickets.flatten import flatten_ticket
from cs_tickets.taxonomy import load_allowlist

allow = load_allowlist(Path("doc/Taxonomy.csv"), Path("doc/CS_ticket_new_categorizations.xlsx"))
path = Path("data/your-export.ndjson")

with path.open(encoding="utf-8") as f:
    for line in f:
        row = flatten_ticket(json.loads(line))
        dec = classify_row_with_explanation(row, allow)
        if not (dec.fallback_used or "tbc" in dec.tier[3].lower()):
            continue
        if dec.candidates:
            continue  # scoring competition — allow-list alone may not help
        if not dec.evidence:
            continue  # rules gap — allow-list alone will not help
        print(row["id"], row.get("tags"), [e.rule_id for e in dec.evidence])
        print("  evidence fired but no scored candidates → allow-list gap candidate")
```

**Look for:** `evidence` non-empty **and** `candidates` empty. That pattern means rules matched but every target tuple was outside the allow-list.

### C3. Build classified upload from analyst work

For each allow-list-gap ticket:

1. Copy the raw ticket fields into a classified `.xlsx` row.
2. Fill all five tier columns with the analyst-approved classification.
3. Upload via Training; preview with the **same** NDJSON export.

---

## Negative control (optional)

Add a tuple that is **not** targeted by any rule, e.g. `TestSeg | TestStream | TestCat | TestType | TestGran`.

**Expected:** Tuple merges into allow-list on Commit, but preview TBC count **unchanged** and probe ticket `910001` unchanged. Confirms Training is not “magic reclassification” without rule support.

---

## Automated pytest (future)

No CI test asserts TBC reduction yet (golden NDJSON deferred in plan). Candidate test:

```python
def test_training_probe_resolves_tbc_when_tuple_missing(repo_root, tmp_path):
    novel = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
    # allow_old = full minus novel; allow_new = full
    # compare_allowlists_on_ndjson(training_tbc_probe.ndjson, allow_old, allow_new)
    # assert result.tbc_new < result.tbc_old
```

---

## Troubleshooting

| Observation | Likely cause |
|-------------|--------------|
| Tuple not in Step 2 checklist | Tuple still in allow-list (workbook and/or Taxonomy.csv). Strip workbook rows or pick a different tuple. |
| TBC unchanged after preview | Rules do not target that tuple, or ticket hits scoring competition (had candidates before). |
| TBC count rises | New tuples increased scoring competition — known behavior; see plan docs. |
| Commit disabled | No checkbox selected (JS enables Commit when ≥1 tuple checked). Preview is optional. |
| `zero_candidate` unchanged | Allow-list was not the blocker; need rule changes. |

---

## Summary

Your original idea was directionally right, with one correction: **use NDJSON for reclassification, xlsx only for new tuples**. Because this repo’s allow-list already contains every rule target, use **Test A** for a fast proof and **Test B** for full portal validation after temporarily removing the probe tuple from the reference workbook.
