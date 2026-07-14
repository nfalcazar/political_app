from pathlib import Path

import pytest

from research_app.domain import EvidenceDraft, ResearchPlan
from research_app.models import ProjectStatus, TaskStatus
from research_app.planner import Planner
from research_app.renderer import DossierRenderer
from research_app.researcher import ResearchEngine


THESIS = (
    "Greater worker unionization improves economic outcomes for US workers and "
    "reduces inequality without imposing larger economy-wide costs."
)


def approved_project(repository, tmp_path):
    project = repository.create_project(THESIS, "Labor unions")
    plan = Planner(repository).create_plan(project.id)
    path = tmp_path / "plan.json"
    plan.write(path)
    loaded = ResearchPlan.read(path)
    assert repository.approve_plan(loaded) == 9
    return project


def test_project_requires_approved_plan(repository):
    project = repository.create_project(THESIS)
    with pytest.raises(ValueError, match="approved plan"):
        ResearchEngine(repository).run(project.id)


def test_plan_is_editable_and_requires_matching_thesis(repository, tmp_path):
    project = repository.create_project(THESIS)
    plan = Planner(repository).create_plan(project.id)
    plan.propositions[0].text = "Edited and approved proposition."
    path = tmp_path / "plan.json"
    plan.write(path)
    loaded = ResearchPlan.read(path)
    repository.approve_plan(loaded)
    edited = next(
        item for item in repository.propositions(project.id) if item.plan_key == "wages"
    )
    assert edited.text == "Edited and approved proposition."

    stale = ResearchPlan.read(path)
    repository.revise_thesis(project.id, "A revised thesis")
    with pytest.raises(ValueError, match="current thesis"):
        repository.approve_plan(stale)


def test_run_without_external_providers_reaches_review(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    result = ResearchEngine(repository).run(project.id)
    assert result["search_configured"] is False
    assert repository.status(project.id)["status"] == ProjectStatus.EVIDENCE_REVIEW.value
    with pytest.raises(ValueError, match="new thesis version"):
        Planner(repository).create_plan(project.id)


def test_tasks_are_idempotent(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    first = repository.get_or_create_task(project.id, "web_search", {"query": "union wages"})
    repository.start_task(first.id)
    repository.complete_task(first.id, {"source_ids": ["one"]})
    second = repository.get_or_create_task(project.id, "web_search", {"query": "union wages"})
    assert first.id == second.id
    assert second.status == TaskStatus.COMPLETE.value
    assert second.attempts == 1


def test_pause_and_thesis_revision_are_durable(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    repository.set_project_status(project.id, ProjectStatus.PAUSED.value, pause=True)
    assert repository.should_pause(project.id)
    revised = repository.revise_thesis(project.id, "Union policy should be evaluated by sector.")
    assert revised.version == 2
    status = repository.status(project.id)
    assert status["status"] == ProjectStatus.DRAFT.value
    assert status["thesis"] == revised.text


def test_primary_source_gate_and_offline_render(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    proposition = repository.propositions(project.id)[0]
    secondary = repository.add_source(
        "https://example.com/article", title="Commentary", is_primary=False
    )
    repository.store_source_content(
        secondary.id,
        "A sufficiently long secondary passage about labor research.",
        [("paragraph 1", "A sufficiently long secondary passage about labor research.")],
    )
    secondary_chunk = repository.source(secondary.id).chunks[0]
    draft = EvidenceDraft(
        finding="A finding",
        excerpt=secondary_chunk.content,
        locator=secondary_chunk.locator,
        relationship="supports",
        explanation="It bears on the proposition.",
    )
    with pytest.raises(ValueError, match="primary source"):
        repository.add_evidence(
            proposition.id, secondary.id, secondary_chunk.id, draft
        )

    primary = repository.add_source(
        "https://www.bls.gov/example-study",
        title="Union membership study",
        publisher="BLS",
        source_type="government_data",
        is_primary=True,
    )
    excerpt = "The study found a measurable union wage premium in the covered sample."
    repository.store_source_content(primary.id, excerpt, [("table 2", excerpt)])
    primary_chunk = repository.source(primary.id).chunks[0]
    with pytest.raises(ValueError, match="verbatim"):
        repository.add_evidence(
            proposition.id,
            primary.id,
            primary_chunk.id,
            EvidenceDraft(
                finding="An invented finding.",
                excerpt="Words that do not appear in the source.",
                locator="table 2",
                relationship="supports",
                explanation="Invalid evidence.",
            ),
        )
    evidence = repository.add_evidence(
        proposition.id,
        primary.id,
        primary_chunk.id,
        EvidenceDraft(
            finding="The covered sample had a measurable union wage premium.",
            excerpt=excerpt,
            locator="table 2",
            relationship="supports",
            explanation="The result directly measures the proposition's wage outcome.",
            geography="United States",
            confidence="high",
        ),
    )
    output = DossierRenderer(repository).render(project.id, tmp_path / "dossier.md")
    text = output.read_text()
    assert evidence.id in text
    assert primary.canonical_url in text
    assert "Evidence gap" in text
    assert secondary.canonical_url not in text


def test_conflicting_evidence_is_preserved(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    proposition = repository.propositions(project.id)[0]
    source = repository.add_source(
        "https://www.bls.gov/two-results", is_primary=True, source_type="government_data"
    )
    text = "Study A reports a positive result. Study B reports a negative result."
    repository.store_source_content(source.id, text, [("results", text)])
    chunk = repository.source(source.id).chunks[0]
    for finding, relationship in (
        ("Study A reports a positive result.", "supports"),
        ("Study B reports a negative result.", "challenges"),
    ):
        repository.add_evidence(
            proposition.id,
            source.id,
            chunk.id,
            EvidenceDraft(
                finding=finding,
                excerpt=finding,
                locator="results",
                relationship=relationship,
                explanation="Directly relevant result.",
            ),
        )
    status = repository.status(project.id)
    assert status["evidence"] == {"supports": 1, "challenges": 1}


def test_revision_keeps_old_evidence_and_accepts_new_plan(repository, tmp_path):
    project = approved_project(repository, tmp_path)
    old_proposition = repository.propositions(project.id)[0]
    source = repository.add_source(
        "https://www.bls.gov/versioned-evidence", is_primary=True
    )
    text = "The original thesis version has durable evidence attached to it."
    repository.store_source_content(source.id, text, [("result", text)])
    chunk = repository.source(source.id).chunks[0]
    evidence = repository.add_evidence(
        old_proposition.id,
        source.id,
        chunk.id,
        EvidenceDraft(
            finding=text,
            excerpt=text,
            locator="result",
            relationship="mixed",
            explanation="Versioned result.",
        ),
    )
    repository.set_evidence_embedding(evidence.id, [1.0, 0.0, 0.0])
    assert repository.similar_evidence([1.0, 0.0, 0.0])[0] == (evidence.id, 0.0)

    repository.revise_thesis(project.id, "Union effects vary materially by industry.")
    new_plan = Planner(repository).create_plan(project.id)
    repository.approve_plan(new_plan)
    assert repository.current_thesis(project.id).version == 2
    assert all(item.thesis_version == 2 for item in repository.propositions(project.id))
    assert repository.project_evidence(project.id) == []
    assert repository.similar_evidence([1.0, 0.0, 0.0])[0][0] == evidence.id
