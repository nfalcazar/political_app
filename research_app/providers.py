from __future__ import annotations

from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

import requests


_SEARCH_STOP_WORDS = {
    "about", "against", "analysis", "data", "effect", "effects", "evidence",
    "findings", "government", "official", "original", "primary", "public",
    "report", "research", "scholarly", "study", "using", "with",
}


def _informative_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 4 and token not in _SEARCH_STOP_WORDS
    }


def _scholarly_relevance(query: str, candidate_text: str) -> tuple[int, list[str]]:
    matched = sorted(_informative_terms(query) & _informative_terms(candidate_text))
    return len(matched), matched


def _title_fingerprint(value: str | None) -> str:
    return " ".join(sorted(_informative_terms(value or "")))


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
    ):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million

    def _usage(self, input_tokens: int = 0, output_tokens: int = 0) -> Usage:
        return Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=(
                input_tokens * self.input_cost_per_million
                + output_tokens * self.output_cost_per_million
            )
            / 1_000_000,
        )

    def json_completion(self, prompt: str, operation: str) -> tuple[dict, Usage]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a rigorous research analyst. Return valid JSON only and never invent citations.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        usage = response.usage
        return json.loads(content), self._usage(
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def embeddings(self, texts: list[str], model: str) -> tuple[list[list[float]], Usage]:
        response = self.client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data], self._usage(
            getattr(response.usage, "prompt_tokens", 0) or 0
        )


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        client=None,
        *,
        hard_max_tokens: int = 1024,
        batch_tokens: int = 16000,
        batch_items: int = 32,
    ):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
        self.client = client
        self.model = model
        from .content_policy import TokenCounter

        self.token_counter = TokenCounter(model)
        self.hard_max_tokens = hard_max_tokens
        self.batch_tokens = batch_tokens
        self.batch_items = batch_items

    def embeddings(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        if not texts:
            return [], Usage()
        counts = [self.token_counter.count(text) for text in texts]
        oversized = next(
            ((index, count) for index, count in enumerate(counts) if count > self.hard_max_tokens),
            None,
        )
        if oversized:
            index, count = oversized
            raise ValueError(
                f"Embedding input[{index}] has {count} tokens; hard maximum is "
                f"{self.hard_max_tokens}. Rechunk the source before embedding."
            )
        vectors: list[list[float]] = []
        total_tokens = 0
        offset = 0
        while offset < len(texts):
            end = offset
            token_total = 0
            while end < len(texts) and end - offset < self.batch_items:
                next_count = counts[end]
                if end > offset and token_total + next_count > self.batch_tokens:
                    break
                token_total += next_count
                end += 1
            response = self.client.embeddings.create(model=self.model, input=texts[offset:end])
            ordered = sorted(
                response.data,
                key=lambda item: getattr(item, "index", 0),
            )
            vectors.extend(item.embedding for item in ordered)
            usage = getattr(response, "usage", None)
            total_tokens += getattr(usage, "prompt_tokens", 0) or 0
            offset = end
        return vectors, Usage(input_tokens=total_tokens)


class DeepSeekProvider:
    """Schema-validated DeepSeek chat completions through its OpenAI-compatible API."""

    provider_name = "deepseek"
    supports_embeddings = False

    def __init__(
        self,
        api_key: str | None,
        model: str = "deepseek-v4-pro",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 300,
        max_attempts: int = 3,
        client=None,
        debug_dir: Path | None = None,
        debug_raw_responses: bool = True,
        thinking: bool = True,
        reasoning_effort: str = "high",
    ):
        self.api_key_configured = bool(api_key)
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.debug_raw_responses = debug_raw_responses
        self.debug_context = "unassigned"
        self.last_diagnostic: dict[str, Any] | None = None
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        if not api_key:
            self.client = None
            self.model = model
            self.base_url = base_url.rstrip("/")
            self.max_attempts = max(1, max_attempts)
            self.schema_dir = Path(__file__).with_name("schemas")
            return
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ValueError(
                    "DeepSeek support is not installed; run `uv sync`"
                ) from exc
            # The provider owns retries and its wall-clock deadline. Disable the
            # SDK's hidden retry layer so one request cannot consume the timeout
            # several times over.
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
            )
        self.client = client
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max(1, max_attempts)
        self.schema_dir = Path(__file__).with_name("schemas")

    def set_debug_context(self, context: str) -> None:
        self.debug_context = context

    def _write_diagnostic(self, diagnostic: dict[str, Any]) -> None:
        self.last_diagnostic = diagnostic
        if self.debug_dir is None:
            return
        directory = self.debug_dir / "deepseek" / self.debug_context
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        prompt_hash = diagnostic.get("prompt_hash", "unknown")[:12]
        path = directory / f"{stamp}-{diagnostic.get('operation', 'call')}-{prompt_hash}-{diagnostic.get('attempt', 1)}.json"
        diagnostic["artifact_path"] = str(path)
        path.write_text(json.dumps(diagnostic, indent=2, default=str), encoding="utf-8")

    def json_completion(self, prompt: str, operation: str) -> tuple[dict, Usage]:
        if self.client is None:
            raise ValueError(
                "DeepSeek reasoning requires DEEPSEEK_API_KEY in political_app/.env "
                "or the shell environment"
            )
        schema_path = self.schema_dir / f"{operation}.json"
        if not schema_path.exists():
            raise ValueError(f"No structured output schema for operation: {operation}")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            from jsonschema import Draft202012Validator
        except ImportError as exc:
            raise ValueError(
                "DeepSeek schema validation is not installed; run `uv sync`"
            ) from exc
        validator = Draft202012Validator(schema)
        last_error = "no response"
        deadline = time.monotonic() + self.timeout
        for attempt in range(1, self.max_attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            started = time.monotonic()
            diagnostic = {
                "provider": self.provider_name,
                "model": self.model,
                "thinking": self.thinking,
                "reasoning_effort": self.reasoning_effort,
                "operation": operation,
                "attempt": attempt,
                "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
                "prompt": prompt if self.debug_raw_responses else None,
            }
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a rigorous political-policy research analyst. "
                                "Return one valid JSON object only. Never invent citations. "
                                f"The JSON must conform to this schema: {json.dumps(schema)}"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    reasoning_effort=self.reasoning_effort,
                    extra_body={
                        "thinking": {
                            "type": "enabled" if self.thinking else "disabled"
                        }
                    },
                    timeout=max(1, remaining),
                )
                content = response.choices[0].message.content
                reasoning_content = getattr(
                    response.choices[0].message, "reasoning_content", None
                )
                diagnostic.update({
                    "response": content if self.debug_raw_responses else None,
                    "reasoning_content": reasoning_content if self.debug_raw_responses else None,
                    "finish_reason": getattr(response.choices[0], "finish_reason", None),
                    "response_hash": hashlib.sha256((content or "").encode()).hexdigest(),
                })
                if not content or not content.strip():
                    raise ValueError("empty JSON response")
                payload = json.loads(content)
                errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
                if errors:
                    raise ValueError(f"schema validation failed: {errors[0].message}")
                usage = getattr(response, "usage", None)
                diagnostic.update({
                    "status": "success",
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                })
                self._write_diagnostic(diagnostic)
                return payload, Usage(
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            except Exception as exc:
                # Error text may contain SDK details, but never the prompt, response, or key.
                last_error = f"{type(exc).__name__}: {exc}"
                diagnostic.update({
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                })
                self._write_diagnostic(diagnostic)
                if attempt < self.max_attempts:
                    time.sleep(min(0.25 * attempt, 0.5))
        raise RuntimeError(
            f"DeepSeek {operation} failed after {self.max_attempts} attempts: {last_error}"
        )

    def connectivity_status(self) -> dict[str, Any]:
        if self.client is None:
            return {"ok": False, "message": "DEEPSEEK_API_KEY is not configured"}
        try:
            self.client.models.list()
            return {"ok": True, "message": "DeepSeek API is reachable"}
        except Exception as exc:
            return {
                "ok": False,
                "message": f"DeepSeek API check failed: {type(exc).__name__}: {exc}",
            }


class GoogleSearchProvider:
    def __init__(self, api_key: str, engine_id: str):
        self.api_key = api_key
        self.engine_id = engine_id

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": self.api_key,
                "cx": self.engine_id,
                "q": query,
                "num": min(limit, 10),
            },
            timeout=20,
        )
        response.raise_for_status()
        return [
            {
                "url": item["link"],
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "display_link": item.get("displayLink"),
            }
            for item in response.json().get("items", [])
            if item.get("link")
        ]


class CodexCliProvider:
    """Structured model access through the user's existing Codex CLI login."""

    supports_embeddings = False
    provider_name = "codex"

    def __init__(
        self,
        runtime_dir: Path,
        timeout: int = 300,
        executable: str = "codex",
    ):
        resolved = shutil.which(executable)
        if not resolved:
            raise ValueError(f"Codex executable not found: {executable}")
        self.executable = resolved
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.model = "codex-account-default"
        self.schema_dir = Path(__file__).with_name("schemas")

    @staticmethod
    def _safe_environment() -> dict[str, str]:
        allowed = {
            "PATH",
            "HOME",
            "CODEX_HOME",
            "TMPDIR",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "no_proxy",
        }
        return {key: value for key, value in os.environ.items() if key in allowed}

    def login_status(self) -> dict[str, Any]:
        result = subprocess.run(
            [self.executable, "login", "status"],
            text=True,
            capture_output=True,
            timeout=30,
            env=self._safe_environment(),
        )
        return {
            "ok": result.returncode == 0,
            "message": (result.stdout or result.stderr).strip(),
        }

    def json_completion(
        self, prompt: str, operation: str, web_search: bool = False
    ) -> tuple[dict, Usage]:
        schema_path = self.schema_dir / f"{operation}.json"
        if not schema_path.exists():
            raise ValueError(f"No structured output schema for operation: {operation}")
        status = self.login_status()
        if not status["ok"]:
            raise ValueError(f"Codex is not authenticated: {status['message']}")
        with tempfile.TemporaryDirectory(dir=self.runtime_dir) as tmp:
            output_path = Path(tmp) / "result.json"
            command = [self.executable]
            if web_search:
                command.append("--search")
            command.extend(
                [
                    "--ask-for-approval",
                    "never",
                    "exec",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                    "--cd",
                    tmp,
                    "-",
                ]
            )
            try:
                result = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout,
                    env=self._safe_environment(),
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(
                    f"Codex {operation} exceeded {self.timeout} seconds"
                ) from exc
            if result.returncode != 0:
                message = (result.stderr or result.stdout).strip()
                raise RuntimeError(f"Codex {operation} failed: {message[-2000:]}")
            if not output_path.exists():
                raise RuntimeError(f"Codex {operation} returned no structured result")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Codex {operation} returned invalid JSON") from exc
            return payload, Usage()


class CodexWebSearchProvider:
    provider_name = "codex"

    def __init__(self, codex: CodexCliProvider):
        self.codex = codex

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        prompt = f"""Use live web search to discover evidence relevant to this political-policy research query:

{query}

Use `query` as query_key for every candidate. Seek both supporting and challenging material. Prefer original research, official datasets,
legislation, court records, and official reports. Secondary sources are useful only when they
lead to a primary source. Return no more than {min(limit, 8)} candidates. A primary-source label
is a hypothesis for the application to verify by fetching the URL; do not invent URLs or citations."""
        payload, _ = self.codex.json_completion(
            prompt, operation="web_search", web_search=True
        )
        return [
            {
                "url": item["url"],
                "title": item.get("title"),
                "snippet": item.get("reason"),
                "display_link": item.get("publisher"),
                "stance_hint": item.get("stance", "unknown"),
                "claimed_primary": item.get("claimed_primary", False),
                "query_key": item.get("query_key", "query"),
            }
            for item in payload.get("candidates", [])[:limit]
        ]

    def search_batch(self, requests_: list[dict], limit_per_query: int = 4) -> list[dict]:
        prompt = f"""Use live web search to research this batch of political-policy propositions:

{json.dumps(requests_, indent=2)}

For each proposition, use its official/original-research and adversarial query families. Seek direct
primary sources and preserve credible conflicting evidence. Return no more than {limit_per_query}
candidates per proposition. Set each candidate's query_key to the matching proposition_id exactly.
Secondary pages are discovery leads only. Do not invent URLs, citations, or source classifications."""
        payload, _ = self.codex.json_completion(
            prompt, operation="web_search", web_search=True
        )
        allowed = {item["proposition_id"] for item in requests_}
        results = []
        for item in payload.get("candidates", []):
            if item.get("query_key") not in allowed:
                continue
            results.append(
                {
                    "url": item["url"],
                    "title": item.get("title"),
                    "snippet": item.get("reason"),
                    "display_link": item.get("publisher"),
                    "stance_hint": item.get("stance", "unknown"),
                    "claimed_primary": item.get("claimed_primary", False),
                    "query_key": item["query_key"],
                }
            )
        return results


class CrossrefSearchProvider:
    """No-key scholarly DOI discovery. Results remain candidates until retrieved."""

    provider_name = "crossref"

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        response = requests.get(
            "https://api.crossref.org/works",
            params={"query": query, "rows": min(max(limit * 3, limit), 20)},
            headers={"User-Agent": "PoliticalResearch/0.2 (personal research tool)"},
            timeout=20,
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("message", {}).get("items", []):
            doi = item.get("DOI")
            url = f"https://doi.org/{doi}" if doi else item.get("URL")
            if not url:
                continue
            titles = item.get("title") or []
            title = titles[0] if titles else None
            candidate_text = " ".join(
                [
                    title or "",
                    " ".join(item.get("subtitle") or []),
                    " ".join(item.get("subject") or []),
                    str(item.get("abstract") or ""),
                ]
            )
            relevance_score, matched_terms = _scholarly_relevance(query, candidate_text)
            if relevance_score == 0:
                continue
            results.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": "Crossref scholarly metadata match",
                    "display_link": item.get("publisher"),
                    "claimed_primary": item.get("type") in {
                        "journal-article", "posted-content", "proceedings-article",
                        "report", "report-series", "dataset",
                    },
                    "relevance_score": relevance_score,
                    "matched_terms": matched_terms,
                }
            )
        return sorted(results, key=lambda item: -item["relevance_score"])[:limit]


class OpenAlexSearchProvider:
    """No-key scholarly discovery from OpenAlex metadata."""

    provider_name = "openalex"

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        response = requests.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": min(max(limit * 3, limit), 25)},
            headers={"User-Agent": "PoliticalResearch/0.2 (personal research tool)"},
            timeout=20,
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("results", []):
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            doi = item.get("doi")
            url = doi or primary_location.get("landing_page_url") or item.get("id")
            if not url:
                continue
            title = item.get("display_name") or item.get("title")
            labels = []
            for field in ("keywords", "topics", "concepts"):
                labels.extend(
                    str(value.get("display_name") or value.get("keyword") or "")
                    for value in (item.get(field) or [])
                    if isinstance(value, dict)
                )
            abstract_terms = " ".join((item.get("abstract_inverted_index") or {}).keys())
            candidate_text = " ".join([title or "", *labels, abstract_terms])
            relevance_score, matched_terms = _scholarly_relevance(query, candidate_text)
            if relevance_score == 0:
                continue
            results.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": (
                        "OpenAlex scholarly metadata match"
                        + (f" ({item['publication_year']})" if item.get("publication_year") else "")
                    ),
                    "display_link": source.get("display_name"),
                    "claimed_primary": item.get("type") in {
                        "article", "dataset", "preprint", "report",
                    },
                    "relevance_score": relevance_score,
                    "matched_terms": matched_terms,
                }
            )
        return sorted(results, key=lambda item: -item["relevance_score"])[:limit]


class CompositeSearchProvider:
    def __init__(self, providers: list, provider_name: str | None = None):
        self.providers = providers
        self.provider_name = provider_name or "+".join(
            getattr(provider, "provider_name", provider.__class__.__name__.lower())
            for provider in providers
        )
        codex = next(
            (provider.codex for provider in providers if isinstance(provider, CodexWebSearchProvider)),
            None,
        )
        self.model = getattr(codex, "model", None)

    @staticmethod
    def _dedupe_key(url: str) -> str:
        value = url.strip().rstrip("/")
        if "doi.org/" in value.lower():
            return "doi:" + value.lower().split("doi.org/", 1)[1]
        return value.lower()

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        provider_results, errors = [], []
        for provider in self.providers:
            try:
                provider_results.append(provider.search(query, limit=limit))
            except Exception as exc:
                errors.append(str(exc))
        results, seen, seen_titles = [], set(), set()
        for index in range(max((len(items) for items in provider_results), default=0)):
            for candidates in provider_results:
                if index >= len(candidates):
                    continue
                item = candidates[index]
                url = item.get("url")
                key = self._dedupe_key(url) if url else None
                title_key = _title_fingerprint(item.get("title"))
                if not url or key in seen or (title_key and title_key in seen_titles):
                    continue
                seen.add(key)
                if title_key:
                    seen_titles.add(title_key)
                results.append(item)
                if len(results) >= limit:
                    return results
        if not results and errors:
            raise RuntimeError("; ".join(errors))
        return results

    def search_batch(self, requests_: list[dict], limit_per_query: int = 4) -> list[dict]:
        results = []
        batch_provider = next(
            (provider for provider in self.providers if hasattr(provider, "search_batch")),
            None,
        )
        if batch_provider is not None:
            results.extend(batch_provider.search_batch(requests_, limit_per_query))
        # Scholarly metadata adds one DOI candidate per proposition without extra model calls.
        for request_ in requests_:
            for provider in self.providers:
                if hasattr(provider, "search_batch"):
                    continue
                try:
                    candidates = provider.search(request_["queries"][0], limit=1)
                except Exception:
                    continue
                for item in candidates:
                    item = dict(item)
                    item["query_key"] = request_["proposition_id"]
                    results.append(item)
        deduped, seen = [], set()
        for item in results:
            url = item.get("url")
            key = (
                item.get("query_key"),
                self._dedupe_key(url) if url else None,
            )
            if not item.get("url") or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped


class EmptySearchProvider:
    """Explicit manual-only mode."""

    provider_name = "none"
    model = None

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return []

    def search_batch(self, requests_: list[dict], limit_per_query: int = 4) -> list[dict]:
        return []
