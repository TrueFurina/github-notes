param([int]$PollSeconds=1800,[string]$LogDir="D:\github\auto-fixer-logs")
$ErrorActionPreference='Continue'
$t=[Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User'); if(-not $t){throw "GITHUB_TOKEN"}
$h=@{}; $h.Authorization="Bearer $t"; $h.Accept="application/vnd.github+json"; $h.'X-GitHub-Api-Version'='2022-11-28'
$repos=@('TencentCloud/Octop','TencentCloud/octop-memory','TencentCloud/octop-harness')
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stateFile = Join-Path $LogDir 'state.json'
if(Test-Path $stateFile){try{$S=Get-Content $stateFile -Raw | ConvertFrom-Json}catch{$S=[PSCustomObject]@{}}}else{$S=[PSCustomObject]@{}}
function Has($k){$S.PSObject.Properties.Name -contains $k}
function AddP($k,$v){if(Has $k){$S.$k=$v}else{$S|Add-Member -NotePropertyName $k -NotePropertyValue $v}}
function GA($u){try{return Invoke-RestMethod $u -Headers $h -Method Get -UseBasicParsing -TimeoutSec 15}catch{return $null}}
function LT($m){Add-Content (Join-Path $LogDir 'ticks.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $m"}

# ============================================================
# Fixer v2 (DETECTOR mode). Poll=${PollSeconds}s.
# Scans recent open bugs, classifies by fixable pattern, logs candidates.
# PS5-compatible: ArrayList, string variable extraction, ASCII separators.
# ============================================================

$patterns = @(
  [PSCustomObject]@{ name="missing-import";  regex='ModuleNotFoundError|No module named';                          hint="try/except ImportError guard" },
  [PSCustomObject]@{ name="static-snapshot"; regex='frozenset|static[_ -]?snapshot';                               hint="accept callable, resolve fresh per-call" },
  [PSCustomObject]@{ name="race-async";      regex='background[_ -]?reload|asyncio\.create_task|fire[_ -]?and[_ -]?forget'; hint="await reload completion or invalidate" },
  [PSCustomObject]@{ name="text-mutation";   regex='append_to_system_message|narrow_skills|trim_skill_list';      hint="trust downstream renderer, only update state" },
  [PSCustomObject]@{ name="none-null";       regex="NoneType|has no attribute 'NoneType'";                        hint="null guard or default value" },
  [PSCustomObject]@{ name="div-zero";        regex='ZeroDivisionError|division by zero';                           hint="denominator guard" },
  [PSCustomObject]@{ name="key-error";       regex='KeyError\b|IndexError\b';                                        hint=".get() with default or bounds check" },
  [PSCustomObject]@{ name="path-traversal";  regex='path[_ -]?traversal|\.\.\/|unsafe[_ -]?path';                   hint="validate + resolve() + relative_to()" },
  [PSCustomObject]@{ name="contextvars";     regex='contextvars|ContextVar';                                         hint="fresh context in background worker" },
  [PSCustomObject]@{ name="mcp-middleware";  regex='MCPToolMiddleware';                                              hint="re-check after append, callable snapshots" }
)

Write-Host "Auto-Fixer v2 (DETECTOR mode). Poll=${PollSeconds}s."
Write-Host "Patterns: $($patterns.Count) - logs fixable candidates for manual work"
$c=0
while($true){
  $c++; $ts=Get-Date; $op=$matched=0
  foreach($repo in $repos){
    # Search recent open bugs
    $q = "repo:$repo is:open is:issue label:bug created:>$(Get-Date (Get-Date).AddDays(-14) -f 'yyyy-MM-dd') sort:created-desc"
    $res = GA "https://api.github.com/search/issues?q=$([uri]::EscapeDataString($q))&per_page=10"
    if(-not $res -or $res.total_count -eq 0){ continue }
    foreach($issue in $res.items){
      $ik = "$repo#$($issue.number)"
      if(Has "tried_$ik"){ continue }
      $op++
      $text = "$($issue.title) $($issue.body)"
      $found = [System.Collections.ArrayList]::new()
      foreach($p in $patterns){
        if($text -match $p.regex){
          $pn = [string]$p.name
          $ph = [string]$p.hint
          [void]$found.Add("$pn -> $ph")
        }
      }
      if($found.Count -gt 0){
        $matched++
        $foundStrs = $found -join ' | '
        $line = "MATCH $ik [$($issue.title.Substring(0,[Math]::Min(50,$issue.title.Length)))] => $foundStrs"
        Write-Host "  $line"
        Add-Content (Join-Path $LogDir 'candidates.log') "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $ik => $foundStrs | https://github.com/$repo/issues/$($issue.number)"
        AddP "tried_$ik" $foundStrs
      } else {
        AddP "tried_$ik" "no_pattern"
      }
      Start-Sleep -Milliseconds 300
    }
  }
  try{ $S | ConvertTo-Json -Depth 8 | Set-Content $stateFile -Encoding UTF8 } catch {}
  $te=[math]::Round(((Get-Date)-$ts).TotalSeconds,1)
  $rl=try{(Invoke-RestMethod "https://api.github.com/rate_limit" -Headers $h -Method Get -TimeoutSec 5).rate}catch{$null}
  $rls=if($rl){"$($rl.remaining)/$($rl.limit)"}else{"?"}
  LT "TICK #$c opps=$op matched=$matched | ${te}s | rate=$rls"
  Start-Sleep -Seconds ([Math]::Max(10,$PollSeconds-$te))
}
