"""Phase 0 public-mode stub; confidential detection is not implemented."""

import os

from .types import Mode


def mode_for(repo_path: str | os.PathLike[str]) -> Mode:
    """Return public as specified for the integration stub.

    Does not inspect markers, paths, registry, or journal. Use only trusted public
    fixtures until real detection replaces this stub; never route private data
    using this result.
    """
    os.fspath(repo_path)
    return "public"
