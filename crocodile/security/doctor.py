"""User diagnostics. Network/ACL evidence is supplied by Part 2, never fabricated.

No admin credentials, direct HTTP, key dumping, or routing changes occur here.
"""

import argparse
import ipaddress
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .approvals import escape
from .classification import default_state_path
from .executables import resolve_pinned
from .integrity import StateIntegrity
from .secrets import secret_scan
from .session import ApprovalSession


@dataclass(frozen=True)
class Diagnostic:
    name: str
    status: str
    detail: str

    def __post_init__(self):
        if self.status not in ("OK", "WARN", "FAIL"):
            raise ValueError("invalid diagnostic status")


def _mask(value):
    # Diagnostic text is never a credential transport. Mask even low-entropy
    # fixture/password assignments, which the shared scanner intentionally skips.
    value = secret_scan(value)
    value = re.sub(
        r"(?i)(\b(?:password|token|secret|api_key|vk_local|vk_public|tavily_key|hmac_key)\b\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)(\b(?:Bearer|Basic)\s+)[A-Za-z0-9_+/=.-]+", r"\1[REDACTED]", value
    )
    return re.sub(r"(?<![A-Za-z0-9_-])(?:tvly-|vk-)[A-Za-z0-9_-]+", "[REDACTED]", value)


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[Diagnostic, ...]

    @property
    def passed(self):
        return not any(c.status == "FAIL" for c in self.checks)

    def render(self):
        return "\n".join(
            f"{c.status} {escape(_mask(c.name))}: {escape(_mask(c.detail))}"
            for c in self.checks
        )


def _loopback(raw, port):
    value = urlsplit(raw)
    if (
        value.scheme != "http"
        or value.username is not None
        or value.password is not None
        or value.query
        or value.fragment
        or value.path not in ("", "/")
        or value.port != port
    ):
        raise ValueError("loopback HTTP endpoint required")
    if (
        value.hostname != "localhost"
        and not ipaddress.ip_address(value.hostname).is_loopback
    ):
        raise ValueError("loopback endpoint required")


def check_local_model(model, allowlist, host):
    """Diagnostic validation only; Part 2 retains per-request routing enforcement."""
    _loopback(host, 11434)
    if not isinstance(model, str) or not model.startswith("ollama/"):
        raise ValueError("local models require the ollama provider prefix")
    tag = model.removeprefix("ollama/")
    if (
        not tag
        or tag not in allowlist
        or any(x in tag.lower() for x in (":cloud", "-cloud", "/", "@"))
        or not re.fullmatch(r"[A-Za-z0-9_.:-]+", tag)
    ):
        raise ValueError("local model is not an allowed local tag")
    return tag


def _prices(config, prices):
    models = config["models"]
    if not isinstance(models, dict):
        raise TypeError("model configuration must be a mapping")
    count = 0
    for rung in ("cheap", "strong", "local"):
        chain = models[rung]["chain"]
        if not isinstance(chain, list) or not chain:
            raise ValueError("each rung requires a nonempty model chain")
        for model in chain:
            if not isinstance(model, str) or "/" not in model:
                raise ValueError("invalid chain model")
            entry = prices.get(
                model, prices.get("ollama/*") if model.startswith("ollama/") else None
            )
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("tiers"), list)
                or not entry["tiers"]
            ):
                raise ValueError("chain model has no price tiers")
            last = 0
            for index, tier in enumerate(entry["tiers"]):
                ceiling = tier["upto"]
                if ceiling is None:
                    if index != len(entry["tiers"]) - 1:
                        raise ValueError("unbounded price tier must be last")
                elif type(ceiling) is not int or ceiling <= last:
                    raise ValueError("price tiers must increase")
                else:
                    last = ceiling
                required = ("in", "cache_read", "out")
                if model.startswith("anthropic/"):
                    required += ("cache_write_5m", "cache_write_1h")
                for key in required:
                    value = tier[key]
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise ValueError(
                            "price must be finite, nonnegative and never TBD"
                        )
            if entry["tiers"][-1]["upto"] is not None:
                raise ValueError("price tiers require a final unbounded tier")
            count += 1
    return count


def _remote(value):
    if isinstance(value, dict):
        return any(
            (
                str(k).lower()
                in {
                    "remote_host",
                    "remote_model",
                    "remote_model_name",
                    "cloud",
                    "cloud_model",
                }
                and bool(v)
            )
            or _remote(v)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(_remote(v) for v in value)
    return False


def diagnose(
    *, session: ApprovalSession, config, prices, evidence=None, environment=None
) -> DoctorReport:
    """Part 2's trusted probe adapter supplies normalized evidence, not repo text.

    Missing probes fail diagnostics. Raw responses/exceptions are never rendered.
    Run via Part 2's egress boundary; this module never opens a socket.
    """
    evidence = evidence if evidence is not None else {}
    environment = environment if environment is not None else os.environ
    checks = []

    def check(name, operation, success):
        try:
            operation()
            checks.append(Diagnostic(name, "OK", success))
        except Exception as error:  # noqa: BLE001 - diagnostics must not expose probe exceptions
            advice = {
                "state integrity": "key/seal missing, invalid, or unavailable; inspect state without re-enrolling it",
                "prices": "check every chain model for complete numeric tiers, cache prices and no TBD values",
                "local model configuration": "require allowed ollama tags, no cloud tags, loopback hosts and sufficient context (minimum 32768)",
                "Ollama probe": "local blob/show evidence missing, malformed, or indicates a remote model",
                "gateway probe": "require inference authentication and a local-VK cloud refusal with zero provider calls",
                "socket guard": "Part 2 has not attested an active socket guard",
                "limits permissions": "require a fresh ACL probe proving admin ownership and no user write access",
            }.get(
                name,
                "trusted executable missing, changed, or resolved inside the repository",
            )
            checks.append(
                Diagnostic(
                    name,
                    "FAIL",
                    advice + " (" + type(error).__name__ + ")",
                )
            )

    def integrity():
        if session.integrity is None:
            raise ValueError("integrity not attached")
        session.verify_integrity()

    check(
        "state integrity", integrity, "HMAC verified; key available without disclosure"
    )
    for name in ("git", "rg", "ruff", "python"):
        check(
            name,
            lambda name=name: resolve_pinned(
                name, session.repo_root, session.repo_root, session._exe_pins
            ),
            "trusted executable resolves outside repository",
        )
    check(
        "prices",
        lambda: _prices(config, prices),
        "all configured chain models have complete numeric tiers",
    )

    def local_config():
        allow = config["confidential"]["local_model_allowlist"]
        if (
            not isinstance(allow, list)
            or not allow
            or any(not isinstance(v, str) for v in allow)
        ):
            raise ValueError("invalid local allowlist")
        host = config["confidential"]["ollama_host"]
        _loopback(host, 11434)
        if "OLLAMA_HOST" in environment:
            _loopback(environment["OLLAMA_HOST"], 11434)
        chain = config["models"]["local"]["chain"]
        if not isinstance(chain, list) or not chain:
            raise ValueError("missing local chain")
        for model in chain:
            check_local_model(model, allow, host)
        wanted = config["models"]["local"]["ctx_window"]
        configured = int(environment["OLLAMA_CONTEXT_LENGTH"])
        if type(wanted) is not int or wanted < 32768 or configured < wanted:
            raise ValueError("insufficient configured local context")

    check(
        "local model configuration",
        local_config,
        "exact local allowlist, loopback hosts and context verified",
    )
    checks.append(
        Diagnostic(
            "Ollama cloud setting",
            "OK" if environment.get("OLLAMA_NO_CLOUD") == "1" else "WARN",
            "OLLAMA_NO_CLOUD=1"
            if environment.get("OLLAMA_NO_CLOUD") == "1"
            else "set OLLAMA_NO_CLOUD=1 on the daemon as well as the client",
        )
    )

    def ollama():
        local_config()
        records = evidence["ollama_tags"]["models"]
        shows = evidence["ollama_show"]
        for model in config["models"]["local"]["chain"]:
            tag = model.removeprefix("ollama/")
            matching = [r for r in records if r.get("name") == tag]
            if not matching or not any(
                re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", r.get("digest", ""))
                and type(r.get("size")) is int
                and r["size"] > 0
                for r in matching
            ):
                raise ValueError("local blob evidence missing")
            show = shows[tag]
            if (
                _remote(show)
                or not isinstance(show.get("model_info"), dict)
                or not show["model_info"]
            ):
                raise ValueError("remote or missing local model evidence")

    check(
        "Ollama probe",
        ollama,
        "owner /api/tags and /api/show evidence indicates local weights",
    )

    def gateway():
        _loopback(config["bifrost"]["base_url"], 8080)
        probe = evidence["gateway"]
        if (
            probe["reachable"] is not True
            or probe["inference_auth"] is not True
            or probe["vk_alias"] != "local"
            or not isinstance(probe["requested_model"], str)
            or not probe["requested_model"].startswith(("anthropic/", "openai/"))
            or type(probe["refusal_status"]) is not int
            or not 400 <= probe["refusal_status"] < 500
            or type(probe["provider_calls"]) is not int
            or probe["provider_calls"] != 0
        ):
            raise ValueError("local VK deny-by-default probe failed")

    check(
        "gateway probe",
        gateway,
        "owner probe: inference auth on; local VK rejects cloud without provider calls",
    )

    def socket_guard():
        if evidence.get("socket_guard_active") is not True:
            raise ValueError("socket guard unverified")

    check("socket guard", socket_guard, "Part 2 attests socket guard active")

    def limits():
        if (
            evidence.get("limits_admin_owned") is not True
            or evidence.get("limits_user_writable") is not False
        ):
            raise ValueError("limits ACL unverified or writable")

    check(
        "limits permissions",
        limits,
        "owner ACL probe: admin-owned and not user-writable",
    )
    return DoctorReport(tuple(checks))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Crocodile user doctor; no admin credentials"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--config-dir", type=Path, default=default_state_path().parent)
    args = parser.parse_args(argv)
    try:
        root = args.repo.resolve(strict=True)
        settings = args.config_dir.resolve(strict=True)
        if settings.is_relative_to(root):
            raise ValueError("repository must not be a configuration source")
        import yaml

        documents = []
        for name in ("config.yaml", "policy.yaml", "prices.yaml"):
            path = settings / name
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size > 1024 * 1024
            ):
                raise ValueError("invalid settings path")
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TypeError("settings require mappings")
            documents.append(value)
        session = ApprovalSession(
            root, integrity=StateIntegrity(settings / "state.db")
        )
        report = diagnose(session=session, config=documents[0], prices=documents[2])
        print(report.render())
        # Part 1 must supply Part 2's live probes: absent probes intentionally fail.
        return 0 if report.passed else 1
    except Exception as error:  # noqa: BLE001 - no raw exception text/credentials in CLI output
        print(
            "FAIL doctor initialization: "
            + type(error).__name__
            + "; run init and check trusted settings/dependencies"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
