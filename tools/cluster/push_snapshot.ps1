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
# core.autocrlf=true (this laptop) makes git archive write CRLF text files,
# which Slurm refuses ("Batch script contains DOS line breaks") and bash
# misreads; with it off the archive holds the commit's blobs byte for byte.
git -c core.autocrlf=false archive --format=tar.gz -o $tgz $Commit
Write-Host "archive $name : $([math]::Round((Get-Item $tgz).Length / 1MB, 1)) MB"
scp -o BatchMode=yes $tgz "cn-04:$W/inbox/$name.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE): nothing unpacked" }
$unpack = @"
set -e
gzip -t $W/inbox/$name.tar.gz
if [ -d $W/$name ]; then echo "$name already unpacked"; else
  mkdir -p $W/$name && tar -xzf $W/inbox/$name.tar.gz -C $W/$name
  chmod -R a-w $W/$name
  echo "unpacked ${name}: `$(ls $W/$name | wc -l) entries"
fi
"@
# PowerShell ends a string piped into a native command with CRLF, so bash
# read "fi\r", never closed the if and unpacked nothing (BF#43); the remote
# tr strips every CR, the file's own line endings included.
$unpack | ssh -o BatchMode=yes cn-04 "tr -d '\r' | bash -s"
if ($LASTEXITCODE -ne 0) { throw "remote unpack failed (exit $LASTEXITCODE)" }
Remove-Item -LiteralPath $tgz
Write-Host ""
Write-Host "Submit from cn-04 (smoke first, then full episodes):"
Write-Host "  ssh cn-04"
Write-Host "  CLEAN_STRAYS=1 sbatch -w cn-110 $W/$name/tools/cluster/bridge_run.sbatch $name smoke 0 1"
Write-Host "  sbatch -w cn-110 $W/$name/tools/cluster/bridge_run.sbatch $name full 0 1 2 3"
Write-Host "  tail -f $W/logs/p4-bridge_<jobid>.txt"
