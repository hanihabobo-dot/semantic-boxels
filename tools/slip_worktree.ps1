# BF#59: a worktree and a branch for one fix of the die-slip campaign (Hani,
# 2026-10-31: "utilize git, worktrees and clusters to test out all
# improvements and fixes in parallel").  The worktree is a sibling of the
# main checkout, so the pipeline's ../pddlstream_lib resolves there as it
# does here; in WSL it is /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-<name>.
#   pwsh tools/slip_worktree.ps1 -Name grasp_align             ..\sb-slip-grasp_align on branch slip/grasp_align from tampura-bridge
#   pwsh tools/slip_worktree.ps1 -Name grasp_align -Base <ref>  from another commit or branch
#   pwsh tools/slip_worktree.ps1 -Name grasp_align -Remove      remove the worktree (the branch stays)
#   pwsh tools/slip_worktree.ps1 -List                          the campaign's worktrees
param([string]$Name, [string]$Base = 'tampura-bridge', [switch]$Remove, [switch]$List)
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels'
if ($List) { git -C $repo worktree list | Select-String 'sb-slip-'; exit 0 }
if (-not $Name -or $Name -notmatch '^[a-z][a-z0-9_]*$') {
    throw "-Name must be lowercase letters, digits and underscores (the fix's switch name)"
}
$path = "C:\Users\HaniAlassiriAlhabbou\git\sb-slip-$Name"
$branch = "slip/$Name"
if ($Remove) {
    git -C $repo worktree remove --force $path
    if ($LASTEXITCODE -ne 0) { throw "worktree remove failed" }
    Write-Host "removed $path (branch $branch kept)"
    exit 0
}
if (Test-Path $path) { throw "$path exists" }
$exists = git -C $repo branch --list $branch
if ($exists) {
    git -C $repo worktree add $path $branch
} else {
    git -C $repo worktree add -b $branch $path $Base
}
if ($LASTEXITCODE -ne 0) { throw "worktree add failed" }
Write-Host "worktree $path on branch $branch (from $Base)"
Write-Host "WSL path /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-$Name"
