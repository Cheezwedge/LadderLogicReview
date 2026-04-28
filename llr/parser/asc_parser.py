"""
Parser for FPWin Pro 7 .asc export files.

STATUS: STUB — awaiting a real .asc sample to implement the grammar.

The .asc format is produced in FPWin Pro 7 via:
  Project → Export → All objects → save as *.asc

Once a sample file is provided, this module will be replaced with a
concrete implementation. The public interface (parse_asc) and the
returned data model (Program) will not change.

------------------------------------------------------------------------
WHAT IS KNOWN SO FAR (update as the real format is confirmed):
  - Encoding: Unicode UTF-16 (default) or Multibyte (MBCS)
  - Contains: POU definitions, variable declarations, program body
  - Languages: LD, IL, FBD, ST, SFC
  - Sections suspected: [POU], [VARIABLE], [TASK], [CONFIGURATION]
  - IL mnemonics: LD, AND, OR, NOT, OT/OUT, TM, CT, SET, RST, etc.
  - Address prefixes: X, Y, R, DT, DDT, WX, WY, WR, T, C, L, FL, IX
------------------------------------------------------------------------
"""
from __future__ import annotations
import os
from ..models import Program, POU, Rung, Instruction, Variable, Language


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_asc(path: str) -> Program:
    """
    Parse a FPWin Pro 7 .asc export file and return a Program.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    AscParseError
        If the file cannot be parsed (format not yet understood).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    raw = _read_file(path)
    return _parse(raw, source_file=path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    """Read the file, trying UTF-16 first then UTF-8 / MBCS fallbacks."""
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "mbcs", "latin-1"):
        try:
            with open(path, encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise AscParseError(f"Could not decode {path} with any known encoding")


def _parse(raw: str, source_file: str = "") -> Program:
    """
    *** STUB ***

    Replace this function body once the real .asc format is known.
    Currently returns a Program with the raw text attached so that
    the Claude deep-analysis path can still work (it reads raw_text
    directly when the parser returns no structured data).
    """
    # Detect if this is likely an .asc file at all
    _sanity_check(raw)

    # TODO: implement real grammar once a sample is available.
    # Suggested approach:
    #   1. Split into top-level sections (e.g. [GLOBAL_VARIABLE], [POU:name], …)
    #   2. For each POU section, detect language tag and delegate to
    #      _parse_il_pou() or _parse_ld_pou() etc.
    #   3. For IL bodies, tokenise line-by-line:
    #         label? <mnemonic> [modifier] [operand] [; comment]
    #   4. For LD bodies the text representation will be rung-delimited —
    #         the exact delimiter tokens need confirmation from a real file.

    return Program(
        source_file=source_file,
        raw_text=raw,
        pous=[_stub_pou(raw)],
    )


def _sanity_check(raw: str) -> None:
    """Raise AscParseError if the text looks nothing like an FPWin export."""
    # These heuristics will be tightened once the real format is confirmed.
    if len(raw.strip()) == 0:
        raise AscParseError("File is empty")


def _stub_pou(raw: str) -> POU:
    """
    Placeholder: wraps the entire raw text in a single POU with no structured
    rungs so that downstream consumers (rule engine, Claude client) still
    receive something meaningful before the real parser is implemented.
    """
    return POU(
        name="__UNPARSED__",
        language=Language.UNKNOWN,
        rungs=[],
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# Future helpers (signatures defined now so callers can be written)
# ---------------------------------------------------------------------------

def _parse_il_pou(name: str, body: str) -> POU:
    """Parse an IL-language POU body into Rungs of Instructions."""
    raise NotImplementedError("IL parser not yet implemented — awaiting .asc sample")


def _parse_ld_pou(name: str, body: str) -> POU:
    """Parse a Ladder Diagram POU body (text representation)."""
    raise NotImplementedError("LD text parser not yet implemented — awaiting .asc sample")


def _parse_variable_section(section: str) -> list[Variable]:
    """Parse a variable/symbol declaration block."""
    raise NotImplementedError("Variable parser not yet implemented — awaiting .asc sample")


def _parse_instruction_line(line: str) -> Instruction | None:
    """
    Parse a single IL instruction line.

    Expected form (IEC 61131-3 IL):
        [label:] <mnemonic>[modifier] [operand] [; comment]

    Examples (to be confirmed against real .asc output):
        LD  X0
        ANDN R10
        OT  Y0
        TM  T0  K100
        F0  (MV) DT0  K5
    """
    raise NotImplementedError("Instruction line parser not yet implemented")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AscParseError(Exception):
    """Raised when the .asc file cannot be parsed."""
