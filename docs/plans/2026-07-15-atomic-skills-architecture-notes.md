# Atomic Skills Architecture — Notes

**Date:** 2026-07-15  
**Canonical design:** [../architecture/agent-skills-framework.md](../architecture/agent-skills-framework.md)  
**Plan:** [2026-07-15-atomic-skills-architecture.md](./2026-07-15-atomic-skills-architecture.md)

## Summary

- Full framework design published under `docs/architecture/agent-skills-framework.md`.
- Thin Christine + six atomic skills + Consistency Gateway `risk` on compile/preview.
- Review chat intent: TBC handoff / compile / profile / clarify (never default-compile).

## Verification

```bash
python -m pytest tests/test_consistency_gateway.py tests/test_review_chat_intent.py \
  tests/test_review_chat.py -v
```

## Deferred

Near-dupe index; session-scoped rule soft-delete; in-chat TBC triage skill UI.
