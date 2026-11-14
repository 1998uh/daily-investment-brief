# Daily brief generation + email delivery for the 08:00 window.
# Runs collection, materialize, prepare, native writing, HTML rendering, the
# content gate, and QQ SMTP delivery. Sends a failure notice on any failure.
#
# Registered by schtasks (task name: DailyInvestmentBrief-Email).
# Logs: data/logs/daily-email-<date>.log and daily-email-claude-<date>.log

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$Force,
    [switch]$DryRun,
    [switch]$SkipPrepare,
    [switch]$SkipSend
)

$ErrorActionPreference = "Continue"
Set-Location $Root

$logDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "daily-email-$Date.log"
$claudeLog = Join-Path $logDir "daily-email-claude-$Date.log"
$reportDir = Join-Path $Root "reports\$Date"
$mdPath = Join-Path $reportDir "daily-brief.md"
$htmlPath = Join-Path $reportDir "daily-brief.html"
$archive = Join-Path $Root "sources\_raw\$Date"
$python = Join-Path $Root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Invoke-Step([string]$Name, [scriptblock]$Body) {
    Write-Log "START $Name"
    $global:LASTEXITCODE = 0
    try {
        & $Body 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding utf8 }
        $code = $LASTEXITCODE
        Write-Log "END   $Name (exit $code)"
        return $code
    } catch {
        Write-Log "FAIL  $Name : $($_.Exception.Message)"
        return 1
    }
}

function Send-Failure([string]$Stage) {
    if ($DryRun) {
        Write-Log "DRY-RUN failure email: stage=$Stage"
        return
    }
    # Pass log paths, not the multi-line log text: PowerShell splits a long
    # detail string into multiple native arguments and argparse rejects it.
    $failureArgs = @("-m", "pipeline.cli", "send-email", "--date", $Date, "--failure-stage", $Stage, "--failure-log", $log)
    if (Test-Path $claudeLog) { $failureArgs += @("--failure-log", $claudeLog) }
    & $python @failureArgs 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding utf8 }
    Write-Log "Failure email attempt finished (exit $LASTEXITCODE)"
}

# Only one prep/write run may touch sources/<date> and reports/<date> at a time.
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

    Write-Log "daily email start (date=$Date dry_run=$DryRun force=$Force)"
    $startedAt = Get-Date

    if (-not $SkipPrepare) {
        # social-health is diagnostic; a non-zero result means partial data,
        # which is allowed and must be marked in the report by the writer.
        $health = Invoke-Step "social-health" { & $python -m pipeline.cli social-health }
        Write-Log "social-health exit=$health"

        Invoke-Step "collect wechat tail" {
            & $python -m pipeline.cli collect --date $Date --platform wechat --out-dir $archive
        } | Out-Null
        Invoke-Step "collect douyin tail" {
            & $python -m pipeline.cli collect --date $Date --platform douyin --out-dir $archive
        } | Out-Null

        $materialized = Invoke-Step "materialize" {
            & $python -m pipeline.cli materialize --date $Date
        }
        if ($materialized -ne 0) {
            Write-Log "materialize reported incomplete sources; continuing under standing authorization"
        }

        $prepared = Invoke-Step "prepare" {
            & $python -m pipeline.cli prepare --date $Date
        }
        if ($prepared -ne 0) {
            Send-Failure "prepare"
            exit 1
        }
    }

    # Count today's articles per platform for the prompt and the failure notice.
    $slugToName = @{
        "xueqiu" = "雪球"
        "weibo"  = "微博"
        "wechat" = "微信公众号"
        "douyin" = "抖音"
    }
    $counts = [ordered]@{ "雪球" = 0; "微博" = 0; "微信公众号" = 0; "抖音" = 0 }
    $sourceDir = Join-Path $Root "sources\$Date"
    if (Test-Path $sourceDir) {
        Get-ChildItem -Path $sourceDir -Filter "*.md" -ErrorAction SilentlyContinue | ForEach-Object {
            $slug = ($_.Name -split "-")[0]
            if ($slugToName.ContainsKey($slug)) {
                $counts[$slugToName[$slug]] = $counts[$slugToName[$slug]] + 1
            }
        }
    }
    $countsText = ($counts.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value) 篇" }) -join "、"

    $reuse = $false
    if (-not $Force -and (Test-Path $mdPath)) {
        $mdTime = (Get-Item $mdPath).LastWriteTime
        if ($mdTime -ge (Get-Date $Date).Date) {
            $reuse = $true
            Write-Log "reusing existing report written at $mdTime"
        }
    }

    if (-not $reuse) {
        if ($DryRun) {
            Write-Log "DRY-RUN: skipping headless writing"
        } else {
            $promptTemplate = Join-Path $Root "templates\headless_daily_brief_prompt.md"
            if (-not (Test-Path $promptTemplate)) {
                Send-Failure "prompt-template-missing"
                exit 1
            }
            $prompt = (Get-Content -Raw -Encoding utf8 $promptTemplate).Replace("{{DATE}}", $Date).Replace("{{COUNTS}}", $countsText)
            # Prefer the .cmd shim: Start-Job uses a fresh session whose
            # execution policy may block the claude.ps1 wrapper.
            $claudeCmd = (Get-Command claude.cmd -ErrorAction SilentlyContinue).Source
            if (-not $claudeCmd) { $claudeCmd = "claude" }
            $job = Start-Job -ScriptBlock {
                param($projectRoot, $writerPrompt, $claudePath)
                Set-Location $projectRoot
                $writerOutput = & $claudePath -p $writerPrompt --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Glob,Grep" --output-format text 2>&1
                $writerExit = $LASTEXITCODE
                $writerOutput
                "__CLAUDE_EXIT__=$writerExit"
            } -ArgumentList $Root, $prompt, $claudeCmd
            $finished = Wait-Job $job -Timeout 1200
            $claudeExit = -1
            $claudeText = ""
            if ($finished) {
                $writerOutput = Receive-Job $job
                $writerOutput | Out-File -FilePath $claudeLog -Encoding utf8
                $claudeText = ($writerOutput | Out-String)
                $exitMatch = [regex]::Match($claudeText, "__CLAUDE_EXIT__=(-?\d+)")
                if ($exitMatch.Success) { $claudeExit = [int]$exitMatch.Groups[1].Value }
                Write-Log "headless writer finished (exit=$claudeExit)"
            } else {
                Stop-Job $job -ErrorAction SilentlyContinue
                Receive-Job $job -ErrorAction SilentlyContinue | Out-File -FilePath $claudeLog -Encoding utf8 -Append
                Write-Log "headless writer timed out after 20 minutes"
            }
            Remove-Job $job -Force -ErrorAction SilentlyContinue

            if (-not $finished) {
                Send-Failure "headless-timeout"
                exit 1
            }
            if ($claudeExit -ne 0) {
                Send-Failure "headless-nonzero"
                exit 1
            }
            if ($claudeText -notmatch "DONE") {
                Write-Log "headless writer did not print DONE; relying on exit code, mtime and content gate"
            }
            if (-not (Test-Path $mdPath)) {
                Send-Failure "headless-missing-report"
                exit 1
            }
            $mdItem = Get-Item $mdPath
            if ($mdItem.LastWriteTime -lt $startedAt -or $mdItem.Length -lt 1000) {
                Send-Failure "headless-invalid-report"
                exit 1
            }
        }
    }

    if (-not (Test-Path $mdPath)) {
        Write-Log "no daily-brief.md available"
        if ($DryRun) { exit 0 }
        Send-Failure "missing-report"
        exit 1
    }

    $rendered = Invoke-Step "render-html" {
        & $python -m pipeline.cli render-html --date $Date --check
    }
    if ($rendered -ne 0) {
        Send-Failure "content-gate"
        exit 1
    }

    if ($SkipSend) {
        Write-Log "SKIP SEND: report generated, email not sent"
        exit 0
    }

    if ($DryRun) {
        Write-Log "DRY-RUN: skipping email send"
        exit 0
    }

    $sendArgs = @("-m", "pipeline.cli", "send-email", "--date", $Date)
    if ($Force) { $sendArgs += "--force" }
    $sent = Invoke-Step "send-email" { & $python @sendArgs }
    if ($sent -ne 0) {
        Write-Log "email send failed"
        exit 1
    }

    Write-Log "daily email finished"
    exit 0
} finally {
    if ($owned) {
        try { $mutex.ReleaseMutex() } catch { }
    }
    try { $mutex.Dispose() } catch { }
}
