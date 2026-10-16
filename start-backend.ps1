# Starts the PowerChat API on http://127.0.0.1:8000 (docs: /docs). Creates the venv on first run.
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
}
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
