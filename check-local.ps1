param(
    [int]$Port = 5055
)

$ErrorActionPreference = "Stop"
$Url = "http://127.0.0.1:$Port/"

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
} catch {
    Write-Host "Local app is not responding at $Url"
    Write-Host $_.Exception.Message
    exit 1
}

if ($response.StatusCode -ne 200) {
    Write-Host "Local app responded with HTTP $($response.StatusCode) at $Url"
    exit 1
}

$content = [string]$response.Content
if (-not $content.Contains("Box Score Analysis")) {
    Write-Host "Local app responded at $Url, but the expected page title was not found."
    exit 1
}

Write-Host "OK: local app is responding at $Url"
