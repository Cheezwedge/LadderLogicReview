"""
Built-in rule check functions.

Each function must have the signature:
    check_<rule_name>(program: Program, rule: RuleDescriptor) -> list[Finding]

The name must match the `name` field in rules.yaml exactly.
New checks added here are automatically discovered by the engine as long as
a matching entry exists in rules.yaml.
"""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

from ..models import Program, AddressType

if TYPE_CHECKING:
    from .engine import RuleDescriptor, Finding, Severity

from .engine import Finding, Severity


# ---------------------------------------------------------------------------
# R001 — every rung must have a comment
# ---------------------------------------------------------------------------

def check_missing_rung_comment(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou_name, rung in program.all_rungs:
        if not rung.has_comment:
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=f"Rung {rung.number} has no comment or description.",
                pou_name=pou_name,
                rung_number=rung.number,
            ))
    return findings


# ---------------------------------------------------------------------------
# R002 — same output coil driven from multiple rungs (duplicate OT/OUT)
# ---------------------------------------------------------------------------

def check_duplicate_output_coil(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou in program.pous:
        coil_rungs: dict[str, list[int]] = defaultdict(list)
        for rung in pou.rungs:
            for operand in rung.output_operands:
                if operand:
                    coil_rungs[operand].append(rung.number)
        for operand, rung_nums in coil_rungs.items():
            if len(rung_nums) > 1:
                findings.append(Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=(
                        f"Output coil '{operand}' is driven by multiple rungs: "
                        f"{rung_nums}. Only the last rung's result will take effect."
                    ),
                    pou_name=pou.name,
                    rung_number=rung_nums[0],
                ))
    return findings


# ---------------------------------------------------------------------------
# R003 — raw physical addresses used instead of named variables
# ---------------------------------------------------------------------------

def check_direct_physical_address(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    _raw_types = {AddressType.X, AddressType.Y, AddressType.R, AddressType.DT,
                  AddressType.DDT, AddressType.WX, AddressType.WY, AddressType.WR}
    findings = []
    named = {v.fp_address.upper() for v in program.all_variables if v.fp_address}

    for pou_name, rung in program.all_rungs:
        for instr in rung.instructions:
            if instr.address_type in _raw_types:
                if instr.operand.upper() not in named:
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=(
                            f"Instruction '{instr.mnemonic} {instr.operand}' uses a raw "
                            f"physical address with no named variable alias."
                        ),
                        pou_name=pou_name,
                        rung_number=rung.number,
                    ))
    return findings


# ---------------------------------------------------------------------------
# R004 — writes to special/system registers (DT9000+, R9000+)
# ---------------------------------------------------------------------------

_SYSTEM_DT_THRESHOLD = 9000
_SYSTEM_R_THRESHOLD = 900

def check_system_register_write(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou_name, rung in program.all_rungs:
        for instr in rung.instructions:
            if not instr.is_output:
                continue
            op = instr.operand.upper()
            if op.startswith("DT"):
                try:
                    num = int(op[2:])
                    if num >= _SYSTEM_DT_THRESHOLD:
                        findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            message=(
                                f"'{instr.mnemonic} {instr.operand}' writes to a system "
                                f"data register (DT{_SYSTEM_DT_THRESHOLD}+). This may "
                                f"overwrite PLC system settings."
                            ),
                            pou_name=pou_name,
                            rung_number=rung.number,
                        ))
                except ValueError:
                    pass
            elif op.startswith("R"):
                try:
                    num = int(op[1:])
                    if num >= _SYSTEM_R_THRESHOLD:
                        findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            message=(
                                f"'{instr.mnemonic} {instr.operand}' writes to a special "
                                f"internal relay (R{_SYSTEM_R_THRESHOLD}+). This may "
                                f"interfere with PLC system behaviour."
                            ),
                            pou_name=pou_name,
                            rung_number=rung.number,
                        ))
                except ValueError:
                    pass
    return findings


# ---------------------------------------------------------------------------
# R005 — variables with no comment in the symbol table
# ---------------------------------------------------------------------------

def check_variable_missing_comment(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for var in program.all_variables:
        if not var.has_comment:
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=f"Variable '{var.name}' ({var.fp_address}) has no comment.",
                variable_name=var.name,
            ))
    return findings


# ---------------------------------------------------------------------------
# R006 — timer/counter instructions with no comment on the rung
# ---------------------------------------------------------------------------

def check_timer_counter_no_comment(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    _tm_ct = {"TM", "CT", "TMX", "TMY", "TMR", "STC", "STP"}
    findings = []
    for pou_name, rung in program.all_rungs:
        has_tc = any(i.mnemonic.upper() in _tm_ct for i in rung.instructions)
        if has_tc and not rung.has_comment:
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=(
                    f"Rung {rung.number} contains a timer/counter instruction "
                    f"but has no comment explaining the setpoint or purpose."
                ),
                pou_name=pou_name,
                rung_number=rung.number,
            ))
    return findings


# ---------------------------------------------------------------------------
# R007 — output coil also appears as a contact in the same rung (self-seal
#         without an explicit latch pattern)
# ---------------------------------------------------------------------------

def check_output_contact_same_rung(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou_name, rung in program.all_rungs:
        outputs = set(rung.output_operands)
        contacts = set(rung.contact_operands)
        overlap = outputs & contacts
        for operand in overlap:
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=(
                    f"'{operand}' appears as both a coil output and a contact "
                    f"in rung {rung.number}. Verify this is an intentional seal-in latch."
                ),
                pou_name=pou_name,
                rung_number=rung.number,
            ))
    return findings


# ---------------------------------------------------------------------------
# R008 — empty rungs (no instructions)
# ---------------------------------------------------------------------------

def check_empty_rung(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou_name, rung in program.all_rungs:
        if not rung.instructions:
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=f"Rung {rung.number} is empty (no instructions).",
                pou_name=pou_name,
                rung_number=rung.number,
            ))
    return findings


# ---------------------------------------------------------------------------
# R009 — Y (output) address used as a contact without a declared variable
#         alias (suggests undocumented feedback / status read-back)
# ---------------------------------------------------------------------------

def check_output_used_as_contact(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    named = {v.fp_address.upper() for v in program.all_variables if v.fp_address}
    for pou_name, rung in program.all_rungs:
        for instr in rung.instructions:
            if instr.is_contact and instr.address_type == AddressType.Y:
                if instr.operand.upper() not in named:
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=(
                            f"Output address '{instr.operand}' is read as a contact "
                            f"in rung {rung.number} but has no named variable. "
                            f"Output feedback should be explicit and documented."
                        ),
                        pou_name=pou_name,
                        rung_number=rung.number,
                    ))
    return findings


# ---------------------------------------------------------------------------
# R010 — no output instructions in a rung (contacts only, nothing driven)
# ---------------------------------------------------------------------------

def check_rung_no_output(program: Program, rule: "RuleDescriptor") -> list[Finding]:
    findings = []
    for pou_name, rung in program.all_rungs:
        if rung.instructions and not any(i.is_output for i in rung.instructions):
            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                message=(
                    f"Rung {rung.number} has contact logic but no output instruction. "
                    f"The rung evaluates a condition but drives nothing."
                ),
                pou_name=pou_name,
                rung_number=rung.number,
            ))
    return findings
