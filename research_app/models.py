from __future__ import annotations

from datetime import datetime, timezone
import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Embedding(TypeDecorator):
    """Use pgvector in PostgreSQL and JSON in lightweight test databases."""

    impl = JSON
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):
        def cosine_distance(self, other):
            return self.expr.op("<=>", return_type=Float)(other)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(JSON())


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    APPROVED = "approved"
    RESEARCHING = "researching"
    PAUSED = "paused"
    EVIDENCE_REVIEW = "evidence_review"
    COMPLETE = "complete"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DRAFT.value)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    theses: Mapped[list[ThesisVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    propositions: Mapped[list[Proposition]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ThesisVersion(Base):
    __tablename__ = "thesis_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_thesis_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("research_projects.id"))
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[ResearchProject] = relationship(back_populates="theses")


class Proposition(Base):
    __tablename__ = "propositions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "thesis_version", "plan_key", name="uq_project_version_plan_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("research_projects.id"))
    thesis_version: Mapped[int] = mapped_column(Integer, default=1)
    plan_key: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="empirical")
    polarity: Mapped[str] = mapped_column(String(20), default="neutral")
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    search_queries: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(), nullable=True)
    embedding_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(32), default="planned")
    review_status: Mapped[str] = mapped_column(String(32), default="reviewed")
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[ResearchProject] = relationship(back_populates="propositions")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_source_canonical_url"),
        UniqueConstraint("content_hash", name="uq_source_content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_url: Mapped[str] = mapped_column(Text)
    identifier: Mapped[str | None] = mapped_column(String(240), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), default="unknown")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retrieval_status: Mapped[str] = mapped_column(String(32), default="lead")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(), nullable=True)
    embedding_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    rights_status: Mapped[str] = mapped_column(String(32), default="unknown")
    detected_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieval_permission: Mapped[str] = mapped_column(String(40), default="unknown")
    robots_status: Mapped[str] = mapped_column(String(40), default="not_checked")
    terms_status: Mapped[str] = mapped_column(String(40), default="not_checked")
    cache_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    chunks: Mapped[list[SourceChunk]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "ordinal", name="uq_source_chunk_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(), nullable=True)
    embedding_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    relevance: Mapped[list] = mapped_column(JSON, default=list)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped[Source] = relationship(back_populates="chunks")


class EvidenceUnit(Base):
    __tablename__ = "evidence_units"
    __table_args__ = (
        UniqueConstraint(
            "source_chunk_id", "finding_hash", name="uq_chunk_finding"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    source_chunk_id: Mapped[str] = mapped_column(ForeignKey("source_chunks.id"))
    finding: Mapped[str] = mapped_column(Text)
    finding_hash: Mapped[str] = mapped_column(String(64))
    excerpt: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(String(240))
    population: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(String(160), nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(160), nullable=True)
    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    extraction_version: Mapped[str] = mapped_column(String(40), default="manual-v1")
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(), nullable=True)
    embedding_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_rights_status: Mapped[str] = mapped_column(String(32), default="unknown")
    quote_word_count: Mapped[int] = mapped_column(Integer, default=0)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        UniqueConstraint("proposition_id", "evidence_id", name="uq_evidence_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    proposition_id: Mapped[str] = mapped_column(ForeignKey("propositions.id"))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_units.id"))
    relationship: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)


class DiscoveryLink(Base):
    __tablename__ = "discovery_links"
    __table_args__ = (
        UniqueConstraint("discovery_source_id", "primary_source_id", name="uq_discovery_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    discovery_source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    primary_source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    context: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "task_type", "input_hash", name="uq_task_input"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("research_projects.id"))
    proposition_id: Mapped[str | None] = mapped_column(
        ForeignKey("propositions.id"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("research_projects.id"))
    operation: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
