"""The sla-credit family: deterministic, solved by the oracle across tiers, and its messy seeds carry every
complication the other stories do."""

import pytest

from reorgbench.gen import TEMPLATES, Knobs, generate
from reorgbench.gen.build import build, run_oracle
from reorgbench.gen.units import is_retraction, told_and_not_retracted, told_value

TPL = TEMPLATES["sla-credit"]


def test_registered_as_a_public_family():
    assert TPL.split == "train" and set(TPL.pool) == {"CANCEL", "MODIFY", "RELAX", "ADD:credit", "ADD:close"}


def test_same_seed_same_task():
    a, b = generate("sla-credit", 9), generate("sla-credit", 9)
    assert a.initial_objects == b.initial_objects and a.budgets == b.budgets
    assert [p.goal for p in a.phases] == [p.goal for p in b.phases]
    assert [p.staffings for p in a.phases] == [p.staffings for p in b.phases]
    assert [(i.trigger.kind, i.trigger.params, i.fallback_round) for i in a.interventions] == \
        [(i.trigger.kind, i.trigger.params, i.fallback_round) for i in b.interventions]
    assert generate("sla-credit", 10).initial_objects != a.initial_objects


@pytest.mark.parametrize("seed,tier", [(7, "standard"), (1, "standard"), (10, "hard"), (8, "expert")])
def test_oracle_solves_seeds_of_every_tier(seed, tier):
    t = generate("sla-credit", seed)
    assert t.tier == tier
    res = run_oracle(t)
    assert res.verdict.success, res.verdict.checks
    assert [i["fired_by"] for i in res.interventions] == ["trigger"] * len(t.interventions)
    assert res.rounds <= t.budgets.round_cap and res.actions_used <= t.budgets.action_cap


def test_cancel_takes_partner_customers_out():
    t = generate("sla-credit", 7)
    assert "cancel" in t.tags and "relax" in t.tags
    cancel = next(i for i in t.interventions if i.id == "cancel")
    assert "partner channel" in cancel.text and "disregard" in cancel.text
    assert "excluded_tickets_consistent" in {c.id for c in t.phases[-1].checkpoints}


def test_look_alikes_are_out_of_scope():
    t, g = build(TPL, 3, Knobs(n=8, crew=1, changes=(), traps=3, code=False))
    kinds = {k: next(a for a in g.accts.values() if k in a.tags) for k in ("lookalike", "closed", "namesake")}
    assert kinds["lookalike"].row["cluster"] == g.story["spared"] and kinds["closed"].row["cluster"] in g.story["hit"]
    assert kinds["namesake"].row["name"].startswith(g.accts[g.cohort[0]].row["name"])
    assert not set(a.cid for a in kinds.values()) & set(g.cohort)
    assert all(f"db.customers/{a.cid}" in g.leave_alone and f"tickets/{a.ticket}" in g.leave_alone
               for a in kinds.values())
    report = t.initial_objects[f"docs/{g.story['doc']}"]["text"]
    assert g.story["spared"] in report and all(c in report for c in g.story["hit"])
    assert run_oracle(t).verdict.success


def test_messy_worlds_carry_the_complications():
    k = Knobs(n=24, crew=2, changes=("CANCEL", "MODIFY"), traps=4, code=True, budget=1.5, messy=True)
    t, g = build(TPL, 1, k)
    s, objs = g.story, t.initial_objects
    assert sum(1 for o in objs if o.startswith("db.customers/")) > 2.5 * len(g.cohort)
    by_contract = [c for c in g.held if c not in g.approved_out + g.leaving]
    assert by_contract and len(g.claims) > len(by_contract)          # some contract claims hold, some don't
    assert g.approved_out and g.not_approved and g.leaving and g.merged
    assert not set(g.held) & set(g.cohort)
    assert g.units["told"].tier_at is not None and "docs/sla-credit-schedule" in objs
    vals = [str(g.accts[c].row["cluster"]) for c in g.cohort]
    assert any(v != v.lower() for v in vals)                          # typed in different capitals
    assert any(v.lower() not in s["hit"] for v in vals)               # the CRM lags the placement log
    assert g.stale and g.holds
    report = objs[f"docs/{s['doc']}"]["text"]
    assert all(c in report for c in g.cohort + g.held + g.excluded)   # the tenant list is the source of truth
    assert not any(c in report for c in g.stale)
    assert not any(c in report for c, a in g.accts.items() if "lookalike" in a.tags or "namesake" in a.tags)
    assert "incident report" in objs["docs/operations-handbook"]["text"]
    assert run_oracle(generate("sla-credit", 1, k)).verdict.success


def test_goodwill_credit_is_for_this_outage():
    k = Knobs(n=16, crew=1, changes=("CANCEL", "ADD:credit"), traps=3, code=True, budget=1.5, messy=True)
    t, g = build(TPL, 2, k)
    inc = g.story["inc"]
    assert inc in t.interventions[-1].text and g.story["incident"] == inc
    this = [d for o, d in t.initial_objects.items() if o.startswith("ledger.entries/E-G")]
    assert this and all(d["note"].endswith(inc) for d in this)
    assert run_oracle(generate("sla-credit", 2, k)).verdict.success


def test_notices_read_as_telling_and_taking_back():
    t, g = build(TPL, 4, Knobs(n=6, crew=1, changes=("CANCEL",), traps=2, code=False))
    c = g.cohort[0]
    tell, back = TPL.tell_text(g, c, "46.0"), TPL.retract_text(g, c)
    assert told_value([tell], [46.0]) and told_and_not_retracted([tell], [46.0])
    assert told_and_not_retracted([TPL.tell_text(g, c, "100")], [46.0])   # a notice even with another figure
    assert is_retraction(back) and not told_and_not_retracted([tell, back], [46.0])
    assert told_value([tell, TPL.correct_text(g, c, "52.0")], [52.0])
