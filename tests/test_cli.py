from pathlib import Path

import pytest

from research_app import cli
from research_app.config import Settings
from research_app.domain import ResearchPlan
from research_app.json_repository import JsonRepository


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", [0]),
        ("1, 3-5", [0, 2, 3, 4]),
        ("5,1,3", [0, 2, 4]),
        ("all", [0, 1, 2, 3, 4]),
    ],
)
def test_parse_selection(value, expected):
    assert cli.parse_selection(value, 5) == expected


@pytest.mark.parametrize(
    "value",
    ["", "0", "6", "2-1", "one", "1,,2", "1-3,3", "1-2-3"],
)
def test_parse_selection_rejects_invalid_input(value):
    with pytest.raises(ValueError):
        cli.parse_selection(value, 5)


@pytest.mark.parametrize(("value", "seconds"), [("30s", 30), ("20m", 1200), ("2h", 7200), ("5", 300)])
def test_parse_duration(value, seconds):
    assert cli.parse_duration(value) == seconds


def settings(data_dir: Path) -> Settings:
    return Settings(
        store="json",
        data_dir=data_dir,
        database_url=None,
        embedding_model="unused",
        codex_executable="unused",
        codex_timeout=10,
    )


def test_guided_workflow_prompts_for_limits_and_writes_full_plan(
    tmp_path, monkeypatch, capsys
):
    repository = JsonRepository(tmp_path)
    monkeypatch.setattr(
        cli, "make_services", lambda settings_, args: (repository, object(), None)
    )
    answers = iter(
        [
            "How does public transit affect cities?",
            "12",
            "5m",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    args = cli.build_parser().parse_args(["guide", "--heuristic"])
    assert cli.execute(args, settings(tmp_path)) == 0

    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_id = project_dirs[0].name
    plan_path = project_dirs[0] / "research_plan.json"
    plan = ResearchPlan.read(plan_path)
    assert [item.key for item in plan.propositions] == [
        "outcomes", "mechanism", "tradeoffs", "normative_priority"
    ]
    assert plan.max_source_attempts == 12
    assert plan.max_runtime_seconds == 300
    assert repository.project(project_id).status == "planned"

    output = capsys.readouterr().out
    assert f"research approve {project_id} {plan_path}" in output
    assert f"research run {project_id}" in output


def test_guided_workflow_cancellation_retains_unapproved_project(
    tmp_path, monkeypatch, capsys
):
    repository = JsonRepository(tmp_path)
    monkeypatch.setattr(
        cli, "make_services", lambda settings_, args: (repository, object(), None)
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "q")

    args = cli.build_parser().parse_args(
        ["guide", "A thesis to investigate", "--heuristic"]
    )
    assert cli.execute(args, settings(tmp_path)) == 130

    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project = repository.project(project_dirs[0].name)
    assert project.status == "planned"
    assert not (project_dirs[0] / "research_plan.json").exists()
    assert f"Project retained: {project.id}" in capsys.readouterr().out


def test_plan_command_can_choose_limits_interactively(
    tmp_path, monkeypatch, capsys
):
    repository = JsonRepository(tmp_path)
    project = repository.create_project("How does public transit affect cities?")
    monkeypatch.setattr(
        cli, "make_services", lambda settings_, args: (repository, object(), None)
    )
    answers = iter(["8", "10m"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    args = cli.build_parser().parse_args(
        ["plan", project.id, "--heuristic", "--interactive"]
    )
    assert cli.execute(args, settings(tmp_path)) == 0

    plan_path = tmp_path / "projects" / project.id / "research_plan.json"
    plan = ResearchPlan.read(plan_path)
    assert len(plan.propositions) == 4
    assert plan.max_source_attempts == 8
    assert plan.max_runtime_seconds == 600
    output = capsys.readouterr().out
    assert f"research approve {project.id} {plan_path}" in output


def test_plan_command_no_interactive_preserves_full_plan(tmp_path, monkeypatch):
    repository = JsonRepository(tmp_path)
    project = repository.create_project("How does public transit affect cities?")
    monkeypatch.setattr(
        cli, "make_services", lambda settings_, args: (repository, object(), None)
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: pytest.fail("non-interactive planning must not prompt"),
    )

    args = cli.build_parser().parse_args(
        ["plan", project.id, "--heuristic", "--no-interactive"]
    )
    assert cli.execute(args, settings(tmp_path)) == 0

    plan_path = tmp_path / "projects" / project.id / "research_plan.json"
    assert len(ResearchPlan.read(plan_path).propositions) == 4
