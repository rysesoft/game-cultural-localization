# Runs the whole unittest suite on Python 3.15 (py -3.15, LocalAppData Python315, python).
# Usage: pwsh tests/run_all.ps1   (from the repository root or anywhere)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$candidates = @()
if ($env:GCL_PYTHON) { $candidates += $env:GCL_PYTHON }
$py315 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python315\python.exe"
if (Test-Path $py315) { $candidates += $py315 }
if (Test-Path "C:\Python315\python.exe") { $candidates += "C:\Python315\python.exe" }
if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += "py -3.15" }
if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += "python" }
$failed = 0
$ran = 0
foreach ($c in ($candidates | Select-Object -Unique)) {
    $parts = $c -split " "
    $exe = $parts[0]; $extra = @(); if ($parts.Length -gt 1) { $extra = $parts[1..($parts.Length - 1)] }
    $ver = & $exe @extra -B -c "import sys; sys.exit(0 if sys.version_info >= (3, 15) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $verStr = & $exe @extra -B -c "import sys; print(sys.version.split()[0])" 2>$null
    Write-Host "=== $c ($verStr): python -B -m unittest discover tests" -ForegroundColor Cyan
    Push-Location $root
    & $exe @extra -B -X utf8 -m unittest discover tests
    $code = $LASTEXITCODE
    Pop-Location
    $ran++
    if ($code -ne 0) { $failed++; Write-Host "FAILED with $c" -ForegroundColor Red } else { Write-Host "OK with $c" -ForegroundColor Green }
    break
}
if ($ran -eq 0) { Write-Host "Python 3.15+ interpreter not found" -ForegroundColor Red; exit 2 }
exit $failed
