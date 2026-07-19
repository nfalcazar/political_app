from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from .briefs import build_brief
from .chat import EvidenceChatService
from .config import Settings
from .jobs import CONTINUATION_LIMITS, INITIAL_LIMITS, ResearchJobManager
from .planner import Planner
from .researcher import ResearchEngine
from .services import make_retriever, make_services
from .states import ProjectStatus


STATIC_DIR = Path(__file__).with_name("web_static")


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=10, max_length=2000)
    title: str | None = Field(default=None, max_length=160)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _job_dict(job) -> dict | None:
    return asdict(job) if job is not None else None


def _not_found(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def create_app(
    settings: Settings | None = None,
    *,
    services=None,
    executor=None,
    recover_orphans: bool = True,
    engine_factory_override=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.store != "json":
        raise ValueError("The local web prototype currently supports only RESEARCH_STORE=json")
    repository, ai, search, embedder = services or make_services(
        settings, SimpleNamespace(store="json")
    )

    def debug_context(project_id: str) -> None:
        if hasattr(ai, "set_debug_context"):
            ai.set_debug_context(project_id)

    def planner_factory(project_id: str):
        debug_context(project_id)
        return Planner(repository, ai)

    def engine_factory(project_id: str, limits: dict):
        if engine_factory_override is not None:
            return engine_factory_override(project_id, limits)
        debug_context(project_id)
        return ResearchEngine(
            repository,
            search=search,
            ai=ai,
            model=getattr(ai, "model", None),
            embedding_model=settings.embedding_model,
            embedding_provider=embedder,
            max_source_attempts=int(limits["max_sources"]),
            max_queries=int(limits["max_queries"]),
            max_runtime_seconds=int(limits["max_runtime_seconds"]),
            retriever=make_retriever(settings),
            passages_per_proposition=settings.source_passages_per_proposition,
            passage_cap=settings.source_passage_cap,
        )

    jobs = ResearchJobManager(
        repository,
        planner_factory=planner_factory,
        engine_factory=engine_factory,
        executor=executor,
        recover_orphans=recover_orphans,
    )
    chat = EvidenceChatService(repository, ai)
    static_assets = {
        "app.js": (STATIC_DIR / "app.js").read_text(encoding="utf-8"),
        "styles.css": (STATIC_DIR / "styles.css").read_text(encoding="utf-8"),
    }
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()

    app = FastAPI(
        title="Policy Claim Research", version="0.1.0", lifespan=lifespan
    )
    app.state.repository = repository
    app.state.jobs = jobs
    app.state.chat = chat
    @app.get("/", include_in_schema=False)
    async def index():
        return HTMLResponse(index_html)

    @app.get("/projects/{project_id}", include_in_schema=False)
    async def project_page(project_id: str):
        return HTMLResponse(index_html)

    @app.get("/static/{asset}", include_in_schema=False)
    async def static_asset(asset: str):
        content = static_assets.get(asset)
        if content is None:
            raise HTTPException(status_code=404, detail="Static asset not found")
        media_type = "application/javascript" if asset.endswith(".js") else "text/css"
        return Response(content, media_type=media_type)

    @app.post("/api/projects", status_code=202)
    async def create_project(request: ClaimRequest):
        claim = request.claim.strip()
        if len(claim) < 10:
            raise HTTPException(status_code=422, detail="Claim must contain at least 10 characters")
        title = request.title.strip() if request.title else None
        project = repository.create_project(claim, title or None)
        job = jobs.enqueue(project.id, "initial", INITIAL_LIMITS)
        return {
            "project_id": project.id,
            "job_id": job.id,
            "state": job.state,
            "url": f"/projects/{project.id}",
        }

    @app.get("/api/projects/{project_id}")
    async def project_status(project_id: str):
        try:
            status = repository.status(project_id)
            job = repository.latest_web_job(project_id)
            scope = [
                {
                    "id": item.id,
                    "key": item.plan_key,
                    "text": item.text,
                    "kind": item.kind,
                    "scope": item.scope,
                    "origin": item.origin,
                }
                for item in repository.propositions(project_id)
            ]
        except ValueError as exc:
            raise _not_found(exc) from exc
        return {
            "project": status,
            "job": _job_dict(job),
            "scope": scope,
            "actions": {
                "can_pause": jobs.has_active_job(project_id)
                and status["status"] == ProjectStatus.RESEARCHING,
                "can_resume": not jobs.has_active_job(project_id)
                and (
                    status["status"]
                    in {ProjectStatus.DRAFT, ProjectStatus.PLANNED, ProjectStatus.RESEARCHING, ProjectStatus.PAUSED}
                    or (job is not None and job.state in {"failed", "interrupted"})
                ),
                "can_continue": not jobs.has_active_job(project_id)
                and status["status"] == ProjectStatus.EVIDENCE_REVIEW
                and status["research_pass"] < 2,
            },
        }

    @app.get("/api/projects/{project_id}/brief")
    async def project_brief(project_id: str):
        try:
            return build_brief(repository, project_id)
        except ValueError as exc:
            raise _not_found(exc) from exc

    @app.get("/api/projects/{project_id}/messages")
    async def project_messages(project_id: str):
        try:
            return {"messages": chat.messages(project_id)}
        except ValueError as exc:
            raise _not_found(exc) from exc

    @app.post("/api/projects/{project_id}/messages")
    async def add_project_message(project_id: str, request: MessageRequest):
        try:
            repository.project(project_id)
        except ValueError as exc:
            raise _not_found(exc) from exc
        if jobs.has_any_active_job():
            raise HTTPException(
                status_code=409,
                detail="Wait for active research to finish before asking follow-up questions.",
            )
        try:
            return chat.answer(project_id, request.message)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"The reasoning provider could not answer this question: {exc}",
            ) from exc

    @app.post("/api/projects/{project_id}/pause")
    async def pause_project(project_id: str):
        try:
            repository.project(project_id)
        except ValueError as exc:
            raise _not_found(exc) from exc
        project = repository.project(project_id)
        if not jobs.has_active_job(project_id) or project.status != ProjectStatus.RESEARCHING:
            raise HTTPException(status_code=409, detail="No active research job to pause")
        repository.set_project_status(project_id, ProjectStatus.PAUSED, pause=True)
        return {"status": "pause_requested"}

    @app.post("/api/projects/{project_id}/resume", status_code=202)
    async def resume_project(project_id: str):
        try:
            project = repository.project(project_id)
        except ValueError as exc:
            raise _not_found(exc) from exc
        if jobs.has_active_job(project_id):
            raise HTTPException(status_code=409, detail="Research is already active")
        if project.status == ProjectStatus.EVIDENCE_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="Use the bounded continuation action from evidence review.",
            )
        if project.status not in {
            ProjectStatus.DRAFT,
            ProjectStatus.PLANNED,
            ProjectStatus.APPROVED,
            ProjectStatus.RESEARCHING,
            ProjectStatus.PAUSED,
        }:
            raise HTTPException(status_code=409, detail="This project cannot be resumed")
        repository.set_project_status(project_id, project.status, pause=False)
        mode = (
            "initial"
            if project.status in {ProjectStatus.DRAFT, ProjectStatus.PLANNED}
            else "resume"
        )
        job = jobs.enqueue(project_id, mode, INITIAL_LIMITS)
        return {"project_id": project_id, "job": _job_dict(job)}

    @app.post("/api/projects/{project_id}/continue", status_code=202)
    async def continue_project(project_id: str):
        try:
            status = repository.status(project_id)
        except ValueError as exc:
            raise _not_found(exc) from exc
        if jobs.has_active_job(project_id):
            raise HTTPException(status_code=409, detail="Research is already active")
        if status["status"] != ProjectStatus.EVIDENCE_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="Continuation is available only from evidence review.",
            )
        try:
            repository.advance_research_pass(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        job = jobs.enqueue(project_id, "continue", CONTINUATION_LIMITS)
        return {"project_id": project_id, "job": _job_dict(job)}

    return app


def main() -> None:
    import uvicorn

    port = int(os.getenv("RESEARCH_WEB_PORT", "8000"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
