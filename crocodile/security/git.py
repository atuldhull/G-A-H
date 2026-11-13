"""Pinned Git with fixed templates, commit-SHA revisions and per-call audits."""

import hashlib
import os
import re
import tempfile
from contextlib import nullcontext
from pathlib import Path

from . import approvals, procs
from .executables import resolve_pinned
from .outputs import prepare_command_result
from .paths import resolve_in_repo
from .provenance import remote_fields
from .session import ApprovalSession
from .types import Action, CmdResult

REV = re.compile(r"^(?!-)[A-Za-z0-9_./~^@{}:-]{1,200}$")
REF = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_/-]{0,100}$")
CORE = {
    "repositoryformatversion",
    "filemode",
    "bare",
    "logallrefupdates",
    "ignorecase",
    "precomposeunicode",
    "autocrlf",
    "safecrlf",
    "eol",
    "symlinks",
    "longpaths",
    "quotepath",
}
BANNED = (
    "--output",
    "--upload-pa",
    "-c",
    "--exec",
    "-C",
    "--git-dir",
    "--work-tree",
    "--config-env",
    "-O",
    "--paginate",
    "--no-index",
)


class GitDenied(PermissionError):
    """Unsafe or unsupported Git input; no requested operation was performed."""


class Git:
    """Use as a context manager. Only ordinary .git directories are supported.

    Linked worktrees, submodule worktrees and alternate object directories fail
    closed until their ownership and metadata paths have an agreed contract.
    """

    def __init__(self, session: ApprovalSession):
        self.session = session
        self.root = session.repo_root
        self.exe = resolve_pinned("git", self.root, self.root, session._exe_pins)
        self.gitdir = self.root / ".git"
        if (
            not self.gitdir.is_dir()
            or self.gitdir.is_symlink()
            or getattr(self.gitdir, "is_junction", lambda: False)()
        ):
            raise GitDenied("only a local ordinary .git directory is supported")
        if (self.gitdir / "objects" / "info" / "alternates").exists():
            raise GitDenied("alternate Git object directories are refused")
        if (
            (self.gitdir / "commondir").exists()
            or (self.gitdir / "config.worktree").exists()
            or (self.gitdir / "objects").resolve() != self.gitdir / "objects"
        ):
            raise GitDenied("shared/redirected Git metadata is refused")
        self._temporary = tempfile.TemporaryDirectory(prefix="crocodile-git-")
        self.hooks = Path(self._temporary.name) / "empty-hooks"
        self.hooks.mkdir()
        self._hashes = None
        self._drivers = set()
        self._config = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._temporary.cleanup()

    def _disable(self, reason):
        self.session._git_disabled = True
        self.session.events.append({"event": "git_config_changed", "reason": reason})
        raise GitDenied(reason)

    def _snapshot(self):
        if self.session._git_disabled:
            raise GitDenied(
                "free Git disabled for this session after unsafe configuration"
            )
        if (
            any(
                (self.gitdir / name).exists()
                for name in ("commondir", "config.worktree", "objects/info/alternates")
            )
            or (self.gitdir / "objects").resolve() != self.gitdir / "objects"
        ):
            self._disable("Git metadata redirection changed")
        if (
            not self.hooks.is_dir()
            or self.hooks.is_symlink()
            or any(self.hooks.iterdir())
        ):
            self._disable("empty-hooks directory changed")
        paths = {
            self.gitdir / "config",
            self.gitdir / "config.worktree",
            self.gitdir / "info" / "attributes",
        }
        entries = 0

        def fail(error):
            raise error

        for directory, dirs, files in os.walk(
            self.root, followlinks=False, onerror=fail
        ):
            dirs[:] = [name for name in dirs if name != ".git"]
            entries += len(dirs) + len(files)
            if entries > 50_000:
                raise GitDenied("Git attribute scan exceeded entry cap")
            for name in dirs:
                path = Path(directory, name)
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise GitDenied("Git attribute scan encountered linked directory")
            if ".gitattributes" in files:
                paths.add(Path(directory, ".gitattributes"))
        hashes, drivers = {}, set()
        for path in sorted(paths):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise GitDenied("linked or non-file Git configuration")
            if path.is_relative_to(self.gitdir) and not path.resolve().is_relative_to(
                self.gitdir
            ):
                raise GitDenied("Git metadata leaves the local git directory")
            if path.exists() and path.stat().st_size > 2_000_000:
                raise GitDenied("Git metadata exceeds audit size limit")
            raw = path.read_bytes() if path.exists() else None
            hashes[str(path)] = (
                hashlib.sha256(raw).hexdigest() if raw is not None else None
            )
            if raw is not None and path.name in ("attributes", ".gitattributes"):
                for driver in re.findall(rb"(?:^|\s)filter=([^\s]+)", raw):
                    if not re.fullmatch(rb"[A-Za-z0-9_.-]+", driver):
                        raise GitDenied("unsupported filter-driver declaration")
                    drivers.add(driver.decode("ascii"))
        return hashes, drivers

    def _options(self, drivers):
        settings = {
            "core.fsmonitor": "false",
            "core.hooksPath": str(self.hooks),
            "core.pager": "cat",
            "diff.external": "",
            "core.sshCommand": "",
            "credential.helper": "",
            "protocol.ext.allow": "never",
            "core.editor": "false",
            "core.askPass": "",
            "core.attributesFile": os.devnull,
            "submodule.recurse": "false",
            "maintenance.auto": "false",
            "gc.auto": "0",
        }
        for driver in sorted(drivers):
            for field in ("process", "clean", "smudge"):
                settings[f"filter.{driver}.{field}"] = ""
            settings[f"filter.{driver}.required"] = "false"
        result = [str(self.exe), "--no-pager"]
        for key, value in settings.items():
            result += ["-c", f"{key}={value}"]
        return result

    def _audit(self):
        hashes, drivers = self._snapshot()
        if hashes == self._hashes:
            return hashes, drivers
        argv = self._options(drivers) + [
            "config",
            "--file",
            str(self.gitdir / "config"),
            "--no-includes",
            "--null",
            "--list",
        ]
        result = procs.run(
            argv,
            self.root,
            root=self.root,
            timeout=30,
            before_spawn=lambda: self._unchanged(hashes),
            git_env=True,
        )
        if result.returncode:
            self._disable("cannot audit repository Git configuration")
        bad, config = [], {}
        for item in result.stdout.split("\0"):
            if not item:
                continue
            key, _, value = item.partition("\n")
            key = key.lower()
            allowed = (key.startswith("core.") and key[5:] in CORE) or bool(
                re.fullmatch(
                    r"remote\..+\.(?:url|fetch)|branch\..+\.(?:remote|merge|rebase)|user\.(?:name|email)",
                    key,
                )
            )
            if not allowed or (key == "core.bare" and value.lower() != "false"):
                bad.append(key)
            config[key] = value
        if bad:
            self._disable(
                "git config changed; offending keys: " + ", ".join(sorted(set(bad)))
            )
        self._unchanged(hashes)
        self._hashes, self._drivers, self._config = hashes, drivers, config
        self.session.events.append({"event": "git_config_audited", "hashes": hashes})
        return hashes, drivers

    def _unchanged(self, hashes):
        resolve_pinned("git", self.root, self.root, self.session._exe_pins)
        if self._snapshot()[0] != hashes:
            raise GitDenied(
                "git config changed before execution; retry for a fresh audit"
            )

    def _call(self, arguments, *, timeout=120, source=None, mutation=False):
        self.session.verify_integrity()
        hashes, drivers = self._audit()
        argv = self._options(drivers) + arguments
        action = Action("git", argv=argv, cwd=str(self.root), source=source)
        # Validated fixed read templates remain free even when their operands
        # originated in repo text; provenance escalates Git mutations only.
        decision = approvals.ask(action, session=self.session) if mutation else None
        if decision is not None and not decision:
            raise approvals.ApprovalDenied("Git operation was not approved")

        def revalidate():
            self._unchanged(hashes)
            if decision is not None:
                approvals.validate_before_execution(
                    action, decision, session=self.session
                )
            if check_integrity is not None:
                check_integrity()

        scope = (
            self.session.watch_integrity(extra=(self.hooks,))
            if mutation
            else nullcontext(None)
        )
        with scope as check_integrity:
            result = procs.run(
                argv,
                self.root,
                root=self.root,
                timeout=timeout,
                before_spawn=revalidate,
                git_env=True,
            )
        if self._snapshot()[0] != hashes:
            self._hashes = None
            self.session.events.append(
                {"event": "git_metadata_changed", "operation": arguments[0]}
            )
        return result

    def validate_rev(self, revision: str) -> str:
        if not isinstance(revision, str) or not REV.fullmatch(revision):
            raise GitDenied("invalid Git revision")
        result = self._call(
            ["rev-parse", "--verify", "--end-of-options", revision + "^{commit}"]
        )
        sha = result.stdout.strip()
        if result.returncode or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            raise GitDenied("revision does not resolve to a commit")
        return sha

    def run(
        self,
        template: str,
        *,
        rev="HEAD",
        paths=(),
        count=20,
        source=None,
        message=None,
        remote="origin",
        branch=None,
        timeout=120,
    ) -> CmdResult:
        """No raw Git options accepted. Paths always follow --; counts are bounded."""
        if not isinstance(template, str) or template not in (
            "status",
            "diff",
            "log",
            "show",
            "commit",
            "restore",
            "checkout",
            "switch",
            "stash",
            "reset-hard",
            "clean",
            "branch-delete",
            "push",
        ):
            raise GitDenied("unknown Git template")
        if type(count) is not int or not 1 <= count <= 200:
            raise GitDenied("Git count must be an integer in [1, 200]")
        if not isinstance(paths, (tuple, list)) or any(
            not isinstance(p, str) or p.startswith(BANNED) for p in paths
        ):
            raise GitDenied("invalid Git path arguments")
        mutation = template not in ("status", "diff", "log", "show")
        # Match caller-supplied refs before revision resolution hides them in SHAs.
        fields = [(rev, "revision"), (remote, "remote")]
        if branch is not None:
            fields.append((branch, "refspec"))
        fields.extend((path, "path") for path in paths)
        derived = self.session.provenance.steered_by(fields)
        if derived:
            source = derived[0].location
        safe = [
            str(
                resolve_in_repo(
                    p, self.root, for_write=mutation, mode=self.session.mode
                ).relative_to(self.root)
            ).replace("\\", "/")
            for p in paths
        ]
        if mutation:
            current = self._call(["ls-files", "--cached", "-z"])
            if current.returncode:
                raise GitDenied("cannot validate current tracked paths")
            for name in current.stdout.split("\0"):
                if name:
                    resolve_in_repo(
                        name, self.root, for_write=True, mode=self.session.mode
                    )
        if template == "status":
            args = ["status", "--porcelain=v1", "--untracked-files=normal", "--", *safe]
        elif template == "diff":
            args = [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--end-of-options",
                self.validate_rev(rev),
                "--",
                *safe,
            ]
        elif template == "log":
            args = [
                "log",
                "--no-ext-diff",
                "--no-textconv",
                f"--max-count={count}",
                "--format=%H %s",
                "--end-of-options",
                self.validate_rev(rev),
                "--",
                *safe,
            ]
        elif template == "show":
            args = [
                "show",
                "--no-ext-diff",
                "--no-textconv",
                "--format=fuller",
                "--end-of-options",
                self.validate_rev(rev),
                "--",
                *safe,
            ]
        elif template == "commit":
            if not isinstance(message, str) or not message or "\0" in message:
                raise GitDenied("commit requires a message")
            args = ["commit", "--no-gpg-sign", "-m", message, "--", *safe]
        elif template in ("restore", "clean"):
            if not safe:
                raise GitDenied("restore/clean require explicit validated file paths")
            args = (
                ["restore", "--source=" + self.validate_rev(rev), "--", *safe]
                if template == "restore"
                else ["clean", "-fdx", "--", *safe]
            )
        elif template in ("checkout", "switch", "reset-hard", "stash"):
            sha = self.validate_rev(rev)
            tree = self._call(["ls-tree", "-r", "--name-only", "-z", sha])
            if tree.returncode:
                raise GitDenied("cannot validate mutation tree")
            for name in tree.stdout.split("\0"):
                if name:
                    resolve_in_repo(
                        name, self.root, for_write=True, mode=self.session.mode
                    )
            args = {
                "checkout": ["checkout", "--detach", sha],
                "switch": ["switch", "--detach", sha],
                "reset-hard": ["reset", "--hard", sha],
                "stash": ["stash", "push"],
            }[template]
        else:
            if (
                not isinstance(branch, str)
                or not REF.fullmatch(branch)
                or ".." in branch
                or "//" in branch
                or branch.endswith("/")
            ):
                raise GitDenied("invalid branch name")
            if template == "branch-delete":
                self.validate_rev("refs/heads/" + branch)
                args = ["branch", "-D", "--", branch]
            else:
                if self.session.mode == "confidential" or source:
                    origin = "; suggested by " + source if source else ""
                    raise GitDenied(
                        "confidential or steered pushes are denied" + origin
                    )
                self._audit()
                if (
                    not isinstance(remote, str)
                    or not REF.fullmatch(remote)
                    or f"remote.{remote.lower()}.url" not in self._config
                ):
                    raise GitDenied("push requires an audited named remote")
                destination = self._config[f"remote.{remote.lower()}.url"]
                origins = self.session.provenance.steered_by(remote_fields(destination))
                if origins:
                    raise GitDenied(
                        "steered push denied; suggested by " + origins[0].location
                    )
                args = [
                    "push",
                    "--no-verify",
                    "--",
                    remote,
                    self.validate_rev(rev) + ":refs/heads/" + branch,
                ]
        result = self._call(args, timeout=timeout, source=source, mutation=mutation)
        return prepare_command_result(
            result, session=self.session, ref="git:" + template
        )
