import json

import pytest

from research_app.domain import EvidenceDraft
from research_app.json_repository import JsonRepository
from research_app.planner import Planner
from research_app.renderer import DossierRenderer


THESIS = "Greater worker unionization improves economic outcomes for US workers."


@pytest.fixture
def json_repository(tmp_path):
    return JsonRepository(tmp_path / "data" / "tmp")


def approve(repository):
    project = repository.create_project(THESIS, "Union research")
    plan = Planner(repository).create_plan(project.id)
    repository.approve_plan(plan)
    return project


def test_json_workflow_and_atomic_records(json_repository, tmp_path):
    project = approve(json_repository)
    project_path = json_repository.root / "projects" / project.id / "project.json"
    assert json.loads(project_path.read_text())["schema_version"] == 1
    assert not list(project_path.parent.glob(".project.json.*"))

    first = json_repository.get_or_create_task(
        project.id, "web_search", {"query": "union wages"}
    )
    json_repository.start_task(first.id)
    json_repository.complete_task(first.id, {"source_ids": []})
    second = json_repository.get_or_create_task(
        project.id, "web_search", {"query": "union wages"}
    )
    assert second.id == first.id
    assert second.status == "complete"


def test_source_evidence_catalog_and_offline_render(json_repository, tmp_path):
    project = approve(json_repository)
    proposition = next(
        item for item in json_repository.propositions(project.id) if item.plan_key == "wages"
    )
    source = json_repository.add_source(
        "https://www.bls.gov/report?utm_source=test",
        title="Union wage report",
        is_primary=True,
        source_type="government_data",
    )
    excerpt = "The report identifies a measurable wage difference for union workers."
    json_repository.store_source_content(source.id, excerpt, [("table 1", excerpt)])
    source = json_repository.source(source.id)
    evidence = json_repository.add_evidence(
        proposition.id,
        source.id,
        source.chunks[0].id,
        EvidenceDraft(
            finding="The report identifies a union wage difference.",
            excerpt=excerpt,
            locator="table 1",
            relationship="supports",
            explanation="The result directly measures the wage proposition.",
        ),
    )
    candidates = json_repository.lexical_evidence_candidates("union wage difference")
    assert candidates[0][0] == evidence.id

    dossier = DossierRenderer(json_repository).render(
        project.id, tmp_path / "dossier.md"
    )
    assert evidence.id in dossier.read_text()
    rebuilt = json_repository.rebuild_catalog()
    assert rebuilt == {"sources": 1, "errors": []}


def test_second_pass_is_explicit_and_bounded(json_repository):
    project = approve(json_repository)
    assert json_repository.research_pass(project.id) == 1
    assert json_repository.advance_research_pass(project.id) == 2
    with pytest.raises(ValueError, match="only one"):
        json_repository.advance_research_pass(project.id)


def test_doctor_reports_corrupt_json(json_repository):
    bad = json_repository.sources_dir / "broken.json"
    bad.write_text("{not-json")
    result = json_repository.doctor()
    assert result["writable"]
    assert len(result["errors"]) == 1
    assert "broken.json" in result["errors"][0]


def test_embedding_metadata_and_synthesis_are_persistent(json_repository):
    project = json_repository.create_project("A test thesis")
    from research_app.planner import Planner
    plan = Planner(json_repository).create_plan(project.id)
    json_repository.approve_plan(plan)
    proposition = json_repository.propositions(project.id)[0]
    metadata = {"model": "text-embedding-3-small", "input_hash": "abc", "dimensions": 2}
    json_repository.set_proposition_embedding(proposition.id, [1.0, 0.0], metadata)
    stored = next(item for item in json_repository.propositions(project.id) if item.id == proposition.id)
    assert stored.embedding == [1.0, 0.0]
    assert stored.embedding_metadata == metadata
    json_repository.save_synthesis(project.id, {"abstract": "Stored synthesis", "input_hash": "one"})
    assert json_repository.synthesis(project.id)["abstract"] == "Stored synthesis"


def test_catalog_can_be_rebuilt_when_catalog_json_is_corrupt(json_repository):
    source = json_repository.add_source("https://www.bls.gov/recover", is_primary=True)
    json_repository.catalog_path.write_text("{broken")
    result = json_repository.rebuild_catalog()
    assert result == {"sources": 1, "errors": []}
    assert json.loads(json_repository.catalog_path.read_text())["urls"] == {
        source.canonical_url: source.id
    }


def test_unknown_rights_full_text_is_private_temporary_cache(json_repository):
    source = json_repository.add_source("https://example.com/copyrighted", is_primary=True)
    text = "A sufficiently detailed source passage for temporary processing."
    stored = json_repository.store_source_content(
        source.id,
        text,
        [("paragraph 1", text)],
        archive_chunks=[("paragraph 1", text)],
    )
    source_json = json.loads((json_repository.sources_dir / f"{source.id}.json").read_text())
    assert stored.rights_status == "unknown"
    assert source_json["normalized_content"] is None
    assert source_json["cache_metadata"]["expires_at"]
    archive = json_repository.documents_dir / f"{source.id}.json.gz"
    assert archive.exists()
    assert archive.stat().st_mode & 0o077 == 0
    assert json_repository.delete_source_cache(source.id)
    assert not archive.exists()


def test_reviewed_permission_removes_cache_expiration(json_repository):
    source = json_repository.add_source("https://example.com/permitted", is_primary=True)
    text = "The owner has permitted durable retention of this test source."
    json_repository.store_source_content(source.id, text, [("paragraph 1", text)])
    reviewed = json_repository.set_source_rights(
        source.id, "permission", basis="Written permission retained by operator"
    )
    assert reviewed.rights_status == "permission"
    assert reviewed.cache_metadata["expires_at"] is None
    assert json_repository.source_archive(source.id)["expires_at"] is None


def test_public_domain_archive_can_persist_and_evidence_snapshots_provenance(json_repository):
    project = approve(json_repository)
    proposition = next(item for item in json_repository.propositions(project.id) if item.kind == "empirical")
    source = json_repository.add_source(
        "https://history.state.gov/historicaldocuments/test",
        title="Federal historical record",
        publisher="U.S. Department of State",
        is_primary=True,
    )
    excerpt = "The official record documents the event and the participants involved."
    stored = json_repository.store_source_content(source.id, excerpt, [("document 1", excerpt)])
    evidence = json_repository.add_evidence(
        proposition.id,
        source.id,
        stored.chunks[0].id,
        EvidenceDraft(
            finding="The federal record documents the event.",
            excerpt=excerpt,
            locator="document 1",
            relationship="mixed",
            explanation="It provides contemporaneous documentation.",
        ),
    )
    assert stored.rights_status == "public_domain"
    assert not json_repository.delete_source_cache(source.id)
    assert evidence.source_url == stored.canonical_url
    assert evidence.source_rights_status == "public_domain"
    assert evidence.quote_word_count == len(excerpt.split())


def test_source_takedown_removes_content_and_prevents_refetch(json_repository):
    project = approve(json_repository)
    proposition = next(item for item in json_repository.propositions(project.id) if item.kind == "empirical")
    source = json_repository.add_source("https://example.com/remove-me", is_primary=True)
    excerpt = "A retained quotation that is removed following a source-owner request."
    stored = json_repository.store_source_content(source.id, excerpt, [("paragraph 1", excerpt)])
    json_repository.add_evidence(
        proposition.id,
        source.id,
        stored.chunks[0].id,
        EvidenceDraft(
            finding="The source contained a finding.", excerpt=excerpt, locator="paragraph 1",
            relationship="mixed", explanation="Temporary test evidence.",
        ),
    )
    result = json_repository.takedown_source(source.id, "owner request")
    removed = json_repository.source(source.id)
    assert result["evidence_deleted"] == 1
    assert removed.retrieval_status == "restricted"
    assert removed.chunks == []
    assert json_repository.source_block_reason(source.canonical_url) == "owner request"
    assert json_repository.project_evidence(project.id) == []
