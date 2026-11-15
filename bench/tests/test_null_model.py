"""Reviewed per-request route joins, synthetic SQLite only; never paid requests."""

from copy import deepcopy
import sqlite3

import pytest

from bench import bifrost_export as exporter
from bench.tests.test_bifrost_export import sample as _sample, insert, export


@pytest.fixture
def sample(tmp_path):
    return _sample.__wrapped__(tmp_path)


@pytest.fixture
def route(sample):
    row = sample["row"]
    row["served_model"] = None
    row.update(dict.fromkeys(exporter.NULL_ROUTE_FIELDS))
    row.update(dict.fromkeys(exporter.ZERO_ROUTE_FIELDS, 0))
    proof = {"request_id": row["id"], "session_id": row["session_id"],
             "virtual_key_name": row["virtual_key_name"], "provider": row["provider"],
             "routing_info": {"provider": "anthropic", "requested_provider": "anthropic",
                              "requested_model": row["model"], "model": row["model"]},
             "resolved_model_used": row["model"]}
    return row, proof


def test_supported_null_model_is_resolved_without_mutating_raw_row(route):
    row, proof = route
    before = deepcopy(row)
    assert exporter._model(row, proof) == "anthropic/synthetic"
    assert row == before and row["served_model"] is None


@pytest.mark.parametrize("field,value", [
    *((field, "ambiguous") for field in exporter.NULL_ROUTE_FIELDS),
    ("fallback_index", 1), ("number_of_retries", 1), ("fallback_index", False),
    ("number_of_retries", "0"), ("fallback_index", -1),
])
def test_every_ambiguous_scalar_is_rejected(route, field, value):
    row, proof = route
    row[field] = value
    with pytest.raises(exporter.Incomplete):
        exporter._model(row, proof)


@pytest.mark.parametrize("field", [*exporter.NULL_ROUTE_FIELDS, *exporter.ZERO_ROUTE_FIELDS])
def test_missing_route_columns_are_not_assumed_zero_or_null(route, field):
    row, proof = route
    del row[field]
    with pytest.raises(exporter.Incomplete):
        exporter._model(row, proof)


@pytest.mark.parametrize("field", ["request_id", "session_id", "virtual_key_name", "provider", "resolved_model_used"])
def test_proof_must_join_exact_request_and_resolved_model(route, field):
    row, proof = route
    proof[field] = "other"
    with pytest.raises(exporter.Incomplete):
        exporter._model(row, proof)


@pytest.mark.parametrize("field", ["provider", "requested_provider", "requested_model", "model"])
def test_each_response_routing_field_must_agree(route, field):
    row, proof = route
    proof["routing_info"][field] = "other"
    with pytest.raises(exporter.Incomplete):
        exporter._model(row, proof)


def test_no_response_evidence_is_not_publishable(route):
    row, _ = route
    with pytest.raises(exporter.Incomplete):
        exporter._model(row)


def test_sqlite_export_reads_observed_optional_columns_and_keeps_raw_null(sample, route):
    row, proof = route
    with sqlite3.connect(sample["db"]) as db:
        for field in exporter.NULL_ROUTE_FIELDS:
            db.execute(f"ALTER TABLE logs ADD COLUMN {field} TEXT")
        for field in exporter.ZERO_ROUTE_FIELDS:
            db.execute(f"ALTER TABLE logs ADD COLUMN {field} INTEGER DEFAULT 0")
    insert(sample)
    sample["selection"]["routing_evidence"] = {
        "schema_version": 1, "source_sha256": "a" * 64, "requests": {row["id"]: proof}}
    before = sample["db"].read_bytes()
    result = export(sample)
    assert result["complete"], result["issues"]
    assert result["requests"][0]["served_model"] is None
    assert result["requests"][0]["model_resolution"] == exporter.NULL_MODEL_RULE
    assert sample["db"].read_bytes() == before
    del sample["selection"]["routing_evidence"]["requests"][row["id"]]
    assert not export(sample)["complete"]


@pytest.mark.parametrize("change", ["hash", "unknown-request", "version"])
def test_invalid_sidecar_cannot_produce_a_cost(sample, route, change):
    row, proof = route
    insert(sample)
    evidence = {"schema_version": 1, "source_sha256": "a" * 64, "requests": {row["id"]: proof}}
    if change == "hash":
        evidence["source_sha256"] = "unverified"
    elif change == "version":
        evidence["schema_version"] = True
    else:
        evidence["requests"]["another-request"] = proof
    sample["selection"]["routing_evidence"] = evidence
    result = export(sample)
    assert not result["complete"] and result["computed_cost_usd"] is None
