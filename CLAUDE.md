# CLAUDE.md

Working notes for future sessions on this repo. Read this before changing the
parser, the rule engine, or the packaging.

## What this is

A static analyser for Panasonic FPWin Pro 7 ladder logic. It reads `.asc` text
exports, runs offline rule checks, and optionally sends the program to the
Claude API for semantic analysis that mechanical rules can't do.

Entry points: `llr review <file>` (CLI), `llr web` (browser UI), `llr rules
list|validate`.

---

## Architecture decisions

### Hybrid local + API, not one or the other

Offline rules run with no network and no API key, so the tool is usable on an
air-gapped plant-floor machine. Claude analysis is opt-in via `--deep`. This was
chosen over a pure-offline tool (can't catch logical/semantic errors) and a
pure-API tool (unusable without internet, sends proprietary logic off-site by
default).

**Consequence:** every new check has to be placed in one of two tiers. Put it in
`rules.yaml` → `rules:` with a `check_*()` implementation if it's mechanically
decidable from the parsed model. Put it in `claude_rules:` if it needs to
understand intent, cross-rung relationships, or data types the parser doesn't
extract. Don't write a local rule that guesses at semantics — it will produce
false positives and erode trust in the whole report.

### `.asc` text exports, not `.pro` / `.pce`

FPWin Pro's native project files are an undocumented binary format. The `.asc`
export (Project → Export → All objects) is a documented-enough text format that
round-trips back into FPWin Pro. Users export, analyse, and can re-import.

### YAML-driven rules

`rules.yaml` is the user-facing config. Toggling `enabled`, changing `severity`,
and adding Claude rules all happen without touching Python. This matters because
the intended users are controls engineers, not Python developers.

The engine discovers implementations by name via `importlib`: a rule named
`foo_bar` in YAML binds to `check_foo_bar(program, rule)` in
`llr/rules/builtin.py`. **The names must match exactly** or the rule silently
loads with `check_fn=None` and never runs. `llr rules validate` catches this.

### Rule failures are non-fatal

`RuleEngine.run()` wraps each check in try/except and converts an exception into
a warning Finding. One broken rule degrades the report instead of killing the
run. Keep this — a crash on rung 300 of a 400-rung program is worse than a
missing check.

---

## The `.asc` format

Reverse-engineered from the real sample in `samples/`, not from documentation
(see "Things that didn't work"). Structure:

```
PROGRAM <name>
  VAR_EXTERNAL RETAIN ... END_VAR
  VAR CONSTANT ... END_VAR
  'LD'                          ← language tag
  BODY
    NET_WORK
      NETWORK_BODY
        B(B_CONTACT,,Var,x1,y1,x2,y2,modifier);
        B(B_COIL,,Var,x1,y1,x2,y2,modifier);
        B(B_COMMENT,,text,x1,y1,x2,y2,);
        B(B_F,FUNC!,,x1,y1,x2,y2,,params);
        L(x1,y1,x2,y2);         ← wiring, ignored
      END_NETWORK_BODY
    END_NET_WORK
  END_BODY
END_PROGRAM
```

One `NET_WORK` = one rung. Field counts: contact/coil/comment/varin/varout have
8 fields; `B_F`/`B_FB` have 9 (extra param string).

| Modifier | On `B_CONTACT` | On `B_COIL` |
|---|---|---|
| *(empty)* | NO → `LD` | normal → `OT` |
| `N` | NC → `LDN` | — |
| `R` | rising edge → `LDP` | reset → `RST` |
| `F` | falling edge → `LDF` | — |
| `S` | — | set → `SET` |
| `E` | — | ENO-driven → `OT` |

Note `R` means **rising edge** on a contact but **reset** on a coil. Easy to get
backwards.

---

## Gotchas

These all cost real debugging time. Don't re-discover them.

### `utf-16` raises `UnicodeError`, not `UnicodeDecodeError`

When a file has no BOM, Python's utf-16 codec raises bare `UnicodeError`.
`UnicodeDecodeError` is its *subclass*, so `except UnicodeDecodeError` does not
catch it and the whole encoding-fallback chain dies on the first attempt.
`_read_file()` catches `UnicodeError`. Don't "tidy" it to the narrower type.

### `B()` content needs a character scanner, not a regex

Values can be single-quoted strings containing commas and closing parens:
`B(B_VARIN,,'Send Initialization Commands',23,13,25,15,)`. Splitting on `,` or
matching to the first `)` corrupts these. `_iter_b_blocks()` tracks quote state
character by character. Keep it that way.

### Comment escapes

`~` → comma, `ø^` → newline. FPWin substitutes these so commas don't break `B()`
field splitting. Decode in `_decode_comment()`.

Comment placement is inferred from the y-coordinate: `y1 <= 3` is a rung
title (becomes `Rung.comment`), `y1 > 3` is an inline annotation (becomes
`Rung.body_comment`). Blocks at position `(0,0)` and the literal `~d` are
internal FPWin markers — skip them.

### Struct members must be detected before address prefixes

`FaultsDUT.MAIN_SEQUENCE_FAULT` starts with `F`, and `StationN_DUT.RunSteps`
would partially match address prefixes. `Instruction.address_type` checks for
`.` **first** and returns `VARIABLE`. Any new prefix matching must stay below
that check.

### `re.DOTALL` as a positional arg is a silent bug

`pattern.search(text, re.DOTALL)` passes `16` as the **`pos`** argument — it
starts the search at offset 16 and the flag is ignored. This was in the original
parser stub. Compile the flag into the pattern instead:
`re.compile(..., re.DOTALL)` then `.search(text)`.

### Packaging

- `pyproject.toml` must use `build-backend = "setuptools.build_meta"`.
  `setuptools.backends.legacy:build` requires setuptools 68+ *in the isolated
  build env*, which fails against older system setuptools with
  `ModuleNotFoundError: No module named 'setuptools.backends'`.
- `tool.setuptools.package-data` rejects a `""` key — keys must be valid package
  names or `"*"`. `rules.yaml` is a root-level file located at runtime via
  `__file__`, so it needs no package-data entry.
- `llr.spec` needs explicit `hiddenimports` for `llr.rules.builtin` (imported
  dynamically by `importlib`, so PyInstaller can't see it) and the full Flask
  chain (`flask`, `werkzeug`, `jinja2`, `itsdangerous`).
- Bundled data files resolve through `sys._MEIPASS` at runtime. See
  `_reference_doc()` in `claude_client.py` for the pattern: check the bundle
  path first, fall back to the source tree, degrade gracefully if absent.

---

## Known false positives

Documented so nobody "fixes" these by making the rules weaker without thinking.

- **R002 (duplicate output coil)** fires on SET/RST pairs in different rungs,
  which is normal PLC practice. It also counts a rung twice when a variable has
  two coils in one rung. Real duplicate-coil bugs are serious enough that the
  noise is worth it, but users may want it disabled.
- **R012 (SET without RST)** scans per-POU. A bit set in one POU and reset in
  another is flagged. The message says "in this POU" to make that clear. Fixing
  properly needs cross-POU analysis, which needs multi-POU sample files.
- **R011 (test/bypass bit)** is name-based (`bypass`, `debug`, `dummy`, `temp`,
  `tmp`, `testbit`, `forcebit`). It correctly caught `TempVar` in the sample but
  will miss bypasses with innocuous names and may flag legitimate variables.

---

## Domain knowledge worth keeping

Extracted from the FPWin Pro InfoHub index; fuller version in
`docs/fpwin_reference.md`, which is loaded into the Claude system prompt.

**Mnemonic prefixes encode operand width** — this is the main lever for
data-type checks:

| Prefix | Width | Example |
|---|---|---|
| *(none)* | 16-bit | `F0_MV`, `F20_ADD`, `F32_DIV` |
| `D` | 32-bit | `F1_DMV`, `F21_DADD`, `F33_DDIV` |
| `F` | REAL | `F309_FMV`, `F310_FADD`, `F313_FDIV` |
| `B` | BCD | `F52_BDIV` |

**STRING layout:** word 0 = max length, word 1 = current length, words 2+ =
character data. A word-level write into offset 0 or 1 corrupts the string.

**`DF` / `DFN` / `DFI` are the only stateful elements callable without an
instance** — the compiler allocates hidden edge memory per call site. A
user-defined `FUNCTION` gets no such allocation, so stateful user code needs a
`FUNCTION_BLOCK` instance, `VAR_IN_OUT` state, or a global array indexed by ID.

**Fault latching** needs two separate bits: one for "fault active" (cleared by
operator ack) and one for "already logged to history" (cleared only when the
*condition* goes false). Using one bit for both causes re-logging when an
operator acknowledges while the condition persists. The sample's rung 9 has this
bug.

---

## Things that didn't work

- **Fetching the Panasonic docs.**
  `infohub.industry.panasonic.eu/documentation/fpwin/` returns 403 to automated
  fetches, as do the PDF manuals on their CDN. The `.asc` format was
  reverse-engineered from the sample instead.
- **Scraping the InfoHub.** The site is a JavaScript SPA routing topic bodies
  through `#/topic/t-NNNNNNN` URL fragments. Fragments never reach the server, so
  a crawl retrieves the navigation index and nothing else — 376 of 445 sections
  came back "Not Found". The index was still useful: 1,148 verified instruction
  identifiers, which is what `docs/fpwin_reference.md` is built from. Per-
  instruction operand tables remain unavailable; the FPWin Pro built-in `.chm`
  is the route to those.
- **Pushing a git tag from this environment.** The git proxy returns 403 on tag
  pushes. The release workflow triggers on `v*` tags, so the first release has to
  be tagged from a normal clone.
- **Aggressive dedupe in `tools/html_to_md.py`.** The first version removed any
  block repeated across pages, which ate every operand table. Dedupe now skips
  tables, code blocks, headings, and anything over 300 chars, and is off by
  default.

---

## Conventions

- **Commits:** conventional commits (`feat:`, `fix:`, `ci:`, `docs:`).
- **Rule IDs:** `R0NN`, sequential. Next free: **R013**.
- **Adding a local rule:** add the YAML entry, add `check_<name>()` to
  `builtin.py` with signature `(program: Program, rule: RuleDescriptor) ->
  list[Finding]`, run `llr rules validate`.
- **Adding a Claude rule:** append a string to `claude_rules:`. Name real
  instructions (see `docs/fpwin_reference.md`) rather than describing them
  generically — grounded rules produce far more precise findings.
- **Exit codes:** `0` clean, `1` usage/parse error, `2` findings at `error`
  severity. `2` is the CI signal.
- **Testing:** no formal suite yet. Verify changes against
  `samples/SequenceMain_StepMode.asc` — 40 rungs, 51 variables, and known
  findings (R002 on `TSB_MainOkToInitialize` rungs 6/7, R011 on `TempVar`, R008
  on the empty placeholder rungs).

---

## Open work

- No automated tests. `samples/` has one file; a pytest suite over it would
  catch parser regressions cheaply.
- Parser discards `B_F`/`B_FB` parameter operands, keeping only the function
  name. This is why the divide-by-zero, double-word, and string-corruption
  checks are Claude rules rather than local ones. Capturing parameters and
  joining them to symbol-table types would let all three run offline.
- Only LD is exercised. IL/FBD/ST/SFC parse into a POU with a language tag but
  no meaningful rung extraction.
- Only single-POU samples tested. Multi-POU behaviour — especially R012's
  per-POU scoping — is unverified.
