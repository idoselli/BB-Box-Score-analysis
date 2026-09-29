param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("u21", "market")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $RepoRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw "Create the ignored .env file with beta collector settings first."
}

Get-Content -LiteralPath $EnvPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
        return
    }
    $name, $value = $line.Split("=", 2)
    $name = $name.Trim()
    $value = $value.Trim().Trim('"').Trim("'")
    if ($name) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if ($env:BB_V1_EXCEPTION_APPROVED -ne "true") {
    throw "Local beta collection is disabled in .env."
}
if (-not $env:BB_V1_PERSONAL_TOKEN) {
    throw "BB_V1_PERSONAL_TOKEN is missing from the ignored .env file."
}

$Candidates = @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe")
)
$PythonExecutable = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $PythonExecutable) {
    throw "No supported Python interpreter was found. Install project dependencies in .venv."
}

Set-Location -LiteralPath $RepoRoot
& $PythonExecutable -m beta_v1.collector $Mode
exit $LASTEXITCODE
