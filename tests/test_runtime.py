"""Harness rules, and the trivial-agent baselines that must fail."""

from helpers import errors, run_script

from reorgbench.tasks.hand import HAND_TASKS

T1 = HAND_TASKS["hand-01-onboarding-doc"]
T2 = HAND_TASKS["hand-02-double-charge"]
T3 = HAND_TASKS["hand-03-vendor-onboarding"]

FINISH = {"type": "finish", "answer": "done"}


def test_role_gating():
    res, _ = run_script(T1, {"orch": [{"type": "env", "tool": "repo.read", "args": {"path": "x"}}, FINISH]})
    assert [e["payload"]["kind"] for e in errors(res)] == ["gating"]


def test_malformed_actions_become_errors():
    res, _ = run_script(T1, {"orch": [
        "not an action",
        {"type": "teleport"},
        {"type": "env", "tool": "docs.read", "args": {"wrong": 1}},
        {"type": "env", "tool": "no.such_tool", "args": {}},
        FINISH,
    ]})
    assert [e["payload"]["kind"] for e in errors(res)] == ["malformed"] * 4
    assert res.actions_used == 5


def test_unknown_recipient_is_an_address_error():
    res, _ = run_script(T1, {"orch": [{"type": "msg", "to": ["a7"], "content": "hi"}, FINISH]})
    assert [e["payload"]["kind"] for e in errors(res)] == ["address"]


def test_spawn_depth_limit_and_brief_delivery():
    plans = {
        "orch": [{"type": "spawn", "role": "engineer", "brief": "hello", "intro": []}],
        "a1": [{"type": "spawn", "role": "analyst", "brief": "child", "intro": []}],
        "a2": [{"type": "spawn", "role": "legal", "brief": "grandchild", "intro": []}],
    }
    res, script = run_script(T1, plans)
    assert [e["payload"]["kind"] for e in errors(res)] == ["depth"]
    spawn_id = next(e["id"] for e in res.events if e["type"] == "spawn" and e["agent"] == "orch")
    assert script.seen["a1"][0].items[0] == {"kind": "brief", "content": "hello", "event": spawn_id}
    depths = {a["id"]: a["depth"] for a in res.agents}
    assert depths == {"orch": 0, "a1": 1, "a2": 2}
    # the orchestrator hears about the grandchild without inspecting
    notices = [i for o in script.seen["orch"] for i in o.items if i["kind"] == "spawn_notice"]
    assert notices and notices[0]["content"]["agent_id"] == "a2"


def test_role_outside_catalog_rejected():
    res, _ = run_script(T1, {"orch": [{"type": "spawn", "role": "orchestrator", "brief": "", "intro": []}, FINISH]})
    assert [e["payload"]["kind"] for e in errors(res)] == ["permission"]


def test_address_book_grows_from_messages():
    plans = {
        "orch": [
            {"type": "spawn", "role": "engineer", "brief": "", "intro": []},
            {"type": "spawn", "role": "finance", "brief": "", "intro": []},
            {"type": "noop"},
            {"type": "msg", "to": ["a1"], "content": "finance is a2"},
        ],
        # a1 doesn't know a2 until the orchestrator names it
        "a1": [{"type": "msg", "to": ["a2"], "content": "too early"}, {"type": "noop"}, {"type": "noop"},
               {"type": "msg", "to": ["a2"], "content": "hello"}],
    }
    res, script = run_script(T1, plans)
    assert [e["payload"]["kind"] for e in errors(res)] == ["address"]
    assert any(e["type"] == "msg" and e["agent"] == "a1" and e["recipients"] == ["a2"] for e in res.events)


def test_kill_gives_one_message_only_turn():
    plans = {
        "orch": [{"type": "spawn", "role": "engineer", "brief": "", "intro": []},
                 {"type": "noop"}, {"type": "kill", "target": "a1"}],
        "a1": [{"type": "noop"}, {"type": "env", "tool": "repo.list", "args": {}},
               {"type": "msg", "to": ["orch"], "content": "never sent"}],
    }
    res, script = run_script(T1, plans)
    # a1 acts in round 2, is killed in round 3 before its turn, gets round 4 to relay, then is gone
    assert [e["payload"]["kind"] for e in errors(res)] == ["relay_only"]
    a1 = next(a for a in res.agents if a["id"] == "a1")
    assert a1["status"] == "dead" and a1["end_round"] == 4
    last = script.seen["a1"][-1]
    assert last.relaying and "kill_notice" in [i["kind"] for i in last.items]
    assert len(script.seen["a1"]) == 2


def test_inspect_only_descendants():
    plans = {
        "orch": [{"type": "spawn", "role": "engineer", "brief": "", "intro": []},
                 {"type": "spawn", "role": "finance", "brief": "", "intro": []}, {"type": "inspect", "target": "a1"}],
        "a2": [{"type": "inspect", "target": "a1"}],
    }
    res, script = run_script(T1, plans)
    assert [e["payload"]["kind"] for e in errors(res)] == ["permission"]
    assert any(i["kind"] == "inspection" for o in script.seen["orch"] for i in o.items)


def test_finish_is_intercepted_while_a_change_is_pending():
    res, script = run_script(T2, {"orch": [FINISH, FINISH]})
    assert res.interventions == [{"id": "add-payco-po", "round": 1, "fired_by": "finish_intercept"}]
    assert any(i["kind"] == "intervention" for o in script.seen["orch"] for i in o.items)
    assert res.stop_reason == "finished" and res.phase == 1


def test_round_cap_is_a_failure():
    res, _ = run_script(T1, {})
    assert res.stop_reason == "round_cap" and res.rounds == T1.budgets.round_cap
    assert not res.verdict.success


# ---- degenerate agents must fail every task (ABC R.13) ------------------------------------------

def test_do_nothing_fails_everywhere():
    for t in HAND_TASKS.values():
        res, _ = run_script(t, {"orch": [FINISH] * 5})
        assert not res.verdict.success, t.id


def test_hire_everyone_and_finish_fails():
    for t in HAND_TASKS.values():
        hires = [{"type": "spawn", "role": r, "brief": "do your job", "intro": []} for r in t.catalog]
        res, _ = run_script(t, {"orch": hires + [FINISH] * 5})
        assert not res.verdict.success, t.id


def test_goal_change_can_write_to_the_world():
    import dataclasses

    from reorgbench.oracle import oracle_factory
    from reorgbench.runtime import Episode

    iv = dataclasses.replace(T2.interventions[0], world_effects={
        "tickets/T-18": {"subject": "Re: charged twice", "status": "open", "customer_id": "C-104", "body": "Any update?"}})
    task = dataclasses.replace(T2, interventions=[iv])
    res = Episode(task, oracle_factory(task)).run()
    ev = next(e for e in res.events if e["type"] == "intervention")
    assert ev["writes"] == ["tickets/T-18"]
    assert res.world.objects["tickets/T-18"]["written_by"] == ev["id"]
    assert res.verdict.success


def test_fallback_round_fires_when_trigger_never_reached():
    res, _ = run_script(T3, {})
    assert res.interventions == [{"id": "cancel-legal", "round": 15, "fired_by": "fallback_round"}]
