# Dev tracks (Hani, 2026-11-06; BF#68): a worktree and a branch for one
# track, cut from the stable base.  The worktree is a sibling of the main
# checkout, so the pipeline's ../pddlstream_lib resolves there as it does
# here; in WSL it is /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-<name>.  The
# main checkout stays on tampura-bridge, the trunk Hani runs from, and only
# the orchestrator merges into it.  The tracks and their sessions are listed
# in archive/tampura_bridge_plan_2026-10-25/tracks/STATE.md.
#   pwsh tools/track_worktree.ps1 -Name draw              ..\sb-draw on branch track/draw from stable-2026-11-06
#   pwsh tools/track_worktree.ps1 -Name draw -Base <ref>  from another commit or branch
#   pwsh tools/track_worktree.ps1 -Name draw -Remove      remove the worktree (the branch stays)
#   pwsh tools/track_worktree.ps1 -List                   the tracks' worktrees
param([string]$Name, [string]$Base = 'stable-2026-11-06', [switch]$Remove, [switch]$List)
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels'
if ($List) { git -C $repo worktree list | Select-String '\[track/'; exit 0 }
# sb-stable is the frozen reference checkout of the stable base, sb-slip-* the
# BF#59 campaign's: a track takes neither name.
if (-not $Name -or $Name -notmatch '^[a-z][a-z0-9_]*$' -or $Name -eq 'stable' -or $Name -like 'slip*') {
    throw "-Name must be lowercase letters, digits and underscores, and neither 'stable' nor 'slip...' (the track's short name)"
}
$path = "C:\Users\HaniAlassiriAlhabbou\git\sb-$Name"
$branch = "track/$Name"
if ($Remove) {
    git -C $repo worktree remove --force $path
    if ($LASTEXITCODE -ne 0) { throw "worktree remove failed" }
    Write-Host "removed $path (branch $branch kept)"
    exit 0
}
if (Test-Path $path) { throw "$path exists" }
# autocrlf off for the checkout: LF files as the cluster snapshots have them
# (bash scripts break on CRLF; Python and PowerShell read both).
$exists = git -C $repo branch --list $branch
if ($exists) {
    git -C $repo -c core.autocrlf=false worktree add $path $branch
} else {
    git -C $repo -c core.autocrlf=false worktree add -b $branch $path $Base
}
if ($LASTEXITCODE -ne 0) { throw "worktree add failed" }
Write-Host "worktree $path on branch $branch (from $Base)"
Write-Host "WSL path /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-$Name"
