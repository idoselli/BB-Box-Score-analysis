param(
    [int]$Port = 5055
)

$ErrorActionPreference = "Stop"
$connections = @()

try {
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
} catch {
    $netstatLines = @(netstat -ano | Select-String ":$Port\s+.*LISTENING")
    foreach ($line in $netstatLines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
        if ($parts.Count -gt 0) {
            $connections += [pscustomobject]@{ OwningProcess = [int]$parts[-1] }
        }
    }
}

if (-not $connections) {
    Write-Host "No local server is listening on port $Port."
    exit 0
}

$stopped = 0
foreach ($connection in $connections) {
    $processId = [int]$connection.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    $commandLine = if ($process) { [string]$process.CommandLine } else { "" }

    if ($commandLine -notmatch "flask" -or $commandLine -notmatch "web_tool") {
        Write-Host "Port $Port is used by PID $processId, but it does not look like this Flask app."
        Write-Host "Command: $commandLine"
        continue
    }

    Stop-Process -Id $processId -Force
    Write-Host "Stopped local Flask server on port $Port (PID $processId)."
    $stopped += 1
}

if ($stopped -eq 0) {
    Write-Host "No matching BB box score Flask server was stopped."
    exit 1
}
