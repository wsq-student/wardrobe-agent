$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath "$project\.env")) {
    function New-Secret { return [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLower() }
    $mysqlSecret = New-Secret
    $content = Get-Content -LiteralPath "$project\.env.example" -Raw
    $content = $content.Replace('MYSQL_PASSWORD=change-me', "MYSQL_PASSWORD=$mysqlSecret")
    $content = $content.Replace('wardrobe:change-me@', "wardrobe:${mysqlSecret}@")
    $content = $content.Replace('change-root-password', (New-Secret)).Replace('JWT_SECRET=replace-with-random-secret', ('JWT_SECRET=' + (New-Secret))).Replace('S3_SECRET_KEY=replace-with-random-secret', ('S3_SECRET_KEY=' + (New-Secret)))
    [IO.File]::WriteAllText("$project\.env", $content, [Text.UTF8Encoding]::new($false))
    Write-Host 'Created .env with random local credentials. Add API keys locally.'
}
docker compose --project-directory $project up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed' }
Write-Host 'Open http://localhost:8088'
