# Starts the PowerChat web app on http://localhost:5173. Installs packages on first run.
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev
