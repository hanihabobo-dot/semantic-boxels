# The holder of the page beside our own window (run boxels; gui_page.py).  Hani, 2026-11-22:
# "can you make them stick together and look like one window and move together?"
#
# The simulator's window and the page are two programs' windows (the simulator is drawn by WSL's
# window host, the page by the browser), so they cannot be one window.  This script makes them
# look and move like one: it waits for this run's two windows and then keeps the page's window
#   - flush against the simulator's window, on its right where the screen has room there, else on
#     its left, with the simulator's top and height; where neither side has the least room it
#     stands at the screen's edge and lies over the simulator's edge by what is missing (drag
#     the simulator aside and it lies flush again);
#   - cut to its page: the browser's own title bar and borders are not shown, so no second frame
#     stands beside the simulator's;
#   - with it when it moves, comes to the front, is minimised or restored (Windows reports each
#     of those as it happens; a look four times a second catches what was missed).
# When the simulator's window or the run is gone the page's window is its own again: whole, with
# its title bar, where it first opened, so that the run's last lines can still be read.
#
# It only places and cuts the page's window and reads the simulator's; nothing is sent to either
# program and nothing reaches the run.  `run boxels` starts it hidden (run.ps1; -LoosePage leaves
# it out) and never ends it: it ends by itself.  The how is in tools/page_dock.cs.
#   pwsh -File tools/page_dock.ps1 -WatchPid <the run's process> [-Width 400] [-MinWidth 240] [-Log <file> [-Trace]]
# -Width, -MinWidth: the page's width and the least room it takes, in pixels at 100 % scaling.
# -WatchPid 0 (no run to watch): it gives up after -WaitSeconds without the two windows.
# The other parameters name the windows and are there for the trial with stand-in windows.
param([int]$WatchPid = 0,
      [int]$Width = 400,
      [int]$MinWidth = 240,
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
Add-Type -Path (Join-Path $PSScriptRoot 'page_dock.cs') -IgnoreWarnings
exit [PageDock]::Run($SimTitle, $SimProcess, $PageTitle, $PageClass, $PageChildClass,
                     $Width, $MinWidth, $WatchPid, $WaitSeconds, $Log, [bool]$Trace)
