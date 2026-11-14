"""Deterministic credential redaction and owner-facing search exclusions.

No secret lookup or credential-store access. Match plaintext credential forms
from Architecture 05 and return only stable kind/SHA-256-prefix markers.
"""

import base64
import binascii
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from .paths import resolve_in_repo

READ_REDACT = (
    ".env*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa*",
    "**/id_ed25519*",
    "**/*.ppk",
    "**/*.p12",
    "**/*.pfx",
    "**/*.jks",
    "**/*.kdbx",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "_netrc",
    "**/credentials*.json",
    "**/*service-account*.json",
    "**/secrets.y*ml",
    "**/*.tfstate",
    ".docker/config.json",
)
MARKER = re.compile(r"\[REDACTED:[a-z_]+:[0-9a-f]{8}\]")
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
PEM = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----[\s\S]*?(?:-----END \1-----|\Z)")
PATTERNS = (
    ("pem", PEM, 0),
    ("aws", re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9])"), 0),
    (
        "github",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})(?![A-Za-z0-9_])"
        ),
        0,
    ),
    (
        "api_key",
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])"),
        0,
    ),
    (
        "slack",
        re.compile(r"(?<![A-Za-z0-9_-])xox[bp]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9_-])"),
        0,
    ),
    (
        "url_credentials",
        re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^\s/@]+:[^\s/@]*)@"),
        1,
    ),
    (
        "jwt",
        re.compile(
            r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{3,}={0,2}\.[A-Za-z0-9_-]{2,}={0,2}\.[A-Za-z0-9_-]*={0,2}(?![A-Za-z0-9_-])"
        ),
        0,
    ),
)
NAME = r"(?:(?:[A-Za-z_][A-Za-z0-9_.-]*[_-])?(?:KEY|TOKEN|SECRET))"
QUOTED = re.compile(
    r"(?<![\w])['\"]?"
    + NAME
    + r"['\"]?\s*[:=]\s*(?P<quote>['\"])(?P<value>(?:\\(?:[^\r\n]|(?=\r?\n|\Z))|(?!(?P=quote))[^\\\r\n])*)(?:(?P=quote)|(?=\r?\n|\Z))",
    re.IGNORECASE,
)
UNQUOTED = re.compile(
    r"(?<![\w])"
    + NAME
    + r"\s*[:=]\s*(?P<value>\$\{[^}\r\n]*\}|\{\{[^}\r\n]*\}\}|\[REDACTED:[a-z_]+:[0-9a-f]{8}\]|[^\s,;}\])'\"]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    kind: str
    sha8: str
    start: int
    end: int


def entropy(value: str) -> float:
    counts = Counter(value)
    return (
        -sum(
            (count / len(value)) * math.log2(count / len(value))
            for count in counts.values()
        )
        if value
        else 0.0
    )


def _high_entropy(value: str) -> bool:
    return (
        len(value) >= 16
        and entropy(value) >= 3.5
        and not MARKER.fullmatch(value)
        and not re.fullmatch(
            r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|\{\{\s*[A-Za-z_][A-Za-z0-9_.]*\s*\}\}", value
        )
    )


def _jwt_header(value: str) -> bool:
    header = value.partition(".")[0]
    try:
        decoded = base64.b64decode(
            header + "=" * (-len(header) % 4), altchars=b"-_", validate=True
        )
        return isinstance(json.loads(decoded), dict)
    except (binascii.Error, ValueError, UnicodeError, RecursionError):
        return False


def redact_with_findings(
    text: str, *, strip_ansi: bool = True
) -> tuple[str, tuple[Finding, ...]]:
    if not isinstance(text, str):
        raise TypeError("secret scanner requires text")
    if strip_ansi:
        text = ANSI.sub(lambda match: "\n" * match[0].count("\n"), text)
    protected = [match.span() for match in MARKER.finditer(text)]
    candidates = []
    for priority, (kind, pattern, group) in enumerate(PATTERNS):
        for match in pattern.finditer(text):
            if kind == "jwt" and not _jwt_header(match[0]):
                continue
            candidates.append((*match.span(group), priority, kind))
    for pattern in (QUOTED, UNQUOTED):
        for match in pattern.finditer(text):
            if _high_entropy(match["value"]):
                candidates.append((*match.span("value"), len(PATTERNS), "high_entropy"))
    cursor, output, findings = 0, [], []
    for start, end, _, kind in sorted(
        candidates, key=lambda item: (item[0], -(item[1] - item[0]), item[2])
    ):
        if start < cursor or any(
            start < right and end > left for left, right in protected
        ):
            continue
        sha8 = hashlib.sha256(
            text[start:end].encode("utf-8", errors="surrogatepass")
        ).hexdigest()[:8]
        output += [
            text[cursor:start],
            f"[REDACTED:{kind}:{sha8}]" + "\n" * text[start:end].count("\n"),
        ]
        findings.append(Finding(kind, sha8, start, end))
        cursor = end
    output.append(text[cursor:])
    return "".join(output), tuple(findings)


def secret_scan(text: str, *, strip_ansi: bool = True) -> str:
    """Redact before truncation, spill, caching, journaling or model exposure."""
    return redact_with_findings(text, strip_ansi=strip_ansi)[0]


redact = secret_scan


def path_is_redacted(path: str | Path) -> bool:
    value = str(path).replace("\\", "/").lower().removeprefix("./")
    # Include directory prefixes, matching ripgrep's excluded-directory behavior.
    prefixes = [
        "/".join(value.split("/")[:end]) for end in range(1, len(value.split("/")) + 1)
    ]
    for prefix in prefixes:
        for pattern in READ_REDACT:
            plain = pattern.removeprefix("**/")
            if fnmatchcase(prefix, plain) or fnmatchcase(prefix, "**/" + plain):
                return True
    return False


def search_exclusion_args() -> list[str]:
    return [value for pattern in READ_REDACT for value in ("--glob", "!" + pattern)]


def search_result_allowed(path: str | Path, *, repo_root: Path, mode="public") -> bool:
    """Post-filter both lexical and canonical paths; do not read their contents."""
    if path_is_redacted(path):
        return False
    try:
        canonical = resolve_in_repo(path, repo_root, mode=mode)
        return not path_is_redacted(canonical.relative_to(repo_root.resolve()))
    except (OSError, ValueError, TypeError, RuntimeError):
        return False
