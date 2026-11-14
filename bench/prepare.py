"""Copy an exercise without its solution metadata or executing its code."""

import argparse
from collections.abc import Iterator, Sequence
import os
from pathlib import Path
import shutil
import stat


def _is_directory(path: Path) -> bool:
    """Inspect an entry without following symlinks or Windows junctions."""
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or path.is_junction():
        raise ValueError(f"Links and junctions are not allowed: {path}")
    if stat.S_ISDIR(metadata.st_mode):
        return True
    if stat.S_ISREG(metadata.st_mode):
        return False
    raise ValueError(f"Only ordinary files and directories are allowed: {path}")


def _inventory(
    root: Path, relative: Path = Path(), *, include: bool = True
) -> Iterator[tuple[Path, bool]]:
    """Validate the entire tree, including entries inside excluded directories."""
    for entry in sorted((root / relative).iterdir()):
        child = relative / entry.name
        is_directory = _is_directory(entry)
        keep = include and not (is_directory and entry.name == ".meta")
        if keep:
            yield child, is_directory
        if is_directory:
            yield from _inventory(root, child, include=keep)


def prepare_workspace(
    source: str | os.PathLike[str], destination: str | os.PathLike[str]
) -> Path:
    """Prepare a new workspace and return its absolute, resolved path.

    The source must be a directory and the destination's parent must exist.
    Every directory named ``.meta`` is omitted. Links, junctions, special files,
    existing destinations, and overlapping paths are rejected. The source must
    remain unchanged while preparation runs. File contents are copied; filesystem
    metadata such as timestamps and permissions is not preserved.
    """
    source_path = Path(source).absolute()
    if not _is_directory(source_path):
        raise NotADirectoryError(f"Source is not a directory: {source_path}")
    source_path = source_path.resolve(strict=True)
    if source_path.name == ".meta":
        raise ValueError("Source cannot itself be a .meta directory")

    destination_path = Path(destination).absolute()
    # lexists also catches dangling symlinks, which must never be overwritten.
    if os.path.lexists(destination_path):
        raise FileExistsError(f"Destination already exists: {destination_path}")
    destination_path = destination_path.resolve(strict=False)
    if (
        source_path == destination_path
        or source_path in destination_path.parents
        or destination_path in source_path.parents
    ):
        raise ValueError("Source and destination paths must not overlap")

    # Finish validation before creating anything in the destination.
    entries = list(_inventory(source_path))
    # Keep this outside the cleanup block: a racing creator owns its directory.
    destination_path.mkdir()
    try:
        for relative, is_directory in entries:
            original = source_path / relative
            copied = destination_path / relative
            if _is_directory(original) != is_directory:
                raise ValueError(f"Source entry changed during preparation: {original}")
            if is_directory:
                copied.mkdir()
            else:
                shutil.copyfile(original, copied, follow_symlinks=False)
                # Also reject a link swapped in between inspection and copying.
                _is_directory(copied)
    except BaseException:
        # Includes Ctrl+C as well as copy errors. Never remove an older directory.
        shutil.rmtree(destination_path)
        raise
    return destination_path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standalone benchmark preparation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        prepared = prepare_workspace(args.source, args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Preparation failed: {error}\n")
    print(f"Prepared workspace: {prepared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
