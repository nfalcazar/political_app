from types import SimpleNamespace

import pytest

from research_app.briefs import build_brief, select_key_sources, validate_synthesis
from research_app.chat import EvidenceChatService
from research_app.domain import EvidenceDraft
from research_app.json_repository import JsonRepository
from research_app.planner import Planner
from research_app.providers import Usage
from research_app.researcher import ResearchEngine


def project_with_evidence(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Public investment improves economic mobility.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    proposition = next(
        item for item in repository.propositions(project.id) if item.kind == "empirical"
    )
    rows = []
    for suffix, relationship in (("support", "supports"), ("challenge", "challenges")):
        source = repository.add_source(
            f"https://example.gov/{suffix}",
            title=f"<script>{suffix}</script>",
            publisher="Public agency",
            source_type="government_data",
            is_primary=True,
        )
        excerpt = f"The official {suffix} report records a measurable result."
        stored = repository.store_source_content(
            source.id, excerpt, [("table 1", excerpt)]
        )
        evidence = repository.add_evidence(
            proposition.id,
            source.id,
            stored.chunks[0].id,
            EvidenceDraft(
                finding=f"The {suffix} report records a measurable result.",
                excerpt=excerpt,
                locator="table 1",
                relationship=relationship,
                explanation="This directly bears on the proposition.",
                geography="United States",
                methodology="Administrative data",
                confidence="high",
            ),
        )
        rows.append(evidence)
    return repository, project, rows


def synthesis(support_id, challenge_id):
    return {
        "schema_version": 2,
        "assessment": {
            "label": "mixed",
            "summary": "The accepted evidence is mixed.",
            "rationale": "Direct findings point in different directions.",
            "evidence_ids": [support_id, challenge_id],
        },
        "arguments": [
            {
                "stance": "supports",
                "title": "Supporting result",
                "explanation": "One source reports the expected outcome.",
                "evidence_ids": [support_id],
            },
            {
                "stance": "challenges",
                "title": "Challenging result",
                "explanation": "Another source reports a conflicting outcome.",
                "evidence_ids": [challenge_id],
            },
        ],
        "uncertainty_and_gaps": ["The studies cover different samples."],
    }


def test_structured_synthesis_and_source_selection_are_traceable(tmp_path):
    repository, project, evidence = project_with_evidence(tmp_path)
    rows = repository.project_evidence(project.id)
    payload = synthesis(evidence[0].id, evidence[1].id)
    assert validate_synthesis(payload, rows) is payload
    repository.save_synthesis(project.id, payload)

    brief = build_brief(repository, project.id)
    assert brief["assessment"]["label"] == "mixed"
    assert {item["relationships"][0] for item in brief["sources"]} == {
        "supports",
        "challenges",
    }
    assert len(select_key_sources(rows)) == 2
    assert "<script>" in brief["sources"][0]["title"]


def test_synthesis_rejects_unknown_or_mismatched_evidence(tmp_path):
    repository, project, evidence = project_with_evidence(tmp_path)
    rows = repository.project_evidence(project.id)
    bad = synthesis(evidence[0].id, "unknown")
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_synthesis(bad, rows)

    bad = synthesis(evidence[0].id, evidence[1].id)
    bad["arguments"][0]["evidence_ids"] = [evidence[1].id]
    with pytest.raises(ValueError, match="not linked"):
        validate_synthesis(bad, rows)


def test_brief_falls_back_without_validated_synthesis(tmp_path):
    repository, project, _ = project_with_evidence(tmp_path)
    brief = build_brief(repository, project.id)
    assert brief["assessment"]["label"] == "insufficient_evidence"
    assert brief["sources"]


def test_chat_persists_only_valid_evidence_citations(tmp_path):
    repository, project, evidence = project_with_evidence(tmp_path)

    class AI:
        provider_name = "fake"
        model = "fake-model"

        def json_completion(self, prompt, operation):
            assert operation == "answer_question"
            assert evidence[0].id in prompt
            return {
                "answer": "The supporting report records a measurable result.",
                "citations": [evidence[0].id],
                "limitations": ["The evidence base is small."],
                "needs_additional_research": False,
            }, Usage(input_tokens=10, output_tokens=5)

    chat = EvidenceChatService(repository, AI())
    result = chat.answer(project.id, "What supports the claim?")
    assert result["assistant"]["citations"] == [evidence[0].id]
    assert [item["role"] for item in chat.messages(project.id)] == ["user", "assistant"]


def test_chat_rejects_invented_citations(tmp_path):
    repository, project, _ = project_with_evidence(tmp_path)

    class AI:
        provider_name = "fake"
        model = "fake-model"

        def json_completion(self, prompt, operation):
            return {
                "answer": "Invented answer",
                "citations": ["not-real"],
                "limitations": [],
                "needs_additional_research": False,
            }, Usage()

    with pytest.raises(ValueError, match="unknown evidence"):
        EvidenceChatService(repository, AI()).answer(project.id, "What happened?")
    assert len(repository.messages(project.id)) == 1


def test_chat_exposes_evidence_gap_without_model_call(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("A sufficiently detailed policy claim.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    result = EvidenceChatService(repository, SimpleNamespace()).answer(
        project.id, "What does the evidence say?"
    )
    assert result["assistant"]["needs_additional_research"]
    assert result["assistant"]["citations"] == []


def test_research_synthesis_saves_only_locally_validated_citations(tmp_path):
    repository, project, evidence = project_with_evidence(tmp_path)

    class AI:
        provider_name = "fake"
        model = "fake-model"

        def json_completion(self, prompt, operation):
            assert operation == "synthesize_findings"
            assert f'"evidence_id": "{evidence[0].id}"' in prompt
            return synthesis(evidence[0].id, evidence[1].id), Usage()

    ResearchEngine(repository, ai=AI())._synthesize(project.id)
    saved = repository.synthesis(project.id)
    assert saved["assessment"]["label"] == "mixed"
    assert set(saved["evidence_ids"]) == {item.id for item in evidence}
    task = next(
        item
        for item in repository._project_data(project.id)["tasks"]
        if item["task_type"] == "synthesize_findings"
    )
    assert task["status"] == "complete"


def test_invalid_research_synthesis_records_processing_failure(tmp_path):
    repository, project, evidence = project_with_evidence(tmp_path)

    class AI:
        provider_name = "fake"
        model = "fake-model"

        def json_completion(self, prompt, operation):
            return synthesis(evidence[0].id, "invented"), Usage()

    ResearchEngine(repository, ai=AI())._synthesize(project.id)
    assert repository.synthesis(project.id) == {}
    assert repository.status(project.id)["postprocess_failures"] == 1
