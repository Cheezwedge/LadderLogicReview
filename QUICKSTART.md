# LadderLogicReview — Quick Start

Static analyser for Panasonic FPWin Pro 7 ladder logic programs.

## Setup

```bash
pip install -r requirements.txt
pip install -e .
```

## Export a file from FPWin Pro 7

1. Open your project in FPWin Pro 7
2. **Project → Export → All objects**
3. Save as `*.asc` (choose Unicode UTF-16 encoding)
4. Drop the file into the `samples/` folder or use a full path below

## Run a review

```bash
# Offline rule check only (no internet, no API key needed)
llr review samples/myprogram.asc

# Deep analysis with Claude API
llr review samples/myprogram.asc --deep --api-key sk-ant-...

# Write an HTML report
llr review samples/myprogram.asc --output report.html

# Write a JSON report (useful for CI pipelines)
llr review samples/myprogram.asc --output report.json

# Only show errors, skip warnings and info
llr review samples/myprogram.asc --min-severity error
```

## Manage rules

```bash
# List all rules and their status
llr rules list

# Check that every enabled rule has an implementation
llr rules validate
```

## Customise rules

Edit `rules.yaml`:

- **`rules` section** — toggle `enabled: true/false`, change `severity`,
  or add new entries (then add a matching `check_<name>()` function to
  `llr/rules/builtin.py`).
- **`claude_rules` section** — add plain-English instructions. No code
  needed; Claude reads them directly when `--deep` is used.

## Build a standalone .exe (Windows/Linux/Mac)

```bash
pip install pyinstaller
pyinstaller llr.spec
# Output: dist/llr.exe
```

The bundled executable includes `rules.yaml` and works fully offline
(only the `--deep` flag requires internet access).

## Status

| Component | Status |
|---|---|
| Data models | ✅ Complete |
| Rule engine | ✅ Complete |
| Built-in rules (R001–R010) | ✅ Complete |
| Claude API client | ✅ Complete |
| Report formatter (terminal/HTML/JSON) | ✅ Complete |
| CLI | ✅ Complete |
| **.asc file parser** | ⏳ **Awaiting sample file** |

The parser stub accepts any `.asc` file and passes the raw text to Claude
(`--deep` mode works now). Structured local-rule checks (duplicate coils,
missing comments per-rung, etc.) require the parser to be completed once
a real `.asc` sample is provided.
