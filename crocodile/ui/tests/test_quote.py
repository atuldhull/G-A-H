"""Static quote tests: repositories and prices here are synthetic, not benchmarks."""

import builtins
from decimal import Decimal
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess

import pytest

from crocodile.ui import BudgetSnapshot, RungPrice, StaticQuote, UsageEstimate, quote_task, render_quote


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src/dates.py").write_text("def parse_dates(): return None\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_dates.py").write_text(
        "def test_dates(): assert False\nasync def test_async_dates(): pass\n", encoding="utf-8"
    )
    (root / ".env").write_text("synthetic sensitive text must never be read", encoding="utf-8")
    canary = tmp_path / "executed.txt"
    payload = f"from pathlib import Path\nPath({str(canary)!r}).write_text('executed')\n"
    (root / "conftest.py").write_text(payload, encoding="utf-8")
    (root / "setup.py").write_text(payload, encoding="utf-8")
    (root / "sitecustomize.py").write_text(payload, encoding="utf-8")
    (root / "__init__.py").write_text(payload, encoding="utf-8")
    return root


@pytest.fixture
def pricing():
    # Deliberately synthetic rates; no actual provider prices are asserted.
    return {"cheap": RungPrice("test/cheap", "2", "10"),
            "strong": RungPrice("test/strong", "20", "50"),
            "local": RungPrice("test/local", "0", "0")}


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_complete_inputs_give_conditional_estimates_and_readable_output(repository, pricing):
    result = quote_task(
        "fix src/dates.py", repository, pricing=pricing,
        budget=BudgetSnapshot("0.01", "1", "2026-11-13T12:00:00+05:30"),
        usage=UsageEstimate(1000, 100), permitted_text=["tests/test_dates.py"],
    )
    assert isinstance(result, StaticQuote)
    assert result.data["method"] == "heuristic v1"
    assert result.data["estimated"] is True
    assert result.data["references"] == {"matched": ["src/dates.py"], "missing": [], "ambiguous": []}
    assert result.data["inspection"]["test_declarations"] == 2
    cheap, strong, local = result.data["rungs"]
    assert cheap["estimated_cost_usd"] == "0.003"
    assert cheap["input_usd_per_million"] == "2"
    assert cheap["estimated_within_remaining"] is True
    assert strong["estimated_cost_usd"] == "0.025"
    assert strong["estimated_within_remaining"] is False
    assert local["estimated_cost_usd"] == "0"
    assert local["estimated_within_remaining"] is True
    assert all(rung["estimated_range_usd"] is None for rung in result.data["rungs"])
    assert "heuristic" in result.rendering and "estimated" in result.rendering
    assert "within supplied remaining (estimate)" in result.rendering
    assert "no code executed" in result.rendering
    assert "80% range" not in result.rendering
    json.dumps(result.data, allow_nan=False)


def test_quote_has_no_execution_network_or_repository_write_side_effects(repository, pricing, monkeypatch):
    before = snapshot(repository)
    original_open = Path.open
    opened = []

    def read_only(path, *args, **kwargs):
        assert path in {repository / "conftest.py", repository / "tests/test_dates.py"}
        assert args == ("rb",)
        opened.append(path)
        return original_open(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Static quote attempted execution, import, or networking")

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"conftest", "sitecustomize", "setup", "src.dates"}:
            raise AssertionError("Repository module was imported")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", read_only)
        guard.setattr(subprocess, "run", forbidden)
        guard.setattr(subprocess, "Popen", forbidden)
        guard.setattr(os, "system", forbidden)
        guard.setattr(socket, "socket", forbidden)
        guard.setattr(socket, "create_connection", forbidden)
        guard.setattr(importlib, "import_module", forbidden)
        guard.setattr(builtins, "__import__", guarded_import)
        quote_task("fix src/dates.py", repository, pricing=pricing,
                   permitted_text=["conftest.py", "tests/test_dates.py"])
    assert set(opened) == {repository / "conftest.py", repository / "tests/test_dates.py"}
    assert not (repository.parent / "executed.txt").exists()
    assert snapshot(repository) == before


def test_default_quote_reads_no_repository_text(repository, monkeypatch):
    def no_open(*args, **kwargs):
        raise AssertionError("Unpermitted repository text was read")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", no_open)
        result = quote_task("fix src/dates.py", repository)
    assert result.data["inspection"]["text_files"] == []
    assert result.data["inspection"]["test_declarations"] is None
    assert all(rung["estimated_cost_usd"] is None for rung in result.data["rungs"])
    assert all(rung["estimated_within_remaining"] is None for rung in result.data["rungs"])
    assert "Budget remaining: unknown" in result.rendering
    assert "unknown (no permitted text read)" in result.rendering
    assert "$0" not in result.rendering


@pytest.mark.parametrize("task", ["", "  \n", None])
def test_empty_task_fails_before_inspection(repository, monkeypatch, task):
    def forbidden(*args, **kwargs):
        raise AssertionError("Empty task inspected repository")

    monkeypatch.setattr(os, "scandir", forbidden)
    with pytest.raises(ValueError, match="nonempty"):
        quote_task(task, repository)


def test_missing_repository_is_unknown_not_an_empty_measured_repository(tmp_path, pricing):
    result = quote_task("fix missing.py", tmp_path / "missing", pricing=pricing,
                        usage=UsageEstimate(1000, 100), budget=BudgetSnapshot("1"))
    assert result.data["inspection"]["status"] == "unavailable"
    assert not result.data["inspection"]["complete"]
    assert "partial/unavailable" in result.rendering
    assert all(rung["estimated_cost_usd"] is None for rung in result.data["rungs"])


def test_repository_file_is_not_treated_as_directory(repository):
    result = quote_task("fix dates.py", repository / "src/dates.py")
    assert result.data["inspection"]["status"] == "unavailable"


def test_missing_and_ambiguous_file_names_block_budget_comparison(repository, pricing):
    (repository / "tests/dates.py").write_text("# synthetic duplicate basename", encoding="utf-8")
    result = quote_task("fix dates.py and missing.py", repository, pricing=pricing,
                        usage=UsageEstimate(1000, 100), budget=BudgetSnapshot("1"))
    assert result.data["references"]["ambiguous"] == ["dates.py"]
    assert result.data["references"]["missing"] == ["missing.py"]
    assert all(rung["estimated_within_remaining"] is None for rung in result.data["rungs"])
    assert "Ambiguous file references" in result.rendering


def test_windows_relative_task_and_permitted_paths_work(repository):
    result = quote_task(r"fix src\dates.py", repository,
                        permitted_text=[r"tests\test_dates.py"])
    assert result.data["references"]["matched"] == ["src/dates.py"]
    assert result.data["inspection"]["test_declarations"] == 2


@pytest.mark.parametrize("missing", ["prices", "partial-price", "usage", "budget", "remaining"])
def test_absent_cost_or_budget_inputs_do_not_claim_fit(repository, pricing, missing):
    prices = pricing.copy()
    usage = UsageEstimate(1000, 100)
    budget = BudgetSnapshot("1")
    if missing == "prices":
        prices = None
    elif missing == "partial-price":
        prices = {"cheap": RungPrice("test/cheap", "2", None)}
    elif missing == "usage":
        usage = None
    elif missing == "budget":
        budget = None
    else:
        budget = BudgetSnapshot(None, "1")
    result = quote_task("fix src/dates.py", repository, pricing=prices, usage=usage, budget=budget)
    assert all(rung["estimated_within_remaining"] is None for rung in result.data["rungs"])
    if missing in {"prices", "partial-price", "usage"}:
        assert all(rung["estimated_cost_usd"] is None for rung in result.data["rungs"])


def test_local_is_not_assumed_free(repository, pricing):
    result = quote_task("fix src/dates.py", repository, pricing={"cheap": pricing["cheap"]},
                        usage=UsageEstimate(1000, 100), budget=BudgetSnapshot("1"))
    assert result.data["rungs"][2]["estimated_cost_usd"] is None
    assert result.data["rungs"][2]["estimated_within_remaining"] is None


def test_explicit_zero_budget_and_zero_usage_are_not_unknown(repository, pricing):
    result = quote_task("fix src/dates.py", repository, pricing=pricing,
                        usage=UsageEstimate(0, 0), budget=BudgetSnapshot(0, 0))
    assert result.data["budget"]["remaining_usd"] == "0"
    assert all(rung["estimated_cost_usd"] == "0" for rung in result.data["rungs"])
    assert all(rung["estimated_within_remaining"] is True for rung in result.data["rungs"])


@pytest.mark.parametrize("value", ["NaN", float("inf"), -1, True, "bad", "1e-10000"])
def test_invalid_prices_are_rejected(repository, value):
    with pytest.raises(ValueError):
        quote_task("fix dates.py", repository, pricing={"cheap": RungPrice("test/model", value, 1)})


@pytest.mark.parametrize("budget", [BudgetSnapshot(-1), BudgetSnapshot("2", "1"), BudgetSnapshot(float("nan"))])
def test_invalid_budgets_are_rejected(repository, budget):
    with pytest.raises(ValueError):
        quote_task("fix dates.py", repository, budget=budget)


@pytest.mark.parametrize("usage", [UsageEstimate(-1, 1), UsageEstimate(True, 1), UsageEstimate(1, 1.5)])
def test_invalid_usage_is_rejected(repository, usage):
    with pytest.raises(ValueError):
        quote_task("fix dates.py", repository, usage=usage)


@pytest.mark.parametrize("path", ["../outside.py", "/absolute.py", "C:/drive.py", ".env", ".git/config", "private.key"])
def test_unpermitted_text_paths_are_not_opened(repository, monkeypatch, path):
    def no_open(*args, **kwargs):
        raise AssertionError("Forbidden text was read")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", no_open)
        result = quote_task("inspect task", repository, permitted_text=[path])
    assert result.data["inspection"]["text_files"][0]["status"] == "blocked"
    assert result.data["inspection"]["complete"] is False


def test_missing_and_binary_permitted_text_are_reported(repository):
    (repository / "binary.py").write_bytes(b"\x00binary")
    result = quote_task("inspect task", repository, permitted_text=["missing.py", "binary.py"])
    assert all(item["status"] == "unavailable" for item in result.data["inspection"]["text_files"])
    assert result.data["inspection"]["test_declarations"] is None


def test_text_and_filename_limits_report_partial_inspection(repository, pricing):
    result = quote_task("fix src/dates.py", repository, max_text_bytes=4,
                        permitted_text=["conftest.py", "tests/test_dates.py"], pricing=pricing,
                        usage=UsageEstimate(1000, 100), budget=BudgetSnapshot("1"))
    assert all(item["status"] == "limit_reached" for item in result.data["inspection"]["text_files"])
    assert not result.data["inspection"]["complete"]
    assert all(rung["estimated_within_remaining"] is None for rung in result.data["rungs"])
    limited = quote_task("inspect task", repository, max_entries=1)
    assert not limited.data["inspection"]["complete"]
    assert any("Filename inspection limit" in warning for warning in limited.data["inspection"]["warnings"])


def test_rendering_is_ascii_when_requested_and_escapes_controls(repository):
    result = quote_task("inspect task", repository)
    data = {**result.data, "repository": "repo/na\u00efve\x1b[31m\u202efile"}
    unicode_render = render_quote(data)
    ascii_render = render_quote(data, ascii_only=True)
    assert "heuristic" in unicode_render and "estimated" in ascii_render
    assert "\x1b" not in unicode_render and "\u202e" not in unicode_render
    assert "\\u001b" in unicode_render and "\\u202e" in unicode_render
    assert ascii_render.isascii()
    assert "\\xef" in ascii_render
    assert quote_task("inspect task", repository, ascii_only=True).rendering.isascii()


def test_allowed_rungs_enable_local_only_rendering_without_routing(repository, pricing):
    result = quote_task("inspect task", repository, pricing=pricing,
                        usage=UsageEstimate(100, 10), rungs=("local",))
    assert [rung["rung"] for rung in result.data["rungs"]] == ["local"]
    assert "test/cheap" not in result.rendering
    assert "test/strong" not in result.rendering


def test_explicit_decimal_inputs_remain_json_serializable(repository):
    result = quote_task("inspect task", repository,
                        pricing={"cheap": RungPrice("test/model", Decimal("0.1"), Decimal("0.2"))},
                        usage=UsageEstimate(1, 1), budget=BudgetSnapshot(Decimal("0.0000003")))
    assert result.data["rungs"][0]["estimated_cost_usd"] == "0.0000003"
    assert result.data["rungs"][0]["estimated_within_remaining"] is True
    json.dumps(result.data, allow_nan=False)


@pytest.mark.parametrize("path", [r"\\server\share\repo", "//server/share/repo"])
def test_network_repository_paths_are_rejected_without_filesystem_access(monkeypatch, path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network path triggered filesystem inspection")

    monkeypatch.setattr(Path, "lstat", forbidden)
    result = quote_task("inspect task", path)
    assert result.data["inspection"]["status"] == "unavailable"
    assert "Network/UNC" in result.rendering


@pytest.mark.parametrize("options", [
    {"permitted_text": None}, {"permitted_text": "conftest.py"},
    {"permitted_text": ["conftest.py"] * 33},
    {"rungs": None}, {"rungs": "cheap"}, {"rungs": ["cheap", "cheap"]},
    {"rungs": ["typo"]}, {"pricing": {"typo": None}},
    {"max_entries": 0}, {"max_text_bytes": True},
])
def test_invalid_options_fail_clearly(repository, options):
    with pytest.raises(ValueError):
        quote_task("inspect task", repository, **options)


@pytest.mark.parametrize("repository", [None, ""])
def test_missing_path_argument_does_not_default_to_current_directory(repository):
    with pytest.raises(ValueError, match="explicit local"):
        quote_task("inspect task", repository)
