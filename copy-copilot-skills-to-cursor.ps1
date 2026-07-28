$root = Split-Path $PSScriptRoot -Parent
$destRoot = Join-Path $root '.cursor\skills'

function Convert-CopilotSkill {
    param(
        [string]$SourceFile,
        [string]$DestFile
    )
    $content = Get-Content -Path $SourceFile -Raw -Encoding UTF8
    if ($content -match '(?s)^---\r?\n(.*?)\r?\n---\r?\n(.*)$') {
        $body = $Matches[2]
        $fm = @{}
        foreach ($line in ($Matches[1] -split '\r?\n')) {
            if ($line -match '^(\w+):\s*(.*)$') {
                $key = $Matches[1]
                $val = $Matches[2].Trim().Trim('"')
                if ($key -ne 'applyTo') {
                    $fm[$key] = $val
                }
            }
        }
        $fmLines = @('---')
        if ($fm.ContainsKey('name')) { $fmLines += "name: $($fm['name'])" }
        if ($fm.ContainsKey('description')) { $fmLines += "description: `"$($fm['description'])`"" }
        $fmLines += '---'
        $out = ($fmLines -join "`n") + "`n`n" + $body.TrimStart()
    }
    else {
        $out = $content
    }
    $dir = Split-Path $DestFile -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($DestFile, $out, [System.Text.UTF8Encoding]::new($false))
}

New-Item -ItemType Directory -Path $destRoot -Force | Out-Null

Get-ChildItem (Join-Path $root '.github\skills') -Directory | ForEach-Object {
    $src = Join-Path $_.FullName 'SKILL.md'
    $dst = Join-Path $destRoot (Join-Path $_.Name 'SKILL.md')
    if (Test-Path $src) {
        Convert-CopilotSkill -SourceFile $src -DestFile $dst
    }
}

$overrides = @(
    @{ src = Join-Path $root 'robotaigeek-server\.github\skills\django-api\SKILL.md'; dst = Join-Path $destRoot 'django-api\SKILL.md' },
    @{ src = Join-Path $root 'robotaigeek-web\.github\skills\nuxt-frontend\SKILL.md'; dst = Join-Path $destRoot 'nuxt-frontend\SKILL.md' },
    @{ src = Join-Path $root 'robotaigeek-server\.github\skills\admin-crm-sidebar\SKILL.md'; dst = Join-Path $destRoot 'admin-crm-sidebar\SKILL.md' }
)
foreach ($o in $overrides) {
    if (Test-Path $o.src) {
        Convert-CopilotSkill -SourceFile $o.src -DestFile $o.dst
    }
}

$formUi = Join-Path $destRoot 'form-ui-consistency\SKILL.md'
if (Test-Path $formUi) {
    $raw = Get-Content $formUi -Raw -Encoding UTF8
    if ($raw -notmatch '(?s)^---\r?\n') {
        $body = $raw -replace '^# Skill: Form UI Consistency\r?\n\r?\n\*\*Use when\*\*: [^\r\n]+\r?\n', ''
        $fm = @"
---
name: form-ui-consistency
description: "Use when adding or modifying form inputs, action buttons, social auth buttons, or spacing in Nuxt pages/components in robotaigeek-web/. Covers sizing tokens, social auth button patterns, and spacing rules aligned with global .form-input styles."
---

"@
        [System.IO.File]::WriteAllText($formUi, ($fm + $body.TrimStart()), [System.Text.UTF8Encoding]::new($false))
    }
}

Write-Host 'Copied skills:'
Get-ChildItem $destRoot -Directory | ForEach-Object { Write-Host "  $($_.Name)" }
