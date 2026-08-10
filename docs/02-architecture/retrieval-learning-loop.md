# Retrieval Learning Loop

This note documents the long-term learning loop for method retrieval.

## Teacher Feedback

When a teacher confirms a result, rejects a false positive, or reports a missed
question, use `record_method_retrieval_feedback`.

- `correct` and `missed` become high-priority positive evidence.
- `incorrect` becomes a hard negative for that method branch.
- Positive feedback can maintain method tags, up to three level-3 knowledge
  points, embeddings, and the derived method index.

## Learning Report

Use `method_retrieval_learning_report` to inspect the accumulated learning
state. It returns:

- teacher feedback counts;
- benchmark constraints derived from the latest feedback;
- high-confidence metadata maintenance candidates;
- recent feedback audit rows.

The report is read-only. It is intended to show the next maintenance targets
without changing canonical question content.

## Quality Gate

`scripts/maintenance/evaluate_method_retrieval.py --check` now includes teacher
feedback constraints. This means:

- questions marked `correct` or `missed` must appear in the top 50 method
  results for that branch;
- questions marked `incorrect` must not appear in confirmed method results;
- curated benchmark cases such as Q00000298 remain checked as before.

This makes retrieval quality improve with use: every teacher correction becomes
part of the next regression check instead of being a one-off local fix.
