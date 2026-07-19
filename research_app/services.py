from __future__ import annotations

from typing import Any

from .config import Settings
from .content_policy import ChunkingConfig, TokenChunker, TokenCounter
from .json_repository import JsonRepository
from .providers import (
    CodexCliProvider,
    CodexWebSearchProvider,
    CompositeSearchProvider,
    CrossrefSearchProvider,
    DeepSeekProvider,
    EmptySearchProvider,
    OpenAIEmbeddingProvider,
    OpenAlexSearchProvider,
)
from .sources import (
    DisabledInteractiveRetriever,
    PlaywrightInteractiveRetriever,
    SourceRetriever,
)


def _option(options: Any, name: str, default=None):
    return getattr(options, name, default) if options is not None else default


def make_services(settings: Settings, options: Any = None):
    """Construct storage and provider services for both CLI and web entrypoints."""
    store = _option(options, "store") or settings.store
    data_dir = _option(options, "data_dir") or settings.data_dir
    if store == "json":
        repository = JsonRepository(data_dir)
    else:
        database_url = _option(options, "database_url") or settings.database_url
        if not database_url:
            raise ValueError("SQL storage requires RESEARCH_DATABASE_URL or --database-url")
        try:
            from .database import Database
            from .repository import Repository
        except ImportError as exc:
            raise ValueError("Install the `db` optional dependency for SQL storage") from exc
        database = Database(database_url)
        database.create_schema()
        repository = Repository(database)

    reasoning = _option(options, "reasoning_provider") or settings.reasoning_provider
    search_mode = _option(options, "search_provider") or settings.search_provider
    model = _option(options, "deepseek_model") or settings.deepseek_model

    codex = None
    if reasoning == "codex" or search_mode in {"codex", "hybrid"}:
        codex = CodexCliProvider(
            data_dir / "runtime",
            timeout=settings.codex_timeout,
            executable=settings.codex_executable,
        )
    if reasoning == "deepseek":
        ai = DeepSeekProvider(
            settings.deepseek_api_key,
            model=model,
            base_url=settings.deepseek_base_url,
            timeout=settings.deepseek_timeout,
            max_attempts=settings.deepseek_max_attempts,
            debug_dir=settings.debug_dir,
            debug_raw_responses=settings.debug_raw_responses,
            thinking=settings.deepseek_thinking,
            reasoning_effort=settings.deepseek_reasoning_effort,
        )
    else:
        ai = codex

    scholarly = [OpenAlexSearchProvider(), CrossrefSearchProvider()]
    if search_mode == "none":
        search = EmptySearchProvider()
    elif search_mode == "scholarly":
        search = CompositeSearchProvider(scholarly, provider_name="scholarly")
    elif search_mode == "codex":
        search = CompositeSearchProvider(
            [CodexWebSearchProvider(codex)], provider_name="codex"
        )
    elif search_mode == "hybrid":
        search = CompositeSearchProvider(
            [CodexWebSearchProvider(codex), *scholarly], provider_name="hybrid"
        )
    else:
        raise ValueError(f"Unknown search provider: {search_mode}")

    embedder = None
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        embedder = OpenAIEmbeddingProvider(
            settings.openai_api_key,
            model=settings.embedding_model,
            hard_max_tokens=settings.embedding_chunk_hard_max,
            batch_tokens=settings.embedding_batch_tokens,
        )
    return repository, ai, search, embedder


def make_retriever(settings: Settings, options: Any = None) -> SourceRetriever:
    browser_override = _option(options, "browser")
    browser_enabled = (
        browser_override
        if browser_override is not None
        else settings.browser_provider == "playwright"
    )
    interactive = (
        PlaywrightInteractiveRetriever(
            timeout=settings.browser_timeout,
            max_actions=settings.browser_max_actions,
            max_pages=settings.browser_max_pages,
            max_download_mb=settings.browser_max_download_mb,
        )
        if browser_enabled
        else DisabledInteractiveRetriever()
    )
    return SourceRetriever(
        timeout=settings.browser_timeout,
        interactive=interactive,
        unpaywall_email=settings.unpaywall_email,
        max_download_mb=settings.browser_max_download_mb,
        chunker=TokenChunker(
            TokenCounter(settings.embedding_model),
            ChunkingConfig(
                target_tokens=settings.embedding_chunk_tokens,
                overlap_tokens=settings.embedding_chunk_overlap,
                hard_max_tokens=settings.embedding_chunk_hard_max,
            ),
        ),
    )
