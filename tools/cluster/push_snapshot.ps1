# #P4: put one commit of this repository on the i6 cluster as an immutable
# snapshot (git archive, the CB#113 pattern: tracked files only, so nothing
# untracked such as 'emails and pdfs/' leaves the laptop), unpacked
# read-only at $W/sb_<sha>.  It submits nothing; it prints the sbatch line.
# Usage: pwsh tools/cluster/push_snapshot.ps1 [-Commit HEAD] [-CodeOnly]
#   -CodeOnly leaves out thesis/, eval_results/, archive/, notes/ and the PDFs,
#   which no cluster run reads: 6 MB instead of 115 MB (BF#56: the connection
#   dropped three full uploads in one night).  Every file kept is the
#   commit's blob, byte for byte, so the tree is still the commit's.
param([string]$Commit = 'HEAD', [switch]$CodeOnly)
$ErrorActionPreference = 'Stop'
# The cluster's names are never written here: they come from the git-ignored file
# tools/cluster/cluster.local.json beside this script, {"work": ..., "host": ..., "partition": ...}
# (cluster.local.example.json shows the form).
$local = Join-Path $PSScriptRoot 'cluster.local.json'
if (-not (Test-Path $local)) { throw "no ${local}: copy cluster.local.example.json there and fill in work, host and partition" }
$cfg = Get-Content -Raw $local | ConvertFrom-Json
$W = $cfg.work; $H = $cfg.host; $P = $cfg.partition
if (-not $W -or -not $H) { throw "${local} needs work and host" }
$sha = (git rev-parse --short=7 $Commit).Trim()
$name = "sb_$sha"
$tgz = Join-Path $env:TEMP "$name.tar.gz"
# core.autocrlf=true (this laptop) makes git archive write CRLF text files,
# which Slurm refuses ("Batch script contains DOS line breaks") and bash
# misreads; with it off the archive holds the commit's blobs byte for byte.
if ($CodeOnly) {
    $paths = @(git ls-tree --name-only $Commit | Where-Object { $_ -notin @('thesis', 'eval_results', 'archive', 'notes') -and $_ -notmatch '\.pdf$' })
    git -c core.autocrlf=false archive --format=tar.gz -o $tgz $Commit -- @paths
} else {
    git -c core.autocrlf=false archive --format=tar.gz -o $tgz $Commit
}
Write-Host "archive $name : $([math]::Round((Get-Item $tgz).Length / 1MB, 1)) MB$(if ($CodeOnly) { ' (code only)' })"
# BF#49: make room under the 1 GiB cap first (twice the archive: the upload
# and the unpacked tree); the archive itself is removed after the unpack.
$prune = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot 'prune_work.sh')).Replace("`r", '')
$prune | ssh -o BatchMode=yes $H "P4_WORK=$W bash -s -- --apply --reserve $(2 * (Get-Item $tgz).Length)"
if ($LASTEXITCODE -ne 0) { throw "prune_work.sh could not make room under the cap (exit $LASTEXITCODE)" }
scp -o BatchMode=yes $tgz "${H}:$W/inbox/$name.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE): nothing unpacked" }
$unpack = @"
set -e
gzip -t $W/inbox/$name.tar.gz
if [ -d $W/$name ]; then echo "$name already unpacked"; else
  mkdir -p $W/$name && tar -xzf $W/inbox/$name.tar.gz -C $W/$name
  chmod -R a-w $W/$name
  echo "unpacked ${name}: `$(ls $W/$name | wc -l) entries"
fi
rm -f $W/inbox/$name.tar.gz
"@
# PowerShell ends a string piped into a native command with CRLF, so bash
# read "fi\r", never closed the if and unpacked nothing (BF#43); the remote
# tr strips every CR, the file's own line endings included.
$unpack | ssh -o BatchMode=yes $H "tr -d '\r' | bash -s"
if ($LASTEXITCODE -ne 0) { throw "remote unpack failed (exit $LASTEXITCODE)" }
Remove-Item -LiteralPath $tgz
Write-Host ""
Write-Host "Submit from the submit node ($H) (smoke first, then full episodes):"
Write-Host "  ssh $H"
$sub = "sbatch -w <node> --partition=$(if ($P) { $P } else { '<partition>' }) --output=$W/logs/%x_%j.txt --export=ALL,P4_WORK=$W"
Write-Host "  CLEAN_STRAYS=1 $sub $W/$name/tools/cluster/bridge_run.sbatch $name smoke 0 1"
Write-Host "  $sub $W/$name/tools/cluster/bridge_run.sbatch $name full 0 1 2 3"
Write-Host "  tail -f $W/logs/p4-bridge_<jobid>.txt"
