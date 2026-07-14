# Political Research

A personal research tool for testing US political-policy theses against primary-source evidence. The application builds a durable evidence library and renders cited Markdown dossiers instead of producing a stream of news-derived claims.

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

Python 3.10 or newer and PostgreSQL with pgvector are recommended. SQLite is supported for local evaluation and tests.

```bash
uv sync --extra dev
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d
```

Configure `RESEARCH_DATABASE_URL` in `.env`. The CLI automatically creates missing research tables. Existing prototype claim/source tables are not read or migrated.

## First workflow

```bash
research new \
  "Greater worker unionization improves economic outcomes for US workers and reduces inequality without imposing larger economy-wide costs." \
  --title "The economic case for labor unions"

research plan PROJECT_ID --output outputs/PROJECT_ID/research_plan.json
```

Review and edit the JSON plan before approving it:

```bash
research approve PROJECT_ID outputs/PROJECT_ID/research_plan.json
research run PROJECT_ID
research status PROJECT_ID
research render PROJECT_ID
```

If the evidence is adverse or incomplete, choose explicitly:

```bash
research pause PROJECT_ID
research revise PROJECT_ID "A narrower thesis" --reason "Initial evidence was sector-specific"
# or
research continue PROJECT_ID
```

Without API credentials, plan generation uses a deterministic decomposition and `run` advances to evidence review without external calls. Sources and reviewed evidence can still be added manually:

```bash
research source add https://www.bls.gov/example --primary --type government_data
research source fetch SOURCE_ID
research source list
research evidence add PROJECT_ID wages SOURCE_ID CHUNK_ID \
  --finding "Narrow finding" \
  --excerpt "Exact source text" \
  --locator "Table 2" \
  --relationship supports \
  --explanation "Why this finding bears on the proposition"
```

## Configuration

- `RESEARCH_DATABASE_URL`: SQLAlchemy database URL.
- `OPENAI_API_KEY` or `OPENAI_KEY`: enables model planning, extraction, and embeddings.
- `G_SEARCH_API_KEY` and `G_SEARCH_ENG_ID`: enable Google Custom Search discovery.
- `RESEARCH_MODEL`: model used for planning and extraction.
- `RESEARCH_EMBEDDING_MODEL`: embedding model; PostgreSQL vectors are 1536 dimensions.
- `RESEARCH_MAX_SEARCHES`: maximum searches in one run.
- `RESEARCH_INPUT_COST_PER_MILLION` and `RESEARCH_OUTPUT_COST_PER_MILLION`: optional model rates used for cost estimates. Defaults to zero rather than embedding potentially stale pricing.

## Verification

```bash
.venv/bin/pytest
```

The tests use SQLite and do not require network access or API credentials.
