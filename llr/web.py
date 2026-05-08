"""
Browser-based UI for LadderLogicReview.

Start with:  llr web
Then open:   http://localhost:8080
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

from flask import Flask, request, Response

from .parser import parse_asc
from .parser.asc_parser import AscParseError
from .rules.engine import RuleEngine
from .report.formatter import ReportFormatter
from .analysis.claude_client import ClaudeClient, ClaudeAnalysisError

_DEFAULT_RULES = Path(__file__).parent.parent / "rules.yaml"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Upload page
# ---------------------------------------------------------------------------

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LadderLogicReview</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #f0f2f5;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    padding: 1rem;
  }
  .card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    padding: 2.5rem 2rem;
    width: 100%;
    max-width: 520px;
  }
  h1 { font-size: 1.5rem; margin: 0 0 0.25rem; color: #1a1a2e; }
  .subtitle { color: #6c757d; font-size: 0.9rem; margin-bottom: 2rem; }
  .drop-zone {
    border: 2px dashed #ced4da;
    border-radius: 8px;
    padding: 2rem 1rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    margin-bottom: 1.5rem;
    position: relative;
  }
  .drop-zone:hover, .drop-zone.dragover {
    border-color: #0d6efd;
    background: #f0f7ff;
  }
  .drop-zone input[type=file] {
    position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%;
  }
  .drop-icon { font-size: 2.5rem; line-height: 1; margin-bottom: 0.5rem; }
  .drop-label { color: #495057; font-size: 0.95rem; }
  .drop-label span { color: #0d6efd; font-weight: 600; }
  .drop-hint { color: #adb5bd; font-size: 0.8rem; margin-top: 0.3rem; }
  .file-name {
    font-size: 0.85rem; color: #198754; margin-top: 0.5rem;
    font-weight: 600; display: none;
  }
  .options { display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem; }
  label.opt-label { font-size: 0.85rem; font-weight: 600; color: #495057; display: block; margin-bottom: 0.3rem; }
  select, input[type=text] {
    width: 100%; padding: 0.45rem 0.7rem; border: 1px solid #ced4da;
    border-radius: 6px; font-size: 0.9rem; color: #212529;
    background: #fff;
  }
  select:focus, input[type=text]:focus { outline: none; border-color: #0d6efd; }
  .deep-row { display: flex; align-items: center; gap: 0.6rem; }
  .deep-row input[type=checkbox] { width: 1.1rem; height: 1.1rem; cursor: pointer; }
  .deep-row label { font-size: 0.9rem; color: #495057; cursor: pointer; margin: 0; }
  .api-key-wrap { margin-top: 0.6rem; display: none; }
  button[type=submit] {
    width: 100%; padding: 0.75rem;
    background: #0d6efd; color: #fff;
    border: none; border-radius: 8px;
    font-size: 1rem; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  button[type=submit]:hover { background: #0b5ed7; }
  button[type=submit]:disabled { background: #6c757d; cursor: not-allowed; }
  .spinner { display: none; text-align: center; margin-top: 1rem; color: #6c757d; font-size: 0.9rem; }
  .error-msg { color: #dc3545; font-size: 0.9rem; margin-top: 1rem; display: none; }
</style>
</head>
<body>
<div class="card">
  <h1>LadderLogicReview</h1>
  <p class="subtitle">Upload a FPWin Pro 7 <code>.asc</code> export to analyse it.</p>
  <form id="reviewForm" method="post" action="/review" enctype="multipart/form-data">
    <div class="drop-zone" id="dropZone">
      <input type="file" name="file" id="fileInput" accept=".asc" required>
      <div class="drop-icon">📂</div>
      <div class="drop-label">Drop your <span>.asc file</span> here, or click to browse</div>
      <div class="drop-hint">FPWin Pro 7 export — Project → Export → All objects</div>
      <div class="file-name" id="fileName"></div>
    </div>
    <div class="options">
      <div>
        <label class="opt-label" for="minSev">Minimum severity to show</label>
        <select name="min_severity" id="minSev">
          <option value="info">Info and above (show everything)</option>
          <option value="warning">Warnings and errors</option>
          <option value="error">Errors only</option>
        </select>
      </div>
      <div>
        <div class="deep-row">
          <input type="checkbox" name="deep" id="deepCheck" value="1">
          <label for="deepCheck">Deep analysis with Claude AI (requires API key)</label>
        </div>
        <div class="api-key-wrap" id="apiKeyWrap">
          <input type="text" name="api_key" id="apiKey"
                 placeholder="sk-ant-api03-…" autocomplete="off" spellcheck="false">
        </div>
      </div>
    </div>
    <button type="submit" id="submitBtn">Analyse</button>
    <div class="spinner" id="spinner">⏳ Analysing, please wait…</div>
    <div class="error-msg" id="errorMsg"></div>
  </form>
</div>
<script>
  const dropZone   = document.getElementById('dropZone');
  const fileInput  = document.getElementById('fileInput');
  const fileName   = document.getElementById('fileName');
  const deepCheck  = document.getElementById('deepCheck');
  const apiKeyWrap = document.getElementById('apiKeyWrap');
  const form       = document.getElementById('reviewForm');
  const submitBtn  = document.getElementById('submitBtn');
  const spinner    = document.getElementById('spinner');

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      fileName.textContent = '✓ ' + fileInput.files[0].name;
      fileName.style.display = 'block';
    }
  });

  ['dragenter','dragover'].forEach(e => dropZone.addEventListener(e, ev => {
    ev.preventDefault(); dropZone.classList.add('dragover');
  }));
  ['dragleave','drop'].forEach(e => dropZone.addEventListener(e, ev => {
    ev.preventDefault(); dropZone.classList.remove('dragover');
  }));
  dropZone.addEventListener('drop', ev => {
    const f = ev.dataTransfer.files[0];
    if (f) { fileInput.files = ev.dataTransfer.files; fileName.textContent = '✓ ' + f.name; fileName.style.display = 'block'; }
  });

  deepCheck.addEventListener('change', () => {
    apiKeyWrap.style.display = deepCheck.checked ? 'block' : 'none';
  });

  form.addEventListener('submit', () => {
    submitBtn.disabled = true;
    spinner.style.display = 'block';
  });
</script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index() -> Response:
    return Response(_INDEX_HTML, mimetype="text/html")


# ---------------------------------------------------------------------------
# Review endpoint
# ---------------------------------------------------------------------------

@app.route("/review", methods=["POST"])
def review() -> Response:
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return _error_page("No file uploaded.")
    if not uploaded.filename.lower().endswith(".asc"):
        return _error_page("File must be a .asc export from FPWin Pro 7.")

    min_severity = request.form.get("min_severity", "info").lower()
    deep         = bool(request.form.get("deep"))
    api_key      = request.form.get("api_key", "").strip() or None

    # Save to a temp file so the parser can open it normally
    suffix = Path(uploaded.filename).suffix or ".asc"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        uploaded.save(tmp_path)

    try:
        program = parse_asc(tmp_path)
        # Restore the original filename so the report header looks right
        program.source_file = uploaded.filename
    except AscParseError as exc:
        os.unlink(tmp_path)
        return _error_page(f"Parse error: {exc}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Local rules
    findings = []
    rules_path = str(_DEFAULT_RULES) if _DEFAULT_RULES.exists() else None
    try:
        engine = RuleEngine(rules_path)
        findings.extend(engine.run(program))
    except FileNotFoundError:
        engine = None

    # Optional Claude deep analysis
    if deep and api_key:
        try:
            claude_rules = engine.claude_rules if engine else []
            client = ClaudeClient(api_key=api_key)
            findings.extend(client.analyse(program, claude_rules))
        except ClaudeAnalysisError as exc:
            # Non-fatal — surface as a finding
            from .rules.engine import Finding, Severity
            findings.append(Finding(
                rule_id="AI", rule_name="Claude analysis",
                severity=Severity.WARNING, source="local",
                message=f"Claude analysis failed: {exc}",
            ))

    # Filter by severity
    _order = {"error": 0, "warning": 1, "info": 2}
    min_order = _order.get(min_severity, 2)
    findings = [f for f in findings if _order.get(f.severity.value, 2) <= min_order]

    formatter = ReportFormatter(program, findings)
    html = formatter.to_html()

    # Inject a "← Back" link at the top of the report body
    back_link = (
        '<p style="margin:1rem 0 0;font-size:0.85rem;">'
        '<a href="/" style="color:#0d6efd;text-decoration:none;">&#8592; Analyse another file</a>'
        '</p>\n'
    )
    html = html.replace("<body>\n", "<body>\n" + back_link, 1)

    return Response(html, mimetype="text/html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_page(message: str) -> Response:
    html = f"""\
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Error — LadderLogicReview</title>
<style>
  body {{ font-family: system-ui, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f0f2f5; }}
  .box {{ background:#fff; padding:2rem; border-radius:12px;
         box-shadow:0 4px 24px rgba(0,0,0,.1); max-width:480px; text-align:center; }}
  h2 {{ color:#dc3545; }}
  a {{ color:#0d6efd; }}
</style></head><body>
<div class="box">
  <h2>Error</h2>
  <p>{message}</p>
  <p><a href="/">&#8592; Go back</a></p>
</div></body></html>"""
    return Response(html, status=400, mimetype="text/html")


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

def run(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    if open_browser:
        import threading, webbrowser
        url = f"http://{host}:{port}"
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)
