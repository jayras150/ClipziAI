<#
ClipziAI - backup dari Windows dalam SATU perintah, lalu unduh arsipnya.

Contoh:
  .\scripts\backup-all.ps1
  .\scripts\backup-all.ps1 -SkipDb
  .\scripts\backup-all.ps1 -OutDir .\backups
#>
param(
  [string]$VpsHost = "root@43.167.162.69",
  [string]$AppDir = "/opt/clipzi/app",
  [string]$OutDir = "$PSScriptRoot\..\backups",
  [switch]$SkipDb
)

$ErrorActionPreference = "Stop"

$flag = if ($SkipDb) { "--skip-db" } else { "" }
Write-Host "[1/3] Menjalankan backup di VPS..." -ForegroundColor Cyan
$result = ssh $VpsHost "bash $AppDir/scripts/backup-all.sh --app-dir $AppDir $flag"
$result | ForEach-Object { Write-Host $_ }

$line = ($result | Select-String -Pattern "SELESAI: (.+?)\(" ).Matches | Select-Object -Last 1
if (-not $line) { throw "Tidak menemukan path arsip pada output backup." }
$remote = $line.Groups[1].Value.Trim()

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Write-Host "[2/3] Mengunduh $remote -> $OutDir" -ForegroundColor Cyan
scp "${VpsHost}:$remote" $OutDir | Out-Null

$local = Join-Path $OutDir (Split-Path $remote -Leaf)
Write-Host "[3/3] Verifikasi checksum lokal" -ForegroundColor Cyan
$hash = (Get-FileHash $local -Algorithm SHA256).Hash
$size = [math]::Round((Get-Item $local).Length / 1MB, 2)
Write-Host "OK  $local  ($size MB)  SHA256=$hash" -ForegroundColor Green
