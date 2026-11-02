param([int]$PollSeconds=1800,[string]$LogDir="D:\github\auto-rebaser-logs")
$ErrorActionPreference='Continue'
$t=[Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User'); if(-not $t){throw "GITHUB_TOKEN"}
$h=@{}; $h.Authorization="Bearer $t"; $h.Accept="application/vnd.github+json"; $h.'X-GitHub-Api-Version'='2022-11-28'
$repoPairs=@(
  @{fork='TrueFurina/Octop';up='TencentCloud/Octop'},
  @{fork='TrueFurina/octop-memory';up='TencentCloud/octop-memory'},
  @{fork='TrueFurina/octop-harness';up='TencentCloud/octop-harness'}
)
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stateFile = Join-Path $LogDir 'state.json'
if(Test-Path $stateFile){try{$S=Get-Content $stateFile -Raw | ConvertFrom-Json}catch{$S=[PSCustomObject]@{}}}else{$S=[PSCustomObject]@{}}
function Has($k){$S.PSObject.Properties.Name -contains $k}
function AddP($k,$v){if(Has $k){$S.$k=$v}else{$S|Add-Member -NotePropertyName $k -NotePropertyValue $v}}
function GA($u){try{return Invoke-RestMethod $u -Headers $h -Method Get -UseBasicParsing -TimeoutSec 15}catch{return $null}}
function LT($m){Add-Content (Join-Path $LogDir 'ticks.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $m"}
function Update-Ref($repo,$ref,$sha){
  Invoke-RestMethod "https://api.github.com/repos/$repo/git/refs/$ref" -Headers $h -Method Patch -Body (@{sha=$sha;force=$true}|ConvertTo-Json -Compress) -ContentType 'application/json' | Out-Null
}
$forkOwner = 'TrueFurina'
Write-Host "Auto-Rebaser v4 started. Poll=${PollSeconds}s."
Write-Host "PER-PR CACHE: only re-check when upstream main SHA changes or cache 24h old"
Write-Host "SAFE FF: behind>0 AND ahead=0 AND total=behind AND PR still open"
$c=0
while($true){
  $c++; $ts=Get-Date; $chk=$rb=$sk=0
  foreach($pair in $repoPairs){
    $fork=$pair.fork; $up=$pair.up
    # Get upstream main SHA once per repo — if unchanged, cached per-PR results still valid
    $upMain = GA "https://api.github.com/repos/$up/git/refs/heads/main"
    $upSha = if($upMain){ $upMain.object.sha } else { $null }
    if(-not $upSha){ Write-Host "  SKIP $up — can't fetch main"; continue }
    $mainCacheKey = "main_$up"
    $mainChanged = -not (Has $mainCacheKey) -or $S.$mainCacheKey -ne $upSha
    AddP $mainCacheKey $upSha

    $openPrs = GA "https://api.github.com/repos/$up/pulls?state=open&per_page=100&head=$forkOwner"
    if(-not $openPrs -or $openPrs.Count -eq 0){ continue }
    foreach($pr in $openPrs){
      $chk++
      $key = "$up#$($pr.number)"
      $branchName = $pr.head.ref
      $cacheKey = "pr_$($pr.number)"

      # Use cached result if upstream main unchanged AND PR cached within 24h
      $cacheHit = $false
      if(Has $cacheKey -and -not $mainChanged){
        $cached = $S.$cacheKey
        $cacheAge = [math]::Round(((Get-Date) - [DateTime]$cached.timestamp).TotalHours, 1)
        if($cacheAge -lt 24 -and $cached.branch -eq $branchName){
          # Cache valid — skip compare, just verify PR still open
          $prFresh = GA "https://api.github.com/repos/$up/pulls/$($pr.number)"
          if(-not $prFresh -or $prFresh.state -ne 'open'){ $sk++; continue }
          if($cached.behind -gt 0 -and $cached.ahead -eq 0 -and $cached.total -eq $cached.behind){
            # Still a FF candidate — retry compare fresh
          } else {
            Write-Host "  [$key] CACHE a=$($cached.ahead) b=$($cached.behind) t=$($cached.total) $cacheAge`nh -> SKIP"
            $sk++; $cacheHit=$true; continue
          }
        }
      }

      # Fresh compare
      $comp = GA "https://api.github.com/repos/$up/compare/main...${forkOwner}:${branchName}"
      if(-not $comp){ Write-Host "  [$key] COMPARE FAIL"; $sk++; continue }
      $behind=[int]$comp.behind_by; $ahead=[int]$comp.ahead_by; $total=[int]$comp.total_commits
      Write-Host "  [$key] a=$ahead b=$behind t=$total"

      # Cache result
      AddP $cacheKey ([PSCustomObject]@{ branch=$branchName; ahead=$ahead; behind=$behind; total=$total; timestamp=(Get-Date).ToString() })

      # Re-verify PR is open right before any force-push
      if($behind -gt 0 -and $ahead -eq 0 -and $total -eq $behind){
        $prFresh = GA "https://api.github.com/repos/$up/pulls/$($pr.number)"
        if(-not $prFresh -or $prFresh.state -ne 'open'){ $sk++; continue }
        if($prFresh.merged -eq $true){ $sk++; continue }
        Write-Host "    -> SAFE FF $behind commits" -ForegroundColor Green
        try{
          Update-Ref $fork "heads/$branchName" $upSha
          Add-Content (Join-Path $LogDir 'rebases.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $key FF ${behind}c (v4 cached-aware)"
          AddP "rr_$key" "ff:$behind"
          $rb++
        } catch { Write-Host "    -> FF FAILED: $_" }
      } else {
        if($ahead -gt 0){ Write-Host "    -> HAS WORK ($ahead unique commits) — leave alone" -ForegroundColor Yellow }
        $sk++
      }
      Start-Sleep -Milliseconds 200
    }
  }
  try{ $S | ConvertTo-Json -Depth 6 | Set-Content $stateFile -Encoding UTF8 } catch {}
  $te=[math]::Round(((Get-Date)-$ts).TotalSeconds,1)
  $rl=try{(Invoke-RestMethod "https://api.github.com/rate_limit" -Headers $h -Method Get -TimeoutSec 5).rate}catch{$null}
  $rls=if($rl){"$($rl.remaining)/$($rl.limit)"}else{"?"}
  LT "TICK #$c checked=$chk rebased=$rb skipped=$sk | ${te}s | rate=$rls"
  Start-Sleep -Seconds ([Math]::Max(10,$PollSeconds-$te))
}
