from __future__ import annotations

import json
from typing import Any

from .domain import PlannedProposition, ResearchPlan
from .states import ProjectStatus


LABOR_DIMENSIONS = (
    ("wages", "unionization changes wages and total compensation for represented and non-represented workers"),
    ("benefits", "unionization changes access to employer-provided benefits and workplace protections"),
    ("inequality", "higher union density changes income and wealth inequality in the United States"),
    ("employment", "unionization changes employment levels, hiring, and unemployment"),
    ("productivity", "unionization changes worker and firm productivity"),
    ("prices", "union-related labor costs materially affect consumer prices"),
    ("firm_survival", "unionization changes profitability, investment, relocation, and firm survival"),
    ("bargaining_power", "unionization changes workers' bargaining power and voice at work"),
)


class Planner:
    def __init__(self, repository: Any, ai=None):
        self.repository = repository
        self.ai = ai

    def create_plan(self, project_id: str) -> ResearchPlan:
        project = self.repository.project(project_id)
        if project.status not in {
            ProjectStatus.DRAFT,
            ProjectStatus.PLANNED,
        }:
            raise ValueError(
                "Create a new thesis version before replacing an approved research plan"
            )
        thesis = self.repository.current_thesis(project_id)
        propositions = (
            self._ai_plan(project_id, thesis.text)
            if self.ai
            else self._heuristic_plan(thesis.text)
        )
        plan = ResearchPlan(
            project_id=project_id,
            thesis=thesis.text,
            thesis_version=thesis.version,
            propositions=propositions,
        )
        self.repository.mark_planned(project_id)
        return plan

    def _heuristic_plan(self, thesis: str) -> list[PlannedProposition]:
        lower = thesis.lower()
        if "union" in lower or "collective bargaining" in lower:
            return [
                PlannedProposition(
                    key=key,
                    text=text.capitalize() + ".",
                    kind="empirical",
                    polarity="neutral",
                    scope={"geography": "United States"},
                    search_queries=[
                        f"{text} United States official data report",
                        f"{text} peer reviewed study DOI",
                        f"{text} strongest counter evidence costs tradeoffs",
                        f"{text} sector differences causal mechanism boundary conditions",
                    ],
                )
                for key, text in LABOR_DIMENSIONS
            ] + [
                PlannedProposition(
                    key="normative_priority",
                    text="Improving worker welfare, equality, and workplace voice should be prioritized when evaluating labor policy.",
                    kind="normative",
                    polarity="supports_thesis",
                    scope={"geography": "United States"},
                    search_queries=[],
                )
            ]
        return [
            PlannedProposition(
                key="outcomes",
                text=f"The measurable outcomes asserted by this thesis occur: {thesis}",
                search_queries=[f'"{thesis}" study data', f"{thesis} counter evidence"],
            ),
            PlannedProposition(
                key="mechanism",
                text="The principal causal mechanism asserted or implied by the thesis is supported by evidence.",
                search_queries=[f"{thesis} causal mechanism research"],
            ),
            PlannedProposition(
                key="tradeoffs",
                text="The thesis remains credible after accounting for material costs and unintended effects.",
                search_queries=[f"{thesis} costs unintended effects evidence"],
            ),
            PlannedProposition(
                key="normative_priority",
                text="The values implied by the thesis should be prioritized over competing values.",
                kind="normative",
                polarity="supports_thesis",
            ),
        ]

    def _ai_plan(self, project_id: str, thesis: str) -> list[PlannedProposition]:
        prompt = f"""Decompose the following US political-policy thesis into narrow propositions.
Separate empirical claims from normative premises. Include the strongest plausible opposing hypotheses.
For every empirical proposition, provide four distinct web searches: official data, original academic research,
strong counterevidence, and boundary conditions. Return JSON with a `propositions` array. Each item must contain:
key, text, kind (empirical|normative), polarity (supports_thesis|challenges_thesis|neutral),
scope with geography/population/timeframe values (nullable), and search_queries.

THESIS: {thesis}"""
        payload, usage = self.ai.json_completion(prompt, operation="plan")
        self.repository.record_run(
            project_id,
            "plan",
            provider=getattr(self.ai, "provider_name", "unknown"),
            model=self.ai.model,
            prompt_version="v1",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=usage.estimated_cost,
        )
        items = [PlannedProposition.from_dict(item) for item in payload["propositions"]]
        if not items:
            raise ValueError("Planner returned no propositions")
        return items
