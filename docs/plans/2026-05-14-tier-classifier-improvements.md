# Tier Classifier Improvements Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce avoidable `TBC (Manual Review)` classifications while preserving the current allow-list safety contract and keeping every decision explainable.

**Architecture:** Keep `load_allowlist()` as the output boundary: no classifier path may emit a 5-tuple outside the allow-list. Add a decision/explanation layer around the existing weighted scorer, move simple high-confidence rules into a data file, then expand coverage with targeted tests from current TBC patterns. Keep the public `classify_row(row, allow)` API backward compatible.

**Tech Stack:** Python 3.11, stdlib `json`, `dataclasses`, `importlib.resources`, `collections.Counter`, `pytest`, existing `openpyxl` workbook/taxonomy loading.

---

## Context

Current files:

- `src/cs_tickets/classify.py`: weighted hard-coded rules, threshold, fallback logic.
- `src/cs_tickets/taxonomy.py`: workbook + taxonomy CSV + schema fallback allow-list.
- `src/cs_tickets/schema.py`: master columns and B2B/B2C TBC fallback tuples.
- `tests/test_classify.py`: current classifier behavior tests.
- `tests/test_pipeline.py`: pipeline output remains in allow-list.

Known baseline (original sample export, pre–rule batch):

- 587 rows processed.
- 244 rows classified as TBC, about 41.6%.
- Allow-list contains 63 tier tuples.
- Current scoring can reach 22 tier tuples directly; 39 allow-list tuples are currently unreachable except fallback/coercion paths.
- High-volume TBC signals include `existing_subscriber`, `digital`, `subscription_-_renew`, `annual_term`, `account_renewal`, delivery/resumption subjects, and account/access subjects.

**Audit baselines (May 2026 exports, before this batch):**

| Export | Rows | TBC | TBC % |
|--------|------|-----|-------|
| `export-2026-05-14-…_1.json` | 634 | 134 | 21.1% |
| `export-2026-05-18-…_1.json` | 459 | 133 | 29.0% |

132–133 of 133–134 TBC rows had **no candidate scores** (coverage gap, not threshold tuning).

Non-goals:

- Do not replace the classifier with generic fuzzy matching against taxonomy labels.
- Do not add an ML or LLM dependency in this phase.
- Do not change output column names or the `classify_row()` return shape.
- Do not overwrite the currently modified sample data file under `data/`.

Acceptance criteria:

- Existing public APIs continue to work.
- Every final tier tuple is still in `AllowList`.
- `pytest -q` passes.
- A repeatable audit command reports TBC rate, top TBC tags, top TBC subjects, and unreachable allow-list tuples.
- Classification explanations expose matched rule ids and top candidates.
- High-confidence coverage additions reduce sample TBC rate without introducing warnings.

---

### Task 1: Add Baseline Regression Tests

**Files:**

- Modify: `tests/test_classify.py`

**Step 1: Add focused tests for current high-confidence behavior**

Append tests that lock current behavior before refactoring:

```python
def test_b2c_upgrade_keyword_classifies_upgrade_inquiry(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Upgrade inquiry",
        "raw_subject": "Upgrade inquiry",
        "description": "I want to upgrade my SCMP subscription plan.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/2.json",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Upgrade Inquiry",
        "N/A",
    )
```

This test is expected to fail at first because B2C upgrade is currently allowed but not scored.

**Step 2: Add B2C account/admin target tests**

Add one test each for high-precision user language that maps to existing allow-list rows:

```python
def test_remove_card_details_classifies_general_support(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Remove card details",
        "raw_subject": "Remove card details",
        "description": "Please remove my credit card details from my account.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/3.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "General Support",
        "Remove card details",
        "N/A",
    )
```

```python
def test_delete_account_request_classifies_account_management(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Delete my account",
        "raw_subject": "Delete my account",
        "description": "I would like to delete my SCMP account permanently.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/4.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Account Management",
        "Request to delete account",
        "N/A",
    )
```

**Step 3: Run the targeted tests**

Run:

```bash
pytest tests/test_classify.py -q
```

Expected: existing tests pass; the new coverage tests fail until later tasks add rules.

**Step 4: Commit**

After confirming the intended failures:

```bash
git add tests/test_classify.py
git commit -m "test: capture classifier improvement targets"
```

---

### Task 2: Add Explanation API Without Changing Output

**Files:**

- Modify: `src/cs_tickets/classify.py`
- Modify: `tests/test_classify.py`

**Step 1: Add dataclasses for decision evidence**

In `src/cs_tickets/classify.py`, near `_RowSignals`, add:

```python
@dataclass(frozen=True)
class RuleEvidence:
    rule_id: str
    tier: tuple[str, str, str, str, str]
    weight: float
    signal: str


@dataclass(frozen=True)
class ClassificationDecision:
    tier: tuple[str, str, str, str, str]
    score: float
    fallback_used: bool
    candidates: tuple[tuple[tuple[str, str, str, str, str], float], ...]
    evidence: tuple[RuleEvidence, ...]
```

**Step 2: Thread evidence through scoring**

Change `_score_tiers()` to collect evidence while preserving score behavior:

```python
def _score_tiers(
    sig: _RowSignals,
    allow: AllowList,
) -> tuple[dict[tuple[str, str, str, str, str], float], list[RuleEvidence]]:
    scores: dict[tuple[str, str, str, str, str], float] = {}
    evidence: list[RuleEvidence] = []

    def add(
        t: tuple[str, str, str, str, str],
        w: float,
        *,
        rule_id: str,
        signal: str,
    ) -> None:
        if w <= 0.0 or t not in allow:
            return
        scores[t] = scores.get(t, 0.0) + w
        evidence.append(RuleEvidence(rule_id=rule_id, tier=t, weight=w, signal=signal))
```

Update each existing `add(...)` call with a stable `rule_id` and short `signal`, for example:

```python
add(
    ("B2C", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A"),
    15.0,
    rule_id="live_chat.b2c",
    signal="tag:zopim_chat",
)
```

Return both:

```python
return scores, evidence
```

**Step 3: Add `classify_row_with_explanation()`**

Keep `classify_row()` backward compatible by delegating to the new API:

```python
def classify_row_with_explanation(
    row: dict[str, Any],
    allow: AllowList,
) -> ClassificationDecision:
    sig = _signals(row)
    scores, evidence = _score_tiers(sig, allow)
    best, best_s = _pick_best(scores)
    candidates = tuple(sorted(scores.items(), key=lambda item: item[1], reverse=True))
    if best is not None and best_s >= SCORE_THRESHOLD:
        return ClassificationDecision(
            tier=best,
            score=best_s,
            fallback_used=False,
            candidates=candidates,
            evidence=tuple(evidence),
        )

    b2b_hint = _b2b_print_context(sig)
    if b2b_hint and DEFAULT_TBC in allow:
        tier = DEFAULT_TBC
    elif B2C_TBC in allow:
        tier = B2C_TBC
    elif DEFAULT_TBC in allow:
        tier = DEFAULT_TBC
    else:
        tier = next(iter(sorted(allow.tuples)))
    return ClassificationDecision(
        tier=tier,
        score=best_s,
        fallback_used=True,
        candidates=candidates,
        evidence=tuple(evidence),
    )


def classify_row(row: dict[str, Any], allow: AllowList) -> tuple[str, str, str, str, str]:
    """Weighted multi-signal tier assignment; fallbacks preserve B2B/B2C TBC behavior."""
    return classify_row_with_explanation(row, allow).tier
```

This also fixes fallback consistency by reusing `_b2b_print_context()`.

**Step 4: Test explanation behavior**

Add:

```python
from cs_tickets.classify import classify_row, classify_row_with_explanation
```

Then:

```python
def test_explanation_reports_matched_rules(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat"]',
        "subject": "Chat",
        "raw_subject": "Chat",
        "description": "",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/5.json",
    }
    decision = classify_row_with_explanation(row, allow)
    assert decision.tier == classify_row(row, allow)
    assert decision.fallback_used is False
    assert any(ev.rule_id == "live_chat.b2c" for ev in decision.evidence)
```

**Step 5: Run tests**

Run:

```bash
pytest tests/test_classify.py -q
```

Expected: explanation tests pass; improvement-target tests from Task 1 may still fail.

**Step 6: Commit**

```bash
git add src/cs_tickets/classify.py tests/test_classify.py
git commit -m "feat: explain classifier decisions"
```

---

### Task 3: Add Repeatable Classifier Audit Tool

**Files:**

- Create: `tools/audit_classifier.py`
- Test manually with current sample export.

**Step 1: Create audit script**

Create `tools/audit_classifier.py`:

```python
from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path

from cs_tickets.classify import classify_row_with_explanation
from cs_tickets.flatten import flatten_ticket
from cs_tickets.schema import PIPELINE_FALLBACK_TIER_TUPLES
from cs_tickets.taxonomy import load_allowlist


TIER_KEYS = (
    "Tier1_Segment",
    "Tier2_Stream",
    "Tier3_Cat",
    "Tier4_Type",
    "Granular_Tech_UI_Type",
)


def _tags(tags_cell: str) -> list[str]:
    try:
        value = json.loads(tags_cell or "[]")
    except json.JSONDecodeError:
        return [tags_cell] if tags_cell else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _scored_targets_from_source(path: Path) -> set[tuple[str, str, str, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[tuple[str, str, str, str, str]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "add"
            and node.args
        ):
            continue
        arg = node.args[0]
        if (
            isinstance(arg, ast.Tuple)
            and len(arg.elts) == 5
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in arg.elts)
        ):
            out.add(tuple(e.value for e in arg.elts))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--taxonomy", default=Path("doc/Taxonomy.csv"), type=Path)
    parser.add_argument("--workbook", default=Path("doc/CS_ticket_new_categorizations.xlsx"), type=Path)
    parser.add_argument("--classifier", default=Path("src/cs_tickets/classify.py"), type=Path)
    args = parser.parse_args()

    allow = load_allowlist(args.taxonomy, args.workbook)
    total = 0
    fallback = 0
    tier_counts: Counter[tuple[str, str, str, str, str]] = Counter()
    tbc_tags: Counter[str] = Counter()
    tbc_subjects: Counter[str] = Counter()

    with args.input.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = flatten_ticket(json.loads(line))
            decision = classify_row_with_explanation(row, allow)
            total += 1
            tier_counts[decision.tier] += 1
            if decision.fallback_used or "tbc" in decision.tier[3].lower():
                fallback += 1
                tbc_tags.update(_tags(str(row.get("tags") or "")))
                subject = str(row.get("subject") or "").strip()
                if subject:
                    tbc_subjects[subject[:120]] += 1

    scored = _scored_targets_from_source(args.classifier)
    reachable = scored | set(PIPELINE_FALLBACK_TIER_TUPLES)
    unreachable = sorted(allow.tuples - reachable)

    print(f"rows: {total}")
    print(f"tbc_or_fallback: {fallback} ({fallback / total:.1%})" if total else "tbc_or_fallback: 0")
    print(f"allow_tuples: {len(allow.tuples)}")
    print(f"scored_tuples: {len(scored)}")
    print(f"unreachable_allow_tuples: {len(unreachable)}")
    print("top_tiers:")
    for tier, count in tier_counts.most_common(15):
        print(f"  {count}: {' | '.join(tier)}")
    print("top_tbc_tags:")
    for tag, count in tbc_tags.most_common(20):
        print(f"  {count}: {tag}")
    print("top_tbc_subjects:")
    for subject, count in tbc_subjects.most_common(20):
        print(f"  {count}: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 2: Run audit**

Run:

```bash
PYTHONPATH=src python tools/audit_classifier.py --input data/export-2026-05-06-0153-10043126-576349730538497a83_1.json
```

Expected: script prints row count, TBC rate, top TBC tags/subjects, and unreachable allow-list count.

**Step 3: Commit**

```bash
git add tools/audit_classifier.py
git commit -m "chore: add classifier audit tool"
```

---

### Task 4: Move Simple Rules Into Data

**Files:**

- Create: `src/cs_tickets/classifier_rules.py`
- Create: `src/cs_tickets/classifier_rules.json`
- Modify: `src/cs_tickets/classify.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_classify.py`

**Step 1: Add package data**

In `pyproject.toml`, change:

```toml
[tool.setuptools.package-data]
cs_tickets = ["static/*.css"]
```

to:

```toml
[tool.setuptools.package-data]
cs_tickets = ["static/*.css", "classifier_rules.json"]
```

**Step 2: Create `classifier_rules.py`**

Add:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


TierTuple = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class RuleSpec:
    id: str
    tier: TierTuple
    weight: float
    any_tags: tuple[str, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    any_blob: tuple[str, ...] = ()
    any_url: tuple[str, ...] = ()
    requires_b2b_print_context: bool = False


def _tuple_strs(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Expected list, got {type(value).__name__}")
    return tuple(str(item).lower() for item in value)


def _tier(value: Any) -> TierTuple:
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError("Rule tier must be a 5-item list")
    return tuple(str(item) for item in value)  # type: ignore[return-value]


def load_rule_specs() -> tuple[RuleSpec, ...]:
    path = files("cs_tickets").joinpath("classifier_rules.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("classifier_rules.json must contain a list")
    rules: list[RuleSpec] = []
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError("Each rule must be an object")
        rules.append(
            RuleSpec(
                id=str(raw["id"]),
                tier=_tier(raw["tier"]),
                weight=float(raw["weight"]),
                any_tags=_tuple_strs(raw.get("any_tags")),
                all_tags=_tuple_strs(raw.get("all_tags")),
                any_subject=_tuple_strs(raw.get("any_subject")),
                any_blob=_tuple_strs(raw.get("any_blob")),
                any_url=_tuple_strs(raw.get("any_url")),
                requires_b2b_print_context=bool(raw.get("requires_b2b_print_context", False)),
            )
        )
    return tuple(rules)
```

**Step 3: Create `classifier_rules.json` for simple rules first**

Start with rules that are direct single-condition mappings. Example:

```json
[
  {
    "id": "live_chat.b2c",
    "tier": ["B2C", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A"],
    "weight": 15.0,
    "any_tags": ["zopim_chat"]
  },
  {
    "id": "live_chat.b2b_print",
    "tier": ["B2B", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A"],
    "weight": 16.0,
    "any_tags": ["zopim_chat"],
    "requires_b2b_print_context": true
  },
  {
    "id": "junk.press_release.b2c",
    "tier": ["B2C", "Junk", "Junk", "PR / External Sales / Editorial Noise", "N/A"],
    "weight": 15.0,
    "any_subject": ["press release", "[press release]"]
  },
  {
    "id": "account.remove_card.b2c",
    "tier": ["B2C", "Service Task", "General Support", "Remove card details", "N/A"],
    "weight": 10.0,
    "any_blob": ["remove card", "remove my credit card", "delete card details", "remove payment card"]
  },
  {
    "id": "account.delete_account.b2c",
    "tier": ["B2C", "Service Task", "Account Management", "Request to delete account", "N/A"],
    "weight": 10.0,
    "any_blob": ["delete my account", "close my account", "remove my account"]
  },
  {
    "id": "sales.upgrade.b2c",
    "tier": ["B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A"],
    "weight": 9.0,
    "any_blob": ["upgrade my subscription", "upgrade inquiry", "upgrade plan", "include physical"]
  }
]
```

Keep complex refund/cancel, invoice, print logistics, and B2B renewal stack in Python until the simple data-driven path is proven.

**Step 4: Add matcher in `classify.py`**

Import rules:

```python
from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
```

Add helpers:

```python
def _contains_any(blob: str, needles: tuple[str, ...]) -> bool:
    return any(needle in blob for needle in needles)


def _rule_matches(rule: RuleSpec, sig: _RowSignals) -> bool:
    if rule.requires_b2b_print_context and not _b2b_print_context(sig):
        return False
    tags = set(sig.tags_joined.split())
    if rule.all_tags and not all(tag in tags for tag in rule.all_tags):
        return False
    if rule.any_tags and not any(tag in tags for tag in rule.any_tags):
        return False
    if rule.any_subject and not _contains_any(sig.subject, rule.any_subject):
        return False
    if rule.any_blob and not _contains_any(sig.blob_1200, rule.any_blob):
        return False
    if rule.any_url and not _contains_any(sig.url, rule.any_url):
        return False
    return True
```

At the top of `_score_tiers()`, before legacy Python rules:

```python
for rule in load_rule_specs():
    if _rule_matches(rule, sig):
        add(rule.tier, rule.weight, rule_id=rule.id, signal="data_rule")
```

Remove legacy Python rules only after a test proves the JSON rule produces the same output. It is acceptable to temporarily duplicate a rule because scores accumulate to the same winning tuple.

**Step 5: Add rule-loader tests**

Add tests:

```python
def test_classifier_rules_load() -> None:
    from cs_tickets.classifier_rules import load_rule_specs

    rules = load_rule_specs()
    assert rules
    assert {rule.id for rule in rules} >= {"live_chat.b2c", "sales.upgrade.b2c"}
```

**Step 6: Run tests**

Run:

```bash
pytest tests/test_classify.py -q
pytest -q
```

Expected: tests pass, including Task 1 improvement tests.

**Step 7: Commit**

```bash
git add src/cs_tickets/classifier_rules.py src/cs_tickets/classifier_rules.json src/cs_tickets/classify.py pyproject.toml tests/test_classify.py
git commit -m "feat: load classifier rules from data"
```

---

### Task 5: Add High-Precision Coverage Rules

**Files:**

- Modify: `src/cs_tickets/classifier_rules.json`
- Modify: `tests/test_classify.py`

**Step 1: Add B2C renewal test**

```python
def test_b2c_renewal_tags_classify_rate_or_renewal(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber","subscription_-_renew","annual_term"]',
        "subject": "Reminder of Your SCMP Renewal",
        "raw_subject": "Reminder of Your SCMP Renewal",
        "description": "Please help with my SCMP renewal.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/6.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )
```

**Step 2: Add access issue test**

```python
def test_paid_subscriber_cannot_access_article_classifies_access_bug(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber","product_-_access_issue"]',
        "subject": "Cannot access article",
        "raw_subject": "Cannot access article",
        "description": "I paid for a subscription but cannot access articles.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/7.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Technical Bug",
        "Access Loop or App Bug",
        "N/A",
    )
```

**Step 3: Add JSON rules**

Append rules:

```json
{
  "id": "sales.renewal.b2c_tags",
  "tier": ["B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"],
  "weight": 10.0,
  "any_tags": ["subscription_-_renew", "account_renewal", "account_-_renewal", "annual_term", "monthly_term"],
  "any_blob": ["renewal", "renew", "subscription period", "scmp renewal"]
}
```

If the simple matcher treats `any_tags` and `any_blob` as both required, split into two rules: one tag-only rule at lower weight and one blob-only rule at lower weight. Prefer combined evidence reaching threshold over single broad words.

Append:

```json
{
  "id": "tech.access_issue.b2c",
  "tier": ["B2C", "Complaint", "Technical Bug", "Access Loop or App Bug", "N/A"],
  "weight": 9.0,
  "any_tags": ["product_-_access_issue", "product_issue_-_digital"],
  "any_blob": ["cannot access", "can't access", "unable to access", "access an article", "paid for a subscription"]
}
```

**Step 4: Keep ambiguous cancellation conservative**

Do not map all `AlipayHK Subscriber Auto Debit Cancellation` subjects to refund/cancellation yet. That phrase could be a system notification or billing administration rather than a customer complaint. Leave it TBC until sampled and labeled.

**Step 5: Run tests and audit**

Run:

```bash
pytest tests/test_classify.py -q
pytest -q
PYTHONPATH=src python tools/audit_classifier.py --input data/export-2026-05-06-0153-10043126-576349730538497a83_1.json
```

Expected: tests pass; TBC count decreases; warning count stays zero.

**Step 6: Commit**

```bash
git add src/cs_tickets/classifier_rules.json tests/test_classify.py
git commit -m "feat: expand high-confidence classifier coverage"
```

---

### Task 6: Add Candidate Margin Logic

**Files:**

- Modify: `src/cs_tickets/classify.py`
- Modify: `tests/test_classify.py`

**Step 1: Add constants**

Near `SCORE_THRESHOLD`:

```python
MIN_SCORE_MARGIN = 2.0
HIGH_CONFIDENCE_SCORE = 12.0
```

**Step 2: Add acceptance helper**

```python
def _accepted_score(
    candidates: tuple[tuple[tuple[str, str, str, str, str], float], ...],
) -> bool:
    if not candidates:
        return False
    best_s = candidates[0][1]
    if best_s < SCORE_THRESHOLD:
        return False
    if best_s >= HIGH_CONFIDENCE_SCORE:
        return True
    if len(candidates) == 1:
        return True
    return best_s - candidates[1][1] >= MIN_SCORE_MARGIN
```

Use it in `classify_row_with_explanation()` after sorting candidates:

```python
if best is not None and _accepted_score(candidates):
    ...
```

**Step 3: Add margin tests**

Add a unit-level test for `_accepted_score()`:

```python
def test_candidate_margin_rejects_close_low_confidence_scores() -> None:
    from cs_tickets.classify import _accepted_score

    first = ("B2C", "Service Task", "General Support", "Remove card details", "N/A")
    second = ("B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A")
    assert _accepted_score(((first, 5.5), (second, 4.5))) is False
    assert _accepted_score(((first, 7.0), (second, 4.5))) is True
    assert _accepted_score(((first, 12.0), (second, 11.5))) is True
```

**Step 4: Run tests**

Run:

```bash
pytest tests/test_classify.py -q
pytest -q
```

Expected: all tests pass. If existing strong rules are rejected because of narrow margins, raise only `HIGH_CONFIDENCE_SCORE` cases through tests rather than weakening the margin globally.

**Step 5: Commit**

```bash
git add src/cs_tickets/classify.py tests/test_classify.py
git commit -m "feat: require candidate margin for low-confidence classifier decisions"
```

---

### Task 7: Update Documentation and Portal Text

**Files:**

- Modify: `README.md`
- Modify: `src/cs_tickets/portal_app.py`

**Step 1: Update README classifier section**

Replace the classifier paragraph with:

```markdown
**Classifier** (`classify.py` + `classifier_rules.json`): builds scores from tags / subject / description / URL using data-driven and computed rules; only adds weight to tuples **in** the allow-list; accepts the best candidate when it passes score and margin thresholds, otherwise applies the B2B-print-hint -> **B2B TBC** else **B2C TBC** chain. `classify_row_with_explanation()` exposes matched rules and candidate scores for audit/debug.
```

**Step 2: Update portal overview text**

In `src/cs_tickets/portal_app.py`, update the same classifier description string so the local portal remains accurate.

**Step 3: Run docs-related tests**

Run:

```bash
pytest tests/test_portal.py -q
pytest -q
```

Expected: portal tests pass.

**Step 4: Commit**

```bash
git add README.md src/cs_tickets/portal_app.py
git commit -m "docs: describe classifier audit and rule strategy"
```

---

### Task 8: Final Verification

**Files:**

- No source changes unless verification exposes a defect.

**Step 1: Run full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

**Step 2: Run audit**

Run:

```bash
PYTHONPATH=src python tools/audit_classifier.py --input data/export-2026-05-06-0153-10043126-576349730538497a83_1.json
```

Record:

- Row count.
- TBC/fallback count and percentage.
- Top newly classified tuples.
- Unreachable allow-list count.

**Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional files changed. Preserve the pre-existing modified file under `data/` if it is unrelated.

**Step 4: Produce implementation summary**

Final summary should include:

- New explanation API.
- New audit command.
- New data-driven rules file.
- New high-confidence categories covered.
- Before/after TBC rate from the sample export.
- Tests run and results.

---

## Follow-Up Strategy

After this plan lands, use the audit output to drive the next rule batch. Add only categories with either strong Zendesk tags or unambiguous customer language. Keep ambiguous business/billing/system notification cases in TBC until sampled and labeled.

Candidate next categories:

- Delivery resumption and missing/delay delivery.
- Activation and paid-access failures.
- Newsletter unsubscribe/update-email requests.
- Retention offer.
- Price mismatch and next billing rate.
- OFCA/regulatory tickets.

---

## Implementation log (2026-05-19)

Second rule batch from May 14 / May 18 export analysis. Changes in `classifier_rules.json`, `classify.py` (computed guards), and `tests/test_classify.py`.

### Audit after implementation

| Export | Rows | TBC before | TBC after | Δ |
|--------|------|------------|-----------|---|
| May 14 | 634 | 134 (21.1%) | **92 (14.5%)** | −42 |
| May 18 | 459 | 133 (29.0%) | **92 (20.0%)** | −41 |

```bash
PYTHONPATH=src python -m tools.audit_classifier --input data/export-2026-05-18-1027-10043126-58045815919513ba30_1.json
PYTHONPATH=src python -m tools.audit_classifier --input data/export-2026-05-14-0707-10043126-579104711879935d85_1.json
pytest -q
```

### Rules added or changed

**`classifier_rules.json` (data-driven)**

| Rule id | Target Tier4 | Signals |
|---------|----------------|---------|
| `sales.renewal.b2c_tags_blob` | Rate or Renewal Inquiry | Renew tags + blob (no bare `renewal` — avoids `non-renewal`) |
| `sales.renewal.b2c_tags_only` | Rate or Renewal Inquiry | `subscription_-_renew`, `account_renewal`, `account_-_renewal` |
| `sales.renewal.b2c_subscriber_digital` | Rate or Renewal Inquiry | `existing_subscriber` + `digital` + rate/renew blob |
| `tech.access_issue.b2c` | Access Loop or App Bug | Extended login/access blobs; weight 12 |
| `tech.access_issue.b2c_login_subject` | Access Loop or App Bug | Login subjects |
| `tech.epaper.b2c` | Access Loop or App Bug | ePaper subject/blob |
| `billing.system_report.order_confirmation.b2c` | System Report | Order/payment confirmation |
| `billing.system_report.remittance.b2c` | System Report | Remittance notification |
| `logistics.address_change_tags.b2c` | Print Subs logistics | `address_-_change_of_address` |
| `general.next_billing_rate.b2c` | Next billing rate | Billing-rate phrases |
| `junk.external_noise_chinese.b2c` | PR noise | Chinese 採訪/新聞稿 phrases |
| `junk.external_noise_editorial_tag.b2c` | PR noise | `editorial` tag + interview blob |
| `junk.external_noise_media_invitation.b2c` | PR noise | Media invitation subject |
| `junk.external_noise.b2c` | PR noise | Extended English PR/spam phrases |
| `complaint.cancel_language.b2c` | Cancellation Request | Cancel/terminate blob |
| `complaint.cancel_posties.b2c` | Cancellation Request | Posties cancel |
| `account.remove_card.b2c` | Remove card details | Extended card-removal phrases |

Renamed: `sales.renewal.b2c_tags` → `sales.renewal.b2c_tags_blob`.

**`classify.py` (computed)**

| Rule id | Behavior |
|---------|----------|
| `computed:non_renewal_cancel.b2c` | Weight 14 → Cancellation Request; runs before JSON renewal rules |
| `computed:cancel_language.b2c` | Cancel blob without refund tag; skips AlipayHK system notices |
| `_rule_matches` | Skips `sales.renewal.*` when non-renewal intent detected |
| `_is_alipayhk_auto_debit_notice` | Holds bare AlipayHK auto-debit subjects out of cancel blob path |

### Implementation log (2026-05-19, TBC reduction — zopim account portal)

After strict `subscribe.scmp.com` live-chat rule, ~175 `zopim_chat` tickets fell to TBC. Added:

- `chat.account_portal.upgrade.b2c` — zopim + Conversation with + `account.scmp.com` + upgrade URL
- `chat.account_portal.subscriber.b2c` — zopim + existing_subscriber + digital + account portal
- `sales.account_enquiry.b2c` — `account_enquiry` tag
- `general.retention_offer.b2c` — retention email phrases
- `tech.access_issue.b2c_tags_only` — access tags without blob phrase
- `computed:chat_account_refund.b2c` / `computed:chat_account_churn.b2c` — refund/churn tags on account chats

### Implementation log (2026-05-19, Sheryl feedback items 1–3)

1. **Strict live chat** — `live_chat.b2c` replaced by `live_chat.b2c.strict` (`zopim_chat` + `conversation with` + `https://subscribe.scmp.com/`).
2. **Rosetta renewals** — `billing.system_report.rosetta_renewal.b2c` (weight 14); renewal JSON rules skipped when `rosetta system email` in blob.
3. **ESP → B2B** — `_is_esp_enterprise_context` + `_apply_esp_b2b_segment` remaps B2C winners to B2B sibling tuples (`ESP-OPP` / `ESP-Inv` patterns only).

### Explicitly not automated (remain TBC-heavy)

- **`RE:` / `Re:` / `FW:` threads** (~63 combined) — need parent ticket / full thread text in export.
- **AlipayHK auto-debit notices** — partial routing to Renewal/Cancel; bare notices without customer language stay TBC or Renewal until labeled.
- **`miscellaneous` / `other_departments` alone** — Zendesk tagging hygiene, not classifier-only.

### Implementation log (2026-05-19, TBC batch 3 — account portal + replies)

| Export | Rows | TBC before | TBC after |
|--------|------|------------|-----------|
| May 14 | 634 | 106 (18.3%) | **60 (9.5%)** |
| May 18 | 459 | 104 (22.7%) | **65 (14.2%)** |

- Broadened zopim account portal: `chat.account_portal.existing/new_subscriber`, `computed:chat_account_subscriber` (annual_term, subscription_-_other, account_-_method).
- Reply-thread cues: `sales.reply_renewal_subject`, `computed:reply_renewal_subject`, `billing.reply_po`.
- Tag/subject paths: `sales.new_subscriber`, `sales.subscription_pricing`, `sales.physical_print`, `sales.site_license_renewal.b2b`, `account.password_reset`, `account.update_info`, `account.contact_change`, `junk.misc_not_subscribed`, `sales.subscription_renew_tag`, delivery subject fix (`exclude_blob` on physical_print; logistics weight 12).
- **`RuleSpec.exclude_blob`** — stops subscriber rules stacking over upgrade URLs.

### Next batch (from remaining TBC audit)

- Retention-offer phrases (“continue to support SCMP Journalism”).
- Newsletter unsubscribe / email change (taxonomy leaves exist).
- Activation failures (`not able to activate the account`).
- Enrich flatten step with follow-up parent tags for reply threads.

