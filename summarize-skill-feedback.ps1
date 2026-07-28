param(
    [Parameter()]
    [string]$StartDate = "",

    [Parameter()]
    [string]$EndDate = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$feedbackFile = Join-Path $repoRoot ".github\skill-feedback\feedback-log.jsonl"
$outputFile = Join-Path $repoRoot ".github\skill-feedback\summary.md"

if (-not (Test-Path -Path $feedbackFile)) {
    throw "Feedback log not found: $feedbackFile"
}

$lines = Get-Content -Path $feedbackFile | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
if ($lines.Count -eq 0) {
    @(
        "# Skill Feedback Summary",
        "",
        "No feedback entries found in .github/skill-feedback/feedback-log.jsonl."
    ) | Set-Content -Path $outputFile

    Write-Host "Summary written to $outputFile"
    exit 0
}

$entries = @()
foreach ($line in $lines) {
    $entries += ($line | ConvertFrom-Json)
}

if (-not [string]::IsNullOrWhiteSpace($StartDate)) {
    $start = [DateTime]::Parse($StartDate)
    $entries = $entries | Where-Object { [DateTime]::Parse($_.timestamp_utc) -ge $start }
}

if (-not [string]::IsNullOrWhiteSpace($EndDate)) {
    $end = [DateTime]::Parse($EndDate)
    $entries = $entries | Where-Object { [DateTime]::Parse($_.timestamp_utc) -le $end }
}

$total = $entries.Count
if ($total -eq 0) {
    @(
        "# Skill Feedback Summary",
        "",
        "No feedback entries in the selected date window."
    ) | Set-Content -Path $outputFile

    Write-Host "Summary written to $outputFile"
    exit 0
}

$groups = $entries | Group-Object -Property skill_name | Sort-Object -Property Name

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# Skill Feedback Summary")
$report.Add("")
$report.Add("Generated: $([DateTime]::UtcNow.ToString('u'))")
$report.Add("Total entries: $total")
$report.Add("")
$report.Add("## Per-Skill Metrics")
$report.Add("")
$report.Add("| Skill | Count | Avg Score | Helpful % | Reuse % |")
$report.Add("|---|---:|---:|---:|---:|")

foreach ($group in $groups) {
    $count = $group.Count
    $avgScore = [Math]::Round((($group.Group | Measure-Object -Property helpfulness_score -Average).Average), 2)
    $helpfulCount = ($group.Group | Where-Object { $_.was_helpful -eq $true }).Count
    $reuseCount = ($group.Group | Where-Object { $_.would_reuse -eq $true }).Count
    $helpfulPct = [Math]::Round((100.0 * $helpfulCount / $count), 1)
    $reusePct = [Math]::Round((100.0 * $reuseCount / $count), 1)

    $report.Add("| $($group.Name) | $count | $avgScore | $helpfulPct% | $reusePct% |")
}

$issueCounts = @{}
foreach ($entry in $entries) {
    foreach ($item in $entry.missing_or_unclear) {
        if ([string]::IsNullOrWhiteSpace($item)) {
            continue
        }

        if (-not $issueCounts.ContainsKey($item)) {
            $issueCounts[$item] = 0
        }

        $issueCounts[$item]++
    }
}

$improvementCounts = @{}
foreach ($entry in $entries) {
    foreach ($item in $entry.suggested_improvements) {
        if ([string]::IsNullOrWhiteSpace($item)) {
            continue
        }

        if (-not $improvementCounts.ContainsKey($item)) {
            $improvementCounts[$item] = 0
        }

        $improvementCounts[$item]++
    }
}

$report.Add("")
$report.Add("## Top Missing Or Unclear Items")
$report.Add("")
if ($issueCounts.Count -eq 0) {
    $report.Add("- None reported")
}
else {
    foreach ($pair in ($issueCounts.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 10)) {
        $report.Add("- $($pair.Key) ($($pair.Value))")
    }
}

$report.Add("")
$report.Add("## Top Suggested Improvements")
$report.Add("")
if ($improvementCounts.Count -eq 0) {
    $report.Add("- None reported")
}
else {
    foreach ($pair in ($improvementCounts.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 10)) {
        $report.Add("- $($pair.Key) ($($pair.Value))")
    }
}

$report | Set-Content -Path $outputFile
Write-Host "Summary written to $outputFile"
