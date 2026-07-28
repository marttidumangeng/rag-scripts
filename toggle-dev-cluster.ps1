param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("off", "on", "status")]
    [string]$Action,

    [ValidateSet("workloads", "cluster")]
    [string]$Mode = "workloads",

    [string]$ProjectId = "robotaigeek-core",
    [string]$ClusterName = "rag-cluster-dev",
    [string]$Region = "asia-southeast1",

    [string[]]$Namespaces = @("default", "rag-web-dev"),

    [string]$StateFile = "",

    [bool]$DeleteIngress = $true,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[dev-cluster-toggle] $Message" -ForegroundColor Cyan
}

function Ensure-Tool {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required tool '$Name' is not installed or not in PATH."
    }
}

function Run-Cmd {
    param([string]$Command)
    Write-Step $Command
    Invoke-Expression $Command
}

function Ensure-ClusterCredentials {
    Write-Step "Ensuring kube credentials for $ClusterName in $Region"
    Run-Cmd "gcloud container clusters get-credentials $ClusterName --region $Region --project $ProjectId"
}

function Get-Deployments {
    param([string]$Namespace)

    $json = kubectl get deployments -n $Namespace -o json | ConvertFrom-Json
    $result = @()

    foreach ($item in $json.items) {
        $result += [PSCustomObject]@{
            namespace = $Namespace
            name = $item.metadata.name
            replicas = if ($null -eq $item.spec.replicas) { 1 } else { [int]$item.spec.replicas }
        }
    }

    return $result
}

function Get-Hpas {
    param([string]$Namespace)

    $json = kubectl get hpa -n $Namespace -o json | ConvertFrom-Json
    $result = @()

    foreach ($item in $json.items) {
        $result += [PSCustomObject]@{
            namespace = $Namespace
            name = $item.metadata.name
        }
    }

    return $result
}

function Get-Ingresses {
    param([string]$Namespace)

    $json = kubectl get ingress -n $Namespace -o json | ConvertFrom-Json
    $result = @()

    foreach ($item in $json.items) {
        $result += [PSCustomObject]@{
            namespace = $Namespace
            name = $item.metadata.name
        }
    }

    return $result
}

function Save-State {
    param(
        [string[]]$TargetNamespaces,
        [string]$Path
    )

    $state = [ordered]@{
        projectId = $ProjectId
        clusterName = $ClusterName
        region = $Region
        savedAtUtc = [DateTime]::UtcNow.ToString("o")
        namespaces = @()
    }

    foreach ($ns in $TargetNamespaces) {
        $state.namespaces += [ordered]@{
            name = $ns
            deployments = @(Get-Deployments -Namespace $ns)
            hpas = @(Get-Hpas -Namespace $ns)
            ingresses = @(Get-Ingresses -Namespace $ns)
        }
    }

    $dir = Split-Path -Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }

    $state | ConvertTo-Json -Depth 8 | Set-Content -Path $Path -Encoding UTF8
    Write-Step "State saved to $Path"
}

function Restore-ReplicaState {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "State file not found: $Path"
    }

    $state = Get-Content -Path $Path -Raw | ConvertFrom-Json

    foreach ($nsState in $state.namespaces) {
        foreach ($dep in $nsState.deployments) {
            Write-Step "Restoring deployment $($dep.namespace)/$($dep.name) replicas=$($dep.replicas)"
            kubectl scale deployment $dep.name -n $dep.namespace --replicas=$($dep.replicas) | Out-Null
        }
    }
}

function Restore-DefaultReplicaState {
    $defaults = @(
        [PSCustomObject]@{ namespace = "default"; name = "robotaigeek-dev"; replicas = 1 },
        [PSCustomObject]@{ namespace = "default"; name = "robotaigeek-mcp-dev"; replicas = 1 },
        [PSCustomObject]@{ namespace = "rag-web-dev"; name = "robotaigeek-web"; replicas = 1 }
    )

    Write-Step "State file not found. Applying default dev replica counts."
    foreach ($dep in $defaults) {
        Write-Step "Restoring default deployment $($dep.namespace)/$($dep.name) replicas=$($dep.replicas)"
        kubectl scale deployment $dep.name -n $dep.namespace --replicas=$($dep.replicas) | Out-Null
    }
}

function Remove-Hpas {
    param([string[]]$TargetNamespaces)

    foreach ($ns in $TargetNamespaces) {
        $hpas = Get-Hpas -Namespace $ns
        foreach ($h in $hpas) {
            Write-Step "Deleting HPA $($h.namespace)/$($h.name)"
            kubectl delete hpa $h.name -n $h.namespace --ignore-not-found | Out-Null
        }
    }
}

function Apply-DevHpaManifest {
    param([string]$RepoRoot)

    $hpaPath = Join-Path $RepoRoot "robotaigeek-server\k8s\dev\hpa.yaml"
    if (Test-Path $hpaPath) {
        Write-Step "Applying HPA manifest: $hpaPath"
        kubectl apply -f $hpaPath | Out-Null
    }
    else {
        Write-Step "HPA manifest not found at $hpaPath (skipping)."
    }
}

function Delete-DevIngresses {
    param([string[]]$TargetNamespaces)

    foreach ($ns in $TargetNamespaces) {
        $ing = Get-Ingresses -Namespace $ns
        foreach ($i in $ing) {
            Write-Step "Deleting ingress $($i.namespace)/$($i.name)"
            kubectl delete ingress $i.name -n $i.namespace --ignore-not-found --wait=false | Out-Null
        }
    }
}

function Reset-FailedManagedCertificates {
    param([string[]]$TargetNamespaces)

    foreach ($ns in $TargetNamespaces) {
        $jsonText = kubectl get managedcertificate -n $ns -o json 2>$null
        if ([string]::IsNullOrWhiteSpace($jsonText)) {
            continue
        }

        $json = $jsonText | ConvertFrom-Json
        foreach ($item in $json.items) {
            $certStatus = ""
            if ($item.status -and $item.status.certificateStatus) {
                $certStatus = [string]$item.status.certificateStatus
            }

            if ($certStatus -eq "ProvisioningFailedPermanently") {
                Write-Step "Recreating failed managed certificate $ns/$($item.metadata.name)"
                kubectl delete managedcertificate $item.metadata.name -n $ns --ignore-not-found | Out-Null
            }
        }
    }
}

function Apply-DevIngressManifests {
    param([string]$RepoRoot)

    Reset-FailedManagedCertificates -TargetNamespaces @("default", "rag-web-dev")

    $paths = @(
        (Join-Path $RepoRoot "robotaigeek-server\k8s\dev\ingress.yaml"),
        (Join-Path $RepoRoot "robotaigeek-server\k8s\dev\mcp\mcp-ingress.yaml"),
        (Join-Path $RepoRoot "robotaigeek-web\k8s\dev\ingress.yaml")
    )

    foreach ($path in $paths) {
        if (Test-Path $path) {
            Write-Step "Applying ingress manifest: $path"
            kubectl apply -f $path | Out-Null
        }
    }
}

function Print-Status {
    param([string[]]$TargetNamespaces)

    Write-Step "Current status in cluster $ClusterName"
    kubectl get nodes -o wide
    foreach ($ns in $TargetNamespaces) {
        Write-Host ""
        Write-Host "Namespace: $ns" -ForegroundColor Yellow
        kubectl get deploy -n $ns
        kubectl get hpa -n $ns
        kubectl get ingress -n $ns
    }
}

function Verify-OffState {
    param(
        [string[]]$TargetNamespaces,
        [bool]$IngressExpectedRemoved
    )

    $runningDeployments = @()
    foreach ($ns in $TargetNamespaces) {
        $json = kubectl get deployments -n $ns -o json | ConvertFrom-Json
        foreach ($item in $json.items) {
            $replicas = if ($null -eq $item.status.replicas) { 0 } else { [int]$item.status.replicas }
            if ($replicas -gt 0) {
                $runningDeployments += "$ns/$($item.metadata.name)=$replicas"
            }
        }
    }

    if ($runningDeployments.Count -eq 0) {
        Write-Step "Verification passed: all target deployments are scaled to 0."
    }
    else {
        Write-Step "WARNING: some deployments still have replicas > 0: $($runningDeployments -join ', ')"
    }

    if ($IngressExpectedRemoved) {
        $remainingIngress = @()
        foreach ($ns in $TargetNamespaces) {
            $ing = kubectl get ingress -n $ns -o json | ConvertFrom-Json
            foreach ($item in $ing.items) {
                $remainingIngress += "$ns/$($item.metadata.name)"
            }
        }

        if ($remainingIngress.Count -eq 0) {
            Write-Step "Verification passed: target ingresses are removed."
        }
        else {
            Write-Step "WARNING: some ingresses still exist: $($remainingIngress -join ', ')"
        }
    }

    Write-Step "Note: public DNS/LB behavior can lag for a few minutes after changes. If URL still responds, run status and recheck in 5-10 minutes."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($StateFile)) {
    $StateFile = Join-Path $repoRoot "tmp_ignore\dev-cluster-state.json"
}

Ensure-Tool -Name "gcloud"
Ensure-Tool -Name "kubectl"

if ($Mode -eq "cluster") {
    if (-not $Force) {
        throw "Cluster mode is destructive/expensive. Re-run with -Force to confirm."
    }

    if ($Action -eq "off") {
        Write-Step "Deleting cluster $ClusterName in $Region"
        Run-Cmd "gcloud container clusters delete $ClusterName --region $Region --project $ProjectId --quiet"
        exit 0
    }

    if ($Action -eq "on") {
        Write-Step "Creating Autopilot cluster $ClusterName in $Region"
        Run-Cmd "gcloud container clusters create-auto $ClusterName --region $Region --project $ProjectId --release-channel regular"
        Write-Step "Cluster created. Next: apply dev manifests and secrets before traffic cutover."
        exit 0
    }

    if ($Action -eq "status") {
        Run-Cmd "gcloud container clusters list --project $ProjectId --filter=name=$ClusterName"
        exit 0
    }
}

Ensure-ClusterCredentials

switch ($Action) {
    "off" {
        Save-State -TargetNamespaces $Namespaces -Path $StateFile

        # HPA can force replicas back up. Remove before scaling down.
        Remove-Hpas -TargetNamespaces $Namespaces

        foreach ($ns in $Namespaces) {
            Write-Step "Scaling all deployments in $ns to 0"
            kubectl scale deployment --all -n $ns --replicas=0 | Out-Null
        }

        if ($DeleteIngress) {
            Delete-DevIngresses -TargetNamespaces $Namespaces
        }

        Verify-OffState -TargetNamespaces $Namespaces -IngressExpectedRemoved:$DeleteIngress

        Write-Step "Dev workloads are now OFF."
        Write-Step "State file: $StateFile"
        Write-Step "To restore: .\scripts\toggle-dev-cluster.ps1 -Action on"
    }

    "on" {
        if (Test-Path $StateFile) {
            Restore-ReplicaState -Path $StateFile
        }
        else {
            Restore-DefaultReplicaState
        }

        Apply-DevHpaManifest -RepoRoot $repoRoot
        Apply-DevIngressManifests -RepoRoot $repoRoot

        Write-Step "Dev workloads are now ON."
    }

    "status" {
        Print-Status -TargetNamespaces $Namespaces
    }
}
