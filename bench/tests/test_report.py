"""Offline reporting tests; all rates, logs, tasks, and outcomes are synthetic."""

import copy
import hashlib
import json

import pytest

from bench.plan import AGENTS
from bench.report import calculate_report, main, render_markdown, write_reports


MODEL = "synthetic/test-model"
TOKENS = ("uncached_input", "cache_write_input", "cache_read_input", "output")


def save(data, *, refresh_proof=True):
    data["paths"]["plan"].write_text(json.dumps(data["plan"]), encoding="utf-8")
    data["paths"]["prices"].write_text(json.dumps(data["prices"]), encoding="utf-8")
    for name in ("logs", "results"):
        if name == "results" and refresh_proof:
            logs = hashlib.sha256(data["paths"]["logs"].read_bytes()).hexdigest()
            prices = hashlib.sha256(data["paths"]["prices"].read_bytes()).hexdigest()
            for row in data["results"]:
                row["cost_provenance"]["logs_sha256"] = logs
                row["cost_provenance"]["prices_sha256"] = prices
        data["paths"][name].write_text(
            "".join(json.dumps(row) + "\n" for row in data[name]), encoding="utf-8"
        )


def fixture_data(tmp_path, *, tasks=3, zero_solved=False, zero_cost=False):
    data = {
        "paths": {"plan": tmp_path / "plan.json", "results": tmp_path / "results.jsonl",
                  "logs": tmp_path / "bifrost.jsonl", "prices": tmp_path / "prices.yaml"},
        "plan": {"schema_version": 1, "kind": "benchmark-run-plan", "execution_enabled": False,
                 "evaluation_policy": {"model": MODEL}, "tasks": [], "runs": [],
                 "runs_per_task": {"crocodile": 2, "mini-swe-agent": 2, "all-off-twin": 1}},
        "prices": {"schema_version": 1, "data_kind": "synthetic", "currency": "USD",
                   "models": {MODEL: {key: 1 for key in TOKENS}}},
        "results": [], "logs": [],
    }
    outcomes = {"crocodile": [[True, True], [False, True], [True, False]],
                "mini-swe-agent": [[True, False], [True, True], [True, False]],
                "all-off-twin": [[True], [True], [True]]}
    costs = {"crocodile": [[1, 4], [3, 1], [2, 5]],
             "mini-swe-agent": [[2, 7], [6, 2], [4, 9]],
             "all-off-twin": [[1], [1], [1]]}
    for index in range(tasks):
        dataset = "quixbugs" if index >= 3 else "polyglot"
        task_id = f"{dataset}/task-{index}"
        task = {"task_id": task_id, "dataset": dataset, "task_text_sha256": "a" * 64,
                "test_command": ["python", "-m", "pytest", "-q"]}
        data["plan"]["tasks"].append(task)
        for agent in AGENTS:
            for number in range(1, data["plan"]["runs_per_task"][agent] + 1):
                run_id = f"{task_id}/{agent}/run-{number}"
                planned = {**task, "run_id": run_id, "agent_variant": agent,
                           "run_number": number, "step_cap": 30, "wall_clock_cap_seconds": 600}
                solved = outcomes[agent][index % 3][number - 1] and not zero_solved
                cost = costs[agent][index % 3][number - 1] if not zero_cost else 0
                session_id = "session:" + run_id
                data["plan"]["runs"].append(planned)
                data["results"].append({
                    **planned, "schema_version": 1, "data_kind": "synthetic", "model": MODEL,
                    "date": "2026-11-13", "gateway_version": "synthetic-v1", "solved": solved,
                    "test_edit": False, "pytest_exit_code": 0 if solved else 1,
                    "timed_out": False, "error": None, "cost_usd": cost,
                    "cost_provenance": {"kind": "bifrost_logs_x_prices_yaml", "session_id": session_id,
                                        "logs_sha256": "", "prices_sha256": ""},
                })
                data["logs"].append({
                    "schema_version": 1, "data_kind": "synthetic", "source": "bifrost", "complete": True,
                    "run_id": run_id, "session_id": session_id, "model": MODEL,
                    "date": "2026-11-13", "gateway_version": "synthetic-v1",
                    "requests": [{"request_id": "request:" + run_id, "model": MODEL,
                                  "usage": {key: cost * 1_000_000 if key == "uncached_input" else 0
                                            for key in TOKENS}}] if cost else [],
                })
    data["plan"]["task_count"] = tasks
    data["plan"]["run_count"] = len(data["results"])
    save(data)
    return data


@pytest.fixture
def data(tmp_path):
    return fixture_data(tmp_path)


def calculate(data, seed=1729):
    paths = data["paths"]
    return calculate_report(paths["plan"], paths["results"], paths["logs"], paths["prices"], seed=seed)


def test_paired_task_means_wins_losses_ties_and_joint_ratio(data):
    summary = calculate(data)
    group = summary["datasets"]["polyglot"]
    assert group["agents"]["crocodile"]["pass_rate"] == pytest.approx(4 / 6)
    assert group["agents"]["mini-swe-agent"]["pass_rate_by_run"] == {"1": 1.0, "2": 1 / 3}
    paired = group["paired_pass_rate"]
    assert paired["difference"] == 0
    assert (paired["wins"], paired["losses"], paired["ties"]) == (1, 1, 1)
    assert paired["ci95"] == [-0.5, 0.5]
    assert paired["non_inferiority"] == "inconclusive"
    assert paired["tasks"][0]["task_id"] == "polyglot/task-0"
    assert [item["run_number"] for item in paired["tasks"][0]["runs"]] == [1, 2]
    assert paired["tasks"][0]["runs"][1]["crocodile_solved"] is True
    assert paired["tasks"][0]["runs"][1]["mini_solved"] is False
    ratio = group["joint_cost_ratio"]
    assert ratio["ratio"] == pytest.approx(0.5)
    assert ratio["ci95"] == pytest.approx([0.5, 0.5])
    assert [item["paired_runs"] for item in ratio["joint_tasks"]] == [[1], [2], [1]]
    assert summary["metadata"]["run_count"] == 15
    assert summary["bootstrap"]["resamples"] == 10_000
    assert summary["status"] == "synthetic_test_only"


def test_cpst_counts_unsolved_costs(data):
    agent = calculate(data)["datasets"]["polyglot"]["agents"]["crocodile"]
    assert agent["total_cost_usd"] == 16
    assert agent["cost_per_solved_task_usd"] == 4
    assert agent["solved_runs"] == 4


def test_ratio_aggregates_same_joint_run_numbers_before_geometric_mean(data):
    for row in data["results"]:
        if row["task_id"] == "polyglot/task-0":
            row.update(solved=True, pytest_exit_code=0)
    save(data)
    ratio = calculate(data)["overall"]["joint_cost_ratio"]
    first = ratio["joint_tasks"][0]
    assert first["paired_runs"] == [1, 2]
    assert first["crocodile_cost_usd"] == 5
    assert first["mini_cost_usd"] == 9
    assert ratio["ratio"] == pytest.approx(((5 / 9) * 0.5 * 0.5) ** (1 / 3))
    assert ratio["ci95"] == pytest.approx([0.5, 5 / 9])


def test_dataset_groups_are_separate_and_overall_is_task_weighted(tmp_path):
    summary = calculate(fixture_data(tmp_path, tasks=4))
    assert summary["metadata"]["datasets"] == ["polyglot", "quixbugs"]
    assert summary["datasets"]["polyglot"]["agents"]["crocodile"]["pass_rate"] == 4 / 6
    assert summary["datasets"]["quixbugs"]["agents"]["crocodile"]["pass_rate"] == 1
    assert summary["overall"]["agents"]["crocodile"]["pass_rate"] == 6 / 8
    assert summary["overall"]["paired_pass_rate"]["difference"] == 0.125


def test_non_inferiority_uses_the_prescribed_margin(data):
    for row in data["results"]:
        row.update(solved=True, pytest_exit_code=0)
    save(data)
    paired = calculate(data)["overall"]["paired_pass_rate"]
    assert paired["ci95"] == [0, 0]
    assert paired["non_inferiority"] == "not_worse_by_more_than_10_percentage_points"


def test_bootstrap_reproducibility_and_input_order(data):
    first = calculate(data)
    assert first == calculate(data)
    data["results"].reverse()
    data["logs"].reverse()
    save(data)
    second = calculate(data)
    assert first["datasets"] == second["datasets"]
    assert first["overall"] == second["overall"]
    assert first["bootstrap"]["seed"] == second["bootstrap"]["seed"] == 1729
    assert calculate(data, seed=44)["bootstrap"]["seed"] == 44


def test_zero_solved_cost_is_undefined_not_zero(tmp_path):
    summary = calculate(fixture_data(tmp_path, zero_solved=True))
    group = summary["overall"]
    agent = group["agents"]["crocodile"]
    assert agent["pass_rate"] == 0
    assert agent["total_cost_usd"] == 16
    assert agent["cost_per_solved_task_usd"] is None
    assert agent["cpst_status"] == "inconclusive"
    assert group["joint_cost_ratio"]["ratio"] is None
    assert group["joint_cost_ratio"]["task_count"] == 0
    assert len(group["joint_cost_ratio"]["excluded_task_ids"]) == 3


def test_measured_zero_cost_has_evidence_and_is_not_missing(tmp_path):
    summary = calculate(fixture_data(tmp_path, zero_cost=True))
    assert summary["overall"]["agents"]["crocodile"]["cost_per_solved_task_usd"] == 0
    ratio = summary["overall"]["joint_cost_ratio"]
    assert ratio["status"] == "inconclusive"
    assert ratio["ratio"] is None
    assert "zero joint cost" in ratio["reason"]
    assert ratio["joint_tasks"][0]["crocodile_cost_usd"] == 0


def test_single_task_has_point_estimates_but_no_interval(tmp_path):
    group = calculate(fixture_data(tmp_path, tasks=1))["overall"]
    assert group["paired_pass_rate"]["difference"] == 0.5
    assert group["paired_pass_rate"]["ci95"] is None
    assert group["paired_pass_rate"]["status"] == "inconclusive"
    assert group["joint_cost_ratio"]["ratio"] == pytest.approx(0.5)
    assert group["joint_cost_ratio"]["ci95"] is None


@pytest.mark.parametrize("missing", ["one", "both", "whole-task"])
def test_missing_pairs_or_entire_tasks_are_rejected_against_plan(data, missing):
    if missing == "one":
        data["results"].pop(0)
    elif missing == "both":
        data["results"] = [row for row in data["results"] if not (
            row["task_id"] == "polyglot/task-0" and row["run_number"] == 1
            and row["agent_variant"] in {"crocodile", "mini-swe-agent"})]
    else:
        data["results"] = [row for row in data["results"] if row["task_id"] != "polyglot/task-0"]
    save(data)
    with pytest.raises(ValueError, match="Incomplete results"):
        calculate(data)


def test_duplicate_results_are_rejected(data):
    data["results"].append(copy.deepcopy(data["results"][0]))
    save(data)
    with pytest.raises(ValueError, match="Duplicate"):
        calculate(data)


@pytest.mark.parametrize("field, value", [
    ("model", "other/model"), ("dataset", "quixbugs"), ("run_number", 8),
    ("task_text_sha256", "b" * 64), ("step_cap", 31), ("gateway_version", "different"),
    ("date", "2026-11-14"), ("run_number", True), ("pytest_exit_code", True),
])
def test_mismatched_pairing_metadata_is_rejected(data, field, value):
    data["results"][0][field] = value
    save(data)
    with pytest.raises(ValueError):
        calculate(data)


@pytest.mark.parametrize("value", [None, "1.0", -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_cost_values_are_rejected(data, value):
    data["results"][0]["cost_usd"] = value
    save(data)
    with pytest.raises(ValueError):
        calculate(data)


@pytest.mark.parametrize("field, value", [
    ("kind", "agent_self_report"), ("logs_sha256", "0" * 64),
    ("prices_sha256", "0" * 64), ("session_id", "wrong-session"),
    ("verified", True),
])
def test_unverified_cost_provenance_is_rejected(data, field, value):
    data["results"][0]["cost_provenance"][field] = value
    save(data, refresh_proof=False)
    with pytest.raises(ValueError):
        calculate(data)


def test_declared_cost_is_recomputed_not_trusted(data):
    data["results"][0]["cost_usd"] = 0
    save(data)
    with pytest.raises(ValueError, match="recomputed charge mismatch"):
        calculate(data)


@pytest.mark.parametrize("broken", ["missing", "incomplete", "duplicate-session", "duplicate-request", "usage"])
def test_invalid_bifrost_evidence_is_rejected(data, broken):
    if broken == "missing":
        data["logs"].pop(0)
    elif broken == "incomplete":
        data["logs"][0]["complete"] = False
    elif broken == "duplicate-session":
        data["logs"][1]["session_id"] = data["logs"][0]["session_id"]
    elif broken == "duplicate-request":
        data["logs"][1]["requests"][0]["request_id"] = data["logs"][0]["requests"][0]["request_id"]
    else:
        data["logs"][0]["requests"][0]["usage"]["uncached_input"] = -1
    save(data)
    with pytest.raises(ValueError):
        calculate(data)


def test_missing_cost_and_nonfinite_prices_are_rejected(data):
    del data["results"][0]["cost_usd"]
    save(data)
    with pytest.raises(ValueError):
        calculate(data)
    data["prices"]["models"][MODEL]["output"] = float("nan")
    save(data)
    with pytest.raises(ValueError, match="Non-finite"):
        calculate(data)


def test_timeout_cannot_be_solved(data):
    data["results"][0]["timed_out"] = True
    save(data)
    with pytest.raises(ValueError, match="Interrupted/error"):
        calculate(data)


def test_plan_missing_runs_and_counts_are_rejected(data):
    data["plan"]["runs"].pop()
    save(data)
    with pytest.raises(ValueError, match="Plan is missing"):
        calculate(data)


def test_blank_and_duplicate_json_records_are_rejected(data):
    path = data["paths"]["results"]
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blank records"):
        calculate(data)
    path.write_text('{"run_id":"a","run_id":"b"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        calculate(data)


def test_test_edits_are_red_flags_without_rewriting_oracle_passes(data):
    data["results"][0]["test_edit"] = True
    save(data)
    summary = calculate(data)
    assert summary["crocodile_test_edit_runs"] == 1
    assert summary["overall"]["agents"]["crocodile"]["solved_runs"] == 4


def test_synthetic_data_cannot_publish_benchmark_reports(data, tmp_path):
    summary = calculate(data)
    assert "SYNTHETIC TEST DATA - NOT BENCHMARK RESULTS" in render_markdown(summary)
    json.dumps(summary, allow_nan=False)
    with pytest.raises(ValueError, match="Synthetic data"):
        write_reports(summary, tmp_path / "out.json", tmp_path / "out.md")
    assert not (tmp_path / "out.json").exists()


def test_cli_rejects_synthetic_publication(data, tmp_path, capsys):
    paths = data["paths"]
    with pytest.raises(SystemExit) as error:
        main([
            "--plan", str(paths["plan"]), "--results", str(paths["results"]),
            "--bifrost-logs", str(paths["logs"]), "--prices", str(paths["prices"]), "--seed", "1729",
            "--summary", str(tmp_path / "out.json"), "--markdown", str(tmp_path / "out.md"),
        ])
    assert error.value.code == 2
    assert "Synthetic data" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists()


def test_exact_fractional_pricing_uses_all_token_categories(data):
    request = data["logs"][0]["requests"][0]
    request["usage"] = dict.fromkeys(TOKENS, 250_000)
    data["prices"]["models"][MODEL] = dict.fromkeys(TOKENS, 0.1)
    for row in data["results"]:
        row["cost_usd"] /= 10
    save(data)
    agent = calculate(data)["overall"]["agents"]["crocodile"]
    assert agent["total_cost_usd"] == pytest.approx(1.6)
    assert agent["cost_per_solved_task_usd"] == pytest.approx(0.4)


def test_production_format_publication_only_in_test_temporary_directory(data, tmp_path):
    # Simulate the production discriminator; evidence remains a synthetic fixture
    # confined to pytest's temp directory, never the checked-in benchmark reports.
    data["prices"]["data_kind"] = "measured"
    for row in [*data["results"], *data["logs"]]:
        row["data_kind"] = "measured"
    save(data)
    summary = calculate(data)
    output_json, output_md = tmp_path / "test-summary.json", tmp_path / "test-report.md"
    write_reports(summary, output_json, output_md)
    assert json.loads(output_json.read_text()) == summary
    markdown = output_md.read_text(encoding="utf-8")
    assert MODEL in markdown
    assert "2026-11-13" in markdown
    assert "synthetic-v1" in markdown
    assert "10000 task resamples" in markdown
    assert "not measured zeros" in markdown
    with pytest.raises(ValueError, match="existing files"):
        write_reports(summary, output_json, output_md)


@pytest.mark.parametrize("seed", [-1, True, 1.5])
def test_invalid_statistical_seed_is_rejected(data, seed):
    with pytest.raises(ValueError, match="bootstrap seed"):
        calculate(data, seed=seed)
