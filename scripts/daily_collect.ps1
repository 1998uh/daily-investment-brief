# Daily background collection for WeChat / Douyin.
# Xueqiu and Weibo are covered continuously by the Docker social-collector daemon.
#
# Registered by schtasks (task name: DailyInvestmentBrief-Collect).
# Logs: data/logs/daily-collect-<date>.log

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Continue"
Set-Location $Root

$logDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "daily-collect-$Date.log"

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

$dockerDesktop = "D:\Docker\DockerDesktop\frontend\Docker Desktop.exe"

function Test-LocalPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $task.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($task)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

Write-Log "daily collection start (date=$Date)"

# Docker Desktop forwards the host system proxy. If the proxy process is not up,
# every container HTTPS request fails with TLS EOF, so start it first.
$proxyPort = 0
$proxyServer = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings").ProxyServer
if ($proxyServer -match '127\.0\.0\.1:(\d+)') {
    $proxyPort = [int]$Matches[1]
} elseif ($proxyServer -match ':(\d+)$') {
    $proxyPort = [int]$Matches[1]
}
if ($proxyPort -gt 0 -and -not (Test-LocalPort $proxyPort)) {
    Write-Log "system proxy 127.0.0.1:$proxyPort not listening; starting Clash Verge"
    $verge = "C:\Program Files\Clash Verge\Clash Verge.exe"
    if (Test-Path $verge) { Start-Process -FilePath $verge | Out-Null }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        if (Test-LocalPort $proxyPort) { break }
    }
    if (-not (Test-LocalPort $proxyPort)) {
        Write-Log "system proxy still not listening; container requests may fail"
    }
}

# Make sure the Docker engine is up; Docker Desktop is set to auto-start on login,
# but the scheduled task should not silently skip collection if it is still booting.
docker info --format "{{.ServerVersion}}" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Log "docker engine not ready; starting Docker Desktop"
    if (Test-Path $dockerDesktop) { Start-Process -FilePath $dockerDesktop | Out-Null }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 5
        docker info --format "{{.ServerVersion}}" *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { Write-Log "docker engine still not ready after 5 minutes" }
}

# Idempotent: starts the daemon if it is stopped, leaves a healthy one alone.
Invoke-Step "docker compose up social-collector" { docker compose up -d social-collector } | Out-Null

$python = Join-Path $Root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

# Write to the natural-day archive only. The formal sources/<date> directory is
# rebuilt from SQLite by `materialize` as part of the "生成日报" flow.
$archive = Join-Path $Root "sources\_raw\$Date"

Invoke-Step "collect wechat" {
    & $python -m pipeline.cli collect --date $Date --platform wechat --out-dir $archive
} | Out-Null

Invoke-Step "collect douyin" {
    & $python -m pipeline.cli collect --date $Date --platform douyin --out-dir $archive
} | Out-Null

Invoke-Step "container status" { docker compose ps } | Out-Null

Write-Log "daily collection finished"
