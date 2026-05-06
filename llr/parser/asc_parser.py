"""
Parser for FPWin Pro 7 .asc export files.

Confirmed file structure (from real sample):

  (*FPWIN Pro:XXXXXXXXXXXXXXXX
    VERSION:7.7.x.x*)
  (*$MODIFICATIONDATE_UTC:... *)
  PROGRAM <PouName>
    (**)
    VAR_EXTERNAL RETAIN
      VarName: TYPE [:= initial];
      ...
    END_VAR
    VAR_EXTERNAL
      ...
    END_VAR
    VAR CONSTANT
      ...
    END_VAR
    VAR
      @'': @'';          ← internal FPWin placeholder, skip
    END_VAR
    'LD'                  ← language tag: LD | IL | FBD | ST | SFC
    BODY
      WORKSPACE
        NETWORK_LIST_TYPE := NWTYPELD ;
      END_WORKSPACE
      NET_WORK
        NETWORK_TYPE  := NWTYPELD ;
        NETWORK_LABEL :=  ;
        NETWORK_TITLE :=  ;        ← almost always empty; title lives in B_COMMENT
        NETWORK_HEIGHT := <n> ;
        NETWORK_BODY
  B(B_CONTACT,,VarName,x1,y1,x2,y2,modifier);
  B(B_COIL,,VarName,x1,y1,x2,y2,modifier);
  B(B_COMMENT,,text,x1,y1,x2,y2,);
  B(B_VARIN,,value_or_var,x1,y1,x2,y2,);
  B(B_VAROUT,,VarName,x1,y1,x2,y2,);
  B(B_F,FUNCNAME!,,x1,y1,x2,y2,,params);
  B(B_FB,FBTYPE!,instance,x1,y1,x2,y2,,params);
  L(x1,y1,x2,y2);        ← wiring (ignored)
        END_NETWORK_BODY
      END_NET_WORK
      ...
    END_BODY
  END_PROGRAM

B() field counts
  B_CONTACT, B_COIL, B_COMMENT, B_VARIN, B_VAROUT → 8 fields
  B_F, B_FB                                        → 9 fields (extra: param string)

Contact modifiers
  (empty) → NO (normally open)
  N       → NC (normally closed)
  R       → rising-edge (positive transition)
  F       → falling-edge (negative transition)

Coil modifiers
  (empty) → normal output coil  → mnemonic OT
  S       → SET (latch)         → mnemonic SET
  R       → RESET (unlatch)     → mnemonic RST
  E       → ENO-driven coil     → mnemonic OT  (still a normal output)

Comment escapes
  ~  → , (comma was replaced by tilde to avoid splitting B() args)
  ø^ → newline

B_COMMENT placement convention
  y1 <= 3 → rung title / header  (used as Rung.comment)
  y1 >  3 → inline annotation    (used as Rung.body_comment)

Special / skip cases
  B(B_COMMENT,,~d,0,0,0,0,) → internal FPWin marker; ignored
  @'': @'';                  → internal variable placeholder; skipped
"""
from __future__ import annotations
import os
import re
from typing import Iterator, Optional

from ..models import Program, POU, Rung, Instruction, Variable, Language


# =========================================================================
# Public API
# =========================================================================

def parse_asc(path: str) -> Program:
    """
    Parse a FPWin Pro 7 .asc export file and return a Program.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    AscParseError
        If the file cannot be parsed.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    raw = _read_file(path)
    return _parse(raw, source_file=path)


# =========================================================================
# Encoding
# =========================================================================

def _read_file(path: str) -> str:
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "mbcs", "latin-1"):
        try:
            with open(path, encoding=encoding) as fh:
                return fh.read()
        except (UnicodeError, LookupError):
            continue
    raise AscParseError(f"Could not decode {path} with any known encoding")


# =========================================================================
# Top-level
# =========================================================================

# PROGRAM … END_PROGRAM  (multiline, non-greedy, anchored to line starts)
_RE_PROGRAM = re.compile(
    r"^PROGRAM\s+(\w+)\s*$(.*?)^END_PROGRAM\s*$",
    re.MULTILINE | re.DOTALL,
)


def _parse(raw: str, source_file: str = "") -> Program:
    _sanity_check(raw)

    pous: list[POU] = []
    for m in _RE_PROGRAM.finditer(raw):
        pous.append(_parse_pou(m.group(1), m.group(2)))

    if not pous:
        # Graceful fallback: no PROGRAM keyword — pass raw text for Claude analysis
        pous = [POU(name="__UNPARSED__", language=Language.UNKNOWN, raw_text=raw)]

    return Program(source_file=source_file, pous=pous, raw_text=raw)


def _sanity_check(raw: str) -> None:
    if not raw.strip():
        raise AscParseError("File is empty")
    if "PROGRAM" not in raw and "FPWIN Pro" not in raw:
        raise AscParseError(
            "File does not appear to be an FPWin Pro .asc export "
            "(neither 'PROGRAM' nor 'FPWIN Pro' found)"
        )


# =========================================================================
# POU
# =========================================================================

_RE_LANGUAGE = re.compile(r"'(LD|IL|FBD|ST|SFC)'")
_RE_BODY     = re.compile(r"\bBODY\b(.*?)\bEND_BODY\b", re.DOTALL)


def _parse_pou(name: str, pou_text: str) -> POU:
    variables = _parse_all_var_sections(pou_text)

    lang_m   = _RE_LANGUAGE.search(pou_text)
    language = Language(lang_m.group(1)) if lang_m else Language.UNKNOWN

    rungs: list[Rung] = []
    body_m = _RE_BODY.search(pou_text)
    if body_m:
        rungs = _parse_body(body_m.group(1))

    return POU(
        name=name,
        language=language,
        rungs=rungs,
        local_variables=variables,
        raw_text=pou_text,
    )


# =========================================================================
# Variable sections
# =========================================================================

# Matches  VAR[_class] [qualifier]\n…\nEND_VAR
# Handles indented declarations (tabs/spaces before keywords)
_RE_VAR_SECTION = re.compile(
    r"(?:^|\n)\s*(VAR(?:_EXTERNAL|_INPUT|_OUTPUT|_INOUT|_GLOBAL)?"
    r"(?:\s+(?:RETAIN|CONSTANT|PERSISTENT))*)\s*\n"
    r"(.*?)"
    r"\n\s*END_VAR",
    re.DOTALL,
)

# Single variable declaration:  name : type [:= initial] ;
# type can include brackets: STRING[50]
_RE_VAR_DECL = re.compile(
    r"(\w+)\s*:\s*"          # name :
    r"(\w+(?:\[\d+\])?)"     # type  (word, optionally [n])
    r"(?:\s*:=\s*(.*?))?"    # optional  := initial_value
    r"\s*;",
    re.DOTALL,
)


def _parse_all_var_sections(pou_text: str) -> list[Variable]:
    variables: list[Variable] = []
    for m in _RE_VAR_SECTION.finditer(pou_text):
        var_class   = " ".join(m.group(1).split())  # normalise whitespace
        section_src = m.group(2)
        variables.extend(_parse_var_section(var_class, section_src))
    return variables


def _parse_var_section(var_class: str, src: str) -> list[Variable]:
    variables: list[Variable] = []
    for m in _RE_VAR_DECL.finditer(src):
        name     = m.group(1).strip()
        var_type = m.group(2).strip()
        initial  = (m.group(3) or "").strip()

        # Skip internal FPWin placeholders like @'': @'';
        if not name or name.startswith("@"):
            continue

        variables.append(Variable(
            name=name,
            var_class=var_class,
            var_type=var_type,
            initial=initial,
        ))
    return variables


# =========================================================================
# Body → networks (rungs)
# =========================================================================

_RE_NETWORK    = re.compile(r"\bNET_WORK\b(.*?)\bEND_NET_WORK\b", re.DOTALL)
_RE_NET_TITLE  = re.compile(r"NETWORK_TITLE\s*:=\s*(.*?)\s*;")
_RE_NET_BODY   = re.compile(r"\bNETWORK_BODY\b(.*?)\bEND_NETWORK_BODY\b", re.DOTALL)


def _parse_body(body_text: str) -> list[Rung]:
    rungs: list[Rung] = []
    for i, m in enumerate(_RE_NETWORK.finditer(body_text), start=1):
        rungs.append(_parse_network(i, m.group(1)))
    return rungs


def _parse_network(number: int, network_text: str) -> Rung:
    # NETWORK_TITLE (usually blank in practice)
    title = ""
    tm = _RE_NET_TITLE.search(network_text)
    if tm:
        t = tm.group(1).strip()
        if t:
            title = t

    instructions: list[Instruction] = []
    top_comments:  list[str] = []
    body_comments: list[str] = []

    bm = _RE_NET_BODY.search(network_text)
    if bm:
        instructions, top_comments, body_comments = _parse_network_body(bm.group(1))

    comment      = title or (top_comments[0] if top_comments else "")
    body_comment = "; ".join(top_comments[1:] + body_comments)

    return Rung(
        number=number,
        comment=comment,
        body_comment=body_comment,
        instructions=instructions,
        raw_text=network_text,
    )


# =========================================================================
# Network body — B() block parsing
# =========================================================================

def _parse_network_body(
    body: str,
) -> tuple[list[Instruction], list[str], list[str]]:
    instructions: list[Instruction] = []
    top_comments:  list[str] = []   # y1 <= 3  → rung title
    body_comments: list[str] = []   # y1 >  3  → inline annotation

    for fields in _iter_b_blocks(body):
        if not fields:
            continue
        block_type = fields[0].strip()

        if block_type == "B_COMMENT":
            _handle_comment(fields, top_comments, body_comments)
        else:
            instr = _fields_to_instruction(block_type, fields)
            if instr is not None:
                instructions.append(instr)

    return instructions, top_comments, body_comments


# -------------------------------------------------------------------------
# B() block iterator — handles quoted strings inside B(…)
# -------------------------------------------------------------------------

def _iter_b_blocks(body: str) -> Iterator[list[str]]:
    """
    Yield the parsed field list for every B(…) block in *body*.

    Scans character-by-character so that single-quoted strings (which may
    contain commas or closing parentheses) are handled correctly.
    """
    i = 0
    n = len(body)
    while i < n - 1:
        if body[i] == "B" and body[i + 1] == "(":
            start    = i + 2
            j        = start
            in_quote = False
            while j < n:
                c = body[j]
                if c == "'":
                    in_quote = not in_quote
                elif c == ")" and not in_quote:
                    yield _split_fields(body[start:j])
                    i = j + 1
                    break
                j += 1
            else:
                break   # unterminated B( — stop scanning
        else:
            i += 1


def _split_fields(content: str) -> list[str]:
    """Split B(…) inner content on commas, respecting single-quoted strings."""
    fields:   list[str] = []
    current:  list[str] = []
    in_quote = False

    for ch in content:
        if ch == "'":
            in_quote = not in_quote
            current.append(ch)
        elif ch == "," and not in_quote:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)

    fields.append("".join(current))
    return fields


# -------------------------------------------------------------------------
# Comment handling
# -------------------------------------------------------------------------

def _handle_comment(
    fields:        list[str],
    top_comments:  list[str],
    body_comments: list[str],
) -> None:
    # fields: [B_COMMENT, subtype, text, x1, y1, x2, y2, modifier]
    if len(fields) < 5:
        return

    text = fields[2].strip().strip("'")
    text = _decode_comment(text)

    # Skip internal FPWin markers (zero-position block or ~d sentinel)
    if not text or text in (",d", "~d"):
        return
    try:
        x1 = int(fields[3].strip())
        y1 = int(fields[4].strip())
    except (ValueError, IndexError):
        y1 = 99
        x1 = 0

    # Zero-sized block at origin = internal placeholder
    if x1 == 0 and y1 == 0:
        return

    if y1 <= 3:
        top_comments.append(text)
    else:
        body_comments.append(text)


def _decode_comment(text: str) -> str:
    """Decode FPWin Pro comment escape sequences."""
    return text.replace("ø^", "\n").replace("~", ",")


# -------------------------------------------------------------------------
# Instruction mapping
# -------------------------------------------------------------------------

def _fields_to_instruction(
    block_type: str,
    fields: list[str],
) -> Optional[Instruction]:
    """Map a parsed B() field list to an Instruction, or None to skip."""

    if block_type in ("B_CONTACT", "B_COIL"):
        if len(fields) < 8:
            return None
        operand  = fields[2].strip()
        modifier = fields[7].strip() if len(fields) > 7 else ""
        mnemonic, norm_modifier = _contact_coil_mnemonic(block_type, modifier)
        return Instruction(
            mnemonic=mnemonic,
            operand=operand,
            modifier=norm_modifier,
            raw=f"{block_type} {operand} [{modifier}]",
        )

    if block_type == "B_VAROUT":
        if len(fields) < 3:
            return None
        operand = fields[2].strip()
        return Instruction(
            mnemonic="VAROUT",
            operand=operand,
            raw=f"VAROUT {operand}",
        )

    if block_type == "B_F":
        # fields: B_F, funcname, instance, x1, y1, x2, y2, modifier, params
        func_name = fields[1].strip() if len(fields) > 1 else ""
        return Instruction(
            mnemonic="F",
            operand=func_name,
            raw=f"F {func_name}",
        )

    if block_type == "B_FB":
        # fields: B_FB, fbtype, instance, x1, y1, x2, y2, modifier, params
        fb_type  = fields[1].strip() if len(fields) > 1 else ""
        instance = fields[2].strip() if len(fields) > 2 else ""
        return Instruction(
            mnemonic="FB",
            operand=fb_type,
            modifier=instance,
            raw=f"FB {fb_type} ({instance})",
        )

    # B_VARIN — data-flow input pin; not a logic contact or output
    return None


def _contact_coil_mnemonic(block_type: str, modifier: str) -> tuple[str, str]:
    """Return (mnemonic, normalised_modifier) for a contact or coil block."""
    mod = modifier.upper()
    if block_type == "B_CONTACT":
        _map = {"N": ("LDN", "N"), "R": ("LDP", "R"), "F": ("LDF", "F")}
        return _map.get(mod, ("LD", ""))
    else:  # B_COIL
        _map = {"S": ("SET", "S"), "R": ("RST", "R")}
        # E = ENO-driven coil — treat as a normal output coil (OT)
        return _map.get(mod, ("OT", mod if mod not in ("", "E") else ""))


# =========================================================================
# Exceptions
# =========================================================================

class AscParseError(Exception):
    """Raised when the .asc file cannot be parsed."""
