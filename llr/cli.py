"""
CLI entry point for LadderLogicReview.

Usage examples:
  llr review program.asc
  llr review program.asc --deep --api-key sk-ant-...
  llr review program.asc --deep --model claude-opus-4-7
  llr review program.asc --output report.html
  llr review program.asc --output report.json
  llr rules list
  llr rules validate
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from . import __version__
from .parser import parse_asc
from .parser.asc_parser import AscParseError
from .rules.engine import RuleEngine
from .report.formatter import ReportFormatter
from .analysis.claude_client import ClaudeClient, ClaudeAnalysisError

console = Console()
err_console = Console(stderr=True)

_DEFAULT_RULES = Path(__file__).parent.parent / "rules.yaml"


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="llr")
def cli() -> None:
    """LadderLogicReview — static analyser for FPWin Pro 7 .asc files."""


# ---------------------------------------------------------------------------
# llr review
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("asc_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--rules", "rules_path",
    default=None,
    envvar="LLR_RULES",
    show_default=True,
    help="Path to rules.yaml (defaults to rules.yaml next to the executable).",
)
@click.option(
    "--deep", is_flag=True, default=False,
    help="Enable Claude API deep analysis in addition to local rule checks.",
)
@click.option(
    "--api-key",
    default=None,
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var).",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model to use for deep analysis.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Write report to file. Extension determines format: .html or .json.",
)
@click.option(
    "--no-local", is_flag=True, default=False,
    help="Skip local rule checks (use with --deep for Claude-only analysis).",
)
@click.option(
    "--min-severity",
    type=click.Choice(["error", "warning", "info"], case_sensitive=False),
    default="info",
    show_default=True,
    help="Only show findings at or above this severity.",
)
def review(
    asc_file: str,
    rules_path: Optional[str],
    deep: bool,
    api_key: Optional[str],
    model: str,
    output: Optional[str],
    no_local: bool,
    min_severity: str,
) -> None:
    """Analyse an FPWin Pro 7 .asc export file for issues."""

    # 1. Parse ---------------------------------------------------------------
    console.print(f"[dim]Parsing[/dim] {asc_file} …")
    try:
        program = parse_asc(asc_file)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)
    except AscParseError as exc:
        err_console.print(f"[red]Parse error:[/red] {exc}")
        sys.exit(1)

    pou_count  = len(program.pous)
    rung_count = sum(len(p.rungs) for p in program.pous)
    var_count  = len(program.all_variables)
    console.print(
        f"[dim]  → {pou_count} POU(s), {rung_count} rung(s), "
        f"{var_count} variable(s)[/dim]"
    )

    # 2. Local rule engine ---------------------------------------------------
    findings = []

    if not no_local:
        console.print("[dim]Running local rule checks …[/dim]")
        try:
            engine = RuleEngine(rules_path)
        except FileNotFoundError as exc:
            err_console.print(f"[red]Rules error:[/red] {exc}")
            sys.exit(1)
        findings.extend(engine.run(program))
        console.print(f"[dim]  → {len(findings)} local finding(s)[/dim]")
    else:
        engine = None

    # 3. Claude deep analysis ------------------------------------------------
    if deep:
        console.print(f"[dim]Running Claude deep analysis ({model}) …[/dim]")
        claude_rules = (engine.claude_rules if engine else [])
        try:
            client = ClaudeClient(api_key=api_key, model=model)
            ai_findings = client.analyse(program, claude_rules)
            findings.extend(ai_findings)
            console.print(f"[dim]  → {len(ai_findings)} AI finding(s)[/dim]")
        except ClaudeAnalysisError as exc:
            err_console.print(f"[yellow]Claude analysis failed:[/yellow] {exc}")

    # 4. Filter by severity --------------------------------------------------
    _sev_order = {"error": 0, "warning": 1, "info": 2}
    min_order = _sev_order[min_severity.lower()]
    findings = [f for f in findings if _sev_order[f.severity.value] <= min_order]

    # 5. Report --------------------------------------------------------------
    formatter = ReportFormatter(program, findings)

    if output:
        out_path = Path(output)
        suffix = out_path.suffix.lower()
        if suffix == ".html":
            formatter.write_html(output)
            console.print(f"[green]HTML report written to[/green] {output}")
        elif suffix == ".json":
            formatter.write_json(output)
            console.print(f"[green]JSON report written to[/green] {output}")
        else:
            err_console.print(
                "[yellow]Warning:[/yellow] Unknown output extension — writing HTML."
            )
            formatter.write_html(output)
    else:
        formatter.print_terminal(console)

    # Exit code: non-zero if any errors found
    if any(f.severity.value == "error" for f in findings):
        sys.exit(2)


# ---------------------------------------------------------------------------
# llr rules
# ---------------------------------------------------------------------------

@cli.group()
def rules() -> None:
    """Manage and inspect the rules configuration."""


@rules.command("list")
@click.option("--rules", "rules_path", default=None, envvar="LLR_RULES")
def rules_list(rules_path: Optional[str]) -> None:
    """List all configured rules and their status."""
    try:
        engine = RuleEngine(rules_path)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    from rich.table import Table
    table = Table(title="Configured Rules", show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Severity")
    table.add_column("Enabled")
    table.add_column("Implementation")
    table.add_column("Description")

    for rule in engine.all_rules:
        sev_style = {"error": "red", "warning": "yellow", "info": "cyan"}.get(
            rule.severity.value, ""
        )
        enabled_str = "[green]yes[/green]" if rule.enabled else "[dim]no[/dim]"
        impl_str = "[green]✓[/green]" if rule.check_fn else "[red]missing[/red]"
        table.add_row(
            rule.id,
            rule.name,
            f"[{sev_style}]{rule.severity.value}[/{sev_style}]",
            enabled_str,
            impl_str,
            rule.description,
        )

    console.print(table)

    claude_rules = engine.claude_rules
    if claude_rules:
        console.print(f"\n[bold]Claude rules ({len(claude_rules)}):[/bold]")
        for i, cr in enumerate(claude_rules, 1):
            console.print(f"  {i}. {cr}")


@rules.command("validate")
@click.option("--rules", "rules_path", default=None, envvar="LLR_RULES")
def rules_validate(rules_path: Optional[str]) -> None:
    """Validate rules.yaml and report any missing check implementations."""
    try:
        engine = RuleEngine(rules_path)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    missing = [r for r in engine.all_rules if r.check_fn is None and r.enabled]
    if missing:
        err_console.print(f"[yellow]{len(missing)} rule(s) have no implementation:[/yellow]")
        for r in missing:
            err_console.print(f"  [dim]{r.id}[/dim]  {r.name}  — add check_{r.name}() to builtin.py")
        sys.exit(1)
    else:
        console.print("[green]All enabled rules have implementations.[/green]")


# ---------------------------------------------------------------------------
# Entry point (also used by PyInstaller)
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
