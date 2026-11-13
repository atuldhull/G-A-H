"""End-to-end loop with a scripted fake model (no network)."""

import pytest

from crocodile import services
from crocodile.agent_types import ChatResult, ToolCallReq, Usage
from crocodile.loop import ALL_FLAGS, Agent

NO_REWIND = ALL_FLAGS - {"rewind"}


class FakeEgress:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools, *, session, tier, max_tokens=4096, temperature=0.0):
        self.calls.append((messages, tier))
        step = self.script.pop(0)
        calls = [ToolCallReq(f"c{len(self.calls)}_{i}", n, a) for i, (n, a) in enumerate(step)]
        return ChatResult("PLAN: read; fix" if len(self.calls) == 1 else "", calls,
                          Usage(1000, 50, 800 if len(self.calls) > 1 else 0), f"fake-{tier}")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    r = tmp_path / "repo"
    r.mkdir()
    (r / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (r / "calc_test.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                                    encoding="utf-8")
    yield r
    services.reset()


def _agent(repo, script, **kw):
    fake = FakeEgress(script)
    services.reset()
    services.override("egress", fake)
    a = Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="auto", **kw)
    return a, fake


def test_solves_and_stops_on_green(repo):
    a, fake = _agent(repo, [
        [("read", {"path": "calc.py"})],
        [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})],
    ])
    r = a.run()
    assert r.solved and r.status == "SOLVED"
    assert len(fake.calls) == 2            # no extra "double-check" turn after green
    assert "a + b" in (repo / "calc.py").read_text()
    first_user = fake.calls[0][0][1]["content"]
    first_user = first_user if isinstance(first_user, str) else first_user[0]["text"]
    assert "failed" in first_user           # reproduce-first: baseline failures shown up front
    assert fake.calls[0][0][-1]["content"].startswith("[TASK STATE]")   # pinned state last


def test_edit_requires_read_first(repo):
    a, _ = _agent(repo, [
        [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})],
        [("finish", {"summary": "gave up"})],
        [("finish", {"summary": "gave up"})],
    ], flags={"ladder", "stop_green", "gate"})
    r = a.run()
    assert not r.solved
    assert "a - b" in (repo / "calc.py").read_text()
    first_tool = next(m for m in a.history if m["role"] == "tool")["content"]
    assert "not read yet" in first_tool and "return a - b" in first_tool   # content handed back


def test_preload_puts_small_sources_in_first_prompt(repo):
    a, fake = _agent(repo, [
        [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})],
    ])
    r = a.run()
    assert r.solved and len(fake.calls) == 1        # no read turn needed


def test_thrash_escalates_to_strong(repo):
    bad = {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a * b"}]}
    bad2 = {"path": "calc.py", "edits": [{"search": "return a * b", "replace": "return a * b + 0"}]}
    good = {"path": "calc.py", "edits": [{"search": "return a * b + 0", "replace": "return a + b"}]}
    a, fake = _agent(repo, [
        [("read", {"path": "calc.py"})], [("edit", bad)], [("edit", bad2)], [("edit", good)],
    ], flags=NO_REWIND)
    r = a.run()
    assert r.solved and r.escalations == 1
    assert fake.calls[-1][1] == "strong" and fake.calls[0][1] == "cheap"


def test_all_off_twin_runs(repo):
    a, fake = _agent(repo, [
        [("read", {"path": "calc.py"})],
        [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})],
        [("finish", {"summary": "done"})],
    ], flags=set())
    r = a.run()
    assert r.status == "UNVERIFIED (no tests)" and len(fake.calls) == 3


def test_path_escape_blocked(repo):
    a, _ = _agent(repo, [[("read", {"path": "../secret.txt"})], [("finish", {"summary": "x"})]])
    a.run()
    tool_msgs = [m for m in a.history if m["role"] == "tool"]
    assert "outside the repo" in tool_msgs[0]["content"]


def test_text_tool_calls_recovered():
    from crocodile.loop import text_tool_calls
    text = ('PLAN: a; b\n\n{"name": "read", "arguments": {"path": "x.py"}}\n'
            '<tool_call>{"name": "search", "arguments": "{\\"pattern\\": \\"f\\"}"}</tool_call>\n'
            '{"name": "rm_rf", "arguments": {}}\n{"name": "edit", "arguments": {"path": "x.py", "edits": [')
    calls = text_tool_calls(text)
    assert [c.name for c in calls] == ["read", "search"]      # unknown tool and truncated JSON dropped
    assert calls[1].arguments == {"pattern": "f"}


def test_text_only_reply_gets_one_nudge(repo):
    class TextOnce(FakeEgress):
        def chat(self, messages, tools, **kw):
            r = super().chat(messages, tools, **kw)
            if len(self.calls) == 1:
                r.tool_calls = []
                r.text = "I will fix it."
            return r
    fake = TextOnce([[], [("read", {"path": "calc.py"})],
                     [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})]])
    services.reset()
    services.override("egress", fake)
    r = Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="auto").run()
    assert r.solved and len(fake.calls) == 3


def test_fit_masks_when_window_small(repo, monkeypatch):
    import crocodile.loop as L
    monkeypatch.setitem(L.CTX_WINDOW, "cheap", 9000)
    big = "x = 1\n" * 3000
    (repo / "big.py").write_text(big, encoding="utf-8")
    a, fake = _agent(repo, [
        [("read", {"path": "big.py", "start": 1, "end": 1000})],
        [("read", {"path": "calc.py"})],
        [("edit", {"path": "calc.py", "edits": [{"search": "return a - b", "replace": "return a + b"}]})],
    ])
    r = a.run()
    assert r.solved
    assert any("masked" in str(m["content"]) for m in a.history if m["role"] == "tool")


def test_already_applied_edit_is_explained(repo):
    a, _ = _agent(repo, [
        [("edit", {"path": "calc.py", "edits": [{"search": "def add(a, b):", "replace": "def add(a, b):  # x"}]})],
        [("edit", {"path": "calc.py", "edits": [{"search": "def add(a, b):\n    return 1", "replace": "def add(a, b):  # x"}]})],
        [("finish", {"summary": "x"})], [("finish", {"summary": "x"})],
    ], flags=NO_REWIND)
    a.run()
    tool_msgs = [m["content"] for m in a.history if m["role"] == "tool"]
    assert "already applied" in tool_msgs[1]


def test_text_tool_calls_lenient_json():
    from crocodile.loop import text_tool_calls
    raw_nl = '```json\n{"name": "edit", "arguments": {"path": "p.py", "edits": [{"search": "pass", "replace": "x = 1\n\treturn x"}]}}\n```'
    calls = text_tool_calls(raw_nl)
    assert calls and calls[0].arguments["edits"][0]["replace"] == "x = 1\n\treturn x"
    bad_esc = r'''{"name": "edit", "arguments": {"path": "p.py", "edits": [{"search": "pass", "replace": "s = \'a\'"}]}}'''
    calls = text_tool_calls(bad_esc)
    assert calls and calls[0].arguments["edits"][0]["replace"] == "s = 'a'"


def test_write_tool_whole_file(repo):
    a, fake = _agent(repo, [
        [("write", {"path": "calc.py", "content": "def add(a, b):\n    return a + b"})],
    ])
    r = a.run()
    assert r.solved and len(fake.calls) == 1
    assert (repo / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    intro = fake.calls[0][0][1]["content"]
    intro = intro if isinstance(intro, str) else intro[0]["text"]
    assert "Tests that must pass" in intro and "assert add(2, 3) == 5" in intro


def test_text_tool_calls_unterminated_string():
    from crocodile.loop import text_tool_calls
    t = ('```json\n{\n  "name": "write",\n  "arguments": {\n    "path": "p.py",\n'
         '    "content": "def f():\n    return f\\"x\\"\n  }\n}\n```')
    calls = text_tool_calls(t)
    assert calls and calls[0].arguments["content"] == 'def f():\n    return f"x"'


def test_salvage_write_with_unescaped_quotes():
    from crocodile.loop import text_tool_calls
    t = ('```json\n{\n  "name": "write",\n  "arguments": {\n    "path": "p.py",\n'
         '    "content": "x = f\'{a + " " if a else ""}\'\nprint(x)"\n  }\n}\n```')
    calls = text_tool_calls(t)
    assert calls and calls[0].arguments == {"path": "p.py", "content": "x = f'{a + \" \" if a else \"\"}'\nprint(x)"}
