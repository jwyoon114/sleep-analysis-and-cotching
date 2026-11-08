$ErrorActionPreference = 'Stop'
$version = '2026.10.7'
$expectedHash = '2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'
$directory = Join-Path $PSScriptRoot 'bin'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$destination = Join-Path $directory "cloudflared-$version.exe"
if (-not (Test-Path -LiteralPath $destination)) {
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/download/$version/cloudflared-windows-amd64.exe" -OutFile $destination
}
if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'Cloudflare download SHA256 mismatch. The file was not executed.'
}
Write-Output "CLOUDFLARED_VERIFIED: $version"
