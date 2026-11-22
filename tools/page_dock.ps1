# The holder of the page beside our own window (run boxels; gui_page.py).  Hani, 2026-11-22:
# "can you make them stick together and look like one window and move together?"
#
# The simulator's window and the page are two programs' windows (the simulator is drawn by WSL's
# window host, the page by the browser), so they cannot be one window.  This script makes them
# look and move like one: it waits for this run's two windows and then keeps the page's window
#   - against the simulator's window, on its right where the screen has room there, else on its
#     left, with the simulator's top and height; where neither side has the least room it
#     stands at the screen's edge and lies over the simulator's edge by what is missing (drag
#     the simulator aside and it lies against it again);
#   - cut to its page: the browser's own title bar and borders are not shown, so no second frame
#     stands beside the simulator's;
#   - with it when it moves, comes to the front, is minimised or restored (Windows reports each
#     of those as it happens; a look four times a second catches what was missed).
# When the simulator's window or the run is gone the page's window is its own again: whole, with
# its title bar, where it first opened, so that the run's last lines can still be read.
#
# "Against the simulator's window" is against the rectangle Windows gives for that window.  WSL's
# window host may send the window's shadow as part of it; the rectangle is then larger than what
# is seen, and -SimInset says by how much (real pixels: left,top,right,bottom).  The log (-Log)
# describes both windows as Windows sees them, so that a look at a real run gives the numbers.
#
# WHICH two windows.  The page's: with -PageWord, the page of THIS run and no other: the script
# asks the page servers on this machine (-PortFrom to -PortTo, as run.ps1's Find-Page does) which
# one gives the run's word back, and takes the window named by that server's port.  A page left
# open by an earlier run on another port is never taken for it, and neither is a browser window
# with tabs that shows the page (its title goes on after the page's: "... - Microsoft Edge"):
# only a window whose whole title is the page's, as the window that `run boxels` opens for the
# page has it.  Without -PageWord the first window whose title starts with -PageTitle is taken
# (the trial).
# The simulator's: one that opened after the script last looked without this run's page
# answering (the run starts its page before it opens its window, so the run's window was not
# open at that look).  When none has opened since, the script may have started late: it then asks
# the run's page whether the run has drawn its window, and takes the simulator window that is
# open if it is the only one.  With more than one it takes none and ends (PageDock.Choose).
#
# It only places and cuts the page's window and reads the simulator's (and puts it behind the
# page when the page is clicked); no message, key or click is sent to either window and nothing
# reaches the run.  `run boxels` starts it hidden (run.ps1; -LoosePage leaves it out) and never
# ends it: it ends by itself.  The how is in tools/page_dock.cs.
#   pwsh -File tools/page_dock.ps1 -WatchPid <the run's process> -PageWord <the run's word>
#        [-Width 400] [-MinWidth 240] [-SimInset 0,0,0,0] [-Log <file> [-Trace]]
# -Width, -MinWidth: the page's width and the least room it takes, in pixels at 100 % scaling.
# -WatchPid 0 (no run to watch): it gives up after -WaitSeconds without the page or the windows.
# -Log: the file is started anew; -Trace adds every report of Windows about the two windows.
# Exit code: 0 after holding; 2 the run ended before its page or its windows came; 3 gave up
# (no run to watch); 4 an error of this script (the log has it); 5 more than one simulator window
# and it cannot tell which is the run's; 6 the run has drawn its window and no simulator window
# is found; 7 no browser window of its own shows the page.
# The other parameters name the windows and are there for the trial with stand-in windows.
param([int]$WatchPid = 0,
      [string]$PageWord = '',
      [int]$PortFrom = 8765,
      [int]$PortTo = 8774,
      [int]$Width = 400,
      [int]$MinWidth = 240,
      [string]$SimInset = '0,0,0,0',
      [int]$WaitSeconds = 120,
      [string]$Log = '',
      [switch]$Trace,
      [string]$PageTitle = 'Semantic Boxels (page ',
      [string]$PageClass = 'Chrome_WidgetWin_',
      [string]$PageChildClass = 'Chrome_RenderWidgetHostHWND',
      [string]$SimTitle = 'Bullet Physics',
      [string]$SimProcess = 'msrdc')
$ErrorActionPreference = 'Stop'
# '*' in place of a name takes any (an empty word does not survive every command line)
if ($SimProcess -eq '*') { $SimProcess = '' }
if ($PageClass -eq '*') { $PageClass = '' }
if ($PageChildClass -eq '*') { $PageChildClass = '' }
if ($Log) {
    # started anew; a log that cannot be written never stops the holder
    try {
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Log)
        Set-Content -LiteralPath $Log -Encoding utf8 -Value ((Get-Date -Format 'HH:mm:ss.fff') +
            " the holder of the page starts ($(Get-Date -Format 'yyyy-MM-dd')): run process $WatchPid, word '$PageWord'")
    } catch { $Log = '' }
}
function Say([string]$text) {
    if ($Log) { try { Add-Content -LiteralPath $Log -Value ((Get-Date -Format 'HH:mm:ss.fff') + ' ' + $text) -Encoding utf8 } catch { } }
}
trap {
    Say "ERROR, the holder ends: $($_.Exception.Message) (line $($_.InvocationInfo.ScriptLineNumber))"
    exit 4
}
if ($SimInset -notmatch '^\s*-?\d+\s*(,\s*-?\d+\s*){3}$') {
    throw "-SimInset takes four whole numbers (left,top,right,bottom), not '$SimInset'"
}
Add-Type -Path (Join-Path $PSScriptRoot 'page_dock.cs') -IgnoreWarnings
$in = @($SimInset -split ',' | ForEach-Object { [int]$_.Trim() })
[PageDock]::SetInset($in[0], $in[1], $in[2], $in[3])
if ($PageWord) {
    Say "waiting for the page that gives this run's word back (ports $PortFrom to $PortTo)"
    $port = 0
    $kept = $false
    $since = Get-Date
    while (-not $port) {
        if ($WatchPid -and -not (Get-Process -Id $WatchPid -ErrorAction SilentlyContinue)) { Say 'the run ended before its page answered'; exit 2 }
        if (-not $WatchPid -and ((Get-Date) - $since).TotalSeconds -gt $WaitSeconds) { Say 'no page gave the word back'; exit 3 }
        # the simulator windows open now, looked at BEFORE the page servers are asked
        $null = [PageDock]::Look($SimTitle, $SimProcess)
        foreach ($one in $PortFrom..$PortTo) {
            $tcp = [System.Net.Sockets.TcpClient]::new()
            try {
                if (-not $tcp.ConnectAsync('127.0.0.1', $one).Wait(150)) { continue }
            } catch { continue } finally { $tcp.Dispose() }
            try {
                $state = Invoke-RestMethod -Uri "http://127.0.0.1:$one/state" -TimeoutSec 2 -NoProxy
                if ($state.run.token -eq $PageWord) { $port = $one; break }
            } catch { }
        }
        if (-not $port) {
            # No page gave the word back, so this run's window was not open at that look (the
            # run starts its page before it opens its window): those windows are not the run's.
            [PageDock]::Keep()
            $kept = $true
            Start-Sleep -Milliseconds 400
        }
    }
    # The page answered at the very first ask: the holder started late, and the list of that
    # look may hold the run's window already.  It is kept all the same; PageDock.Run then asks
    # the run whether it has drawn its window before it takes a window of that list.
    if (-not $kept) { [PageDock]::Keep() }
    $PageTitle = 'Semantic Boxels (page ' + $port + ')'
    [PageDock]::WholeTitle = $true      # the page's own window, never a browser window with the page in a tab
    $stateUrl = "http://127.0.0.1:$port/state"
    [PageDock]::RunWindowOpen = [Func[bool]] {
        # the run hands the page a render only once its window is open (boxel_env.py)
        try { $null -ne (Invoke-RestMethod -Uri $stateUrl -TimeoutSec 2 -NoProxy).camera } catch { $false }
    }.GetNewClosure()
    Say ("this run's page answers on port $port (run $($state.console.run_id)); its window is named $PageTitle; " +
         $(if ($kept) { 'the list of simulator windows was taken before the page answered' }
           else { 'the page answered at the first ask, so the list of simulator windows may hold the run''s window' }))
}
exit [PageDock]::Run($SimTitle, $SimProcess, $PageTitle, $PageClass, $PageChildClass,
                     $Width, $MinWidth, $WatchPid, $WaitSeconds, $Log, [bool]$Trace)
