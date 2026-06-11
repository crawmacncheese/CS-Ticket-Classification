# Training Rule Proposals — Implementation Plan

> **For implementer:** When you execute this plan (the actual coding), document your steps, process, and final design decisions in a separate markdown file (e.g. `docs/plans/2026-06-09-training-rule-proposals-notes.md`) so the requester can review rationale, catch bugs early, and understand the code. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** Close the gap between **allow-list expansion** (Training Phase 1) and **ticket routing** (classifier rules). When analysts accept new tier combinations, the system should also produce **explainable routing rules** so tickets can actually score toward those tuples — not merely become legal output.

**Architecture:** Keep the existing weighted rule-based classifier (`classify.py` + `classifier_rules.json`). Add a **coverage audit** layer, a **`doc/training_rules.json`** overlay merged at load time, **deterministic rule generation** from committed exemplar rows, and a **golden NDJSON** regression fixture. Defer ML/embeddings and exemplar-similarity fallback to a later optional phase.

**Tech stack:** Python 3.11, FastAPI, openpyxl, existing `RuleSpec` / `load_rule_specs()` / `classify_row_with_explanation`, pytest.

**Depends on:** [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md) (shipped), [2026-06-08-allowlist-training-fixes.md](./2026-06-08-allowlist-training-fixes.md) (shipped or in progress).

**PRD alignment:** Implements PRD Phase 3 direction ("feedback loop: manual relabel → rule proposals") in a form compatible with NFR-01 explainability.

**Review amendments (2026-06-09):** Senior-engineer review identified integration gaps (classifier rule injection, cache invalidation, Step 2 coverage model, commit atomicity). Amendments below are **normative** — implement per amended tasks/FRs, not the pre-review sketches alone.

---

## Context

### The problem

Training today commits **exemplar rows** to `doc/CS_ticket_new_categorizations.xlsx`. That grows the allow-list via `load_allowlist()`, but **does not change routing**.

Classification only assigns score when a rule fires:

```python
# classify._score_tiers — allow-list is a filter, not a router
if w <= 0.0 or t not in allow:
    return
scores[t] = scores.get(t, 0.0) + w
```

A tuple can be in Taxonomy.csv, the workbook, and the allow-list, yet tickets never reach it because no rule in `classifier_rules.json` or computed blocks in `classify.py` targets it.

| Layer | Question it answers | Updated by Training today? |
|-------|---------------------|----------------------------|
| **Allow-list** | Is this tier legal output? | Yes |
| **Rules** | Which tiers get score for which ticket signals? | No |

**Symptom → cause → fix** (from [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md)):

| Symptom | Likely cause | Fix direction |
|---------|--------------|---------------|
| `zero_candidate` unchanged after allow-list growth | No rules target those tuples | Add routing rules |
| TBC up, candidates exist | Margin competition | Tune weights / disambiguation |
| New tuple never in preview `changed_rows` | Tuple allow-listed but unscored | Rules work, not allow-list work |

### What success looks like

After this plan:

1. Training **Commit** writes **two artifacts**: exemplar row(s) + generated rule(s).
2. Training checklist shows **coverage badges** (routable vs allow-only).
3. Preview explains whether TBC delta is **zero-candidate** vs **margin-loss**.
4. Golden NDJSON CI catches TBC regressions when rules or allow-list change.
5. Revert restores workbook **and** `doc/training_rules.json`.

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Code preservation | **New modules/functions**; minimal edits to `classify._score_tiers` and `load_rule_specs()` | Per `CONTEXT.md` — extend, don't rewrite |
| Core rules | Keep `src/cs_tickets/classifier_rules.json` hand-curated | Reviewed baseline; Training must not silently overwrite |
| Training rules | New `doc/training_rules.json` — append/upsert per commit batch | Revertible, git-diffable, separable from core rules |
| Rule load order | Core rules first, then training rules (same `RuleSpec` shape + optional metadata fields ignored by matcher) | Predictable merge; training rules can supplement gaps |
| Generation strategy | **Deterministic** signal extraction from exemplar row (tags, subject phrases, blob phrases, url) | Explainable (NFR-01); no ML infra |
| Generation trigger | On **Commit** for selected tuples with **no existing rule target** | Avoid duplicate rules; idempotent upsert by tuple hash |
| Default weight | `10.0` (≥ `SCORE_THRESHOLD`, < `HIGH_CONFIDENCE_SCORE`) | Conservative; margin gate still applies |
| B2B print context | Set `requires_b2b_print_context: true` when exemplar url/tags indicate printsupport / print_subs | Matches existing computed-rule guards |
| Golden set | Fixed NDJSON in `tests/fixtures/` — **not** a frozen allow-list | Allow-list reflects approved taxonomy; golden set validates behavior |
| Exemplar similarity fallback | **Defer** to Phase 3 optional | Weaker explainability; only if rule proposals insufficient |
| Taxonomy.csv sync | **Defer** (unchanged from Training Phase 2 backlog) | Out of scope for this plan |
| Classifier rule injection | Add optional `rule_specs` kwarg to `classify_row_with_explanation` → `_score_tiers`; default `None` → `load_rule_specs()` | Preview must simulate candidate rules without disk write; compare-only params are insufficient |
| `load_rule_specs` cache | Call `load_rule_specs.cache_clear()` after training commit, revert, and in tests that mutate `training_rules.json` | FastAPI is long-lived; stale cache hides new rules until process restart |
| `training_rules.json` path | Resolve via same semantics as `portal_app._repo_root()` (`CS_TICKETS_REPO_ROOT`, walk for `doc/`) — **not** bare `Path("doc/…")` relative to cwd | Core rules use package resources; doc artifacts use deploy root |
| Computed-rule registry | **Reuse** `tools/audit_classifier._scored_targets_from_source()` (move to shared module) — no parallel maintained frozenset | Avoid drift between audit and coverage |
| Step 2 coverage | Separate `training_routing_badge()` from audit `tuple_rule_coverage()` | New tuples are not in current allow-list; three-state audit model does not apply |
| Commit atomicity | Generate rules in memory first; write workbook + `training_rules.json`; on rule-write failure, restore from snapshot | Prevent exemplar-without-rule inconsistent state |
| Rules ⊆ merged tuples | Generate/upsert rules only for tuples that received an exemplar row (`added` set) | `merge_tuples_into_workbook` silently skips missing exemplars |

### Commit artifacts (updated semantics)

| File | On Commit | On Revert |
|------|-----------|-----------|
| `doc/CS_ticket_new_categorizations.xlsx` | Append exemplar rows (existing) | Restore from snapshot |
| `doc/training_rules.json` | Upsert generated rules for accepted tuples | Restore from snapshot |
| `doc/Taxonomy.csv` | Unchanged | Restore if snapshotted (existing behavior) |
| `doc/.snapshots/<uuid>/` | Copy all of the above before write | N/A |

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-R1 | `tuple_rule_coverage()` reports per 5-tuple: `routable`, `allow_only`, or `blocked` (rule exists, tuple not in allow-list) — **audit tool only** |
| FR-R2 | Training Step 2 uses `training_routing_badge(tier)` → **"Already routable"** or **"Needs routing rule"** (rule-target check only; ignores current allow-list membership) |
| FR-R3 | `commit_session()` generates routing rules only for **merged** tuples that lack rule coverage; returns `CommitResult(rows_added, rules_added, rules_skipped)` |
| FR-R4 | Generated rules persist to `doc/training_rules.json` with stable ids and exemplar `id` reference |
| FR-R5 | `load_rule_specs()` merges core + training rules; matcher behavior unchanged |
| FR-R6 | Snapshot/revert includes `training_rules.json` when present |
| FR-R7 | Preview UI distinguishes `zero_candidate` vs margin-loss TBC; **"New" column** classifies with `rule_specs=core+candidate_training` (see Task 7) |
| FR-R8 | Golden NDJSON fixture + pytest asserts TBC / zero-candidate bounds; plus probe tests (negative control + positive rule fix) |
| FR-R9 | `tools/audit_classifier.py` (or sibling) reports unreachable allow-list tuples and TBC reason buckets aligned with `_accepted_score` |
| FR-R10 | Commit success page states exemplar rows **and** rules added (plain language), including skipped tuples when `rows_added < len(selected)` |
| FR-R11 | `classify_row_with_explanation(row, allow, *, rule_specs=None)` — backward compatible; `classify_row(row, allow)` unchanged |
| FR-R12 | `load_rule_specs.cache_clear()` invoked after commit/revert; same-process preview after commit sees new rules |
| FR-R13 | First post-deploy snapshot copies `training_rules.json` as `[]` when absent, so revert has a defined rules baseline |

---

## Phase 2a — Coverage audit and golden NDJSON

### Task 1 — Rule coverage module

**Files (new):**

- `src/cs_tickets/rule_coverage.py`
- `tests/test_rule_coverage.py`

**Add:**

```python
CoverageStatus = Literal["routable", "allow_only", "blocked"]

@dataclass(frozen=True)
class TupleCoverage:
    tier: TierTuple
    status: CoverageStatus
    rule_ids: tuple[str, ...]  # core + training rules targeting this tier

def rule_target_tiers(rule_specs: tuple[RuleSpec, ...]) -> dict[TierTuple, tuple[str, ...]]:
    """Map tier → rule ids from JSON-loaded specs."""

def computed_rule_targets(classify_py: Path | None = None) -> dict[TierTuple, tuple[str, ...]]:
    """Reuse audit_classifier AST scrape of classify._score_tiers add() calls (shared helper)."""

def has_rule_target(
    tier: TierTuple,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]] | None = None,
) -> bool:
    """True if any core/training JSON rule or computed add() targets this tier."""

def training_routing_badge(tier: TierTuple, *, json_rules, computed_targets) -> Literal["already_routable", "needs_rule"]:
    """Step 2 checklist only — ignores allow-list membership."""

def tuple_rule_coverage(
    tier: TierTuple,
    allow: AllowList,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]] | None = None,
) -> TupleCoverage:
    ...
```

**Notes:**

- Move `_scored_targets_from_source()` from `tools/audit_classifier.py` into `rule_coverage.py` (or `classifier_targets.py`); audit tool imports the shared helper.
- `tuple_rule_coverage()` is for **audit/reachability** (tuple must be in allow-list for `routable` / `allow_only`). Do **not** use it for Step 2 badges on `session.new_tuples` — those tuples are not in the current allow-list.
- `training_routing_badge()`: `already_routable` when `has_rule_target()`; else `needs_rule`. Document in UI footnote that "Already routable" means a scorer exists, not that the exemplar ticket would necessarily win (margin competition may still apply).
- `blocked` is rare after Training but useful for audit when a rule targets a tuple missing from allow-list.

**Tests:**

- Tuple with `sales.renewal` json rule → `routable`
- Novel tuple in allow-list, no rule → `allow_only`
- Rule tier not in allow → `blocked`
- Novel tuple **not** in allow, no rule → `training_routing_badge` → `needs_rule` (not `blocked` / `allow_only`)
- `computed_rule_targets()` output matches audit tool on `classify.py` (same set of tiers)

---

### Task 2 — Golden NDJSON fixture and CI test

**Files:**

- `tests/fixtures/golden_export.ndjson` (curate from existing `five_tickets.ndjson` or a larger anonymized export)
- `tests/fixtures/golden_baseline.json` — `{"tbc_max": N, "zero_candidate_max": M, "total": T}`
- `tests/test_golden_classifier.py`
- Modify: `README.md` (one paragraph on golden set)

**Test sketch — baseline regression (upper bounds only):**

```python
def test_golden_export_tbc_within_baseline(repo_root):
    allow = load_allowlist(tax, ref)
    result = compare_allowlists_on_ndjson(golden_path, allow, allow)
    assert result.total == baseline["total"]
    assert result.tbc_old <= baseline["tbc_max"]
    assert result.zero_candidate_old <= baseline["zero_candidate_max"]
```

**Test sketch — training probe (from `testcase.md`; required, not optional):**

```python
def test_training_negative_control_tuple_without_rule_does_not_reduce_tbc(repo_root, tmp_path):
    """Novel tuple merged into allow-list but no generated rule → TBC unchanged on probe NDJSON."""

def test_training_probe_resolves_zero_candidate_when_rule_generated(repo_root, tmp_path):
    """Novel tuple + generated rule + candidate rule_specs on compare 'new' side → zero_candidate_new < zero_candidate_old."""
```

Use `tests/fixtures/training_tbc_probe.ndjson` (single ticket from `testcase.md` probe). Negative control: commit tuple with generation skipped (no exemplar signals / force `None`). Positive: real exemplar with distinctive tags.

**Curation guidance:**

- Include mix of B2B print-support, B2C cancel/renewal, live chat, invoice, junk.
- Record baseline numbers from current classifier on first commit of fixture.
- Update baseline only when rules intentionally change (document in notes file).

---

### Task 3 — Extend audit tooling

**Files:**

- Modify: `tools/audit_classifier.py`
- `tests/test_audit_classifier.py` (extend if exists)

**Add report sections:**

1. **Unreachable allow-list tuples** — in allow-list, no json/computed rule target
2. **TBC breakdown** — `zero_candidate` | `allowlist_filtered` | `below_threshold` | `lost_margin` | `other`
3. Optional: `--training-rules` path override

**`tbc_reason()` sketch** — must mirror `_accepted_score()` in `classify.py` (no dead branches):

```python
def tbc_reason(decision: ClassificationDecision) -> str:
    if not decision.fallback_used:
        return "not_tbc"
    if not decision.candidates:
        # Distinguish rules fired but all targets outside allow-list
        if decision.evidence:
            return "allowlist_filtered"
        return "zero_candidate"
    best_s = decision.candidates[0][1]
    if best_s < SCORE_THRESHOLD:
        return "below_threshold"
    if len(decision.candidates) >= 2 and best_s - decision.candidates[1][1] < MIN_SCORE_MARGIN:
        return "lost_margin"  # includes high-score pairs where margin gate fails
    return "other"
```

Note: `best_s >= HIGH_CONFIDENCE_SCORE` always passes `_accepted_score` when it is the top candidate — there is no `fallback_despite_high_score` bucket.

Add **`tbc_reason()`** in `classify.py` or `rule_coverage.py`. Do **not** change `ClassificationDecision` fields. Preview margin-loss counts (Task 7) should use the same helper and optionally split B2B/B2C like existing TBC metrics.

---

## Phase 2b — Exemplar-driven rule generation

### Task 4 — Training rules file, loader merge, and classifier hook

**Files:**

- `doc/training_rules.json` (initially `[]` or absent)
- Modify: `src/cs_tickets/classifier_rules.py`
- Modify: `src/cs_tickets/classify.py` (optional `rule_specs` kwarg — see FR-R11)
- `tests/test_classifier_rules.py` (extend)

**`RuleSpec` extension** (optional fields, ignored by `_rule_matches`):

```python
@dataclass(frozen=True)
class RuleSpec:
    ...
    source: str = ""           # "training_commit"
    exemplar_id: str = ""      # Zendesk id from exemplar row
    tuple_key: str = ""        # stable hash for upsert
```

**`load_rule_specs()` change:**

```python
def _training_rules_path() -> Path | None:
    """Resolve doc/training_rules.json via _repo_root() semantics; None if missing."""

@lru_cache(maxsize=1)
def load_rule_specs() -> tuple[RuleSpec, ...]:
    core = _load_rules_file(files("cs_tickets").joinpath("classifier_rules.json"))
    path = _training_rules_path()
    training = _load_rules_file(path) if path and path.is_file() else ()
    return core + training

def reload_rule_specs() -> tuple[RuleSpec, ...]:
    """load_rule_specs.cache_clear(); return load_rule_specs(). Call after commit/revert."""
```

**`_score_tiers` / `classify_row_with_explanation` change:**

```python
def classify_row_with_explanation(
    row: dict[str, Any],
    allow: AllowList,
    *,
    rule_specs: tuple[RuleSpec, ...] | None = None,
) -> ClassificationDecision:
    specs = rule_specs if rule_specs is not None else load_rule_specs()
    # pass specs into _score_tiers(sig, allow, rule_specs=specs)
```

**Loader:** parse `source`, `exemplar_id`, `tuple_key` from JSON into `RuleSpec` (defaults `""`). Missing file → empty training tuple, not an error.

**Justification for editing `load_rule_specs` / `_score_tiers`:** Single load entry point already exists; `rule_specs` override is required for preview (FR-R7, FR-R11). Document in implementation notes.

**`doc/training_rules.json` entry shape:**

```json
{
  "id": "training.exemplar.gift_purchase_inquiry.b2b",
  "source": "training_commit",
  "exemplar_id": "48291",
  "tuple_key": "a1b2c3d4e5f6",
  "tier": ["B2B", "Service Task", "Sales Leads", "Gift Purchase Inquiry", "N/A"],
  "weight": 10.0,
  "any_tags": ["print_subs"],
  "any_blob": ["gift subscription", "corporate gift"],
  "requires_b2b_print_context": true
}
```

---

### Task 5 — Rule generator from exemplar

**Files (new):**

- `src/cs_tickets/rule_generator.py`
- `tests/test_rule_generator.py`

**API:**

```python
@dataclass(frozen=True)
class GeneratedRule:
    spec: RuleSpec
    warnings: tuple[str, ...]

def generate_rule_from_exemplar(
    exemplar: dict[str, str],
    tier: TierTuple,
    *,
    existing_targets: dict[TierTuple, tuple[str, ...]],
) -> GeneratedRule | None:
    """Return None if tuple already routable (skip generation)."""
```

**Signal extraction rules (v1 heuristics):**

| Signal | Include when | Exclude |
|--------|--------------|---------|
| Tags | Non-generic Zendesk tags (`existing_subscriber`, `subscription_-_refund`, …) | `miscellaneous`, `other_departments`, `customer_-_misc` alone |
| Subject | Distinctive phrases ≥ 4 chars, lowercased | `conversation with`, `re:`, `fw:` alone |
| Blob | 2–4 significant phrases from `subject + raw_subject + description` (same construction as `classify._signals`) | Phrases appearing in > 5 existing rules (collision check) |
| URL | `printsupport`, `account.scmp.com` path fragments | Bare `zendesk.com` |
| Tag parsing | Use same logic as `classify._tags_list` (JSON array or plain string, lowercased) | Raw workbook cell strings without parsing |

**Rule shape priority:**

1. `all_tags` (2+ specific tags) + optional `any_blob`
2. `any_tags` + `any_subject`
3. `any_tags` + `any_blob`
4. `any_blob` only — allowed only if ≥ 2 phrases and generator emits **warning** string

**Weight:** default `10.0`; if exemplar tags include a tag already used by a json rule for a *different* tier, use `11.0` and add warning (competition).

**`tuple_key`:** `sha256("|".join(tier))[:16]` for upsert — one training rule per tuple; re-commit replaces entry.

**Tests:**

- Exemplar with `zopim_chat` + `account.scmp.com` → chat-shaped rule
- Tuple already in `rule_target_tiers` → `None`
- B2B printsupport url → `requires_b2b_print_context: true`

---

### Task 6 — Wire generator into Training commit

**Files:**

- Modify: `src/cs_tickets/allowlist_training.py`
- Modify: `src/cs_tickets/portal_app.py`
- Modify: `src/cs_tickets/portal_training.py`
- `tests/test_allowlist_session.py` (extend commit/revert)

**`commit_session()` updated flow:**

```text
1. snapshot_doc_artifacts()          # copy workbook, taxonomy, training_rules.json (write [] snapshot if absent — FR-R13)
2. merged_tuples = resolve exemplars for selected (same lookup as merge_tuples_into_workbook)
3. rules_to_upsert = []
   for each tuple in merged_tuples only:
     if has_rule_target(tuple): skip (rules_skipped += 1)
     else: rules_to_upsert.append(generate_rule_from_exemplar(exemplar, tuple, ...))
4. merge_tuples_into_workbook()      # existing; rows_added may be < len(selected)
5. upsert_training_rules(doc/training_rules.json, rules_to_upsert)  # atomic write
   on failure: revert_snapshot(snapshot_dir) and re-raise
6. reload_rule_specs()
7. drop_session()
8. return CommitResult(rows_added, rules_added, rules_skipped)
```

`rules_added` counts only tuples that received a new upserted rule. `rules_skipped` = already routable + selected-but-not-merged.

**`upsert_training_rules(path, rules)`** — new helper in `rule_generator.py` or `allowlist_training.py`:

- Read existing list
- Replace entries with matching `tuple_key`
- Append new
- Write atomically (temp file + rename)

**Snapshot/revert:**

- Modify `snapshot_doc_artifacts()` to copy `doc/training_rules.json` when `is_file()`, else write `[]` into snapshot as `training_rules.json`
- Modify `revert_snapshot()` to restore `training_rules.json` when present in snapshot dir; call `reload_rule_specs()` after restore

**Portal copy (plain language):**

- Step 2 badge: **`training_routing_badge()`** → **"Needs routing rule"** vs **"Already routable"** (not `tuple_rule_coverage` statuses)
- Success: "Added 3 categories and 2 matching rules (1 already had rules, 1 skipped — no exemplar row in upload)." when applicable

---

### Task 7 — Preview enhancements

**Files:**

- Modify: `src/cs_tickets/allowlist_compare.py`
- Modify: `src/cs_tickets/portal_training.py`

**`AllowlistCompareResult` extensions:**

```python
margin_loss_old: int
margin_loss_new: int
below_threshold_old: int
below_threshold_new: int
```

**Candidate allow-list + rules for preview:**

```python
def build_candidate_rule_set(
    session: _TrainingSession,
    selected: frozenset[TierTuple],
) -> tuple[RuleSpec, ...]:
    """load_rule_specs() + in-memory generated rules for selected tuples that need_rule (no disk write)."""
```

Wire `compare_allowlists_on_ndjson` with optional **`rule_specs_new`**:

```python
def compare_allowlists_on_ndjson(
    ndjson_path, allow_old, allow_new, *,
    rule_specs_old: tuple[RuleSpec, ...] | None = None,  # default: load_rule_specs()
    rule_specs_new: tuple[RuleSpec, ...] | None = None,  # default: same as old
    ...
) -> AllowlistCompareResult:
```

`_compare_row` passes `rule_specs_old` to the old-side `classify_row_with_explanation` and `rule_specs_new` to the new side. **Do not** rely on temp `training_rules.json` + cache clear for preview — in-memory `rule_specs` only.

`portal_app.training_preview()` sets `rule_specs_new = build_candidate_rule_set(session, selected)`.

**Preview table additions:**

| Metric | Old | New | Delta |
|--------|-----|-----|-------|
| Margin-loss TBC | … | … | … |
| Below-threshold TBC | … | … | … |
| Rules targeting selected tuples | … | … | … |

**Footnote:** "Preview includes proposed routing rules for selected categories."

---

## Phase 2c — Margin-loss tooling (no global threshold changes)

### Task 8 — Disambiguation guidance (documentation + audit only)

**Files:**

- Modify: `docs/design.md` (short § on TBC buckets)
- Modify: `tools/audit_classifier.py`

Do **not** change `SCORE_THRESHOLD`, `MIN_SCORE_MARGIN`, or `HIGH_CONFIDENCE_SCORE` in this plan.

Audit output should list top margin-loss pairs:

```text
TBC margin-loss: B2C Rate or Renewal Inquiry (11.0) vs B2C Cancellation Request (10.5) — 42 tickets
```

This guides manual `exclude_blob` / weight edits in `classifier_rules.json`.

---

## Phase 3 — Optional exemplar similarity fallback (deferred)

**Not in scope for initial implementation.** Document as future option:

- Feature flag `CS_TICKETS_EXEMPLAR_FALLBACK=1`
- Run only when `fallback_used` would trigger and `best_s < SCORE_THRESHOLD`
- Score = tag overlap + phrase overlap against workbook exemplar rows
- Evidence: `exemplar_fallback:id=…,score=…`

Acceptance criteria for Phase 3 only if rule proposals leave unacceptable TBC on golden set.

---

## Implementation tasks (ordered)

| Order | Task | Est. |
|-------|------|------|
| 1 | Task 1 — `rule_coverage.py` | 0.5–1 d |
| 2 | Task 2 — Golden NDJSON + baseline test | 0.5–1 d |
| 3 | Task 3 — Audit TBC breakdown + unreachable tuples | 1 d |
| 4 | Task 4 — `training_rules.json` + loader + `rule_specs` hook | 1 d |
| 5 | Task 5 — `rule_generator.py` | 1–2 d |
| 6 | Task 6 — Commit/snapshot/revert wiring + atomicity | 1–1.5 d |
| 7 | Task 7 — Preview with `rule_specs_new` + UI badges | 1–2 d |
| 8 | Task 8 — Docs + margin-loss audit output | 0.5 d |

**Total:** ~7–10 days

---

## Portal UI changes (summary)

### Step 2 — Checklist columns

| Column | Content |
|--------|---------|
| (checkbox) | Select tuple |
| Tier1 … Granular | Existing |
| Tickets in upload | Existing |
| **Coverage** | Badge: **Already routable** / **Needs routing rule** (`training_routing_badge`; not audit `blocked`) |

### Step 3 — Preview (updated copy)

> Preview simulates **categories and matching rules** for your selection. Nothing is saved until Commit.

### Commit success

> Added **N** categories and **M** matching rules to `doc/`. Review with `git diff doc/` before committing to git.

### Footer

Existing **Undo last update** restores workbook + `training_rules.json`.

---

## Acceptance criteria

### Phase 2a

- [ ] `tuple_rule_coverage()` correctly classifies routable / allow_only / blocked tuples (audit)
- [ ] `training_routing_badge()` returns `needs_rule` for novel tuples not in allow-list
- [ ] `computed_rule_targets()` matches audit AST scrape on `classify.py`
- [ ] Golden NDJSON baseline test passes on current classifier
- [ ] Probe tests: negative control (allow-only, TBC unchanged) + positive (rule reduces `zero_candidate_new`)
- [ ] `tbc_reason()` buckets align with `_accepted_score`; no `fallback_despite_high_score` bucket
- [ ] `audit_classifier` reports unreachable allow-list tuples and TBC reason buckets

### Phase 2b

- [ ] Commit with a novel tuple adds exemplar row **and** entry in `doc/training_rules.json`
- [ ] Rules generated only for merged tuples (`rules_added <= rows_added`)
- [ ] Re-commit same tuple replaces rule (same `tuple_key`), does not duplicate
- [ ] Commit with already-routable tuple adds exemplar only, **no** duplicate rule (`rules_skipped` incremented)
- [ ] Rule-write failure rolls back workbook via snapshot restore
- [ ] Revert restores `training_rules.json` to pre-commit state; `reload_rule_specs()` called
- [ ] First snapshot after deploy includes `training_rules.json` (`[]` when file was absent)
- [ ] `load_rule_specs()` returns core + training rules from `_repo_root()`-resolved path
- [ ] Same-process: commit then preview/classify sees new rules without process restart
- [ ] Preview passes `rule_specs_new=build_candidate_rule_set(...)`; `zero_candidate_new` can decrease vs allow-list-only preview
- [ ] Training UI shows `training_routing_badge` labels and plain-language commit summary (rows/rules/skipped)

### Phase 2c

- [ ] Audit tool lists top margin-loss tier pairs
- [ ] No global threshold changes

### Non-regression

- [ ] All existing pytest suite passes
- [ ] `classify_row(row, allow)` signature and behavior unchanged (no new required args)
- [ ] `classify_row_with_explanation(row, allow)` unchanged when `rule_specs` omitted
- [ ] Training cancel still writes nothing to `doc/`

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Auto-rules too broad (`any_blob` matches everything) | Require multi-signal rules; collision check; default weight 10; warnings in generator output |
| TBC rises after new rules (competition) | Preview with `rule_specs_new`; margin-loss metrics in preview table; conservative weights; UI footnote on "Already routable" |
| `computed_rule_targets()` drifts from `classify.py` | Shared AST helper + test equality with audit tool output |
| Training rules pollute core quality | Separate file; promote good rules to `classifier_rules.json` manually |
| Revert without `training_rules.json` in old snapshots | FR-R13: snapshot writes `[]` when absent; revert restores when present in snapshot |
| Stale `load_rule_specs` cache after commit | `reload_rule_specs()` after commit/revert; test same-process visibility |
| `training_rules.json` not found (wrong cwd) | `_training_rules_path()` uses `_repo_root()` semantics, not relative cwd |
| Rules for unmerged tuples | Generate only for `merged_tuples`; success page reports skipped count |
| `requires_b2b_print_context` on B2B exemplar without print signals | Generator sets flag only when url/tags match; warn when B2B tier but flag false and url is printsupport-like |
| Training rule ids miss `sales.renewal` guards | Document: auto-rules do not inherit core id-prefix guards; prefer `exclude_blob` in generator when exemplar matches non-renewal patterns |
| Core + training rules stack weights on same tier | Upsert one training rule per tuple; document that core rules still contribute; preview shows margin-loss when TBC rises |

---

## Out of scope

- Taxonomy.csv auto-sync on commit
- Embeddings / k-NN classifier
- Hosted Training on read-only deploys
- Auto-promote training rules to core rules without human review
- Changing confidence thresholds globally
- Phase 2 UI wizard simplification (can proceed in parallel)

---

## Amendments summary (post-review)

| Area | Before | After |
|------|--------|-------|
| Preview rules | `extra_rules` on compare only | `rule_specs` on `classify_row_with_explanation`; `rule_specs_new` on compare |
| Cache | Unmentioned | `reload_rule_specs()` after commit/revert; same-process test |
| Step 2 badge | `tuple_rule_coverage` (3 states) | `training_routing_badge()` (2 states; ignore allow-list) |
| Commit scope | All `selected` tuples | `merged_tuples` only; `CommitResult` with skipped counts |
| Commit failure | Workbook may succeed, rules fail | Roll back from snapshot on rule-write failure |
| `tbc_reason` | Included dead `fallback_despite_high_score` | Mirrors `_accepted_score`; adds `allowlist_filtered` |
| Computed targets | Maintained frozenset | Shared AST helper from audit tool |
| Golden CI | Upper-bound snapshot only | + required probe negative/positive tests |
| Estimates | Task 4 = 0.5 d, total 6–9 d | Task 4 = 1 d, total 7–10 d |

---

## References

- [`CONTEXT.md`](../../CONTEXT.md) — allow-list, exemplar, Training glossary
- [`docs/prd.md`](../prd.md) — Phase 3 feedback loop, NFR-01 explainability
- [`allowlistupdatefeature.md`](../../allowlistupdatefeature.md) — original Training brief and TBC competition note
- [`testcase.md`](../../testcase.md) — `zero_candidate` troubleshooting
- [`2026-06-06-allowlist-training-feature.md`](./2026-06-06-allowlist-training-feature.md) — shipped Training flow
