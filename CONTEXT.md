# Glossary — CS Ticket Automation

Domain terms for this project. Implementation details belong in code and design docs, not here.

## Code preservation

When adding features or fixing bugs, **preserve as much of the original code as possible**. Prefer adding new functions over rewriting existing ones. If modifying an existing function is clearly better, document the justification in the implementation notes for that change (e.g. `docs/plans/*-notes.md`).

## Allow-list

The set of approved **5-tuples** `(Tier1_Segment … Granular_Tech_UI_Type)` that the classifier may emit. Built at runtime from the reference workbook, Taxonomy.csv leaves, and pipeline fallback tuples in code. Not stored as its own file.

## 5-tuple (tier combination)

The five tier columns that together define a classification path: Tier1_Segment, Tier2_Stream, Tier3_Cat, Tier4_Type, Granular_Tech_UI_Type.

## Reference workbook

`doc/CS_ticket_new_categorizations.xlsx` — a classified ticket master sheet whose distinct 5-tuples contribute to the allow-list. Contains real ticket rows; many rows may share the same 5-tuple.

## Exemplar row

When expanding the allow-list via Training, one real ticket row copied from the upload for each accepted new 5-tuple. Serves as a classified example in the reference workbook, not a tier-only placeholder.

## TBC (Manual Review)

A tier4 bucket meaning the classifier could not assign a confident specific category. Tracked as a success metric (TBC rate); distinct from allow-list membership.

## Training (portal flow)

Portal workflow for expanding the **allow-list** from an analyst-uploaded classified `.xlsx`. Despite the name, it does not train a model — it lets users review new tier combinations, optionally preview NDJSON impact, commit exemplar rows to the reference workbook, or revert the last commit.

Abandon the in-progress Training session before Commit. No changes are written to `doc/`; the classified upload is discarded.

## Revert (Training flow)

Undo the **last** successful Commit by restoring `doc/` artifacts from that commit's snapshot. Phase 1 does not offer a snapshot history picker.

## CSAT / satisfaction_rating

Zendesk field on ticket exports: customer satisfaction survey outcome (`good`, `bad`, `offered`, `unoffered`, etc.). Distinct from tier categorization quality. The portal and CLI optional filter **bad CSAT only** processes tickets where `satisfaction_rating.score` is `bad`.

## Thread enrichment

Pre-classification step that merges tags and conversation text from a **parent Zendesk ticket** into a **reply** ticket in the same export, so tier rules can use full thread context. Does not change workbook columns, the allow-list, or Training artifacts — only how a ticket row is scored before a **5-tuple** is chosen.
