from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    output_dir: Path
    openai_api_key: str | None
    openai_model: str
    embedding_model: str
    google_api_key: str | None
    google_engine_id: str | None
    max_searches_per_run: int
    input_cost_per_million: float
    output_cost_per_million: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "RESEARCH_DATABASE_URL",
                "sqlite:///political_research.db",
            ),
            output_dir=Path(os.getenv("RESEARCH_OUTPUT_DIR", "outputs")),
            openai_api_key=os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("RESEARCH_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv(
                "RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            google_api_key=os.getenv("G_SEARCH_API_KEY"),
            google_engine_id=os.getenv("G_SEARCH_ENG_ID"),
            max_searches_per_run=int(os.getenv("RESEARCH_MAX_SEARCHES", "12")),
            input_cost_per_million=float(
                os.getenv("RESEARCH_INPUT_COST_PER_MILLION", "0")
            ),
            output_cost_per_million=float(
                os.getenv("RESEARCH_OUTPUT_COST_PER_MILLION", "0")
            ),
        )
