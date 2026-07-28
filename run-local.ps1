param(
    [int]$Port = 5055
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $RepoRoot ".env"

function Import-LocalEnv {
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        return
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
}

function Test-PortInUse {
    param([int]$LocalPort)

    try {
        return [bool](Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue)
    } catch {
        $matches = netstat -ano | Select-String ":$LocalPort\s+.*LISTENING"
        return [bool]$matches
    }
}

Set-Location -LiteralPath $RepoRoot
Import-LocalEnv

if (Test-PortInUse -LocalPort $Port) {
    Write-Host "Port $Port is already in use."
    Write-Host "Run .\stop-local.ps1 -Port $Port if this repo's Flask server is still running."
    exit 1
}

Write-Host "Starting BB box score analysis on http://127.0.0.1:$Port/"
Write-Host "Press Ctrl+C in this window to stop the server."
python -m flask --app web_tool run --host 127.0.0.1 --port $Port
