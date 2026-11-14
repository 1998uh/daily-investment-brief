# Daily report-input preparation for the 08:00 brief window.
# Catch the 07:30-08:00 tail for WeChat/Douyin, rebuild sources/<date> from
# SQLite, then produce the Codex article pack. Report writing stays manual.
#
# Manual prep utility. Not registered as a scheduled task; the 08:00
# DailyInvestmentBrief-Email task performs these steps itself.
# Logs: data/logs/daily-prepare-<date>.log

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Continue"
Set-Location $Root

$logDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "daily-prepare-$Date.log"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Invoke-Step([string]$Name, [scriptblock]$Body) {
    Write-Log "START $Name"
    $global:LASTEXITCODE = 0
    try {
        & $Body 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding utf8 }
        Write-Log "END   $Name (exit $LASTEXITCODE)"
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-Log "FAIL  $Name : $($_.Exception.Message)"
        return $false
    }
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$archive = Join-Path $Root "sources\_raw\$Date"

Write-Log "daily prepare start (date=$Date)"

# Share the prepare mutex with the 07:30 collect and 08:00 email jobs.
$mutex = New-Object System.Threading.Mutex($false, "Global\DailyInvestmentBrief-Prepare")
$owned = $false
try {
    try {
        $owned = $mutex.WaitOne([TimeSpan]::FromMinutes(20))
    } catch [System.Threading.AbandonedMutexException] {
        $owned = $true
    }
    if (-not $owned) {
        Write-Log "another preparation run holds the lock; exiting"
        exit 1
    }

    Invoke-Step "collect wechat tail" {
        & $python -m pipeline.cli collect --date $Date --platform wechat --out-dir $archive
    } | Out-Null

    Invoke-Step "collect douyin tail" {
        & $python -m pipeline.cli collect --date $Date --platform douyin --out-dir $archive
    } | Out-Null

    Invoke-Step "materialize" {
        & $python -m pipeline.cli materialize --date $Date
    } | Out-Null

    Invoke-Step "prepare" {
        & $python -m pipeline.cli prepare --date $Date
    } | Out-Null

    Write-Log "daily prepare finished"
} finally {
    if ($owned) { try { $mutex.ReleaseMutex() } catch { } }
    try { $mutex.Dispose() } catch { }
}
