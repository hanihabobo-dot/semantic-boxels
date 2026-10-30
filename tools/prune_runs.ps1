<#
Run-data hygiene on the laptop (user policy 2026-10-30, PAPER_AUDIT BF#49):
the debug data of pipeline runs is COMPACTED after a day and DELETED after
two weeks.  A run directory is one named run_<date>_<time> (test_full_pipeline),
watch_s<k>_<stamp> (tools/watch.ps1), bridge_<time> (the bridge driver's
default) or s<k>_headless_<stamp>, under logs/, archive/, eval_results/ and
runs/ of this repo and of its sibling eval snapshots (..\Semantic_Boxels_*),
plus TAMPURA's own runs/ in WSL (/root/tampura-work/tampura_environments/runs,
where bridge runs land by default).
  compact: in a run directory whose newest file is older than -CompactAfterDays,
           every .log .jsonl .pkl .pddl .sas .txt file is gzipped in place
           (console_debug.log, eye.log, eye.jsonl, the run log, the ledger,
           their RolloutHistory); .json, .yml and images stay as they are.
  delete:  a run directory whose newest file is older than -DeleteAfterDays
           goes entirely.
A run directory holding any git-tracked file is evidence and is never
touched (its images are the screenshot pruner's business).  Dry run unless
-Apply; every applied run appends a line to logs/prune_runs.log.  A daily
scheduled task (SemanticBoxels-prune-runs, 12:20) runs it with -Apply.

  pwsh -NoProfile -File tools\prune_runs.ps1              # show what would happen
  pwsh -NoProfile -File tools\prune_runs.ps1 -Apply
  pwsh -NoProfile -File tools\prune_runs.ps1 -DeleteAfterDays 30 -Apply
#>
param([int]$CompactAfterDays = 1, [int]$DeleteAfterDays = 14, [switch]$Apply,
      [switch]$SkipWsl)
$ErrorActionPreference = 'Continue'
$repo = Split-Path $PSScriptRoot -Parent
$roots = @($repo) + @(Get-ChildItem (Split-Path $repo -Parent) -Directory -Filter 'Semantic_Boxels_*' -ErrorAction SilentlyContinue | ForEach-Object FullName)
$runPattern = '^(run_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}|watch_s\d+_.*|bridge_\d+(\.\d+)?|s\d+_headless_.*)$'
$compactExt = @('.log', '.jsonl', '.pkl', '.pddl', '.sas', '.txt')
$compactCut = (Get-Date).AddDays(-$CompactAfterDays)
$deleteCut = (Get-Date).AddDays(-$DeleteAfterDays)

# Every directory that holds a tracked file (and its ancestors) is evidence.
$evidence = @{}
git -C $repo ls-files -z 2>$null | ForEach-Object { $_ -split "`0" } | Where-Object { $_ } | ForEach-Object {
    $d = Split-Path (Join-Path $repo ($_ -replace '/', '\')) -Parent
    while ($d -and $d.Length -ge $repo.Length -and -not $evidence.ContainsKey($d.ToLower())) {
        $evidence[$d.ToLower()] = $true
        $d = Split-Path $d -Parent
    }
}

function Compress-InPlace([System.IO.FileInfo]$f) {
    $gz = $f.FullName + '.gz'
    $in = [System.IO.File]::OpenRead($f.FullName)
    $out = [System.IO.File]::Create($gz)
    $z = New-Object System.IO.Compression.GZipStream($out, [System.IO.Compression.CompressionLevel]::Optimal)
    try { $in.CopyTo($z) } finally { $z.Dispose(); $out.Dispose(); $in.Dispose() }
    [System.IO.File]::SetLastWriteTime($gz, $f.LastWriteTime)
    Remove-Item -LiteralPath $f.FullName -Force
}

$runDirs = foreach ($root in $roots) {
    foreach ($sub in 'logs', 'archive', 'eval_results', 'runs') {
        $dir = Join-Path $root $sub
        if (-not (Test-Path $dir)) { continue }
        $found = Get-ChildItem $dir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match $runPattern }
        # The outermost matching directory is the unit (watch_s*/ours/run_* is one run).
        $outer = @{}
        foreach ($d in $found) { $outer[$d.FullName] = $true }
        foreach ($d in $found) {
            $p = Split-Path $d.FullName -Parent; $nested = $false
            while ($p -and $p.Length -gt $dir.Length) { if ($outer.ContainsKey($p)) { $nested = $true; break }; $p = Split-Path $p -Parent }
            if (-not $nested) { $d }
        }
    }
}
$runDirs = @($runDirs)
$toCompact = [System.Collections.Generic.List[object]]::new()
$toDelete = [System.Collections.Generic.List[object]]::new()
$kept = 0
foreach ($d in $runDirs) {
    if ($evidence.ContainsKey($d.FullName.ToLower())) { $kept++; continue }
    $files = @(Get-ChildItem $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue)
    if (-not $files) { $toDelete.Add([pscustomobject]@{ dir = $d; mb = 0.0 }); continue }
    $newest = ($files | Measure-Object LastWriteTime -Maximum).Maximum
    $mb = ($files | Measure-Object Length -Sum).Sum / 1MB
    if ($newest -lt $deleteCut) { $toDelete.Add([pscustomobject]@{ dir = $d; mb = $mb }); continue }
    if ($newest -lt $compactCut) {
        foreach ($f in $files) { if ($compactExt -contains $f.Extension.ToLower()) { $toCompact.Add($f) } }
    }
}
$delMb = [math]::Round(($toDelete | Measure-Object mb -Sum).Sum, 1)
$cmpMb = [math]::Round((($toCompact | Measure-Object Length -Sum).Sum) / 1MB, 1)
$wslCmd = ("R=/root/tampura-work/tampura_environments/runs; [ -d `$R ] || exit 0; cd `$R; " +
           "find . -mindepth 1 -maxdepth 1 -type d -mtime +{0} -print0 | xargs -0 -r {1} rm -rf; " +
           "find . -type f \( -name '*.log' -o -name '*.jsonl' -o -name '*.pkl' -o -name '*.pddl' -o -name '*.sas' -o -name '*.txt' \) -mtime +{2} ! -name '*.gz' -print0 | xargs -0 -r {1} gzip -q; " +
           "echo `"their runs/: `$(ls | wc -l) dirs left, `$(du -sh . | cut -f1)`"") -f $DeleteAfterDays, ($(if ($Apply) { '' } else { 'echo would:' })), $CompactAfterDays
if (-not $Apply) {
    "dry run: {0} run dirs seen, {1} are evidence (tracked, untouched); would compact {2} files ({3} MB) in runs older than {4} d and delete {5} run dirs ({6} MB) older than {7} d; add -Apply" -f $runDirs.Count, $kept, $toCompact.Count, $cmpMb, $CompactAfterDays, $toDelete.Count, $delMb, $DeleteAfterDays
    $toDelete | Select-Object -First 3 | ForEach-Object { "  delete  $($_.dir.FullName)" }
    $toCompact | Select-Object -First 3 | ForEach-Object { "  compact $($_.FullName)" }
    if (-not $SkipWsl) { wsl -e bash -c $wslCmd 2>&1 | Select-Object -Last 1 }
    return
}
$compacted = 0; $failed = 0
foreach ($f in $toCompact) { try { Compress-InPlace $f; $compacted++ } catch { $failed++ } }
$deleted = 0
foreach ($t in $toDelete) {
    Remove-Item -LiteralPath $t.dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $t.dir.FullName)) { $deleted++ } else { $failed++ }
}
$wsl = if ($SkipWsl) { 'wsl skipped' } else { (wsl -e bash -c $wslCmd 2>&1 | Select-Object -Last 1) }
$line = "{0}  compacted {1} files ({2} MB) in runs older than {3} d, deleted {4} run dirs ({5} MB) older than {6} d, {7} evidence dirs untouched, {8} failed; {9}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $compacted, $cmpMb, $CompactAfterDays, $deleted, $delMb, $DeleteAfterDays, $kept, $failed, $wsl
New-Item -ItemType Directory -Force (Join-Path $repo 'logs') | Out-Null
Add-Content (Join-Path $repo 'logs\prune_runs.log') $line
$line
