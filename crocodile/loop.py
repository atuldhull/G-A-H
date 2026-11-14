"""The agent loop (architecture/03). Phase machine, step cap, stop-on-green, escalation.

All policy (budget, privacy, approvals, command execution) lives behind crocodile.services; the
loop never decides policy or price itself.
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import prompt, services
from .agent_types import BudgetStop, Session, ToolCallReq, Usage
from .engine.gate import Spill, est_tokens
from .engine.ladder import verify
from .engine.masking import maybe_mask
from .engine.readcache import ReadCache
from .engine.rewind import Rewinder
from .engine.savings import Savings
from .engine.thrash import Thrash, failure_sig
from .state import TaskState
from .tools import SCHEMAS, TOOLS, RunCtx, dispatch
from .tools.base import SKIP_DIRS
from .tools.tests import TestRunner

ALL_FLAGS = {"cache", "gate", "readcache", "mask", "ladder", "stop_green", "thrash", "escalate", "preload",
             "rewind"}
STEP_CAP = 30
MAX_OUT = 4096
# Context window per tier (tokens). Local must match OLLAMA_CONTEXT_LENGTH or Ollama silently truncates.
CTX_WINDOW = {"strong": 200_000, "cheap": 200_000,
              "local": int(os.environ.get("OLLAMA_CONTEXT_LENGTH") or 32_768)}


@dataclass
class Receipt:
    session: str
    solved: bool
    status: str                      # SOLVED | SOLVED (partial suite) | STOPPED: <why> | UNVERIFIED
    steps: int = 0
    usage: Usage = field(default_factory=Usage)
    models: list[str] = field(default_factory=list)
    fallbacks: int = 0
    escalations: int = 0
    tokens_avoided: int = 0
    test_runs: int = 0
    wall_s: float = 0.0
    cost_usd: float | None = None
    stubs: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    rewinds: int = 0
    checkpoints: int = 0
    savings: dict = field(default_factory=dict)    # technique -> tokens saved (estimated, first-order)

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        d["usage"] = self.usage.__dict__.copy()
        return d


def state_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "crocodile" / "sessions"


def _brief_tree(root: Path, limit: int = 60) -> str:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= 2:
            dirnames[:] = []
        for f in sorted(filenames):
            out.append((Path(dirpath) / f).relative_to(root).as_posix())
            if len(out) >= limit:
                return "\n".join(out) + "\n..."
    return "\n".join(out)


_DEC = json.JSONDecoder(strict=False)        # allow raw newlines/tabs inside strings
_BAD_ESC = re.compile(r"\\(?![\"\\/bfnrtu])")  # \' \( etc. are invalid JSON escapes: drop the backslash


def text_tool_calls(text: str) -> list[ToolCallReq]:
    """Local models often write tool calls as JSON text (one or more objects, maybe in <tool_call>
    tags or code fences). Recover every {"name", "arguments"} object naming a known tool."""
    if not text or '"name"' not in text:
        return []
    out = _scan(text)
    if not out:
        out = _scan(_BAD_ESC.sub("", text))
    if not out:
        out = _salvage_write(text)
    return out


_ESC = re.compile(r'\\(u[0-9a-fA-F]{4}|["\\/bfnrt])')
_ESC_MAP = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def _salvage_write(text: str) -> list[ToolCallReq]:
    """Last resort for `write` calls whose content has unescaped quotes (invalid JSON):
    take the path, and everything between `"content": "` and the final quote before the closing braces."""
    m = re.search(r'"name"\s*:\s*"write".*?"path"\s*:\s*"([^"]+)".*?"content"\s*:\s*"', text, re.S)
    if not m:
        return []
    rest = text[m.end():]
    end = re.search(r'"\s*\}\s*\}?\s*(?:```)?\s*$', rest)
    if not end:
        return []
    raw = rest[: end.start()]
    content = _ESC.sub(lambda e: chr(int(e.group(1)[1:], 16)) if e.group(1)[0] == "u"
                       else _ESC_MAP[e.group(1)], raw)
    return [ToolCallReq("text_0", "write", {"path": m.group(1), "content": content})]


def _scan(text: str) -> list[ToolCallReq]:
    out: list[ToolCallReq] = []
    i = 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = _DEC.raw_decode(text, i)
        except json.JSONDecodeError:
            obj = _close_braces(text, i)
            if obj is None:
                i += 1
                continue
            end = len(text)
        i = end
        for o in obj if isinstance(obj, list) else [obj]:
            if not (isinstance(o, dict) and (o.get("name") in TOOLS or o.get("name") == "finish")):
                continue
            args = o.get("arguments") or o.get("parameters") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            out.append(ToolCallReq(f"text_{len(out)}", o["name"], args))
    return out


def _close_braces(text: str, i: int):
    """Repair a tool-call object that is only missing closing braces at the end (common local-model slip)."""
    if not re.match(r'\{\s*"name"\s*:', text[i:]):
        return None
    chunk = text[i:].rstrip().removesuffix("```").rstrip()
    body = chunk.rstrip("}] \n\t\r")             # also try: last string left unterminated
    candidates = [chunk + e for e in ("}", "}}", "}}}")]
    candidates += [body + '"' + e for e in ("}", "}}", "}]}}", "}}}")]
    for cand in candidates:
        try:
            obj, end = _DEC.raw_decode(cand)
        except json.JSONDecodeError:
            continue
        if end == len(cand):
            return obj
    return None

class Agent:
    def __init__(self, repo: Path, task: str, *, oracle: list[str] | None = None, full_suite: bool = False,
                 flags: set[str] | None = None, tier: str = "cheap", approve_mode: str = "ask",
                 step_cap: int = STEP_CAP, user: str = "default", on_event=None,
                 security_session=None):
        """security_session: a Part 3 ApprovalSession made by a trusted harness (e.g. for_bench)."""
        repo = repo.resolve()
        sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        sdir = state_root() / sid
        sdir.mkdir(parents=True, exist_ok=True)
        mode = services.get("confidential").mode_for(repo)
        self.s = Session(id=sid, repo=repo, mode=mode, user=user, approve_mode=approve_mode,  # type: ignore[arg-type]
                         flags=set(ALL_FLAGS if flags is None else flags), state_dir=sdir)
        if security_session is not None:
            bridge = services.get("approvals")
            if not hasattr(bridge, "bind_session"):
                raise RuntimeError("security_session given but Part 3 security is not installed")
            bridge.bind_session(self.s, security_session)
        from .tools import web as _web
        self.schemas = list(SCHEMAS)            # frozen for the session (part of the cache-stable prefix)
        if _web.enabled(self.s):                # Tavily: public + interactive + key present
            self.s.flags.add("_web")
            self.schemas = sorted(self.schemas + [_web.SCHEMA], key=lambda s: s["function"]["name"])
        self.ctx = RunCtx(self.s, Spill(sdir), ReadCache(), Thrash())
        self.ctx.tests = TestRunner(self.ctx, oracle)
        if full_suite:
            self.ctx.tests.full_targets = []
        self.ctx.oracle_files = {o.split("::")[0].replace("\\", "/") for o in (oracle or [])}
        self.state = TaskState(task=task, oracle=list(oracle or []),
                               tier="local" if mode == "confidential" else tier)
        self.step_cap = step_cap
        self.history: list[dict] = []
        self.meta: list[dict] = []
        self.r = Receipt(session=sid, solved=False, status="UNVERIFIED",
                         stubs=[n for n in ("egress", "journal", "approvals", "cmd", "confidential")
                                if services.is_stub(n)],
                         flags=sorted(self.s.flags))
        self.on_event = on_event or (lambda kind, data: None)
        self.j = services.get("journal")
        self._nudge = ""
        self.sav = Savings()
        self.rw: Rewinder | None = None
        self._base_score = -1
        self._last_prompt = 0

    # ---- helpers ----
    def _add(self, msg: dict, meta: dict | None = None) -> None:
        self.history.append(msg)
        self.meta.append(meta or {})

    def _event(self, kind: str, **data) -> None:
        self.j.append(self.s, kind, data)
        self.on_event(kind, data)

    def _escalate(self, why: str) -> bool:
        """Returns False if we should stop instead."""
        if "escalate" not in self.s.flags or self.state.tier != "cheap":
            return False
        self.state.tier = "strong"
        self.state.switches += 1
        self.r.escalations += 1
        self._event("escalate", reason=why, to="strong")
        return True

    def _fit(self, msgs: list[dict], step: int) -> list[dict] | None:
        """Keep prompt + max output under the window: mask everything old, else refuse (never truncate)."""
        tier = "local" if self.s.mode == "confidential" else self.state.tier
        window = CTX_WINDOW[tier]
        size = est_tokens(json.dumps(msgs)) + est_tokens(json.dumps(self.schemas))
        if size + MAX_OUT <= 0.7 * window:
            return msgs
        saved = maybe_mask(self.history, self.meta, step, self.ctx.masked, age=1, min_gain=0)
        self.r.tokens_avoided += saved
        self._event("fit", before=size, saved=saved, window=window)
        msgs = prompt.build(self.history, self.state.render(), cache="cache" in self.s.flags)
        size = est_tokens(json.dumps(msgs)) + est_tokens(json.dumps(self.schemas))
        return msgs if size + MAX_OUT <= 0.95 * window else None

    def _rewind(self, v, step: int) -> None:
        """Undo a failed attempt: files back to the checkpoint, attempt cut from history, note left."""
        rw = self.rw
        assert rw is not None and rw.cp.hist_len is not None
        diff = rw.diff()
        restored = rw.restore()
        current = ""
        for rel in restored:          # show the restored text so SEARCH blocks match what is on disk
            p = self.s.repo / rel
            if p.is_file() and p.stat().st_size <= 6000:
                current += f"\n--- {rel} (current content, after undo) ---\n{p.read_text(encoding='utf-8')}"
        cut = rw.cp.hist_len
        removed = self.history[cut:]
        removed_tokens = sum(est_tokens(json.dumps(m, default=str)) for m in removed)
        del self.history[cut:]
        del self.meta[cut:]
        self.ctx.masked = {i for i in self.ctx.masked if i < cut}
        for path, seen in list(self.ctx.readcache.seen.items()):
            if seen.msg_index >= cut:
                self.ctx.readcache.invalidate(path)
        self.ctx.thrash.calls.clear()
        plus = [x[1:].strip() for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++")]
        gist = "; ".join(x for x in plus if x)[:120] or "(no visible change)"
        why = (v.first_error or v.stage)[:160]
        self.state.attempts.append(f"{gist} -> {why}")
        before = "broken code" if v.passed < 0 else f"{v.passed} passing"
        self._add({"role": "user", "content": (
            f"[rewind #{rw.rewinds}] Your last attempt did not increase the number of passing tests "
            f"({before} vs {rw.cp.score} at the checkpoint), so it was undone: the files are back to the "
            f"content shown earlier in this conversation.\nWhat that attempt changed:\n{diff}\n"
            f"Why it failed:\n{v.shown[:1500]}\n{current}\n"
            "Edit the CURRENT content above (not the undone attempt). Try a different approach.")})
        self.sav.carried("rewind", removed_tokens, step)
        if rw.rewinds >= 2:            # two dead ends are evidence the task is hard: use the strong model
            self._escalate(f"{rw.rewinds} failed attempts rewound")
        self._event("rewind", n=rw.rewinds, removed_tokens=removed_tokens, passed=v.passed,
                    checkpoint_passed=rw.cp.score)

    # ---- main ----
    def run(self) -> Receipt:
        t0 = time.monotonic()
        try:
            self._run()
        except BudgetStop as e:
            self.r.status = f"STOPPED: budget ({e})"
            self._event("budget_stop", message=str(e))
        except KeyboardInterrupt:
            self.r.status = "STOPPED: interrupted"
        finally:
            self.r.wall_s = round(time.monotonic() - t0, 1)
            self.r.test_runs = self.ctx.tests.runs
            self.r.savings = self.sav.report(self.r.steps, self.r.usage.cached_tokens)
            if self.rw is not None:
                self.r.rewinds, self.r.checkpoints = self.rw.rewinds, self.rw.commits
            self._event("session_end", status=self.r.status, solved=self.r.solved,
                        usage=self.r.usage.__dict__)
        return self.r

    def _evidence_files(self) -> list[Path]:
        """Source files the evidence points at: paths named in the task text, modules the oracle tests
        import, then small top-level .py files. Zero LLM tokens (localisation-lite)."""
        root = self.s.repo
        seen: list[Path] = []

        def add(p: Path) -> None:
            if p.is_file() and p.suffix == ".py" and p not in seen:
                seen.append(p)

        for m in re.findall(r"[\w./\\-]+\.py\b", self.state.task):
            add((root / m.replace("\\", "/")).resolve())
        for o in sorted(self.ctx.oracle_files):
            tp = root / o
            try:
                tree = ast.parse(tp.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                mods = [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level \
                    else [a.name for a in node.names] if isinstance(node, ast.Import) else []
                for mod in mods:
                    rel_mod = Path(*mod.split("."))
                    for base in (root, tp.parent):
                        add((base / rel_mod).with_suffix(".py").resolve())
                        add((base / rel_mod / "__init__.py").resolve())
        for p in sorted(root.glob("*.py")):
            add(p.resolve())
        return seen

    def _preload(self, max_files: int = 3, max_chars: int = 3000) -> str:
        """Small source files the evidence points at go into the first prompt (saves read/search turns)."""
        if "preload" not in self.s.flags:
            return ""
        out = []
        root = self.s.repo.resolve()
        for p in self._evidence_files():
            if root not in p.parents:
                continue
            r = p.relative_to(root).as_posix()
            if r in self.ctx.oracle_files or p.name.startswith("test_") or p.stem.endswith("_test") \
                    or p.name in ("conftest.py", "__init__.py") or p.stat().st_size > max_chars:
                continue
            out.append(f"\n--- {r} ---\n{p.read_text(encoding='utf-8', errors='replace')}")
            self.ctx.shown_paths.add(r)
            if len(out) >= max_files:
                break
        tests = []
        for o in sorted(self.ctx.oracle_files)[:2]:      # the oracle is the spec: show it if small
            p = self.s.repo / o
            if p.is_file() and p.stat().st_size <= 4 * max_chars:
                tests.append(f"\n--- {o} ---\n{p.read_text(encoding='utf-8', errors='replace')}")
                self.ctx.shown_paths.add(o)
        text = ("\n\nSource files (current content):" + "".join(out)) if out else ""
        if tests:
            text += "\n\nTests that must pass (do not edit):" + "".join(tests)
        return text

    def _baseline(self) -> str:
        """Reproduce-first: run the oracle once so the model starts with the failures in hand."""
        tr = self.ctx.tests
        if not tr.oracle_ids or "ladder" not in self.s.flags:
            return ""
        try:
            rep = tr.run()
        except Exception as e:  # consent declined etc.
            self.s.flags.add("_no_test_consent")
            return f"\n[tests not run: {e}]"
        tr.baseline_passed = set(rep.passed)
        if tr.full_targets is not None:
            tr.baseline_passed |= tr.run(tr.full_targets).passed
        self.state.failing = sorted(rep.failed)
        self._base_score = len(rep.passed)
        res = tr.show(rep)
        self.r.tokens_avoided += res.tokens_avoided
        self.sav.carried("gate", res.tokens_avoided, 0)
        return f"\nCurrent test results (before any change):\n{res.shown}"

    def _run(self) -> None:
        self._event("session_start", repo=str(self.s.repo), mode=self.s.mode, flags=sorted(self.s.flags),
                    tier=self.state.tier)
        intro = (f"Task:\n{self.state.task}\n\nRepo files:\n{_brief_tree(self.s.repo)}"
                 f"{self._preload()}{self._baseline()}")
        self._add({"role": "user", "content": intro})
        if "rewind" in self.s.flags and self._base_score >= 0:
            self.rw = Rewinder(self.s.repo, self._base_score)
            self.ctx.on_before_write = self.rw.before_write
        finish_rejections = 0
        nudges = 0
        for step in range(1, self.step_cap + 1):
            self.r.steps = step
            self.ctx.turn = step
            if "mask" in self.s.flags:
                saved = maybe_mask(self.history, self.meta, step, self.ctx.masked)
                if saved:
                    self.r.tokens_avoided += saved
                    self.sav.carried("mask", saved, step - 1)
                    self._event("mask", saved=saved)
            pre_len = len(self.history)
            msgs = prompt.build(self.history, self.state.render() + self._nudge,
                                cache="cache" in self.s.flags)
            msgs = self._fit(msgs, step)
            if msgs is None:
                self.r.status = "STOPPED: context full"
                return
            tier = "local" if self.s.mode == "confidential" else self.state.tier
            res = services.get("egress").chat(msgs, self.schemas, session=self.s, tier=tier, max_tokens=MAX_OUT,
                                                temperature=0.7 if (self.state.switches or (
                                                    self.rw and self.rw.rewinds)) else 0.0)
            self.r.usage.add(res.usage)
            self._last_prompt = res.usage.prompt_tokens
            if res.cost_usd is not None:
                self.r.cost_usd = (self.r.cost_usd or 0.0) + res.cost_usd
            if res.model_used not in self.r.models:
                self.r.models.append(res.model_used)
            if res.is_fallback:
                self.r.fallbacks += 1
                self._event("takeover", model=res.model_used, error_class=res.error_class)
            if not res.tool_calls:
                res.tool_calls = text_tool_calls(res.text)
            self._event("model_call", model=res.model_used, tier=tier, usage=res.usage.__dict__,
                        tool_calls=[c.name for c in res.tool_calls], text=(res.text or "")[:8000])
            self.state.absorb(res.text)

            amsg: dict = {"role": "assistant", "content": res.text or None}
            if res.tool_calls:
                amsg["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                    "name": c.name, "arguments": json.dumps(c.arguments)}} for c in res.tool_calls]
            self._add(amsg)

            if res.tool_calls:
                nudges = 0
            elif nudges < 2:          # text-only reply: never counts as finishing on its own
                nudges += 1
                self._nudge = ("\n\nIMPORTANT: your last reply had no tool call. Reply now with tool calls "
                               "(e.g. edit the source file); call finish only when done.")
                self._add({"role": "user", "content": "[no tool call received]"})
                continue
            self._nudge = ""
            finishing = not res.tool_calls
            edited_before = len(self.ctx.touched), self.state.edits
            for c in res.tool_calls:
                if c.name == "finish":
                    finishing = True
                    self._add({"role": "tool", "tool_call_id": c.id, "content": "ok"},
                              {"turn": step, "tool": "finish"})
                    continue
                self._event("tool_started", tool=c.name, call_id=c.id,
                            args={k: (v if len(str(v)) <= 300 else str(v)[:300] + "...")
                                  for k, v in c.arguments.items()})
                self.ctx.thrash.record_call(c.name, c.arguments)
                out = dispatch(c.name, c.arguments, self.ctx)
                if c.name in ("edit", "write") and out.ok:
                    self.state.edits += 1
                self.r.tokens_avoided += out.tokens_avoided
                self.sav.carried("readcache" if c.name == "read" else "gate", out.tokens_avoided, step)
                self._add({"role": "tool", "tool_call_id": c.id, "content": out.shown},
                          {"turn": step, "tool": c.name, "spill": out.spill, "exit": out.exit})
                if out.read_key and "readcache" in self.s.flags:
                    path, window, text = out.read_key
                    if not out.shown.split("\n", 1)[-1].startswith("[unchanged"):
                        self.ctx.readcache.record(path, window, text, step, len(self.history) - 1)
                self._event("tool_done", tool=c.name, call_id=c.id, ok=out.ok,
                            shown_tokens=est_tokens(out.shown), avoided=out.tokens_avoided)

            edited = self.state.edits > edited_before[1]
            if edited:
                self.state.phase = "verify"
                if self.rw is not None:
                    self.rw.arm(pre_len)
            if (edited and "stop_green" in self.s.flags) or finishing:
                checks_on = "ladder" in self.s.flags or "stop_green" in self.s.flags
                v = verify(self.ctx, sorted(self.ctx.touched), full=True) if (
                    (edited or self.state.edits) and checks_on) else None
                if v is not None and v.green:
                    self.r.solved = True
                    self.r.status = "SOLVED"
                    self.state.phase = "done"
                    self.sav.once("stop_green", self._last_prompt + 150, step)   # no "double-check" turn
                    self._event("green", stage=v.stage)
                    return
                if v is not None and not v.ok:
                    self.state.failing = v.sig_ids or self.state.failing
                    self.state.phase = "fix"
                    rw = self.rw
                    if rw is not None and v.stage in ("syntax", "lint", "oracle") and not finishing \
                            and not rw.improved(v.passed) and rw.can_rewind():
                        self._rewind(v, step)
                    else:
                        if "thrash" in self.s.flags:
                            self.ctx.thrash.record_failure(failure_sig(v.sig_ids, v.first_error))
                        self._add({"role": "user", "content": f"[auto-check: {v.stage} failed]\n{v.shown}"})
                        if rw is not None and rw.cp.hist_len is not None and rw.improved(v.passed):
                            rw.commit(len(self.history), v.passed)       # progress: new checkpoint
                            self._event("checkpoint", passed=v.passed)
                if finishing:
                    if v is None or (v.ok and not self.ctx.tests.oracle_ids):
                        self.r.status = "UNVERIFIED (no tests)" if v is None or not v.green else "SOLVED"
                        return
                    finish_rejections += 1
                    if finish_rejections >= 2:
                        self.r.status = "STOPPED: model finished but tests fail"
                        return
            if "thrash" in self.s.flags:
                self.ctx.thrash.record_turn(edited, self.state.edits > 0)
                verdict = self.ctx.thrash.check()
                if verdict == "escalate":
                    # First switch: stronger model if one is available, else (local/confidential) just a
                    # change of strategy. The second trigger stops.
                    self._escalate(self.ctx.thrash.reason)
                    self.state.switches = max(self.state.switches, 1)
                    self._add({"role": "user", "content": f"[strategy switch: {self.ctx.thrash.reason}. "
                               "Step back, re-read the failing test and try a different approach.]"})
                elif verdict is not None:
                    self.r.status = f"STOPPED: thrash ({self.ctx.thrash.reason})"
                    self._event("stop_report", reason=self.ctx.thrash.reason, failing=self.state.failing)
                    return
        self.r.status = f"STOPPED: step cap {self.step_cap}"
