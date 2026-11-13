"""Static pytest configuration inventory; never imports repository code."""

import configparser
import hashlib
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAMES = {
    "conftest.py",
    "pytest.ini",
    ".pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "pytest.toml",
    ".pytest.toml",
}
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def check_options(options: str) -> None:
    """Refuse collection/config indirection that this static inventory cannot cover."""
    if any(
        option in options
        for option in (
            "-c",
            "-o",
            "--rootdir",
            "--confcutdir",
            "--override-ini",
            "--pyargs",
            "--config-file",
            "--noconftest",
            "@",
        )
    ):
        raise ValueError(
            "pytest config/collection overrides are not supported for consent"
        )
    if "/" in options or "\\" in options or ".." in options:
        raise ValueError("path-bearing pytest addopts are not supported for consent")


def _check_config(path: Path, content: str, root: Path) -> None:
    if path.name == "conftest.py":
        return
    try:
        if path.suffix == ".toml":
            data = tomllib.loads(content)
            table = (
                data.get("tool", {}).get("pytest", {})
                if path.name == "pyproject.toml"
                else data.get("pytest", {})
            )
            options = table.get("ini_options", {}).get("addopts", "")
            if "addopts" in table:
                options = table["addopts"]
            if isinstance(options, list) and all(isinstance(v, str) for v in options):
                options = " ".join(options)
            selected_paths = [
                section.get(key, [])
                for section in (table, table.get("ini_options", {}))
                for key in ("testpaths", "pythonpath")
            ]
        else:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read_string(content)
            section = "tool:pytest" if path.name == "setup.cfg" else "pytest"
            options = parser.get(section, "addopts", fallback="")
            selected_paths = [
                parser.get(section, key, fallback="")
                for key in ("testpaths", "pythonpath")
            ]
        if not isinstance(options, str):
            raise TypeError("unrecognized pytest addopts schema")
        check_options(options)
        for values in selected_paths:
            if isinstance(values, str):
                if any(char in values for char in "\"'"):
                    raise ValueError(
                        "quoted pytest paths require an extended static scanner"
                    )
                values = values.split()
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise TypeError("unrecognized pytest path schema")
            for value in values:
                selected = (path.parent / value).resolve()
                if not selected.is_relative_to(root) or any(
                    part.lower() in SKIP for part in selected.relative_to(root).parts
                ):
                    raise ValueError(
                        "configured pytest path leaves the static config inventory"
                    )
    except (
        configparser.Error,
        tomllib.TOMLDecodeError,
        AttributeError,
        TypeError,
    ) as error:
        raise ValueError("cannot statically review pytest configuration") from error


@dataclass(frozen=True)
class ConfigFile:
    path: str
    sha256: str
    content: str


def discover(root: Path, cwd: Path, *, cap: int = 50_000) -> tuple[ConfigFile, ...]:
    """Inventory configs below root and above cwd, including additions/removals.

    Read errors, linked directories and an exhausted scan fail closed.
    A superset avoids importing pytest to determine applicable conftests.
    """
    found = set()
    count = 0

    def fail(error):
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        count += len(dirs) + len(files)
        if count > cap:
            raise ValueError("pytest config scan exceeded entry cap")
        for name in dirs:
            path = Path(directory, name)
            if name not in SKIP and (
                path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            ):
                raise ValueError("pytest config scan encountered linked directory")
        dirs[:] = [name for name in dirs if name not in SKIP]
        found.update(Path(directory, name) for name in files if name in CONFIG_NAMES)
    for directory in (cwd, *cwd.parents):
        for name in CONFIG_NAMES:
            path = directory / name
            if path.exists():
                found.add(path)
    result = []
    for path in sorted(found):
        if path.is_symlink() or not path.is_file():
            raise ValueError("pytest configuration must be a regular file")
        if path.stat().st_size > 2_000_000:
            raise ValueError("pytest configuration exceeds review size limit")
        raw = path.read_bytes()
        content = raw.decode("utf-8", errors="strict")
        _check_config(path, content, root)
        result.append(
            ConfigFile(
                str(path.resolve()),
                hashlib.sha256(raw).hexdigest(),
                content,
            )
        )
    return tuple(result)
