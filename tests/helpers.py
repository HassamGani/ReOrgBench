from __future__ import annotations

from typing import Any

from reorgbench.runtime import Episode
from reorgbench.runtime.policy import AgentInfo, Observation


class Script:
    """Per-agent action lists; an agent with nothing left does noop."""

    def __init__(self, plans: dict[str, list[dict[str, Any]]]):
        self.plans = {k: list(v) for k, v in plans.items()}
        self.seen: dict[str, list[Observation]] = {}

    def __call__(self, info: AgentInfo):
        script = self

        class P:
            def act(self, obs: Observation) -> dict[str, Any]:
                script.seen.setdefault(info.id, []).append(obs)
                plan = script.plans.get(info.id, [])
                return plan.pop(0) if plan else {"type": "noop"}

        return P()


def run_script(task, plans):
    script = Script(plans)
    res = Episode(task, script).run()
    return res, script


def errors(res, kind=None):
    return [e for e in res.events if e["type"] == "error" and (kind is None or e["payload"]["kind"] == kind)]
