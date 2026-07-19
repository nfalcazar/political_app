from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from .states import ProjectStatus, WebJobStatus


INITIAL_LIMITS = {
    "max_sources": 10,
    "max_queries": 30,
    "max_runtime_seconds": 600,
}

CONTINUATION_LIMITS = {
    "max_sources": 5,
    "max_queries": 15,
    "max_runtime_seconds": 300,
}


class ResearchJobManager:
    """A single-worker local queue backed by durable JSON job records."""

    def __init__(
        self,
        repository,
        *,
        planner_factory,
        engine_factory,
        executor=None,
        recover_orphans: bool = True,
    ):
        self.repository = repository
        self.planner_factory = planner_factory
        self.engine_factory = engine_factory
        self.executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="research-web"
        )
        self._futures = {}
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        if recover_orphans:
            self.repository.interrupt_active_web_jobs()

    def has_active_job(self, project_id: str) -> bool:
        job = self.repository.latest_web_job(project_id)
        if job is None or job.state not in {
            WebJobStatus.PENDING,
            WebJobStatus.RUNNING,
        }:
            return False
        future = self._futures.get(job.id)
        return future is None or not future.done()

    def has_any_active_job(self) -> bool:
        with self._lock:
            return any(not future.done() for future in self._futures.values())

    def enqueue(self, project_id: str, mode: str, limits: dict | None = None):
        limits = dict(
            limits
            or (CONTINUATION_LIMITS if mode == "continue" else INITIAL_LIMITS)
        )
        job = self.repository.create_web_job(project_id, mode, limits)
        with self._lock:
            future = self._futures.get(job.id)
            if future is None or future.done():
                self._futures[job.id] = self.executor.submit(
                    self._run_job, project_id, job.id
                )
        return job

    def _run_job(self, project_id: str, job_id: str) -> None:
        job = self.repository.update_web_job(
            project_id,
            job_id,
            state=WebJobStatus.RUNNING,
            increment_attempts=True,
        )
        try:
            project = self.repository.project(project_id)
            if job.mode == "initial" and project.status in {
                ProjectStatus.DRAFT,
                ProjectStatus.PLANNED,
            }:
                planner = self.planner_factory(project_id)
                plan = planner.create_plan(project_id)
                plan.max_source_attempts = int(job.limits["max_sources"])
                plan.max_runtime_seconds = int(job.limits["max_runtime_seconds"])
                plan.approval_required = False
                proposition_count = self.repository.approve_plan(plan)
                self.repository.record_run(
                    project_id,
                    "web_auto_approve",
                    provider=getattr(getattr(planner, "ai", None), "provider_name", None),
                    model=getattr(getattr(planner, "ai", None), "model", None),
                    metadata_={
                        "authorization": "user_submitted_claim",
                        "propositions": proposition_count,
                        "limits": dict(job.limits),
                    },
                )
            engine = self.engine_factory(project_id, job.limits)
            result = engine.run(project_id)
            if self._stopping.is_set():
                self.repository.update_web_job(
                    project_id,
                    job_id,
                    state=WebJobStatus.INTERRUPTED,
                    result=result,
                    error="The local web process stopped before this job finished.",
                )
            else:
                self.repository.update_web_job(
                    project_id,
                    job_id,
                    state=WebJobStatus.COMPLETE,
                    result=result,
                )
        except Exception as exc:
            self.repository.update_web_job(
                project_id,
                job_id,
                state=(
                    WebJobStatus.INTERRUPTED
                    if self._stopping.is_set()
                    else WebJobStatus.FAILED
                ),
                error=(
                    "The local web process stopped before this job finished."
                    if self._stopping.is_set()
                    else f"{type(exc).__name__}: {exc}"[:4000]
                ),
            )

    def shutdown(self) -> None:
        self._stopping.set()
        for project_id in self.repository.project_ids():
            job = self.repository.latest_web_job(project_id)
            if job is None or job.state not in {
                WebJobStatus.PENDING,
                WebJobStatus.RUNNING,
            }:
                continue
            project = self.repository.project(project_id)
            if project.status == ProjectStatus.RESEARCHING:
                self.repository.set_project_status(
                    project_id, ProjectStatus.RESEARCHING, pause=True
                )
            self.repository.update_web_job(
                project_id,
                job.id,
                state=WebJobStatus.INTERRUPTED,
                error="The local web process stopped before this job finished.",
            )
        self.executor.shutdown(wait=False, cancel_futures=True)
