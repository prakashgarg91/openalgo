"""The agent's research-platform toolkit: four reads, no writes, chat only."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("agno.tools", reason="the agent module needs agno")

from services.agent.tools import (  # noqa: E402
    SURFACE_CHART,
    SURFACE_CHAT,
    SURFACE_VOICE,
    ToolContext,
    select_specs,
)
from services.agent.tools.algos_read import AlgosReadToolkit  # noqa: E402
from services.algos import registry  # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "services" / "agent" / "tools" / "algos_read.py"
FOUR = {"get_idea_register", "get_forward_tests", "check_idea_draft", "was_idea_tried"}


def toolkit(surface=SURFACE_CHAT):
    return AlgosReadToolkit(ToolContext(api_key="k", surface=surface))


def payload(block: str) -> dict:
    return json.loads(re.search(r"\{.*\}", block, re.S).group(0))


def test_exactly_four_tools_and_all_of_them_are_reads():
    assert set(toolkit().functions) == FOUR


def test_the_toolkit_is_offered_in_chat_and_withheld_on_voice_and_the_chart():
    key = "algos_read"
    for surface, offered in ((SURFACE_CHAT, True), (SURFACE_VOICE, False), (SURFACE_CHART, False)):
        ctx = ToolContext(api_key="k", surface=surface, trading_enabled=True)
        assert (key in {s.key for s in select_specs(ctx)}) is offered, surface


def test_the_file_reaches_no_function_that_writes_runs_deploys_or_toggles():
    text = SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "registry.register", "record_run", "record_forward", "add_builder_trials", "placeorder",
        "place_order", "analyzer/toggle", "set_live", "deploy(", "start_run", "builder_jobs",
        "write_text", "open(",
    )  # fmt: skip
    assert [w for w in forbidden if w in text] == []


def test_the_register_view_reads_the_count_without_creating_the_folder(tmp_path, monkeypatch):
    folder = tmp_path / "nothing_here"
    monkeypatch.setenv("ALGO_REGISTRY_DIR", str(folder))
    out = payload(toolkit().get_idea_register())
    assert out["trial_count"] == registry.SEED_TRIALS and out["registrations"] == []
    assert not folder.exists()


def test_a_draft_check_saves_nothing_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGO_REGISTRY_DIR", str(tmp_path))
    out = payload(toolkit().check_idea_draft(json.dumps({"name": "x"})))
    assert out["ready_to_register"] is False and out["written"] is False
    assert not list(tmp_path.iterdir())
    assert payload(toolkit().check_idea_draft("not json"))["ok"] is False
    assert payload(toolkit().check_idea_draft("[1]"))["ok"] is False


def test_what_was_tried_before_reads_the_real_register():
    out = payload(toolkit().was_idea_tried("month end"))
    assert any(
        "c1" in m["text"].lower() or "month-end" in m["text"].lower() for m in out["matches"]
    )
