from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import math

from sqlalchemy import func, select

from .database import Database
from .domain import EvidenceDraft, ResearchPlan
from .models import (
    DiscoveryLink,
    EvidenceLink,
    EvidenceUnit,
    ProjectStatus,
    Proposition,
    ResearchProject,
    ResearchRun,
    ResearchTask,
    Source,
    SourceChunk,
    TaskStatus,
    ThesisVersion,
    utcnow,
)
from .utils import canonicalize_url, stable_hash
from .content_policy import classify_rights


class Repository:
    def __init__(self, database: Database):
        self.db = database

    def create_project(self, thesis: str, title: str | None = None) -> ResearchProject:
        thesis = thesis.strip()
        if not thesis:
            raise ValueError("Thesis cannot be empty")
        with self.db.session() as session:
            project = ResearchProject(title=title or thesis[:120])
            project.theses.append(ThesisVersion(version=1, text=thesis))
            session.add(project)
            session.flush()
            return project

    def project(self, project_id: str) -> ResearchProject:
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            if project is None:
                raise ValueError(f"Unknown project: {project_id}")
            _ = list(project.theses)
            _ = list(project.propositions)
            return project

    def current_thesis(self, project_id: str) -> ThesisVersion:
        with self.db.session() as session:
            thesis = session.scalar(
                select(ThesisVersion)
                .where(ThesisVersion.project_id == project_id)
                .order_by(ThesisVersion.version.desc())
                .limit(1)
            )
            if thesis is None:
                raise ValueError(f"Project {project_id} has no thesis")
            return thesis

    def mark_planned(self, project_id: str) -> None:
        self.set_project_status(project_id, ProjectStatus.PLANNED.value)

    def approve_plan(self, plan: ResearchPlan) -> int:
        with self.db.session() as session:
            project = session.get(ResearchProject, plan.project_id)
            if project is None:
                raise ValueError(f"Unknown project: {plan.project_id}")
            thesis = session.scalar(
                select(ThesisVersion)
                .where(ThesisVersion.project_id == plan.project_id)
                .order_by(ThesisVersion.version.desc())
                .limit(1)
            )
            if thesis is None or thesis.version != plan.thesis_version or thesis.text != plan.thesis:
                raise ValueError("Plan thesis does not match the project's current thesis version")
            old = session.scalars(
                select(Proposition).where(
                    Proposition.project_id == plan.project_id,
                    Proposition.thesis_version == plan.thesis_version,
                )
            ).all()
            for item in old:
                session.delete(item)
            session.flush()
            for item in plan.propositions:
                session.add(
                    Proposition(
                        project_id=plan.project_id,
                        thesis_version=plan.thesis_version,
                        plan_key=item.key,
                        text=item.text,
                        kind=item.kind,
                        polarity=item.polarity,
                        scope=item.scope,
                        approved=True,
                        search_queries=item.search_queries,
                        origin=item.origin,
                        review_status=item.review_status,
                        provenance=item.provenance,
                    )
                )
            project.status = ProjectStatus.APPROVED.value
            project.pause_requested = False
            project.settings = {
                **(project.settings or {}),
                "max_source_attempts": plan.max_source_attempts,
                "max_runtime_seconds": plan.max_runtime_seconds,
            }
            return len(plan.propositions)

    def revise_thesis(self, project_id: str, text: str, reason: str | None = None) -> ThesisVersion:
        text = text.strip()
        if not text:
            raise ValueError("Revised thesis cannot be empty")
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            if project is None:
                raise ValueError(f"Unknown project: {project_id}")
            version = session.scalar(
                select(func.max(ThesisVersion.version)).where(
                    ThesisVersion.project_id == project_id
                )
            ) or 0
            thesis = ThesisVersion(
                project_id=project_id,
                version=version + 1,
                text=text,
                revision_reason=reason,
            )
            session.add(thesis)
            project.status = ProjectStatus.DRAFT.value
            project.pause_requested = False
            session.flush()
            return thesis

    def propositions(self, project_id: str) -> list[Proposition]:
        thesis_version = self.current_thesis(project_id).version
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(Proposition)
                    .where(
                        Proposition.project_id == project_id,
                        Proposition.thesis_version == thesis_version,
                    )
                    .order_by(Proposition.plan_key)
                ).all()
            )

    def set_proposition_embedding(self, proposition_id: str, embedding: list[float], metadata: dict | None = None) -> None:
        with self.db.session() as session:
            proposition = session.get(Proposition, proposition_id)
            if proposition is None:
                raise ValueError(f"Unknown proposition: {proposition_id}")
            proposition.embedding = embedding
            proposition.embedding_metadata = metadata or {}

    def set_chunk_embeddings(self, embeddings: dict) -> None:
        with self.db.session() as session:
            for chunk_id, value in embeddings.items():
                chunk = session.get(SourceChunk, chunk_id)
                if chunk is not None:
                    embedding, metadata = value if isinstance(value, tuple) else (value, {})
                    chunk.embedding = embedding
                    chunk.embedding_metadata = metadata

    def set_source_embedding(self, source_id: str, embedding: list[float], metadata: dict) -> None:
        with self.db.session() as session:
            source = session.get(Source, source_id)
            if source is not None:
                source.embedding = embedding
                source.embedding_metadata = metadata

    def set_evidence_embedding(self, evidence_id: str, embedding: list[float], metadata: dict | None = None) -> None:
        with self.db.session() as session:
            evidence = session.get(EvidenceUnit, evidence_id)
            if evidence is not None:
                evidence.embedding = embedding
                evidence.embedding_metadata = metadata or {}

    def add_emergent_proposition(self, project_id: str, value: dict) -> Proposition:
        thesis_version = self.current_thesis(project_id).version
        with self.db.session() as session:
            count = session.scalar(select(func.count(Proposition.id)).where(Proposition.project_id == project_id)) or 0
            item = Proposition(
                project_id=project_id, thesis_version=thesis_version,
                plan_key=f"emergent_{count + 1}", text=value["text"],
                kind="empirical", polarity=value.get("polarity", "neutral"),
                scope=value.get("scope", {}), approved=True,
                search_queries=value.get("search_queries", []),
                origin="source_discovered", review_status="unreviewed",
                provenance=value.get("provenance", {}),
            )
            session.add(item); session.flush(); return item

    def save_synthesis(self, project_id: str, synthesis: dict) -> None:
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            project.settings = {**(project.settings or {}), "synthesis": synthesis}

    def synthesis(self, project_id: str) -> dict:
        return dict((self.project(project_id).settings or {}).get("synthesis", {}))

    def similar_evidence(
        self, embedding: list[float], limit: int = 10
    ) -> list[tuple[str, float]]:
        """Return candidates only; callers must never infer polarity from similarity."""
        with self.db.session() as session:
            if self.db.engine.dialect.name == "postgresql":
                rows = session.execute(
                    select(
                        EvidenceUnit.id,
                        EvidenceUnit.embedding.cosine_distance(embedding).label("distance"),
                    )
                    .where(EvidenceUnit.embedding.is_not(None))
                    .order_by("distance")
                    .limit(limit)
                ).all()
                return [(row[0], float(row[1])) for row in rows]
            evidence = session.scalars(
                select(EvidenceUnit).where(EvidenceUnit.embedding.is_not(None))
            ).all()
            scored = [
                (item.id, self._cosine_distance(embedding, item.embedding))
                for item in evidence
            ]
            return sorted(scored, key=lambda item: item[1])[:limit]

    @staticmethod
    def _cosine_distance(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 1.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 1.0
        return 1.0 - dot / (left_norm * right_norm)

    def set_project_status(self, project_id: str, status: str, pause: bool | None = None) -> None:
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            if project is None:
                raise ValueError(f"Unknown project: {project_id}")
            project.status = status
            if pause is not None:
                project.pause_requested = pause

    def should_pause(self, project_id: str) -> bool:
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            return bool(project and project.pause_requested)

    def research_pass(self, project_id: str) -> int:
        return int((self.project(project_id).settings or {}).get("research_pass", 1))

    def advance_research_pass(self, project_id: str) -> int:
        with self.db.session() as session:
            project = session.get(ResearchProject, project_id)
            if project is None:
                raise ValueError(f"Unknown project: {project_id}")
            current = int((project.settings or {}).get("research_pass", 1))
            if current >= 2:
                raise ValueError("The balanced pilot permits only one gap-filling pass")
            settings = dict(project.settings or {})
            settings["research_pass"] = current + 1
            project.settings = settings
            project.status = ProjectStatus.APPROVED.value
            project.pause_requested = False
            return current + 1

    def get_or_create_task(
        self,
        project_id: str,
        task_type: str,
        payload: dict,
        proposition_id: str | None = None,
    ) -> ResearchTask:
        input_hash = stable_hash(json.dumps(payload, sort_keys=True))
        with self.db.session() as session:
            task = session.scalar(
                select(ResearchTask).where(
                    ResearchTask.project_id == project_id,
                    ResearchTask.task_type == task_type,
                    ResearchTask.input_hash == input_hash,
                )
            )
            if task is None:
                task = ResearchTask(
                    project_id=project_id,
                    proposition_id=proposition_id,
                    task_type=task_type,
                    input_hash=input_hash,
                    payload=payload,
                )
                session.add(task)
                session.flush()
            return task

    def start_task(self, task_id: str) -> None:
        with self.db.session() as session:
            task = session.get(ResearchTask, task_id)
            task.status = TaskStatus.RUNNING.value
            task.attempts += 1
            task.error = None

    def complete_task(self, task_id: str, result: dict) -> None:
        with self.db.session() as session:
            task = session.get(ResearchTask, task_id)
            task.status = TaskStatus.COMPLETE.value
            task.result = result

    def fail_task(self, task_id: str, error: str) -> None:
        with self.db.session() as session:
            task = session.get(ResearchTask, task_id)
            task.status = TaskStatus.FAILED.value
            task.error = error

    def add_source(
        self,
        url: str,
        *,
        title: str | None = None,
        publisher: str | None = None,
        source_type: str = "unknown",
        is_primary: bool = False,
        identifier: str | None = None,
        metadata: dict | None = None,
        rights_status: str | None = None,
        detected_license: str | None = None,
    ) -> Source:
        canonical_url = canonicalize_url(url)
        with self.db.session() as session:
            source = session.scalar(
                select(Source).where(Source.canonical_url == canonical_url)
            )
            if source is None:
                source = Source(
                    canonical_url=canonical_url,
                    title=title,
                    publisher=publisher,
                    source_type=source_type,
                    is_primary=is_primary,
                    identifier=identifier,
                    metadata_=metadata or {},
                    rights_status=rights_status or classify_rights(canonical_url, detected_license)[0],
                    detected_license=detected_license,
                )
                session.add(source)
                session.flush()
            else:
                source.title = source.title or title
                source.publisher = source.publisher or publisher
                source.is_primary = source.is_primary or is_primary
                if source.source_type == "unknown" and source_type != "unknown":
                    source.source_type = source_type
                incoming = metadata or {}
                if rights_status:
                    source.rights_status = rights_status
                if detected_license:
                    source.detected_license = detected_license
                merged = dict(source.metadata_ or {})
                for key, value in incoming.items():
                    merged.setdefault(key, value)
                proposition_id = incoming.get("proposition_id")
                if proposition_id:
                    discovered_for = list(merged.get("discovered_for", []))
                    if proposition_id not in discovered_for:
                        discovered_for.append(proposition_id)
                    merged["discovered_for"] = discovered_for
                source.metadata_ = merged
            return source

    def store_source_content(
        self,
        source_id: str,
        content: str,
        chunks: list[tuple[str, str]],
        *,
        archive_chunks: list[tuple[str, str]] | None = None,
        access_metadata: dict | None = None,
    ) -> Source:
        normalized = "\n\n".join(part.strip() for part in content.split("\n\n") if part.strip())
        content_hash = stable_hash(normalized)
        with self.db.session() as session:
            duplicate = session.scalar(
                select(Source).where(
                    Source.content_hash == content_hash,
                    Source.id != source_id,
                )
            )
            if duplicate is not None:
                return duplicate
            source = session.get(Source, source_id)
            if source is None:
                raise ValueError(f"Unknown source: {source_id}")
            access = access_metadata or {}
            rights_status, detected_license = classify_rights(
                source.canonical_url, access.get("detected_license")
            )
            source.rights_status = access.get("rights_status", rights_status)
            source.detected_license = detected_license
            source.normalized_content = (
                normalized
                if source.rights_status in {"public_domain", "open_license", "permission"}
                else None
            )
            source.content_hash = content_hash
            source.retrieval_status = "retrieved"
            source.retrieved_at = utcnow()
            source.accessed_at = source.retrieved_at
            source.retrieval_permission = access.get("retrieval_permission", "public_http")
            source.robots_status = access.get("robots_status", "not_checked")
            source.terms_status = access.get("terms_status", "not_checked")
            source.chunks.clear()
            for ordinal, (locator, text) in enumerate(chunks):
                session.add(
                    SourceChunk(
                        source_id=source.id,
                        ordinal=ordinal,
                        locator=locator,
                        content=text,
                        content_hash=stable_hash(text),
                        token_count=access.get("token_counts", {}).get(stable_hash(text)),
                        relevance=access.get("relevance", {}).get(stable_hash(text), []),
                    )
                )
            session.flush()
            return source

    def source(self, source_id: str) -> Source:
        with self.db.session() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise ValueError(f"Unknown source: {source_id}")
            _ = list(source.chunks)
            return source

    def sources(self) -> list[Source]:
        with self.db.session() as session:
            return list(session.scalars(select(Source).order_by(Source.title)).all())

    def add_discovery_link(self, discovery_id: str, primary_id: str, context: str = "") -> None:
        with self.db.session() as session:
            existing = session.scalar(
                select(DiscoveryLink).where(
                    DiscoveryLink.discovery_source_id == discovery_id,
                    DiscoveryLink.primary_source_id == primary_id,
                )
            )
            if existing is None:
                session.add(
                    DiscoveryLink(
                        discovery_source_id=discovery_id,
                        primary_source_id=primary_id,
                        context=context,
                    )
                )

    def add_evidence(
        self,
        proposition_id: str,
        source_id: str,
        source_chunk_id: str,
        draft: EvidenceDraft,
        extraction_version: str = "manual-v1",
    ) -> EvidenceUnit:
        draft.validate()
        finding_hash = stable_hash(" ".join(draft.finding.lower().split()))
        with self.db.session() as session:
            source = session.get(Source, source_id)
            if source is None or not source.is_primary:
                raise ValueError("Final evidence must be attached to a primary source")
            chunk = session.get(SourceChunk, source_chunk_id)
            if chunk is None or chunk.source_id != source_id:
                raise ValueError("Evidence chunk does not belong to the selected source")
            normalized_excerpt = " ".join(draft.excerpt.split()).casefold()
            normalized_chunk = " ".join(chunk.content.split()).casefold()
            if normalized_excerpt not in normalized_chunk:
                raise ValueError("Evidence excerpt must occur verbatim in the stored source chunk")
            proposition = session.get(Proposition, proposition_id)
            if proposition is None:
                raise ValueError(f"Unknown proposition: {proposition_id}")
            evidence = session.scalar(
                select(EvidenceUnit).where(
                    EvidenceUnit.source_chunk_id == source_chunk_id,
                    EvidenceUnit.finding_hash == finding_hash,
                )
            )
            if evidence is None:
                evidence = EvidenceUnit(
                    source_id=source_id,
                    source_chunk_id=source_chunk_id,
                    finding=draft.finding,
                    finding_hash=finding_hash,
                    excerpt=draft.excerpt,
                    locator=draft.locator,
                    population=draft.population,
                    geography=draft.geography,
                    timeframe=draft.timeframe,
                    methodology=draft.methodology,
                    confidence=draft.confidence,
                    extraction_version=extraction_version,
                    source_url=source.canonical_url,
                    source_title=source.title,
                    source_publisher=source.publisher,
                    source_publication_date=source.publication_date,
                    source_accessed_at=source.accessed_at or source.retrieved_at,
                    source_rights_status=source.rights_status,
                    quote_word_count=len(draft.excerpt.split()),
                )
                session.add(evidence)
                session.flush()
            link = session.scalar(
                select(EvidenceLink).where(
                    EvidenceLink.proposition_id == proposition_id,
                    EvidenceLink.evidence_id == evidence.id,
                )
            )
            if link is None:
                session.add(
                    EvidenceLink(
                        proposition_id=proposition_id,
                        evidence_id=evidence.id,
                        relationship=draft.relationship,
                        explanation=draft.explanation,
                    )
                )
            return evidence

    def project_evidence(self, project_id: str) -> list[dict]:
        thesis_version = self.current_thesis(project_id).version
        with self.db.session() as session:
            rows = session.execute(
                select(Proposition, EvidenceLink, EvidenceUnit, Source)
                .join(EvidenceLink, EvidenceLink.proposition_id == Proposition.id)
                .join(EvidenceUnit, EvidenceUnit.id == EvidenceLink.evidence_id)
                .join(Source, Source.id == EvidenceUnit.source_id)
                .where(
                    Proposition.project_id == project_id,
                    Proposition.thesis_version == thesis_version,
                )
                .order_by(Proposition.plan_key, EvidenceLink.relationship, EvidenceUnit.finding)
            ).all()
            return [
                {
                    "proposition": proposition,
                    "link": link,
                    "evidence": evidence,
                    "source": source,
                }
                for proposition, link, evidence, source in rows
            ]

    def record_run(self, project_id: str, operation: str, **values) -> None:
        with self.db.session() as session:
            session.add(ResearchRun(project_id=project_id, operation=operation, **values))

    def status(self, project_id: str) -> dict:
        project = self.project(project_id)
        propositions = self.propositions(project_id)
        evidence = self.project_evidence(project_id)
        counts = Counter(row["link"].relationship for row in evidence)
        covered = {row["proposition"].id for row in evidence}
        with self.db.session() as session:
            task_rows = list(session.scalars(
                select(ResearchTask).where(ResearchTask.project_id == project_id)
            ).all())
            tasks = Counter(item.status for item in task_rows)
            runs = list(session.scalars(
                select(ResearchRun).where(ResearchRun.project_id == project_id)
            ).all())
            usage = session.execute(
                select(
                    func.coalesce(func.sum(ResearchRun.input_tokens), 0),
                    func.coalesce(func.sum(ResearchRun.output_tokens), 0),
                    func.coalesce(func.sum(ResearchRun.estimated_cost), 0.0),
                ).where(ResearchRun.project_id == project_id)
            ).one()
        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "thesis": self.current_thesis(project_id).text,
            "propositions": len(propositions),
            "covered_propositions": len(covered),
            "evidence": dict(counts),
            "tasks": dict(tasks),
            "input_tokens": usage[0],
            "output_tokens": usage[1],
            "estimated_cost": float(usage[2]),
            "model_calls": len([item for item in runs if item.provider in {"codex", "deepseek"}]),
            "failed_tasks": tasks.get("failed", 0),
            "postprocess_failures": sum(
                1 for item in task_rows if "postprocess_validation" in str(item.error or "")
            ),
            "evidence_items_received": sum(
                (item.result or {}).get("processing", {}).get("received_items", 0)
                for item in task_rows
            ),
            "evidence_items_accepted": sum(
                (item.result or {}).get("processing", {}).get("accepted_items", 0)
                for item in task_rows
            ),
        }

    def errors(self, project_id: str) -> list[dict]:
        with self.db.session() as session:
            tasks = session.scalars(
                select(ResearchTask).where(
                    ResearchTask.project_id == project_id,
                    ResearchTask.error.is_not(None),
                )
            ).all()
            return [
                {
                    "kind": "task", "task_id": item.id,
                    "task_type": item.task_type, "status": item.status,
                    "attempts": item.attempts, "error": item.error,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in tasks
            ]
