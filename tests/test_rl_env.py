import json

import pytest

from reorgbench.oracle import oracle_factory
from reorgbench.rl import ReOrgEnv
from reorgbench.runtime import Episode
from reorgbench.tasks.registry import all_tasks

TASKS = list(all_tasks().values())


def drive(env, factory):
    """Play every controlled turn with policies built from the same factory the oracle uses."""
    policies, turn, steps = {}, env.reset(), 0
    reward = done = None
    while turn is not None:
        p = policies.setdefault(turn.agent.id, factory(turn.agent))
        turn, reward, done, info = env.step(p.act(turn.observation))
        steps += 1
    return reward, done, steps


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
@pytest.mark.parametrize("who", ["all", "orchestrator"])
def test_env_reproduces_a_normal_run(task, who):
    controlled = (lambda i: True) if who == "all" else (lambda i: i.role == "orchestrator")
    env = ReOrgEnv(task, controlled=controlled, others=oracle_factory(task))
    reward, done, steps = drive(env, oracle_factory(task))
    ref = Episode(task, oracle_factory(task)).run()
    assert done and reward == 1.0 and steps > 0
    assert json.dumps(env.result().events) == json.dumps(ref.events)


def test_uncontrolled_agents_need_a_policy():
    task = TASKS[1]
    env = ReOrgEnv(task, controlled=lambda i: i.role == "orchestrator")
    turn = env.reset()
    with pytest.raises(ValueError):
        env.step({"type": "spawn", "role": "finance", "brief": "", "intro": []})
        while turn is not None:
            turn, *_ = env.step({"type": "noop"})


def test_step_after_done_raises():
    task = TASKS[0]
    env = ReOrgEnv(task)
    env.reset()
    _, reward, done, _ = env.step({"type": "finish", "answer": ""})
    assert done and reward == 0.0
    with pytest.raises(RuntimeError):
        env.step({"type": "noop"})
