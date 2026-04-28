"""
Claude API client for deep semantic analysis of ladder logic programs.

Uses prompt caching so the system prompt (FPWin Pro context + rules) is
cached across multiple calls within a session, keeping costs low.

Model: claude-sonnet-4-6 (good balance of speed and reasoning quality).
Use --model claude-opus-4-7 for the most thorough analysis.
"""
from __future__ import annotations
import json
import os
import textwrap
from typing import Optional

import anthropic

from ..models import Program
from ..rules.engine import Finding, Severity

_DEFAULT_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert PLC (Programmable Logic Controller) engineer specialising in
    Panasonic FP-series PLCs programmed with FPWin Pro 7 (IEC 61131-3 compliant).

    You will be given the text of a ladder logic program exported from FPWin Pro 7
    (in .asc or IL/ST text format), plus a list of rules to check. Your job is to
    review the program for:

    - Logical errors (conditions that can never be true, outputs that can never fire,
      interlocks that can be bypassed, etc.)
    - Safety issues (dangerous outputs without adequate interlocks, missing E-stop logic)
    - Bad practices (magic numbers instead of named constants, overly complex rungs,
      poor structure)
    - Missing documentation (rungs or variables that need comments to be maintainable)
    - Any issues from the specific rule list provided

    ## Panasonic FP address types
    - X / WX  : external input relays (bit / word)
    - Y / WY  : external output relays (bit / word)
    - R / WR  : internal relays (bit / word)
    - DT      : data registers (16-bit word)
    - DDT     : double data registers (32-bit)
    - T / TM  : timers
    - C / CT  : counters
    - DT9000+ : special system data registers (dangerous to write)
    - R900+   : special system internal relays (read-only in most cases)

    ## Output format
    Respond with a JSON array of findings. Each finding must have:
    {
      "severity":    "error" | "warning" | "info",
      "rule_id":     "CLAUDE-NNN" (use sequential numbers),
      "rule_name":   short_snake_case_name,
      "pou_name":    string or "",
      "rung_number": integer or null,
      "message":     "Clear explanation of the issue and why it matters"
    }

    Return ONLY the JSON array — no markdown, no prose before or after.
    If no issues are found, return an empty array: []
""")


class ClaudeClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ClaudeAnalysisError(
                "No Anthropic API key found. Set the ANTHROPIC_API_KEY environment "
                "variable or pass --api-key on the command line."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._model = model

    def analyse(
        self,
        program: Program,
        claude_rules: list[str],
    ) -> list[Finding]:
        """
        Send the program to Claude and return a list of Findings.

        Uses prompt caching on the system prompt + rules block so repeated
        calls in one session reuse the cached tokens.
        """
        program_text = self._program_text(program)
        rules_block = self._rules_block(claude_rules)
        user_message = f"{rules_block}\n\n## Program\n\n```\n{program_text}\n```"

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _program_text(program: Program) -> str:
        """Best available text representation of the program."""
        if program.raw_text:
            return program.raw_text
        lines = []
        for pou in program.pous:
            lines.append(f"POU: {pou.name}  [{pou.language.value}]")
            for rung in pou.rungs:
                lines.append(f"  Rung {rung.number}: {rung.comment}")
                for instr in rung.instructions:
                    lines.append(f"    {instr.mnemonic:<8} {instr.operand}")
        return "\n".join(lines)

    @staticmethod
    def _rules_block(claude_rules: list[str]) -> str:
        if not claude_rules:
            return "## Additional rules\n(none specified)"
        items = "\n".join(f"- {r}" for r in claude_rules)
        return f"## Additional rules to check\n{items}"

    @staticmethod
    def _parse_response(raw: str) -> list[Finding]:
        # Strip any accidental markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeAnalysisError(
                f"Claude returned non-JSON response: {exc}\n\nRaw response:\n{raw}"
            ) from exc

        findings = []
        for item in data:
            sev_str = item.get("severity", "info").lower()
            try:
                sev = Severity(sev_str)
            except ValueError:
                sev = Severity.INFO

            findings.append(Finding(
                rule_id=item.get("rule_id", "CLAUDE-?"),
                rule_name=item.get("rule_name", "claude_finding"),
                severity=sev,
                message=item.get("message", ""),
                pou_name=item.get("pou_name", ""),
                rung_number=item.get("rung_number"),
                source="claude",
            ))
        return findings


class ClaudeAnalysisError(Exception):
    """Raised when the Claude API call fails or returns unusable output."""
