# Start the SYNTHETIC-DATA demo of Aditya BioNova Smart HMS on this Windows
# computer (Docker Desktop). Phones on the same Wi-Fi can then open the web
# app and use the LAN demo APK. See docs/DEMO.md.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demo-up.ps1          start
#   powershell -ExecutionPolicy Bypass -File scripts\demo-up.ps1 down     stop, keep data
#   powershell -ExecutionPolicy Bypass -File scripts\demo-up.ps1 reset    stop, DELETE data
#
# Never use this for real patients: development mode over plain HTTP, with
# throw-away secrets in infra\docker\.env.demo (git-ignored).
param([ValidateSet("up", "down", "reset")][string]$Action = "up")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$EnvFile = "infra/docker/.env.demo"
$Compose = @("compose", "-p", "hms-demo", "-f", "infra/docker/docker-compose.yml",
             "-f", "infra/docker/docker-compose.demo.yml", "--env-file", $EnvFile)

if ($Action -eq "down") { & docker @Compose down; exit $LASTEXITCODE }
if ($Action -eq "reset") {
  & docker @Compose down -v
  Remove-Item -ErrorAction SilentlyContinue $EnvFile
  exit 0
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker Desktop is not installed (docs/DEMO.md)."
}

# Works in Windows PowerShell 5.1 (.NET Framework) and PowerShell 7.
$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
function New-Bytes([int]$n) { $b = New-Object byte[] $n; $Rng.GetBytes($b); return ,$b }
function New-Hex { -join ((New-Bytes 24) | ForEach-Object { "{0:x2}" -f $_ }) }

if (-not (Test-Path $EnvFile)) {
  $key = [Convert]::ToBase64String((New-Bytes 32)).Replace("+", "-").Replace("/", "_")
  @(
    "# Throw-away secrets for the synthetic-data demo (scripts/demo-up.ps1).",
    "HMS_PG_PASSWORD=$(New-Hex)",
    "HMS_APP_PASSWORD=$(New-Hex)",
    "JWT_SECRET=$(New-Hex)",
    "FIELD_ENCRYPTION_KEY=$key",
    "HMS_ENVIRONMENT=development",
    "HMS_BIND_ADDRESS=0.0.0.0",
    "HMS_PG_HOST_PORT=55432"
  ) | Set-Content -Encoding ascii $EnvFile
  Write-Host "Created $EnvFile with random demo secrets."
}

& docker @Compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Waiting for the demo to start..."
$ready = $false
for ($i = 0; $i -lt 100; $i++) {
  try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:3000/api/v1/health/ready | Out-Null
    $ready = $true; break
  } catch { Start-Sleep -Seconds 3 }
}
if (-not $ready) {
  & docker @Compose ps -a
  Write-Error "The demo did not become ready. Logs: docker $($Compose -join ' ') logs"
}

$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -match '^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)' } |
  Select-Object -ExpandProperty IPAddress
Write-Host ""
Write-Host "Aditya BioNova Smart HMS demo is running (SYNTHETIC DATA ONLY)."
Write-Host "  On this computer:   http://localhost:3000"
foreach ($ip in $ips) {
  Write-Host "  From your phone:    http://${ip}:3000   (web)"
  Write-Host "  Android demo app:   server address ${ip}:8000"
}
Write-Host "  Password for every demo account: Demo-Sunrise-2026!   (accounts: docs/DEMO.md)"
Write-Host "  If the phone cannot connect, allow ports 3000 and 8000 in Windows Defender Firewall (docs/DEMO.md)."
