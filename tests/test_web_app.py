import httpx2
import pytest

from research_app.config import Settings
from research_app.json_repository import JsonRepository
from research_app.providers import Usage
from research_app.researcher import ResearchEngine
from research_app.web import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


class ManualFuture:
    def __init__(self, fn, args):
        self.fn = fn
        self.args = args
        self._done = False

    def run(self):
        self.fn(*self.args)
        self._done = True

    def done(self):
        return self._done


class ManualExecutor:
    def __init__(self):
        self.futures = []

    def submit(self, fn, *args):
        future = ManualFuture(fn, args)
        self.futures.append(future)
        return future

    def run_next(self):
        next(item for item in self.futures if not item.done()).run()

    def shutdown(self, wait=False, cancel_futures=False):
        return None


class FakeAI:
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, fail_plan=False):
        self.fail_plan = fail_plan

    def json_completion(self, prompt, operation):
        if operation == "plan":
            if self.fail_plan:
                raise RuntimeError("planning unavailable")
            return {
                "propositions": [
                    {
                        "key": "outcomes",
                        "text": "The claimed measurable outcome occurs.",
                        "kind": "empirical",
                        "polarity": "neutral",
                        "scope": {
                            "geography": "United States",
                            "population": None,
                            "timeframe": None,
                        },
                        "search_queries": ["official outcome data"],
                    }
                ]
            }, Usage()
        raise AssertionError(f"Unexpected operation: {operation}")


def settings(tmp_path):
    return Settings(
        store="json",
        data_dir=tmp_path / "store",
        database_url=None,
        embedding_model="text-embedding-3-small",
        codex_executable="codex",
        codex_timeout=10,
        reasoning_provider="deepseek",
        search_provider="none",
    )


def make_test_app(tmp_path, *, ai=None, executor=None, recover_orphans=True):
    configured = settings(tmp_path)
    repository = JsonRepository(configured.data_dir)
    executor = executor or ManualExecutor()
    app = create_app(
        configured,
        services=(repository, ai or FakeAI(), None, None),
        executor=executor,
        recover_orphans=recover_orphans,
        engine_factory_override=lambda project_id, limits: ResearchEngine(
            repository,
            max_source_attempts=limits["max_sources"],
            max_queries=limits["max_queries"],
            max_runtime_seconds=limits["max_runtime_seconds"],
        ),
    )
    return app, repository, executor


@pytest.mark.anyio
async def test_claim_runs_in_background_and_exposes_brief(tmp_path):
    app, repository, executor = make_test_app(tmp_path)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/projects",
            json={"claim": "Public investment improves economic mobility."},
        )
        assert response.status_code == 202
        project_id = response.json()["project_id"]
        assert repository.latest_web_job(project_id).state == "pending"
        assert (await client.get(f"/api/projects/{project_id}")).json()["scope"] == []

        executor.run_next()
        status = (await client.get(f"/api/projects/{project_id}")).json()
        assert status["job"]["state"] == "complete"
        assert status["project"]["status"] == "evidence_review"
        assert status["scope"][0]["text"] == "The claimed measurable outcome occurs."
        runs = repository._project_data(project_id)["runs"]
        approval = next(item for item in runs if item["operation"] == "web_auto_approve")
        assert approval["metadata_"]["authorization"] == "user_submitted_claim"

        brief = (await client.get(f"/api/projects/{project_id}/brief")).json()
        assert brief["assessment"]["label"] == "insufficient_evidence"
        assert brief["sources"] == []

        answer = await client.post(
            f"/api/projects/{project_id}/messages",
            json={"message": "What does the evidence say?"},
        )
        assert answer.status_code == 200
        assert answer.json()["assistant"]["needs_additional_research"]


@pytest.mark.anyio
async def test_continuation_is_explicit_and_bounded(tmp_path):
    app, repository, executor = make_test_app(tmp_path)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_id = (await client.post(
            "/api/projects", json={"claim": "A detailed public policy claim to examine."}
        )).json()["project_id"]
        executor.run_next()
        response = await client.post(f"/api/projects/{project_id}/continue")
        assert response.status_code == 202
        assert response.json()["job"]["limits"] == {
            "max_sources": 5,
            "max_queries": 15,
            "max_runtime_seconds": 300,
        }
        executor.run_next()
        assert repository.research_pass(project_id) == 2
        assert (await client.post(f"/api/projects/{project_id}/continue")).status_code == 409


@pytest.mark.anyio
async def test_failed_job_is_visible_and_resumable(tmp_path):
    app, repository, executor = make_test_app(tmp_path, ai=FakeAI(fail_plan=True))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_id = (await client.post(
            "/api/projects", json={"claim": "A detailed public policy claim to examine."}
        )).json()["project_id"]
        executor.run_next()
        status = (await client.get(f"/api/projects/{project_id}")).json()
        assert status["job"]["state"] == "failed"
        assert "planning unavailable" in status["job"]["error"]
        assert status["actions"]["can_resume"]


@pytest.mark.anyio
async def test_orphaned_job_is_marked_interrupted_and_can_resume(tmp_path):
    app, repository, _ = make_test_app(tmp_path, recover_orphans=False)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_id = (await client.post(
            "/api/projects", json={"claim": "A detailed public policy claim to examine."}
        )).json()["project_id"]
    assert repository.latest_web_job(project_id).state == "pending"

    restarted_executor = ManualExecutor()
    restarted = create_app(
        settings(tmp_path),
        services=(repository, FakeAI(), None, None),
        executor=restarted_executor,
        recover_orphans=True,
        engine_factory_override=lambda project_id, limits: ResearchEngine(repository),
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        status = (await client.get(f"/api/projects/{project_id}")).json()
        assert status["job"]["state"] == "interrupted"
        assert (await client.post(f"/api/projects/{project_id}/resume")).status_code == 202
        restarted_executor.run_next()
        assert repository.latest_web_job(project_id).state == "complete"


@pytest.mark.anyio
async def test_pause_and_missing_project_errors(tmp_path):
    app, repository, _ = make_test_app(tmp_path)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/projects", json={"claim": "A detailed public policy claim to examine."}
        )
        project_id = response.json()["project_id"]
        repository.set_project_status(project_id, "researching")
        assert (await client.post(f"/api/projects/{project_id}/pause")).status_code == 200
        assert repository.should_pause(project_id)
        assert (await client.get("/api/projects/not-real")).status_code == 404


@pytest.mark.anyio
async def test_shutdown_marks_queued_job_interrupted(tmp_path):
    app, repository, _ = make_test_app(tmp_path, recover_orphans=False)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_id = (await client.post(
            "/api/projects", json={"claim": "A detailed public policy claim to examine."}
        )).json()["project_id"]
    app.state.jobs.shutdown()
    assert repository.latest_web_job(project_id).state == "interrupted"


@pytest.mark.anyio
async def test_static_client_uses_safe_dom_rendering(tmp_path):
    app, _, _ = make_test_app(tmp_path)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/")).status_code == 200
        script = (await client.get("/static/app.js")).text
        assert "textContent" in script
        assert "innerHTML" not in script
        assert 'link.rel = "noopener noreferrer"' in script
