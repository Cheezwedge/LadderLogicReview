"""
Core data models produced by the parser and consumed by the rule engine,
Claude client, and report formatter.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Language(str, Enum):
    LD = "LD"
    IL = "IL"
    FBD = "FBD"
    ST = "ST"
    SFC = "SFC"
    UNKNOWN = "UNKNOWN"


class AddressType(str, Enum):
    X = "X"       # external input relay (bit)
    Y = "Y"       # external output relay (bit)
    WX = "WX"     # external input (word)
    WY = "WY"     # external output (word)
    R = "R"       # internal relay (bit)
    WR = "WR"     # internal relay (word)
    DT = "DT"     # data register (16-bit)
    DDT = "DDT"   # double data register (32-bit)
    T = "T"       # timer contact/coil
    C = "C"       # counter contact/coil
    L = "L"       # link relay
    WL = "WL"     # link relay (word)
    FL = "FL"     # file register
    IX = "IX"     # index register
    CONSTANT = "CONSTANT"
    VARIABLE = "VARIABLE"   # named variable (not a raw address)
    UNKNOWN = "UNKNOWN"


@dataclass
class Instruction:
    mnemonic: str           # LD, AND, OR, OUT, TM, CT, F, OT, etc.
    operand: str            # X0, Y1A, R10, DT0, myVar, etc.
    modifier: str = ""      # N (negation), P (positive edge), F (falling edge)
    raw: str = ""           # raw text as it appeared in the file

    @property
    def address_type(self) -> AddressType:
        op = self.operand.upper()
        # Struct member access (e.g. FaultsDUT.MAIN_SEQUENCE_FAULT) → named variable
        if "." in op:
            return AddressType.VARIABLE
        for at in (AddressType.DDT, AddressType.WX, AddressType.WY,
                   AddressType.WR, AddressType.WL, AddressType.FL):
            if op.startswith(at.value):
                return at
        for at in (AddressType.X, AddressType.Y, AddressType.R,
                   AddressType.DT, AddressType.T, AddressType.C,
                   AddressType.L, AddressType.IX):
            if op.startswith(at.value):
                return at
        if op.startswith("K") or op.startswith("H"):
            return AddressType.CONSTANT
        if self.operand:
            return AddressType.VARIABLE
        return AddressType.UNKNOWN

    @property
    def is_output(self) -> bool:
        # OT/OUT/SET/RST = coil outputs
        # F/FB/VAROUT = function calls and data writes (count as outputs for R010)
        # TM/CT variants = timer/counter coils
        return self.mnemonic.upper() in {
            "OT", "OUT", "SET", "RST", "KP", "KEEP",
            "TM", "CT", "TMX", "TMY", "TMR", "STC", "STP",
            "F", "FB", "VAROUT",
        }

    @property
    def is_coil(self) -> bool:
        # Strict coil outputs — used for duplicate-coil detection (R002)
        return self.mnemonic.upper() in {"OT", "OUT", "SET", "RST", "KP", "KEEP"}

    @property
    def is_contact(self) -> bool:
        # LD   = normally open (NO) contact
        # LDN  = normally closed (NC) contact
        # LDP  = rising-edge contact
        # LDF  = falling-edge contact
        return self.mnemonic.upper() in {
            "LD", "LDN", "LDP", "LDF",
            "AN", "AND", "OR", "ANS", "ORS", "PSHS", "POPS", "ANB", "ORB",
        }


@dataclass
class Rung:
    number: int
    comment: str = ""                           # rung title / description
    body_comment: str = ""                      # inline body comment
    instructions: list[Instruction] = field(default_factory=list)
    raw_text: str = ""                          # complete raw text of this rung

    @property
    def has_comment(self) -> bool:
        return bool(self.comment.strip())

    @property
    def output_operands(self) -> list[str]:
        return [i.operand for i in self.instructions if i.is_coil]

    @property
    def contact_operands(self) -> list[str]:
        return [i.operand for i in self.instructions if i.is_contact]


@dataclass
class Variable:
    name: str
    fp_address: str = ""    # FP-style address: X0, DT5, R100, etc.
    iec_address: str = ""   # IEC address: %IX0.0, %MW5, etc.
    var_class: str = ""     # VAR, VAR_GLOBAL, VAR_INPUT, etc.
    var_type: str = ""      # BOOL, INT, DINT, REAL, etc.
    initial: str = ""       # initial value
    comment: str = ""       # description / comment

    @property
    def has_comment(self) -> bool:
        return bool(self.comment.strip())

    @property
    def address_type(self) -> AddressType:
        return Instruction(mnemonic="", operand=self.fp_address).address_type


@dataclass
class POU:
    name: str
    language: Language = Language.UNKNOWN
    rungs: list[Rung] = field(default_factory=list)
    local_variables: list[Variable] = field(default_factory=list)
    raw_text: str = ""

    @property
    def all_instructions(self) -> list[Instruction]:
        return [instr for rung in self.rungs for instr in rung.instructions]


@dataclass
class Program:
    """Top-level container for a parsed .asc project export."""
    source_file: str = ""
    pous: list[POU] = field(default_factory=list)
    global_variables: list[Variable] = field(default_factory=list)
    raw_text: str = ""

    @property
    def all_rungs(self) -> list[tuple[str, Rung]]:
        """Returns (pou_name, rung) pairs across all POUs."""
        return [(pou.name, rung) for pou in self.pous for rung in pou.rungs]

    @property
    def all_variables(self) -> list[Variable]:
        local = [v for pou in self.pous for v in pou.local_variables]
        return self.global_variables + local
