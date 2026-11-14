"""Part 1 -> Part 4 screens: snapshot, evidence-gated receipt, quote. Skipped without crocodile.ui."""

import pytest
from test_loop import _agent, repo  # noqa: F401

pytest.importorskip("crocodile.ui")

from crocodile import ui_bridge  # noqa: E402
from crocodile.ui import render_receipt, render_status  # noqa: E402


def test_solved_run_renders_solved(repo):  # noqa: F811
    a, _ = _agent(repo, [[("edit", {"path": "calc.py",
                                    "edits": [{"search": "return a - b", "replace": "return a + b"}]})]])
    a.run()
    text = render_receipt(ui_bridge.receipt(a))
    assert text.splitlines()[0].startswith("SOLVED")
    assert render_status(ui_bridge.snapshot(a))


def test_unsolved_run_is_not_called_solved(repo):  # noqa: F811
    a, _ = _agent(repo, [[("finish", {"summary": "x"})], [("finish", {"summary": "x"})],
                         [("finish", {"summary": "x"})]])
    a.run()
    assert not render_receipt(ui_bridge.receipt(a)).startswith("SOLVED")


def test_quote_runs_no_code(repo):  # noqa: F811
    q = ui_bridge.quote("Fix add() so the tests pass.", repo, ascii_only=True)
    assert q.rendering and isinstance(q.data, dict)


def test_no_tests_says_tests_not_run(tmp_path, monkeypatch):
    from test_loop import FakeEgress

    from crocodile import services
    from crocodile.loop import Agent
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    services.reset()
    services.override("egress", FakeEgress([[("finish", {"summary": "x"})], [("finish", {"summary": "x"})],
                                            [("finish", {"summary": "x"})]]))
    a = Agent(tmp_path, "Fix add.", approve_mode="auto")
    a.run()
    services.reset()
    assert render_receipt(ui_bridge.receipt(a)).startswith("TESTS NOT RUN")
