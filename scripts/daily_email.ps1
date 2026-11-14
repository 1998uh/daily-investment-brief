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
    [switch]$SkipPrepare
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

function Get-FailureDetail {
    $parts = @()
    if (Test-Path $claudeLog) { $parts += (Get-Content $claudeLog -Tail 40 -Encoding utf8) }
    if (Test-Path $log) { $parts += (Get-Content $log -Tail 30 -Encoding utf8) }
    $detail = ($parts -join "`n")
    if ($detail.Length -gt 2000) {
        $detail = $detail.Substring($detail.Length - 2000)
    }
    return $detail
}

function Send-Failure([string]$Stage) {
    if ($DryRun) {
        Write-Log "DRY-RUN failure email: stage=$Stage"
        return
    }
    $detail = Get-FailureDetail
    $failureArgs = @("-m", "pipeline.cli", "send-email", "--date", $Date, "--failure-stage", $Stage, "--failure-detail", $detail)
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
            $prompt = @"
你正在无人值守模式下生成 $Date 的投资日报。

必读文件（按顺序完整读取）：
- AGENTS.md
- skill/daily-investment-brief/SKILL.md
- templates/direct_brief_prompt.md
- reports/$Date/codex-context.json
- reports/$Date/article-pack.md

无人值守覆盖：
- 采集、social-health、materialize、prepare 已由外层脚本完成。不要运行任何命令，不要尝试自行采集或重建目录。
- 只写 reports/$Date/daily-brief.md，不要生成 HTML。
- 不要调用 generate、fallback 或任何外部模型。

当日各平台文章数：$countsText。
若任一平台为 0，仍按用户长期授权正常写作，但必须在标题元信息和数据覆盖章节显著标注“数据源不完整”，并列出缺失平台；不得写成“当日无观点”或“市场静默”。

完成后只输出一行 DONE。
"@
            $job = Start-Job -ScriptBlock {
                param($projectRoot, $writerPrompt)
                Set-Location $projectRoot
                claude -p $writerPrompt --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Glob,Grep" --output-format text 2>&1
            } -ArgumentList $Root, $prompt
            $finished = Wait-Job $job -Timeout 1200
            if ($finished) {
                Receive-Job $job | Out-File -FilePath $claudeLog -Encoding utf8
                Write-Log "headless writer finished"
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
