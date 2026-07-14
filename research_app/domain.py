from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "thesis": self.thesis,
            "thesis_version": self.thesis_version,
            "approval_required": self.approval_required,
            "propositions": [asdict(item) for item in self.propositions],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

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

