from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any


VALID_KINDS = {"empirical", "normative"}
VALID_POLARITIES = {"supports_thesis", "challenges_thesis", "neutral"}
VALID_RELATIONSHIPS = {"supports", "challenges", "mixed"}


@dataclass
class PlannedProposition:
    key: str
    text: str
    kind: str = "empirical"
    polarity: str = "neutral"
    scope: dict[str, Any] = field(default_factory=dict)
    search_queries: list[str] = field(default_factory=list)
    origin: str = "planned"
    review_status: str = "reviewed"
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PlannedProposition":
        required = {"key", "text"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"Proposition is missing: {', '.join(sorted(missing))}")
        item = cls(
            key=str(value["key"]).strip(),
            text=str(value["text"]).strip(),
            kind=str(value.get("kind", "empirical")),
            polarity=str(value.get("polarity", "neutral")),
            scope=dict(value.get("scope", {})),
            search_queries=[str(query).strip() for query in value.get("search_queries", [])],
            origin=str(value.get("origin", "planned")),
            review_status=str(value.get("review_status", "reviewed")),
            provenance=dict(value.get("provenance", {})),
        )
        if not item.key or not item.text:
            raise ValueError("Proposition key and text cannot be empty")
        if item.kind not in VALID_KINDS:
            raise ValueError(f"Invalid proposition kind: {item.kind}")
        if item.polarity not in VALID_POLARITIES:
            raise ValueError(f"Invalid proposition polarity: {item.polarity}")
        return item


@dataclass
class ResearchPlan:
    project_id: str
    thesis: str
    thesis_version: int
    propositions: list[PlannedProposition]
    approval_required: bool = True
    max_source_attempts: int = 20
    max_runtime_seconds: int = 900

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "thesis": self.thesis,
            "thesis_version": self.thesis_version,
            "approval_required": self.approval_required,
            "limits": {
                "max_source_attempts": self.max_source_attempts,
                "max_runtime_seconds": self.max_runtime_seconds,
            },
            "propositions": [asdict(item) for item in self.propositions],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.to_dict(), handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @classmethod
    def read(cls, path: Path) -> "ResearchPlan":
        value = json.loads(path.read_text(encoding="utf-8"))
        propositions = [
            PlannedProposition.from_dict(item) for item in value.get("propositions", [])
        ]
        if not propositions:
            raise ValueError("A research plan must include at least one proposition")
        keys = [item.key for item in propositions]
        if len(keys) != len(set(keys)):
            raise ValueError("Proposition keys must be unique")
        return cls(
            project_id=str(value["project_id"]),
            thesis=str(value["thesis"]),
            thesis_version=int(value["thesis_version"]),
            propositions=propositions,
            approval_required=bool(value.get("approval_required", True)),
            max_source_attempts=int(value.get("limits", {}).get("max_source_attempts", 20)),
            max_runtime_seconds=int(value.get("limits", {}).get("max_runtime_seconds", 900)),
        )


@dataclass
class EvidenceDraft:
    finding: str
    excerpt: str
    locator: str
    relationship: str
    explanation: str
    population: str | None = None
    geography: str | None = None
    timeframe: str | None = None
    methodology: str | None = None
    confidence: str = "medium"

    def validate(self) -> None:
        if self.relationship not in VALID_RELATIONSHIPS:
            raise ValueError(f"Invalid evidence relationship: {self.relationship}")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValueError(f"Invalid confidence: {self.confidence}")
        if not all((self.finding.strip(), self.excerpt.strip(), self.locator.strip())):
            raise ValueError("Finding, excerpt, and locator are required")
