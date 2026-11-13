"""Part 1 output-gate hook and Part 3 command-result sanitation."""

from .provenance import Source
from .secrets import secret_scan
from .types import CmdResult


def prepare_tool_result(text: str, *, index, source: Source) -> str:
    """Sanitize and index before truncation, spill/cache/journal or model use.

    Call for file contents, search snippets, list/symbol names and web results.
    Search/read owners must apply the separate sensitive-path filter first.
    """
    clean = secret_scan(text)
    index.add(clean, source)
    return clean


def prepare_command_result(result, *, session, ref: str, argv=None) -> CmdResult:
    session._output_counter += 1
    sequence = session._output_counter
    stdout = prepare_tool_result(
        result.stdout,
        index=session.provenance,
        source=Source("cmd", f"{ref}:{sequence}:stdout", 1),
    )
    stderr = prepare_tool_result(
        result.stderr,
        index=session.provenance,
        source=Source("cmd", f"{ref}:{sequence}:stderr", 1),
    )
    args = result.argv if argv is None else argv
    return CmdResult(
        [secret_scan(arg) for arg in args], result.returncode, stdout, stderr
    )
