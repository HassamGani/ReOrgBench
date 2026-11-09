"""Deterministic object store with provenance.

Every object remembers which event last wrote it, and every tool call logs the object ids it
read and wrote. That is what turns most env->env causal edges into plain data flow.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class AccessLog:
    event_id: int | None = None
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)

    def read(self, oid: str) -> None:
        if oid not in self.reads:
            self.reads.append(oid)

    def write(self, oid: str) -> None:
        if oid not in self.writes:
            self.writes.append(oid)


class World:
    def __init__(self, objects: dict[str, dict[str, Any]] | None = None):
        # oid -> {"data": {...}, "version": int, "written_by": event id or None}
        self.objects: dict[str, dict[str, Any]] = {}
        self.counters: dict[str, int] = {}
        # environment-side deliveries due in a later round, e.g. vendor replies
        self.scheduled: list[dict[str, Any]] = []
        for oid, data in (objects or {}).items():
            self.objects[oid] = {"data": copy.deepcopy(data), "version": 0, "written_by": None,
                                 "initial": copy.deepcopy(data)}

    @staticmethod
    def collection_of(oid: str) -> str:
        return oid.rsplit("/", 1)[0]

    def exists(self, oid: str) -> bool:
        return oid in self.objects

    def get(self, oid: str, log: AccessLog | None = None) -> dict[str, Any] | None:
        obj = self.objects.get(oid)
        if obj is None:
            return None
        if log is not None:
            log.read(oid)
        return copy.deepcopy(obj["data"])

    def put(self, oid: str, data: dict[str, Any], log: AccessLog | None = None) -> None:
        prev = self.objects.get(oid)
        self.objects[oid] = {
            "data": copy.deepcopy(data),
            "version": (prev["version"] + 1) if prev else 1,
            "written_by": log.event_id if log is not None else None,
            **({"initial": prev["initial"]} if prev and "initial" in prev else {}),
        }
        if log is not None:
            log.write(oid)

    def iter(self, collection: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """Objects in a collection, in insertion order. Does not log reads; callers log what they use."""
        prefix = collection + "/"
        for oid, obj in self.objects.items():
            if oid.startswith(prefix) and "/" not in oid[len(prefix):]:
                yield oid, obj["data"]

    def next_id(self, counter: str, prefix: str) -> str:
        n = self.counters.get(counter, 0) + 1
        self.counters[counter] = n
        return f"{prefix}{n}"

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {"objects": self.objects, "counters": self.counters, "scheduled": self.scheduled}
        )

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> "World":
        w = cls()
        snap = copy.deepcopy(snap)
        w.objects, w.counters, w.scheduled = snap["objects"], snap["counters"], snap["scheduled"]
        return w

    def digest(self) -> str:
        import hashlib

        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()[:16]

    def data(self, oid: str) -> dict[str, Any] | None:
        """Read without logging. For verifiers and triggers only, never for agent tools."""
        obj = self.objects.get(oid)
        return copy.deepcopy(obj["data"]) if obj else None
