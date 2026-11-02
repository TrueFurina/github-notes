param([int]$PollSeconds=600,[string]$LogDir="D:\github\scout-logs")
$ErrorActionPreference='Continue'
$t=[Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User'); if(-not $t){throw "GITHUB_TOKEN"}
$h=@{}; $h.Authorization="Bearer $t"; $h.Accept="application/vnd.github+json"; $h.'X-GitHub-Api-Version'='2022-11-28'
$upstreams=@('TencentCloud/Octop','TencentCloud/octop-memory','TencentCloud/octop-harness')
New-Item -ItemType Directory -Force -Path $LogDir|Out-Null
if(Test-Path (Join-Path $LogDir 'state.json')){try{$S=Get-Content (Join-Path $LogDir 'state.json')-Raw|ConvertFrom-Json}catch{$S=[PSCustomObject]@{seen=@{};releases=@{};last_checks=@{}}}}else{$S=[PSCustomObject]@{seen=@{};releases=@{};last_checks=@{}}}
function Has($k){$S.PSObject.Properties.Name -contains $k}
function AddP($k,$v){if(Has $k){$S.$k=$v}else{$S|Add-Member -NotePropertyName $k -NotePropertyValue $v}}
function GA($u){for($i=0;$i-lt 3;$i++){try{return Invoke-RestMethod $u -Headers $h -Method Get -UseBasicParsing}catch{Start-Sleep -Seconds (3*(2*$i))}};return $null}
function LT($m){Add-Content (Join-Path $LogDir 'ticks.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $m"}
Write-Host "Upstream Scout started. Poll=${PollSeconds}s"; $c=0
while($true){
  $c++; $ts=Get-Date; $nb=$nr=$no=0
  foreach($repo in $upstreams){
    $rel=GA "https://api.github.com/repos/$repo/releases?per_page=3"
    if($rel){foreach($r in $rel){$rk="$repo/$($r.tag_name)"; if(-not (Has "rl_$rk")){AddP "rl_$rk" $r.published_at; Add-Content (Join-Path $LogDir 'releases.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] NEW REL $repo $($r.tag_name)"; Write-Host "RELEASE: $repo $($r.tag_name)"; $nr++; $no++}}}
    $searches=@("repo:$repo is:open is:issue label:bug sort:created-desc","repo:$repo is:open is:issue label:good-first-issue sort:created-desc","repo:$repo is:open is:issue label:help-wanted sort:created-desc")
    foreach($q in $searches){$enc=[uri]::EscapeDataString($q); $res=GA "https://api.github.com/search/issues?q=$enc&sort=created&order=desc&per_page=10"
    if($res -and $res.items){foreach($i in $res.items){$ik="$repo#$($i.number)"; if(-not (Has "is_$ik")){AddP "is_$ik" $i.created_at; Add-Content (Join-Path $LogDir 'bugs.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] BUG $ik — $($i.title)"; Write-Host "BUG: $repo#$($i.number) $($i.title.Substring(0,[Math]::Min(60,$i.title.Length)))"; $nb++; $no++}}}
    Start-Sleep -Milliseconds 600}
    AddP "lc_$repo" (Get-Date -Format 'o')
  }
  try{$S|ConvertTo-Json -Depth 8|Set-Content (Join-Path $LogDir 'state.json') -Encoding UTF8}catch{}
  $te=[math]::Round(((Get-Date)-$ts).TotalSeconds,1); $rl=try{(Invoke-RestMethod "https://api.github.com/rate_limit" -Headers $h -Method Get).rate}catch{$null}; $rls=if($rl){"$($rl.remaining)/$($rl.limit)"}else{"?"}
  $seenCount=($S.PSObject.Properties.Name|?{$_ -like 'is_*'}).Count; LT "TICK #$c bugs=$nb rels=$nr opps=$no seen=$seenCount | ${te}s | rate=$rls"
  Start-Sleep -Seconds ([Math]::Max(5,$PollSeconds-$te))
}
