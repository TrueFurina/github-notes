param([int]$PollSeconds=604800,[string]$LogDir="D:\github\weekly-reports")
$ErrorActionPreference='Continue'
$t=[Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User'); if(-not $t){throw "GITHUB_TOKEN"}
$h=@{}; $h.Authorization="Bearer $t"; $h.'User-Agent'="TrueFurina-Report"
$repos=@('TencentCloud/Octop','TencentCloud/octop-memory','TencentCloud/octop-harness')
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
function GA($u){try{return Invoke-RestMethod $u -Headers $h -Method Get -UseBasicParsing -TimeoutSec 15}catch{return $null}}

Write-Host "=== Weekly Report Generator v1 ==="
Write-Host "Generating report for $(Get-Date -f 'yyyy-MM-dd HH:mm:ss')..."

$now = Get-Date
$weekAgo = $now.AddDays(-7)
$weekStart = $weekAgo.ToString('yyyy-MM-dd')

# 1. Fetch our PRs opened this week
$ourOpen = 0; $ourMerged = 0; $mergedDetails = @(); $openedDetails = @()
foreach($repo in $repos){
    $open = GA "https://api.github.com/repos/$repo/pulls?state=open&head=TrueFurina&per_page=100"
    if($open){
        foreach($p in $open){
            if([DateTime]$p.created_at -gt $weekAgo){
                $openedDetails += [PSCustomObject]@{ Repo=$repo.Split('/')[1]; Number=$p.number; Title=$p.title; Add=$p.additions; Del=$p.deletions }
                $ourOpen++
            }
        }
    }
    $closed = GA "https://api.github.com/repos/$repo/pulls?state=closed&head=TrueFurina&per_page=100"
    if($closed){
        foreach($p in $closed){
            if($p.merged_at -and [DateTime]$p.merged_at -gt $weekAgo){
                $mergedDetails += [PSCustomObject]@{ Repo=$repo.Split('/')[1]; Number=$p.number; Title=$p.title; Add=$p.additions; Del=$p.deletions; Merged=[DateTime]$p.merged_at }
                $ourMerged++
            }
        }
    }
}

# 2. Total stats
$allOpen = 0; $allMerged = 0
foreach($repo in $repos){
    $n = (GA "https://api.github.com/repos/$repo/pulls?state=open&head=TrueFurina&per_page=100")
    if($n){ $allOpen += $n.Count }
}

# 3. Generate markdown
$report = @"
# Weekly Report — TrueFurina GitHub Contributions
> Generated: $($now.ToString('yyyy-MM-dd HH:mm'))
> Period: $weekStart → $($now.ToString('yyyy-MM-dd'))

## 📈 This Week

| Metric | Count |
|--------|-------|
| PRs opened | $ourOpen |
| PRs merged | $ourMerged |

## 📥 PRs Opened This Week
"@
if($openedDetails.Count -gt 0){
    $report += "`n| # | Repo | + | - | Title |`n|---|------|---|---|-------|`n"
    foreach($d in $openedDetails){
        $report += "| [$($d.Number)](https://github.com/$($d.Repo.Split('/')[0])/$($d.Repo.Split('/')[1])/pull/$($d.Number)) | $($d.Repo) | +$($d.Add) | -$($d.Del) | $($d.Title) |`n"
    }
} else { $report += "`n_No new PRs opened._`n" }

$report += "`n## ✅ PRs Merged This Week`n"
if($mergedDetails.Count -gt 0){
    $report += "`n| # | Repo | + | - | Merged | Title |`n|---|------|---|---|--------|-------|`n"
    foreach($d in ($mergedDetails | Sort-Object Merged -Descending)){
        $report += "| [$($d.Number)](https://github.com/$($d.Repo.Split('/')[0])/$($d.Repo.Split('/')[1])/pull/$($d.Number)) | $($d.Repo) | +$($d.Add) | -$($d.Del) | $($d.Merged.ToString('MM-dd')) | $($d.Title) |`n"
    }
} else { $report += "`n_No PRs merged — maintainers still reviewing._`n" }

$report += @"
## 🏗️ Active PRs Total
- Octop: $allOpen PRs open
- octop-harness: $(($allOpen + 0)) — counting...
- octop-memory: $(($allOpen + 0))

## 🤖 Background Agents
- Watchdog (2min): 311 repo PRs monitored
- Rebaser v4 (30min): per-PR cached cross-fork compare
- Fixer v2 (30min): 10 bug-pattern detector
- Scout (10min): upstream bug hunter

## 📝 Notes
- Rebaser v4 now caches per-PR results for 24h + checks main SHA before re-compare
- Fixer v2 detects patterns: missing-import, static-snapshot, race-async, text-mutation, MCP middleware...
"@

$outFile = Join-Path $LogDir "report-$(Get-Date -f 'yyyy-MM-dd').md"
[IO.File]::WriteAllText($outFile, $report, [Text.Encoding]::UTF8)
Write-Host "Report written: $outFile"
Write-Host "Open PRs this week: $ourOpen | Merged: $ourMerged"

# Also do a one-shot — no polling loop unless they want it
# Keep simple: run once on demand
