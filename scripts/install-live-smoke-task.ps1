param(
    [string]$TaskName = "CFS Price Compare Live Smoke",
    [string]$OutputPath = "",
    [string]$ConfigPath = "",
    [string]$Time = "08:00",
    [switch]$Daily
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $OutputPath) {
    $OutputPath = Join-Path $repoRoot "smoke-reports"
}

$python = (Get-Command python).Source
$arguments = @("-m", "pc_pricer.live_smoke", "--output", "`"$OutputPath`"")
if ($ConfigPath) {
    $arguments += @("--config", "`"$ConfigPath`"")
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument ($arguments -join " ") `
    -WorkingDirectory $repoRoot

$start = [datetime]::ParseExact($Time, "HH:mm", $null)
if ($Daily) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $start
} else {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $start
}

$description = "Runs python -m pc_pricer.live_smoke for live eBay/Refurb.io/Amazon smoke validation."
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Description $description `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Working directory: $repoRoot"
Write-Host "Command: $python $($arguments -join ' ')"
Write-Host "Output path: $OutputPath"
