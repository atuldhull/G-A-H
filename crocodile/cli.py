"""crocodile CLI (Part 1: `run`). Other parts add their own subcommands to `app`."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__, services, ui_bridge
from .loop import ALL_FLAGS, Agent

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Crocodile: snaps up wasted tokens.")
err = Console(stderr=True, highlight=False)


def _flags(spec: str) -> set[str]:
    spec = spec.strip().lower()
    if spec in ("all", ""):
        return set(ALL_FLAGS)
    if spec in ("none", "off"):
        return set()
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if part.startswith("-"):
            out = (out or set(ALL_FLAGS)) - {part[1:]}
        elif part in ALL_FLAGS:
            out.add(part)
        else:
            raise typer.BadParameter(f"unknown flag {part}; known: {', '.join(sorted(ALL_FLAGS))}")
    return out


def _printer(quiet: bool, holder: dict):
    def on_event(kind: str, d: dict) -> None:
        if quiet:
            return
        if kind == "model_call":
            u = d["usage"]
            hit = f"{100 * u['cached_tokens'] // max(1, u['prompt_tokens'])}%" if u["prompt_tokens"] else "-"
            err.print(
                f"[dim]· {d['model']}  in {u['prompt_tokens']} (cache {hit})  out {u['completion_tokens']}"
                f"  -> {', '.join(d['tool_calls']) or 'text'}[/dim]"
            )
        elif (
            kind == "tool_done"
            and holder.get("agent") is not None
            and ui_bridge.available()
            and d.get("tool") == "run_tests"
        ):
            try:  # Part 4 status line after test runs (cheap; skipped if Part 4 rejects a value)
                from crocodile.ui import render_status

                err.print(render_status(ui_bridge.snapshot(holder["agent"])), markup=False, highlight=False)
            except ValueError:
                pass
        elif kind == "takeover" and services.is_stub("egress"):  # the real gateway draws its own banner
            err.print(
                f"[bold yellow]▲ MODEL TAKEOVER → {d['model']} (primary failed: {d.get('error_class')})"
                "[/bold yellow]"
            )
        elif kind == "escalate":
            err.print(f"[bold magenta]▲ ESCALATE: {d['reason']} → {d['to']}[/bold magenta]")
        elif kind == "green":
            err.print(f"[bold green]✔ tests green ({d['stage']})[/bold green]")
        elif kind == "tool_done" and not d["ok"]:
            err.print(f"[dim red]  ✗ {d['tool']}[/dim red]")

    return on_event


@app.command()
def run(
    task: str | None = typer.Argument(None, help="Task text (or use --task-file)."),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root."),
    task_file: Path | None = typer.Option(None, "--task-file"),
    test: list[str] = typer.Option(
        [], "--test", help="Oracle test file/id (repeatable). Enables stop-on-green."
    ),
    full_suite: bool = typer.Option(
        False, "--full-suite", help="Also run the whole suite (regression check)."
    ),
    flags: str = typer.Option("all", "--flags", help="all | none | comma list | -flag to drop one."),
    tier: str = typer.Option("cheap", "--tier", help="Starting model tier: cheap | strong."),
    steps: int = typer.Option(30, "--steps", help="Step cap."),
    yes: bool = typer.Option(False, "--yes", help="Rejected here; automation requires the trusted bench API."),
    json_out: Path | None = typer.Option(None, "--json-out", help="Write the receipt as JSON."),
    quiet: bool = typer.Option(False, "--quiet"),
    user: str = typer.Option(
        os.environ.get("USERNAME") or os.environ.get("USER") or "default",
        "--user",
        help="Budget principal (per-user daily limit).",
    ),
    resume: str | None = typer.Option(
        None, "--resume", help="Resume a signed session checkpoint; approvals are not restored."
    ),
):
    """Run the agent on a task. Exit 0 = solved (tests green), 1 = not solved, 2 = error."""
    if task_file:
        task = task_file.read_text(encoding="utf-8")
    if not task and not resume:
        raise typer.BadParameter("give a task or --task-file")
    if tier not in ("cheap", "strong"):
        raise typer.BadParameter("tier must be cheap or strong")
    if yes:
        raise typer.BadParameter(
            "--yes is not permitted on user repositories; use the trusted for_bench harness"
        )
    holder: dict = {}
    try:
        agent = Agent(
            repo,
            task or "",
            oracle=test or None,
            full_suite=full_suite,
            flags=_flags(flags),
            tier=tier,
            approve_mode="ask",
            step_cap=steps,
            on_event=_printer(quiet, holder),
            user=user,
            resume=resume,
        )
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        from .security.approvals import escape

        err.print("Security initialization refused: " + escape(str(error)), markup=False)
        raise typer.Exit(2) from error
    holder["agent"] = agent
    if agent.r.stubs and not quiet:
        err.print(f"[yellow]note: using stubs for {', '.join(agent.r.stubs)} (not for demos)[/yellow]")
    try:
        r = agent.run()
    except Exception as e:  # model/HTTP errors: still write a receipt for the bench
        agent.r.status = f"ERROR: {type(e).__name__}: {e}"[:300]
        r = agent.r
        code = 2
    else:
        code = 0 if r.solved else 1
    u = r.usage
    err.print(
        f"[bold]{r.status}[/bold]  steps {r.steps}  tokens in {u.prompt_tokens} (cached {u.cached_tokens})"
        f" out {u.completion_tokens}  avoided ~{r.tokens_avoided}  {r.wall_s}s"
    )
    if r.savings and not quiet:
        total = sum(r.savings.values())
        items = "  ".join(f"{k} -{v:,}" for k, v in list(r.savings.items())[:5])
        err.print(f"[green]saved ~{total:,} input tokens (estimated, first-order): {items}[/green]")
    if r.rewinds or r.checkpoints:
        err.print(f"[dim]rewinds {r.rewinds}  checkpoints kept {r.checkpoints}[/dim]")
    if not quiet and ui_bridge.available():
        try:  # Part 4's evidence-gated receipt
            from crocodile.ui import render_receipt

            err.print(render_receipt(ui_bridge.receipt(agent)), markup=False, highlight=False)
        except ValueError as e:
            err.print(f"[dim](receipt unavailable: {e})[/dim]")
    if json_out:
        json_out.write_text(json.dumps(r.to_json(), indent=2), encoding="utf-8")
    raise typer.Exit(code)


@app.command()
def quote(
    task: str | None = typer.Argument(None, help="Task text (or use --task-file)."),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root."),
    task_file: Path | None = typer.Option(None, "--task-file"),
    ascii_only: bool = typer.Option(False, "--ascii"),
):
    """Static cost quote before running (no code is executed, no model is called)."""
    if task_file:
        task = task_file.read_text(encoding="utf-8")
    if not task:
        raise typer.BadParameter("give a task or --task-file")
    if not ui_bridge.available():
        raise typer.BadParameter("quote needs the Part 4 UI package (crocodile.ui)")
    typer.echo(ui_bridge.quote(task, repo, ascii_only=ascii_only).rendering)


@app.command()
def version():
    """Print the version."""
    typer.echo(__version__)


@app.command()
def audit(
    session: str | None = typer.Argument(None),
    all_sessions: bool = typer.Option(False, "--all"),
    state_db: Path | None = typer.Option(None, "--state-db"),
    allow_model: list[str] = typer.Option(..., "--allow-model"),
    gateway_log: Path | None = typer.Option(None, "--gateway-log"),
    journal: list[Path] = typer.Option([], "--journal"),
):
    """Audit recorded egress (0 PASS, 1 FAIL, 2 INCOMPLETE); no requests are sent."""
    from .security import audit as handler

    args = ["--state-db", str(state_db or adapters_state_path())]
    for model in allow_model:
        args += ["--allow-model", model]
    if session:
        args += ["--session", session]
    if all_sessions:
        args += ["--all"]
    if session and all_sessions:
        raise typer.BadParameter("choose a session or --all")
    if gateway_log:
        args += ["--gateway-log", str(gateway_log)]
    for path in journal:
        args += ["--journal", str(path)]
    raise typer.Exit(handler.main(args))


def adapters_state_path():
    from .runtime_security import state_path

    return state_path()


@app.command()
def undo(
    steps: int = typer.Argument(1, min=1),
    repo: Path = typer.Option(Path("."), "--repo"),
    list_only: bool = typer.Option(False, "--list"),
):
    """Undo file edits with conflict checks; snapshots use separate shadow Git."""
    from .runtime_security import SecurityContext
    from .security import undo as handler

    try:
        factory = services._cache.get("security_factory", SecurityContext)
        context = factory(repo.resolve(), "user-invoked file undo")
        args = [str(steps), "--repo", str(repo)] + (["--list"] if list_only else [])
        code = handler.main(args, session=context.p3)
    except (RuntimeError, OSError, ValueError) as error:
        from .security.approvals import escape

        err.print(escape(str(error)), markup=False)
        raise typer.Exit(1) from error
    raise typer.Exit(code)


@app.command()
def doctor(
    repo: Path = typer.Option(Path("."), "--repo"),
    config_dir: Path | None = typer.Option(None, "--config-dir"),
):
    """User diagnostics with masked credentials (0 healthy, 1 failure)."""
    from .security import doctor as handler

    args = ["--repo", str(repo)]
    if config_dir is not None:
        args += ["--config-dir", str(config_dir)]
    raise typer.Exit(handler.main(args))


@app.command()
def redteam(inventory_only: bool = typer.Option(False, "--inventory")):
    """Show Part 4's case inventory; unimplemented assertions return 2, never PASS."""
    from redteam.inventory import inventory

    report = inventory(Path(__file__).resolve().parents[1])
    typer.echo(json.dumps(report, indent=2))
    raise typer.Exit(0 if inventory_only else 2)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
