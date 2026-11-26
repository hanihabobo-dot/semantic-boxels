# Run tools/cluster/prune_work.sh on the submit node (the cluster's data hygiene, user
# policy 2026-10-30, PAPER_AUDIT BF#49) and refresh the copy the submit node's crontab
# runs ($W/prune_work.sh, Mondays 03:25).  Dry run unless -Apply; retries the flaky
# connection.  The weekly scheduled task SemanticBoxels-prune-cluster (Mondays
# 12:25) runs it with -Apply from the laptop as well.
#   pwsh -NoProfile -File tools\cluster\prune_work.ps1           # show what would happen
#   pwsh -NoProfile -File tools\cluster\prune_work.ps1 -Apply
param([switch]$Apply, [int]$Attempts = 3)
$W = $env:SB_CLUSTER_WORK; $H = $env:SB_CLUSTER_HOST     # the cluster work folder and the ssh host, never written here
if (-not $W -or -not $H) { throw 'set SB_CLUSTER_WORK (the cluster work folder) and SB_CLUSTER_HOST (the ssh host of the submit node)' }
$script = Join-Path $PSScriptRoot 'prune_work.sh'
$text = [System.IO.File]::ReadAllText($script).Replace("`r", '')
$flag = if ($Apply) { '--apply' } else { '' }
for ($i = 1; $i -le $Attempts; $i++) {
    $out = ($text | ssh -o BatchMode=yes -o ConnectTimeout=40 $H "cat > $W/prune_work.sh.new && mv -f $W/prune_work.sh.new $W/prune_work.sh && bash $W/prune_work.sh $flag" 2>&1) -join "`n"
    if ($out -notmatch 'ssh: connect|Connection closed|timed out') { $out; break }
    Write-Host "attempt $i : $out"
    Start-Sleep -Seconds 30
}
if ($Apply) {
    $repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    New-Item -ItemType Directory -Force (Join-Path $repo 'logs') | Out-Null
    Add-Content (Join-Path $repo 'logs\prune_runs.log') ("{0}  cluster: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), (($out -split "`n") | Where-Object { $_ -match '^counted total|STILL OVER' } | Select-Object -Last 2) -join '; ')
}
