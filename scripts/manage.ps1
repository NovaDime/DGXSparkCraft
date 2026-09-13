param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ToolArguments
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$roundtableRoot = Split-Path -Parent $PSScriptRoot
try {
    if ($env:ROUNDTABLE_PYTHON) {
        $roundtablePython = $env:ROUNDTABLE_PYTHON
    } elseif (Test-Path -LiteralPath (Join-Path $roundtableRoot '.venv\Scripts\python.exe')) {
        $roundtablePython = Join-Path $roundtableRoot '.venv\Scripts\python.exe'
    } else {
        $roundtablePython = (Get-Command python -ErrorAction Stop).Source
    }
    & $roundtablePython -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    & $roundtablePython (Join-Path $PSScriptRoot 'service.py') $Action @ToolArguments
    exit $LASTEXITCODE
} catch {
    Write-Host "Failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Install Python 3.11+, or set ROUNDTABLE_PYTHON to your python.exe path.'
    Write-Host 'For missing packages, run: python -m pip install -r requirements.txt'
    exit 1
}
