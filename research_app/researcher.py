from __future__ import annotations

from dataclasses import asdict
import json
import re

from .domain import EvidenceDraft
from .models import ProjectStatus, TaskStatus
from .repository import Repository
from .sources import SourceRetriever, infer_source_type, looks_primary


class ResearchEngine:
    def __init__(
        self,
        repository: Repository,
        *,
        search=None,
        ai=None,
        retriever: SourceRetriever | None = None,
        model: str | None = None,
        embedding_model: str = "text-embedding-3-small",
        max_searches: int = 12,
    ):
        self.repository = repository
        self.search = search
        self.ai = ai
        self.retriever = retriever or SourceRetriever()
        self.model = model
        self.embedding_model = embedding_model
        self.max_searches = max_searches

    def run(self, project_id: str) -> dict:
        project = self.repository.project(project_id)
        if project.status not in {
            ProjectStatus.APPROVED.value,
            ProjectStatus.RESEARCHING.value,
            ProjectStatus.PAUSED.value,
        }:
            raise ValueError(
                "Research requires an approved plan. Use `research plan` and `research approve` first."
            )
        self.repository.set_project_status(
            project_id, ProjectStatus.RESEARCHING.value, pause=False
        )
        searched = 0
        discovered = 0
        retrieved = 0
        extracted = 0
        reusable_candidates = 0

        if self.ai is not None:
            reusable_candidates = self._search_stored_evidence(project_id)

        if self.search is not None:
            for proposition in self.repository.propositions(project_id):
                if proposition.kind != "empirical":
                    continue
                for query in proposition.search_queries:
                    if searched >= self.max_searches or self.repository.should_pause(project_id):
                        break
                    result = self._run_search(project_id, proposition.id, query)
                    searched += int(result["performed"])
                    discovered += result["discovered"]
                if searched >= self.max_searches or self.repository.should_pause(project_id):
                    break

        if self.repository.should_pause(project_id):
            self.repository.set_project_status(
                project_id, ProjectStatus.PAUSED.value, pause=True
            )
            return {"searched": searched, "discovered": discovered, "paused": True}

        # Retrieval and extraction are independent, idempotent tasks.
        for source in self.repository.sources():
            if not source.is_primary or source.retrieval_status == "retrieved":
                continue
            if self.repository.should_pause(project_id):
                break
            if self._retrieve(project_id, source.id):
                retrieved += 1

        if self.ai is not None:
            for proposition in self.repository.propositions(project_id):
                if proposition.kind != "empirical":
                    continue
                for source in self.repository.sources():
                    if not source.is_primary or source.retrieval_status != "retrieved":
                        continue
                    if self.repository.should_pause(project_id):
                        break
                    extracted += self._extract(project_id, proposition.id, source.id)

        paused = self.repository.should_pause(project_id)
        self.repository.set_project_status(
            project_id,
            ProjectStatus.PAUSED.value if paused else ProjectStatus.EVIDENCE_REVIEW.value,
            pause=paused,
        )
        return {
            "searched": searched,
            "discovered": discovered,
            "retrieved": retrieved,
            "evidence_extracted": extracted,
            "reusable_evidence_candidates": reusable_candidates,
            "paused": paused,
            "search_configured": self.search is not None,
            "ai_configured": self.ai is not None,
        }

    def _search_stored_evidence(self, project_id: str) -> int:
        propositions = [
            item for item in self.repository.propositions(project_id) if item.kind == "empirical"
        ]
        if not propositions:
            return 0
        missing = [item for item in propositions if item.embedding is None]
        if missing:
            vectors, usage = self.ai.embeddings(
                [item.text for item in missing], model=self.embedding_model
            )
            for item, vector in zip(missing, vectors):
                self.repository.set_proposition_embedding(item.id, vector)
                item.embedding = vector
            self.repository.record_run(
                project_id,
                "embed_propositions",
                provider="openai",
                model=self.embedding_model,
                input_tokens=usage.input_tokens,
                estimated_cost=usage.estimated_cost,
            )
        candidate_count = 0
        for proposition in propositions:
            task = self.repository.get_or_create_task(
                project_id,
                "stored_evidence_search",
                {"proposition_id": proposition.id, "version": "v1"},
                proposition_id=proposition.id,
            )
            if task.status == TaskStatus.COMPLETE.value:
                candidate_count += len(task.result.get("candidates", []))
                continue
            self.repository.start_task(task.id)
            candidates = [
                {"evidence_id": evidence_id, "distance": distance}
                for evidence_id, distance in self.repository.similar_evidence(
                    proposition.embedding, limit=10
                )
                if distance <= 0.25
            ]
            # Similarity proposes review candidates; it never determines support or polarity.
            self.repository.complete_task(task.id, {"candidates": candidates})
            candidate_count += len(candidates)
        return candidate_count

    def _run_search(self, project_id: str, proposition_id: str, query: str) -> dict:
        task = self.repository.get_or_create_task(
            project_id,
            "web_search",
            {"query": query},
            proposition_id=proposition_id,
        )
        if task.status == TaskStatus.COMPLETE.value:
            return {"performed": False, "discovered": len(task.result.get("source_ids", []))}
        self.repository.start_task(task.id)
        try:
            results = self.search.search(query)
            source_ids = []
            for item in results:
                primary = looks_primary(item["url"])
                source = self.repository.add_source(
                    item["url"],
                    title=item.get("title"),
                    publisher=item.get("display_link"),
                    source_type=infer_source_type(item["url"]),
                    is_primary=primary,
                    metadata={"search_query": query, "snippet": item.get("snippet")},
                )
                source_ids.append(source.id)
                if not primary:
                    self._discover_primary_links(project_id, source.id)
            self.repository.complete_task(task.id, {"source_ids": source_ids})
            return {"performed": True, "discovered": len(source_ids)}
        except Exception as exc:
            self.repository.fail_task(task.id, str(exc))
            return {"performed": True, "discovered": 0}

    def _discover_primary_links(self, project_id: str, discovery_source_id: str) -> None:
        task = self.repository.get_or_create_task(
            project_id,
            "discover_primary_links",
            {"source_id": discovery_source_id},
        )
        if task.status == TaskStatus.COMPLETE.value:
            return
        self.repository.start_task(task.id)
        try:
            source = self.repository.source(discovery_source_id)
            document = self.retriever.retrieve(source.canonical_url)
            self.repository.store_source_content(source.id, document.content, document.chunks)
            primary_ids = []
            for url in document.outbound_links:
                if not looks_primary(url):
                    continue
                primary = self.repository.add_source(
                    url,
                    source_type=infer_source_type(url),
                    is_primary=True,
                    metadata={"discovered_from": source.canonical_url},
                )
                self.repository.add_discovery_link(
                    source.id, primary.id, "Primary-looking link found in discovery source"
                )
                primary_ids.append(primary.id)
                if len(primary_ids) >= 10:
                    break
            self.repository.complete_task(task.id, {"primary_source_ids": primary_ids})
        except Exception as exc:
            self.repository.fail_task(task.id, str(exc))

    def _retrieve(self, project_id: str, source_id: str) -> bool:
        task = self.repository.get_or_create_task(
            project_id, "retrieve_source", {"source_id": source_id}
        )
        if task.status == TaskStatus.COMPLETE.value:
            return False
        self.repository.start_task(task.id)
        try:
            source = self.repository.source(source_id)
            document = self.retriever.retrieve(source.canonical_url)
            stored = self.repository.store_source_content(
                source.id, document.content, document.chunks
            )
            stored = self.repository.source(stored.id)
            if stored.chunks:
                vectors, usage = self.ai.embeddings(
                    [chunk.content for chunk in stored.chunks],
                    model=self.embedding_model,
                ) if self.ai is not None else ([], None)
                if vectors:
                    self.repository.set_chunk_embeddings(
                        {chunk.id: vector for chunk, vector in zip(stored.chunks, vectors)}
                    )
                    self.repository.record_run(
                        project_id,
                        "embed_source_chunks",
                        provider="openai",
                        model=self.embedding_model,
                        input_tokens=usage.input_tokens,
                        estimated_cost=usage.estimated_cost,
                        metadata_={"source_id": stored.id},
                    )
            self.repository.complete_task(
                task.id,
                {"source_id": stored.id, "chunks": len(document.chunks)},
            )
            return True
        except Exception as exc:
            self.repository.fail_task(task.id, str(exc))
            return False

    def _extract(self, project_id: str, proposition_id: str, source_id: str) -> int:
        task = self.repository.get_or_create_task(
            project_id,
            "extract_evidence",
            {"proposition_id": proposition_id, "source_id": source_id, "version": "v1"},
            proposition_id=proposition_id,
        )
        if task.status == TaskStatus.COMPLETE.value:
            return len(task.result.get("evidence_ids", []))
        proposition = next(
            item for item in self.repository.propositions(project_id) if item.id == proposition_id
        )
        source = self.repository.source(source_id)
        chunks = self._relevant_chunks(proposition.text, source.chunks, limit=5)
        if not chunks:
            self.repository.complete_task(task.id, {"evidence_ids": []})
            return 0
        self.repository.start_task(task.id)
        chunk_text = "\n\n".join(
            f"CHUNK {chunk.id} [{chunk.locator}]\n{chunk.content}" for chunk in chunks
        )
        prompt = f"""Assess a proposition using only the primary-source excerpts below.
Return JSON with an `evidence` array. Include an item only when the excerpt directly bears on the proposition.
Each item requires: chunk_id, finding, exact_excerpt, locator, relationship (supports|challenges|mixed),
explanation, population, geography, timeframe, methodology, confidence (low|medium|high).
The exact_excerpt must be copied from its chunk. Do not infer conclusions beyond the source.

PROPOSITION: {proposition.text}
SOURCE: {source.title or source.canonical_url}

{chunk_text}"""
        try:
            payload, usage = self.ai.json_completion(prompt, operation="extract_evidence")
            chunk_by_id = {chunk.id: chunk for chunk in chunks}
            evidence_ids = []
            for item in payload.get("evidence", []):
                chunk = chunk_by_id.get(str(item.get("chunk_id")))
                excerpt = str(item.get("exact_excerpt", "")).strip()
                if chunk is None or self._normalize(excerpt) not in self._normalize(chunk.content):
                    continue
                draft = EvidenceDraft(
                    finding=str(item.get("finding", "")),
                    excerpt=excerpt,
                    locator=str(item.get("locator") or chunk.locator),
                    relationship=str(item.get("relationship", "mixed")),
                    explanation=str(item.get("explanation", "")),
                    population=item.get("population"),
                    geography=item.get("geography"),
                    timeframe=item.get("timeframe"),
                    methodology=item.get("methodology"),
                    confidence=str(item.get("confidence", "medium")),
                )
                evidence = self.repository.add_evidence(
                    proposition.id,
                    source.id,
                    chunk.id,
                    draft,
                    extraction_version="openai-v1",
                )
                vectors, embedding_usage = self.ai.embeddings(
                    [draft.finding], model=self.embedding_model
                )
                self.repository.set_evidence_embedding(evidence.id, vectors[0])
                self.repository.record_run(
                    project_id,
                    "embed_evidence",
                    provider="openai",
                    model=self.embedding_model,
                    input_tokens=embedding_usage.input_tokens,
                    estimated_cost=embedding_usage.estimated_cost,
                    metadata_={"evidence_id": evidence.id},
                )
                evidence_ids.append(evidence.id)
            self.repository.complete_task(task.id, {"evidence_ids": evidence_ids})
            self.repository.record_run(
                project_id,
                "extract_evidence",
                provider="openai",
                model=self.model,
                prompt_version="v1",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost=usage.estimated_cost,
                metadata_={"proposition_id": proposition.id, "source_id": source.id},
            )
            return len(evidence_ids)
        except Exception as exc:
            self.repository.fail_task(task.id, str(exc))
            return 0

    @staticmethod
    def _relevant_chunks(query: str, chunks, limit: int):
        terms = {
            word
            for word in re.findall(r"[a-z]{4,}", query.lower())
            if word not in {"that", "this", "with", "from", "have", "should", "changes"}
        }
        scored = []
        for chunk in chunks:
            lower = chunk.content.lower()
            score = sum(lower.count(term) for term in terms)
            scored.append((score, chunk.ordinal, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:limit] if item[0] > 0]

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()
