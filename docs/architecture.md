# Architecture

## Boundary

`research_app` is the active application. It does not import the deprecated `app` tree. PostgreSQL is the production store, pgvector supplies similarity candidate retrieval, and SQLite supplies isolated tests.

## Data flow

```text
thesis
  -> editable research plan
  -> approved propositions
  -> stored-evidence candidates (review only)
  -> broad-web discovery
  -> primary-source resolution
  -> normalized source chunks
  -> evidence extraction
  -> supports/challenges/mixed links
  -> evidence-review checkpoint
  -> deterministic Markdown dossier
```

Each external operation is represented by a `research_tasks` row whose input hash makes retries idempotent. Source bodies and chunks are stored once. Model usage is recorded in `research_runs`.

## Trust boundary

Vector similarity may suggest reusable evidence but cannot establish equivalence, polarity, truth, or an evidence relationship. A primary source and exact excerpt are required before a finding can become an evidence unit. Dossier prose is generated from stored evidence and remains renderable without external services.

## Main modules

- `models.py`: research schema and pgvector/SQLite embedding type.
- `repository.py`: persistence invariants, deduplication, task checkpoints, and retrieval candidates.
- `planner.py`: model-assisted or deterministic thesis decomposition.
- `sources.py`: HTML/PDF normalization and primary-source hints.
- `researcher.py`: resumable discovery, retrieval, extraction, and evidence checkpoint.
- `renderer.py`: deterministic cited Markdown dossier.
- `cli.py`: user-facing workflow and manual evidence tools.

