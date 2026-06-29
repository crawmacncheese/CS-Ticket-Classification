# Start the local portal using prod Drive folders (.env / .env.example).
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example."
        Write-Host "Place the service-account key at secrets/google/credentials.json before Drive sync works."
    } else {
        throw ".env missing and no .env.example to copy."
    }
}

$creds = Join-Path $Root "secrets\google\credentials.json"
if (-not (Test-Path $creds)) {
    Write-Warning "Missing $creds — portal will fall back to local runs/live/ seeds until credentials are added."
}

$uvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicorn)) {
    $uvicorn = "uvicorn"
}

Write-Host "Starting portal on http://127.0.0.1:8777 (Drive live config enabled when credentials are present)."
& $uvicorn cs_tickets.portal_app:app --reload --port 8777 --env-file .env
