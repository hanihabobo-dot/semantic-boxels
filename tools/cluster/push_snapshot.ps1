# #P4: put one commit of this repository on the i6 cluster as an immutable
# snapshot (git archive, the CB#113 pattern: tracked files only, so nothing
# untracked such as 'emails and pdfs/' leaves the laptop), unpacked
# read-only at $W/sb_<sha>.  It submits nothing; it prints the sbatch line.
# Usage: pwsh tools/cluster/push_snapshot.ps1 [-Commit HEAD]
param([string]$Commit = 'HEAD')
$ErrorActionPreference = 'Stop'
$W = '/work/rleap1/hani.alassiri.alhabboub/p4'
$sha = (git rev-parse --short=7 $Commit).Trim()
$name = "sb_$sha"
$tgz = Join-Path $env:TEMP "$name.tar.gz"
git archive --format=tar.gz -o $tgz $Commit
Write-Host "archive $name : $([math]::Round((Get-Item $tgz).Length / 1MB, 1)) MB"
scp -o BatchMode=yes $tgz "cn-04:$W/inbox/$name.tar.gz"
$unpack = @"
set -e
if [ -d $W/$name ]; then echo "$name already unpacked"; else
  mkdir -p $W/$name && tar -xzf $W/inbox/$name.tar.gz -C $W/$name
  chmod -R a-w $W/$name
  echo "unpacked ${name}: `$(ls $W/$name | wc -l) entries"
fi
"@
$unpack.Replace("`r", '') | ssh -o BatchMode=yes cn-04 "bash -s"
Remove-Item -LiteralPath $tgz
Write-Host ""
Write-Host "Submit from cn-04 (smoke first, then full episodes):"
Write-Host "  ssh cn-04"
Write-Host "  CLEAN_STRAYS=1 sbatch -w cn-110 $W/$name/tools/cluster/bridge_run.sbatch $name smoke 0 1"
Write-Host "  sbatch -w cn-110 $W/$name/tools/cluster/bridge_run.sbatch $name full 0 1 2 3"
Write-Host "  tail -f $W/logs/p4-bridge_<jobid>.txt"
