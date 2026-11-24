$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
docker compose --project-directory $project up -d --no-build
if ($LASTEXITCODE -ne 0) { throw 'Development startup failed' }
Write-Host 'Open http://localhost:8088. Source and API configuration reload automatically.'
