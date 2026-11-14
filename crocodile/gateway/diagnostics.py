"""Live local probes for Part 3 doctor; output contains no response bodies or keys."""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from .egress import EgressClient, network_scope
from .network_policy import NetworkPolicy
from .records import read_gateway_records


class ProbeUnavailable(RuntimeError):
    pass


def limits_permissions(path):
    path = Path(path).absolute()
    if not path.is_file() or any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("limits file missing or linked")
    if os.name != "nt":
        mode = path.stat()
        return mode.st_uid == 0, bool(stat.S_IMODE(mode.st_mode) & 0o022)
    # Fixed script, path passed as environment data, never interpolated code.
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:CROCODILE_LIMITS_PROBE_PATH
$owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$sids = @($id.User.Value) + @($id.Groups | ForEach-Object { $_.Value }) + @('S-1-1-0','S-1-5-11','S-1-5-32-545')
$admins = @('S-1-5-18','S-1-5-32-544')
$writable = $false
foreach ($rule in $acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])) {
  $rights = [int64]$rule.FileSystemRights
  if ($rule.AccessControlType -eq 'Allow' -and ($rights -band 0xD0156) -ne 0 -and $rule.IdentityReference.Value -in $sids -and $rule.IdentityReference.Value -notin $admins) { $writable = $true }
}
@{ admin_owned=($owner -in $admins); user_writable=$writable } | ConvertTo-Json -Compress
"""
    executable = (
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    if not executable.is_file():
        raise ProbeUnavailable("ACL probe unavailable")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    }
    env["CROCODILE_LIMITS_PROBE_PATH"] = str(path)
    result = subprocess.run(
        [
            str(executable),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
        ],
        env=env,
        capture_output=True,
        timeout=8,
        creationflags=0x08000000,
        check=False,
    )
    if result.returncode:
        raise ProbeUnavailable("ACL probe could not run")
    data = json.loads(result.stdout.decode("utf-8-sig"))
    if type(data.get("admin_owned")) is not bool or type(data.get("user_writable")) is not bool:
        raise ProbeUnavailable("invalid ACL evidence")
    return data["admin_owned"], data["user_writable"]


def collect_evidence(
    config,
    *,
    client=None,
    local_key=None,
    gateway_log=None,
    limits_path=None,
    acl_probe=limits_permissions,
    repo=None,
):
    """Independent probes; exceptions become type-free status flags, not text.

    A gateway export is needed to prove zero upstream calls for the local-VK
    refusal. A 4xx status alone never fabricates that evidence.
    """
    gateway = config["bifrost"]["base_url"]
    ollama = config["confidential"]["ollama_host"]
    policy = NetworkPolicy(gateways=(gateway,), ollama=(ollama,))
    owns_client = client is None
    client = client or EgressClient(bifrost_base_url=gateway, network_policy=policy)
    evidence = {"probe_status": {}, "gateway": {}}

    def probe(name, operation):
        try:
            operation()
        except ProbeUnavailable:
            evidence["probe_status"][name] = "INCOMPLETE"
        except Exception:
            evidence["probe_status"][name] = "FAIL"
        else:
            evidence["probe_status"][name] = "OK"

    def reach():
        code, _ = client.probe(gateway, "/health")
        evidence["gateway"]["reachable"] = 200 <= code < 300
        if not evidence["gateway"]["reachable"]:
            raise ValueError()

    def authentication():
        code, _ = client.probe(
            gateway,
            "/v1/chat/completions",
            method="POST",
            body={"model": "ollama/doctor-invalid-model", "messages": [], "max_tokens": 1},
        )
        evidence["gateway"]["inference_auth"] = code in (401, 403)
        if not evidence["gateway"]["inference_auth"]:
            raise ValueError()

    def local_refusal():
        if not local_key:
            raise ProbeUnavailable()
        validated, _ = client.probe(gateway, "/v1/models", headers={"x-bf-vk": local_key})
        if validated != 200:
            raise ValueError("local virtual key could not be validated")
        request = "doctor_" + uuid.uuid4().hex
        model = "openai/doctor-cloud-refusal"
        code, _ = client.probe(
            gateway,
            "/v1/chat/completions",
            method="POST",
            body={
                "model": model,
                "messages": [{"role": "user", "content": "Crocodile diagnostic"}],
                "max_tokens": 1,
            },
            headers={
                "x-bf-vk": local_key,
                "x-crocodile-request-id": request,
                "x-bf-request-id": request,
                "x-request-id": request,
                "x-bf-lh-crocodile-request-id": request,
            },
        )
        evidence["gateway"].update(vk_alias="local", requested_model=model, refusal_status=code)
        if code not in (400, 403):
            raise ValueError()
        if not gateway_log:
            raise ProbeUnavailable()
        try:
            matches = [
                row
                for row in read_gateway_records(gateway_log, repo=repo)
                if row.get("request_id") == request
            ]
        except OSError as error:
            raise ProbeUnavailable() from error
        if not matches or (len(matches) == 1 and "provider_calls" not in matches[0]):
            raise ProbeUnavailable()
        if len(matches) != 1 or matches[0].get("provider_calls") != 0 or matches[0].get("status") != code:
            raise ValueError()
        evidence["gateway"]["provider_calls"] = 0

    def availability():
        code, data = client.probe(ollama, "/api/tags", service="ollama")
        if code != 200 or not isinstance(data.get("models"), list):
            raise ValueError()
        evidence["ollama_tags"] = data

    def models():
        shows = {}
        for model in config["models"]["local"]["chain"]:
            tag = model.removeprefix("ollama/")
            code, data = client.probe(
                ollama, "/api/show", method="POST", body={"model": tag}, service="ollama"
            )
            if code != 200:
                raise ValueError()
            shows[tag] = data
        evidence["ollama_show"] = shows

    def guard():
        with network_scope(client.network_policy, gateway, mode="confidential", service="gateway"):
            from .egress import _SOCKET_PAIRS

            allowed_host, allowed_port = next(iter(_SOCKET_PAIRS.get()))
            sys.audit("socket.connect", object(), (allowed_host, allowed_port))
            # Exercise the installed hook, without connecting a socket.
            for pair in ((allowed_host, 1 if allowed_port != 1 else 2), ("203.0.113.1", 443)):
                try:
                    sys.audit("socket.connect", object(), pair)
                except PermissionError:
                    continue
                raise ValueError()
            evidence["socket_guard_active"] = True

    def limits():
        if limits_path is None:
            raise ProbeUnavailable()
        owned, writable = acl_probe(limits_path)
        evidence.update(limits_admin_owned=owned, limits_user_writable=writable)
        if owned is not True or writable is not False:
            raise ValueError()

    try:
        for name, operation in (
            ("gateway reachability", reach),
            ("gateway authentication", authentication),
            ("gateway probe", local_refusal),
            ("Ollama availability", availability),
            ("Ollama probe", models),
            ("socket guard", guard),
            ("limits permissions", limits),
        ):
            probe(name, operation)
        return evidence
    finally:
        if owns_client:
            client._http_client.close()
