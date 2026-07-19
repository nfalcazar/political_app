from __future__ import annotations

import re
from typing import Iterable

from .entities import QueryNodeRecord, new_id


QUERY_KINDS = {
    "direct_primary",
    "official_record",
    "scholarly",
    "counterevidence",
    "mechanism",
    "historical_context",
    "citation_chase",
    "alternate_copy",
    "retrieval_recovery",
    "evidence_gap",
    "emergent_proposition",
}

RECOVERY_KINDS = {"alternate_copy", "retrieval_recovery"}
MAX_QUERY_DEPTH = 3


def normalize_query(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def seed_queries(proposition) -> Iterable[dict]:
    text = proposition.text.strip()
    supplied = [query.strip() for query in proposition.search_queries if query.strip()]
    # Planner queries are intentionally ordered by search purpose.  Preserve
    # each one instead of using only the first query and replacing the rest
    # with long, generic proposition strings.
    direct = f'"{text}" primary source'
    official = supplied[0] if supplied else f"{text} official government report data"
    scholarly = supplied[1] if len(supplied) > 1 else f"{text} peer reviewed original research"
    counter = supplied[2] if len(supplied) > 2 else f"{text} contrary findings counterevidence"
    mechanism = supplied[3] if len(supplied) > 3 else f"{text} mechanism boundary conditions"
    yield {
        "query": direct,
        "query_kind": "direct_primary",
        "target_stance": "unknown",
        "target_source_class": "primary",
        "priority": 8.0,
    }
    yield {
        "query": official,
        "query_kind": "official_record",
        "target_stance": "unknown",
        "target_source_class": "official",
        "priority": 9.0,
    }
    yield {
        "query": scholarly,
        "query_kind": "scholarly",
        "target_stance": "unknown",
        "target_source_class": "scholarly",
        "priority": 7.0,
    }
    yield {
        "query": counter,
        "query_kind": "counterevidence",
        "target_stance": "challenges",
        "target_source_class": "primary",
        "priority": 8.5,
    }
    yield {
        "query": mechanism,
        "query_kind": "mechanism",
        "target_stance": "mixed",
        "target_source_class": "primary",
        "priority": 6.0,
    }


def make_node(project_id: str, value: dict) -> QueryNodeRecord:
    kind = str(value.get("query_kind", "evidence_gap"))
    if kind not in QUERY_KINDS:
        raise ValueError(f"Invalid query kind: {kind}")
    query = str(value.get("query", "")).strip()
    if len(query) < 8 or len(query) > 800:
        raise ValueError("Query text must contain 8 to 800 characters")
    depth = int(value.get("depth", 0))
    if depth < 0 or depth > MAX_QUERY_DEPTH:
        raise ValueError(f"Query depth must be between 0 and {MAX_QUERY_DEPTH}")
    return QueryNodeRecord(
        id=str(value.get("id") or new_id()),
        project_id=project_id,
        query=query,
        query_kind=kind,
        proposition_ids=[str(item) for item in value.get("proposition_ids", [])],
        target_stance=str(value.get("target_stance", "unknown")),
        target_source_class=str(value.get("target_source_class", "primary")),
        parent_id=value.get("parent_id"),
        expansion_reason=str(value.get("expansion_reason", "seed")),
        depth=depth,
        priority=float(value.get("priority", 0.0)),
        provider=value.get("provider"),
    )
