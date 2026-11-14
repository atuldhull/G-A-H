"""Build the benchmark inputs (54 tasks) reproducibly from pinned upstream revisions.

Usage:  python build_bench_inputs.py <polyglot-benchmark clone> <QuixBugs clone> <output dir> <python exe>
Output: <out>/polyglot/<task>/..., <out>/quixbugs/<task>/..., <out>/tasks.json, <out>/oracles.json,
        <out>/MANIFEST.md. Clones must be at the pinned revisions below (checked).
"""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path

POLYGLOT_REV = "7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f"   # github.com/Aider-AI/polyglot-benchmark
QUIXBUGS_REV = "4257f44b0ff1181dedaedee6a447e133219fcebf"   # github.com/jkoppel/QuixBugs
QB_COUNT, QB_TIMEOUT = 20, 30
CMD = ["python", "-m", "pytest", "-q"]

poly_src, qb_src, out, py = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]


def rev(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


assert rev(poly_src) == POLYGLOT_REV, f"polyglot clone is not at {POLYGLOT_REV}"
assert rev(qb_src) == QUIXBUGS_REV, f"QuixBugs clone is not at {QUIXBUGS_REV}"
if out.exists() and any(out.iterdir()):
    sys.exit(f"output dir {out} is not empty; choose a new one")
(out / "polyglot" / "tasks").mkdir(parents=True)
(out / "quixbugs" / "tasks").mkdir(parents=True)


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:16]


tasks, oracles, rows = [], {}, []

# ---- Polyglot: all 34 Python practice exercises -------------------------------------------
practice = poly_src / "python" / "exercises" / "practice"
for ex in sorted(p for p in practice.iterdir() if p.is_dir()):
    tid = ex.name.lower()
    dst = out / "polyglot" / tid
    shutil.copytree(ex, dst, ignore=shutil.ignore_patterns(".meta"))
    tests = sorted(p.name for p in dst.glob("*_test.py"))
    stub = sorted(p.name for p in dst.glob("*.py") if not p.name.endswith("_test.py"))
    text = (ex / ".docs" / "instructions.md").read_text(encoding="utf-8")
    app = ex / ".docs" / "instructions.append.md"
    if app.exists():
        text += "\n" + app.read_text(encoding="utf-8")
    text += (f"\n\nImplement the code in {', '.join(stub)} so the tests in {', '.join(tests)} pass. "
             "Do not modify the tests.\n")
    (out / "polyglot" / "tasks" / f"{tid}.md").write_text(text, encoding="utf-8")
    tasks.append({"dataset": "polyglot", "id": tid, "source": tid, "task_file": f"tasks/{tid}.md",
                  "test_command": CMD})
    oracles[f"polyglot/{tid}"] = tests
    rows.append(("polyglot", tid, tree_hash(dst)))

# ---- QuixBugs: 20 programs by a fixed, mechanical rule ------------------------------------
# Rule: Python programs whose test reads json_testcases/<name>.json, whose test file has no
# slow marker, and whose BUGGY version finishes its tests within QB_TIMEOUT seconds (the runner
# cannot pass per-task timeouts yet); then the first QB_COUNT alphabetically.
candidates, excluded = [], []
for t in sorted((qb_src / "python_testcases").glob("test_*.py")):
    name = t.stem[len("test_"):]
    src = t.read_text(encoding="utf-8")
    if not (qb_src / "json_testcases" / f"{name}.json").exists() or "load_json_testcases" not in src:
        continue
    if "slow" in src:
        excluded.append((name, "tests marked slow"))
        continue
    candidates.append(name)


def assemble(name: str, dst: Path) -> None:
    (dst / "python_programs").mkdir(parents=True)
    (dst / "python_testcases").mkdir()
    (dst / "json_testcases").mkdir()
    shutil.copy(qb_src / "conftest.py", dst)
    shutil.copy(qb_src / "python_programs" / f"{name}.py", dst / "python_programs")
    shutil.copy(qb_src / "python_programs" / "node.py", dst / "python_programs")
    for f in ("load_testdata.py", "node.py", f"test_{name}.py"):
        shutil.copy(qb_src / "python_testcases" / f, dst / "python_testcases")
    shutil.copy(qb_src / "json_testcases" / f"{name}.json", dst / "json_testcases")


selected = []
for name in candidates:
    if len(selected) == QB_COUNT:
        break
    dst = out / "quixbugs" / name
    assemble(name, dst)
    try:
        r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=dst,
                           capture_output=True, text=True, timeout=QB_TIMEOUT)
        if r.returncode == 0:
            excluded.append((name, "buggy version already passes"))
            shutil.rmtree(dst)
            continue
    except subprocess.TimeoutExpired:
        excluded.append((name, f"buggy version does not finish within {QB_TIMEOUT}s"))
        shutil.rmtree(dst)
        continue
    selected.append(name)
    text = (f"The function in python_programs/{name}.py has a bug: the tests in "
            f"python_testcases/test_{name}.py fail. Find and fix the bug in python_programs/{name}.py. "
            "Do not modify the tests.\n")
    (out / "quixbugs" / "tasks" / f"{name}.md").write_text(text, encoding="utf-8")
    tasks.append({"dataset": "quixbugs", "id": name, "source": name, "task_file": f"tasks/{name}.md",
                  "test_command": CMD,
                  "test_paths": ["conftest.py", "python_testcases/load_testdata.py",
                                 "python_testcases/node.py", f"json_testcases/{name}.json"]})
    oracles[f"quixbugs/{name}"] = [f"python_testcases/test_{name}.py"]
    rows.append(("quixbugs", name, tree_hash(dst)))
assert len(selected) == QB_COUNT, f"only {len(selected)} QuixBugs programs met the rule"

(out / "tasks.json").write_text(json.dumps({"schema_version": 1, "tasks": tasks}, indent=2), encoding="utf-8")
(out / "oracles.json").write_text(json.dumps(oracles, indent=2), encoding="utf-8")


def fhash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


m = ["# Benchmark inputs manifest", "",
     f"- Polyglot: github.com/Aider-AI/polyglot-benchmark @ `{POLYGLOT_REV}` (34 Python practice exercises, `.meta/` excluded)",
     f"- QuixBugs: github.com/jkoppel/QuixBugs @ `{QUIXBUGS_REV}` ({QB_COUNT} programs, rule below)",
     f"- QuixBugs rule: JSON-testcase programs, no slow marker, buggy version finishes within {QB_TIMEOUT}s, "
     "first 20 alphabetically. Each task is a self-contained copy of conftest.py, the program, node.py, "
     "load_testdata.py, its test and its JSON data.",
     f"- tasks.json sha256 `{fhash(out / 'tasks.json')}`", f"- oracles.json sha256 `{fhash(out / 'oracles.json')}`",
     f"- Built with: {subprocess.run([py, '--version'], capture_output=True, text=True).stdout.strip()}",
     "", "## Excluded QuixBugs candidates", ""]
m += [f"- {n}: {why}" for n, why in excluded] or ["- none"]
m += ["", "## Tasks (dataset, id, source tree sha256/16)", ""] + [f"- {d}/{i} `{h}`" for d, i, h in rows]
(out / "MANIFEST.md").write_text("\n".join(m) + "\n", encoding="utf-8")
print(f"tasks: {len(tasks)} (polyglot {sum(t['dataset']=='polyglot' for t in tasks)}, quixbugs {len(selected)})")
print("excluded:", excluded)
