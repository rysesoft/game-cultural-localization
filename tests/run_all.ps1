# Runs the whole unittest suite with every Python found (bundled DSH runtime, "py -3.14", "python").
# Usage: pwsh tests/run_all.ps1   (from the repository root or anywhere)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$candidates = @()
if ($env:GCL_PYTHON) { $candidates += $env:GCL_PYTHON }
$bundled = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (Test-Path $bundled) { $candidates += $bundled }
if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += "py -3.14"; $candidates += "py -3.12" }
if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += "python" }
$failed = 0
$ran = 0
foreach ($c in ($candidates | Select-Object -Unique)) {
    $parts = $c -split " "
    $exe = $parts[0]; $extra = @(); if ($parts.Length -gt 1) { $extra = $parts[1..($parts.Length - 1)] }
    $ver = & $exe @extra -c "import sys; print(sys.version.split()[0])" 2>$null
    if (-not $ver) { continue }
    Write-Host "=== $c ($ver): python -m unittest discover tests" -ForegroundColor Cyan
    Push-Location $root
    & $exe @extra -B -X utf8 -m unittest discover tests
    $code = $LASTEXITCODE
    Pop-Location
    $ran++
    if ($code -ne 0) { $failed++; Write-Host "FAILED with $c" -ForegroundColor Red } else { Write-Host "OK with $c" -ForegroundColor Green }
}
if ($ran -eq 0) { Write-Host "No Python interpreter found" -ForegroundColor Red; exit 2 }
exit $failed
