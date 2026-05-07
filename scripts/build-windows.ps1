param(
    [string]$Version = "0.3.0",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseName = "CFS-Price-Compare-v$Version-windows"
$PyInstallerCliOutput = Join-Path $RepoRoot "dist\pc_pricer"
$PyInstallerGuiOutput = Join-Path $RepoRoot "dist\pc_pricer_gui"
$ReleaseDir = Join-Path $RepoRoot "dist\$ReleaseName"
$ZipPath = Join-Path $RepoRoot "dist\$ReleaseName.zip"

Set-Location $RepoRoot

if (-not $SkipDependencyInstall) {
    python -m pip install -r requirements-build.txt
    python -m pip install -e ".[gui]"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name pc_pricer `
    --specpath build `
    pc_pricer\cli.py

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name pc_pricer_gui `
    --specpath build `
    pc_pricer\gui.py

if (Test-Path $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
}

New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
Copy-Item -Path (Join-Path $PyInstallerGuiOutput "*") -Destination $ReleaseDir -Recurse
$CliInternal = Join-Path $PyInstallerCliOutput "_internal"
if (Test-Path $CliInternal) {
    Copy-Item -Path (Join-Path $CliInternal "*") -Destination (Join-Path $ReleaseDir "_internal") -Recurse -Force
}
Copy-Item -Path (Join-Path $PyInstallerCliOutput "pc_pricer.exe") -Destination $ReleaseDir -Force
Copy-Item -Path "config.yaml" -Destination $ReleaseDir
Copy-Item -Path ".env.example" -Destination $ReleaseDir
Copy-Item -Path "README-QUICKSTART.txt" -Destination $ReleaseDir

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath

Write-Host "Built release folder: $ReleaseDir"
Write-Host "Built release zip:    $ZipPath"
