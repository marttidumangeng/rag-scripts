param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("root", "backend", "frontend")]
    [string]$WorkspaceScope,

    [Parameter(Mandatory = $true)]
    [string]$SkillName,

    [Parameter(Mandatory = $true)]
    [string]$SkillFile,

    [Parameter(Mandatory = $true)]
    [string]$TaskSummary,

    [Parameter()]
    [ValidateRange(1, 5)]
    [int]$HelpfulnessScore = 4,

    [Parameter()]
    [bool]$WasHelpful = $true,

    [Parameter()]
    [bool]$WouldReuse = $true,

    [Parameter()]
    [string]$MissingOrUnclear = "",

    [Parameter()]
    [string]$SuggestedImprovements = "",

    [Parameter()]
    [ValidateRange(0, 100000)]
    [int]$TimeSavedMinutes = 0,

    [Parameter()]
    [string]$ModelName = "GPT-5.3-Codex",

    [Parameter()]
    [string]$AgentName = "GitHub Copilot",

    [Parameter()]
    [string]$Notes = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Split-ListValue {
    param(
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }

    return ($Value -split ";" |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$feedbackDir = Join-Path $repoRoot ".github\skill-feedback"
$feedbackFile = Join-Path $feedbackDir "feedback-log.jsonl"

if (-not (Test-Path -Path $feedbackDir)) {
    New-Item -ItemType Directory -Path $feedbackDir -Force | Out-Null
}

if (($HelpfulnessScore -le 3) -and [string]::IsNullOrWhiteSpace($SuggestedImprovements)) {
    Write-Warning "Helpfulness score is 3 or below. Add SuggestedImprovements for actionable feedback."
}

$entry = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    workspace_scope = $WorkspaceScope
    skill_name = $SkillName
    skill_file = $SkillFile
    task_summary = $TaskSummary
    helpfulness_score = $HelpfulnessScore
    was_helpful = $WasHelpful
    would_reuse = $WouldReuse
    missing_or_unclear = @(Split-ListValue -Value $MissingOrUnclear)
    suggested_improvements = @(Split-ListValue -Value $SuggestedImprovements)
    time_saved_minutes = $TimeSavedMinutes
    model_name = $ModelName
    agent_name = $AgentName
    notes = $Notes
}

$jsonLine = $entry | ConvertTo-Json -Depth 5 -Compress
Add-Content -Path $feedbackFile -Value $jsonLine

Write-Host "Skill feedback recorded in $feedbackFile"
