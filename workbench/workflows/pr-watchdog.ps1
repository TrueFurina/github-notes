param([int]$PollSeconds=120,[string]$LogDir="D:\github\pr-watchdog-logs")
$ErrorActionPreference='Continue'
$t=[Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User'); if(-not $t){throw "GITHUB_TOKEN"}
$h=@{}; $h.Authorization="Bearer $t"; $h.Accept="application/vnd.github+json"; $h.'X-GitHub-Api-Version'='2022-11-28'
$repos=@('TencentCloud/Octop','TencentCloud/octop-memory')
New-Item -ItemType Directory -Force -Path $LogDir|Out-Null
if(Test-Path (Join-Path $LogDir 'state.json')){try{$S=Get-Content (Join-Path $LogDir 'state.json')-Raw|ConvertFrom-Json}catch{$S=[PSCustomObject]@{}}}else{$S=[PSCustomObject]@{}}
function Has($k){$S.PSObject.Properties.Name -contains $k}
function AddProp($k,$v){if(Has $k){$S.$k=$v}else{$S|Add-Member -NotePropertyName $k -NotePropertyValue $v}}
function GA($u){for($i=0;$i-lt 3;$i++){try{return Invoke-RestMethod $u -Headers $h -Method Get -UseBasicParsing}catch{Start-Sleep -Seconds (3*(2*$i))}};return $null}
function LogTick($m){Add-Content (Join-Path $LogDir 'ticks.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $m"}
function LogAlert($m){Add-Content (Join-Path $LogDir 'alerts.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $m"}
Write-Host "Watchdog started. Poll=${PollSeconds}s"; $c=0
while($true){
  $c++; $ts=Get-Date; $open=$CIok=$CIfail=$stale=$rev=$new=0; $mergedCount=0
  foreach($repo in $repos){
    $prs=@(); $p=1
    do{$b=GA "https://api.github.com/repos/$repo/pulls?state=open&per_page=100&page=$p&head=TrueFurina"; if(-not $b -or $b.Count -eq 0){break}; $prs+=$b; $p++}while($b.Count -eq 100 -and $p -le 3)
    foreach($pr in $prs){
      $key="$repo#$($pr.number)"; $open++
      $ci="unknown"
      if($pr.head.sha){$runs=GA "https://api.github.com/repos/$repo/commits/$($pr.head.sha)/check-runs?per_page=30"; if($runs){$failed=@($runs.check_runs|?{$_.conclusion -eq 'failure' -or $_.conclusion -eq 'timed_out'}); if($failed.Count -gt 0){$ci="issues";$CIfail++}else{$ci="green";$CIok++}}}
      $ms=$pr.mergeable_state
      $rv=GA "https://api.github.com/repos/$repo/pulls/$($pr.number)/reviews?per_page=5"; $rs=if($rv){($rv|%{$_.state})-join ','}else{''}; if($rs -match 'APPROVED|CHANGES_REQUESTED'){$rev++}
      $cm=GA "https://api.github.com/repos/$repo/issues/$($pr.number)/comments?per_page=3"; $cc=if($cm){$cm.Count}else{0}
      $silent=[math]::Round(((Get-Date)-[DateTime]$pr.updated_at).TotalHours,1); $age=[math]::Round(((Get-Date)-[DateTime]$pr.created_at).TotalHours,1)
      $isStale=$silent -gt 48; if($isStale){$stale++}
      $al=@()
      if(Has $key){$prev=$S.$key; if($prev.ci -and $prev.ci -ne $ci){$al+="CI: $($prev.ci)->$ci"}; if($prev.merge -and $prev.merge -ne $ms){$al+="Merge: $($prev.merge)->$ms"}; if($prev.comments -and $prev.comments -ne $cc -and $cc -gt $prev.comments){$al+="+$($cc-$prev.comments) comments"}; if(-not $prev.alerted_stale -and $isStale){$al+="STALE ${silent}h"}}else{if($isStale){$al+="STALE ${silent}h"}}
      foreach($a in $al){LogAlert "[$key] $a -- $($pr.title)"; $new++}
      AddProp $key ([PSCustomObject]@{ci=$ci;merge=$ms;comments=$cc;silent_h=$silent;alerted_stale=$isStale;merged=$false;title=$pr.title})
      Start-Sleep -Milliseconds 150
    }
    $closed=GA "https://api.github.com/repos/$repo/pulls?state=closed&per_page=5&head=TrueFurina&sort=updated&direction=desc"
    if($closed){foreach($m in $closed){if($m.merged_at){$k="$repo#$($m.number)"; if((Has $k) -and -not $S.$k.merged_alerted){LogAlert "MERGED [$k] $($m.title)"; AddProp $k ([PSCustomObject]@{merged=$true;merged_at=$m.merged_at;merged_alerted=$true}); $mergedCount++}}}}
  }
  try{$S|ConvertTo-Json -Depth 8|Set-Content (Join-Path $LogDir 'state.json') -Encoding UTF8}catch{}
  $te=[math]::Round(((Get-Date)-$ts).TotalSeconds,1); $rl=try{(Invoke-RestMethod "https://api.github.com/rate_limit" -Headers $h -Method Get).rate}catch{$null}; $rls=if($rl){"$($rl.remaining)/$($rl.limit)"}else{"?"}
  LogTick "TICK #$c open=$open merged=$mergedCount CI=$CIok/$CIfail stale=$stale new=$new rev=$rev | ${te}s | rate=$rls"
  Start-Sleep -Seconds ([Math]::Max(5,$PollSeconds-$te))
}
