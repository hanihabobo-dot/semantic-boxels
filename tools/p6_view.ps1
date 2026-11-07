# Path 6, rule 15 (Hani, 2026-11-07): prints the commands for the visual check of a comparison
# eval.  PRINT ONLY: no window, no wsl call, no episode; Hani starts every run himself.
#   & tools\p6_view.ps1 -Wave 1               wave 1: arms A and B on the tabletop
#   & tools\p6_view.ps1 -Wave 2 -Arm T        wave 2: arms A, Aprime and T on find_dice scenes 113 and 102
# It needs Windows Python (standard library only) to read the arms' own eval_runner sources.
param(
    [ValidateSet(1, 2)][int]$Wave = 1,
    [ValidateSet('all', 'A', 'B', 'Aprime', 'T')][string]$Arm = 'all',
    [string]$Python = 'C:\Python312\python.exe'
)
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python (Join-Path $PSScriptRoot 'p6_view.py') --wave $Wave --arm $Arm
exit $LASTEXITCODE
