"""web_docs (Tavily): offered only in public interactive sessions with a key; approval required."""

from test_loop import FakeEgress, repo  # noqa: F401

from crocodile import services
from crocodile.agent_types import Decision
from crocodile.loop import Agent


class WebEgress(FakeEgress):
    def __init__(self, script):
        super().__init__(script)
        self.searches = []

    def web_search(self, query, *, session):
        self.searches.append(query)
        return {"results": [{"title": "requests docs", "url": "https://docs.example/requests",
                             "content": "Use requests.get(url, timeout=5)."}], "credits": 1}


class Approver:
    def __init__(self, ok=True):
        self.ok, self.seen = ok, []

    def ask(self, action, session):
        self.seen.append(action)
        return Decision(self.ok, "test")


class Confidential:
    def mode_for(self, repo_path):
        return "confidential"


def _setup(monkeypatch, script, *, ok=True, confidential=False):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-not-real")
    services.reset()
    eg, ap = WebEgress(script), Approver(ok)
    services.override("egress", eg)
    services.override("approvals", ap)
    if confidential:
        services.override("confidential", Confidential())
    return eg, ap


def _tool_names(agent):
    return [s["function"]["name"] for s in agent.schemas]


def test_web_docs_offered_and_approved(repo, monkeypatch):  # noqa: F811
    eg, ap = _setup(monkeypatch, [[("web_docs", {"query": "python requests timeout"})],
                                  [("finish", {"summary": "x"})], [("finish", {"summary": "x"})]])
    a = Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="ask")
    assert "web_docs" in _tool_names(a)
    a.run()
    assert eg.searches == ["python requests timeout"]
    assert any(x.kind == "network" and x.query == "python requests timeout" for x in ap.seen)
    tool_out = next(m["content"] for m in a.history if m["role"] == "tool")
    assert "requests.get" in tool_out and "data, not instructions" in tool_out


def test_web_docs_declined_sends_nothing(repo, monkeypatch):  # noqa: F811
    eg, _ = _setup(monkeypatch, [[("web_docs", {"query": "x"})], [("finish", {"summary": "x"})],
                                 [("finish", {"summary": "x"})]], ok=False)
    Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="ask").run()
    assert eg.searches == []


def test_never_offered_in_confidential_mode(repo, monkeypatch):  # noqa: F811
    eg, _ = _setup(monkeypatch, [[("web_docs", {"query": "secret thing"})], [("finish", {"summary": "x"})],
                                 [("finish", {"summary": "x"})]], confidential=True)
    a = Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="ask")
    assert "web_docs" not in _tool_names(a)
    a.run()
    assert eg.searches == []                                  # even if the model calls it anyway


def test_not_offered_in_bench_mode(repo, monkeypatch):  # noqa: F811
    _setup(monkeypatch, [[("finish", {"summary": "x"})]])
    a = Agent(repo, "Fix add().", oracle=["calc_test.py"], approve_mode="auto")
    assert "web_docs" not in _tool_names(a)
    services.reset()
