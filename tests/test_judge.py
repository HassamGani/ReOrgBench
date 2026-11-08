import json

from reorgbench.gen.units import set_judge, still_told
from reorgbench.judge import Judge, question

TELL = "Your new monthly price is $988 from 1 December. Change reference: CHG-11111. Account: C-2026."
HOLD = "Please disregard our earlier message for now: the price change is on hold for your account."


def test_without_a_judge_the_rules_decide():
    set_judge(None)
    assert still_told(True, [TELL, HOLD], [988.0]) is True


def test_a_plain_notice_never_reaches_the_judge():
    asked = []
    set_judge(lambda *a: asked.append(a) or False)
    try:
        assert still_told(True, [TELL], [988.0], (), "C-2026") is True and asked == []
    finally:
        set_judge(None)


def test_a_ticket_with_a_hold_goes_to_the_judge():
    set_judge(lambda texts, values, olds, account: False)
    try:
        assert still_told(True, [TELL, HOLD], [988.0], (), "C-2026") is False
    finally:
        set_judge(None)


def test_an_unanswered_question_falls_back_to_the_rules_and_is_collected(tmp_path):
    j = Judge(tmp_path / "cache.json")
    set_judge(j)
    try:
        assert still_told(False, [TELL, HOLD], [988.0], (), "C-2026") is False
        assert len(j.pending) == 1
        n = j.write_pending(tmp_path / "q" / "questions.json")
        qid = json.loads((tmp_path / "q" / "questions.json").read_text())[0]["id"]
        (tmp_path / "a.json").write_text(json.dumps({qid: True}))
        j.load_answers(tmp_path / "a.json")
        assert n == 1 and still_told(False, [TELL, HOLD], [988.0], (), "C-2026") is True
        assert json.loads((tmp_path / "cache.json").read_text()) == {qid: True}
    finally:
        set_judge(None)


def test_a_backend_is_asked_once_per_question(tmp_path):
    calls = []
    j = Judge(tmp_path / "cache.json", lambda system, prompt: calls.append(prompt) or "NO")
    set_judge(j)
    try:
        for _ in range(3):
            assert still_told(True, [TELL, HOLD], [988.0], (), "C-2026") is False
        assert len(calls) == 1 and "C-2026" in calls[0] and "988" in calls[0]
    finally:
        set_judge(None)


def test_the_question_carries_everything_the_rubric_needs():
    q = question([TELL, HOLD], [988.0], [760.0], "C-2026")
    assert "C-2026" in q and "988" in q and "760" in q and "Reply 2" in q
