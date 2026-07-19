# Architecture

## Boundary

`research_app` is the active application. It does not import the deprecated `app` tree. The default repository is an atomic JSON workspace under `data/tmp`. PostgreSQL/pgvector remains an optional adapter.

## Data flow

```text
thesis
  -> web auto-plan or guided/terminal plan direction selection
  -> editable research plan
  -> approved propositions
  -> local lexical evidence candidates (review only)
  -> durable priority query graph
  -> hybrid web/scholarly discovery
  -> DOI and public alternate-location resolution
  -> static extraction, host adapters, optional guarded browser rendering
  -> rights/access classification and token-safe temporary cache
  -> proposition-relevant retained passages
  -> evidence extraction
  -> supports/challenges/mixed links
  -> evidence-review checkpoint
  -> deterministic Markdown dossier
```

Each external operation is represented by a durable JSON task whose input hash makes retries idempotent. Query nodes are written atomically to each project's `query_graph.json`; completed searches resume without repetition and failed retrievals produce bounded recovery branches. Full source bodies are not an unrestricted permanent library: copyrighted or unknown-rights bodies are private temporary gzip caches, while selected context passages and accepted quotations remain durable.

## Trust boundary

Lexical or vector similarity may suggest reusable evidence but cannot establish equivalence, polarity, truth, or an evidence relationship. A fetched primary source and locally verified exact excerpt are required before a finding can become an evidence unit. Dossiers remain renderable without external services.

## Main modules

- `json_repository.py`: default atomic persistence, query-graph checkpoints, retrieval history, deduplication, recovery, and lexical candidates.
- `query_graph.py`: seed families, normalized query validation, depth limits, and graph node construction.
- `repository.py`: optional SQL persistence adapter.
- `planner.py`: model-assisted or deterministic thesis decomposition.
- `sources.py`: safe URL preflight, DOI alternates, Trafilatura/high-recall HTML extraction, host document adapters, PDF fallbacks, and optional isolated Playwright rendering.
- `content_policy.py`: conservative rights classification, cache expiry, token counting, and hard-bounded chunking.
- `providers.py`: isolated DeepSeek/Codex reasoning, optional Codex web search, OpenAlex/Crossref scholarly discovery, and provider composition.
- `researcher.py`: budgeted graph scheduling, citation resolution, retrieval recovery, semantic routing, extraction, and evidence checkpoints.
- `renderer.py`: deterministic cited Markdown dossier.
- `cli.py`: guided direction selection, user-facing workflow, and manual evidence tools.
- `services.py`: shared CLI/web provider, storage, and retrieval construction.
- `jobs.py`: persisted single-worker web research lifecycle and restart recovery.
- `briefs.py` and `chat.py`: citation-validated citizen brief selection and evidence-bounded follow-up answers.
- `web.py`: localhost FastAPI surface and dependency-free browser interface.

## Local web boundary

The web prototype uses only the atomic JSON repository and one research worker. API
requests enqueue bounded jobs and poll durable project/job records rather than waiting
for research to finish. A submitted claim is authorization for the initial generated
plan; the plan scope remains inspectable. Follow-up answers can cite only accepted
evidence IDs already attached to the project. New searches require the explicit,
single gap-filling continuation action.
