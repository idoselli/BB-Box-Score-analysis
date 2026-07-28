param(
    [Parameter(Mandatory = $true)]
    [string]$HtmlPath,
    [Parameter(Mandatory = $true)]
    [string]$PdfPath
)

$ErrorActionPreference = "Stop"

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chrome)) {
    throw "Chrome not found at $chrome"
}

$resolvedHtml = (Resolve-Path $HtmlPath).Path
$pdfDirectory = Split-Path -Parent $PdfPath
if (-not (Test-Path $pdfDirectory)) {
    New-Item -ItemType Directory -Path $pdfDirectory | Out-Null
}

$resolvedPdf = [System.IO.Path]::GetFullPath($PdfPath)
$userDataDir = Join-Path $env:TEMP "codex-chrome-report-profile"
$fileUrl = "file:///" + ($resolvedHtml -replace "\\", "/")

& $chrome `
    --headless `
    --disable-gpu `
    --disable-software-rasterizer `
    --disable-dev-shm-usage `
    --no-first-run `
    --no-default-browser-check `
    --allow-file-access-from-files `
    --user-data-dir="$userDataDir" `
    --print-to-pdf="$resolvedPdf" `
    --no-pdf-header-footer `
    "$fileUrl"

if (-not (Test-Path $resolvedPdf)) {
    throw "Chrome did not create the PDF."
}

Write-Output $resolvedPdf
