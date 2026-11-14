"""Gateway-owned normalized evidence; never synthesize it from client intent.

A gateway logging/export adapter must record the forwarded client correlation
header, session and actual routing, plus received payload-hash/length metadata.
These functions import only the explicit normalized export format, not guessed
vendor schemas or arbitrary raw request/response bodies containing credentials.
"""

import argparse
import json
from pathlib import Path


def normalize_logged_metadata(record):
    """Project a gateway export with id/provider/model and captured metadata.

    Provider and model must be the gateway's actual routing fields. Metadata
    binds the client correlation/header claims; it is not body re-hashing or
    independent proof that no provider was contacted.
    """
    metadata = record["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    if not isinstance(metadata, dict):
        raise ValueError("gateway metadata missing")

    def field(name):
        return metadata["crocodile-" + name]

    normalized = {
        "request_id": field("request-id"),
        "gateway_request_id": record["id"],
        "session": field("session"),
        "provider": record["provider"],
        "model": record["model"],
        "model_requested": field("model-requested"),
        "vk_alias": field("vk-alias"),
        "payload_sha256": field("payload-sha256"),
        "payload_bytes": int(field("payload-bytes")),
        "fallbacks": json.loads(field("fallbacks")),
    }
    if not all(
        isinstance(normalized[key], str) and normalized[key]
        for key in ("request_id", "gateway_request_id", "provider", "model")
    ):
        raise ValueError("actual gateway routing fields missing")
    # Never infer zero calls from a missing provider, error code or attempt list.
    for key in ("provider_calls", "status"):
        if key in record:
            normalized[key] = record[key]
    return normalized


def read_gateway_records(path, *, repo=None):
    path = Path(path).absolute()
    if (repo is not None and path.resolve().is_relative_to(Path(repo).resolve())) or any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("gateway evidence must be trusted storage outside the repository")
    if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("invalid gateway evidence file")
    text = path.read_text(encoding="utf-8")
    records = (
        json.loads(text)
        if text.lstrip().startswith("[")
        else [json.loads(line) for line in text.splitlines() if line.strip()]
    )
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("invalid gateway records")
    # Do not retain headers, credentials, message content or raw errors.
    allowed = {
        "request_id",
        "gateway_request_id",
        "session",
        "provider",
        "model",
        "model_requested",
        "fallbacks",
        "payload_sha256",
        "payload_bytes",
        "vk_alias",
        "status",
        "provider_calls",
    }
    return [
        normalize_logged_metadata(row)
        if "metadata" in row
        else {key: value for key, value in row.items() if key in allowed}
        for row in records
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Project gateway-owned log exports without credentials or content"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = read_gateway_records(args.input, repo=args.repo)
        target = args.output.absolute()
        if (
            target.resolve().is_relative_to(args.repo.resolve())
            or target.exists()
            or any(
                p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                for p in (target, *target.parents)
            )
        ):
            raise ValueError("output must be new trusted storage outside the repository")
        with target.open("x", encoding="utf-8") as stream:
            json.dump(rows, stream, separators=(",", ":"))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("INCOMPLETE: gateway export missing required correlation or actual routing evidence")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
