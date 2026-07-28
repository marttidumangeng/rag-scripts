param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("apply", "status", "rollback")]
    [string]$Action,

    # conservative: keep SYSTEM+WORKLOAD logging, narrow monitoring to SYSTEM,POD,DEPLOYMENT,HPA
    # aggressive  : drop to SYSTEM-only logging, SYSTEM-only monitoring (minimal observability)
    [ValidateSet("conservative", "aggressive")]
    [string]$Profile = "conservative",

    [string]$ProjectId = "robotaigeek-core",
    [string]$ClusterName = "rag-cluster-prod",
    [string]$Region = "asia-southeast1",

    # Required for apply and rollback to prevent accidental prod changes.
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Prevent stderr warnings from native commands (for example gcloud quota warnings)
# from being treated as terminating PowerShell errors.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Write-Step {
    param([string]$Message)
    Write-Host "[prod-telemetry-cost] $Message" -ForegroundColor Cyan
}

function Ensure-Tool {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required tool '$Name' is not installed or not in PATH."
    }
}

function Run-GCloud {
    param(
        [string]$Cmd,
        [switch]$AllowFailure
    )

    Write-Step $Cmd

    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = Invoke-Expression $Cmd 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }

    if ($output) {
        $output | Out-Host
    }

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "Command failed (exit code $exitCode): $Cmd"
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output   = ($output | Out-String)
    }
}

function Assert-ForceRequired {
    if (-not $Force) {
        Write-Host ""
        Write-Host "================================================================" -ForegroundColor Red
        Write-Host "  PROD CLUSTER CHANGE: -Action $Action" -ForegroundColor Red
        Write-Host "  Target cluster : $ClusterName ($Region)" -ForegroundColor Red
        Write-Host "  Project        : $ProjectId" -ForegroundColor Red
        Write-Host ""
        Write-Host "  This will modify PRODUCTION telemetry configuration." -ForegroundColor Yellow
        Write-Host "  Re-run with -Force to confirm." -ForegroundColor Yellow
        Write-Host "================================================================" -ForegroundColor Red
        Write-Host ""
        throw "Aborted. -Force flag is required to run '$Action' against prod."
    }
}

function Set-ProjectAndCheckCluster {
    Run-GCloud "gcloud config set project $ProjectId" | Out-Null
    $cluster = gcloud container clusters list --project $ProjectId --filter="name=$ClusterName AND location=$Region" --format="value(name)"
    if ([string]::IsNullOrWhiteSpace($cluster)) {
        throw "Cluster '$ClusterName' in region '$Region' not found in project '$ProjectId'."
    }
    Write-Step "Cluster confirmed: $ClusterName ($Region)"
}

function Get-ClusterTelemetryConfig {
    $json = gcloud container clusters describe $ClusterName --region $Region --project $ProjectId --format="json(loggingConfig,monitoringConfig)"
    return ($json | ConvertFrom-Json)
}

function Show-TelemetryStatus {
    $cfg = Get-ClusterTelemetryConfig

    $logging = @()
    if ($cfg.loggingConfig -and $cfg.loggingConfig.componentConfig -and $cfg.loggingConfig.componentConfig.enableComponents) {
        $logging = $cfg.loggingConfig.componentConfig.enableComponents
    }

    $monitoring = @()
    if ($cfg.monitoringConfig -and $cfg.monitoringConfig.componentConfig -and $cfg.monitoringConfig.componentConfig.enableComponents) {
        $monitoring = $cfg.monitoringConfig.componentConfig.enableComponents
    }

    $managedProm = $false
    if ($cfg.monitoringConfig -and $cfg.monitoringConfig.managedPrometheusConfig) {
        $managedProm = [bool]$cfg.monitoringConfig.managedPrometheusConfig.enabled
    }

    Write-Host ""
    Write-Host "Telemetry status for $ClusterName" -ForegroundColor Yellow
    Write-Host "Logging components   : $($logging -join ', ')"
    Write-Host "Monitoring components: $($monitoring -join ', ')"
    Write-Host "Managed Prometheus   : $managedProm"
}

function Apply-ConservativeProfile {
    # Logging is left at SYSTEM+WORKLOAD (already the prod default — no change needed).
    # Monitoring: we WANT to narrow it, but GKE Autopilot rejects granular component selection (POD, DEPLOYMENT, etc.).
    # Because we cannot safely drop all workload monitoring (which aggressive profile does), we make NO change to monitoring here.
    Write-Step "Conservative profile: Prod observability preserved. No cluster-level reductions applied because Autopilot prevents granular monitoring cuts."

    Write-Step "Attempting to disable managed Prometheus"
    $promResult = Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --disable-managed-prometheus" -AllowFailure

    if ($promResult.ExitCode -ne 0) {
        Write-Host "[prod-telemetry-cost] WARNING: Managed Prometheus cannot be disabled on this Autopilot cluster version. Keeping it enabled." -ForegroundColor Yellow
    }

    Write-Step "Conservative profile applied (no base metrics dropped)."
}

function Apply-AggressiveProfile {
    # Drops to SYSTEM-only logging (no workload logs) and SYSTEM-only monitoring.
    # Use only if you accept minimal observability on prod.
    Write-Host "[prod-telemetry-cost] WARNING: Aggressive profile drops workload logs. Prod app/error logs will NOT be available in Cloud Logging." -ForegroundColor Red

    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --logging=SYSTEM" | Out-Null
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --monitoring=SYSTEM" | Out-Null

    Write-Step "Attempting to disable managed Prometheus"
    $promResult = Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --disable-managed-prometheus" -AllowFailure

    if ($promResult.ExitCode -ne 0) {
        Write-Host "[prod-telemetry-cost] WARNING: Managed Prometheus cannot be disabled on this Autopilot cluster version. Keeping it enabled." -ForegroundColor Yellow
    }

    Write-Step "Aggressive profile applied."
}

function Apply-RollbackProfile {
    Write-Step "Restoring full prod telemetry profile"

    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --logging=SYSTEM,WORKLOAD" | Out-Null
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --monitoring=SYSTEM,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA,JOBSET,CADVISOR,KUBELET,DCGM" | Out-Null

    Write-Step "Re-enabling managed Prometheus"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --enable-managed-prometheus" | Out-Null

    Write-Step "Rollback profile applied."
}

# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
Ensure-Tool -Name "gcloud"

if ($Action -in @("apply", "rollback")) {
    Assert-ForceRequired
}

Set-ProjectAndCheckCluster

switch ($Action) {
    "status" {
        Show-TelemetryStatus
    }
    "apply" {
        if ($Profile -eq "conservative") {
            Apply-ConservativeProfile
        }
        else {
            Apply-AggressiveProfile
        }
        Show-TelemetryStatus
        Write-Step "Next: validate alerts/dashboards and monitor cost trend at 24h, 72h, and 7d."
    }
    "rollback" {
        Apply-RollbackProfile
        Show-TelemetryStatus
    }
}
