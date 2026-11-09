"""The Claude call itself needs a key; what we do with its reply does not."""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from hwplot import solve
from hwplot.page import PX_PER_MM


def fake_client(reply: dict, stop_reason="end_turn"):
    sent = {}

    @contextmanager
    def stream(**kwargs):
        sent.update(kwargs)
        msg = SimpleNamespace(
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=2500, output_tokens=7000),
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=json.dumps(reply))],
        )
        yield SimpleNamespace(get_final_message=lambda: msg)

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream))), sent


def test_reply_becomes_answers_in_page_millimetres(tmp_path):
    reply = {
        "notes": "",
        "answers": [{"id": "1", "question": "12 x 7", "answer": "84", "kind": "write",
                     "x": 600, "y": 120, "w": 300, "h": 60, "confidence": "high"}],
    }
    client, sent = fake_client(reply)
    answers, _, usage = solve.solve(np.full((100, 80, 3), 255, np.uint8), "0123456789", client)
    assert answers[0].answer == "84"
    assert answers[0].box == pytest.approx((600 / PX_PER_MM, 120 / PX_PER_MM, 300 / PX_PER_MM, 60 / PX_PER_MM))
    assert sent["model"] == solve.MODEL == "claude-sonnet-5-5"
    assert sent["fallbacks"] == "default"
    assert usage.dollars == pytest.approx((2500 * 2 + 7000 * 10) / 1e6)
    assert "0123456789" in sent["messages"][0]["content"][1]["text"]

    path = tmp_path / "answers.json"
    solve.save(str(path), answers, "n")
    again, notes = solve.load(str(path))
    assert again == answers and notes == "n"


def test_refusal_is_an_error_not_an_empty_sheet():
    client, _ = fake_client({}, stop_reason="refusal")
    with pytest.raises(RuntimeError):
        solve.solve(np.full((10, 10, 3), 255, np.uint8), "a", client)


def test_haiku_is_not_sent_a_fallback_it_does_not_support():
    reply = {"notes": "", "answers": []}
    client, sent = fake_client(reply)
    solve.solve(np.full((10, 10, 3), 255, np.uint8), "a", client, model="claude-haiku-5-5")
    assert sent["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in sent and "betas" not in sent


def test_unknown_model_is_refused_before_any_call():
    client, sent = fake_client({"notes": "", "answers": []})
    with pytest.raises(ValueError):
        solve.solve(np.full((10, 10, 3), 255, np.uint8), "a", client, model="gpt-4")
    assert not sent
