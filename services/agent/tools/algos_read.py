"""Read-only view of the idea register and the forward tests, for the in-app agent.

Four tools, all reads: the register (trial count, the bar a forward result must clear, the next free
idea month), the forward tests, a check of a draft idea that saves nothing, and a search of what was
tried before. The agent can see the research platform and explain it; it cannot register an idea,
run a screen, record a result, start a deployment or touch the Live and Analyze switch, because no
tool here, and no function the tools call, does any of that. A test pins the four names and checks
that this file reaches no write function (docs/algos/algo-builder-v2.md).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.agent.prompts import wrap_tool_result
from services.agent.tools.base import OpenAlgoToolkit, dumps_capped
from services.algos import agent_view

if TYPE_CHECKING:  # pragma: no cover - typing only
    from services.agent.tools import ToolContext

RESULT_CHARS = 12_000
DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs" / "algos"


def _folder() -> Path:
    return Path(os.getenv("ALGO_REGISTRY_DIR", "db/algo_registry"))


class AlgosReadToolkit(OpenAlgoToolkit):
    """What is registered, what is running forward, and whether an idea was already tried."""

    def __init__(self, context: ToolContext) -> None:
        super().__init__(
            context,
            name="algos_read",
            tools=[
                self.get_idea_register,
                self.get_forward_tests,
                self.check_idea_draft,
                self.was_idea_tried,
            ],
        )

    def _result(self, tool: str, payload: Any) -> str:
        return wrap_tool_result(tool, dumps_capped(payload, RESULT_CHARS))

    def get_idea_register(self) -> str:
        """Read the idea register: how many ideas and settings have been tried, the bar a forward
        result must clear, the next month with a free idea slot, and every registered idea with its
        status. Read only. Use it before suggesting anything, and quote the count and the bar.

        Returns:
            JSON with trial_count, pass_bar, next_free_month, months_used and registrations.
        """
        return self._result(
            "get_idea_register", agent_view.register_status(_folder(), datetime.now())
        )

    def get_forward_tests(self) -> str:
        """Read where each forward test in Sandbox mode stands: its state, trades done, trades still
        to go and net after costs. Nothing here is a result until a test has ended; say so.

        Returns:
            JSON with a list of forward tests.
        """
        return self._result("get_forward_tests", {"forward_tests": agent_view.forward_status()})

    def check_idea_draft(self, draft_json: str) -> str:
        """Check a draft idea against the registration rules WITHOUT saving it: missing fields,
        settings with more than one value, a used month, a restated idea. Only the owner registers an
        idea, from the Register an idea tab; this tool cannot.

        Args:
            draft_json: The draft as a JSON object with the registration fields.

        Returns:
            JSON with ready_to_register, problems and written (always false).
        """
        try:
            draft = json.loads(draft_json)
        except ValueError:
            return self._result(
                "check_idea_draft", {"ok": False, "message": "The draft is not valid JSON."}
            )
        if not isinstance(draft, dict):
            return self._result(
                "check_idea_draft", {"ok": False, "message": "The draft must be a JSON object."}
            )
        from services.algos.templates import ALGOS

        return self._result(
            "check_idea_draft",
            agent_view.validate_draft(draft, _folder(), datetime.now(), set(ALGOS)),
        )

    def was_idea_tried(self, query: str) -> str:
        """Search the trial register and the results pages for an idea, by its words, to see whether
        it, or something close, was already tried and how it ended.

        Args:
            query: A few words, for example "month end ETF" or "weekly call spread".

        Returns:
            JSON with matching lines (file, line, text), at most eight.
        """
        return self._result(
            "was_idea_tried", {"matches": agent_view.tried_before(query, DOCS_ROOT)}
        )
