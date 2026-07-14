from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import Settings
from .database import Database
from .domain import EvidenceDraft, ResearchPlan
from .models import ProjectStatus
from .planner import Planner
from .providers import GoogleSearchProvider, OpenAIProvider
from .renderer import DossierRenderer
from .repository import Repository
from .researcher import ResearchEngine
from .sources import SourceRetriever, infer_source_type, looks_primary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Build primary-source-grounded political research dossiers.",
    )
    parser.add_argument("--database-url", help="Override RESEARCH_DATABASE_URL")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Create a research project")
    new.add_argument("thesis")
    new.add_argument("--title")

    plan = sub.add_parser("plan", help="Generate an editable research plan")
    plan.add_argument("project_id")
    plan.add_argument("--output", type=Path)
    plan.add_argument("--heuristic", action="store_true", help="Do not call a model")

    approve = sub.add_parser("approve", help="Approve an edited plan")
    approve.add_argument("project_id")
    approve.add_argument("plan_file", type=Path)

    run = sub.add_parser("run", help="Run or resume approved research")
    run.add_argument("project_id")

    status = sub.add_parser("status", help="Show project coverage and usage")
    status.add_argument("project_id")

    pause = sub.add_parser("pause", help="Request a checkpointed pause")
    pause.add_argument("project_id")

    revise = sub.add_parser("revise", help="Create a new thesis version")
    revise.add_argument("project_id")
    revise.add_argument("thesis")
    revise.add_argument("--reason")

    continue_parser = sub.add_parser(
        "continue", help="Acknowledge the evidence checkpoint and research further"
    )
    continue_parser.add_argument("project_id")

    render = sub.add_parser("render", help="Render a dossier from stored evidence")
    render.add_argument("project_id")
    render.add_argument("--output", type=Path)

    source = sub.add_parser("source", help="Manage research sources")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_add = source_sub.add_parser("add", help="Add a candidate or primary source")
    source_add.add_argument("url")
    source_add.add_argument("--title")
    source_add.add_argument("--publisher")
    source_add.add_argument("--type", dest="source_type")
    source_add.add_argument("--primary", action="store_true")
    source_fetch = source_sub.add_parser("fetch", help="Download and chunk a source")
    source_fetch.add_argument("source_id")
    source_sub.add_parser("list", help="List stored sources")

    evidence = sub.add_parser("evidence", help="Attach manually reviewed evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_add = evidence_sub.add_parser("add")
    evidence_add.add_argument("project_id")
    evidence_add.add_argument("proposition_key")
    evidence_add.add_argument("source_id")
    evidence_add.add_argument("chunk_id")
    evidence_add.add_argument("--finding", required=True)
    evidence_add.add_argument("--excerpt", required=True)
    evidence_add.add_argument("--locator", required=True)
    evidence_add.add_argument(
        "--relationship", required=True, choices=("supports", "challenges", "mixed")
    )
    evidence_add.add_argument("--explanation", required=True)
    evidence_add.add_argument("--population")
    evidence_add.add_argument("--geography")
    evidence_add.add_argument("--timeframe")
    evidence_add.add_argument("--methodology")
    evidence_add.add_argument(
        "--confidence", choices=("low", "medium", "high"), default="medium"
    )
    return parser


def make_services(settings: Settings, database_url: str | None):
    database = Database(database_url or settings.database_url)
    database.create_schema()
    repository = Repository(database)
    ai = (
        OpenAIProvider(
            settings.openai_api_key,
            settings.openai_model,
            settings.input_cost_per_million,
            settings.output_cost_per_million,
        )
        if settings.openai_api_key
        else None
    )
    search = (
        GoogleSearchProvider(settings.google_api_key, settings.google_engine_id)
        if settings.google_api_key and settings.google_engine_id
        else None
    )
    return repository, ai, search


def execute(args: argparse.Namespace, settings: Settings) -> int:
    repository, ai, search = make_services(settings, args.database_url)

    if args.command == "new":
        project = repository.create_project(args.thesis, args.title)
        print(project.id)
        return 0

    if args.command == "plan":
        planner = Planner(repository, None if args.heuristic else ai)
        plan = planner.create_plan(args.project_id)
        output = args.output or settings.output_dir / args.project_id / "research_plan.json"
        plan.write(output)
        print(output)
        return 0

    if args.command == "approve":
        plan = ResearchPlan.read(args.plan_file)
        if plan.project_id != args.project_id:
            raise ValueError("Plan file belongs to a different project")
        count = repository.approve_plan(plan)
        print(f"Approved {count} propositions")
        return 0

    if args.command in {"run", "continue"}:
        if args.command == "continue":
            repository.set_project_status(
                args.project_id, ProjectStatus.APPROVED.value, pause=False
            )
        engine = ResearchEngine(
            repository,
            search=search,
            ai=ai,
            model=settings.openai_model,
            embedding_model=settings.embedding_model,
            max_searches=settings.max_searches_per_run,
        )
        print(json.dumps(engine.run(args.project_id), indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(repository.status(args.project_id), indent=2))
        return 0

    if args.command == "pause":
        repository.set_project_status(
            args.project_id, ProjectStatus.PAUSED.value, pause=True
        )
        print("Pause requested")
        return 0

    if args.command == "revise":
        thesis = repository.revise_thesis(args.project_id, args.thesis, args.reason)
        print(f"Created thesis version {thesis.version}")
        return 0

    if args.command == "render":
        output = args.output or settings.output_dir / args.project_id / "dossier.md"
        print(DossierRenderer(repository).render(args.project_id, output))
        return 0

    if args.command == "source":
        if args.source_command == "add":
            is_primary = args.primary or looks_primary(args.url)
            source = repository.add_source(
                args.url,
                title=args.title,
                publisher=args.publisher,
                source_type=args.source_type or infer_source_type(args.url),
                is_primary=is_primary,
            )
            print(source.id)
            return 0
        if args.source_command == "fetch":
            source = repository.source(args.source_id)
            document = SourceRetriever().retrieve(source.canonical_url)
            stored = repository.store_source_content(
                source.id, document.content, document.chunks
            )
            print(json.dumps({"source_id": stored.id, "chunks": len(document.chunks)}))
            return 0
        if args.source_command == "list":
            for source in repository.sources():
                print(
                    json.dumps(
                        {
                            "id": source.id,
                            "primary": source.is_primary,
                            "status": source.retrieval_status,
                            "type": source.source_type,
                            "title": source.title,
                            "url": source.canonical_url,
                        }
                    )
                )
            return 0

    if args.command == "evidence" and args.evidence_command == "add":
        proposition = next(
            (
                item
                for item in repository.propositions(args.project_id)
                if item.plan_key == args.proposition_key
            ),
            None,
        )
        if proposition is None:
            raise ValueError(f"Unknown proposition key: {args.proposition_key}")
        evidence = repository.add_evidence(
            proposition.id,
            args.source_id,
            args.chunk_id,
            EvidenceDraft(
                finding=args.finding,
                excerpt=args.excerpt,
                locator=args.locator,
                relationship=args.relationship,
                explanation=args.explanation,
                population=args.population,
                geography=args.geography,
                timeframe=args.timeframe,
                methodology=args.methodology,
                confidence=args.confidence,
            ),
        )
        print(evidence.id)
        return 0

    raise ValueError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(execute(args, Settings.from_env()))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
