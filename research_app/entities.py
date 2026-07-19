from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectRecord:
    id: str
    title: str
    status: str = "draft"
    pause_requested: bool = False
    research_pass: int = 1
    max_source_attempts: int = 20
    max_runtime_seconds: int = 900
    synthesis: dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class ThesisRecord:
    id: str
    project_id: str
    version: int
    text: str
    revision_reason: str | None = None
    created_at: str = field(default_factory=now_iso)


@dataclass
class PropositionRecord:
    id: str
    project_id: str
    thesis_version: int
    plan_key: str
    text: str
    kind: str = "empirical"
    polarity: str = "neutral"
    scope: dict = field(default_factory=dict)
    approved: bool = False
    search_queries: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    embedding_metadata: dict = field(default_factory=dict)
    origin: str = "planned"
    review_status: str = "reviewed"
    provenance: dict = field(default_factory=dict)


@dataclass
class TaskRecord:
    id: str
    project_id: str
    task_type: str
    input_hash: str
    payload: dict
    proposition_id: str | None = None
    status: str = "pending"
    attempts: int = 0
    result: dict = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class WebJobRecord:
    id: str
    project_id: str
    mode: str
    state: str = "pending"
    limits: dict = field(default_factory=dict)
    attempts: int = 0
    result: dict = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class ChatMessageRecord:
    id: str
    project_id: str
    role: str
    content: str
    citations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    needs_additional_research: bool = False
    created_at: str = field(default_factory=now_iso)


@dataclass
class QueryNodeRecord:
    id: str
    project_id: str
    query: str
    query_kind: str
    proposition_ids: list[str] = field(default_factory=list)
    target_stance: str = "unknown"
    target_source_class: str = "primary"
    parent_id: str | None = None
    expansion_reason: str = "seed"
    depth: int = 0
    priority: float = 0.0
    provider: str | None = None
    status: str = "pending"
    attempts: int = 0
    result_source_ids: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class SourceChunkRecord:
    id: str
    source_id: str
    ordinal: int
    locator: str
    content: str
    content_hash: str
    embedding: list[float] | None = None
    embedding_metadata: dict = field(default_factory=dict)
    relevance: list[dict] = field(default_factory=list)
    token_count: int | None = None


@dataclass
class SourceRecord:
    id: str
    canonical_url: str
    identifier: str | None = None
    title: str | None = None
    publisher: str | None = None
    source_type: str = "unknown"
    is_primary: bool = False
    publication_date: str | None = None
    retrieval_status: str = "lead"
    content_hash: str | None = None
    normalized_content: str | None = None
    retrieved_at: str | None = None
    metadata_: dict = field(default_factory=dict)
    chunks: list[SourceChunkRecord] = field(default_factory=list)
    embedding: list[float] | None = None
    embedding_metadata: dict = field(default_factory=dict)
    rights_status: str = "unknown"
    detected_license: str | None = None
    accessed_at: str | None = None
    retrieval_permission: str = "unknown"
    robots_status: str = "not_checked"
    terms_status: str = "not_checked"
    cache_metadata: dict = field(default_factory=dict)
    retrieval_history: list[dict] = field(default_factory=list)
    needs_ocr: bool = False


@dataclass
class EvidenceRecord:
    id: str
    source_id: str
    source_chunk_id: str
    finding: str
    finding_hash: str
    excerpt: str
    locator: str
    population: str | None = None
    geography: str | None = None
    timeframe: str | None = None
    methodology: str | None = None
    confidence: str = "medium"
    extraction_version: str = "manual-v1"
    embedding: list[float] | None = None
    embedding_metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    source_url: str | None = None
    source_title: str | None = None
    source_publisher: str | None = None
    source_publication_date: str | None = None
    source_accessed_at: str | None = None
    source_rights_status: str = "unknown"
    quote_word_count: int = 0


@dataclass
class EvidenceLinkRecord:
    id: str
    proposition_id: str
    evidence_id: str
    relationship: str
    explanation: str


def record_dict(value):
    return asdict(value)
