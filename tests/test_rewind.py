"""Progress-gated rewind + counterfactual savings."""

from test_loop import _agent, repo  # noqa: F401  (pytest fixture re-export)

from crocodile.engine.savings import Savings


def _text(msg):
    c = msg["content"]
    return c if isinstance(c, str) else c[0]["text"]


TWO_TESTS = ("from calc import add, sub\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
             "def test_sub():\n    assert sub(5, 3) == 2\n")
START = "def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a - b\n"   # 1 of 2 passing
WORSE = {"path": "calc.py", "content": "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a * b"}
SAME = {"path": "calc.py", "content": "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a - b"}
GOOD = {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b"}


def _two(repo):  # noqa: F811
    (repo / "calc_test.py").write_text(TWO_TESTS, encoding="utf-8")
    (repo / "calc.py").write_text(START, encoding="utf-8")


def test_rewind_undoes_regression_and_cuts_history(repo):  # noqa: F811
    _two(repo)
    a, fake = _agent(repo, [[("write", WORSE)], [("write", GOOD)]])
    r = a.run()
    assert r.solved and r.rewinds == 1
    second_call = fake.calls[1][0]
    assert [m["role"] for m in second_call].count("assistant") == 0   # failed attempt cut from history
    note = _text(second_call[-2])
    assert "[rewind #1]" in note and "a * b" in note                  # ...its diff survives as a note
    assert "already tried and FAILED" in _text(second_call[-1])       # attempt memory in pinned state
    assert r.savings.get("rewind", 0) > 0 and r.savings.get("stop_green", 0) > 0


def test_equal_score_attempt_is_kept_not_rewound(repo):  # noqa: F811
    _two(repo)
    a, fake = _agent(repo, [[("write", SAME)], [("write", GOOD)]])
    r = a.run()
    assert r.solved and r.rewinds == 0                                 # sideways move stayed
    assert "[auto-check" in _text(fake.calls[1][0][-2])                # with its feedback in context


def test_rewind_restores_files(repo):  # noqa: F811
    _two(repo)
    a, _ = _agent(repo, [[("write", WORSE)], [("finish", {"summary": "x"})], [("finish", {"summary": "x"})]])
    a.run()
    assert (repo / "calc.py").read_text() == START


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


def test_idle_switch_note_says_edit_now_with_current_code(repo):  # noqa: F811
    _two(repo)
    reads = [[("search", {"pattern": f"x{i}"})] for i in range(4)]       # 4 turns without an edit
    a, fake = _agent(repo, [[("write", SAME)], *reads, [("write", GOOD)]])
    r = a.run()
    assert r.solved
    note = next(_text(m) for call in fake.calls for m in call[0]
                if m["role"] == "user" and "strategy switch" in _text(m))
    assert "Make your best edit NOW" in note and "re-read the failing test" not in note
    assert "calc_test.py::test_add" in note                              # failing tests re-attached
    assert "--- calc.py (current content) ---" in note and "a * b" in note   # current code re-attached


def test_precision_hint_when_nearly_all_pass(repo):  # noqa: F811
    (repo / "calc_test.py").write_text(
        "from calc import add, sub, mul, neg\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_sub():\n    assert sub(5, 3) == 2\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n\n\n"
        "def test_neg():\n    assert neg(2) == -2\n", encoding="utf-8")
    body = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n"
    (repo / "calc.py").write_text(body + "\n\ndef neg(a):\n    return 0\n", encoding="utf-8")
    nearly = {"path": "calc.py", "content": body + "\n\ndef neg(a):\n    return a\n"}
    done = {"path": "calc.py", "content": body + "\n\ndef neg(a):\n    return -a\n"}
    a, fake = _agent(repo, [[("write", nearly)], [("write", done)]])
    assert a.run().solved
    feedback = _text(fake.calls[1][0][-2])
    assert "[close: 3 of 4 tests passed" in feedback and "use `edit`" in feedback


def test_no_precision_hint_when_far_from_done(repo):  # noqa: F811
    _two(repo)
    a, fake = _agent(repo, [[("write", SAME)], [("write", GOOD)]])
    a.run()
    assert "[close:" not in _text(fake.calls[1][0][-2])                # 1 of 2 passing: not "close"


def test_edit_accepts_string_and_python_literal_edits(repo):  # noqa: F811
    from crocodile.tools.edit import _normalize_edits

    want = [{"search": "a - b", "replace": "a + b"}]
    assert _normalize_edits('[{"search": "a - b", "replace": "a + b"}]') == want      # JSON string
    assert _normalize_edits("[{'search': 'a - b', 'replace': 'a + b'}]") == want      # Python literal
    assert _normalize_edits({"search": "a - b", "replace": "a + b"}) == want          # single object
    assert _normalize_edits("__import__('os').system('x')") == "__import__('os').system('x')"  # never run
    a, _ = _agent(repo, [[("read", {"path": "calc.py"})],
                         [("edit", {"path": "calc.py",
                                    "edits": "[{'search': 'return a - b', 'replace': 'return a + b'}]"})]])
    assert a.run().solved                                                            # end to end
