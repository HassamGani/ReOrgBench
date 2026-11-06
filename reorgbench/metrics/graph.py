"""Causal action graph over a trace, built from rules only.

Edge kinds:
- structural: a spawn enables every action of the agent it created; a kill enables the
  killed agents' relay messages.
- provenance: the event that last wrote an object enables any later event that reads it;
  an agent's own read of an object enables its later write to that object (read-modify-write).
- delivery: the vendor email enables the reply the environment delivers.
- value flow: a salient token (an ID like INV-5521, or an amount >= 100) that first entered an
  agent's context through event x enables that agent's later actions that use the token.
  "First" is what makes message use a causal claim: if the recipient already had the token, or
  got it another way first, the message gets no edge.

Messages with no salient token can't be resolved by rules; they are counted separately for a
judge tier (not implemented yet).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..env.world import World
from ..tasks.spec import Task

ACTION_TYPES = frozenset({"env", "msg", "relay", "spawn", "inspect", "kill", "finish", "ask_human", "error"})

_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+\b")      # INV-5521, PX-14b, QA-55X1
_NUM = re.compile(r"(?<![\w.\-])\d+(?:\.\d+)?(?![\w.\-])")     # 240.0, $1200; not the 8812 in CNQ-8812
MIN_AMOUNT = 100


def _canon(n: str) -> str:
    v = float(n)
    return str(int(v)) if v.is_integer() else repr(v)


def salient_tokens(x: Any, planted: Iterable[str] = ()) -> set[str]:
    """IDs and amounts by pattern, plus any planted fact token by exact substring (they can look like anything)."""
    s = x if isinstance(x, str) else json.dumps(x, sort_keys=True)
    out = set(_ID.findall(s))
    out |= {_canon(n) for n in _NUM.findall(s) if float(n) >= MIN_AMOUNT}
    out |= {t for t in planted if t in s}
    return out


def action_text(e: dict[str, Any]) -> Any:
    """What an action puts out into the world or into others' contexts (excluding tool results)."""
    p = e["payload"]
    if e["type"] == "env":
        return p.get("args", {})
    if e["type"] in ("msg", "relay"):
        return p.get("content", "")
    if e["type"] == "spawn":
        return p.get("brief", "")
    if e["type"] == "finish":
        return p.get("answer", "")
    return ""


@dataclass
class CausalGraph:
    parents: dict[int, set[int]]
    kinds: dict[tuple[int, int], set[str]]
    actions: list[int]                  # T: all agent actions, including errors
    by_agent: dict[str, list[int]]
    seeds: set[int]
    contributing: set[int]              # C: seeds and their ancestors, actions only
    exposure: dict[str, dict[str, int | None]]   # agent -> token -> event that first exposed it
    events: list[dict[str, Any]] = field(repr=False, default_factory=list)

    def edge_kinds(self, src: int, dst: int) -> set[str]:
        return self.kinds.get((src, dst), set())

    def ancestors(self, nodes: Iterable[int]) -> set[int]:
        seen, stack = set(), list(nodes)
        while stack:
            n = stack.pop()
            for p in self.parents.get(n, ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        return seen


def build_graph(task: Task, events: list[dict[str, Any]], world: World, final_phase: int) -> CausalGraph:
    parents: dict[int, set[int]] = {}
    kinds: dict[tuple[int, int], set[str]] = {}

    def add(src: int | None, dst: int, kind: str) -> None:
        if src is None or src == dst:
            return
        parents.setdefault(dst, set()).add(src)
        kinds.setdefault((src, dst), set()).add(kind)

    planted = [f.token for f in task.facts]
    spawn_of: dict[str, int] = {}
    kill_of: dict[str, int] = {}
    last_writer: dict[str, int] = {}
    own_reads: dict[tuple[str, str], int] = {}
    exposure: dict[str, dict[str, int | None]] = {}
    actions: list[int] = []
    by_agent: dict[str, list[int]] = {}

    for e in events:
        eid, agent, t = e["id"], e["agent"], e["type"]

        if t == "observation":
            seen = exposure.setdefault(agent, {})
            src = e["caused_by"][0] if e["caused_by"] else None
            for tok in salient_tokens(e["payload"]["content"], planted):
                seen.setdefault(tok, src)
            continue

        if t == "system":
            for d in e["payload"].get("deliveries", []):
                if d.get("in_reply_to"):
                    add(last_writer.get(f"outbox/{d['in_reply_to']}"), eid, "delivery")

        if t in ACTION_TYPES:
            actions.append(eid)
            by_agent.setdefault(agent, []).append(eid)
            add(spawn_of.get(agent), eid, "structural")
            if t == "relay":
                add(kill_of.get(agent), eid, "structural")
            seen = exposure.get(agent, {})
            for tok in salient_tokens(action_text(e), planted):
                add(seen.get(tok), eid, "value")

        for o in e["reads"]:
            add(last_writer.get(o), eid, "provenance")
        for o in e["writes"]:
            add(own_reads.get((agent, o)), eid, "provenance")
        for o in e["reads"]:
            own_reads[(agent, o)] = eid
        for o in e["writes"]:
            last_writer[o] = eid

        if t == "spawn":
            spawn_of[e["payload"]["new_agent"]] = eid
        elif t == "kill":
            for a in e["payload"]["cascade"]:
                kill_of[a] = eid

    # seeds: the events that wrote the final version of each object realizing a passed checkpoint
    from ..tasks.spec import EpisodeView

    fired = {e["payload"]["intervention_id"]: e["id"] for e in events if e["type"] == "intervention"}
    view = EpisodeView(events, fired)
    seeds: set[int] = set()
    for c in task.phases[final_phase].checkpoints:
        if c.negative or c.realized_by is None or not c.check(world, view):
            continue
        for oid in c.realized_by(world):
            wb = world.objects[oid]["written_by"]
            if wb is not None:
                seeds.add(wb)

    g = CausalGraph(parents, kinds, actions, by_agent, seeds, set(), exposure, events)
    action_set = set(actions)
    g.contributing = {n for n in seeds | g.ancestors(seeds) if n in action_set}
    return g
