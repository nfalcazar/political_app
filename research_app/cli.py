from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

from .config import Settings
from .domain import EvidenceDraft, ResearchPlan
from .planner import Planner
from .renderer import DossierRenderer
from .researcher import ResearchEngine
from .sources import (
    infer_source_type,
    looks_primary,
)
from .content_policy import TokenCounter
from .services import make_retriever, make_services
from .states import ProjectStatus
from .utils import stable_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Build primary-source-grounded political research dossiers.",
    )
    parser.add_argument("--store", choices=("json", "sql"), help="Persistence adapter")
    parser.add_argument("--data-dir", type=Path, help="JSON workspace root")
    parser.add_argument("--database-url", help="Override RESEARCH_DATABASE_URL")
    parser.add_argument(
        "--reasoning-provider", choices=("deepseek", "codex"),
        help="Model provider for planning and evidence analysis",
    )
    parser.add_argument(
        "--search-provider", choices=("scholarly", "codex", "hybrid", "none"),
        help="Provider for discovering candidate sources",
    )
    parser.add_argument("--deepseek-model", help="Override the DeepSeek model")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Create a research project")
    new.add_argument("thesis")
    new.add_argument("--title")

    guide = sub.add_parser(
        "guide", help="Choose research directions in an interactive planning session"
    )
    guide.add_argument("thesis", nargs="?")
    guide.add_argument("--title")
    guide.add_argument("--output", type=Path)
    guide.add_argument("--heuristic", action="store_true", help="Do not call a model")

    plan = sub.add_parser("plan", help="Generate an editable research plan")
    plan.add_argument("project_id")
    plan.add_argument("--output", type=Path)
    plan.add_argument("--heuristic", action="store_true", help="Do not call a model")
    plan.add_argument(
        "--interactive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Choose plan directions interactively (default when attached to a terminal)",
    )

    approve = sub.add_parser("approve", help="Approve an edited plan")
    approve.add_argument("project_id")
    approve.add_argument("plan_file", type=Path)

    run = sub.add_parser("run", help="Run or resume approved research")
    run.add_argument("project_id")
    run.add_argument(
        "--max-sources", type=int,
        help="stop after this many sources are retrieved successfully",
    )
    run.add_argument("--max-runtime", type=str)
    run.add_argument("--max-queries", type=int, help="maximum query-graph nodes to execute")
    run.add_argument(
        "--browser", action=argparse.BooleanOptionalAction, default=None,
        help="enable the optional safe Playwright retrieval fallback",
    )

    status = sub.add_parser("status", help="Show project coverage and usage")
    status.add_argument("project_id")

    errors = sub.add_parser("errors", help="Show provider and processing errors")
    errors.add_argument("project_id")

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
    continue_parser.add_argument(
        "--max-sources", type=int,
        help="stop after this many sources are retrieved successfully",
    )
    continue_parser.add_argument("--max-runtime", type=str)
    continue_parser.add_argument("--max-queries", type=int)
    continue_parser.add_argument(
        "--browser", action=argparse.BooleanOptionalAction, default=None,
    )

    graph = sub.add_parser("graph", help="Show the durable research query graph")
    graph.add_argument("project_id")
    graph.add_argument("--json", action="store_true", dest="as_json")

    benchmark = sub.add_parser(
        "benchmark", help="Report recorded retrieval outcomes without live web access"
    )
    benchmark.add_argument("project_id")

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
    source_add.add_argument(
        "--rights",
        choices=("public_domain", "open_license", "permission", "copyrighted", "unknown", "restricted"),
    )
    source_add.add_argument("--license")
    source_fetch = source_sub.add_parser("fetch", help="Download and chunk a source")
    source_fetch.add_argument("source_id")
    source_sub.add_parser("list", help="List stored sources")
    source_block = source_sub.add_parser("block", help="Block a URL or domain from retrieval")
    source_block.add_argument("target")
    source_block.add_argument("--reason", required=True)
    source_unblock = source_sub.add_parser("unblock", help="Remove a URL or domain block")
    source_unblock.add_argument("target")
    source_purge = source_sub.add_parser("purge-cache", help="Delete a source's full-text cache")
    source_purge.add_argument("source_id")
    source_takedown = source_sub.add_parser(
        "takedown", help="Remove retained content/evidence and block future retrieval"
    )
    source_takedown.add_argument("source_id")
    source_takedown.add_argument("--reason", required=True)
    source_rights = source_sub.add_parser("rights", help="Record a reviewed source rights status")
    source_rights.add_argument("source_id")
    source_rights.add_argument(
        "status",
        choices=("public_domain", "open_license", "permission", "copyrighted", "unknown", "restricted"),
    )
    source_rights.add_argument("--license")
    source_rights.add_argument("--basis", required=True)

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

    catalog = sub.add_parser("catalog", help="Maintain the JSON source catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_sub.add_parser("rebuild", help="Rebuild URL and content indexes")
    catalog_sub.add_parser(
        "migrate-storage",
        help="Rechunk legacy sources and move full text into rights-aware caches",
    )

    sub.add_parser("doctor", help="Check storage and configured provider access")
    return parser


class InteractiveCancelled(Exception):
    pass


def parse_selection(value: str, item_count: int) -> list[int]:
    """Parse a one-based comma/range selection into sorted zero-based indexes."""
    value = value.strip().lower()
    if value == "all":
        return list(range(item_count))
    if not value:
        raise ValueError("choose at least one direction")

    selected: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            raise ValueError("use numbers separated by commas")
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2 or not all(bound.strip().isdigit() for bound in bounds):
                raise ValueError(f"invalid range: {part}")
            start, end = (int(bound.strip()) for bound in bounds)
            if start > end:
                raise ValueError(f"range must be ascending: {part}")
            numbers = range(start, end + 1)
        elif part.isdigit():
            numbers = (int(part),)
        else:
            raise ValueError(f"invalid choice: {part}")

        for number in numbers:
            if not 1 <= number <= item_count:
                raise ValueError(f"choice {number} is outside 1-{item_count}")
            index = number - 1
            if index in selected:
                raise ValueError(f"choice {number} was selected more than once")
            selected.add(index)
    return sorted(selected)


def prompt_for_thesis() -> str:
    while True:
        try:
            value = input("Topic or thesis (q to cancel): ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InteractiveCancelled from exc
        if value.lower() == "q":
            raise InteractiveCancelled
        if value:
            return value
        print("Please enter a topic or thesis.")


def choose_propositions(plan: ResearchPlan) -> list[int]:
    print("\nResearch directions:\n")
    for number, proposition in enumerate(plan.propositions, start=1):
        query_count = len(proposition.search_queries)
        query_word = "query" if query_count == 1 else "queries"
        query_label = f"{query_count} search {query_word}"
        print(
            f"{number}. [{proposition.kind}; {proposition.polarity}] "
            f"{proposition.text}\n   {query_label}"
        )

    while True:
        try:
            value = input(
                "\nChoose directions (for example 1,3-5 or all; q to cancel): "
            ).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InteractiveCancelled from exc
        if value.lower() == "q":
            raise InteractiveCancelled
        try:
            return parse_selection(value, len(plan.propositions))
        except ValueError as exc:
            print(f"Invalid selection: {exc}")


def selected_plan(plan: ResearchPlan, indexes: list[int]) -> ResearchPlan:
    return ResearchPlan(
        project_id=plan.project_id,
        thesis=plan.thesis,
        thesis_version=plan.thesis_version,
        propositions=[plan.propositions[index] for index in indexes],
        approval_required=plan.approval_required,
        max_source_attempts=plan.max_source_attempts,
        max_runtime_seconds=plan.max_runtime_seconds,
    )


def use_interactive_plan(args: argparse.Namespace) -> bool:
    if args.interactive is not None:
        return args.interactive
    return sys.stdin.isatty() and sys.stdout.isatty()


def parse_duration(value: str) -> int:
    value = value.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600}
    if value and value[-1] in units:
        number, multiplier = value[:-1], units[value[-1]]
    else:
        number, multiplier = value, 60
    if not number.isdigit() or int(number) <= 0:
        raise ValueError("Runtime must be a positive duration such as 20m or 1h")
    return int(number) * multiplier


def prompt_limits(plan: ResearchPlan) -> ResearchPlan:
    try:
        source_value = input(
            f"Maximum successfully retrieved sources [{plan.max_source_attempts}]: "
        ).strip()
        runtime_value = input("Maximum runtime [15m]: ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise InteractiveCancelled from exc
    if source_value:
        if not source_value.isdigit() or int(source_value) <= 0:
            raise ValueError("Maximum sources must be a positive integer")
        plan.max_source_attempts = int(source_value)
    if runtime_value:
        plan.max_runtime_seconds = parse_duration(runtime_value)
    return plan


def execute(args: argparse.Namespace, settings: Settings) -> int:
    services = make_services(settings, args)
    repository, ai, search = services[:3]
    embedder = services[3] if len(services) > 3 else None
    data_dir = args.data_dir or settings.data_dir

    def debug_context(project_id: str) -> None:
        if hasattr(ai, "set_debug_context"):
            ai.set_debug_context(project_id)

    if args.command == "new":
        project = repository.create_project(args.thesis, args.title)
        print(project.id)
        return 0

    if args.command == "guide":
        try:
            thesis = args.thesis.strip() if args.thesis else prompt_for_thesis()
        except InteractiveCancelled:
            print("Guided planning cancelled.")
            return 130
        if not thesis:
            raise ValueError("Thesis cannot be empty")

        project = repository.create_project(thesis, args.title)
        debug_context(project.id)
        print(f"Project: {project.id}")
        planner = Planner(repository, None if args.heuristic else ai)
        plan = planner.create_plan(project.id)
        try:
            plan = prompt_limits(plan)
        except (InteractiveCancelled, ValueError) as exc:
            print(f"Guided planning cancelled. Project retained: {project.id}")
            return 130
        output = args.output or data_dir / "projects" / project.id / "research_plan.json"
        plan.write(output)
        quoted_output = shlex.quote(str(output))
        print(f"\nPlan: {output}")
        print("Review or edit the plan, then run:")
        print(f"research approve {project.id} {quoted_output}")
        print(f"research run {project.id}")
        return 0

    if args.command == "plan":
        debug_context(args.project_id)
        planner = Planner(repository, None if args.heuristic else ai)
        plan = planner.create_plan(args.project_id)
        if use_interactive_plan(args):
            try:
                plan = prompt_limits(plan)
            except InteractiveCancelled:
                print(
                    f"Interactive planning cancelled. Project retained: {args.project_id}"
                )
                return 130
        output = args.output or data_dir / "projects" / args.project_id / "research_plan.json"
        plan.write(output)
        if use_interactive_plan(args):
            print(f"\nPlan: {output}")
            print("Review or edit the plan, then run:")
            print(f"research approve {args.project_id} {shlex.quote(str(output))}")
        else:
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
        debug_context(args.project_id)
        if args.max_sources is not None and args.max_sources <= 0:
            raise ValueError("--max-sources must be a positive integer")
        if args.max_queries is not None and args.max_queries <= 0:
            raise ValueError("--max-queries must be a positive integer")
        if args.command == "continue":
            status = repository.status(args.project_id)
            if status["status"] != ProjectStatus.EVIDENCE_REVIEW:
                raise ValueError("Continue is available only at the evidence-review checkpoint")
            repository.advance_research_pass(args.project_id)
        engine = ResearchEngine(
            repository,
            search=search,
            ai=ai,
            model=getattr(ai, "model", None),
            embedding_model=settings.embedding_model,
            embedding_provider=embedder,
            max_source_attempts=args.max_sources,
            max_queries=args.max_queries,
            max_runtime_seconds=(parse_duration(args.max_runtime) if args.max_runtime else None),
            retriever=make_retriever(settings, args),
            passages_per_proposition=settings.source_passages_per_proposition,
            passage_cap=settings.source_passage_cap,
        )
        print(json.dumps(engine.run(args.project_id), indent=2))
        return 0

    if args.command == "graph":
        if not hasattr(repository, "query_nodes"):
            raise ValueError("Query graphs are currently available for JSON storage")
        nodes = repository.query_nodes(args.project_id)
        if args.as_json:
            from dataclasses import asdict
            print(json.dumps({"summary": repository.query_graph_summary(args.project_id), "nodes": [asdict(item) for item in nodes]}, indent=2))
        else:
            summary = repository.query_graph_summary(args.project_id)
            print(json.dumps(summary, indent=2))
            for node in sorted(nodes, key=lambda item: (-item.priority, item.created_at)):
                print(f"{node.status:8} d{node.depth} p{node.priority:g} {node.query_kind}: {node.query}")
        return 0

    if args.command == "status":
        print(json.dumps(repository.status(args.project_id), indent=2))
        return 0

    if args.command == "benchmark":
        if not hasattr(repository, "retrieval_benchmark"):
            raise ValueError("Recorded retrieval benchmarks currently require JSON storage")
        print(json.dumps(repository.retrieval_benchmark(args.project_id), indent=2))
        return 0

    if args.command == "errors":
        print(json.dumps(repository.errors(args.project_id), indent=2))
        return 0

    if args.command == "pause":
        repository.set_project_status(
            args.project_id, ProjectStatus.PAUSED, pause=True
        )
        print("Pause requested")
        return 0

    if args.command == "revise":
        thesis = repository.revise_thesis(args.project_id, args.thesis, args.reason)
        print(f"Created thesis version {thesis.version}")
        return 0

    if args.command == "render":
        output = args.output or data_dir / "projects" / args.project_id / "dossier.md"
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
                rights_status=args.rights,
                detected_license=args.license,
            )
            print(source.id)
            return 0
        if args.source_command == "fetch":
            source = repository.source(args.source_id)
            document = make_retriever(settings, args).retrieve(source.canonical_url)
            stored = repository.store_source_content(
                source.id,
                document.content,
                document.chunks[: settings.source_passage_cap],
                archive_chunks=document.chunks,
                access_metadata={
                    "detected_license": document.detected_license,
                    "retrieval_permission": document.retrieval_permission,
                    "robots_status": document.robots_status,
                    "terms_status": document.terms_status,
                    "resolved_url": document.resolved_url,
                    "alternate_urls": document.alternate_urls or [],
                    "retrieval_attempts": document.retrieval_attempts or [],
                    "needs_ocr": document.needs_ocr,
                    "token_counts": {
                        stable_hash(text): TokenCounter(settings.embedding_model).count(text)
                        for _, text in document.chunks
                    },
                },
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
        if args.source_command == "block":
            if not hasattr(repository, "block_source"):
                raise ValueError("Source blocking is currently available for JSON storage")
            print(json.dumps(repository.block_source(args.target, args.reason), indent=2))
            return 0
        if args.source_command == "unblock":
            if not hasattr(repository, "unblock_source"):
                raise ValueError("Source blocking is currently available for JSON storage")
            print(json.dumps({"removed": repository.unblock_source(args.target)}))
            return 0
        if args.source_command == "purge-cache":
            if not hasattr(repository, "delete_source_cache"):
                raise ValueError("Source caches are currently available for JSON storage")
            print(json.dumps({"deleted": repository.delete_source_cache(args.source_id, force=True)}))
            return 0
        if args.source_command == "takedown":
            if not hasattr(repository, "takedown_source"):
                raise ValueError("Takedown is currently available for JSON storage")
            print(json.dumps(repository.takedown_source(args.source_id, args.reason), indent=2))
            return 0
        if args.source_command == "rights":
            if not hasattr(repository, "set_source_rights"):
                raise ValueError("Rights review is currently available for JSON storage")
            source = repository.set_source_rights(
                args.source_id,
                args.status,
                license_value=args.license,
                basis=args.basis,
            )
            print(json.dumps({
                "source_id": source.id,
                "rights_status": source.rights_status,
                "license": source.detected_license,
                "cache_expires_at": source.cache_metadata.get("expires_at"),
            }, indent=2))
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

    if args.command == "catalog" and args.catalog_command == "rebuild":
        if not hasattr(repository, "rebuild_catalog"):
            raise ValueError("Catalog rebuilding applies only to JSON storage")
        print(json.dumps(repository.rebuild_catalog(), indent=2))
        return 0

    if args.command == "catalog" and args.catalog_command == "migrate-storage":
        if not hasattr(repository, "project_ids"):
            raise ValueError("Storage migration currently applies only to JSON storage")
        engine = ResearchEngine(
            repository,
            embedding_model=settings.embedding_model,
            retriever=make_retriever(settings, args),
            passages_per_proposition=settings.source_passages_per_proposition,
            passage_cap=settings.source_passage_cap,
        )
        repaired = sum(
            engine._repair_oversized_chunks(project_id)
            for project_id in repository.project_ids()
        )
        expired = repository.expire_caches()
        print(json.dumps({"sources_migrated": repaired, "expired_caches_deleted": expired}, indent=2))
        return 0

    if args.command == "doctor":
        storage = (
            repository.doctor()
            if hasattr(repository, "doctor")
            else {"store": "sql", "configured": True}
        )
        result = {
            "storage": storage,
            "reasoning_provider": getattr(ai, "provider_name", None),
            "search_provider": getattr(search, "provider_name", None),
            "deepseek_key_configured": bool(settings.deepseek_api_key),
            "embedding_provider": getattr(embedder, "provider_name", "none"),
            "embedding_model": getattr(embedder, "model", None),
            "openai_key_configured": bool(settings.openai_api_key),
        }
        if getattr(ai, "provider_name", None) == "codex":
            result["codex"] = ai.login_status()
        elif getattr(ai, "provider_name", None) == "deepseek":
            result["deepseek"] = {
                "configured": True,
                "model": ai.model,
                "thinking": getattr(ai, "thinking", False),
                "reasoning_effort": getattr(ai, "reasoning_effort", None),
            }
        print(json.dumps(result, indent=2))
        return 0

    raise ValueError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(execute(args, Settings.from_env()))
    except (ValueError, OSError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
