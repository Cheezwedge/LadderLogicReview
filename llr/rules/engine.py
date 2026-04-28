"""
Rule engine: loads rules.yaml and runs enabled checks against a Program.
"""
from __future__ import annotations
import importlib
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import yaml

from ..models import Program


# ---------------------------------------------------------------------------
# Finding — one issue found by a rule
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: Severity
    message: str
    pou_name: str = ""
    rung_number: Optional[int] = None
    variable_name: str = ""
    source: str = "local"       # "local" | "claude"

    def location(self) -> str:
        parts = []
        if self.pou_name and self.pou_name != "__UNPARSED__":
            parts.append(self.pou_name)
        if self.rung_number is not None:
            parts.append(f"rung {self.rung_number}")
        if self.variable_name:
            parts.append(self.variable_name)
        return " / ".join(parts) if parts else "—"


# ---------------------------------------------------------------------------
# Rule descriptor (loaded from YAML)
# ---------------------------------------------------------------------------

@dataclass
class RuleDescriptor:
    id: str
    name: str
    severity: Severity
    enabled: bool
    description: str
    check_fn: Optional[Callable] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------

_BUILTIN_MODULE = "llr.rules.builtin"

_DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "rules.yaml"


class RuleEngine:
    def __init__(self, rules_path: Optional[str] = None) -> None:
        path = Path(rules_path) if rules_path else _DEFAULT_RULES_PATH
        self._config = self._load_config(path)
        self._rules: list[RuleDescriptor] = self._build_rules(self._config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, program: Program) -> list[Finding]:
        """Run all enabled local rules against *program*."""
        findings: list[Finding] = []
        for rule in self._rules:
            if not rule.enabled or rule.check_fn is None:
                continue
            try:
                results = rule.check_fn(program, rule)
                findings.extend(results)
            except Exception as exc:
                findings.append(Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=Severity.WARNING,
                    message=f"Rule check raised an exception: {exc}",
                    source="local",
                ))
        return findings

    @property
    def claude_rules(self) -> list[str]:
        """Return the list of plain-English rules to send to Claude."""
        return self._config.get("claude_rules", [])

    @property
    def all_rules(self) -> list[RuleDescriptor]:
        return list(self._rules)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(
                f"Rules file not found: {path}\n"
                "Run with --rules to specify a custom path, or ensure rules.yaml "
                "is in the same directory as the tool."
            )
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _build_rules(self, config: dict) -> list[RuleDescriptor]:
        try:
            builtin = importlib.import_module(_BUILTIN_MODULE)
        except ImportError as exc:
            raise RuntimeError(f"Could not import built-in rules module: {exc}") from exc

        rules: list[RuleDescriptor] = []
        for entry in config.get("rules", []):
            severity_str = entry.get("severity", "warning").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.WARNING

            fn_name = f"check_{entry['name']}"
            check_fn = getattr(builtin, fn_name, None)

            rules.append(RuleDescriptor(
                id=entry["id"],
                name=entry["name"],
                severity=severity,
                enabled=entry.get("enabled", True),
                description=entry.get("description", ""),
                check_fn=check_fn,
            ))
        return rules
