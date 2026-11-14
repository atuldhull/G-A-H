"""Read-only, fail-closed cost evidence from the conversation-supplied logs mapping."""

import argparse
import base64
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sqlite3

from bench.plan import _object
from bench.report import _json, _prices, _sessions


COLUMNS = (
    "session_id", "id", "parent_request_id", "virtual_key_name", "virtual_key_id",
    "provider", "model", "served_model", "prompt_tokens", "completion_tokens",
    "total_tokens", "cached_read_tokens", "token_usage", "cost", "status", "timestamp",
)
REVIEW_FLAGS = (
    "vk_binding_verified", "session_finished", "log_flush_verified",
    "request_inventory_complete", "retention_verified", "quiescent_snapshot_verified",
    "gateway_origin_verified",
)
CONVENTION = "prompt-includes-cache;total=prompt+completion"


class Incomplete(ValueError):
    """A safe diagnostic code, never raw SQL, JSON, payload or exception text."""


def _text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise Incomplete("missing_or_invalid_identifier")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise Incomplete("missing_or_invalid_usage")
    return value


def _money(value):
    if isinstance(value, float):  # SQLite REAL, not JSON input.
        value = Decimal(str(value))
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except ArithmeticError:
            raise Incomplete("invalid_cost_or_rate") from None
    if type(value) not in (int, Decimal) or not Decimal(value).is_finite() or value < 0:
        raise Incomplete("invalid_cost_or_rate")
    return Fraction(value)


def _encode(value):
    """Write exact terminating monetary fractions as JSON numbers, not floats."""
    if isinstance(value, (Decimal, Fraction)):
        number = Fraction(value)
        denominator, twos, fives = number.denominator, 0, 0
        while denominator % 2 == 0:
            twos += 1
            denominator //= 2
        while denominator % 5 == 0:
            fives += 1
            denominator //= 5
        if denominator != 1:
            raise ValueError("Nonterminating JSON number")
        places = max(twos, fives)
        scaled = abs(number.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
        digits = str(scaled).rjust(places + 1, "0")
        result = digits if not places else digits[:-places] + "." + digits[-places:]
        return ("-" if number < 0 else "") + result
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + _encode(v) for k, v in sorted(value.items())) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(v) for v in value) + "]"
    return json.dumps(value, allow_nan=False, ensure_ascii=True)


def _bytes(value):
    return (_encode(value) + "\n").encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _qualified(origin, raw):
    # Reversible pair encoding; never qualify by exporting machine/snapshot.
    encoded = json.dumps([origin, raw], separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return "bf:" + base64.urlsafe_b64encode(encoded).decode("ascii")


def _native_prices(raw):
    try:
        return _json(raw)
    except (ValueError, UnicodeError):
        # JSON-native fixtures need no extra dependency. The application's native
        # YAML uses its existing PyYAML dependency, loaded only when necessary.
        try:
            import yaml
        except ImportError:
            raise Incomplete("pyyaml_required_for_native_yaml") from None

        class Loader(yaml.SafeLoader):
            pass

        def decimal(loader, node):
            return Decimal(loader.construct_scalar(node))

        def mapping(loader, node):
            return _object(loader.construct_pairs(node))

        Loader.add_constructor("tag:yaml.org,2002:float", decimal)
        Loader.add_constructor("tag:yaml.org,2002:map", mapping)
        try:
            return yaml.load(raw.decode("utf-8"), Loader=Loader)
        except (ValueError, ArithmeticError, UnicodeError, yaml.YAMLError):
            raise Incomplete("invalid_native_prices") from None


def _rates(prices, model):
    if not isinstance(prices, dict):
        raise Incomplete("invalid_native_prices")
    if model in prices:
        entry = prices[model]
    else:
        matches = [value for pattern, value in prices.items()
                   if isinstance(pattern, str) and pattern.endswith("/*")
                   and model.startswith(pattern[:-1])]
        if len(matches) != 1:
            raise Incomplete("unknown_or_ambiguous_model_price")
        entry = matches[0]
    tiers = entry.get("tiers") if isinstance(entry, dict) else None
    if (not isinstance(tiers, list) or len(tiers) != 1 or not isinstance(tiers[0], dict)
            or tiers[0].get("upto", "missing") is not None):
        raise Incomplete("tiered_pricing_unsupported")
    tier = tiers[0]
    keys = {"uncached_input": "in", "output": "out", "cache_read_input": "cache_read",
            "cache_write_input": "cache_write_5m"}
    try:
        return {key: _money(tier[source]) for key, source in keys.items()}
    except (KeyError, TypeError):
        raise Incomplete("missing_model_rate") from None


def _usage(row):
    try:
        raw = row["token_usage"]
        if not isinstance(raw, str) or not raw.strip():
            raise Incomplete("missing_or_invalid_usage")
        usage = _json(raw.encode("utf-8"))
        prompt, output, total = (_count(usage[key]) for key in
                                 ("prompt_tokens", "completion_tokens", "total_tokens"))
        details = usage["prompt_tokens_details"]
        read, write = _count(details["cached_tokens"]), _count(details["cache_write_tokens"])
        scalar = [_count(row[key]) for key in
                  ("prompt_tokens", "completion_tokens", "total_tokens", "cached_read_tokens")]
        if scalar != [prompt, output, total, read] or total != prompt + output or read + write > prompt:
            raise Incomplete("inconsistent_scalar_json_usage")
        if write != 0:
            raise Incomplete("cache_write_ttl_unverified")
        costs = usage.get("cost")
        if row["cost"] is not None:
            _money(row["cost"])
        if costs is not None:
            incoming, outgoing, logged = (_money(costs[key]) for key in
                                          ("input_cost", "output_cost", "total_cost"))
            if incoming + outgoing != logged:
                raise Incomplete("inconsistent_logged_cost")
            if row["cost"] is not None and _money(row["cost"]) != logged:
                raise Incomplete("inconsistent_logged_cost")
        return {"uncached_input": prompt - read - write, "cache_read_input": read,
                "cache_write_input": write, "output": output}
    except (KeyError, TypeError, ValueError, UnicodeError, ArithmeticError) as error:
        if isinstance(error, Incomplete):
            raise
        raise Incomplete("missing_or_invalid_usage") from None


def _model(row):
    provider, served = _text(row["provider"]), _text(row["served_model"])
    model = served if "/" in served else provider + "/" + served
    if not model.startswith(provider + "/"):
        raise Incomplete("inconsistent_served_provider")
    return model


def _selection(selection):
    for key in ("run_id", "session_id", "gateway_instance_id", "virtual_key_id", "virtual_key_name",
                "model", "date"):
        _text(selection[key])
    if selection["gateway_version"] != "2.5.1" or selection["data_kind"] not in {"synthetic", "measured"}:
        raise Incomplete("unsupported_version_or_data_kind")
    if date.fromisoformat(selection["date"]).isoformat() != selection["date"]:
        raise Incomplete("invalid_date")
    review = selection["review"]
    _text(review["reviewer"])
    _text(review["evidence_reference"])
    if any(review.get(flag) is not True for flag in REVIEW_FLAGS):
        raise Incomplete("session_completeness_or_vk_binding_unverified")
    if review.get("usage_convention") != CONVENTION:
        raise Incomplete("usage_semantics_unverified")
    ids = selection["request_ids"]
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise Incomplete("missing_reviewed_request_inventory")
    for item in ids:
        _text(item)
    if len(ids) != len(set(ids)):
        raise Incomplete("duplicate_inventory_request_id")


def _read(db, selection):
    """Only an explicitly reviewed quiescent snapshot; never touch WAL/SHM."""
    path = Path(db).absolute()
    if not path.is_file() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise Incomplete("snapshot_missing_or_linked")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise Incomplete("consistent_standalone_snapshot_required")
    before = _sha(path.read_bytes())
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        kind = connection.execute("SELECT type FROM sqlite_master WHERE name='logs'").fetchone()
        columns = [(r[1], r[2], r[3], r[5]) for r in connection.execute("PRAGMA table_info(logs)")]
        if kind != ("table",) or not set(COLUMNS) <= {c[0] for c in columns}:
            raise Incomplete("supplied_mapping_not_present")
        connection.row_factory = sqlite3.Row
        selected = connection.execute(
            "SELECT " + ",".join(COLUMNS) + " FROM logs WHERE session_id COLLATE BINARY = ? "
            "AND virtual_key_id COLLATE BINARY = ? AND virtual_key_name COLLATE BINARY = ?",
            (selection["session_id"], selection["virtual_key_id"], selection["virtual_key_name"]),
        ).fetchall()
        rows = [dict(row) for row in selected]
        for row in rows:
            # A request ID shared by other attribution scopes is ambiguous.
            scopes = connection.execute(
                "SELECT DISTINCT session_id,virtual_key_id,virtual_key_name FROM logs WHERE id COLLATE BINARY = ?",
                (row["id"],),
            ).fetchall()
            if len(scopes) != 1:
                raise Incomplete("request_id_attribution_ambiguous")
    finally:
        connection.close()
    if (any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
            or _sha(path.read_bytes()) != before):
        raise Incomplete("snapshot_changed_during_read")
    return rows, {"database_sha256": before, "columns": columns,
                  "schema_sha256": _sha(_bytes(columns)), "physical_version_verified": False}


def _compare(receipt_cost, computed):
    if receipt_cost is None:
        return {"status": "unavailable", "above_one_percent": None}
    try:
        receipt = _money(receipt_cost)
    except Incomplete:
        return {"status": "unavailable", "above_one_percent": None}
    mismatch = receipt != 0 if computed == 0 else abs(receipt - computed) > computed / 100
    return {"status": "mismatch" if mismatch else "within_one_percent",
            "above_one_percent": mismatch, "receipt_cost_usd": receipt,
            "absolute_difference_usd": abs(receipt - computed)}


def export_session(db, prices_path, selection, receipt):
    """Build a bundle in memory. Incomplete bundles contain no reporter row/rates."""
    result = {"schema_version": 1, "complete": False, "issues": [], "session": None,
              "prices": None, "computed_cost_usd": None, "receipt_comparison": {"status": "unavailable"},
              "requests": [], "duplicate_rows": 0, "source": {},
              "schema_evidence": "conversation-supplied-redacted-v2.5.1-field-mapping"}
    try:
        _selection(selection)
        if not isinstance(receipt, dict):
            raise Incomplete("invalid_agent_receipt")
        if receipt.get("session") != selection["session_id"]:
            raise Incomplete("receipt_session_mismatch")
        raw_prices = Path(prices_path).read_bytes()
        prices = _native_prices(raw_prices)
        rows, source = _read(db, selection)
        result["source"] = {**source, "native_prices_sha256": _sha(raw_prices),
                             "gateway_instance_id": selection["gateway_instance_id"],
                             "selection_sha256": _sha(_bytes(selection)),
                             "review": selection["review"], "data_kind": selection["data_kind"]}
        unique = {}
        for row in rows:
            key = _text(row["id"])
            if key in unique:
                if row != unique[key]:
                    raise Incomplete("conflicting_duplicate_request_id")
                result["duplicate_rows"] += 1
            unique[key] = row
        if set(unique) != set(selection["request_ids"]):
            raise Incomplete("reviewed_request_inventory_mismatch")
        origin = selection["gateway_instance_id"]
        requests, rates_by_model, cost = [], {}, Fraction(0)
        result["requests"] = [{"raw_request_id": key, "qualified_request_id": _qualified(origin, key),
                                       "parent_request_id": row["parent_request_id"],
                                       "status": row["status"], "requested_model": row["model"],
                                       "served_model": row["served_model"], "timestamp": row["timestamp"]}
                              for key, row in sorted(unique.items())]
        for key, row in sorted(unique.items()):
            if row["parent_request_id"] is not None:
                raise Incomplete("retry_parent_semantics_unverified")
            if row["status"] != "success":
                raise Incomplete("terminal_status_unverified")
            timestamp = datetime.fromisoformat(_text(row["timestamp"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.astimezone(timezone.utc).date().isoformat() != selection["date"]:
                raise Incomplete("timestamp_scope_unverified")
            model, usage = _model(row), _usage(row)
            rates = _rates(prices, model)
            requested = _text(row["model"])
            requested = requested if "/" in requested else row["provider"] + "/" + requested
            if requested != model:
                raise Incomplete("fallback_semantics_unverified")
            if model != selection["model"]:
                raise Incomplete("served_model_not_comparable_with_plan")
            rates_by_model[model] = rates
            cost += sum(usage[token] * rates[token] for token in usage) / 1_000_000
            requests.append({"request_id": _qualified(origin, key), "model": model, "usage": usage})
        # An independently reviewed empty inventory is a known zero-call session,
        # but the model still needs a supported price for strict report evidence.
        rates_by_model.setdefault(selection["model"], _rates(prices, selection["model"]))
        result.update(complete=True, computed_cost_usd=cost, raw_session_id=selection["session_id"],
                      raw_virtual_key_id=selection["virtual_key_id"], raw_virtual_key_name=selection["virtual_key_name"],
                      receipt_comparison=_compare(receipt.get("cost_usd"), cost),
                      prices={"schema_version": 1, "data_kind": selection["data_kind"], "currency": "USD",
                              "models": rates_by_model},
                      session={"schema_version": 1, "data_kind": selection["data_kind"], "source": "bifrost",
                               "complete": True, "run_id": selection["run_id"],
                               "session_id": _qualified(origin, selection["session_id"]),
                               "model": selection["model"], "date": selection["date"],
                               "gateway_version": "2.5.1", "requests": requests})
    except (Incomplete, KeyError, TypeError, ValueError, ArithmeticError, OSError, sqlite3.Error) as error:
        result["issues"].append(str(error) if isinstance(error, Incomplete) else "invalid_or_unreadable_evidence")
    return result


def _write_bundle(output, sessions, prices, costs, diagnostics):
    destination = Path(output).absolute()
    destination.mkdir()  # Never overwrite evidence.
    logs = b"".join(_bytes(row) for row in sessions)
    rates = _bytes(prices) if prices is not None else b""
    for row in costs:
        row["cost_provenance"] = {"kind": "bifrost_logs_x_prices_yaml", "session_id": row["session_id"],
                                  "logs_sha256": _sha(logs), "prices_sha256": _sha(rates)}
    files = {"evidence.jsonl": logs, "prices.yaml": rates,
             "costs.jsonl": b"".join(_bytes(row) for row in costs), "diagnostics.json": _bytes(diagnostics)}
    for name, raw in files.items():
        (destination / name).write_bytes(raw)
    manifest = {name: _sha(raw) for name, raw in files.items()}
    (destination / "manifest.json").write_bytes(_bytes(manifest))
    return destination


def write_export(result, output):
    sessions, costs = [], []
    if result["complete"]:
        session = result["session"]
        sessions = [session]
        costs = [{"run_id": session["run_id"], "session_id": session["session_id"],
                  "cost_usd": result["computed_cost_usd"], "receipt_comparison": result["receipt_comparison"]}]
    return _write_bundle(output, sessions, result["prices"], costs, result)


def combine_exports(inputs, output):
    """Combine complete bundles, rejecting overlaps and incompatible price sources."""
    sessions, costs, diagnostics, normalized, native_hashes, kinds = [], [], [], {}, set(), set()
    source_origins = {}
    for directory in map(Path, inputs):
        manifest = _json((directory / "manifest.json").read_bytes())
        files = {name: (directory / name).read_bytes()
                 for name in ("evidence.jsonl", "prices.yaml", "costs.jsonl", "diagnostics.json")}
        if any(manifest.get(name) != _sha(raw) for name, raw in files.items()):
            raise ValueError("Export bundle hashes changed")
        evidence = _json(files["diagnostics.json"])
        if evidence.get("complete") is not True:
            raise ValueError("Cannot combine incomplete exports")
        source = evidence["source"]
        origin, fingerprint = source["gateway_instance_id"], source["database_sha256"]
        if fingerprint in source_origins and source_origins[fingerprint] != origin:
            raise ValueError("Same database snapshot assigned conflicting gateway origins")
        source_origins[fingerprint] = origin
        prices = _json(files["prices.yaml"])
        _prices(prices)
        native_hashes.add(evidence["source"]["native_prices_sha256"])
        kinds.add(prices["data_kind"])
        for model, rates in prices["models"].items():
            if model in normalized and normalized[model] != rates:
                raise ValueError("Incompatible normalized rates")
            normalized[model] = rates
        sessions.extend(_json(line) for line in files["evidence.jsonl"].splitlines())
        incoming = [_json(line) for line in files["costs.jsonl"].splitlines()]
        verified = _sessions([_json(line) for line in files["evidence.jsonl"].splitlines()], _prices(prices))
        if (len(incoming) != len(verified) or {row["run_id"] for row in incoming} != set(verified)
                or any(row["run_id"] not in verified
                                               or _money(row["cost_usd"]) != verified[row["run_id"]][1]
                                               or row["session_id"] != verified[row["run_id"]][0]["session_id"]
                       for row in incoming)):
            raise ValueError("Cost bundle does not match evidence")
        costs.extend(incoming)
        diagnostics.append(evidence)
    if not sessions or len(native_hashes) != 1 or len(kinds) != 1:
        raise ValueError("Exports need a common native price snapshot and data kind")
    prices = {"schema_version": 1, "data_kind": next(iter(kinds)), "currency": "USD", "models": normalized}
    _sessions(sessions, _prices(prices))  # Global run/session/request uniqueness.
    return _write_bundle(output, sorted(sessions, key=lambda r: r["run_id"]), prices,
                         sorted(costs, key=lambda r: r["run_id"]),
                         {"complete": True, "origins": diagnostics})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    for option in ("db", "prices", "selection", "receipt", "output"):
        export.add_argument("--" + option, type=Path, required=True)
    combine = commands.add_parser("combine")
    combine.add_argument("--inputs", type=Path, nargs="+", required=True)
    combine.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "combine":
            combine_exports(args.inputs, args.output)
            print("Combined complete evidence; no benchmark report published.")
            return 0
        result = export_session(args.db, args.prices, _json(args.selection.read_bytes()),
                                _json(args.receipt.read_bytes()))
        # Outputs cannot overlap the source file, its directory or inputs.
        destination = args.output.absolute().resolve(strict=False)
        if destination == args.db.resolve().parent or destination in args.db.resolve().parents:
            raise ValueError("Output must not contain the source database")
        write_export(result, destination)
        print("Complete cost evidence." if result["complete"] else "Incomplete cost evidence; see diagnostic codes.")
        return 0 if result["complete"] else 1
    except (ValueError, OSError, ArithmeticError, KeyError, TypeError, sqlite3.Error):
        parser.exit(2, "Export failed; input or output validation error.\n")


if __name__ == "__main__":
    raise SystemExit(main())
