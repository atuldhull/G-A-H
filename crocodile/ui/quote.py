"""Static heuristic quotes: bounded filename/text reads, never execution or egress."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import math
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import unicodedata


Money = Decimal | int | float | str
RUNGS = ("cheap", "strong", "local")
EXCLUDED = {
    ".git", ".meta", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache",
}
TEXT_SUFFIXES = {".py", ".md", ".rst", ".txt", ".toml", ".ini", ".cfg", ".json"}
REFERENCES = re.compile(
    r"(?<![\w./:-])[\w.-]+(?:/[\w.-]+)*\.(?:py|md|rst|txt|toml|ini|cfg|json|js|ts|tsx|jsx|c|cpp|h|rs|go|java)(?![\w.-])",
    re.IGNORECASE,
)
TEST_DECLARATION = re.compile(r"^\s*(?:async\s+)?def\s+test_\w+\s*\(", re.MULTILINE)


@dataclass(frozen=True)
class RungPrice:
    model: str
    input_usd_per_million: Money | None
    output_usd_per_million: Money | None


@dataclass(frozen=True)
class BudgetSnapshot:
    remaining_usd: Money | None
    limit_usd: Money | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class UsageEstimate:
    """Caller-supplied total task usage estimate, not measured model usage."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class StaticQuote:
    """JSON-compatible structured data plus its literal terminal rendering."""

    data: dict[str, object]
    rendering: str


def _money(value: Money | None, label: str) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{label} must be a finite nonnegative amount or None")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"Invalid {label}") from error
    if (not number.is_finite() or number < 0 or not math.isfinite(float(number))
            or (number != 0 and float(number) == 0)):
        raise ValueError(f"{label} must be finite and nonnegative")
    return Fraction(number)


def _decimal(value: Fraction | None) -> str | None:
    """Serialize exact finite-decimal money without binary rounding artifacts."""
    if value is None:
        return None
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    places = max(twos, fives)
    scaled = value.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    text = str(scaled).rjust(places + 1, "0")
    if places:
        text = (text[:-places] + "." + text[-places:]).rstrip("0").rstrip(".")
    return text


def _plain_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError(f"{label} must be nonempty plain text")


def _kind(path: Path) -> str:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or path.is_junction():
        return "link"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    return "file" if stat.S_ISREG(metadata.st_mode) else "special"


def _sensitive(parts: Sequence[str]) -> bool:
    for part in parts:
        name = part.casefold()
        if (
            name in EXCLUDED or name in {".aws", ".ssh", ".codex", ".agents", "secrets", "credentials"}
            or name == ".env" or name.startswith(".env.")
            or name.endswith((".key", ".pem", ".p12", ".pfx"))
        ):
            return True
    return False


def _inspect(repository, permitted_text, max_entries, max_text_bytes):
    report = {
        "status": "unavailable", "complete": False, "files": [],
        "text_files": [], "text_characters": 0, "test_declarations": None,
        "warnings": [],
    }
    name = os.fspath(repository)
    if name.startswith(("//", "\\\\")) or PureWindowsPath(name).drive.startswith("\\\\"):
        report["warnings"].append("Network/UNC repository paths are not inspected")
        return report
    root = Path(repository).absolute()
    try:
        if _kind(root) != "directory":
            report["warnings"].append("Repository must be an ordinary directory, not a file or link")
            return report
        root = root.resolve(strict=True)
    except (OSError, ValueError):
        report["warnings"].append("Repository is missing or unreadable")
        return report
    report.update(status="available", complete=True)
    stack, seen = [root], 0
    while stack:
        directory = stack.pop()
        try:
            # Bound enumeration before sorting; do not load an unbounded directory.
            entries = []
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    seen += 1
                    if seen > max_entries:
                        report["complete"] = False
                        report["warnings"].append("Filename inspection limit reached; counts are partial")
                        break
                    entries.append(Path(entry.path))
            for path in sorted(entries, reverse=True):
                relative = path.relative_to(root)
                if _sensitive(relative.parts):
                    continue
                kind = _kind(path)
                if kind == "directory":
                    stack.append(path)
                elif kind == "file":
                    report["files"].append(relative.as_posix())
                else:
                    report["complete"] = False
                    report["warnings"].append(f"Skipped link or special entry: {relative.as_posix()}")
            if seen > max_entries:
                break
        except (OSError, ValueError):
            report["complete"] = False
            report["warnings"].append("A directory or entry was unreadable; counts are partial")
    report["files"].sort()
    remaining = max_text_bytes
    for supplied in sorted({os.fspath(path).replace("\\", "/") for path in permitted_text}):
        parts = supplied.split("/")
        item = {"path": supplied, "status": "blocked"}
        report["text_files"].append(item)
        if (
            any(part in {"", ".", ".."} for part in parts) or ":" in supplied
            or any(unicodedata.category(character).startswith("C") for character in supplied)
            or _sensitive(parts) or Path(supplied).suffix.casefold() not in TEXT_SUFFIXES
        ):
            report["complete"] = False
            report["warnings"].append(f"Text path not permitted: {supplied}")
            continue
        if remaining == 0:
            item["status"] = "limit_reached"
            report["complete"] = False
            report["warnings"].append(f"Text inspection limit reached: {supplied}")
            continue
        try:
            path = root
            for index, part in enumerate(parts):
                path /= part
                expected = "file" if index == len(parts) - 1 else "directory"
                if _kind(path) != expected:
                    raise ValueError("not an ordinary text file")
            # Even permitted files are bounded and must be UTF-8, non-binary text.
            with path.open("rb") as stream:
                raw = stream.read(remaining + 1)
            exceeded = len(raw) > remaining
            remaining -= min(len(raw), remaining)
            if exceeded:
                item["status"] = "limit_reached"
                report["complete"] = False
                report["warnings"].append(f"Text inspection limit reached: {supplied}")
                continue
            text = raw.decode("utf-8")
            if "\0" in text:
                raise ValueError("binary text")
            item.update(status="read", characters=len(text))
            report["text_characters"] += len(text)
            report["test_declarations"] = (report["test_declarations"] or 0) + len(TEST_DECLARATION.findall(text))
        except (OSError, UnicodeError, ValueError):
            item["status"] = "unavailable"
            report["complete"] = False
            report["warnings"].append(f"Text unavailable or not permitted UTF-8: {supplied}")
    return report


def quote_task(
    task: str, repository: str | os.PathLike[str], *,
    pricing: Mapping[str, RungPrice | None] | None = None,
    budget: BudgetSnapshot | None = None,
    usage: UsageEstimate | None = None,
    permitted_text: Sequence[str | os.PathLike[str]] = (),
    rungs: Sequence[str] = RUNGS,
    ascii_only: bool = False,
    max_entries: int = 2000,
    max_text_bytes: int = 131_072,
) -> StaticQuote:
    """Return structured heuristic data and literal text without code execution.

    Cost needs explicit model prices and caller task-level usage. Budget comparison
    also needs a remaining-budget snapshot and complete permitted inspection. None
    means unknown; local pricing, cached usage, and a probabilistic range are never
    inferred. Read only explicitly permitted text, with a total byte bound.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("Task must be nonempty text")
    if not isinstance(permitted_text, Sequence) or isinstance(permitted_text, (str, bytes)):
        raise ValueError("permitted_text must be a sequence of relative paths")
    if len(permitted_text) > 32:
        raise ValueError("At most 32 text paths may be permitted")
    if (not isinstance(rungs, Sequence) or isinstance(rungs, (str, bytes)) or not rungs or len(set(rungs)) != len(rungs)
            or any(rung not in RUNGS for rung in rungs)):
        raise ValueError("rungs must be a nonempty unique selection of cheap, strong, local")
    for value in (max_entries, max_text_bytes):
        if type(value) is not int or value < 1:
            raise ValueError("Inspection limits must be positive integers")
    if not isinstance(repository, (str, os.PathLike)) or not os.fspath(repository).strip():
        raise ValueError("repository must be an explicit local directory path")
    if pricing is not None and (not isinstance(pricing, Mapping) or set(pricing) - set(RUNGS)):
        raise ValueError("pricing must map cheap/strong/local to RungPrice or None")
    prices = {}
    for rung, price in (pricing or {}).items():
        if price is None:
            continue
        if not isinstance(price, RungPrice):
            raise ValueError("Each price must be RungPrice or None")
        _plain_text(price.model, "model")
        prices[rung] = (price.model, _money(price.input_usd_per_million, "input price"),
                        _money(price.output_usd_per_million, "output price"))
    if budget is not None and not isinstance(budget, BudgetSnapshot):
        raise ValueError("budget must be BudgetSnapshot or None")
    remaining = _money(budget.remaining_usd, "remaining budget") if budget else None
    limit = _money(budget.limit_usd, "budget limit") if budget else None
    if remaining is not None and limit is not None and remaining > limit:
        raise ValueError("Remaining budget must not exceed its limit")
    if budget and budget.as_of is not None:
        _plain_text(budget.as_of, "budget as_of")
    if usage is not None:
        if not isinstance(usage, UsageEstimate):
            raise ValueError("usage must be UsageEstimate or None")
        if any(type(value) is not int or value < 0 for value in (usage.input_tokens, usage.output_tokens)):
            raise ValueError("Usage estimates must be nonnegative integers")

    inspection = _inspect(repository, permitted_text, max_entries, max_text_bytes)
    references = sorted(set(REFERENCES.findall(task.replace("\\", "/"))))
    matched, missing, ambiguous = [], [], []
    for reference in references:
        compare = str.casefold if os.name == "nt" else str
        candidates = [path for path in inspection["files"] if compare(path) == compare(reference)
                      or ("/" not in reference and compare(Path(path).name) == compare(reference))]
        if len(candidates) == 1:
            matched.append(candidates[0])
        elif not candidates:
            missing.append(reference)
        else:
            ambiguous.append(reference)
    ready = inspection["complete"] and not missing and not ambiguous
    proxy = math.ceil((len(task) + sum(map(len, set(matched))) + inspection["text_characters"]) / 4)
    quotes = []
    for rung in rungs:
        model, input_rate, output_rate = prices.get(rung, (None, None, None))
        reason = None
        if not ready:
            reason = "repository inspection is unavailable, partial, or has unresolved filenames"
        elif input_rate is None or output_rate is None:
            reason = "explicit model prices are unavailable"
        elif usage is None:
            reason = "caller task-level token usage estimate is unavailable"
        cost = None if reason else (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000
        fits = None if cost is None or remaining is None else cost <= remaining
        quotes.append({
            "rung": rung, "model": model, "estimated_cost_usd": _decimal(cost),
            "input_usd_per_million": _decimal(input_rate),
            "output_usd_per_million": _decimal(output_rate),
            "cost_reason": reason, "estimated_within_remaining": fits,
            "budget_reason": "cost or remaining-budget input unavailable" if fits is None else None,
            "estimated_range_usd": None,
        })
    data = {
        "schema_version": 1, "method": "heuristic v1", "estimated": True,
        "repository": os.fspath(repository), "inspection": inspection,
        "references": {"matched": sorted(set(matched)), "missing": missing, "ambiguous": ambiguous},
        "observed_input_token_proxy": proxy,
        "proxy_rule": "ceil((task characters + matched filename characters + permitted text characters) / 4); not session usage",
        "usage_estimate": None if usage is None else {
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "basis": "caller-supplied total task estimate",
        },
        "budget": {"remaining_usd": _decimal(remaining), "limit_usd": _decimal(limit),
                   "as_of": budget.as_of if budget else None},
        "rungs": quotes,
        "limitations": [
            "Uncalibrated heuristic; no probability/confidence range is available",
            "Character proxy is not a model tokenizer or a prediction of total task usage",
            "No cache discounts, retries, tool turns, fallback charges, fees, or local compute expense are inferred",
            "Budget snapshot may be stale; an estimated comparison does not reserve money or guarantee a fit",
            "Static test declarations are text matches, not collected or executed tests",
        ],
    }
    return StaticQuote(data=data, rendering=render_quote(data, ascii_only=ascii_only))


def _display(value, ascii_only):
    text = str(value)
    text = "".join(f"\\u{ord(char):04x}" if unicodedata.category(char).startswith("C") else char for char in text)
    return text.encode("ascii", "backslashreplace").decode("ascii") if ascii_only else text


def render_quote(data: Mapping[str, object], *, ascii_only: bool = False) -> str:
    """Render literal text; escape terminal controls, bidi formatting, and ASCII fallbacks."""
    separator = "-" if ascii_only else "\u2014"
    inspection = data["inspection"]
    references = data["references"]
    observed = str(len(inspection["files"]))
    if not inspection["complete"]:
        observed += " (partial/unavailable)"
    lines = [f"Quote {separator} heuristic v1 / estimated (static; no code executed)",
             f"Repository: {_display(data['repository'], ascii_only)} [{inspection['status']}]",
             f"Referenced files found: {len(references['matched'])}; filename observations: {observed}",
             f"Permitted text files read: {sum(item['status'] == 'read' for item in inspection['text_files'])}",
             f"Test declarations (text matches): {inspection['test_declarations'] if inspection['test_declarations'] is not None else 'unknown (no permitted text read)'}",
             f"Observed input proxy: ~{data['observed_input_token_proxy']} tokens (characters / 4; not total task usage)"]
    usage = data["usage_estimate"]
    lines.append("Estimated task usage: unknown" if usage is None else
                 f"Estimated task usage (caller): {usage['input_tokens']} input / {usage['output_tokens']} output tokens")
    lines += ["", "rung | model | estimated USD | estimated budget comparison"]
    for rung in data["rungs"]:
        cost = rung["estimated_cost_usd"]
        cost_text = "unknown" if cost is None else "~$" + format(Decimal(cost), ".2g")
        fits = rung["estimated_within_remaining"]
        status = "unknown" if fits is None else ("within supplied remaining (estimate)" if fits else "above supplied remaining (estimate)")
        lines.append(f"{rung['rung']} | {_display(rung['model'] or 'unknown', ascii_only)} | {cost_text} | {status}")
        if rung["cost_reason"]:
            lines.append(f"  {_display(rung['cost_reason'], ascii_only)}")
    budget = data["budget"]
    lines += ["", "Budget remaining: " + ("unknown" if budget["remaining_usd"] is None else "$" + budget["remaining_usd"]),
              "Budget limit: " + ("unknown" if budget["limit_usd"] is None else "$" + budget["limit_usd"])]
    if budget["as_of"]:
        lines.append("Snapshot as of: " + _display(budget["as_of"], ascii_only))
    for key in ("missing", "ambiguous"):
        if references[key]:
            lines.append(f"{key.capitalize()} file references: " + ", ".join(_display(item, ascii_only) for item in references[key]))
    lines.extend("Warning: " + _display(item, ascii_only) for item in inspection["warnings"])
    lines.extend("Note: " + _display(item, ascii_only) for item in data["limitations"])
    return "\n".join(lines)
