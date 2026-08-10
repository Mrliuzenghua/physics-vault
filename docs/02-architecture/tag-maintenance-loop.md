# Tag Maintenance Loop

Question tags are a teachable retrieval signal. Agents may create and maintain
tags, but they should treat tag changes as metadata maintenance rather than
question-content editing.

## Workflow

1. Use `diagnose_tag_maintenance` to find near-duplicate tags and unused catalog
   tags.
2. Use `suggest_question_tags` when a question has strong method or content
   evidence but is missing teaching tags.
3. Use `maintain_question_tags` with `dry_run=true` to preview additions,
   removals, or alias merges.
4. Apply with `dry_run=false` only when the reason is clear enough to audit.

## Guardrails

- New high-confidence teaching tags can be added to `tag_catalog`.
- Similar tags can be merged through `merge_map`, for example
  `{"配速法": ["速度补偿法"]}`.
- Alias tags are marked as `merged` in `tag_catalog` instead of being silently
  forgotten.
- Tag updates refresh question embeddings and the derived method index.
- Ambiguous labels should remain suggestions until a teacher confirms them.

This keeps retrieval improving with use while avoiding tag sprawl.
