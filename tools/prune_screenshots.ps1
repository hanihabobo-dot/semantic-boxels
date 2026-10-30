<#
Deletes PyBullet sim screenshots older than a week (user policy 2026-10-28):
the world-eye camera and GUI images (eye_<k>_camera.png, eye_<k>_gui.png) and
capture / screenshot images under logs/, eval_results/ and runs/ of this repo
and of its sibling eval snapshots (..\Semantic_Boxels_*).  They are kept for
debugging until then.  Git-tracked images, archive/ and the thesis graphics
are never touched.  Dry run unless -Apply; every applied run appends a line
to logs/prune_screenshots.log.  A daily scheduled task (SemanticBoxels-prune-screenshots, 12:15) runs it with -Apply.

  pwsh -NoProfile -File tools\prune_screenshots.ps1              # show what would go
  pwsh -NoProfile -File tools\prune_screenshots.ps1 -Apply
  pwsh -NoProfile -File tools\prune_screenshots.ps1 -Days 14
#>
param([int]$Days = 7, [switch]$Apply)

$repo = Split-Path $PSScriptRoot -Parent
$roots = @($repo) + @(Get-ChildItem (Split-Path $repo -Parent) -Directory -Filter 'Semantic_Boxels_*' | ForEach-Object FullName)
$tracked = @{}
git -C $repo ls-files '*.png' '*.jpg' 2>$null | ForEach-Object { $tracked[(Join-Path $repo ($_ -replace '/', '\')).ToLower()] = $true }
$cutoff = (Get-Date).AddDays(-$Days)
$pattern = '^(eye_\d+_(camera|gui)|.*capture.*|.*screenshot.*)\.(png|jpe?g)$'

$old = foreach ($root in $roots) {
    foreach ($sub in 'logs', 'eval_results', 'runs') {
        $dir = Join-Path $root $sub
        if (Test-Path $dir) {
            Get-ChildItem $dir -Recurse -File -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match $pattern -and $_.LastWriteTime -lt $cutoff -and -not $tracked.ContainsKey($_.FullName.ToLower()) }
        }
    }
}
$old = @($old)
$mb = [math]::Round((($old | Measure-Object Length -Sum).Sum) / 1MB, 1)
if (-not $Apply) {
    "dry run: {0} sim screenshots older than {1} days, {2} MB (add -Apply to delete)" -f $old.Count, $Days, $mb
    $old | Select-Object -First 5 | ForEach-Object { "  $($_.FullName)" }
    return
}
$old | Remove-Item -Force -ErrorAction SilentlyContinue
$left = @($old | Where-Object { Test-Path $_.FullName }).Count
$line = "{0}  deleted {1} sim screenshots older than {2} days ({3} MB), {4} failed" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), ($old.Count - $left), $Days, $mb, $left
New-Item -ItemType Directory -Force (Join-Path $repo 'logs') | Out-Null
Add-Content (Join-Path $repo 'logs\prune_screenshots.log') $line
$line
