from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import gzip
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from .domain import EvidenceDraft, ResearchPlan
from .entities import (
    ChatMessageRecord,
    EvidenceLinkRecord,
    EvidenceRecord,
    ProjectRecord,
    PropositionRecord,
    QueryNodeRecord,
    SourceChunkRecord,
    SourceRecord,
    TaskRecord,
    ThesisRecord,
    WebJobRecord,
    new_id,
    now_iso,
)
from .utils import canonicalize_url, stable_hash
from .content_policy import cache_expiry, classify_rights, is_expired
from .query_graph import make_node, normalize_query, seed_queries


SCHEMA_VERSION = 1


class JsonRepository:
    """Atomic, human-inspectable storage for the database-free research pilot."""

    def __init__(self, root: Path):
        self.root = root
        self.projects_dir = root / "projects"
        self.sources_dir = root / "library" / "sources"
        self.evidence_dir = root / "library" / "evidence"
        self.documents_dir = root / "library" / "documents"
        self.blocklist_path = root / "library" / "blocklist.json"
        self.catalog_path = root / "catalog.json"
        for directory in (
            self.projects_dir,
            self.sources_dir,
            self.evidence_dir,
            self.documents_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            if directory == self.documents_dir:
                directory.chmod(0o700)
        if not self.blocklist_path.exists():
            self._write_json(self.blocklist_path, {"entries": []})
        if not self.catalog_path.exists():
            self._write_json(
                self.catalog_path,
                {"schema_version": SCHEMA_VERSION, "urls": {}, "content_hashes": {}},
            )

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read JSON record {path}: {exc}") from exc

    @staticmethod
    def _write_gzip_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
                    handle.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))
                raw.flush()
                os.fsync(raw.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _read_gzip_json(path: Path) -> dict:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    @contextmanager
    def _lock(self, name: str):
        lock_path = self.root / ".locks" / f"{name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _project_path(self, project_id: str) -> Path:
        return self.projects_dir / project_id / "project.json"

    def _query_graph_path(self, project_id: str) -> Path:
        return self.projects_dir / project_id / "query_graph.json"

    def _project_data(self, project_id: str) -> dict:
        path = self._project_path(project_id)
        if not path.exists():
            raise ValueError(f"Unknown project: {project_id}")
        return self._read_json(path)

    def _save_project(self, project_id: str, data: dict) -> None:
        data["project"]["updated_at"] = now_iso()
        self._write_json(self._project_path(project_id), data)

    def _source_path(self, source_id: str) -> Path:
        return self.sources_dir / f"{source_id}.json"

    def _evidence_path(self, evidence_id: str) -> Path:
        return self.evidence_dir / f"{evidence_id}.json"

    @staticmethod
    def _project_record(value: dict) -> ProjectRecord:
        return ProjectRecord(**value)

    @staticmethod
    def _thesis_record(value: dict) -> ThesisRecord:
        return ThesisRecord(**value)

    @staticmethod
    def _proposition_record(value: dict) -> PropositionRecord:
        return PropositionRecord(**value)

    @staticmethod
    def _task_record(value: dict) -> TaskRecord:
        return TaskRecord(**value)

    @staticmethod
    def _web_job_record(value: dict) -> WebJobRecord:
        return WebJobRecord(**value)

    @staticmethod
    def _chat_message_record(value: dict) -> ChatMessageRecord:
        return ChatMessageRecord(**value)

    @staticmethod
    def _source_record(value: dict) -> SourceRecord:
        copied = dict(value)
        copied["chunks"] = [SourceChunkRecord(**item) for item in copied.get("chunks", [])]
        return SourceRecord(**copied)

    @staticmethod
    def _evidence_record(value: dict) -> EvidenceRecord:
        return EvidenceRecord(**value)

    def create_project(self, thesis: str, title: str | None = None) -> ProjectRecord:
        thesis = thesis.strip()
        if not thesis:
            raise ValueError("Thesis cannot be empty")
        project = ProjectRecord(id=new_id(), title=title or thesis[:120])
        thesis_record = ThesisRecord(
            id=new_id(), project_id=project.id, version=1, text=thesis
        )
        data = {
            "schema_version": SCHEMA_VERSION,
            "project": asdict(project),
            "theses": [asdict(thesis_record)],
            "propositions": [],
            "tasks": [],
            "web_jobs": [],
            "messages": [],
            "evidence_links": [],
            "discovery_links": [],
            "runs": [],
        }
        with self._lock(project.id):
            self._save_project(project.id, data)
        return project

    def project(self, project_id: str) -> ProjectRecord:
        return self._project_record(self._project_data(project_id)["project"])

    def project_ids(self) -> list[str]:
        return sorted(path.parent.name for path in self.projects_dir.glob("*/project.json"))

    def current_thesis(self, project_id: str) -> ThesisRecord:
        values = self._project_data(project_id)["theses"]
        if not values:
            raise ValueError(f"Project {project_id} has no thesis")
        return self._thesis_record(max(values, key=lambda item: item["version"]))

    def mark_planned(self, project_id: str) -> None:
        self.set_project_status(project_id, "planned")

    def approve_plan(self, plan: ResearchPlan) -> int:
        with self._lock(plan.project_id):
            data = self._project_data(plan.project_id)
            thesis_value = max(data["theses"], key=lambda item: item["version"])
            if (
                thesis_value["version"] != plan.thesis_version
                or thesis_value["text"] != plan.thesis
            ):
                raise ValueError("Plan thesis does not match the project's current thesis version")
            data["propositions"] = [
                item
                for item in data["propositions"]
                if item["thesis_version"] != plan.thesis_version
            ]
            data["propositions"].extend(
                asdict(
                    PropositionRecord(
                        id=new_id(),
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
                for item in plan.propositions
            )
            data["project"]["status"] = "approved"
            data["project"]["pause_requested"] = False
            data["project"]["research_pass"] = 1
            data["project"]["max_source_attempts"] = plan.max_source_attempts
            data["project"]["max_runtime_seconds"] = plan.max_runtime_seconds
            self._save_project(plan.project_id, data)
            graph_path = self._query_graph_path(plan.project_id)
            if graph_path.exists():
                graph_path.unlink()
        return len(plan.propositions)

    def revise_thesis(
        self, project_id: str, text: str, reason: str | None = None
    ) -> ThesisRecord:
        text = text.strip()
        if not text:
            raise ValueError("Revised thesis cannot be empty")
        with self._lock(project_id):
            data = self._project_data(project_id)
            version = max(item["version"] for item in data["theses"]) + 1
            thesis = ThesisRecord(
                id=new_id(),
                project_id=project_id,
                version=version,
                text=text,
                revision_reason=reason,
            )
            data["theses"].append(asdict(thesis))
            data["project"].update(
                status="draft", pause_requested=False, research_pass=1
            )
            self._save_project(project_id, data)
            return thesis

    def propositions(self, project_id: str) -> list[PropositionRecord]:
        data = self._project_data(project_id)
        version = max(item["version"] for item in data["theses"])
        return sorted(
            [
                self._proposition_record(item)
                for item in data["propositions"]
                if item["thesis_version"] == version
            ],
            key=lambda item: item.plan_key,
        )

    def query_nodes(self, project_id: str) -> list[QueryNodeRecord]:
        self.project(project_id)
        path = self._query_graph_path(project_id)
        if not path.exists():
            return []
        values = self._read_json(path).get("nodes", [])
        return [QueryNodeRecord(**item) for item in values]

    def _save_query_nodes(self, project_id: str, nodes: list[QueryNodeRecord]) -> None:
        path = self._query_graph_path(project_id)
        metadata = self._read_json(path).get("metadata", {}) if path.exists() else {}
        self._write_json(
            path,
            {
                "schema_version": 1,
                "project_id": project_id,
                "metadata": metadata,
                "nodes": [asdict(item) for item in nodes],
            },
        )

    def add_query_node(self, project_id: str, value: dict) -> QueryNodeRecord | None:
        node = make_node(project_id, value)
        normalized = normalize_query(node.query)
        with self._lock(project_id):
            nodes = self.query_nodes(project_id)
            existing = next(
                (item for item in nodes if normalize_query(item.query) == normalized),
                None,
            )
            if existing is not None:
                merged = list(dict.fromkeys([
                    *existing.proposition_ids, *node.proposition_ids
                ]))
                if merged != existing.proposition_ids:
                    existing.proposition_ids = merged
                    existing.priority = max(existing.priority, node.priority)
                    existing.updated_at = now_iso()
                    self._save_query_nodes(project_id, nodes)
                return None
            nodes.append(node)
            self._save_query_nodes(project_id, nodes)
        return node

    def seed_query_graph(self, project_id: str) -> int:
        added = 0
        for proposition in self.propositions(project_id):
            if proposition.kind != "empirical":
                continue
            for value in seed_queries(proposition):
                value.update(
                    proposition_ids=[proposition.id],
                    expansion_reason=(
                        "emergent_proposition" if proposition.origin == "source_discovered" else "seed"
                    ),
                )
                if proposition.origin == "source_discovered":
                    value["query_kind"] = "emergent_proposition"
                if self.add_query_node(project_id, value):
                    added += 1
        return added

    def update_query_node(self, project_id: str, node_id: str, **changes) -> QueryNodeRecord:
        with self._lock(project_id):
            nodes = self.query_nodes(project_id)
            node = next((item for item in nodes if item.id == node_id), None)
            if node is None:
                raise ValueError(f"Unknown query node: {node_id}")
            for key, value in changes.items():
                if hasattr(node, key):
                    setattr(node, key, value)
            node.updated_at = now_iso()
            self._save_query_nodes(project_id, nodes)
            return node

    def next_query_node(self, project_id: str) -> QueryNodeRecord | None:
        pending = [
            item for item in self.query_nodes(project_id)
            if item.status in {"pending", "running"}
            or item.status == "failed" and item.attempts < 2
        ]
        if not pending:
            return None
        running = [item for item in pending if item.status == "running"]
        if running:
            return sorted(running, key=lambda item: (item.updated_at, item.id))[0]
        propositions = self.propositions(project_id)
        planned_empirical_ids = {
            item.id
            for item in propositions
            if item.kind == "empirical" and item.origin == "planned"
        }
        attempted_proposition_ids = {
            proposition_id
            for node in self.query_nodes(project_id)
            if node.attempts > 0
            for proposition_id in node.proposition_ids
        }
        untouched = planned_empirical_ids - attempted_proposition_ids
        if untouched:
            coverage_kinds = {"direct_primary", "official_record", "scholarly"}
            coverage_nodes = [
                node
                for node in pending
                if node.parent_id is None
                and node.query_kind in coverage_kinds
                and untouched.intersection(node.proposition_ids)
            ]
            if coverage_nodes:
                kind_order = {
                    "official_record": 0,
                    "direct_primary": 1,
                    "scholarly": 2,
                }
                return sorted(
                    coverage_nodes,
                    key=lambda node: (
                        0 if node.status == "running" else 1,
                        kind_order[node.query_kind],
                        node.created_at,
                        node.id,
                    ),
                )[0]
        try:
            evidence = self.project_evidence(project_id)
        except ValueError:
            evidence = []
        covered = {row["proposition"].id for row in evidence}
        challenged = {
            row["proposition"].id
            for row in evidence
            if row["link"].relationship in {"challenges", "mixed"}
        }
        sources = {item.id: item for item in self.sources()}

        def score(node: QueryNodeRecord) -> float:
            value = node.priority - node.depth * 0.5
            if any(item not in covered for item in node.proposition_ids):
                value += 3.0
            if node.target_stance == "challenges" and any(
                item not in challenged for item in node.proposition_ids
            ):
                value += 2.5
            parent_sources = [sources[item] for item in node.result_source_ids if item in sources]
            failures = sum(
                1
                for source in parent_sources
                if source.retrieval_status in {"failed", "restricted", "needs_ocr"}
            )
            if parent_sources:
                value -= failures / len(parent_sources)
            value += min(float(node.metrics.get("novel_sources", 0)), 3.0) * 0.25
            return value

        return sorted(
            pending,
            key=lambda item: (
                0 if item.status == "running" else 1,
                -score(item), item.depth, item.created_at, item.id,
            ),
        )[0]

    def record_query_graph_stop(self, project_id: str, reason: str, metrics: dict) -> None:
        path = self._query_graph_path(project_id)
        if not path.exists():
            return
        with self._lock(project_id):
            data = self._read_json(path)
            data["metadata"] = {
                **data.get("metadata", {}),
                "last_stop_reason": reason,
                "last_run_metrics": metrics,
                "updated_at": now_iso(),
            }
            self._write_json(path, data)

    def query_graph_summary(self, project_id: str) -> dict:
        nodes = self.query_nodes(project_id)
        path = self._query_graph_path(project_id)
        metadata = self._read_json(path).get("metadata", {}) if path.exists() else {}
        statuses = Counter(item.status for item in nodes)
        return {
            "nodes": len(nodes),
            "statuses": dict(statuses),
            "recovery_nodes": len([item for item in nodes if item.query_kind in {"alternate_copy", "retrieval_recovery"}]),
            "max_depth": max((item.depth for item in nodes), default=0),
            "queries_executed": len([item for item in nodes if item.attempts > 0]),
            "sources_discovered": len({source_id for item in nodes for source_id in item.result_source_ids}),
            "last_stop_reason": metadata.get("last_stop_reason"),
            "last_run_metrics": metadata.get("last_run_metrics", {}),
        }

    def add_emergent_proposition(self, project_id: str, value: dict) -> PropositionRecord:
        with self._lock(project_id):
            data = self._project_data(project_id)
            version = max(item["version"] for item in data["theses"])
            existing_keys = {item["plan_key"] for item in data["propositions"]}
            base = f"emergent_{len([k for k in existing_keys if k.startswith('emergent_')]) + 1}"
            key, suffix = base, 2
            while key in existing_keys:
                key, suffix = f"{base}_{suffix}", suffix + 1
            item = PropositionRecord(
                id=new_id(), project_id=project_id, thesis_version=version,
                plan_key=key, text=str(value["text"]).strip(), kind="empirical",
                polarity=str(value.get("polarity", "neutral")),
                scope=dict(value.get("scope", {})), approved=True,
                search_queries=list(value.get("search_queries", [])),
                origin="source_discovered", review_status="unreviewed",
                provenance=dict(value.get("provenance", {})),
            )
            data["propositions"].append(asdict(item))
            self._save_project(project_id, data)
            return item

    def set_proposition_embedding(self, proposition_id: str, embedding: list[float], metadata: dict | None = None) -> None:
        project_id = self._project_for_proposition(proposition_id)
        with self._lock(project_id):
            data = self._project_data(project_id)
            for item in data["propositions"]:
                if item["id"] == proposition_id:
                    item["embedding"] = embedding
                    item["embedding_metadata"] = metadata or {}
                    self._save_project(project_id, data)
                    return

    def set_chunk_embeddings(self, embeddings: dict[str, tuple[list[float], dict] | list[float]]) -> None:
        with self._lock("library"):
            for path in self.sources_dir.glob("*.json"):
                data = self._read_json(path)
                changed = False
                for chunk in data.get("chunks", []):
                    if chunk["id"] in embeddings:
                        value = embeddings[chunk["id"]]
                        if isinstance(value, tuple):
                            chunk["embedding"], chunk["embedding_metadata"] = value
                        else:
                            chunk["embedding"] = value
                        changed = True
                if changed:
                    self._write_json(path, data)

    def set_source_embedding(self, source_id: str, embedding: list[float], metadata: dict) -> None:
        path = self._source_path(source_id)
        data = self._read_json(path)
        data["embedding"] = embedding
        data["embedding_metadata"] = metadata
        self._write_json(path, data)

    def set_evidence_embedding(self, evidence_id: str, embedding: list[float], metadata: dict | None = None) -> None:
        path = self._evidence_path(evidence_id)
        data = self._read_json(path)
        data["embedding"] = embedding
        data["embedding_metadata"] = metadata or {}
        self._write_json(path, data)

    def save_synthesis(self, project_id: str, synthesis: dict) -> None:
        with self._lock(project_id):
            data = self._project_data(project_id)
            data["project"]["synthesis"] = synthesis
            self._save_project(project_id, data)

    def synthesis(self, project_id: str) -> dict:
        return dict(self._project_data(project_id)["project"].get("synthesis", {}))

    def set_project_status(
        self, project_id: str, status: str, pause: bool | None = None
    ) -> None:
        with self._lock(project_id):
            data = self._project_data(project_id)
            data["project"]["status"] = status
            if pause is not None:
                data["project"]["pause_requested"] = pause
            self._save_project(project_id, data)

    def research_pass(self, project_id: str) -> int:
        return int(self._project_data(project_id)["project"].get("research_pass", 1))

    def advance_research_pass(self, project_id: str) -> int:
        with self._lock(project_id):
            data = self._project_data(project_id)
            current = int(data["project"].get("research_pass", 1))
            if current >= 2:
                raise ValueError("The balanced pilot permits only one gap-filling pass")
            data["project"]["research_pass"] = current + 1
            data["project"]["status"] = "approved"
            data["project"]["pause_requested"] = False
            self._save_project(project_id, data)
            return current + 1

    def should_pause(self, project_id: str) -> bool:
        return self.project(project_id).pause_requested

    def get_or_create_task(
        self,
        project_id: str,
        task_type: str,
        payload: dict,
        proposition_id: str | None = None,
    ) -> TaskRecord:
        input_hash = stable_hash(json.dumps(payload, sort_keys=True))
        with self._lock(project_id):
            data = self._project_data(project_id)
            for item in data["tasks"]:
                if item["task_type"] == task_type and item["input_hash"] == input_hash:
                    return self._task_record(item)
            task = TaskRecord(
                id=new_id(),
                project_id=project_id,
                proposition_id=proposition_id,
                task_type=task_type,
                input_hash=input_hash,
                payload=payload,
            )
            data["tasks"].append(asdict(task))
            self._save_project(project_id, data)
            return task

    def _update_task(self, task_id: str, update) -> None:
        for project_path in self.projects_dir.glob("*/project.json"):
            project_id = project_path.parent.name
            with self._lock(project_id):
                data = self._project_data(project_id)
                for item in data["tasks"]:
                    if item["id"] == task_id:
                        update(item)
                        item["updated_at"] = now_iso()
                        self._save_project(project_id, data)
                        return
        raise ValueError(f"Unknown task: {task_id}")

    def start_task(self, task_id: str) -> None:
        def update(item):
            item.update(status="running", attempts=item["attempts"] + 1, error=None)

        self._update_task(task_id, update)

    def complete_task(self, task_id: str, result: dict) -> None:
        self._update_task(task_id, lambda item: item.update(status="complete", result=result))

    def fail_task(self, task_id: str, error: str) -> None:
        self._update_task(task_id, lambda item: item.update(status="failed", error=error))

    def create_web_job(
        self, project_id: str, mode: str, limits: dict
    ) -> WebJobRecord:
        if mode not in {"initial", "resume", "continue"}:
            raise ValueError(f"Unknown web job mode: {mode}")
        with self._lock(project_id):
            data = self._project_data(project_id)
            jobs = data.setdefault("web_jobs", [])
            active = next(
                (
                    item
                    for item in reversed(jobs)
                    if item["state"] in {"pending", "running"}
                ),
                None,
            )
            if active is not None:
                return self._web_job_record(active)
            job = WebJobRecord(
                id=new_id(), project_id=project_id, mode=mode, limits=dict(limits)
            )
            jobs.append(asdict(job))
            self._save_project(project_id, data)
            return job

    def web_jobs(self, project_id: str) -> list[WebJobRecord]:
        return [
            self._web_job_record(item)
            for item in self._project_data(project_id).get("web_jobs", [])
        ]

    def latest_web_job(self, project_id: str) -> WebJobRecord | None:
        jobs = self.web_jobs(project_id)
        return jobs[-1] if jobs else None

    def update_web_job(
        self,
        project_id: str,
        job_id: str,
        *,
        state: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
    ) -> WebJobRecord:
        with self._lock(project_id):
            data = self._project_data(project_id)
            job = next(
                (
                    item
                    for item in data.setdefault("web_jobs", [])
                    if item["id"] == job_id
                ),
                None,
            )
            if job is None:
                raise ValueError(f"Unknown web job: {job_id}")
            if state is not None:
                job["state"] = state
            if result is not None:
                job["result"] = dict(result)
            job["error"] = error
            if increment_attempts:
                job["attempts"] = int(job.get("attempts", 0)) + 1
            job["updated_at"] = now_iso()
            self._save_project(project_id, data)
            return self._web_job_record(job)

    def interrupt_active_web_jobs(self) -> int:
        interrupted = 0
        for project_id in self.project_ids():
            with self._lock(project_id):
                data = self._project_data(project_id)
                changed = False
                for job in data.setdefault("web_jobs", []):
                    if job.get("state") in {"pending", "running"}:
                        job["state"] = "interrupted"
                        job["error"] = "The local web process stopped before this job finished."
                        job["updated_at"] = now_iso()
                        interrupted += 1
                        changed = True
                if changed:
                    self._save_project(project_id, data)
        return interrupted

    def add_message(
        self,
        project_id: str,
        role: str,
        content: str,
        *,
        citations: list[str] | None = None,
        limitations: list[str] | None = None,
        needs_additional_research: bool = False,
    ) -> ChatMessageRecord:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unknown message role: {role}")
        content = content.strip()
        if not content:
            raise ValueError("Message cannot be empty")
        message = ChatMessageRecord(
            id=new_id(),
            project_id=project_id,
            role=role,
            content=content,
            citations=list(citations or []),
            limitations=list(limitations or []),
            needs_additional_research=needs_additional_research,
        )
        with self._lock(project_id):
            data = self._project_data(project_id)
            data.setdefault("messages", []).append(asdict(message))
            self._save_project(project_id, data)
        return message

    def messages(self, project_id: str) -> list[ChatMessageRecord]:
        return [
            self._chat_message_record(item)
            for item in self._project_data(project_id).get("messages", [])
        ]

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
    ) -> SourceRecord:
        canonical_url = canonicalize_url(url)
        with self._lock("library"):
            catalog = self._read_json(self.catalog_path)
            existing_id = catalog["urls"].get(canonical_url)
            if existing_id:
                source = self.source(existing_id)
                source.title = source.title or title
                source.publisher = source.publisher or publisher
                source.is_primary = source.is_primary or is_primary
                if source.source_type == "unknown" and source_type != "unknown":
                    source.source_type = source_type
                incoming = metadata or {}
                source.metadata_.update(
                    {
                        key: value
                        for key, value in incoming.items()
                        if key not in source.metadata_
                    }
                )
                if rights_status:
                    source.rights_status = rights_status
                if detected_license:
                    source.detected_license = detected_license
                proposition_id = incoming.get("proposition_id")
                if proposition_id:
                    discovered_for = source.metadata_.setdefault("discovered_for", [])
                    if proposition_id not in discovered_for:
                        discovered_for.append(proposition_id)
                self._write_json(self._source_path(source.id), asdict(source))
                return source
            source = SourceRecord(
                id=new_id(),
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
            if source.metadata_.get("proposition_id"):
                source.metadata_["discovered_for"] = [
                    source.metadata_["proposition_id"]
                ]
            self._write_json(self._source_path(source.id), asdict(source))
            catalog["urls"][canonical_url] = source.id
            self._write_json(self.catalog_path, catalog)
            return source

    def set_source_rights(
        self,
        source_id: str,
        rights_status: str,
        *,
        license_value: str | None = None,
        basis: str,
    ) -> SourceRecord:
        from .content_policy import RIGHTS_STATUSES

        if rights_status not in RIGHTS_STATUSES:
            raise ValueError(f"Unknown rights status: {rights_status}")
        path = self._source_path(source_id)
        data = self._read_json(path)
        data["rights_status"] = rights_status
        data["detected_license"] = license_value
        metadata = dict(data.get("metadata_", {}))
        metadata["rights_basis"] = {"basis": basis, "recorded_at": now_iso()}
        data["metadata_"] = metadata
        cache = dict(data.get("cache_metadata", {}))
        cache["expires_at"] = cache_expiry(rights_status)
        data["cache_metadata"] = cache
        archive_path = self.documents_dir / f"{source_id}.json.gz"
        if archive_path.exists():
            archive = self._read_gzip_json(archive_path)
            archive["rights_status"] = rights_status
            archive["detected_license"] = license_value
            archive["expires_at"] = cache["expires_at"]
            self._write_gzip_json(archive_path, archive)
        self._write_json(path, data)
        return self.source(source_id)

    def store_source_content(
        self,
        source_id: str,
        content: str,
        chunks: list[tuple[str, str]],
        *,
        archive_chunks: list[tuple[str, str]] | None = None,
        access_metadata: dict | None = None,
    ) -> SourceRecord:
        normalized = "\n\n".join(
            part.strip() for part in content.split("\n\n") if part.strip()
        )
        if not normalized:
            raise ValueError("Cannot store an empty source")
        content_hash = stable_hash(normalized)
        with self._lock("library"):
            catalog = self._read_json(self.catalog_path)
            duplicate_id = catalog["content_hashes"].get(content_hash)
            if duplicate_id and duplicate_id != source_id:
                return self.source(duplicate_id)
            source = self.source(source_id)
            access = access_metadata or {}
            rights_status, detected_license = classify_rights(
                source.canonical_url, access.get("detected_license")
            )
            if access.get("rights_status") in {
                "public_domain", "open_license", "permission", "copyrighted", "unknown", "restricted"
            }:
                rights_status = access["rights_status"]
            all_chunks = archive_chunks or chunks
            existing_chunks = {
                (item.locator, item.content_hash): item for item in source.chunks
            }
            records = [
                self._content_chunk_record(
                    source.id,
                    ordinal,
                    locator,
                    text,
                    existing_chunks.get((locator, stable_hash(text))),
                    access,
                )
                for ordinal, (locator, text) in enumerate(all_chunks)
            ]
            by_key = {(item.locator, item.content_hash): item for item in records}
            selected = []
            for locator, text in chunks:
                item = by_key.get((locator, stable_hash(text)))
                if item is not None and item not in selected:
                    selected.append(item)
            archive_path = self.documents_dir / f"{source.id}.json.gz"
            expires_at = cache_expiry(rights_status)
            self._write_gzip_json(
                archive_path,
                {
                    "source_id": source.id,
                    "content_hash": content_hash,
                    "normalized_content": normalized,
                    "chunks": [asdict(item) for item in records],
                    "rights_status": rights_status,
                    "detected_license": detected_license,
                    "created_at": now_iso(),
                    "expires_at": expires_at,
                    "chunker_version": "token-v1",
                },
            )
            source.normalized_content = None
            source.content_hash = content_hash
            source.retrieval_status = "retrieved"
            source.retrieved_at = now_iso()
            source.chunks = selected
            source.rights_status = rights_status
            source.detected_license = detected_license
            source.accessed_at = access.get("accessed_at") or source.retrieved_at
            source.retrieval_permission = access.get("retrieval_permission", "public_http")
            source.robots_status = access.get("robots_status", "not_checked")
            source.terms_status = access.get("terms_status", "not_checked")
            source.retrieval_history.extend(access.get("retrieval_attempts") or [])
            source.needs_ocr = bool(access.get("needs_ocr", False))
            source.metadata_["resolved_url"] = access.get("resolved_url")
            source.metadata_["alternate_urls"] = access.get("alternate_urls") or []
            if access.get("document_quality") is not None:
                source.metadata_["document_quality"] = access["document_quality"]
            source.cache_metadata = {
                "path": str(archive_path.relative_to(self.root)),
                "compression": "gzip",
                "expires_at": expires_at,
                "deleted_at": None,
                "chunk_count": len(records),
                "selected_passage_count": len(selected),
                "chunker_version": "token-v1",
            }
            self._write_json(self._source_path(source.id), asdict(source))
            catalog["content_hashes"][content_hash] = source.id
            self._write_json(self.catalog_path, catalog)
            return source

    def record_source_retrieval(
        self,
        source_id: str,
        attempts: list[dict],
        *,
        outcome: str,
        needs_ocr: bool = False,
    ) -> None:
        """Persist failed retrieval diagnostics without retaining fetched content."""
        path = self._source_path(source_id)
        data = self._read_json(path)
        data.setdefault("retrieval_history", []).extend(attempts)
        data["retrieval_status"] = "needs_ocr" if needs_ocr else "failed"
        data["needs_ocr"] = needs_ocr
        metadata = dict(data.get("metadata_", {}))
        metadata["last_retrieval_outcome"] = outcome
        metadata["last_retrieval_at"] = now_iso()
        data["metadata_"] = metadata
        self._write_json(path, data)

    @staticmethod
    def _content_chunk_record(
        source_id: str,
        ordinal: int,
        locator: str,
        text: str,
        existing: SourceChunkRecord | None,
        access: dict,
    ) -> SourceChunkRecord:
        content_hash = stable_hash(text)
        return SourceChunkRecord(
            id=existing.id if existing else new_id(),
            source_id=source_id,
            ordinal=ordinal,
            locator=locator,
            content=text,
            content_hash=content_hash,
            embedding=existing.embedding if existing else None,
            embedding_metadata=existing.embedding_metadata if existing else {},
            token_count=(
                access.get("token_counts", {}).get(content_hash)
                or (existing.token_count if existing else None)
            ),
            relevance=(
                access.get("relevance", {}).get(content_hash)
                or (existing.relevance if existing else [])
            ),
        )

    def source_archive(self, source_id: str) -> dict | None:
        path = self.documents_dir / f"{source_id}.json.gz"
        return self._read_gzip_json(path) if path.exists() else None

    def evidence_for_source(self, source_id: str) -> list[EvidenceRecord]:
        results = []
        for path in self.evidence_dir.glob("*.json"):
            value = self._read_json(path)
            if value.get("source_id") == source_id:
                results.append(self._evidence_record(value))
        return results

    def remap_evidence_chunks(self, source_id: str) -> int:
        source = self.source(source_id)
        updated = 0
        for path in self.evidence_dir.glob("*.json"):
            value = self._read_json(path)
            if value.get("source_id") != source_id:
                continue
            excerpt = " ".join(value.get("excerpt", "").split()).casefold()
            match = next(
                (
                    chunk for chunk in source.chunks
                    if excerpt and excerpt in " ".join(chunk.content.split()).casefold()
                ),
                None,
            )
            if match is None:
                raise ValueError(
                    f"Cannot preserve evidence {value.get('id')} while rechunking source {source_id}"
                )
            if value.get("source_chunk_id") != match.id:
                value["source_chunk_id"] = match.id
                self._write_json(path, value)
                updated += 1
        return updated

    def delete_source_cache(self, source_id: str, *, force: bool = False) -> bool:
        source = self.source(source_id)
        if not force and source.rights_status in {"public_domain", "open_license", "permission"}:
            return False
        path = self.documents_dir / f"{source_id}.json.gz"
        if path.exists():
            path.unlink()
        data = self._read_json(self._source_path(source_id))
        metadata = dict(data.get("cache_metadata", {}))
        metadata["deleted_at"] = now_iso()
        data["cache_metadata"] = metadata
        self._write_json(self._source_path(source_id), data)
        return True

    def expire_caches(self) -> int:
        deleted = 0
        for source in self.sources():
            if is_expired(source.cache_metadata.get("expires_at")):
                deleted += int(self.delete_source_cache(source.id))
        return deleted

    def block_source(self, target: str, reason: str) -> dict:
        normalized = target.strip().casefold()
        if "://" in normalized:
            normalized = canonicalize_url(normalized)
            kind = "url"
        else:
            normalized = normalized.lstrip(".")
            kind = "domain"
        with self._lock("library"):
            data = self._read_json(self.blocklist_path)
            entry = {"kind": kind, "value": normalized, "reason": reason, "created_at": now_iso()}
            if not any(item["kind"] == kind and item["value"] == normalized for item in data["entries"]):
                data["entries"].append(entry)
                self._write_json(self.blocklist_path, data)
            return entry

    def unblock_source(self, target: str) -> bool:
        normalized = target.strip().casefold().lstrip(".")
        candidates = {normalized}
        if "://" in normalized:
            candidates.add(canonicalize_url(normalized))
        with self._lock("library"):
            data = self._read_json(self.blocklist_path)
            before = len(data["entries"])
            data["entries"] = [item for item in data["entries"] if item["value"] not in candidates]
            self._write_json(self.blocklist_path, data)
            return len(data["entries"]) != before

    def source_block_reason(self, url: str) -> str | None:
        canonical = canonicalize_url(url)
        host = urlsplit(canonical).netloc.casefold()
        data = self._read_json(self.blocklist_path)
        for item in data.get("entries", []):
            if item["kind"] == "url" and item["value"] == canonical:
                return item.get("reason") or "blocked URL"
            if item["kind"] == "domain" and (
                host == item["value"] or host.endswith(f".{item['value']}")
            ):
                return item.get("reason") or "blocked domain"
        return None

    def mark_source_restricted(self, source_id: str, reason: str) -> None:
        path = self._source_path(source_id)
        data = self._read_json(path)
        data["rights_status"] = "restricted"
        data["retrieval_status"] = "restricted"
        metadata = dict(data.get("metadata_", {}))
        metadata["restriction_reason"] = reason
        data["metadata_"] = metadata
        self._write_json(path, data)

    def takedown_source(self, source_id: str, reason: str) -> dict:
        source = self.source(source_id)
        self.block_source(source.canonical_url, reason)
        self.delete_source_cache(source_id, force=True)
        evidence_ids = {
            path.stem
            for path in self.evidence_dir.glob("*.json")
            if self._read_json(path).get("source_id") == source_id
        }
        for evidence_id in evidence_ids:
            path = self._evidence_path(evidence_id)
            if path.exists():
                path.unlink()
        links_removed = 0
        for project_path in self.projects_dir.glob("*/project.json"):
            data = self._read_json(project_path)
            before = len(data.get("evidence_links", []))
            data["evidence_links"] = [
                item for item in data.get("evidence_links", [])
                if item.get("evidence_id") not in evidence_ids
            ]
            links_removed += before - len(data["evidence_links"])
            if before != len(data["evidence_links"]):
                data["project"]["synthesis"] = {}
                self._save_project(data["project"]["id"], data)
        source_data = self._read_json(self._source_path(source_id))
        old_hash = source_data.get("content_hash")
        source_data.update(
            retrieval_status="restricted",
            rights_status="restricted",
            normalized_content=None,
            content_hash=None,
            chunks=[],
        )
        metadata = dict(source_data.get("metadata_", {}))
        metadata["takedown"] = {"reason": reason, "created_at": now_iso()}
        source_data["metadata_"] = metadata
        self._write_json(self._source_path(source_id), source_data)
        catalog = self._read_json(self.catalog_path)
        if old_hash and catalog.get("content_hashes", {}).get(old_hash) == source_id:
            del catalog["content_hashes"][old_hash]
            self._write_json(self.catalog_path, catalog)
        return {
            "source_id": source_id,
            "evidence_deleted": len(evidence_ids),
            "links_removed": links_removed,
            "blocked_url": source.canonical_url,
        }

    def source(self, source_id: str) -> SourceRecord:
        path = self._source_path(source_id)
        if not path.exists():
            raise ValueError(f"Unknown source: {source_id}")
        return self._source_record(self._read_json(path))

    def sources(self) -> list[SourceRecord]:
        return sorted(
            [self._source_record(self._read_json(path)) for path in self.sources_dir.glob("*.json")],
            key=lambda item: item.title or item.canonical_url,
        )

    def add_discovery_link(self, discovery_id: str, primary_id: str, context: str = "") -> None:
        # Discovery provenance is project-independent in the pilot catalog.
        with self._lock("library"):
            catalog = self._read_json(self.catalog_path)
            links = catalog.setdefault("discovery_links", [])
            key = [discovery_id, primary_id]
            if not any(item["key"] == key for item in links):
                links.append({"key": key, "context": context})
                self._write_json(self.catalog_path, catalog)

    def add_evidence(
        self,
        proposition_id: str,
        source_id: str,
        source_chunk_id: str,
        draft: EvidenceDraft,
        extraction_version: str = "manual-v1",
    ) -> EvidenceRecord:
        draft.validate()
        source = self.source(source_id)
        if not source.is_primary:
            raise ValueError("Final evidence must be attached to a primary source")
        chunk = next((item for item in source.chunks if item.id == source_chunk_id), None)
        if chunk is None:
            raise ValueError("Evidence chunk does not belong to the selected source")
        if " ".join(draft.excerpt.split()).casefold() not in " ".join(
            chunk.content.split()
        ).casefold():
            raise ValueError("Evidence excerpt must occur verbatim in the stored source chunk")
        finding_hash = stable_hash(" ".join(draft.finding.lower().split()))
        evidence = None
        for path in self.evidence_dir.glob("*.json"):
            value = self._read_json(path)
            if (
                value["source_chunk_id"] == source_chunk_id
                and value["finding_hash"] == finding_hash
            ):
                evidence = self._evidence_record(value)
                break
        if evidence is None:
            evidence = EvidenceRecord(
                id=new_id(),
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
            self._write_json(self._evidence_path(evidence.id), asdict(evidence))
        project_id = self._project_for_proposition(proposition_id)
        with self._lock(project_id):
            data = self._project_data(project_id)
            if not any(
                item["proposition_id"] == proposition_id
                and item["evidence_id"] == evidence.id
                for item in data["evidence_links"]
            ):
                data["evidence_links"].append(
                    asdict(
                        EvidenceLinkRecord(
                            id=new_id(),
                            proposition_id=proposition_id,
                            evidence_id=evidence.id,
                            relationship=draft.relationship,
                            explanation=draft.explanation,
                        )
                    )
                )
                self._save_project(project_id, data)
        return evidence

    def _project_for_proposition(self, proposition_id: str) -> str:
        for path in self.projects_dir.glob("*/project.json"):
            data = self._read_json(path)
            if any(item["id"] == proposition_id for item in data["propositions"]):
                return path.parent.name
        raise ValueError(f"Unknown proposition: {proposition_id}")

    def project_evidence(self, project_id: str) -> list[dict]:
        data = self._project_data(project_id)
        version = max(item["version"] for item in data["theses"])
        propositions = {
            item["id"]: self._proposition_record(item)
            for item in data["propositions"]
            if item["thesis_version"] == version
        }
        rows = []
        for link_value in data["evidence_links"]:
            proposition = propositions.get(link_value["proposition_id"])
            if proposition is None:
                continue
            evidence = self._evidence_record(
                self._read_json(self._evidence_path(link_value["evidence_id"]))
            )
            rows.append(
                {
                    "proposition": proposition,
                    "link": EvidenceLinkRecord(**link_value),
                    "evidence": evidence,
                    "source": self.source(evidence.source_id),
                }
            )
        return sorted(
            rows,
            key=lambda row: (
                row["proposition"].plan_key,
                row["link"].relationship,
                row["evidence"].finding,
            ),
        )

    def record_run(self, project_id: str, operation: str, **values) -> None:
        with self._lock(project_id):
            data = self._project_data(project_id)
            data["runs"].append(
                {
                    "id": new_id(),
                    "operation": operation,
                    "created_at": now_iso(),
                    **values,
                }
            )
            self._save_project(project_id, data)

    def status(self, project_id: str) -> dict:
        data = self._project_data(project_id)
        project = self._project_record(data["project"])
        propositions = self.propositions(project_id)
        rows = self.project_evidence(project_id)
        counts = Counter(row["link"].relationship for row in rows)
        tasks = Counter(item["status"] for item in data["tasks"])
        runs = data["runs"]
        sessions = [item for item in runs if item.get("operation") == "research_session"]
        proposition_ids = {item.id for item in propositions}
        graph_source_ids = {
            source_id
            for node in self.query_nodes(project_id)
            for source_id in node.result_source_ids
        }
        evidence_source_ids = {row["source"].id for row in rows}
        project_sources = [
            source
            for source in self.sources()
            if source.id in graph_source_ids | evidence_source_ids
            or proposition_ids.intersection(source.metadata_.get("discovered_for", []))
        ]
        attempted_source_ids = {
            str(item.get("payload", {}).get("source_id"))
            for item in data["tasks"]
            if item.get("task_type") == "retrieve_source" and item.get("attempts", 0) > 0
        }
        funnel = {
            "leads_discovered": len(project_sources),
            "retrieval_attempts": len(
                [source for source in project_sources if source.id in attempted_source_ids]
            ),
            "documents_retrieved": len(
                [source for source in project_sources if source.retrieval_status == "retrieved"]
            ),
            "relevant_documents": len(
                [
                    source
                    for source in project_sources
                    if source.metadata_.get("document_quality", {}).get(
                        "usable", source.id in evidence_source_ids
                    )
                ]
            ),
            "evidence_sources": len(evidence_source_ids),
            "evidence_items": len(rows),
        }
        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "research_pass": project.research_pass,
            "thesis": self.current_thesis(project_id).text,
            "propositions": len(propositions),
            "planned_propositions": len([item for item in propositions if item.origin == "planned"]),
            "emergent_propositions": len([item for item in propositions if item.origin == "source_discovered"]),
            "max_source_attempts": project.max_source_attempts,
            "max_runtime_seconds": project.max_runtime_seconds,
            "covered_propositions": len({row["proposition"].id for row in rows}),
            "evidence": dict(counts),
            "tasks": dict(tasks),
            "input_tokens": sum(item.get("input_tokens", 0) for item in runs),
            "output_tokens": sum(item.get("output_tokens", 0) for item in runs),
            "estimated_cost": sum(item.get("estimated_cost", 0.0) for item in runs),
            "model_calls": len([
                item for item in runs
                if item.get("provider") in {"codex", "deepseek"}
            ]),
            "failed_tasks": tasks.get("failed", 0),
            "postprocess_failures": sum(
                1 for item in data["tasks"]
                if "postprocess_validation" in str(item.get("error", ""))
            ),
            "evidence_items_received": sum(
                item.get("result", {}).get("processing", {}).get("received_items", 0)
                for item in data["tasks"]
            ),
            "evidence_items_accepted": sum(
                item.get("result", {}).get("processing", {}).get("accepted_items", 0)
                for item in data["tasks"]
            ),
            "last_research_session": sessions[-1].get("metadata_", {}) if sessions else {},
            "query_graph": self.query_graph_summary(project_id),
            "research_funnel": funnel,
        }

    def retrieval_benchmark(self, project_id: str) -> dict:
        """Summarize recorded retrieval behavior without making live requests."""
        proposition_ids = {item.id for item in self.propositions(project_id)}
        graph_source_ids = {
            source_id for node in self.query_nodes(project_id)
            for source_id in node.result_source_ids
        }
        evidence_source_ids = {
            row["source"].id for row in self.project_evidence(project_id)
        }
        sources = [
            source for source in self.sources()
            if source.id in graph_source_ids | evidence_source_ids
            or proposition_ids.intersection(source.metadata_.get("discovered_for", []))
            or source.metadata_.get("proposition_id") in proposition_ids
        ]
        attempted = [
            source for source in sources
            if source.retrieval_history or source.retrieval_status != "lead"
        ]
        primary_attempted = [source for source in attempted if source.is_primary]
        primary_success = [
            source for source in primary_attempted if source.retrieval_status == "retrieved"
        ]
        method_outcomes = Counter()
        policy_rejections = Counter()
        recovery_success = Counter()
        policy_codes = {
            "blocklisted", "private_network", "unsafe_url", "robots_disallowed",
            "http_401", "http_402", "http_403", "access_control_page",
        }
        for source in attempted:
            for item in source.retrieval_history:
                method_outcomes[(item.get("method", "unknown"), item.get("outcome", "unknown"))] += 1
                if item.get("outcome") in policy_codes:
                    policy_rejections[item.get("outcome")] += 1
            if source.retrieval_status != "retrieved":
                continue
            history = source.retrieval_history
            if any(item.get("method") == "browser" and item.get("outcome") == "success" for item in history):
                recovery_success["browser"] += 1
            if any(item.get("method") == "host_adapter" for item in history):
                recovery_success["host_adapter"] += 1
            if any(item.get("method") == "identifier_resolution" and item.get("outcome") == "alternates_found" for item in history):
                recovery_success["doi_alternate"] += 1
            if any(item.get("outcome") not in {"success", "allowed", "not_present", "not_applicable", "alternates_found", "alternate_discovered"} for item in history):
                recovery_success["after_prior_failure"] += 1
        status = self.status(project_id)
        graph = self.query_nodes(project_id)
        return {
            "project_id": project_id,
            "recorded_sources": len(sources),
            "attempted_sources": len(attempted),
            "primary_attempted": len(primary_attempted),
            "primary_retrieved": len(primary_success),
            "primary_retrieval_success_rate": (
                round(len(primary_success) / len(primary_attempted), 4)
                if primary_attempted else None
            ),
            "recovery_success_by_strategy": dict(recovery_success),
            "browser_attempts": sum(
                count for (method, _), count in method_outcomes.items() if method == "browser"
            ),
            "policy_rejections": dict(policy_rejections),
            "retrieval_outcomes": {
                f"{method}:{outcome}": count
                for (method, outcome), count in sorted(method_outcomes.items())
            },
            "graph_novel_sources": sum(
                int(node.metrics.get("novel_sources", 0)) for node in graph
            ),
            "graph_queries_completed": len([node for node in graph if node.status == "complete"]),
            "runtime_seconds": status["last_research_session"].get("elapsed_seconds"),
            "estimated_cost": status["estimated_cost"],
            "note": "Recorded metrics only; no live web request is made.",
        }

    def errors(self, project_id: str) -> list[dict]:
        data = self._project_data(project_id)
        return [
            {
                "kind": "task",
                "task_id": item["id"],
                "task_type": item["task_type"],
                "status": item["status"],
                "attempts": item.get("attempts", 0),
                "error": item["error"],
                "updated_at": item.get("updated_at"),
            }
            for item in data["tasks"] if item.get("error")
        ]

    def lexical_evidence_candidates(self, text: str, limit: int = 10) -> list[tuple[str, float]]:
        terms = self._terms(text)
        if not terms:
            return []
        scored = []
        for path in self.evidence_dir.glob("*.json"):
            evidence = self._evidence_record(self._read_json(path))
            candidate_terms = self._terms(evidence.finding)
            overlap = len(terms & candidate_terms)
            if overlap:
                scored.append((evidence.id, overlap / math.sqrt(len(terms) * len(candidate_terms))))
        return sorted(scored, key=lambda item: (-item[1], item[0]))[:limit]

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[a-z0-9]{3,}", text.casefold())
            if term not in {"the", "and", "that", "with", "from", "this", "should"}
        }

    def rebuild_catalog(self) -> dict:
        try:
            discovery_links = self._read_json(self.catalog_path).get(
                "discovery_links", []
            )
        except ValueError:
            discovery_links = []
        catalog = {
            "schema_version": SCHEMA_VERSION,
            "urls": {},
            "content_hashes": {},
            "discovery_links": discovery_links,
        }
        errors = []
        for path in self.sources_dir.glob("*.json"):
            try:
                source = self._source_record(self._read_json(path))
                catalog["urls"][source.canonical_url] = source.id
                if source.content_hash:
                    catalog["content_hashes"][source.content_hash] = source.id
            except ValueError as exc:
                errors.append(str(exc))
        self._write_json(self.catalog_path, catalog)
        return {"sources": len(catalog["urls"]), "errors": errors}

    def doctor(self) -> dict:
        errors = []
        for path in [self.catalog_path] + list(self.projects_dir.glob("*/project.json")) + list(
            self.sources_dir.glob("*.json")
        ) + list(self.evidence_dir.glob("*.json")):
            try:
                self._read_json(path)
            except ValueError as exc:
                errors.append(str(exc))
        evidence_ids = {path.stem for path in self.evidence_dir.glob("*.json")}
        source_ids = {path.stem for path in self.sources_dir.glob("*.json")}
        for project_path in self.projects_dir.glob("*/project.json"):
            try:
                project_data = self._read_json(project_path)
            except ValueError:
                continue
            for link in project_data.get("evidence_links", []):
                if link.get("evidence_id") not in evidence_ids:
                    errors.append(
                        f"Dangling evidence reference {link.get('evidence_id')} in {project_path}"
                    )
        for evidence_path in self.evidence_dir.glob("*.json"):
            try:
                value = self._read_json(evidence_path)
            except ValueError:
                continue
            if value.get("source_id") not in source_ids:
                errors.append(
                    f"Dangling source reference {value.get('source_id')} in {evidence_path}"
                )
        return {
            "root": str(self.root),
            "writable": os.access(self.root, os.W_OK),
            "projects": len(list(self.projects_dir.glob("*/project.json"))),
            "sources": len(list(self.sources_dir.glob("*.json"))),
            "evidence": len(list(self.evidence_dir.glob("*.json"))),
            "errors": errors,
        }
