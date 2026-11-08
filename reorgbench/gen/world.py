"""Seeded world material for generated tasks: company names, unique ids, customer accounts."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

_FIRST = ["Abbot", "Brisa", "Calloway", "Harrow", "Esk", "Fenmore", "Gilt", "Hollin", "Ibex", "Juniper", "Kirkby",
          "Lantern", "Mossgrove", "Northgate", "Orrin", "Pike", "Quarry", "Rowan", "Saltmarsh", "Tamsin", "Upton",
          "Verity", "Wendover", "Yelland", "Ashby", "Birchley", "Corrie", "Dunmore", "Elmstead", "Farrow", "Glenrock",
          "Heathcote", "Ivel", "Jasper", "Kestrel", "Linden", "Marlow", "Nettlebed", "Oakham", "Penrose", "Quillon",
          "Redfern", "Sorrel", "Thorne", "Ullswater", "Valemont", "Wrenfield", "Yarrow", "Alder", "Bramble", "Cobalt",
          "Driftwood", "Ember", "Fable", "Garnet", "Hawthorn", "Indigo", "Juno", "Kelpie", "Lowther", "Meridian",
          "Nimbus", "Oriel", "Pellow", "Ravel", "Stratton", "Tidewell", "Umber", "Vantage", "Westcott", "Zephyr"]
_SECOND = ["Lane", "Foods", "Print", "Studio", "Dairy", "Labs", "Tours", "Analytics", "Joinery", "Dental", "Freight",
           "Books", "Farm", "Media", "Optics", "Cafe", "Florists", "Kilns", "Audio", "Bakes", "Marine", "Works",
           "Partners", "Supply", "Clinic", "Fitness", "Design", "Logistics", "Brewing", "Textiles", "Robotics",
           "Ceramics", "Interiors", "Surveys", "Pharmacy", "Outfitters", "Garage", "Nursery", "Archive", "Signs"]
_NAMESAKE_SUFFIX = [" Group", " & Co", " Holdings", " International", " UK"]

# ids the shared base world already uses
_TAKEN = {"C-104", "C-221", "C-305", "T-12", "INV-5498"}


class Ids:
    def __init__(self, rng: random.Random):
        self.rng, self.used = rng, set(_TAKEN)
        self.names: set[str] = set()

    def new(self, prefix: str, lo: int, hi: int) -> str:
        while True:
            i = f"{prefix}{self.rng.randint(lo, hi)}"
            if i not in self.used:
                self.used.add(i)
                return i

    def customer(self) -> str:
        return self.new("C-", 1000, 9999)

    def ticket(self) -> str:
        return self.new("T-", 100, 9999)

    def invoice(self) -> str:
        return self.new("INV-", 6000, 9999)

    def name(self) -> str:
        while True:
            n = f"{self.rng.choice(_FIRST)} {self.rng.choice(_SECOND)}"
            if n not in self.names and not any(n.startswith(m) or m.startswith(n) for m in self.names):
                self.names.add(n)
                return n

    def namesake(self, of: str) -> str:
        n = of + self.rng.choice(_NAMESAKE_SUFFIX)
        self.names.add(n)
        return n


@dataclass
class Acct:
    cid: str
    row: dict[str, Any]                  # the customer record as it starts
    ticket: str | None = None            # the account's ticket for this task
    subject: str | None = None
    invoice: str | None = None
    inv_amount: float | None = None
    prior_refund: float = 0.0            # refunded on the invoice before the task starts
    billed: int | None = None            # seats billing charges for, where that differs from the record
    charged: dict[str, int] = field(default_factory=dict)   # seat lines on the invoice by kind, where it has lines
    tags: set[str] = field(default_factory=set)   # "closed", "namesake", "excluded", ...

    @property
    def seats(self) -> int:
        return self.row["seats"]

    @property
    def qty(self) -> int:
        """Seats a per-seat refund or notice is worked out on: the overcharged invoice lines where there are any,
        else the record."""
        return self.charged["seats"] + self.charged.get("added", 0) if self.charged else self.seats

    @property
    def bseats(self) -> int:
        return self.billed if self.billed is not None else self.row["seats"]
