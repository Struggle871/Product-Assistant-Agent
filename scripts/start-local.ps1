param(
    [switch]$DependenciesOnly,
    [switch]$Evaluate
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot

$taskDocker = Get-Command docker -ErrorAction SilentlyContinue
$taskDockerPath = if ($taskDocker) { $taskDocker.Source } else { $null }
if (-not $taskDockerPath) {
    foreach ($taskCandidate in @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
    )) {
        if (Test-Path -LiteralPath $taskCandidate) { $taskDockerPath = $taskCandidate; break }
    }
}
if (-not $taskDockerPath) { throw 'Install Docker Desktop first. See README.md Windows setup.' }
& $taskDockerPath info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) {
    throw 'Docker engine is unavailable. Start Docker Desktop; restart Windows if WSL setup requires it.'
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    throw 'Created .env. Set EMBEDDING_API_KEY locally, then run this script again.'
}
& $taskDockerPath compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration.' }
& $taskDockerPath compose --progress quiet up -d --build --wait --wait-timeout 180 postgres redis minio
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure startup failed. Run docker compose ps.' }
& $taskDockerPath compose --progress quiet run --build --rm minio-init
if ($LASTEXITCODE -ne 0) { throw 'MinIO bucket initialization failed.' }
if ($DependenciesOnly) {
    Write-Output 'Infrastructure ready. PostgreSQL host port defaults to 5433.'
    return
}
& $taskDockerPath compose --progress quiet up -d --build --wait --wait-timeout 300 api worker frontend
if ($LASTEXITCODE -ne 0) { throw 'Application startup or database migration failed.' }
& $taskDockerPath compose exec -T api python -m scripts.check_dependencies
if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed; see dependency codes above.' }
& $taskDockerPath compose exec -T api python -m scripts.import_demo
if ($LASTEXITCODE -ne 0) { throw 'Demo import failed; indexes were not accepted.' }
if ($Evaluate) {
    & $taskDockerPath compose exec -T api python -m scripts.evaluate_retrieval
    if ($LASTEXITCODE -ne 0) { throw 'Retrieval smoke evaluation failed.' }
}
Write-Output 'Application ready: http://localhost:8080'
