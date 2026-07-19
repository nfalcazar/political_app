import json
from pathlib import Path
from types import SimpleNamespace

from research_app.providers import (
    CodexCliProvider, CodexWebSearchProvider, DeepSeekProvider,
    OpenAIEmbeddingProvider, CompositeSearchProvider,
)


def fake_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "codex"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

if sys.argv[1:3] == ['login', 'status']:
    print('Logged in')
    raise SystemExit(0)

output = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
schema = pathlib.Path(sys.argv[sys.argv.index('--output-schema') + 1]).name
prompt = sys.stdin.read()
if schema == 'web_search.json':
    query_key = 'p1' if 'proposition_id' in prompt else 'query'
    payload = {'candidates': [{'url': 'https://www.bls.gov/test', 'title': 'Test', 'publisher': 'BLS', 'reason': 'Primary data', 'stance': 'mixed', 'claimed_primary': True, 'query_key': query_key}]}
elif schema == 'plan.json':
    payload = {'propositions': [{'key': 'test', 'text': 'Test proposition', 'kind': 'empirical', 'polarity': 'neutral', 'scope': {}, 'search_queries': ['test query']}]}
else:
    payload = {'evidence': []}
output.write_text(json.dumps(payload))
"""
    )
    executable.chmod(0o755)
    return executable


def test_codex_provider_uses_login_and_structured_output(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_SHOULD_NOT_LEAK", "secret")
    executable = fake_codex(tmp_path)
    provider = CodexCliProvider(
        tmp_path / "runtime", executable=str(executable), timeout=10
    )
    assert provider.login_status()["ok"]
    payload, usage = provider.json_completion("Plan", "plan")
    assert payload["propositions"][0]["key"] == "test"
    assert usage.input_tokens == 0
    assert "SECRET_SHOULD_NOT_LEAK" not in provider._safe_environment()


def test_codex_web_search_maps_candidates(tmp_path):
    provider = CodexCliProvider(
        tmp_path / "runtime", executable=str(fake_codex(tmp_path)), timeout=10
    )
    results = CodexWebSearchProvider(provider).search("union wages")
    assert results[0]["url"] == "https://www.bls.gov/test"
    assert results[0]["stance_hint"] == "mixed"
    assert results[0]["query_key"] == "query"
    batched = CodexWebSearchProvider(provider).search_batch(
        [{"proposition_id": "p1", "proposition": "Union wages", "queries": ["query"]}]
    )
    assert batched[0]["query_key"] == "p1"


def test_deepseek_writes_raw_diagnostic(tmp_path):
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({
                "propositions": [{
                    "key": "test", "text": "Test", "kind": "empirical",
                    "polarity": "neutral",
                    "scope": {"geography": None, "population": None, "timeframe": None},
                    "search_queries": ["test"],
                }]
            })),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=8),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))
    )
    provider = DeepSeekProvider(
        "secret", client=client, debug_dir=tmp_path, max_attempts=1
    )
    payload, usage = provider.json_completion("private prompt", "plan")
    assert payload["propositions"][0]["key"] == "test"
    assert usage.input_tokens == 4
    artifact = next((tmp_path / "deepseek" / "unassigned").glob("*.json"))
    diagnostic = json.loads(artifact.read_text())
    assert diagnostic["prompt"] == "private prompt"
    assert diagnostic["status"] == "success"
    assert diagnostic["artifact_path"] == str(artifact)


def test_openai_embedding_provider_batches_inputs():
    seen = {}
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0, 0.0]), SimpleNamespace(embedding=[0.0, 1.0])],
        usage=SimpleNamespace(prompt_tokens=7),
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(
        create=lambda **kwargs: seen.update(kwargs) or response
    ))
    provider = OpenAIEmbeddingProvider("secret", client=client)
    vectors, usage = provider.embeddings(["one", "two"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert seen == {"model": "text-embedding-3-small", "input": ["one", "two"]}
    assert usage.input_tokens == 7


def test_openai_embedding_provider_rejects_oversized_individual_input():
    client = SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs: None))
    provider = OpenAIEmbeddingProvider("secret", client=client, hard_max_tokens=8)
    import pytest

    with pytest.raises(ValueError, match=r"input\[0\].*hard maximum"):
        provider.embeddings(["This sentence is intentionally longer than eight embedding tokens."])


def test_openai_embedding_provider_batches_by_token_budget():
    calls = []

    def create(**kwargs):
        calls.append(kwargs["input"])
        return SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[float(len(text))]) for i, text in enumerate(kwargs["input"])],
            usage=SimpleNamespace(prompt_tokens=sum(len(text.split()) for text in kwargs["input"])),
        )

    provider = OpenAIEmbeddingProvider(
        "secret",
        client=SimpleNamespace(embeddings=SimpleNamespace(create=create)),
        hard_max_tokens=20,
        batch_tokens=5,
        batch_items=32,
    )
    vectors, _ = provider.embeddings(["one two three", "four five six", "seven"])
    assert len(calls) >= 2
    assert vectors == [[13.0], [13.0], [5.0]]


def test_composite_search_deduplicates_title_variants():
    class First:
        provider_name = "first"
        def search(self, query, limit=5):
            return [{
                "url": "https://doi.org/10.1/a",
                "title": "Public Transit Access and Employment Outcomes",
            }]

    class Second:
        provider_name = "second"
        def search(self, query, limit=5):
            return [
                {
                    "url": "https://example.edu/working-paper",
                    "title": "Public Transit Access & Employment Outcomes",
                },
                {
                    "url": "https://doi.org/10.1/b",
                    "title": "A Distinct Mobility Experiment",
                },
            ]

    results = CompositeSearchProvider([First(), Second()]).search("transit", limit=5)
    assert [item["url"] for item in results] == [
        "https://doi.org/10.1/a", "https://doi.org/10.1/b"
    ]
