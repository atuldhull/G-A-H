"""Synthetic SQLite: supplied field mapping, not a verified physical database DDL."""

from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path
import sqlite3

import pytest

from bench.bifrost_export import (
    COLUMNS, CONVENTION, REVIEW_FLAGS, _bytes, _json, _prices, _sessions,
    Incomplete, _native_prices, _rates, combine_exports, export_session, main, write_export,
)


@pytest.fixture
def sample(tmp_path):
    db = tmp_path / "logs.db"
    connection = sqlite3.connect(db)
    # The user supplied field names, not SQL types or constraints. Types here are
    # explicitly synthetic. No guessed uniqueness constraint hides duplicate tests.
    columns = ",".join(name + (" INTEGER" if name in {
        "prompt_tokens", "completion_tokens", "total_tokens", "cached_read_tokens",
    } else " TEXT") for name in COLUMNS)
    connection.execute("CREATE TABLE logs (" + columns + ", prompt TEXT, payload TEXT)")
    connection.commit()
    connection.close()
    prices = tmp_path / "native-prices.yaml"
    prices.write_bytes(_bytes({"anthropic/synthetic": {"tiers": [{
        "upto": None, "in": 2, "out": 4, "cache_read": Decimal("0.5"),
        "cache_write_5m": Decimal("2.5"), "cache_write_1h": 4,
    }], "max_out": 4096}}))
    selection = {
        "gateway_instance_id": "synthetic-gateway-A", "gateway_version": "2.5.1",
        "data_kind": "synthetic", "run_id": "polyglot/synthetic/crocodile/run-1",
        "session_id": "agent-session-1", "virtual_key_id": "internal-vk-1", "virtual_key_name": "bench",
        "model": "anthropic/synthetic", "date": "2026-11-14", "request_ids": ["request-1"],
        "review": {**dict.fromkeys(REVIEW_FLAGS, True), "reviewer": "synthetic reviewer",
                   "evidence_reference": "synthetic closed-session request inventory",
                   "usage_convention": CONVENTION},
    }
    row = {
        "session_id": "agent-session-1", "id": "request-1", "parent_request_id": None,
        "virtual_key_name": "bench", "virtual_key_id": "internal-vk-1", "provider": "anthropic",
        "model": "anthropic/synthetic", "served_model": "synthetic", "prompt_tokens": 100,
        "completion_tokens": 20, "total_tokens": 120, "cached_read_tokens": 30,
        "status": "success", "timestamp": "2026-11-14T10:00:00Z", "cost": "0.000235",
        "token_usage": _bytes({
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 0},
            "cost": {"input_cost": Decimal("0.000155"), "output_cost": Decimal("0.00008"),
                     "total_cost": Decimal("0.000235")},
        }).decode("utf-8"),
    }
    return {"db": db, "prices": prices, "selection": selection, "row": row,
            "receipt": {"session": "agent-session-1", "cost_usd": Decimal("0.000235")}}


def insert(sample, *rows):
    with sqlite3.connect(sample["db"]) as connection:
        for row in rows or [sample["row"]]:
            connection.execute("INSERT INTO logs (" + ",".join(COLUMNS) + ",prompt,payload) VALUES ("
                               + ",".join("?" for _ in range(len(COLUMNS) + 2)) + ")",
                               [row[key] for key in COLUMNS] + ["SYNTHETIC-DO-NOT-EXPORT-PROMPT",
                                                              "SYNTHETIC-DO-NOT-EXPORT-PAYLOAD"])


def export(sample, **changes):
    return export_session(sample["db"], sample["prices"], changes.get("selection", sample["selection"]),
                          changes.get("receipt", sample["receipt"]))


def test_cache_read_success_and_strict_reporter_compatibility_without_db_writes(sample, tmp_path):
    insert(sample)
    before = sample["db"].read_bytes()
    result = export(sample)
    assert result["complete"], result["issues"]
    assert result["computed_cost_usd"] == Fraction(235, 1_000_000)
    assert result["session"]["requests"][0]["usage"] == {
        "uncached_input": 70, "cache_read_input": 30, "cache_write_input": 0, "output": 20,
    }
    assert result["receipt_comparison"]["above_one_percent"] is False
    output = write_export(result, tmp_path / "export")
    prices = _prices(_json((output / "prices.yaml").read_bytes()))
    rows = [_json(line) for line in (output / "evidence.jsonl").read_bytes().splitlines()]
    verified = _sessions(rows, prices)
    assert verified[sample["selection"]["run_id"]][1] == result["computed_cost_usd"]
    assert sample["db"].read_bytes() == before
    assert not any(Path(str(sample["db"]) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
    for path in output.iterdir():
        assert b"DO-NOT-EXPORT" not in path.read_bytes()
    assert result["source"]["physical_version_verified"] is False


def test_no_cache_usage_is_supported_when_both_cache_counts_are_explicit_zero(sample):
    usage = _json(sample["row"]["token_usage"].encode())
    usage["prompt_tokens_details"]["cached_tokens"] = 0
    sample["row"].update(cached_read_tokens=0, token_usage=_bytes(usage).decode())
    insert(sample)
    result = export(sample)
    assert result["complete"] and result["computed_cost_usd"] == Fraction(280, 1_000_000)


def test_exact_scope_selection_and_duplicate_deduplication(sample):
    other = {**sample["row"], "id": "another-request", "virtual_key_id": "other-vk"}
    case = {**sample["row"], "id": "case-request", "session_id": "AGENT-SESSION-1"}
    insert(sample, sample["row"], sample["row"], other, case)
    result = export(sample)
    assert result["complete"] and result["duplicate_rows"] == 1
    assert len(result["session"]["requests"]) == 1
    assert result["computed_cost_usd"] == Fraction(235, 1_000_000)


@pytest.mark.parametrize("change", [{"completion_tokens": 21}, {"status": "error"},
                                    {"virtual_key_id": "another-vk"}])
def test_conflicting_ids_and_attribution_are_incomplete(sample, change):
    insert(sample, sample["row"], {**sample["row"], **change})
    result = export(sample)
    assert not result["complete"] and result["computed_cost_usd"] is None
    assert result["session"] is None


@pytest.mark.parametrize("kind", ["missing_json", "missing_cache", "missing_scalar", "inconsistent_total",
                                  "inconsistent_read", "write_ttl", "negative", "unknown_model", "missing_served",
                                  "status", "parent", "naive_timestamp", "cost_columns", "fallback"])
def test_unsupported_cases_never_become_publishable(sample, tmp_path, kind):
    row = sample["row"]
    usage = _json(row["token_usage"].encode())
    if kind == "missing_json":
        row["token_usage"] = None
    elif kind == "missing_cache":
        del usage["prompt_tokens_details"]["cache_write_tokens"]
    elif kind == "missing_scalar":
        row["prompt_tokens"] = None
    elif kind == "inconsistent_total":
        row["total_tokens"] = 121
    elif kind == "inconsistent_read":
        row["cached_read_tokens"] = 29
    elif kind == "write_ttl":
        usage["prompt_tokens_details"]["cache_write_tokens"] = 5
    elif kind == "negative":
        usage["completion_tokens"] = -1
    elif kind == "unknown_model":
        row["served_model"] = "unknown-model"
    elif kind == "missing_served":
        row["served_model"] = None
    elif kind == "status":
        row["status"] = "completed"
    elif kind == "parent":
        row["parent_request_id"] = "parent-request"
    elif kind == "naive_timestamp":
        row["timestamp"] = "2026-11-14T10:00:00"
    elif kind == "cost_columns":
        row["cost"] = "0.1"
    elif kind == "fallback":
        row["model"] = "anthropic/another-requested-model"
    if kind != "missing_json":
        row["token_usage"] = _bytes(usage).decode()
    insert(sample)
    result = export(sample)
    assert not result["complete"] and result["computed_cost_usd"] is None
    output = write_export(result, tmp_path / "blocked")
    assert (output / "evidence.jsonl").read_bytes() == b""
    assert (output / "costs.jsonl").read_bytes() == b""
    with pytest.raises(ValueError, match="incomplete"):
        combine_exports([output], tmp_path / "must-not-publish")


def test_retry_parent_and_status_relationships_are_retained_but_incomplete(sample):
    parent = {**sample["row"], "id": "z-parent", "status": "error"}
    child = {**sample["row"], "id": "a-child", "parent_request_id": "z-parent"}
    sample["selection"]["request_ids"] = ["z-parent", "a-child"]
    insert(sample, parent, child)
    result = export(sample)
    assert not result["complete"]
    assert [(r["raw_request_id"], r["parent_request_id"], r["status"]) for r in result["requests"]] == [
        ("a-child", "z-parent", "success"), ("z-parent", None, "error"),
    ]


@pytest.mark.parametrize("issue", ["missing_request", "extra_request", "vk_review", "flush", "semantics"])
def test_completeness_requires_independent_reviewed_inventory(sample, issue):
    insert(sample)
    selection = sample["selection"]
    if issue == "missing_request":
        selection["request_ids"].append("not-yet-flushed")
    elif issue == "extra_request":
        selection["request_ids"] = []
    elif issue == "vk_review":
        selection["review"]["vk_binding_verified"] = False
    elif issue == "flush":
        selection["review"]["log_flush_verified"] = False
    else:
        selection["review"]["usage_convention"] = "unknown"
    assert not export(sample)["complete"]


@pytest.mark.parametrize("price_case", ["tiered", "bounded_tier", "missing_rate", "negative_rate"])
def test_unsupported_prices_are_incomplete(sample, price_case):
    insert(sample)
    prices = _json(sample["prices"].read_bytes())
    tier = prices["anthropic/synthetic"]["tiers"][0]
    if price_case == "tiered":
        prices["anthropic/synthetic"]["tiers"].append(deepcopy(tier))
    elif price_case == "bounded_tier":
        tier["upto"] = 100000
    elif price_case == "missing_rate":
        del tier["cache_read"]
    else:
        tier["out"] = -1
    sample["prices"].write_bytes(_bytes(prices))
    assert not export(sample)["complete"]


def test_receipt_mismatch_does_not_replace_log_cost_and_one_percent_is_strict(sample):
    insert(sample)
    for receipt, mismatch in [(Decimal("0.1"), True), (Decimal("0.00023735"), False),
                              (Decimal("0.0002373501"), True)]:
        result = export(sample, receipt={"session": "agent-session-1", "cost_usd": receipt})
        assert result["complete"] and result["computed_cost_usd"] == Fraction(235, 1_000_000)
        assert result["receipt_comparison"]["above_one_percent"] is mismatch
    assert export(sample, receipt={"session": "agent-session-1", "cost_usd": None})["complete"]


def test_empty_session_is_only_known_zero_with_review_and_supported_price(sample):
    sample["selection"]["request_ids"] = []
    result = export(sample)
    assert result["complete"] and result["computed_cost_usd"] == 0
    assert result["receipt_comparison"]["above_one_percent"] is True
    sample["selection"]["review"]["session_finished"] = False
    assert not export(sample)["complete"]


def test_wal_sidecars_are_refused_without_modifying_any_file(sample):
    insert(sample)
    wal = Path(str(sample["db"]) + "-wal")
    wal.write_bytes(b"synthetic snapshot-not-ready marker")
    before = sample["db"].read_bytes()
    assert not export(sample)["complete"]
    assert sample["db"].read_bytes() == before and wal.read_bytes().startswith(b"synthetic")


def test_same_snapshot_cannot_be_relabelled_as_two_origins(sample, tmp_path):
    insert(sample)
    first = write_export(export(sample), tmp_path / "one")
    changed = deepcopy(sample["selection"])
    changed.update(gateway_instance_id="another-gateway", run_id="another-run")
    second = write_export(export(sample, selection=changed), tmp_path / "two")
    with pytest.raises(ValueError, match="conflicting gateway origins"):
        combine_exports([first, second], tmp_path / "not-independent")


def test_native_yaml_preserves_decimal_prices_and_rejects_duplicate_keys():
    pytest.importorskip("yaml", reason="Optional native-YAML parser unavailable; JSON-native prices covered separately")
    raw = b"provider/model:\n  tiers:\n    - {upto: null, in: 0.1, out: 0.4, cache_read: 0.01, cache_write_5m: 0.125}\n"
    assert _rates(_native_prices(raw), "provider/model")["uncached_input"] == Fraction(1, 10)
    with pytest.raises(Incomplete):
        _native_prices(raw + raw)


def test_missing_physical_column_is_not_treated_as_the_supplied_mapping(sample):
    with sqlite3.connect(sample["db"]) as connection:
        connection.execute("ALTER TABLE logs DROP COLUMN served_model")
    result = export(sample)
    assert not result["complete"] and result["issues"] == ["supplied_mapping_not_present"]


def test_four_gateway_origins_combine_without_id_collisions_and_reject_overlaps(sample, tmp_path):
    insert(sample)
    bundles = []
    for number in range(4):
        # Distinct synthetic snapshots/origins, retaining colliding native IDs.
        with sqlite3.connect(sample["db"]) as connection:
            connection.execute("UPDATE logs SET timestamp=?", (f"2026-11-14T10:00:0{number}Z",))
        selection = deepcopy(sample["selection"])
        selection["gateway_instance_id"] = f"synthetic-gateway-{number}"
        selection["run_id"] = f"polyglot/task-{number}/crocodile/run-1"
        bundles.append(write_export(export(sample, selection=selection), tmp_path / f"export-{number}"))
    combined = combine_exports(bundles, tmp_path / "combined")
    rows = [_json(line) for line in (combined / "evidence.jsonl").read_bytes().splitlines()]
    assert len({row["session_id"] for row in rows}) == 4
    assert len({row["requests"][0]["request_id"] for row in rows}) == 4
    costs = [_json(line) for line in (combined / "costs.jsonl").read_bytes().splitlines()]
    assert all(row["cost_provenance"]["logs_sha256"] == hashlib.sha256(
        (combined / "evidence.jsonl").read_bytes()).hexdigest() for row in costs)
    with pytest.raises(ValueError, match="Duplicate"):
        combine_exports([bundles[0], bundles[0]], tmp_path / "overlap")
    evidence = bundles[0] / "evidence.jsonl"
    evidence.write_bytes(evidence.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hashes"):
        combine_exports([bundles[0]], tmp_path / "tampered")


def test_cli_exports_safely_without_printing_rows(sample, tmp_path, capsys):
    insert(sample)
    selection, receipt = tmp_path / "selection.json", tmp_path / "receipt.json"
    selection.write_bytes(_bytes(sample["selection"]))
    receipt.write_bytes(_bytes(sample["receipt"]))
    assert main(["export", "--db", str(sample["db"]), "--prices", str(sample["prices"]),
                 "--selection", str(selection), "--receipt", str(receipt), "--output", str(tmp_path / "cli")]) == 0
    assert capsys.readouterr().out == "Complete cost evidence.\n"
