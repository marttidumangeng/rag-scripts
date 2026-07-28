param(
    [string]$ProjectId = "robotaigeek-core",
    [string]$ClusterName = "rag-cluster-dev",
    [string]$Region = "asia-southeast1",

    [string]$Deployment = "robotaigeek-dev",
    [string]$Container = "django-app",
    [string]$Namespace = "default",

    [int]$Iterations = 20,
    [int]$DelaySeconds = 1,
    [int]$TimeoutSeconds = 20,

    [string[]]$Urls = @(
        "https://ragadmin-dev.robotaigeek.com/api/v1/forums/topics/?limit=5",
        "https://ragadmin-dev.robotaigeek.com/api/v1/content/videos/?limit=5"
    ),

    [bool]$EnsureClusterCredentials = $true,
    [bool]$CaptureLogsOnFailure = $true,
    [int]$LogLookbackMinutes = 15,
    [int]$LogTailLines = 200,

    [string]$OutputCsv = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[probe-dev-endpoints] $Message" -ForegroundColor Cyan
}

function Ensure-Tool {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required tool '$Name' is not installed or not in PATH."
    }
}

function Ensure-ClusterAuth {
    Write-Step "Ensuring kube credentials for $ClusterName in $Region"
    gcloud container clusters get-credentials $ClusterName --region $Region --project $ProjectId | Out-Null
}

function Invoke-Probe {
    param(
        [string]$Url,
        [string]$DebugId,
        [int]$TimeoutSec
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $statusCode = -1
    $errorText = ""

    try {
        $headers = @{
            "X-Debug-Id" = $DebugId
            "Cache-Control" = "no-cache"
            "Pragma" = "no-cache"
        }

        $response = Invoke-WebRequest -Uri $Url -Method GET -Headers $headers -TimeoutSec $TimeoutSec -UseBasicParsing
        $statusCode = [int]$response.StatusCode
    }
    catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        else {
            $statusCode = -1
        }

        $errorText = $_.Exception.Message
    }
    finally {
        $sw.Stop()
    }

    return [PSCustomObject]@{
        StatusCode = $statusCode
        DurationMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
        Error = $errorText
    }
}

function Capture-FailureEvidence {
    param(
        [string]$Url,
        [string]$DebugId,
        [int]$StatusCode,
        [string]$ErrorText
    )

    Write-Host ""
    Write-Host "--- Failure Evidence ---" -ForegroundColor Yellow
    Write-Host "URL      : $Url"
    Write-Host "Debug ID : $DebugId"
    Write-Host "Status   : $StatusCode"
    if (-not [string]::IsNullOrWhiteSpace($ErrorText)) {
        Write-Host "Error    : $ErrorText"
    }

    if (-not $CaptureLogsOnFailure) {
        return
    }

    try {
        $sinceArg = "--since=${LogLookbackMinutes}m"
        Write-Step "Fetching pod logs for $Namespace/deployment/$Deployment container=$Container"
        kubectl logs -n $Namespace deployment/$Deployment -c $Container $sinceArg --tail=$LogTailLines
    }
    catch {
        Write-Host "[probe-dev-endpoints] Failed to fetch logs: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Ensure-Tool -Name "gcloud"
Ensure-Tool -Name "kubectl"

if ($Iterations -lt 1) {
    throw "Iterations must be >= 1"
}
if ($DelaySeconds -lt 0) {
    throw "DelaySeconds must be >= 0"
}
if ($TimeoutSeconds -lt 1) {
    throw "TimeoutSeconds must be >= 1"
}
if (-not $Urls -or $Urls.Count -eq 0) {
    throw "Provide at least one URL via -Urls"
}

if ($EnsureClusterCredentials) {
    Ensure-ClusterAuth
}

$results = New-Object System.Collections.Generic.List[object]
$firstFailureCaptured = $false

foreach ($url in $Urls) {
    Write-Host ""
    Write-Host "### Probing $url" -ForegroundColor Green

    for ($i = 1; $i -le $Iterations; $i++) {
        $debugId = "probe-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))-$i"
        $probe = Invoke-Probe -Url $url -DebugId $debugId -TimeoutSec $TimeoutSeconds

        $row = [PSCustomObject]@{
            TimestampUtc = [DateTime]::UtcNow.ToString("o")
            Url = $url
            Iteration = $i
            DebugId = $debugId
            StatusCode = $probe.StatusCode
            DurationMs = $probe.DurationMs
            Error = $probe.Error
        }
        $results.Add($row)

        $statusLabel = if ($probe.StatusCode -ge 200 -and $probe.StatusCode -lt 300) { "OK" } else { "FAIL" }
        $color = if ($statusLabel -eq "OK") { "Gray" } else { "Red" }

        Write-Host ("try {0,2} -> {1} ({2} ms) [{3}]" -f $i, $probe.StatusCode, $probe.DurationMs, $debugId) -ForegroundColor $color

        if (($probe.StatusCode -lt 200 -or $probe.StatusCode -ge 300) -and -not $firstFailureCaptured) {
            $firstFailureCaptured = $true
            Capture-FailureEvidence -Url $url -DebugId $debugId -StatusCode $probe.StatusCode -ErrorText $probe.Error
        }

        if ($i -lt $Iterations -and $DelaySeconds -gt 0) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Yellow

$grouped = $results | Group-Object Url
foreach ($g in $grouped) {
    $total = [int]$g.Count
    $ok = @($g.Group | Where-Object { $_.StatusCode -ge 200 -and $_.StatusCode -lt 300 }).Count
    $fail = $total - $ok
    $avgMs = [math]::Round((($g.Group | Measure-Object DurationMs -Average).Average), 2)
    $p95Window = [math]::Max([int][math]::Ceiling($total * 0.05), 1)
    $p95 = (($g.Group | Sort-Object DurationMs | Select-Object -Last $p95Window | Measure-Object DurationMs -Maximum).Maximum)

    Write-Host "URL        : $($g.Name)"
    Write-Host "Total      : $total"
    Write-Host "OK         : $ok"
    Write-Host "Fail       : $fail"
    Write-Host "Avg ms     : $avgMs"
    Write-Host "P95 approx : $([math]::Round($p95, 2))"
    Write-Host ""
}

if (-not [string]::IsNullOrWhiteSpace($OutputCsv)) {
    $results | Export-Csv -Path $OutputCsv -NoTypeInformation -Encoding UTF8
    Write-Step "Wrote probe results to $OutputCsv"
}

$totalFailCount = ($results | Where-Object { $_.StatusCode -lt 200 -or $_.StatusCode -ge 300 }).Count
if ($totalFailCount -gt 0) {
    Write-Host "Completed with failures: $totalFailCount non-2xx responses detected." -ForegroundColor Yellow
    exit 1
}

Write-Host "Completed successfully: all probes returned 2xx." -ForegroundColor Green
exit 0
