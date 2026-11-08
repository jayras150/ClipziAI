<#
.SYNOPSIS
    Build dan push image Docker Clipzi AI (backend & frontend) ke Docker Hub.

.DESCRIPTION
    Menghasilkan dua image terpisah:
        <user>/clipzi-backend:<tag>
        <user>/clipzi-frontend:<tag>
    Image frontend meng-inject NEXT_PUBLIC_API_URL saat container dijalankan,
    sehingga satu image bisa dipakai untuk environment mana pun.

.EXAMPLE
    ./scripts/build-and-push.ps1 -DockerHubUser budi

.EXAMPLE
    ./scripts/build-and-push.ps1 -DockerHubUser budi -Tag 1.0.0 -Platform linux/amd64

.EXAMPLE
    ./scripts/build-and-push.ps1 -DockerHubUser budi -SkipPush
#>
param(
    [Parameter(Mandatory = $true)][string]$DockerHubUser,
    [string]$Tag = "latest",
    [string]$Platform = "linux/amd64",
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

$backendImage = "$DockerHubUser/clipzi-backend:$Tag"
$frontendImage = "$DockerHubUser/clipzi-frontend:$Tag"

function Invoke-Docker {
    param([string[]]$Arguments)

    Write-Host "> docker $($Arguments -join ' ')" -ForegroundColor Cyan
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Perintah docker gagal dengan exit code $LASTEXITCODE."
    }
}

Write-Host "== Cek Docker daemon ==" -ForegroundColor Yellow
Invoke-Docker @("version", "--format", "{{.Server.Version}}")

if (-not $FrontendOnly) {
    Write-Host "`n== Build backend ($backendImage) ==" -ForegroundColor Yellow
    Invoke-Docker @(
        "build",
        "--platform", $Platform,
        "-t", $backendImage,
        "-f", (Join-Path $backendDir "Dockerfile"),
        $backendDir
    )

    if (-not $SkipPush) {
        Write-Host "`n== Push backend ==" -ForegroundColor Yellow
        Invoke-Docker @("push", $backendImage)
    }
}

if (-not $BackendOnly) {
    Write-Host "`n== Build frontend ($frontendImage) ==" -ForegroundColor Yellow
    Invoke-Docker @(
        "build",
        "--platform", $Platform,
        "-t", $frontendImage,
        "-f", (Join-Path $frontendDir "Dockerfile"),
        $frontendDir
    )

    if (-not $SkipPush) {
        Write-Host "`n== Push frontend ==" -ForegroundColor Yellow
        Invoke-Docker @("push", $frontendImage)
    }
}

Write-Host "`n== Selesai ==" -ForegroundColor Green
if (-not $FrontendOnly) { Write-Host "Backend : $backendImage" }
if (-not $BackendOnly) { Write-Host "Frontend: $frontendImage" }
Write-Host "`nContoh menjalankan di instance (Vast.ai / VPS):"
Write-Host "  docker run -d --name clipzi-api -p 8000:8000 --env-file backend/.env $backendImage"
Write-Host "  docker run -d --name clipzi-web -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000 $frontendImage"
