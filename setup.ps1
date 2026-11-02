# One-command setup for Windows PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = $null
foreach ($v in @("3.12", "3.13", "3.11")) {
    try { & py "-$v" --version *> $null; if ($LASTEXITCODE -eq 0) { $py = "-$v"; break } } catch {}
}
if (-not $py) { Write-Host "Python 3.11-3.13 not found. Install 3.12 from python.org (tick 'Add to PATH')."; exit 1 }

if (-not (Test-Path .venv)) { & py $py -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt

Write-Host "`nSetup finished. In every new terminal run:  .venv\Scripts\Activate.ps1"
& .\.venv\Scripts\python.exe check_setup.py
