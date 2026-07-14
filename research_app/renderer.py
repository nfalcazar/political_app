from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .repository import Repository


class DossierRenderer:
    def __init__(self, repository: Repository):
        self.repository = repository

    def render(self, project_id: str, path: Path) -> Path:
        status = self.repository.status(project_id)
        propositions = self.repository.propositions(project_id)
        rows = self.repository.project_evidence(project_id)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["proposition"].id].append(row)

        lines = [
            f"# {status['title']}",
            "",
            "## Thesis",
            "",
            status["thesis"],
            "",
            "## Research status",
            "",
            f"- Project status: `{status['status']}`",
            f"- Proposition coverage: {status['covered_propositions']}/{status['propositions']}",
            f"- Stored evidence relationships: {sum(status['evidence'].values())}",
            f"- Model tokens recorded: {status['input_tokens']} input / {status['output_tokens']} output",
            "",
            "## Assessment",
            "",
            "This dossier reports the currently stored evidence without changing the thesis. "
            "Missing coverage and conflicting findings are retained explicitly.",
            "",
        ]
        for proposition in propositions:
            lines.extend([f"## {proposition.plan_key}: {proposition.text}", ""])
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
                    f"- [{source.title or source.canonical_url}]({source.canonical_url}) — {source.publisher or source.source_type}"
                )
            lines.append("")
        lines.extend(
            [
                "## Method note",
                "",
                "Secondary reporting and advocacy material may be retained as discovery provenance, "
                "but only evidence linked to a retrieved primary source appears above.",
                "",
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

