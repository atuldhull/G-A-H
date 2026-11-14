"""Strict, offline calculations from planned runs and local billing evidence."""

import argparse
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys

from bench.plan import AGENTS, DATASETS, ID_PATTERN, TEST_PREFIX, _object


RESAMPLES = 10_000
TOKENS = {"uncached_input", "cache_write_input", "cache_read_input", "output"}
KINDS = {"measured", "synthetic"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label}: expected exactly {sorted(required)}")


def _version(value):
    if type(value) is not int or value != 1:
        raise ValueError("schema_version must be integer 1")


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be nonempty text without control characters")
    return value


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value, label):
    try:
        valid = type(value) in (int, Decimal) and math.isfinite(float(value)) and value >= 0
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a finite nonnegative JSON number")
    return Fraction(value)


def _float(value):
    result = float(value)
    if not math.isfinite(result) or (value != 0 and result == 0):
        raise ValueError("Calculation is outside the supported finite numeric range")
    return result


def _nonfinite(value):
    raise ValueError(f"Non-finite JSON value is forbidden: {value}")


def _json(raw):
    return json.loads(raw, parse_float=Decimal, parse_constant=_nonfinite, object_pairs_hook=_object)


def _jsonl(raw, label):
    lines = raw.decode("utf-8").splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise ValueError(f"{label}: expected nonempty JSONL without blank records")
    rows = []
    for number, line in enumerate(lines, 1):
        try:
            rows.append(_json(line))
        except ValueError as error:
            raise ValueError(f"{label} line {number}: {error}") from error
    return rows


def _sha(value, label):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _date(value):
    _text(value, "date")
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must use YYYY-MM-DD")


def _plan(document):
    if not isinstance(document, dict):
        raise ValueError("Expected a benchmark-run-plan object")
    _version(document.get("schema_version"))
    if document.get("kind") != "benchmark-run-plan" or document.get("execution_enabled") is not False:
        raise ValueError("Expected a planning-only milestone 3 manifest")
    repeats = document.get("runs_per_task")
    _fields(repeats, AGENTS, "runs_per_task")
    for count in repeats.values():
        _integer(count, "run count", 1)
    if repeats["crocodile"] != repeats["mini-swe-agent"] or repeats["all-off-twin"] != 1:
        raise ValueError("Paired agents need equal repeats and the twin needs one")
    tasks, planned = document.get("tasks"), document.get("runs")
    if not isinstance(tasks, list) or not tasks or not isinstance(planned, list):
        raise ValueError("Plan must contain nonempty tasks and a runs list")
    policy = document.get("evaluation_policy")
    if not isinstance(policy, dict):
        raise ValueError("Plan requires an evaluation_policy object")
    model = _text(policy.get("model"), "planned model")
    by_task = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Invalid planned task")
        dataset, task_id = task.get("dataset"), task.get("task_id")
        if dataset not in DATASETS or not isinstance(task_id, str):
            raise ValueError("Invalid planned dataset or task ID")
        prefix, separator, local_id = task_id.partition("/")
        if not separator or prefix != dataset or not ID_PATTERN.fullmatch(local_id):
            raise ValueError("Task ID must match dataset/id")
        if task_id in by_task:
            raise ValueError(f"Duplicate planned task: {task_id}")
        _sha(task.get("task_text_sha256"), "planned task text hash")
        command = task.get("test_command")
        if not isinstance(command, list) or command[:4] != TEST_PREFIX:
            raise ValueError("Invalid planned test command")
        for argument in command:
            _text(argument, "test command argument")
        by_task[task_id] = task
    expected = {}
    for task_id, task in sorted(by_task.items()):
        for agent in AGENTS:
            for number in range(1, repeats[agent] + 1):
                run_id = f"{task_id}/{agent}/run-{number}"
                expected[run_id] = {
                    "run_id": run_id, "task_id": task_id, "dataset": task["dataset"],
                    "agent_variant": agent, "run_number": number,
                    "task_text_sha256": task["task_text_sha256"],
                    "test_command": task["test_command"],
                    "step_cap": 30, "wall_clock_cap_seconds": 600,
                }
    seen = set()
    for run in planned:
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
            raise ValueError("Invalid planned run")
        key = run["run_id"]
        if key in seen or key not in expected:
            raise ValueError(f"Duplicate or unexpected planned run: {key}")
        _integer(run.get("run_number"), "planned run number", 1)
        if any(run.get(field) != value for field, value in expected[key].items()):
            raise ValueError(f"Mismatched planned run: {key}")
        seen.add(key)
    if seen != set(expected):
        raise ValueError("Plan is missing expected runs")
    if (
        type(document.get("task_count")) is not int or document["task_count"] != len(tasks)
        or type(document.get("run_count")) is not int or document["run_count"] != len(expected)
    ):
        raise ValueError("Plan counts do not match its task/run grid")
    return expected, model


def _prices(document):
    _fields(document, {"schema_version", "data_kind", "currency", "models"}, "prices.yaml")
    _version(document["schema_version"])
    if not isinstance(document["data_kind"], str) or document["data_kind"] not in KINDS or document["currency"] != "USD":
        raise ValueError("Prices require data_kind measured/synthetic and currency USD")
    if not isinstance(document["models"], dict) or not document["models"]:
        raise ValueError("Prices must list at least one model")
    result = {}
    for model, rates in document["models"].items():
        _text(model, "priced model")
        _fields(rates, TOKENS, f"prices for {model}")
        result[model] = {key: _number(rates[key], f"{model} {key} USD/million") for key in TOKENS}
    return result


def _sessions(rows, prices):
    sessions, session_ids, request_ids = {}, set(), set()
    required = {
        "schema_version", "data_kind", "source", "complete", "run_id", "session_id",
        "model", "date", "gateway_version", "requests",
    }
    for row in rows:
        _fields(row, required, "Bifrost session export")
        _version(row["schema_version"])
        if (row["source"] != "bifrost" or row["complete"] is not True
                or not isinstance(row["data_kind"], str) or row["data_kind"] not in KINDS):
            raise ValueError("Bifrost session evidence must be complete and identify its source/kind")
        for field in ("run_id", "session_id", "model", "gateway_version"):
            _text(row[field], field)
        if row["model"] not in prices:
            raise ValueError("Bifrost session model is not priced")
        _date(row["date"])
        if row["run_id"] in sessions or row["session_id"] in session_ids:
            raise ValueError("Duplicate Bifrost run/session evidence")
        if not isinstance(row["requests"], list):
            raise ValueError("Bifrost requests must be a list, explicitly empty for no calls")
        cost = Fraction(0)
        for request in row["requests"]:
            _fields(request, {"request_id", "model", "usage"}, "Bifrost request")
            key = _text(request["request_id"], "request_id")
            if key in request_ids:
                raise ValueError("Duplicate Bifrost request ID")
            request_ids.add(key)
            if request["model"] != row["model"] or request["model"] not in prices:
                raise ValueError("Mismatched or unpriced request model")
            _fields(request["usage"], TOKENS, "request usage")
            for token in TOKENS:
                quantity = _integer(request["usage"][token], f"usage {token}")
                cost += quantity * prices[request["model"]][token] / 1_000_000
        sessions[row["run_id"]] = (row, cost)
        session_ids.add(row["session_id"])
    return sessions


def _validated(rows, expected, model, sessions, log_hash, price_hash, data_kind):
    metadata = {"schema_version", "data_kind", "model", "date", "gateway_version"}
    grading = {"solved", "test_edit", "pytest_exit_code", "timed_out", "error"}
    required = set(next(iter(expected.values()))) | metadata | grading | {"cost_usd", "cost_provenance"}
    result, versions = {}, set()
    for row in rows:
        _fields(row, required, "run result")
        _version(row["schema_version"])
        key = _text(row["run_id"], "run_id")
        if key in result or key not in expected:
            raise ValueError(f"Duplicate or unexpected result: {key}")
        _integer(row["run_number"], "run_number", 1)
        if any(row[field] != value for field, value in expected[key].items()):
            raise ValueError(f"Mismatched pairing/fairness metadata: {key}")
        if row["model"] != model or row["data_kind"] != data_kind:
            raise ValueError("Model or data_kind mismatch")
        _date(row["date"])
        _text(row["gateway_version"], "gateway_version")
        versions.add(row["gateway_version"])
        for field in ("solved", "test_edit", "timed_out"):
            if type(row[field]) is not bool:
                raise ValueError(f"{field} must be a boolean")
        if row["error"] is not None:
            _text(row["error"], "execution error")
        interrupted = row["timed_out"] or row["error"] is not None
        if interrupted:
            if row["pytest_exit_code"] is not None or row["solved"]:
                raise ValueError("Interrupted/error runs need null exit code and solved false")
        elif type(row["pytest_exit_code"]) is not int or row["solved"] != (row["pytest_exit_code"] == 0):
            raise ValueError("Solved status must agree with a completed pytest exit")
        cost = _number(row["cost_usd"], "cost_usd")
        proof = row["cost_provenance"]
        _fields(proof, {"kind", "session_id", "logs_sha256", "prices_sha256"}, "cost provenance")
        if (
            proof["kind"] != "bifrost_logs_x_prices_yaml"
            or proof["logs_sha256"] != log_hash or proof["prices_sha256"] != price_hash
        ):
            raise ValueError("Unverified cost provenance: source or evidence hash mismatch")
        if key not in sessions:
            raise ValueError(f"Missing Bifrost session evidence: {key}")
        session, verified_cost = sessions[key]
        for field in ("model", "date", "gateway_version", "data_kind"):
            if session[field] != row[field]:
                raise ValueError(f"Mismatched Bifrost {field}: {key}")
        if session["session_id"] != proof["session_id"] or cost != verified_cost:
            raise ValueError(f"Unverified cost: session or recomputed charge mismatch for {key}")
        result[key] = {**row, "_cost": verified_cost}
    if set(result) != set(expected):
        raise ValueError(f"Incomplete results: missing {sorted(set(expected) - set(result))}")
    if set(sessions) != set(expected):
        raise ValueError("Bifrost evidence does not match the complete planned run grid")
    if len(versions) != 1:
        raise ValueError("Gateway versions differ across paired runs")
    return [result[key] for key in sorted(result)]


def _interval(values, seed, label, *, exponential=False):
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    rng = random.Random(int.from_bytes(digest, "big"))
    samples = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(RESAMPLES)]
    if exponential:
        samples = [math.exp(value) for value in samples]
        if any(value == 0 or not math.isfinite(value) for value in samples):
            raise ValueError("Cost ratio bootstrap is outside the finite positive range")
    samples.sort()

    def percentile(probability):
        position = (len(samples) - 1) * probability
        lower = math.floor(position)
        fraction = position - lower
        return samples[lower] * (1 - fraction) + samples[min(lower + 1, len(samples) - 1)] * fraction

    return [percentile(0.025), percentile(0.975)]


def _group(rows, seed, label):
    tasks = sorted({row["task_id"] for row in rows})
    agents = {}
    for agent in AGENTS:
        selected = [row for row in rows if row["agent_variant"] == agent]
        solved = sum(row["solved"] for row in selected)
        cost = sum((row["_cost"] for row in selected), Fraction(0))
        agents[agent] = {
            "tasks": len(tasks), "runs": len(selected), "solved_runs": solved,
            "pass_rate": solved / len(selected),
            "pass_rate_by_run": {
                str(number): sum(row["solved"] for row in selected if row["run_number"] == number) / len(tasks)
                for number in sorted({row["run_number"] for row in selected})
            },
            "total_cost_usd": _float(cost),
            "cost_per_solved_task_usd": _float(cost / solved) if solved else None,
            "cpst_status": "available" if solved else "inconclusive",
            "cpst_reason": None if solved else "zero solved runs; division undefined",
            "test_edit_runs": sum(row["test_edit"] for row in selected),
        }
    differences, joint, excluded, paired_tasks = [], [], [], []
    for task in tasks:
        ours = {row["run_number"]: row for row in rows if row["task_id"] == task
                and row["agent_variant"] == "crocodile"}
        mini = {row["run_number"]: row for row in rows if row["task_id"] == task
                and row["agent_variant"] == "mini-swe-agent"}
        difference = Fraction(sum(row["solved"] for row in ours.values())
                              - sum(row["solved"] for row in mini.values()), len(ours))
        differences.append(difference)
        paired_tasks.append({
            "task_id": task, "difference": _float_signed(difference),
            "runs": [{"run_number": number,
                      "crocodile_solved": ours[number]["solved"],
                      "mini_solved": mini[number]["solved"],
                      "crocodile_cost_usd": _float(ours[number]["_cost"]),
                      "mini_cost_usd": _float(mini[number]["_cost"])}
                     for number in sorted(ours)],
        })
        matched = [number for number in sorted(ours) if ours[number]["solved"] and mini[number]["solved"]]
        if matched:
            joint.append({
                "task_id": task, "paired_runs": matched,
                "ours": sum((ours[number]["_cost"] for number in matched), Fraction(0)),
                "mini": sum((mini[number]["_cost"] for number in matched), Fraction(0)),
            })
        else:
            excluded.append(task)
    paired = {
        "task_count": len(tasks), "difference": _float_signed(statistics.mean(differences)),
        "units": "proportion", "tasks": paired_tasks,
        "wins": sum(value > 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "ci95": None, "status": "inconclusive", "non_inferiority": "inconclusive",
        "reason": "fewer than two independent tasks" if len(tasks) < 2 else None,
        "non_inferiority_reason": "fewer than two independent tasks",
    }
    if len(tasks) >= 2:
        paired["ci95"] = _interval([float(value) for value in differences], seed, label + ":pass")
        paired["status"] = "available"
        paired["non_inferiority_reason"] = "CI lower bound does not strictly exceed -0.10"
        if paired["ci95"][0] > -0.10:
            paired["non_inferiority"] = "not_worse_by_more_than_10_percentage_points"
            paired["non_inferiority_reason"] = None
    ratio = {
        "task_count": len(joint), "ratio": None, "ci95": None, "status": "inconclusive",
        "reason": "no jointly solved paired runs", "excluded_task_ids": excluded,
        "joint_tasks": [{"task_id": item["task_id"], "paired_runs": item["paired_runs"],
                         "crocodile_cost_usd": _float(item["ours"]),
                         "mini_cost_usd": _float(item["mini"])} for item in joint],
    }
    if joint and any(item["ours"] == 0 or item["mini"] == 0 for item in joint):
        ratio["reason"] = "measured zero joint cost; positive geometric ratios are undefined"
    elif joint:
        logs = [math.log((item["ours"] / item["mini"]).numerator)
                - math.log((item["ours"] / item["mini"]).denominator) for item in joint]
        try:
            value = math.exp(statistics.fmean(logs))
            if value == 0 or not math.isfinite(value):
                raise ValueError("Cost ratio is outside the finite positive range")
            ratio["ratio"] = value
            ratio["reason"] = "fewer than two jointly solved tasks" if len(joint) < 2 else None
            if len(joint) >= 2:
                ratio["ci95"] = _interval(logs, seed, label + ":cost", exponential=True)
                ratio["status"] = "available"
        except (ValueError, OverflowError) as error:
            ratio.update(ratio=None, ci95=None, reason=str(error))
    return {"task_count": len(tasks), "agents": agents,
            "paired_pass_rate": paired, "joint_cost_ratio": ratio}


def _float_signed(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite pass-rate calculation")
    return result


def calculate_report(plan_path, results_path, logs_path, prices_path, *, seed):
    """Read four local artifacts, verify a full run grid, and calculate statistics."""
    _integer(seed, "bootstrap seed")
    paths = {"plan": Path(plan_path), "results": Path(results_path),
             "bifrost_logs": Path(logs_path), "prices": Path(prices_path)}
    if paths["prices"].name != "prices.yaml":
        raise ValueError("The price snapshot must be named prices.yaml")
    raw = {key: path.read_bytes() for key, path in paths.items()}
    hashes = {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
    plan_document = _json(raw["plan"])
    expected, model = _plan(plan_document)
    prices_doc = _json(raw["prices"])
    prices = _prices(prices_doc)
    sessions = _sessions(_jsonl(raw["bifrost_logs"], "Bifrost logs"), prices)
    rows = _validated(
        _jsonl(raw["results"], "results"), expected, model, sessions,
        hashes["bifrost_logs"], hashes["prices"], prices_doc["data_kind"],
    )
    datasets = sorted({row["dataset"] for row in rows})
    return {
        "schema_version": 1, "status": "complete" if prices_doc["data_kind"] == "measured" else "synthetic_test_only",
        "data_kind": prices_doc["data_kind"],
        "metadata": {
            "model": model, "datasets": datasets, "task_count": len({row["task_id"] for row in rows}),
            "run_count": len(rows), "runs_per_task": plan_document["runs_per_task"],
            "dates": sorted({row["date"] for row in rows}), "gateway_version": rows[0]["gateway_version"],
        },
        "bootstrap": {"resamples": RESAMPLES, "seed": seed, "python_version": sys.version.split()[0],
                      "unit": "tasks", "interval": "percentile 2.5/97.5; linear (n-1)*p",
                      "rng": "random.Random; SHA256(seed:dataset:metric) independent streams"},
        "cost_verification": {"status": "verified_against_local_evidence", "input_sha256": hashes,
                              "rule": "exact rational token usage times USD/million rates; no rounding"},
        "datasets": {dataset: _group([row for row in rows if row["dataset"] == dataset], seed, dataset)
                     for dataset in datasets},
        "overall": _group(rows, seed, "overall"),
        "crocodile_test_edit_runs": sum(row["test_edit"] for row in rows if row["agent_variant"] == "crocodile"),
        "unavailable_metrics": ["token savings", "race overshoot", "reservation overshoot", "red-team score"],
        "public_claims": "not generated; human review of scope, test-edit red flags, and limitations required",
    }


def render_markdown(summary):
    """Render numbers without generating promotional claims."""
    metadata = summary["metadata"]
    heading = "Offline benchmark report" if summary["data_kind"] == "measured" else "SYNTHETIC TEST DATA - NOT BENCHMARK RESULTS"
    lines = [f"# {heading}", "", f"Status: {summary['status']} (complete only relative to the supplied plan).", ""]
    for name, value in metadata.items():
        lines.append(f"- {name}: {str(value).replace('|', '/').replace(chr(10), ' ')}")
    bootstrap = summary["bootstrap"]
    lines += ["", f"Bootstrap: {bootstrap['resamples']} task resamples; statistical seed {bootstrap['seed']}.",
              "This seed controls offline resampling, not independent model runs.", ""]
    for name, group in [*summary["datasets"].items(), ("overall (pooled tasks; supplementary)", summary["overall"])]:
        lines += [f"## {name}", "", "| Agent | Solved / runs | Pass rate | Total USD (all runs) | CPST USD | Test edits |",
                  "|---|---:|---:|---:|---:|---:|"]
        for agent, values in group["agents"].items():
            cpst = values["cost_per_solved_task_usd"]
            display = "inconclusive (zero solved)" if cpst is None else f"{cpst:.8g}"
            lines.append(f"| {agent} | {values['solved_runs']}/{values['runs']} | {values['pass_rate']:.2%} | "
                         f"{values['total_cost_usd']:.8g} | {display} | {values['test_edit_runs']} |")
        paired, ratio = group["paired_pass_rate"], group["joint_cost_ratio"]
        pass_interval = ("inconclusive" if paired["ci95"] is None else
                         f"[{100 * paired['ci95'][0]:.6g}, {100 * paired['ci95'][1]:.6g}] percentage points")
        lines += ["", f"Paired difference (Crocodile - mini): {100 * paired['difference']:.6g} percentage points; "
                  f"95% interval {pass_interval}. W/L/T: {paired['wins']}/{paired['losses']}/{paired['ties']}.",
                  f"Comparison: {paired['status']}; non-inferiority: {paired['non_inferiority']}; "
                  f"reason: {paired['reason'] or paired['non_inferiority_reason']}.",
                  f"Jointly solved cost ratio: {ratio['ratio']}; 95% interval {ratio['ci95']}; "
                  f"tasks: {ratio['task_count']}; {ratio['status']}; reason: {ratio['reason']}.", ""]
    lines += ["## Calculation rules and limitations", "",
              "- Pass rates are reported by dataset, agent, and run in JSON; aggregate rates average complete repeats.",
              "- Pair by task ID and run number. Average repeats within tasks; wins/losses/ties compare task averages.",
              "- Bootstrap whole tasks with replacement 10,000 times; percentile intervals use linear interpolation.",
              "- Non-inferiority requires the pass-difference lower bound strictly above -0.10; otherwise inconclusive.",
              "- CPST includes costs of every solved and unsolved run, divided by solved runs; zero solved gives null.",
              "- Cost ratios use only run numbers jointly solved by both agents. Sum matched costs per task, then geometric-mean task ratios.",
              "- Cost-ratio bootstrap resamples eligible tasks, not independent runs. Zero joint cost is explicit and makes the ratio inconclusive.",
              "- Fewer than two eligible tasks cannot support an interval. Small samples and degenerate bootstrap intervals limit inference.",
              "- Local hashes and recomputation verify consistency, not authenticity/completeness of the upstream exporter or price snapshot.",
              "- Dataset contamination, selected scope, shared tasks, and execution-environment differences remain limitations. No significance claims.",
              "- Test-edit flags remain separate from restored-oracle passes and are red for Crocodile.",
              "- Token savings, race/reservation overshoot, and red-team results are not supplied, not measured zeros.",
              "- Full rules, schema, and evidence assumptions are documented in bench/README.md.", ""]
    return "\n".join(lines)


def write_reports(summary, summary_path, markdown_path, *, overwrite=False):
    if summary["data_kind"] != "measured":
        raise ValueError("Synthetic data may be calculated in tests but cannot publish report artifacts")
    destinations = [Path(summary_path).absolute().resolve(), Path(markdown_path).absolute().resolve()]
    if destinations[0] == destinations[1]:
        raise ValueError("Summary and Markdown outputs must differ")
    contents = [json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", render_markdown(summary)]
    for path in destinations:
        if not path.parent.is_dir() or path.is_dir() or (path.exists() and not overwrite):
            raise ValueError(f"Output parent must exist and existing files need --overwrite: {path}")
    for path, text in zip(destinations, contents):
        path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--bifrost-logs", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--summary", type=Path, default=Path("bench/report.json"))
    parser.add_argument("--markdown", type=Path, default=Path("bench/report.md"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = calculate_report(args.plan, args.results, args.bifrost_logs, args.prices, seed=args.seed)
        outputs = {args.summary.resolve(), args.markdown.resolve()}
        inputs = {path.resolve() for path in (args.plan, args.results, args.bifrost_logs, args.prices)}
        if outputs & inputs:
            raise ValueError("Report outputs must not overwrite input artifacts")
        write_reports(summary, args.summary, args.markdown, overwrite=args.overwrite)
    except (OSError, ValueError, OverflowError) as error:
        parser.exit(2, f"Reporting failed: {error}\n")
    print(f"Wrote {args.summary} and {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
