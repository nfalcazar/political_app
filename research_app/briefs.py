from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit


ASSESSMENT_LABELS = {
    "leans_supporting",
    "leans_challenging",
    "mixed",
    "insufficient_evidence",
}
STANCES = {"supports", "challenges", "mixed"}
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def validate_synthesis(payload: dict, rows: list[dict]) -> dict:
    """Validate model references and stance relationships against accepted evidence."""
    if payload.get("schema_version") != 2:
        raise ValueError("Structured synthesis must use schema version 2")
    assessment = payload.get("assessment")
    if not isinstance(assessment, dict) or assessment.get("label") not in ASSESSMENT_LABELS:
        raise ValueError("Structured synthesis has an invalid assessment")
    known_ids = {row["evidence"].id for row in rows}
    relationships: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        relationships[row["evidence"].id].add(row["link"].relationship)

    def validate_ids(values, *, required: bool) -> list[str]:
        if not isinstance(values, list) or (required and not values):
            raise ValueError("Structured synthesis is missing evidence citations")
        ids = [str(value) for value in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Structured synthesis repeats an evidence citation")
        unknown = set(ids) - known_ids
        if unknown:
            raise ValueError(
                f"Structured synthesis cites unknown evidence: {', '.join(sorted(unknown))}"
            )
        return ids

    assessment_ids = validate_ids(
        assessment.get("evidence_ids", []),
        required=assessment["label"] != "insufficient_evidence",
    )
    assessment_relationships = {
        relationship
        for evidence_id in assessment_ids
        for relationship in relationships[evidence_id]
    }
    if (
        assessment["label"] == "leans_supporting"
        and "supports" not in assessment_relationships
    ):
        raise ValueError("Supporting assessment does not cite supporting evidence")
    if (
        assessment["label"] == "leans_challenging"
        and "challenges" not in assessment_relationships
    ):
        raise ValueError("Challenging assessment does not cite challenging evidence")
    if assessment["label"] == "mixed" and not (
        "mixed" in assessment_relationships
        or {"supports", "challenges"}.issubset(assessment_relationships)
    ):
        raise ValueError("Mixed assessment does not cite conflicting or mixed evidence")
    arguments = payload.get("arguments")
    if not isinstance(arguments, list):
        raise ValueError("Structured synthesis arguments must be a list")
    for argument in arguments:
        if not isinstance(argument, dict) or argument.get("stance") not in STANCES:
            raise ValueError("Structured synthesis has an invalid argument stance")
        evidence_ids = validate_ids(argument.get("evidence_ids"), required=True)
        stance = argument["stance"]
        if not any(stance in relationships[evidence_id] for evidence_id in evidence_ids):
            raise ValueError(
                f"The {stance} argument is not linked to matching accepted evidence"
            )
    return payload


def _safe_external_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    return value


def _source_score(rows: list[dict]) -> tuple[int, int, int, int]:
    propositions = {row["proposition"].id for row in rows}
    findings = {row["evidence"].finding.strip().casefold() for row in rows}
    confidence = sum(
        CONFIDENCE_WEIGHT.get(row["evidence"].confidence, 0) for row in rows
    )
    scope = sum(
        bool(getattr(row["evidence"], field, None))
        for row in rows
        for field in ("population", "geography", "timeframe", "methodology")
    )
    return len(propositions), confidence, scope, len(findings)


def select_key_sources(rows: list[dict], limit: int = 5) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["source"].id].append(row)

    candidates = sorted(
        grouped.values(),
        key=lambda source_rows: (
            tuple(-value for value in _source_score(source_rows)),
            source_rows[0]["source"].canonical_url,
        ),
    )
    selected: list[list[dict]] = []
    for stance in ("supports", "challenges"):
        match = next(
            (
                source_rows
                for source_rows in candidates
                if any(row["link"].relationship == stance for row in source_rows)
                and source_rows not in selected
            ),
            None,
        )
        if match is not None:
            selected.append(match)
    for source_rows in candidates:
        if source_rows not in selected:
            selected.append(source_rows)
        if len(selected) >= limit:
            break

    cards = []
    for source_rows in selected[:limit]:
        source = source_rows[0]["source"]
        relationships = sorted({row["link"].relationship for row in source_rows})
        propositions = sorted({row["proposition"].text for row in source_rows})
        relationship_text = ", ".join(relationships)
        coverage_text = (
            f"It contributes accepted {relationship_text} evidence across "
            f"{len(propositions)} research {'claim' if len(propositions) == 1 else 'claims'}."
        )
        seen_evidence = set()
        evidence_items = []
        for row in source_rows:
            evidence = row["evidence"]
            if evidence.id in seen_evidence:
                continue
            seen_evidence.add(evidence.id)
            evidence_items.append(
                {
                    "evidence_id": evidence.id,
                    "finding": evidence.finding,
                    "excerpt": evidence.excerpt,
                    "locator": evidence.locator,
                    "confidence": evidence.confidence,
                    "relationship": row["link"].relationship,
                    "proposition": row["proposition"].text,
                }
            )
        cards.append(
            {
                "source_id": source.id,
                "title": source.title or source.canonical_url,
                "publisher": source.publisher,
                "url": _safe_external_url(source.canonical_url),
                "publication_date": source.publication_date,
                "source_type": source.source_type,
                "relationships": relationships,
                "why_selected": coverage_text,
                "evidence": evidence_items,
            }
        )
    return cards


def _fallback_assessment(rows: list[dict], covered: int, empirical: int) -> dict:
    if not rows or covered == 0:
        summary = "There is not enough accepted primary-source evidence to assess this claim."
        rationale = "No empirical research claim currently has accepted evidence."
    else:
        summary = "Accepted evidence exists, but a validated overall assessment is unavailable."
        rationale = (
            "The evidence remains visible below, but the structured synthesis was not "
            "available or did not pass citation validation."
        )
    return {
        "label": "insufficient_evidence",
        "summary": summary,
        "rationale": rationale,
        "evidence_ids": [],
    }


def build_brief(repository, project_id: str) -> dict:
    status = repository.status(project_id)
    propositions = repository.propositions(project_id)
    rows = repository.project_evidence(project_id)
    empirical = [item for item in propositions if item.kind == "empirical"]
    covered_ids = {row["proposition"].id for row in rows}
    synthesis = repository.synthesis(project_id)
    structured = synthesis if synthesis.get("schema_version") == 2 else None
    if structured is not None:
        try:
            validate_synthesis(structured, rows)
        except ValueError:
            structured = None
    assessment = (
        structured["assessment"]
        if structured is not None
        else _fallback_assessment(rows, len(covered_ids), len(empirical))
    )
    gaps = (
        list(structured.get("uncertainty_and_gaps", []))
        if structured is not None
        else [
            f"{item.text}"
            for item in empirical
            if item.id not in covered_ids
        ]
    )
    return {
        "project_id": project_id,
        "claim": status["thesis"],
        "assessment": assessment,
        "arguments": list(structured.get("arguments", [])) if structured else [],
        "uncertainty_and_gaps": gaps,
        "coverage": {
            "covered": len(covered_ids),
            "total": len(empirical),
        },
        "sources": select_key_sources(rows),
        "scope": [
            {
                "id": item.id,
                "key": item.plan_key,
                "text": item.text,
                "kind": item.kind,
                "scope": item.scope,
                "origin": item.origin,
            }
            for item in propositions
        ],
    }
