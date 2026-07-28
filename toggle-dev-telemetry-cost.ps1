param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("apply", "status", "rollback")]
    [string]$Action,

    [string]$ProjectId = "robotaigeek-core",
    [string]$ClusterName = "rag-cluster-dev",
    [string]$Region = "asia-southeast1"
)

$ErrorActionPreference = "Stop"

# Prevent stderr warnings from native commands (for example gcloud quota warnings)
# from being treated as terminating PowerShell errors.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Write-Step {
    param([string]$Message)
    Write-Host "[dev-telemetry-cost] $Message" -ForegroundColor Cyan
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
        Output = ($output | Out-String)
    }
}

function Set-ProjectAndCheckCluster {
    Run-GCloud "gcloud config set project $ProjectId"
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

function Apply-CostCutConfig {
    Write-Step "Applying dev logging=SYSTEM"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --logging=SYSTEM" | Out-Null

    Write-Step "Applying dev monitoring=SYSTEM"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --monitoring=SYSTEM" | Out-Null

    Write-Step "Attempting to disable managed Prometheus"
    $promResult = Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --disable-managed-prometheus" -AllowFailure

    if ($promResult.ExitCode -ne 0) {
        Write-Host "[dev-telemetry-cost] WARNING: Managed Prometheus cannot be disabled on this Autopilot cluster version. Keeping it enabled." -ForegroundColor Yellow
    }

    Write-Step "Cost-cut telemetry profile applied."
}

function Apply-RollbackConfig {
    Write-Step "Restoring dev logging to SYSTEM+WORKLOAD"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --logging=SYSTEM,WORKLOAD"

    Write-Step "Restoring broad monitoring component set"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --monitoring=SYSTEM,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA,JOBSET,CADVISOR,KUBELET,DCGM"

    Write-Step "Re-enabling managed Prometheus"
    Run-GCloud "gcloud container clusters update $ClusterName --region $Region --project $ProjectId --enable-managed-prometheus"

    Write-Step "Rollback telemetry profile applied."
}

Ensure-Tool -Name "gcloud"

Set-ProjectAndCheckCluster

switch ($Action) {
    "apply" {
        Apply-CostCutConfig
        Show-TelemetryStatus
        Write-Step "Next: review Logging/Monitoring cost trend at 24h, 72h, and 7d."
    }
    "status" {
        Show-TelemetryStatus
    }
    "rollback" {
        Apply-RollbackConfig
        Show-TelemetryStatus
    }
}
