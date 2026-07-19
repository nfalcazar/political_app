# Political Research

A personal research tool for testing US political-policy theses against primary-source evidence. The application builds a durable JSON evidence library and renders cited Markdown dossiers instead of producing a stream of news-derived claims.

The active application is `research_app`. The previous RSS fact-collection pipeline remains temporarily in `app` and is not imported by the new code; see [app/LEGACY_REMOVAL.md](app/LEGACY_REMOVAL.md).

## What it does

1. Accepts a thesis and creates a versioned research project.
2. Decomposes the thesis into editable empirical propositions and normative premises.
3. Requires approval before search or model calls.
4. Searches both stored evidence and the broad web.
5. Treats news and advocacy pages as discovery material, not final evidence.
6. Retrieves primary HTML/PDF sources once and stores stable cited chunks.
7. Preserves supporting, challenging, and mixed findings separately.
8. Pauses at an evidence-review checkpoint before further research.
9. Renders an offline Markdown dossier from stored evidence.

## Setup

Python 3.10 or newer and a configured reasoning provider are required. Use a
`DEEPSEEK_API_KEY` for the default provider, or set `RESEARCH_REASONING_PROVIDER=codex`
and authenticate the Codex CLI. No database or OpenAI API key is required.

```bash
uv sync --extra dev
cp .env.example .env
codex login status
research doctor
research errors PROJECT_ID
```

### Local web prototype

Install the API extra and start the citizen-facing policy-claim interface:

```bash
uv sync --extra dev --extra api
research-web
```

Open `http://127.0.0.1:8000`. The web prototype supports the JSON store only and
binds to localhost. Submitting a claim authorizes one automatically generated,
bounded research plan with up to ten proposition-relevant, usable documents, thirty
queries, and ten minutes of runtime. The evidence brief still selects at most five key
sources. The generated scope remains visible in the
project's “How this was researched” panel.

Research runs in a durable single-worker queue. Closing the server marks unfinished
jobs as interrupted; restart the server and use Resume to continue from stored tasks.
Follow-up chat is evidence-bounded and never launches new web research implicitly.
Use the explicit Research gaps action for the one permitted continuation pass.

The default store is `data/tmp`. Project records, durable tasks, reusable sources, normalized source chunks, and evidence units are written as ignored, human-readable JSON. Writes use locks and atomic replacement.

## First workflow

For a guided start, provide a topic or omit it and answer the prompt. The CLI proposes
balanced research directions and accepts individual numbers, comma-separated choices,
ranges such as `1,3-5`, or `all`:

```bash
research guide "How does public transit investment affect US cities?"
```

The guided command writes an editable plan containing only the selected directions. It
prints the project ID and the exact `approve` and `run` commands, but does not execute
either step. Use `--heuristic` for suggestions without a model call.

The equivalent manual workflow starts by creating a project:

```bash
research new \
  "Greater worker unionization improves economic outcomes for US workers and reduces inequality without imposing larger economy-wide costs." \
  --title "The economic case for labor unions"

research plan PROJECT_ID
```

When `research plan` runs in a terminal, it displays the proposed empirical claims,
counterarguments, and normative premises and asks which numbered directions to keep.
Use `--no-interactive` to write the complete generated plan without prompting, such as
from a script or CI job. Use `--interactive` to force the picker when input is piped.

After choosing directions, review and edit the JSON plan before approving it:

```bash
research approve PROJECT_ID data/tmp/projects/PROJECT_ID/research_plan.json
research run PROJECT_ID
research status PROJECT_ID
research graph PROJECT_ID
research render PROJECT_ID
```

By default, the generated plan lives at `data/tmp/projects/PROJECT_ID/research_plan.json`; use that path in `research approve`. The first `run` performs at most three batched discovery calls and stops at evidence review. After inspecting coverage, `research continue PROJECT_ID` authorizes one gap-filling pass of at most two additional discovery calls.

If the evidence is adverse or incomplete, choose explicitly:

```bash
research pause PROJECT_ID
research revise PROJECT_ID "A narrower thesis" --reason "Initial evidence was sector-specific"
# or
research continue PROJECT_ID
```

Use `--heuristic` to generate a deterministic plan without a model call. Sources and reviewed evidence can also be added manually:

```bash
research source add https://www.bls.gov/example --primary --type government_data
research source fetch SOURCE_ID
research source list
research source block example.com --reason "source-owner request"
research source rights SOURCE_ID open_license --license "CC BY 4.0" --basis "License shown on source page"
research source purge-cache SOURCE_ID
research source takedown SOURCE_ID --reason "source-owner request"
research evidence add PROJECT_ID wages SOURCE_ID CHUNK_ID \
  --finding "Narrow finding" \
  --excerpt "Exact source text" \
  --locator "Table 2" \
  --relationship supports \
  --explanation "Why this finding bears on the proposition"
```

## Configuration

- `RESEARCH_STORE`: `json` by default; set `sql` only after installing the `db` extra.
- `RESEARCH_DATA_DIR`: JSON workspace, default `data/tmp`.
- `RESEARCH_CODEX_EXECUTABLE`: Codex executable, default `codex`.
- `RESEARCH_CODEX_TIMEOUT`: per-call timeout in seconds, default 300.
- `RESEARCH_REASONING_PROVIDER`: `deepseek` (default) or `codex`.
- `RESEARCH_SEARCH_PROVIDER`: `hybrid` (default), `scholarly`, `codex`, or `none`.
- `DEEPSEEK_API_KEY`: DeepSeek API key, loaded from `political_app/.env` or the shell.
- `RESEARCH_DEEPSEEK_MODEL`: DeepSeek model, default `deepseek-v4-pro`.
- `RESEARCH_DEEPSEEK_THINKING`: enable DeepSeek thinking mode, default `true`.
- `RESEARCH_DEEPSEEK_REASONING_EFFORT`: `high` (default) or `max`.
- `RESEARCH_EMBEDDING_PROVIDER`: `openai` when `OPENAI_API_KEY` is present, otherwise `none`.
- `RESEARCH_EMBEDDING_MODEL`: embedding model, default `text-embedding-3-small`.
- `RESEARCH_EMBEDDING_CHUNK_TOKENS`: target chunk size, default 768 tokens.
- `RESEARCH_EMBEDDING_CHUNK_OVERLAP`: adjacent chunk overlap, default 96 tokens.
- `RESEARCH_EMBEDDING_CHUNK_HARD_MAX`: local per-input ceiling, default 1024 tokens.
- `RESEARCH_EMBEDDING_BATCH_TOKENS`: local aggregate batch ceiling, default 16000 tokens.
- `RESEARCH_SOURCE_PASSAGES_PER_PROPOSITION`: passages retained per proposition, default 3.
- `RESEARCH_SOURCE_PASSAGE_CAP`: non-evidence passage cap per source, default 32.
- `RESEARCH_BROWSER_PROVIDER`: `none` (default) or `playwright` for the guarded JavaScript fallback.
- `RESEARCH_BROWSER_TIMEOUT`: per-browser-attempt ceiling, default 30 seconds.
- `RESEARCH_BROWSER_MAX_ACTIONS`: allowlisted actions per page, default 5.
- `RESEARCH_BROWSER_MAX_PAGES`: public pages per browser attempt, default 3.
- `RESEARCH_BROWSER_MAX_DOWNLOAD_MB`: retrieval/download ceiling, default 25 MB.
- `RESEARCH_UNPAYWALL_EMAIL`: email used for authorized Unpaywall DOI resolution.
- `RESEARCH_DEBUG_RAW_RESPONSES`: retain full DeepSeek prompts/responses for debugging, default `true`.
- `RESEARCH_DEBUG_DIR`: diagnostic artifact directory, default `data/tmp/debug`.
- `RESEARCH_WEB_PORT`: local web port, default `8000`; the host remains `127.0.0.1`.

Provider choices can also be overridden globally per invocation, for example:

```bash
research --reasoning-provider deepseek --search-provider hybrid plan PROJECT_ID
research --reasoning-provider deepseek --search-provider none run PROJECT_ID
```

Bound an autonomous run by proposition-relevant usable documents and wall-clock time.
Failed, thin, or irrelevant retrievals are still counted and reported, but do not
consume `--max-sources`:

```bash
research run PROJECT_ID --max-sources 25 --max-runtime 20m --max-queries 100
```

Search work is stored atomically in `query_graph.json` and resumes without rerunning
completed nodes. Five seed branches cover primary evidence, official records, scholarly
research, counterevidence, and mechanisms; failed retrievals add bounded recovery nodes.
Inspect the queue with `research graph PROJECT_ID --json`. The default query ceiling is
`max(30, max_sources * 4)`.

Static retrieval uses Trafilatura with the high-recall parser fallback, DOI alternates,
public document-link adapters, and pypdf. PyMuPDF is available through the `documents`
extra for malformed PDFs. To opt into the isolated browser fallback:

```bash
uv sync --extra browser
playwright install chromium
research run PROJECT_ID --browser
```

The browser uses a fresh context with no credentials or shared cookies. It only permits
same-origin expansion, tabs, public pagination, cookie-overlay dismissal, and public
downloads; it is never attempted for access denials, paywalls, CAPTCHAs, or robots
denials. Run `research benchmark PROJECT_ID` for a no-network report based on recorded
retrieval history.

OpenAI embeddings are cached independently of the reasoning provider. DeepSeek remains responsible for evidence judgment, emergent-proposition classification, and the stored findings abstract.
- `RESEARCH_DATABASE_URL`: required only for `--store sql`.

Codex subprocesses are ephemeral, read-only, noninteractive, schema-constrained, and launched with an allowlisted environment. Live web search is enabled only for discovery. Retrieved source excerpts are explicitly treated as untrusted input.

## Research strategy

- A durable priority query graph covers official data, original academic research, counterevidence, mechanisms, historical context, citation chasing, and retrieval recovery.
- Deterministic code enforces normalized-query deduplication, depth, source, runtime, query, and no-novelty limits; the reasoning model may only propose schema-constrained expansions.
- Secondary pages may reveal citations but are traversed by only one hop and never become evidence.
- URLs are fetched only when they are not blocklisted and robots policy permits retrieval; paywalls and access controls are not bypassed.
- Full text is placed in a private gzip cache. Unknown/copyrighted caches expire within 24 hours and are deleted after extraction; public-domain, licensed, or permitted archives may persist.
- Only proposition-relevant context passages, concise verified quotations, summaries, provenance, and original-source links remain in normal records.
- Token-aware chunks are capped at 1024 tokens and routed semantically when OpenAI embeddings are configured, with lexical matching as the offline fallback.
- Exact excerpts are verified against stored chunks before an evidence unit is accepted.
- Supporting, challenging, and mixed evidence remain separate; gap searches target uncovered or one-sided propositions.

Catalog indexes can be reconstructed from authoritative source files:

```bash
research catalog rebuild
research catalog migrate-storage
```

PostgreSQL/pgvector remains available as an optional adapter:

```bash
uv sync --extra db
research --store sql --database-url postgresql+psycopg2://... status PROJECT_ID
```

## Verification

```bash
.venv/bin/pytest
```

The default tests use temporary JSON workspaces and a fake Codex executable. SQL compatibility tests use SQLite when the development dependencies are installed. No network access or account usage is required by the test suite.
