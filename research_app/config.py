from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Keep the CLI usable before optional dependencies are installed.
    def load_dotenv(path, override=False):
        path = Path(path)
        if not path.exists():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip("'\"")
            if override or key not in os.environ:
                os.environ[key] = value
        return True


@dataclass(frozen=True)
class Settings:
    store: str
    data_dir: Path
    database_url: str | None
    embedding_model: str
    codex_executable: str
    codex_timeout: int
    reasoning_provider: str = "deepseek"
    search_provider: str = "hybrid"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_timeout: int = 300
    deepseek_max_attempts: int = 3
    deepseek_thinking: bool = True
    deepseek_reasoning_effort: str = "high"
    debug_raw_responses: bool = True
    debug_dir: Path = Path("data/tmp/debug")
    embedding_provider: str = "none"
    openai_api_key: str | None = None
    embedding_chunk_tokens: int = 768
    embedding_chunk_overlap: int = 96
    embedding_chunk_hard_max: int = 1024
    embedding_batch_tokens: int = 16000
    source_passages_per_proposition: int = 3
    source_passage_cap: int = 32
    browser_provider: str = "none"
    browser_timeout: int = 30
    browser_max_actions: int = 5
    browser_max_pages: int = 3
    browser_max_download_mb: int = 25
    unpaywall_email: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / ".env", override=False)
        return cls(
            store=os.getenv("RESEARCH_STORE", "json"),
            data_dir=Path(os.getenv("RESEARCH_DATA_DIR", "data/tmp")),
            database_url=os.getenv("RESEARCH_DATABASE_URL"),
            embedding_model=os.getenv(
                "RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            embedding_provider=os.getenv(
                "RESEARCH_EMBEDDING_PROVIDER",
                "openai" if os.getenv("OPENAI_API_KEY") else "none",
            ).lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            embedding_chunk_tokens=int(os.getenv("RESEARCH_EMBEDDING_CHUNK_TOKENS", "768")),
            embedding_chunk_overlap=int(os.getenv("RESEARCH_EMBEDDING_CHUNK_OVERLAP", "96")),
            embedding_chunk_hard_max=int(os.getenv("RESEARCH_EMBEDDING_CHUNK_HARD_MAX", "1024")),
            embedding_batch_tokens=int(os.getenv("RESEARCH_EMBEDDING_BATCH_TOKENS", "16000")),
            source_passages_per_proposition=int(
                os.getenv("RESEARCH_SOURCE_PASSAGES_PER_PROPOSITION", "3")
            ),
            source_passage_cap=int(os.getenv("RESEARCH_SOURCE_PASSAGE_CAP", "32")),
            browser_provider=os.getenv("RESEARCH_BROWSER_PROVIDER", "none").lower(),
            browser_timeout=int(os.getenv("RESEARCH_BROWSER_TIMEOUT", "30")),
            browser_max_actions=int(os.getenv("RESEARCH_BROWSER_MAX_ACTIONS", "5")),
            browser_max_pages=int(os.getenv("RESEARCH_BROWSER_MAX_PAGES", "3")),
            browser_max_download_mb=int(os.getenv("RESEARCH_BROWSER_MAX_DOWNLOAD_MB", "25")),
            unpaywall_email=os.getenv("RESEARCH_UNPAYWALL_EMAIL"),
            reasoning_provider=os.getenv(
                "RESEARCH_REASONING_PROVIDER", "deepseek"
            ).lower(),
            search_provider=os.getenv(
                "RESEARCH_SEARCH_PROVIDER", "hybrid"
            ).lower(),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_model=os.getenv(
                "RESEARCH_DEEPSEEK_MODEL", "deepseek-v4-pro"
            ),
            deepseek_base_url=os.getenv(
                "RESEARCH_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ),
            deepseek_timeout=int(os.getenv("RESEARCH_DEEPSEEK_TIMEOUT", "300")),
            deepseek_max_attempts=int(
                os.getenv("RESEARCH_DEEPSEEK_MAX_ATTEMPTS", "3")
            ),
            deepseek_thinking=os.getenv("RESEARCH_DEEPSEEK_THINKING", "true").lower()
            in {"1", "true", "yes", "on"},
            deepseek_reasoning_effort=os.getenv(
                "RESEARCH_DEEPSEEK_REASONING_EFFORT", "high"
            ).lower(),
            debug_raw_responses=os.getenv("RESEARCH_DEBUG_RAW_RESPONSES", "true").lower()
            in {"1", "true", "yes", "on"},
            debug_dir=Path(os.getenv("RESEARCH_DEBUG_DIR", "data/tmp/debug")),
            codex_executable=os.getenv("RESEARCH_CODEX_EXECUTABLE", "codex"),
            codex_timeout=int(os.getenv("RESEARCH_CODEX_TIMEOUT", "300")),
        )
