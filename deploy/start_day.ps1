# start_day.ps1  -  Sentinel :: Google Cloud preflight (agora-data-driven)
# Signs you in as the Agora account via the BROWSER (full web flow, so you never get the
# "Reauthentication required / enter password" terminal prompt), pins the project, and
# confirms access - so deploy.ps1 / seed-job.ps1 run without surprises.
#
# Lives in:  sentinel/deploy/
# Run:               .\deploy\start_day.ps1
# Or double-click:   deploy\start_day.cmd
#
# Tip: run this in a STANDALONE PowerShell window (from the Start menu), not the VS Code
# integrated terminal - that's what lets gcloud pop your browser.

$ACCOUNT = "info@agoradatadriven.com"
$PROJECT = "agora-data-driven"

# Work from the sentinel/ root so the printed next-step commands are correct.
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host ""
Write-Host "=== Sentinel :: cloud preflight ===" -ForegroundColor Cyan
Write-Host "Working dir: $(Get-Location)" -ForegroundColor DarkGray

# 1. gcloud present?
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "[X] gcloud not found. Install the Google Cloud SDK, then reopen PowerShell." -ForegroundColor Red
    exit 1
}

# 2. Is the Agora account already valid?
Write-Host "[*] Checking credentials for $ACCOUNT ..." -ForegroundColor Yellow
$token = gcloud auth print-access-token --account $ACCOUNT 2>$null
if (-not $token) {
    Write-Host "[!] Sign-in needed. Opening your browser (full web flow - password goes on Google's page, NOT the terminal)..." -ForegroundColor Yellow
    gcloud auth login $ACCOUNT --force --update-adc
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Login did not complete. If no browser opened, set a default browser in Windows Settings and re-run." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] Credentials valid." -ForegroundColor Green
}

# 3. Pin the active account + project.
gcloud config set account $ACCOUNT 2>$null | Out-Null
gcloud config set project $PROJECT 2>$null | Out-Null
Write-Host "[OK] Active account = $ACCOUNT" -ForegroundColor Green
Write-Host "[OK] Project        = $PROJECT" -ForegroundColor Green

# 4. Confirm this account can actually see the project.
Write-Host "[*] Confirming project access..." -ForegroundColor Yellow
$check = gcloud projects describe $PROJECT --format "value(projectId)" 2>$null
if ($check -eq $PROJECT) {
    Write-Host "[OK] Access to $PROJECT confirmed." -ForegroundColor Green
} else {
    Write-Host "[!] Signed in, but this account cannot access $PROJECT." -ForegroundColor Yellow
    Write-Host "    Confirm $ACCOUNT has a role on that project, or pick a different host." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Ready. Two ways forward:" -ForegroundColor Cyan
Write-Host "  * Easiest: switch back to Claude and reply 'done' - it runs setup + deploy for you." -ForegroundColor Gray
Write-Host "  * Or deploy yourself once Cloud SQL exists (see deploy\DEPLOY.md):" -ForegroundColor Gray
Write-Host "      .\deploy\deploy.ps1 -CloudSqlInstance ""agora-data-driven:asia-southeast1:sentinel-db""" -ForegroundColor Gray
Write-Host ""
