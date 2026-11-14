"""Tavily search client and documentation lookup tool.

Implements lean, gated search (architecture/09 §7):
- Direct REST call to api.tavily.com/search (no SDK dependency).
- Basic search depth (1 credit), max 3 results, raw content excluded.
- Maximum 3 calls per task limit.
- Completely blocked and unregistered in confidential mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TAVILY_API_URL = "https://api.tavily.com/search"
MAX_CALLS_PER_TASK = 3
MAX_SNIPPET_CHARS = 4000  # ~1000-1500 tokens


class TavilyDeny(Exception):
    """Raised when Tavily is invoked illegally (e.g. in confidential mode or call cap exceeded)."""
    pass


@dataclass
class TavilyResult:
    query: str
    results: list[dict[str, str]] = field(default_factory=list)
    credits_used: int = 1
    total_chars: int = 0


def sanitize_query(query: str, canaries: list[str] | None = None) -> str:
    """Sanitizes search query to prevent accidental token or secret leakage."""
    sanitized = query.strip()
    canaries = canaries or []
    for c in canaries:
        if c in sanitized:
            sanitized = sanitized.replace(c, "[CANARY_REDACTED]")

    # Strip code block fences or large multi-line bodies
    if "```" in sanitized:
        sanitized = re.sub(r"```.*?```", "", sanitized, flags=re.DOTALL)

    return sanitized


def build_tavily_request(
    query: str,
    api_key: str,
    domains: list[str] | None = None,
    canaries: list[str] | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Builds lean JSON payload for Tavily search."""
    clean_query = sanitize_query(query, canaries=canaries)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "query": clean_query,
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": False,
        "include_raw_content": False,
        "auto_parameters": False,
        "include_usage": True,
    }
    if domains:
        payload["include_domains"] = domains
        payload["include_domains_mode"] = "restrict"

    return TAVILY_API_URL, headers, payload


def parse_tavily_response(data: dict[str, Any]) -> TavilyResult:
    """Parses Tavily response extracting clean snippets under the size limit."""
    results = []
    total_chars = 0
    raw_results = data.get("results", [])

    for r in raw_results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")

        # Truncate content to keep snippets concise
        if total_chars + len(content) > MAX_SNIPPET_CHARS:
            content = content[: max(0, MAX_SNIPPET_CHARS - total_chars)]

        results.append({"title": title, "url": url, "content": content})
        total_chars += len(title) + len(url) + len(content)
        if total_chars >= MAX_SNIPPET_CHARS:
            break

    credits_used = data.get("usage", {}).get("credits", 1)
    return TavilyResult(
        query=data.get("query", ""),
        results=results,
        credits_used=credits_used,
        total_chars=total_chars,
    )
