"""Progress-gated rewind + counterfactual savings."""

from test_loop import _agent, repo  # noqa: F401  (pytest fixture re-export)

from crocodile.engine.savings import Savings


def _text(msg):
    c = msg["content"]
    return c if isinstance(c, str) else c[0]["text"]


def test_rewind_undoes_failed_attempt_and_cuts_history(repo):  # noqa: F811
    bad = {"path": "calc.py", "content": "def add(a, b):\n    return a * b"}
    good = {"path": "calc.py", "content": "def add(a, b):\n    return a + b"}
    a, fake = _agent(repo, [[("write", bad)], [("write", good)]])
    r = a.run()
    assert r.solved and r.rewinds == 1
    second_call = fake.calls[1][0]
    assert [m["role"] for m in second_call].count("assistant") == 0   # failed attempt cut from history
    note = _text(second_call[-2])
    assert "[rewind #1]" in note and "a * b" in note                  # ...its diff survives as a note
    assert "already tried and FAILED" in _text(second_call[-1])       # attempt memory in pinned state
    assert r.savings.get("rewind", 0) > 0 and r.savings.get("stop_green", 0) > 0


def test_rewind_restores_files(repo):  # noqa: F811
    bad = {"path": "calc.py", "content": "def add(a, b):\n    return a * b"}
    a, _ = _agent(repo, [[("write", bad)], [("finish", {"summary": "x"})], [("finish", {"summary": "x"})]])
    a.run()
    assert (repo / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


def test_progress_is_committed_not_rewound(repo):  # noqa: F811
    (repo / "calc_test.py").write_text(
        "from calc import add, sub\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_sub():\n    assert sub(5, 3) == 2\n", encoding="utf-8")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a + b\n",
                                  encoding="utf-8")
    half = {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b"}
    full = {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b"}
    a, fake = _agent(repo, [[("write", half)], [("write", full)]])
    r = a.run()
    assert r.solved and r.rewinds == 0 and r.checkpoints == 1
    assert "[auto-check" in _text(fake.calls[1][0][-2])                # progress kept in context


def test_savings_counterfactual_math():
    s = Savings()
    s.carried("gate", 100, 2)       # kept out at step 2 of 5 -> would ride along on calls 3,4,5
    s.once("stop_green", 500, 5)
    rep = s.report(total_calls=5, cached_tokens=1000)
    assert rep["gate"] == 300 and rep["stop_green"] == 500 and rep["cache (90% discount on cached input)"] == 900


def test_preload_follows_test_imports(tmp_path, monkeypatch):
    from test_loop import FakeEgress

    from crocodile import services
    from crocodile.loop import Agent
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    r = tmp_path / "repo"
    (r / "pkg").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (r / "pkg" / "mathx.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (r / "tests" / "test_mathx.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
        "from pkg.mathx import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    fake = FakeEgress([[("edit", {"path": "pkg/mathx.py",
                                  "edits": [{"search": "return a - b", "replace": "return a + b"}]})]])
    services.reset()
    services.override("egress", fake)
    res = Agent(r, "Fix add.", oracle=["tests/test_mathx.py"], approve_mode="ask").run()
    services.reset()
    assert res.solved and len(fake.calls) == 1          # no search/read turns: the import pointed at it
