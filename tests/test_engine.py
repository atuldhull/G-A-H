import pytest

from crocodile.engine.gate import Spill, gate, head_tail
from crocodile.engine.masking import maybe_mask
from crocodile.engine.readcache import ReadCache
from crocodile.engine.thrash import Thrash, failure_sig
from crocodile.tools.edit import NoMatch, apply_edit, locate

SRC = "def f(x):\n    if x:\n        return 1\n    return 2\n\n\ndef g():\n    pass\n"


def test_exact_match():
    new, m = apply_edit(SRC, "        return 1", "        return 10")
    assert m.stage == "exact" and "return 10" in new and new.endswith("\n")


def test_whitespace_match_reindents():
    new, m = apply_edit(SRC, "if x:\n    return 1", "if x:\n    return 3")
    assert m.stage == "whitespace"
    assert "    if x:\n        return 3\n" in new


def test_ambiguous_exact_is_rejected():
    with pytest.raises(NoMatch, match="2 places"):
        locate("a\nb\na\n", "a")


def test_elision():
    new, m = apply_edit(SRC, "def f(x):\n...\n    return 2", "def f(x):\n    return 0")
    assert m.stage == "elision" and new.startswith("def f(x):\n    return 0\n\n")


def test_fuzzy_single_candidate():
    _, m = apply_edit(SRC, "def g():\n    pas", "def g():\n    return 1")
    assert m.stage == "fuzzy" and m.score >= 0.9


def test_did_you_mean():
    with pytest.raises(NoMatch, match="Did you mean"):
        locate(SRC, "def f(y):\n    if y and z:\n        return 11")


def test_crlf_preserved():
    new, _ = apply_edit("a\r\nb\r\n", "b", "c")
    assert new == "a\r\nc\r\n"


def test_gate_small_passthrough():
    g = gate("hello\n", 0, Spill(None))
    assert g.spill is None and "hello" in g.shown and "[exit 0]" in g.shown


def test_gate_spills_and_keeps_errors():
    lines = [f"noise line {i}" for i in range(3000)]
    lines[1500] = "ValueError: the important one"
    s = Spill(None)
    g = gate("\n".join(lines), 1, s)
    assert g.spill == "out:1" and "ValueError: the important one" in g.shown
    assert g.shown_tokens < g.raw_tokens / 5
    assert s.get("out:1").count("\n") == 2999


def test_gate_redacts_secrets():
    g = gate("key sk-abcdefghijklmnopqrstuvwxyz123456\n", 0, Spill(None))
    assert "sk-abc" not in g.shown


def test_head_tail_is_tail_biased():
    out = head_tail([str(i) for i in range(1000)], 100, 100_000)
    assert out[0] == "0" and out[-1] == "999" and sum(1 for x in out if x.isdigit() and int(x) > 900) > 70


def test_readcache_unchanged_and_diff():
    rc = ReadCache()
    rc.record("a.py", (1, 3), "x\ny\nz", 2, 5)
    assert "turn-2 read result" in rc.lookup("a.py", (1, 3), "x\ny\nz", 4, set())
    big = "\n".join(f"line {i}" for i in range(100))
    rc.record("b.py", (1, 100), big, 1, 6)
    assert "diff" in rc.lookup("b.py", (1, 100), big.replace("line 50", "LINE 50"), 3, set())
    assert rc.lookup("a.py", (1, 3), "x\ny\nz", 4, {5}) is None     # masked -> resend


def test_masking_batches():
    hist, meta = [], []
    for t in range(1, 15):
        hist.append({"role": "tool", "content": "x" * 4000})
        meta.append({"turn": t, "tool": "read", "spill": None, "exit": None})
    masked: set[int] = set()
    assert maybe_mask(hist, meta, 12, masked) == 0          # 1 old message: below the batch threshold
    saved = maybe_mask(hist, meta, 20, masked)
    assert saved > 6000 and "masked" in hist[0]["content"] and "masked" not in hist[-1]["content"]


def test_thrash_escalate_then_stop():
    t = Thrash()
    sig = failure_sig(["t::a"], "AssertionError: 1 != 2 at line 40")
    t.record_failure(sig)
    t.record_failure(failure_sig(["t::a"], "AssertionError: 1 != 2 at line 41"))
    assert t.check() == "escalate"
    t.record_failure(sig)
    t.record_failure(sig)
    assert t.check() == "stop_report"


def test_thrash_repeated_identical_call():
    t = Thrash()
    for _ in range(3):
        t.record_call("read", {"path": "a.py"})
    assert t.check() == "escalate" and "repeated" in t.reason


def test_whitespace_match_no_double_indent():
    src = "class A:\n    def f(self):\n        if x:\n            return 1\n"
    new, m = apply_edit(src, "if x:\n    return 1", "        if x:\n            return 2")
    assert m.stage == "whitespace"
    assert "        if x:\n            return 2\n" in new and "                if" not in new


def test_thrash_idle_after_first_edit():
    t = Thrash()
    t.record_turn(False, False)          # exploring before any edit is fine
    for _ in range(4):
        t.record_turn(False, True)
    assert t.check() is None
    t.record_turn(False, True)
    assert t.check() == "escalate" and "without an edit" in t.reason
