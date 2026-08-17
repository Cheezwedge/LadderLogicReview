# FPWin Pro 7 — Instruction Reference

Condensed reference extracted from the Panasonic Control FPWIN Pro7 InfoHub
documentation index (`infohub.industry.panasonic.eu/documentation/fpwin/en`).

This file is loaded into the Claude deep-analysis system prompt so that
`--deep` findings reference **real** FPWin Pro instruction names rather than
guessed ones. Keep entries accurate — a wrong name here produces wrong findings.

---

## Naming conventions

These prefixes are load-bearing for data-type analysis:

| Pattern | Meaning | Example |
|---|---|---|
| `F<n>_<NAME>` | FP instruction, numbered | `F0_MV` |
| `D` prefix on the mnemonic | **32-bit / double word** operand | `F1_DMV`, `F21_DADD`, `F33_DDIV` |
| `F` prefix on the mnemonic | **REAL / floating point** operand | `F310_FADD`, `F313_FDIV` |
| `B` prefix on the mnemonic | **BCD** operand | `F52_BDIV`, `F42_BADD` |
| `E_` prefix | ENO-enabled IEC variant | `E_MOVE`, `E_GT` |
| `@` prefix | inline/expression form in LD | `@GT-2!`, `@AND-2!` |
| trailing `!` in `.asc` exports | function call marker | `F0_MV!` |

**The `D`/`F`/`B` prefix is the primary signal for width mismatches.** A
`F1_DMV` (32-bit source) writing into an `INT` destination truncates the upper
word. Same for `F21_DADD` results assigned to a 16-bit target.

---

## Data movement

| 16-bit | 32-bit | Purpose |
|---|---|---|
| `F0_MV` | `F1_DMV` | Single move |
| — | `F3_DMVN` | Move inverted |
| — | `F8_DMV2` | Move two double words |
| — | `F191_DMV3` | Move three double words |
| `F10_BKMV` | — | Block move (also `_OFFSET`, `_NUMBER`, `_NUMBER_OFFSET`) |
| `F11_COPY` | — | Fill a block with one value |
| `MOVE` / `E_MOVE` | — | IEC move |
| `FP_COPY` | — | Copy with type conversion |

## Arithmetic

| 16-bit | 32-bit | REAL | BCD | Operation |
|---|---|---|---|---|
| `F20_ADD` | `F21_DADD` | `F310_FADD` | `F40_BADD` family | Add (A := A+B) |
| `F22_ADD2` | `F23_DADD2` | — | — | Add (C := A+B) |
| `F25_SUB` | `F26_DSUB` | `F311_FSUB` | — | Subtract |
| `F27_SUB2` | `F28_DSUB2` | — | — | Subtract to third operand |
| `F30_MUL` | `F31_DMUL` | `F312_FMUL` | — | Multiply |
| `F34_MULW` | `F39_DMULD` | — | — | Multiply, widened result |
| **`F32_DIV`** | **`F33_DDIV`** | **`F313_FDIV`** | **`F52_BDIV`**, `F53_DBDIV` | **Divide** |
| `F35_INC` | `F36_DINC` | — | — | Increment |
| `F37_DEC` | `F38_DDEC` | — | — | Decrement |
| `MOD` / `DIV` | — | — | `FP_DIV_MOD`, `FP_DIV_BCD`, `FP_DIV_MOD_BCD` | IEC operators |
| `DIV_TIME_INT` | `DIV_TIME_DINT` | `DIV_TIME_REAL` | — | Divide a TIME value |

### Divide-by-zero surface

Every instruction below can raise a PLC operation error on a zero divisor:

```
F32_DIV  F33_DDIV  F313_FDIV  F52_BDIV  F53_DBDIV
DIV  MOD  FP_DIV_MOD  FP_DIV_BCD  FP_DIV_MOD_BCD
DIV_TIME_INT  DIV_TIME_DINT  DIV_TIME_REAL
```

## Comparison

| 16-bit | 32-bit | REAL | Purpose |
|---|---|---|---|
| `F60_CMP` | `F61_DCMP` | `F345_FCMP` | Compare |
| `F62_WIN` | `F63_DWIN` | `F346_FWIN` | Band / window compare |
| `F64_BCMP` | — | — | Block compare |

IEC operators: `GT` `GE` `LT` `LE` `EQ` `NE`, plus `E_` ENO variants
(`E_GT`, `E_EQ`, …) and inline `@GT-2!` forms seen in `.asc` exports.

## Edge detection

| Instruction | Behaviour | Instance required? |
|---|---|---|
| `DF` | Rising edge — TRUE for one scan | **No** — compiler allocates edge memory per call site |
| `DFN` | Falling edge | No |
| `DFI` | Rising edge, initial-scan variant | No |

`DF`/`DFN`/`DFI` are the only stateful elements callable without declaring an
instance. User-defined `FUNCTION`s get no such allocation — they need either a
`FUNCTION_BLOCK` instance, `VAR_IN_OUT` state, or a global state array indexed
by an ID.

## Timers and counters

IEC function blocks (**require an instance**): `TON` `TOF` `TP` `CTU` `CTD` `CTUD`
Function forms (no instance): `TON_FUN` `TOF_FUN` `TP_FUN` `CTU_FUN` `CTD_FUN` `CTUD_FUN`
FP forms: `F137_STMR` (auxiliary timer), `F118_UDC` (up/down counter)

## STRING handling

**Memory layout — critical for corruption checks:**

| Word offset | Contents |
|---|---|
| 0 | **Maximum length** of the string |
| 1 | **Current length** of the string |
| 2 … n | Character data |

Writing a word-level value into offset 0 or 1 corrupts the header and causes
downstream string operations to read garbage or overrun. Word-level
instructions (`F0_MV`, `F10_BKMV`, `F11_COPY`, `FP_COPY`) aimed at a STRING's
underlying words are the usual culprit.

Conversions **to** STRING:
`BOOL_TO_STRING` `INT_TO_STRING` `DINT_TO_STRING` `UINT_TO_STRING`
`UDINT_TO_STRING` `WORD_TO_STRING` `DWORD_TO_STRING` `REAL_TO_STRING`
`LREAL_TO_STRING` `TIME_TO_STRING` `DATE_TO_STRING` `DT_TO_STRING`
`TOD_TO_STRING` `IPADDR_TO_STRING` `ETLANADDR_TO_STRING`
— plus `_LEADING_ZEROS` and `_LEFT_ALIGNED` variants on the integer types.

Conversions **from** STRING:
`STRING_TO_INT` `STRING_TO_DINT` `STRING_TO_UINT` `STRING_TO_UDINT`
`STRING_TO_WORD` `STRING_TO_DWORD` `STRING_TO_REAL` `STRING_TO_LREAL`
`STRING_TO_IPADDR` `STRING_TO_ETLANADDR`
— plus `_STEPSAVER` variants.

Other: `FP_FORMAT_STRING`, `LEN`, `LEFT`, `GET_CHAR`, `GET_BYTE`

## Shift, rotate, bit

Shift: `F100_SHR` `F101_SHL` `F102_DSHR` `F103_DSHL` `F105_BSR` `F106_BSL`
`F108_BITR` `F109_BITL` `F110_WSHR` `F111_WSHL` `F112_WBSR` `F113_WBSL`
Rotate: `F120_ROR` `F121_ROL` `F122_RCR` `F123_RCL` `F125_DROR` `F126_DROL`
`F127_DRCR` `F128_DRCL`
Bit ops: `F130_BTS` (set) `F131_BTR` (reset) `F132_BTI` (invert) `F133_BTT` (test)
Bitwise: `F65_WAN` `F66_WOR` `F67_XOR` `F68_XNR` `F69_WUNI`

## Buffers

FIFO: `F115_FIFT` (define) `F116_FIFR` (read) `F117_FIFW` (write)
Shift register: `F119_LRSR`

## System / control

`F140_STC` (set carry) `F141_CLC` (clear carry) `F142_WDT` (watchdog)
`F143_IORF` (I/O refresh)

## Address types

| Prefix | Meaning |
|---|---|
| `X` / `WX` | External input relay (bit / word) |
| `Y` / `WY` | External output relay (bit / word) |
| `R` / `WR` | Internal relay (bit / word) |
| `L` / `WL` | Link relay (bit / word) |
| `DT` | Data register (16-bit) |
| `DDT` | Double data register (32-bit) |
| `FL` | File register |
| `T` / `TM` | Timer |
| `C` / `CT` | Counter |
| `IX` / `IY` | Index registers |
| `DT9000+` | Special system data registers — **treat as read-only** |
| `R900+` | Special system internal relays — **treat as read-only** |

## IEC data types and widths

| Type | Width | Notes |
|---|---|---|
| `BOOL` | 1 bit | |
| `INT`, `UINT`, `WORD` | 16-bit | single word |
| `DINT`, `UDINT`, `DWORD` | 32-bit | **double word** |
| `REAL` | 32-bit | **double word**, floating point |
| `LREAL` | 64-bit | quad word |
| `TIME` | 32-bit | double word |
| `STRING` | n words | 2-word header + character data |

Moving any 32-bit or wider type into a 16-bit destination truncates.

---

## Source and limitations

Extracted from a capture of the Control FPWIN Pro7 InfoHub site. The InfoHub is
a JavaScript single-page app whose topic bodies load via `#/topic/t-NNNNNNN`
fragment routes — fragments never reach the server, so only the navigation index
was retrievable. The **1,148 instruction identifiers** and the topic hierarchy
above come from that index and are accurate; per-instruction operand tables,
timing diagrams, and error-code details are **not** included.

For full per-instruction detail, the FPWin Pro 7 built-in help (`.chm` under the
install directory) is the authoritative source.
