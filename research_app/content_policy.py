from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit


RIGHTS_STATUSES = {
    "public_domain",
    "open_license",
    "permission",
    "copyrighted",
    "unknown",
    "restricted",
}

US_FEDERAL_HOSTS = (
    "archives.gov",
    "bls.gov",
    "census.gov",
    "congress.gov",
    "gao.gov",
    "govinfo.gov",
    "history.state.gov",
    "justice.gov",
    "state.gov",
    "supremecourt.gov",
    "uscourts.gov",
    "uscode.house.gov",
)


def classify_rights(url: str, detected_license: str | None = None) -> tuple[str, str | None]:
    """Return a conservative storage classification, not a legal conclusion."""
    license_value = (detected_license or "").strip()
    lower_license = license_value.casefold()
    if any(marker in lower_license for marker in ("creativecommons.org", "cc by", "cc0")):
        return "open_license", license_value
    host = urlsplit(url).netloc.casefold().split(":", 1)[0]
    if any(host == item or host.endswith(f".{item}") for item in US_FEDERAL_HOSTS):
        return "public_domain", None
    return "unknown", license_value or None


def cache_expiry(rights_status: str, *, now: datetime | None = None) -> str | None:
    if rights_status in {"public_domain", "open_license", "permission"}:
        return None
    current = now or datetime.now(timezone.utc)
    return (current + timedelta(hours=24)).isoformat()


def is_expired(value: str | None, *, now: datetime | None = None) -> bool:
    if not value:
        return False
    expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return expires <= (now or datetime.now(timezone.utc))


class TokenCounter:
    def __init__(self, model: str = "text-embedding-3-small"):
        try:
            import tiktoken

            try:
                self.encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                self.encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            self.encoding = None

    def encode(self, text: str) -> list[int]:
        if self.encoding is not None:
            return self.encoding.encode(text)
        # Conservative fallback: byte-sized units cannot undercount UTF-8 tokens.
        return list(text.encode("utf-8"))

    def decode(self, tokens: list[int]) -> str:
        if self.encoding is not None:
            return self.encoding.decode(tokens)
        return bytes(tokens).decode("utf-8", errors="ignore")

    def count(self, text: str) -> int:
        return len(self.encode(text))


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 768
    overlap_tokens: int = 96
    hard_max_tokens: int = 1024

    def __post_init__(self):
        if not 0 <= self.overlap_tokens < self.target_tokens <= self.hard_max_tokens:
            raise ValueError("Chunk token limits must satisfy overlap < target <= hard maximum")


class TokenChunker:
    def __init__(self, counter: TokenCounter | None = None, config: ChunkingConfig | None = None):
        self.counter = counter or TokenCounter()
        self.config = config or ChunkingConfig()

    def split(self, text: str, locator: str) -> list[tuple[str, str]]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        tokens = self.counter.encode(normalized)
        if len(tokens) <= self.config.hard_max_tokens:
            return [(locator, normalized)]
        chunks: list[tuple[str, str]] = []
        start = 0
        part = 1
        while start < len(tokens):
            end = min(start + self.config.target_tokens, len(tokens))
            if end < len(tokens):
                candidate = self.counter.decode(tokens[start:end])
                boundaries = [match.end() for match in re.finditer(r"[.!?](?:[\"')\]]*)\s+", candidate)]
                if boundaries:
                    boundary_tokens = self.counter.encode(candidate[: boundaries[-1]])
                    if len(boundary_tokens) >= self.config.target_tokens // 2:
                        end = start + len(boundary_tokens)
            piece = self.counter.decode(tokens[start:end]).strip()
            if piece:
                chunks.append((f"{locator}, part {part}", piece))
                part += 1
            if end >= len(tokens):
                break
            start = max(start + 1, end - self.config.overlap_tokens)
        if any(self.counter.count(piece) > self.config.hard_max_tokens for _, piece in chunks):
            raise ValueError(f"Token chunker exceeded hard maximum for {locator}")
        return chunks


def excessive_summary_overlap(summary: str, excerpt: str) -> bool:
    """Flag near-copy summaries while allowing short factual phrases."""
    from difflib import SequenceMatcher

    left = " ".join(summary.casefold().split())
    right = " ".join(excerpt.casefold().split())
    return len(left) >= 80 and SequenceMatcher(None, left, right).ratio() >= 0.82

