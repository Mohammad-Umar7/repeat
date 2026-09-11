# One-command dev start (Windows): backend on :8765 and a fresh extension build.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$root\backend\.env")) { Copy-Item "$root\.env.example" "$root\backend\.env"; Write-Host "created backend\.env from .env.example (demo mode)" }
Push-Location "$root\extension"
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
Write-Host ""
Write-Host "Backend: http://127.0.0.1:8765/docs   Extension: load extension\dist unpacked in chrome://extensions"
Write-Host "Ctrl+C stops the backend. Reset the demo any time with .\scripts\reset-demo.ps1"
Push-Location "$root\backend"
try { python -m repeat } finally { Pop-Location }
