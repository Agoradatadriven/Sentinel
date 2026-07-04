<#
  seed-job.ps1 - seed (or re-seed) the deployed database via a Cloud Run Job.

  WARNING: seed.py WIPES and rebuilds all tables with demo data. Run it for the INITIAL seed, or a
  deliberate reset - never against a database holding real records you want to keep.

  For an empty production start, skip this entirely: the app auto-creates empty tables on first
  boot (create_all). Seed only when you want the demo dataset.

  Usage (from sentinel/ root), same DB target as your deploy:
    .\deploy\seed-job.ps1 -CloudSqlInstance "agora-data-driven:asia-southeast1:sentinel-db"
#>
param(
  [string]$Project          = "agora-data-driven",
  [string]$Region           = "asia-southeast1",
  [string]$Repo             = "agora",
  [string]$Service          = "sentinel",
  [Parameter(Mandatory = $true)][string]$CloudSqlInstance,
  [string]$DbUrlSecretName  = "sentinel-database-url",
  [string]$JobName          = "sentinel-seed"
)
$ErrorActionPreference = "Stop"

$Image = "$Region-docker.pkg.dev/$Project/$Repo/${Service}:latest"

Write-Host "Deploying seed job '$JobName' (image: $Image)" -ForegroundColor Cyan
gcloud run jobs deploy $JobName `
  --project $Project --region $Region --image $Image `
  --set-cloudsql-instances $CloudSqlInstance `
  --set-secrets "DATABASE_URL=${DbUrlSecretName}:latest" `
  --command python --args seed.py `
  --max-retries 0
if ($LASTEXITCODE -ne 0) { throw "Job deploy failed." }

Write-Host "Executing seed (this WIPES + rebuilds the DB)..." -ForegroundColor Yellow
gcloud run jobs execute $JobName --project $Project --region $Region --wait
if ($LASTEXITCODE -ne 0) { throw "Seed execution failed - check: gcloud run jobs executions list --job $JobName" }

Write-Host ""
Write-Host "Database seeded." -ForegroundColor Green
