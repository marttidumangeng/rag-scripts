param(
    [string]$Project = "robotaigeek-core",
    [string]$Repository = "gcr.io",
    [int]$KeepDays = 30,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[cleanup-artifacts] $Message" -ForegroundColor Cyan
}

Write-Step "Fetching images in $Repository for project $Project..."
$images = gcloud container images list --repository="gcr.io/$Project" --format="value(name)"

if (-not $images) {
    Write-Host "No images found." -ForegroundColor Yellow
    exit
}

$cutoffDate = (Get-Date).AddDays(-$KeepDays)
Write-Step "Finding digests older than $cutoffDate..."

$totalDeleted = 0
$freedCount = 0

foreach ($img in $images) {
    Write-Host "Analyzing $img ..." -ForegroundColor Yellow
    
    # We want to list all digests for this image, sorting by timestamp.
    # Keep any digest that has a 'latest' tag, or is newer than cutoff, or is one of the 5 most recent.
    # To be safe, we use gcloud container images list-tags with JSON format.
    $tagsJson = gcloud container images list-tags $img --format="json(digest,tags,timestamp.datetime)" | ConvertFrom-Json
    
    if (-not $tagsJson) { continue }
    
    # Sort by timestamp descending
    $tagsJson = $tagsJson | Sort-Object -Property timestamp -Descending

    # Always keep top 5
    $keepList = $tagsJson | Select-Object -First 5
    $candidateList = $tagsJson | Select-Object -Skip 5

    if (-not $candidateList) { continue }

    foreach ($candidate in $candidateList) {
        $timestamp = [datetime]$candidate.timestamp.datetime
        
        # Check if safe to delete
        if ($timestamp -lt $cutoffDate) {
            # Ensure 'latest' is not somehow in the older ones
            if ($candidate.tags -contains "latest") {
                Write-Host "  Skipping latest tag natively."
                continue
            }
            
            $target = "${img}@$($candidate.digest)"
            if ($WhatIf) {
                Write-Host "  [WhatIf] Would delete: $target (Age: $timestamp)" -ForegroundColor Gray
                $freedCount++
            } else {
                Write-Host "  Deleting: $target (Age: $timestamp)" -ForegroundColor Red
                gcloud container images delete $target --force-delete-tags --quiet
                $totalDeleted++
            }
        }
    }
}

if ($WhatIf) {
    Write-Step "Cleanup dry-run complete. $freedCount images would be deleted."
} else {
    Write-Step "Cleanup complete. $totalDeleted images deleted."
}
