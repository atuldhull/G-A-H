"""Grade an agent's final tree against a restored original pytest oracle."""

import argparse
from collections.abc import Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from bench.prepare import prepare_workspace


CONFIG_NAMES = frozenset({
    "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml",
    "pyproject.toml", "tox.ini", "setup.cfg",
})
CACHE_NAMES = frozenset({"__pycache__", ".pytest_cache"})
RUNTIME_NAMES = frozenset({
    "pytest", "pytest.py", "sitecustomize.py", "usercustomize.py",
})


def _extra_paths(paths: Sequence[str | os.PathLike[str]]) -> tuple[Path, ...]:
    result = []
    for value in paths:
        path = Path(value)
        if (
            path.is_absolute() or path.drive or not path.parts
            or ".." in path.parts or ".meta" in path.parts
        ):
            raise ValueError(f"Extra test paths must be relative inside the exercise: {value}")
        result.append(path)
    return tuple(result)


def _protected(path: Path, extra: tuple[Path, ...]) -> bool:
    if path.parts[0].casefold() in RUNTIME_NAMES:
        return True
    for component in path.parts:
        part = component.casefold()
        if part in {"test", "tests", "conftest.py"} or part in CONFIG_NAMES:
            return True
        if part.endswith(".py") and (part.startswith("test_") or part.endswith("_test.py")):
            return True
    folded = tuple(part.casefold() for part in path.parts)
    return any(
        folded[:len(item.parts)] == tuple(part.casefold() for part in item.parts)
        for item in extra
    )


def _remove_caches(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and path.name.casefold() in CACHE_NAMES:
            shutil.rmtree(path)
        elif path.is_file() and path.suffix.casefold() in {".pyc", ".pyo"}:
            path.unlink()


def _manifest(root: Path, extra: tuple[Path, ...]) -> dict[Path, str]:
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_file() and _protected(relative, extra):
            with path.open("rb") as stream:
                result[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _restore(
    original: Path, workspace: Path,
    original_files: dict[Path, str], final_files: dict[Path, str],
) -> None:
    for relative in final_files:
        _remove(workspace / relative)
    for relative in original_files:
        parent = workspace
        for component in relative.parts[:-1]:
            parent /= component
            if parent.exists() and not parent.is_dir():
                parent.unlink()
            parent.mkdir(exist_ok=True)
        target = workspace / relative
        _remove(target)
        shutil.copyfile(original / relative, target)


def _environment(workspace: Path) -> dict[str, str]:
    # Do not inherit caller test selection, plugins, or alternate Python paths.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("PYTEST_", "PYTHON"))
    }
    environment.update({
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTEST_ADDOPTS": shlex.join([
            "--rootdir", str(workspace), "--confcutdir", str(workspace),
        ]),
    })
    return environment


def grade_exercise(
    original: str | os.PathLike[str], final: str | os.PathLike[str],
    output: str | os.PathLike[str], *, task_id: str,
    timeout: float = 180, test_paths: Sequence[str | os.PathLike[str]] = (),
) -> dict[str, object]:
    """Write grading artifacts in a new output directory and return result.json.

    Only the subprocess imports exercise code. Inputs must be stable, self-contained
    exercise trees. A successful oracle exit and a test-edit policy violation are
    recorded independently; the latter is a red flag for the later harness.
    """
    if not task_id.strip():
        raise ValueError("task_id must not be empty")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and greater than zero")
    extra = _extra_paths(test_paths)
    output_path = Path(output).absolute()
    if os.path.lexists(output_path):
        raise FileExistsError(f"Output directory already exists: {output_path}")
    output_path = output_path.resolve(strict=False)
    for source in (original, final):
        source_path = Path(source).resolve(strict=False)
        if (
            source_path == output_path or source_path in output_path.parents
            or output_path in source_path.parents
        ):
            raise ValueError("Output must not overlap either exercise directory")

    output_path.mkdir()
    workspace = output_path / "workspace"
    stdout = output_path / "stdout.txt"
    stderr = output_path / "stderr.txt"
    stdout.touch()
    stderr.touch()
    result: dict[str, object] = {
        "schema_version": 1,
        "task_id": task_id,
        "pytest_exit_code": None,
        "timed_out": False,
        "timeout_seconds": timeout,
        "solved": False,
        "test_edit": False,
        "test_changes": {"added": [], "removed": [], "changed": []},
        "error": None,
        "stdout_path": str(stdout),
        "stderr_path": str(stderr),
        "workspace_path": str(workspace),
        "command": [sys.executable, "-m", "pytest", "-q"],
        "extra_test_paths": [path.as_posix() for path in extra],
    }
    try:
        frozen = prepare_workspace(original, output_path / "original")
        prepare_workspace(final, workspace)
        _remove_caches(frozen)
        _remove_caches(workspace)
        for path in extra:
            if not (frozen / path).exists():
                raise ValueError(f"Extra test path is absent from the original: {path}")
        original_files = _manifest(frozen, extra)
        final_files = _manifest(workspace, extra)
        changes = {
            "added": sorted(path.as_posix() for path in final_files.keys() - original_files.keys()),
            "removed": sorted(path.as_posix() for path in original_files.keys() - final_files.keys()),
            "changed": sorted(
                path.as_posix() for path in original_files.keys() & final_files.keys()
                if original_files[path] != final_files[path]
            ),
        }
        result["test_changes"] = changes
        result["test_edit"] = any(changes.values())
        _restore(frozen, workspace, original_files, final_files)
        # If the exercise has no usable root config, this blocks config discovery
        # above the artifact directory. Root configs restored above take priority.
        (output_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        with stdout.open("wb") as out, stderr.open("wb") as err:
            completed = subprocess.run(
                result["command"], cwd=workspace, env=_environment(workspace),
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                timeout=timeout, check=False,
            )
        result["pytest_exit_code"] = completed.returncode
        result["solved"] = completed.returncode == 0
    except subprocess.TimeoutExpired:
        result["timed_out"] = True
    except (OSError, ValueError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    (output_path / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--test-path", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        result = grade_exercise(
            args.original, args.final, args.output, task_id=args.task_id,
            timeout=args.timeout, test_paths=args.test_path,
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"Grading setup failed: {error}\n")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["solved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
