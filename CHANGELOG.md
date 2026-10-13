# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `CLAUDE.md` — architecture rationale, `.asc` format notes, parser gotchas,
  known false positives, domain knowledge, and a record of approaches that
  failed and why.
- `README.md` — install, usage, rule tables, privacy notes, build and release
  instructions, project layout.
- `CHANGELOG.md` — this file.

### Changed
- `QUICKSTART.md` status table refreshed; it still listed the parser as
  "awaiting sample file" after the parser had been completed.

---

## [0.1.0] — 2026-10-13

First working version. Offline analysis, Claude deep analysis, browser UI, and
a Windows build pipeline.

### Added

**Parser**
- `.asc` reader for FPWin Pro 7 exports, reverse-engineered from a real sample
  (Panasonic's documentation site blocks automated access).
- Encoding fallback chain: utf-16, utf-8-sig, utf-8, mbcs, latin-1.
- Quote-aware character scanner for `B()` blocks, so single-quoted strings
  containing commas and parentheses parse correctly.
- Comment decoding: `~` → comma, `ø^` → newline. Rung titles vs. inline
  annotations distinguished by y-coordinate.
- `B_CONTACT` / `B_COIL` / `B_F` / `B_FB` / `B_VAROUT` mapped to instructions;
  modifiers resolved (`N`→`LDN`, `R`→`LDP`, `F`→`LDF`, `S`→`SET`, `R`→`RST`,
  `E`→`OT`).

**Rules — 12 local**
- R001 `missing_rung_comment`, R002 `duplicate_output_coil`,
  R003 `direct_physical_address`, R004 `system_register_write`,
  R005 `variable_missing_comment`, R006 `timer_counter_no_comment`,
  R007 `output_contact_same_rung`, R008 `empty_rung`,
  R009 `output_used_as_contact`, R010 `rung_no_output`.
- R011 `test_bypass_bit` — flags operands and variables named like test or
  debug leftovers (`bypass`, `debug`, `dummy`, `temp`, `tmp`, `testbit`,
  `forcebit`).
- R012 `set_without_reset` — SET coils with no RST path in the same POU.

**Rules — 19 Claude deep-analysis**
- Safety interlocks, unreachable logic, outputs that can never de-energise,
  zero/negative presets, rung complexity, magic constants, duplicate comments,
  POU and variable documentation.
- Station handshaking — done/acknowledge interlocks before step transitions.
- Scan-time independence — scan-cycle counting and edge contacts misused for
  timing.
- Parallel-station isolation — upstream loaders and feeders gated by main
  sequence pause state.
- Safety reset coverage — motion-commanding SET bits lacking reset paths on
  E-stop, fault, and re-initialisation.
- Test and debug remnants — hardcoded TRUE/FALSE contacts, TODO/FIXME comments,
  unconditionally disabled rungs.
- Data-type safety — double-word into single-word truncation, divide-by-zero
  across all 13 dividing instructions, STRING length-header corruption.

**Interfaces**
- `llr review` with `--deep`, `--rules`, `--output`, `--min-severity`,
  `--no-local`, `--api-key`, `--model`. Exit code 2 on error-severity findings.
- `llr web` — Flask browser UI with drag-and-drop upload, severity filter, and
  optional API key entry. Binds to localhost.
- `llr rules list` / `llr rules validate`.
- Terminal (Rich), HTML, and JSON report formats.

**Claude integration**
- Prompt caching on the system prompt so repeated runs reuse cached tokens.
- `docs/fpwin_reference.md` — condensed reference built from 1,148 verified
  instruction identifiers, loaded into the cached system prompt so findings
  cite real instruction names. Covers the `D`/`F`/`B` width-prefix convention,
  the full divide surface, STRING memory layout, edge-detection instructions,
  address types, and IEC type widths.

**Packaging and tooling**
- `llr.spec` for single-file PyInstaller builds, bundling `rules.yaml` and the
  instruction reference.
- `.github/workflows/release.yml` — builds `llr.exe` on a Windows runner and
  publishes a GitHub Release on any `v*` tag.
- `tools/html_to_md.py` — combines HTML help trees into one Markdown file.
  Strips nav chrome, filters stub pages, tries CHM-typical encodings, and
  unescapes identifiers so instruction names stay greppable. Optional dedupe
  never touches tables, code blocks, or long passages.

### Fixed
- Encoding detection caught `UnicodeDecodeError`, but Python's utf-16 codec
  raises bare `UnicodeError` for a file with no BOM — the parent class, so the
  fallback chain died on the first attempt instead of trying the next encoding.
- `pyproject.toml` used `build-backend = "setuptools.backends.legacy:build"`,
  which fails against older system setuptools in pip's isolated build
  environment. Switched to `setuptools.build_meta`.
- `tool.setuptools.package-data` had an invalid `""` key; setuptools requires
  valid package names or `"*"`.
- `flask` was in `requirements.txt` but missing from `pyproject.toml`
  dependencies.
- Struct member access (`FaultsDUT.MAIN_SEQUENCE_FAULT`) was misclassified as a
  physical address; `address_type` now checks for `.` before prefix matching.
- Models recognised neither LD-specific contact mnemonics (`LDN`/`LDP`/`LDF`)
  nor `F`/`FB`/`VAROUT` as outputs.
