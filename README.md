# LadderLogicReview

Static analyser for Panasonic FPWin Pro 7 ladder logic programs.

FPWin Pro already catches compilation errors. This catches the things it
doesn't: duplicate coils, missing comments, unsafe latches, test bypasses left
in production code, and — with the Claude API — logical and safety problems that
need an understanding of what the program is trying to do.

Runs fully offline. Claude analysis is optional and opt-in.

---

## Install

```bash
git clone https://github.com/Cheezwedge/LadderLogicReview.git
cd LadderLogicReview
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Or download a prebuilt `llr.exe` from the [Releases](../../releases) page — no
Python needed.

## Export a file from FPWin Pro 7

1. Open the project
2. **Project → Export → All objects**
3. Save as `.asc` (Unicode UTF-16)

## Use it

### Browser UI

```bash
llr web
```

Opens `http://localhost:8080`. Drag an `.asc` file onto the page, pick a
severity filter, optionally tick deep analysis and supply an API key.

The server binds to `127.0.0.1` only. To share it on a LAN, use
`llr web --host 0.0.0.0` — note there is no authentication.

### Command line

```bash
llr review program.asc                      # offline checks, terminal output
llr review program.asc -o report.html       # HTML report
llr review program.asc -o report.json       # JSON, for CI
llr review program.asc --min-severity error # errors only
llr review program.asc --deep --api-key sk-ant-...   # add Claude analysis
```

Exit code is `2` when any `error`-severity finding is present, so it drops
straight into a CI pipeline.

### Inspect the rules

```bash
llr rules list        # every rule, severity, enabled state, implementation status
llr rules validate    # confirm each enabled rule has an implementation
```

---

## Rules

Two tiers. Local rules run offline and are mechanically decidable. Claude rules
are plain-English instructions requiring semantic understanding, and only run
with `--deep`.

### Local (12)

| ID | Rule | Severity | Catches |
|---|---|---|---|
| R001 | `missing_rung_comment` | warning | Undocumented rungs |
| R002 | `duplicate_output_coil` | error | Same coil driven from multiple rungs |
| R003 | `direct_physical_address` | info | Raw X/Y/R/DT with no named alias |
| R004 | `system_register_write` | error | Writes to DT9000+ / R900+ |
| R005 | `variable_missing_comment` | info | Undocumented symbol-table entries |
| R006 | `timer_counter_no_comment` | warning | Timer/counter rungs with no explanation |
| R007 | `output_contact_same_rung` | warning | Self-seal latches needing verification |
| R008 | `empty_rung` | warning | Dead rungs |
| R009 | `output_used_as_contact` | info | Undocumented output feedback |
| R010 | `rung_no_output` | warning | Logic that drives nothing |
| R011 | `test_bypass_bit` | warning | `bypass`/`debug`/`temp`/`dummy` bits left in |
| R012 | `set_without_reset` | warning | SET coils with no RST path in the POU |

### Claude (19, with `--deep`)

Grouped by theme: safety interlocks, logic errors, bad practices, documentation,
station handshaking, scan-time independence, parallel-station isolation, safety
reset coverage, test/debug remnants, and data-type safety (double-word
truncation, divide-by-zero, STRING header corruption).

Deep analysis loads `docs/fpwin_reference.md` — a condensed reference of 1,148
verified FPWin Pro instruction names — into a cached system prompt, so findings
cite real instructions rather than guessed ones.

### Customising

Everything lives in `rules.yaml`.

- Toggle `enabled: true/false`, change `severity`, or reword `description`
- Add a Claude rule by appending a plain-English string to `claude_rules:` —
  no code required
- Add a local rule by adding a YAML entry **and** a matching
  `check_<name>()` function in `llr/rules/builtin.py`, then run
  `llr rules validate`

When using the bundled `.exe`, place an edited `rules.yaml` next to the
executable and it takes precedence over the built-in copy.

---

## Privacy

Offline mode sends nothing anywhere — parsing and rule checks are entirely
local.

`--deep` sends your program text to the Anthropic API. Anthropic does not train
on API data by default. If that's still a concern, the 12 local rules catch the
most common issues with no network traffic at all.

---

## Build a standalone executable

```bash
pip install pyinstaller
pyinstaller llr.spec       # → dist/llr.exe (Windows) or dist/llr
```

`rules.yaml` and `docs/fpwin_reference.md` are bundled in. Only `--deep` needs
internet.

### Releases

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which builds
`llr.exe` on a Windows runner and publishes a GitHub Release with the binary
attached:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Extras

`tools/html_to_md.py` combines a tree of HTML help files (a `.chm` extraction,
saved help pages) into one Markdown document — strips nav chrome, filters stub
pages, preserves tables.

```bash
pip install beautifulsoup4 markdownify
python tools/html_to_md.py -i ./help -o docs/fpwin_help.md --dry-run
```

---

## Project layout

```
llr/
  cli.py                 Click CLI — review, web, rules
  models.py              Program / POU / Rung / Instruction / Variable
  web.py                 Flask browser UI
  parser/asc_parser.py   .asc reader
  rules/engine.py        YAML loader + rule dispatch
  rules/builtin.py       check_*() implementations
  report/formatter.py    terminal / HTML / JSON output
  analysis/claude_client.py   Claude API with prompt caching
rules.yaml               user-editable rule config
docs/fpwin_reference.md  instruction reference for deep analysis
samples/                 test .asc files
tools/html_to_md.py      HTML help → Markdown
```

See [CLAUDE.md](CLAUDE.md) for architecture rationale, format details, and
known gotchas.

## Status

Working: `.asc` parsing (LD), all 12 local rules, Claude deep analysis, terminal
/ HTML / JSON reports, browser UI, Windows build pipeline.

Not yet: automated tests, function-block parameter extraction, meaningful
IL/FBD/ST/SFC support, multi-POU verification.
