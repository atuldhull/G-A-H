"""Literal provenance-lite: untrusted text can influence a proposal, never policy."""

import ast
import re
import textwrap
from dataclasses import dataclass, replace
from typing import Literal
from urllib.parse import urlsplit

URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>|`]+")
HOST = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z0-9-]{2,}(?::[0-9]+)?$"
)


@dataclass(frozen=True)
class Source:
    kind: Literal["file", "cmd", "web", "search"]
    ref: str
    line: int | None = None

    def __post_init__(self):
        if (
            self.kind not in ("file", "cmd", "web", "search")
            or not isinstance(self.ref, str)
            or not self.ref
        ):
            raise ValueError("invalid provenance source")
        if self.line is not None and (type(self.line) is not int or self.line < 1):
            raise ValueError("source line must be a positive integer")

    @property
    def location(self) -> str:
        return self.ref if self.line is None else f"{self.ref}:{self.line}"


class ProvenanceIndex:
    """One session's append-only observations, ordered by first exposure.

    No case folding, decoding, fuzzy matching, or task paraphrase matching.
    Starting lines are one-based; multiline matches retain their original line.
    """

    def __init__(self, task_text: str = ""):
        if not isinstance(task_text, str):
            raise TypeError("task_text must be a string")
        self._task = task_text
        self._entries: list[tuple[str, Source]] = []

    def add(self, text: str, src: Source) -> None:
        if not isinstance(text, str) or not isinstance(src, Source):
            raise TypeError("add requires text and a Source")
        if text:
            self._entries.append((text, src))

    def steered_by(self, fields: list[tuple[str, str]]) -> list[Source]:
        values = []
        for value, kind in fields:
            if not isinstance(value, str) or not isinstance(kind, str):
                raise TypeError("sensitive fields must contain string pairs")
            if (
                value
                and (len(value) >= 8 or kind in ("url", "host"))
                and value not in self._task
                and value not in values
            ):
                values.append(value)
        sources = []
        for text, src in self._entries:
            positions = sorted(
                {position for value in values if (position := text.find(value)) >= 0}
            )
            for position in positions:
                source = (
                    replace(src, line=src.line + text.count("\n", 0, position))
                    if src.line is not None
                    else src
                )
                if source not in sources:
                    sources.append(source)
        return sources


def url_fields(text: str) -> list[tuple[str, str]]:
    fields = []
    for match in URL.finditer(text):
        url = match[0].rstrip(").,;")
        if url.endswith("]") and not url.split("://", 1)[1].startswith("["):
            url = url.rstrip("]")
        fields.append((url, "url"))
        try:
            authority = urlsplit(url).netloc.rsplit("@", 1)[-1]
        except ValueError:
            continue
        # Preserve the original host spelling: urlsplit.hostname folds case.
        host = (
            authority[1:].split("]", 1)[0]
            if authority.startswith("[")
            else authority.split(":", 1)[0]
        )
        if host:
            fields.append((host, "host"))
    return fields


def remote_fields(value: str) -> list[tuple[str, str]]:
    """Git's URI and SCP-style remotes, preserving literal host spelling."""
    fields = [(value, "remote"), *url_fields(value)]
    if "://" not in value:
        match = re.fullmatch(
            r"(?:[^@\s/]+@)?(?P<host>\[[^\]]+\]|[^:/\s]+):(?P<path>.*)", value
        )
        if match and not (
            len(match["host"]) == 1 and match["path"].startswith(("/", "\\"))
        ):
            fields.append((match["host"].strip("[]"), "host"))
    return fields


def imports(text: str) -> set[str]:
    try:
        tree = ast.parse(textwrap.dedent(text))
    except (SyntaxError, ValueError, RecursionError):
        # REPLACE sides can be fragments; this fallback never executes them.
        return {
            match[1] or match[2]
            for match in re.finditer(
                r"(?m)^\s*(?:from\s+([.\w]+)\s+import\b|import\s+([\w.]+))", text
            )
        }
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add("." * node.level + (node.module or ""))
            result.update(alias.name for alias in node.names if alias.name != "*")
    return result


def sensitive_fields(action, *, previous_texts=()) -> list[tuple[str, str]]:
    """Typed action values; previous_texts are validated edit pre-images only."""
    fields = []
    for value in action.argv or ():
        fields.append((value, "argv"))
        fields.extend(url_fields(value))
        if HOST.fullmatch(value):
            fields.append((value.split(":", 1)[0], "host"))
    fields.extend((value, "path") for value in action.paths)
    if action.query is not None:
        fields.append((action.query, "query"))
        fields.extend(url_fields(action.query))
    if action.url is not None:
        fields.append((action.url, "url"))
        fields.extend(url_fields(action.url))
    old_imports = set().union(*(imports(text) for text in previous_texts))
    for replacement in action.replacements:
        fields.extend(url_fields(replacement))
        fields.extend(
            (name, "import") for name in sorted(imports(replacement) - old_imports)
        )
    return fields
