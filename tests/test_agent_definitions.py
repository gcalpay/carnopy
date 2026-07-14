from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIRECTORY = REPOSITORY_ROOT / ".codex" / "agents"
EXPECTED_AGENTS = {
    "architect": ("gpt-5.6-sol", "max", "read-only"),
    "explorer": ("gpt-5.6-luna", "high", "read-only"),
    "reviewer": ("gpt-5.6-sol", "xhigh", "read-only"),
    "worker": ("gpt-5.6-luna", "max", "workspace-write"),
}
NICKNAME_PATTERN = re.compile(r"[A-Za-z0-9 _-]+\Z")


def _load_agent(name: str) -> dict[str, Any]:
    with (AGENT_DIRECTORY / f"{name}.toml").open("rb") as source:
        return tomllib.load(source)


def test_only_approved_project_agent_definitions_exist() -> None:
    discovered = {path.stem for path in AGENT_DIRECTORY.glob("*.toml")}

    assert discovered == set(EXPECTED_AGENTS)


@pytest.mark.parametrize(("name", "expected"), EXPECTED_AGENTS.items())
def test_project_agent_definition_pins_required_runtime(
    name: str,
    expected: tuple[str, str, str],
) -> None:
    model, reasoning_effort, sandbox_mode = expected
    definition = _load_agent(name)
    instructions = " ".join(definition["developer_instructions"].split())

    assert set(definition) == {
        "name",
        "description",
        "model",
        "model_reasoning_effort",
        "sandbox_mode",
        "nickname_candidates",
        "developer_instructions",
    }
    assert definition["name"] == name
    assert definition["description"].strip()
    assert instructions
    assert definition["model"] == model
    assert definition["model_reasoning_effort"] == reasoning_effort
    assert definition["sandbox_mode"] == sandbox_mode
    assert "Do not spawn descendant agents." in instructions


def test_project_agent_nickname_pools_are_distinct_and_well_formed() -> None:
    all_nicknames: list[str] = []

    for name in EXPECTED_AGENTS:
        nicknames = _load_agent(name)["nickname_candidates"]
        assert len(nicknames) >= 8
        assert len(nicknames) == len(set(nicknames))
        assert all(NICKNAME_PATTERN.fullmatch(nickname) for nickname in nicknames)
        all_nicknames.extend(nicknames)

    assert len(all_nicknames) == len(set(all_nicknames))


def test_delegation_policy_distinguishes_roles_tasks_and_lifecycle() -> None:
    policy = " ".join((REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8").split())

    assert "`agent_type`" in policy
    assert "`task_name` is only a canonical thread-path label" in policy
    assert "`close_agent`" in policy
    assert "`interrupt_agent` stops a turn but leaves its thread open" in policy
