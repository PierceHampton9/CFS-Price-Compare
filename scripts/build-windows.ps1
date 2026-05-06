param(
    [string]$Version = "0.1.1",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseName = "CFS-Price-Compare-v$Version-windows"
$PyInstallerOutput = Join-Path $RepoRoot "dist\pc_pricer"
$ReleaseDir = Join-Path $RepoRoot "dist\$ReleaseName"
$ZipPath = Join-Path $RepoRoot "dist\$ReleaseName.zip"

Set-Location $RepoRoot

if (-not $SkipDependencyInstall) {
    python -m pip install -r requirements-build.txt
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name pc_pricer `
    --specpath build `
    pc_pricer\cli.py

if (Test-Path $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
}

New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
Copy-Item -Path (Join-Path $PyInstallerOutput "*") -Destination $ReleaseDir -Recurse
Copy-Item -Path "config.yaml" -Destination $ReleaseDir
Copy-Item -Path ".env.example" -Destination $ReleaseDir
Copy-Item -Path "README-QUICKSTART.txt" -Destination $ReleaseDir

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath

Write-Host "Built release folder: $ReleaseDir"
Write-Host "Built release zip:    $ZipPath"
