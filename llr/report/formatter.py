"""
Report formatters: terminal (rich), JSON, and HTML.
"""
from __future__ import annotations
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from ..models import Program
from ..rules.engine import Finding, Severity

_SEVERITY_STYLE = {
    Severity.ERROR:   "bold red",
    Severity.WARNING: "yellow",
    Severity.INFO:    "cyan",
}
_SEVERITY_ICON = {
    Severity.ERROR:   "✖",
    Severity.WARNING: "⚠",
    Severity.INFO:    "ℹ",
}


class ReportFormatter:
    def __init__(self, program: Program, findings: list[Finding]) -> None:
        self._program = program
        self._findings = findings

    # ------------------------------------------------------------------
    # Terminal
    # ------------------------------------------------------------------

    def print_terminal(self, console: Optional[Console] = None) -> None:
        con = console or Console()
        source = Path(self._program.source_file).name if self._program.source_file else "unknown"
        con.rule(f"[bold]LadderLogicReview — {source}[/bold]")

        if not self._findings:
            con.print("\n[bold green]No issues found.[/bold green]\n")
            return

        errors   = [f for f in self._findings if f.severity == Severity.ERROR]
        warnings = [f for f in self._findings if f.severity == Severity.WARNING]
        infos    = [f for f in self._findings if f.severity == Severity.INFO]

        # Summary line
        parts = []
        if errors:
            parts.append(f"[bold red]{len(errors)} error{'s' if len(errors) != 1 else ''}[/bold red]")
        if warnings:
            parts.append(f"[yellow]{len(warnings)} warning{'s' if len(warnings) != 1 else ''}[/yellow]")
        if infos:
            parts.append(f"[cyan]{len(infos)} info[/cyan]")
        con.print()
        con.print("  " + ",  ".join(parts))
        con.print()

        # Findings table
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold dim")
        table.add_column("", width=2, no_wrap=True)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Location", no_wrap=True)
        table.add_column("Source", width=6, no_wrap=True)
        table.add_column("Message")

        for finding in sorted(self._findings, key=_sort_key):
            style = _SEVERITY_STYLE[finding.severity]
            icon  = _SEVERITY_ICON[finding.severity]
            src_badge = "[dim]local[/dim]" if finding.source == "local" else "[magenta]AI[/magenta]"
            table.add_row(
                Text(icon, style=style),
                Text(finding.rule_id, style="dim"),
                finding.location() or "—",
                src_badge,
                finding.message,
            )

        con.print(table)
        con.print()

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        return json.dumps({
            "source_file": self._program.source_file,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total": len(self._findings),
                "errors":   sum(1 for f in self._findings if f.severity == Severity.ERROR),
                "warnings": sum(1 for f in self._findings if f.severity == Severity.WARNING),
                "infos":    sum(1 for f in self._findings if f.severity == Severity.INFO),
            },
            "findings": [
                {
                    "rule_id":      f.rule_id,
                    "rule_name":    f.rule_name,
                    "severity":     f.severity.value,
                    "source":       f.source,
                    "pou_name":     f.pou_name,
                    "rung_number":  f.rung_number,
                    "variable_name": f.variable_name,
                    "message":      f.message,
                }
                for f in sorted(self._findings, key=_sort_key)
            ],
        }, indent=indent)

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def to_html(self) -> str:
        source = Path(self._program.source_file).name if self._program.source_file else "unknown"
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        errors   = sum(1 for f in self._findings if f.severity == Severity.ERROR)
        warnings = sum(1 for f in self._findings if f.severity == Severity.WARNING)
        infos    = sum(1 for f in self._findings if f.severity == Severity.INFO)

        rows = ""
        for f in sorted(self._findings, key=_sort_key):
            sev_class = f.severity.value
            src = "AI" if f.source == "claude" else "local"
            rows += (
                f'<tr class="{sev_class}">'
                f'<td class="sev-icon">{_SEVERITY_ICON[f.severity]}</td>'
                f'<td class="rule-id">{_esc(f.rule_id)}</td>'
                f'<td>{_esc(f.location())}</td>'
                f'<td class="src">{src}</td>'
                f'<td>{_esc(f.message)}</td>'
                f'</tr>\n'
            )

        return _HTML_TEMPLATE.format(
            source=_esc(source),
            timestamp=ts,
            errors=errors,
            warnings=warnings,
            infos=infos,
            rows=rows,
        )

    def write_html(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_html())

    def write_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sort_key(f: Finding) -> tuple:
    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return (order[f.severity], f.pou_name or "", f.rung_number or 0)


def _esc(s: str) -> str:
    return (s or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLR Report — {source}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f8f9fa; color: #212529; }}
  h1   {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
  .meta {{ color: #6c757d; font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .summary {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; }}
  .badge {{ padding: 0.4rem 0.9rem; border-radius: 6px; font-weight: 600; font-size: 0.9rem; }}
  .badge.error   {{ background: #f8d7da; color: #842029; }}
  .badge.warning {{ background: #fff3cd; color: #664d03; }}
  .badge.info    {{ background: #d1ecf1; color: #0c5460; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
  th    {{ background: #343a40; color: #fff; padding: 0.6rem 0.8rem; text-align: left; font-size: 0.85rem; }}
  td    {{ padding: 0.55rem 0.8rem; font-size: 0.88rem; border-bottom: 1px solid #e9ecef; vertical-align: top; }}
  tr.error   td {{ background: #fff5f5; }}
  tr.warning td {{ background: #fffdf0; }}
  tr.info    td {{ background: #f0faff; }}
  .sev-icon  {{ text-align: center; width: 2rem; }}
  .rule-id   {{ white-space: nowrap; color: #6c757d; font-size: 0.8rem; }}
  .src       {{ text-align: center; font-size: 0.75rem; font-weight: 600;
                color: #6610f2; width: 3.5rem; }}
  tr:last-child td {{ border-bottom: none; }}
</style>
</head>
<body>
<h1>LadderLogicReview Report</h1>
<p class="meta">File: <strong>{source}</strong> &nbsp;&bull;&nbsp; Generated: {timestamp}</p>
<div class="summary">
  <span class="badge error">✖ {errors} error(s)</span>
  <span class="badge warning">⚠ {warnings} warning(s)</span>
  <span class="badge info">ℹ {infos} info</span>
</div>
<table>
<thead>
  <tr><th></th><th>Rule</th><th>Location</th><th>Source</th><th>Message</th></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""
