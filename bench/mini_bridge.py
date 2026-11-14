"""Trusted separate WSL interpreter bridge; never imported by Crocodile.

Only stdlib imports occur at module load. Live mini imports are worker/probe-only.
Raw streams, conversations and model configuration are deliberately not persisted.
"""

import argparse
import contextlib
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile


VERSION = "2.4.6"
TEMPLATE_BLOB = "8b72f71f8092ae805ec43221dbeaeefc2340cd3e"


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def probe(credential_env):
    if "wsl2" not in platform.release().casefold():
        return {"ready": False, "reason": "WSL2Required"}
    try:
        actual = version("mini-swe-agent")
    except Exception:
        return {"ready": False, "reason": "MiniNotInstalled"}
    if actual != VERSION:
        return {"ready": False, "reason": "MiniVersionMismatch", "version": actual}
    if sys.prefix == sys.base_prefix:
        return {"ready": False, "reason": "SeparateMiniEnvironmentRequired"}
    if not os.environ.get(credential_env):
        return {"ready": False, "reason": "MissingBenchCredential"}
    return {"ready": True, "version": actual}


def usage_summary(messages):
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    seen = 0
    for message in messages:
        if message.get("role") != "assistant":
            continue
        usage = message.get("extra", {}).get("response", {}).get("usage")
        if not isinstance(usage, dict):
            return None
        values = [usage.get("prompt_tokens"), usage.get("completion_tokens"),
                  (usage.get("prompt_tokens_details") or {}).get("cached_tokens")]
        if any(type(v) is not int or v < 0 for v in values) or values[2] > values[0]:
            return None
        for key, value in zip(totals, values):
            totals[key] += value
        seen += 1
    return totals if seen else None


def worker(spec):
    readiness = probe(spec["credential_env"])
    if not readiness["ready"]:
        save(spec["receipt"], {"exit_status": readiness["reason"], "steps": None, "usage": None})
        return 2
    key = os.environ.pop(spec["credential_env"])
    # Keep provider credentials out of LocalEnvironment's child environment and
    # template vars. Never load mini's normal per-user .env or enable debug logs.
    safe = {k: v for k, v in os.environ.items() if k in {
        "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR",
    }}
    os.environ.clear()
    os.environ.update(safe)
    os.environ.update(MSWEA_SILENT_STARTUP="1", MSWEA_CONFIGURED="true")
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="mini-bench-config-") as config_home:
        os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = config_home
        with open(os.devnull, "w") as silent, contextlib.redirect_stdout(silent), contextlib.redirect_stderr(silent):
            try:
                import yaml
                from minisweagent.config import builtin_config_dir
                from minisweagent.agents.default import DefaultAgent
                from minisweagent.environments.local import LocalEnvironment
                from minisweagent.models.litellm_model import LitellmModel

                raw = (builtin_config_dir / "mini.yaml").read_bytes()
                blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                if blob != TEMPLATE_BLOB:
                    save(spec["receipt"], {"exit_status": "MiniTemplateMismatch", "steps": None, "usage": None})
                    return 2
                config = yaml.safe_load(raw)
                overlay = spec["config"]
                headers = {"x-bf-vk": key}
                if spec["session_header"] is not None:
                    headers["x-bf-session-id"] = spec["session_header"]
                model_options = config.get("model", {}) | overlay["model"]
                model_options["model_kwargs"] = {
                    **config.get("model", {}).get("model_kwargs", {}),
                    **overlay["model"]["model_kwargs"], "api_base": spec["api_base"],
                    "api_key": "bifrost", "extra_headers": headers,
                }
                model = LitellmModel(**model_options)
                environment = LocalEnvironment(cwd=spec["workspace"], **config.get("environment", {}))

                class EvidenceAgent(DefaultAgent):
                    # Upstream serialize() includes credentials in model_kwargs.
                    # Preserve only a small allowlisted receipt, never trajectory.
                    def save(self, path, *extra):
                        last = self.messages[-1].get("extra", {}) if self.messages else {}
                        result = {"mini_version": VERSION, "template_git_blob": blob,
                                  "litellm_version": version("litellm"), "steps": self.n_calls,
                                  "exit_status": last.get("exit_status", ""),
                                  "usage": usage_summary(self.messages)}
                        save(spec["receipt"], result)
                        return result

                agent = EvidenceAgent(model, environment, **(config["agent"] | overlay["agent"]))
                # Mini's built-in mini.yaml includes interactive-only keys. The
                # default agent's Pydantic config ignores those; no templates change.
                try:
                    agent.run(Path(spec["task_file"]).read_text(encoding="utf-8"))
                except KeyboardInterrupt:
                    save(spec["receipt"], {"exit_status": "Interrupted", "steps": agent.n_calls,
                                           "usage": usage_summary(agent.messages)})
                    return 130
                except Exception as error:
                    # No raw exception text, provider headers, or output persisted.
                    save(spec["receipt"], {"exit_status": type(error).__name__, "steps": agent.n_calls,
                                           "usage": usage_summary(agent.messages)})
                    return 1
                return 0
            except Exception as error:
                save(spec["receipt"], {"exit_status": type(error).__name__, "steps": None, "usage": None})
                return 2


def _start_time(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def stop(control, attempt_id):
    """Target only this worker's recorded PID/group; never terminate a distro."""
    try:
        data = json.loads(Path(control).read_text())
        pid = data["pid"]
        if (not isinstance(data.get("start_time"), str) or data["attempt_id"] != attempt_id
                or _start_time(pid) != data["start_time"]):
            return False
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0").split(b"\0")
        if [a.decode("utf-8") for a in arguments[-3:]] != [str(Path(__file__).resolve()), "--worker", data["spec_path"]]:
            return False
        os.killpg(pid, signal.SIGKILL)
        return True
    except (OSError, ValueError, KeyError):
        return False


def supervise(spec, spec_path):
    process = subprocess.Popen([sys.executable, "-I", __file__, "--worker", spec_path],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    save(spec["control"], {"pid": process.pid, "start_time": _start_time(process.pid),
                           "attempt_id": spec["attempt_id"], "spec_path": str(spec_path)})
    timed_out = False
    try:
        code = process.wait(timeout=600)
    except subprocess.TimeoutExpired:
        timed_out = True
        stop(spec["control"], spec["attempt_id"])
        process.kill()
        code = process.wait()
    finally:
        if process.poll() is None:
            stop(spec["control"], spec["attempt_id"])
            process.kill()
            process.wait()
    save(spec["process_result"], {"returncode": code, "timed_out": timed_out,
                                  "worker_deadline_enforced": True,
                                  "escaped_descendants_contained": False})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe")
    parser.add_argument("--credential-env")
    parser.add_argument("--spec")
    parser.add_argument("--worker")
    parser.add_argument("--cancel")
    parser.add_argument("--attempt-id")
    parser.add_argument("--cancel-result")
    args = parser.parse_args(argv)
    if args.probe:
        save(args.probe, probe(args.credential_env))
        return 0
    if args.cancel:
        save(args.cancel_result, {"worker_group_signalled": stop(args.cancel, args.attempt_id)})
        return 0
    path = args.worker or args.spec
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    return worker(spec) if args.worker else supervise(spec, path)


if __name__ == "__main__":
    raise SystemExit(main())
