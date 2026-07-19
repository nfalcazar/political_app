from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


class DossierRenderer:
    def __init__(self, repository: Any):
        self.repository = repository

    def render(self, project_id: str, path: Path) -> Path:
        status = self.repository.status(project_id)
        propositions = self.repository.propositions(project_id)
        rows = self.repository.project_evidence(project_id)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["proposition"].id].append(row)
        synthesis = self.repository.synthesis(project_id) if hasattr(self.repository, "synthesis") else {}
        assessment = synthesis.get("assessment", {})
        findings_abstract = (
            assessment.get("summary")
            or synthesis.get("abstract")
            or "No synthesized findings are available yet."
        )

        lines = [
            f"# {status['title']}",
            "",
            "## Thesis",
            "",
            status["thesis"],
            "",
            "## Findings abstract",
            "",
            findings_abstract,
            "",
            "## Research status",
            "",
            f"- Project status: `{status['status']}`",
            f"- Proposition coverage: {status['covered_propositions']}/{status['propositions']}",
            f"- Stored evidence relationships: {sum(status['evidence'].values())}",
            f"- Model calls recorded: {status.get('model_calls', 'not available')}",
            f"- Evidence items accepted/received: {status.get('evidence_items_accepted', 0)}/{status.get('evidence_items_received', 0)}",
            f"- Post-processing failures: {status.get('postprocess_failures', 0)}",
            f"- Provider-reported tokens: {status['input_tokens']} input / {status['output_tokens']} output",
            "",
            "## Assessment",
            "",
            (
                f"**{assessment.get('label', 'unclassified').replace('_', ' ').title()}:** "
                f"{assessment.get('rationale')}"
                if assessment.get("rationale")
                else "This dossier reports the currently stored evidence without changing the thesis. "
                "Missing coverage and conflicting findings are retained explicitly."
            ),
            "",
        ]
        for proposition in propositions:
            label = " — source-discovered, unreviewed" if getattr(proposition, "origin", "planned") == "source_discovered" else ""
            lines.extend([f"## {proposition.plan_key}: {proposition.text}{label}", ""])
            if proposition.kind == "normative":
                lines.extend(
                    [
                        "This is a normative premise. Empirical evidence may inform its consequences but cannot establish the value judgment itself.",
                        "",
                    ]
                )
                continue
            evidence_rows = grouped.get(proposition.id, [])
            if not evidence_rows:
                if status.get("postprocess_failures", 0):
                    lines.extend([
                        "**Evidence processing failure:** model responses were received, but evidence items did not pass local source verification. See `research errors` and the debug artifacts under the configured debug directory.",
                        "",
                    ])
                else:
                    lines.extend(["**Evidence gap:** no primary-source evidence is stored yet.", ""])
                continue
            for relationship in ("supports", "challenges", "mixed"):
                related = [row for row in evidence_rows if row["link"].relationship == relationship]
                if not related:
                    continue
                lines.extend([f"### {relationship.title()}", ""])
                for row in related:
                    evidence, source, link = row["evidence"], row["source"], row["link"]
                    lines.extend(
                        [
                            f"- **{evidence.finding}** ([evidence `{evidence.id}`]({source.canonical_url}))",
                            f"  - Why it matters: {link.explanation}",
                            f"  - Source locator: {evidence.locator}; confidence: {evidence.confidence}",
                            f"  - Provenance: [{source.title or source.canonical_url}]({source.canonical_url}); "
                            f"publisher: {source.publisher or 'unknown'}; published: {source.publication_date or 'unknown'}; "
                            f"accessed: {getattr(evidence, 'source_accessed_at', None) or source.retrieved_at or 'unknown'}",
                            f"  - Source excerpt: “{evidence.excerpt}”",
                        ]
                    )
                lines.append("")

        sources = {row["source"].id: row["source"] for row in rows}
        lines.extend(["## Primary-source bibliography", ""])
        if not sources:
            lines.extend(["No evidentiary primary sources have been attached yet.", ""])
        else:
            for source in sorted(sources.values(), key=lambda item: item.title or item.canonical_url):
                lines.append(
                    f"- [{source.title or source.canonical_url}]({source.canonical_url}) — "
                    f"{source.publisher or source.source_type}; rights: "
                    f"`{getattr(source, 'rights_status', 'unknown')}`"
                )
            lines.append("")
        lines.extend(
            [
                "## Method note",
                "",
                "Secondary reporting and advocacy material may be retained as discovery provenance, "
                "but only evidence linked to a retrieved primary source appears above. Full text from "
                "copyrighted or unknown-rights sources is used only as a temporary processing cache; "
                "the dossier retains concise verified quotations, summaries, locators, and source links.",
                "",
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
