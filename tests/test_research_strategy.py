from research_app.json_repository import JsonRepository
from research_app.planner import Planner
from research_app.researcher import ResearchEngine
from research_app.content_policy import TokenCounter
from research_app.sources import RetrievedDocument
from research_app.query_graph import MAX_QUERY_DEPTH
import pytest


def test_first_pass_searches_all_propositions_before_second_queries(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    plan = Planner(repository).create_plan(project.id)
    repository.approve_plan(plan)
    engine = ResearchEngine(repository)
    schedule = list(engine._query_schedule(project.id))
    empirical_count = len(
        [item for item in repository.propositions(project.id) if item.kind == "empirical"]
    )
    first_round = schedule[:empirical_count]
    assert len({proposition.id for proposition, _ in first_round}) == empirical_count
    assert all("official data" in query for _, query in first_round)
    batches = list(engine._discovery_batches(project.id))
    assert len(batches) == 3
    assert all(len(batch) <= 3 for batch in batches)


def test_gap_pass_targets_uncovered_propositions(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    plan = Planner(repository).create_plan(project.id)
    repository.approve_plan(plan)
    repository.advance_research_pass(project.id)
    schedule = list(ResearchEngine(repository)._query_schedule(project.id))
    assert schedule
    assert all(
        "counter evidence" in query or "sector differences" in query
        for _, query in schedule
    )


def test_embedding_failure_pauses_project_and_records_warning(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))

    class BrokenEmbeddingProvider:
        model = "text-embedding-3-small"
        hard_max_tokens = 1024

        def embeddings(self, texts):
            raise RuntimeError("temporary embedding outage")

    result = ResearchEngine(
        repository, embedding_provider=BrokenEmbeddingProvider()
    ).run(project.id)
    assert result["paused"]
    assert result["stop_reason"] == "embedding_failure"
    assert repository.project(project.id).status == "paused"
    assert any(run["operation"] == "embedding_failure" for run in repository._project_data(project.id)["runs"])


def test_source_limit_counts_successes_not_failed_attempts(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    proposition = next(
        item for item in repository.propositions(project.id) if item.kind == "empirical"
    )
    for url, title in (
        ("https://example.gov/a-failure", "A failed source"),
        ("https://example.gov/b-success", "B successful source"),
    ):
        repository.add_source(
            url,
            title=title,
            is_primary=True,
            metadata={"proposition_id": proposition.id},
        )

    class OneFailureThenSuccess:
        def retrieve(self, url):
            if url.endswith("a-failure"):
                raise ValueError("temporary retrieval failure")
            text = (
                proposition.text + " The report presents direct measured evidence. "
            ) * 24
            return RetrievedDocument(text, [("paragraph 1", text)], "Report", [])

    result = ResearchEngine(
        repository,
        retriever=OneFailureThenSuccess(),
        max_source_attempts=1,
    ).run(project.id)

    assert result["source_attempts"] == 2
    assert result["successful_sources"] == 1
    assert result["max_successful_sources"] == 1
    assert result["stop_reason"] == "successful_source_limit"


def test_legacy_oversized_chunks_are_repaired_before_embedding(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    proposition = next(item for item in repository.propositions(project.id) if item.kind == "empirical")
    source = repository.add_source(
        "https://history.state.gov/oversized",
        is_primary=True,
        metadata={"proposition_id": proposition.id},
    )
    huge = "official evidence without punctuation " * 12000
    repository.store_source_content(source.id, huge, [("paragraph 1", huge)])
    engine = ResearchEngine(repository)
    assert engine._repair_oversized_chunks(project.id) == 1
    repaired = repository.source(source.id)
    assert len(repaired.chunks) > 1
    assert max(TokenCounter().count(chunk.content) for chunk in repaired.chunks) <= 1024


def test_query_graph_is_persistent_deduplicated_and_depth_limited(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    added = repository.seed_query_graph(project.id)
    assert added > 0
    nodes = repository.query_nodes(project.id)
    assert {node.query_kind for node in nodes} >= {
        "direct_primary", "official_record", "scholarly", "counterevidence", "mechanism"
    }
    assert repository.seed_query_graph(project.id) == 0
    duplicate = repository.add_query_node(project.id, {
        "query": nodes[0].query.upper(), "query_kind": nodes[0].query_kind
    })
    assert duplicate is None
    with pytest.raises(ValueError):
        repository.add_query_node(project.id, {
            "query": "A valid but excessively deep follow-up query",
            "query_kind": "evidence_gap",
            "depth": MAX_QUERY_DEPTH + 1,
        })
    repository.update_query_node(project.id, nodes[0].id, status="complete", attempts=1)
    assert repository.query_nodes(project.id)[0].status == "complete"
    repository.update_query_node(project.id, nodes[1].id, status="running", attempts=1)
    assert repository.next_query_node(project.id).id == nodes[1].id


def test_query_graph_preserves_planner_queries_and_searches_breadth_first(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    propositions = [
        item
        for item in repository.propositions(project.id)
        if item.kind == "empirical" and item.origin == "planned"
    ]
    repository.seed_query_graph(project.id)
    nodes = repository.query_nodes(project.id)
    first = propositions[0]
    by_kind = {
        node.query_kind: node.query
        for node in nodes
        if node.proposition_ids == [first.id]
    }
    assert by_kind["official_record"] == first.search_queries[0]
    assert by_kind["scholarly"] == first.search_queries[1]
    assert by_kind["counterevidence"] == first.search_queries[2]
    assert by_kind["mechanism"] == first.search_queries[3]

    selected = []
    for _ in propositions:
        node = repository.next_query_node(project.id)
        selected.append(node)
        repository.update_query_node(
            project.id, node.id, status="complete", attempts=1
        )
    assert len({node.proposition_ids[0] for node in selected}) == len(propositions)
    assert all(
        node.query_kind in {"direct_primary", "official_record", "scholarly"}
        for node in selected
    )


def test_document_quality_separates_retrieval_from_relevance():
    source = type("Source", (), {
        "metadata_": {"discovered_for": ["p1"], "search_relevance_score": 0}
    })()
    short = ResearchEngine._document_quality(
        source, "worker outcomes " * 10,
        {"chunk": [{
            "proposition_id": "p1", "lexical_score": 12,
            "matched_terms": ["worker", "outcomes", "earnings"],
        }]},
    )
    irrelevant = ResearchEngine._document_quality(
        source, "astronomy telescope observations " * 40,
        {"chunk": [{
            "proposition_id": "p1", "lexical_score": 0, "matched_terms": [],
        }]},
    )
    usable = ResearchEngine._document_quality(
        source, "worker earnings benefits outcomes " * 40,
        {"chunk": [{
            "proposition_id": "p1", "lexical_score": 12,
            "matched_terms": ["worker", "earnings", "benefits", "outcomes"],
        }]},
    )
    assert not short["usable"]
    assert not irrelevant["usable"]
    assert usable["usable"]


def test_extraction_uses_only_sources_discovered_for_the_proposition(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    propositions = [
        item for item in repository.propositions(project.id) if item.kind == "empirical"
    ]
    first, second = propositions[:2]
    first_source = repository.add_source(
        "https://example.gov/first", title="First source", is_primary=True,
        metadata={"discovered_for": [first.id]},
    )
    second_source = repository.add_source(
        "https://example.gov/second", title="Second source", is_primary=True,
        metadata={"discovered_for": [second.id]},
    )
    first_text = first.text + " This report contains direct measured evidence."
    second_text = second.text + " This separate report concerns another proposition."
    repository.store_source_content(
        first_source.id, first_text, [("paragraph 1", first_text)]
    )
    repository.store_source_content(
        second_source.id, second_text, [("paragraph 1", second_text)]
    )

    class AI:
        provider_name = "fake"
        supports_embeddings = False
        prompts = []
        def json_completion(self, prompt, operation):
            self.prompts.append(prompt)
            return {"evidence": []}, type("Usage", (), {
                "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0
            })()

    ai = AI()
    engine = ResearchEngine(repository, ai=ai)
    engine._extract_across_sources(
        project.id,
        first.id,
        [repository.source(first_source.id), repository.source(second_source.id)],
    )
    assert first_source.id in ai.prompts[0]
    assert second_source.id not in ai.prompts[0]


def test_exact_quote_repair_copies_source_sentence_without_relaxing_match():
    original = (
        "The evaluation found that transit access increased employment by twelve percent "
        "among participants in the treatment group while reducing average commute times "
        "and increasing access to jobs in neighboring employment centers."
    )
    altered = (
        "Researchers concluded that transit access increased employment by twelve percent "
        "among participants in the treatment group while reducing average commute times "
        "and increasing access to jobs in neighboring employment centers."
    )
    repaired = ResearchEngine._repair_exact_excerpt(altered, original)
    assert repaired == original
    assert ResearchEngine._repair_exact_excerpt("unrelated short claim", original) is None


def test_query_graph_records_stop_reason_in_status(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    repository.seed_query_graph(project.id)
    repository.record_query_graph_stop(project.id, "query_limit", {"queries_executed": 3})
    summary = repository.status(project.id)["query_graph"]
    assert summary["last_stop_reason"] == "query_limit"
    assert summary["last_run_metrics"]["queries_executed"] == 3


def test_recorded_benchmark_does_not_require_live_web(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    proposition = next(item for item in repository.propositions(project.id) if item.kind == "empirical")
    source = repository.add_source(
        "https://example.gov/report", is_primary=True,
        metadata={"discovered_for": [proposition.id]},
    )
    repository.record_source_retrieval(
        source.id,
        [{"method": "http", "url": source.canonical_url, "outcome": "http_403"}],
        outcome="http_403",
    )
    report = repository.retrieval_benchmark(project.id)
    assert report["primary_attempted"] == 1
    assert report["policy_rejections"] == {"http_403": 1}


def test_query_budget_and_no_novelty_saturation_are_deterministic(tmp_path):
    class EmptySearch:
        provider_name = "fake"
        def search(self, _query, limit=6):
            return []

    repository = JsonRepository(tmp_path / "budget")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    result = ResearchEngine(
        repository, search=EmptySearch(), max_source_attempts=1, max_queries=2
    ).run(project.id)
    assert result["queries_executed"] == 2
    assert result["stop_reason"] == "query_limit"

    repository = JsonRepository(tmp_path / "saturation")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    result = ResearchEngine(
        repository, search=EmptySearch(), max_source_attempts=1, max_queries=20
    ).run(project.id)
    empirical_count = len(
        [item for item in repository.propositions(project.id) if item.kind == "empirical"]
    )
    assert result["queries_executed"] == max(5, empirical_count)
    assert result["stop_reason"] == "query_saturation"


def test_model_query_validation_rejects_urls_and_irrelevant_expansions(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))
    proposition = next(item for item in repository.propositions(project.id) if item.kind == "empirical")
    engine = ResearchEngine(repository)
    assert not engine._query_is_relevant(
        project.id, "https://example.com/results", [proposition.id]
    )
    assert not engine._query_is_relevant(
        project.id, "astronomy telescope observations", [proposition.id]
    )
    assert engine._query_is_relevant(
        project.id, f"{proposition.text} administrative records", [proposition.id]
    )


def test_new_query_sources_are_retrieved_before_more_searches(tmp_path):
    repository = JsonRepository(tmp_path / "store")
    project = repository.create_project("Labor unions improve worker outcomes.")
    repository.approve_plan(Planner(repository).create_plan(project.id))

    class Search:
        provider_name = "fake"
        calls = 0
        def search(self, _query, limit=6):
            self.calls += 1
            return [{
                "url": "https://example.gov/report",
                "title": "Official report",
                "claimed_primary": True,
            }]

    class Retriever:
        def retrieve(self, _url):
            text = (
                "Labor unions improve measurable economic outcomes, earnings, and benefits "
                "for covered workers. " * 24
            )
            return RetrievedDocument(text, [("paragraph 1", text)], "Report", [])

    search = Search()
    result = ResearchEngine(
        repository,
        search=search,
        retriever=Retriever(),
        max_source_attempts=1,
        max_queries=20,
    ).run(project.id)
    assert result["successful_sources"] == 1
    empirical_count = len(
        [item for item in repository.propositions(project.id) if item.kind == "empirical"]
    )
    assert search.calls == empirical_count
