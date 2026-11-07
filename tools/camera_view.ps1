# The window of `run tampura -Draw cameras` (BF#68): what each of our cameras saw at its latest
# render, live.  The bridge run (tampura_bridge/camera_overlay.py) writes, per camera <name> into
# -Dir: <name>.png (the rgb image the camera produced; below it the depth image, near = bright,
# and the segmentation image, one colour per body) and then <name>.json (the caption: render count,
# plan and step, clock).  This script only reads the folder: it makes nothing in it and sends
# nothing to the run.  It runs at low priority; its polling (5 times a second) costs a little CPU.
#   pwsh -File tools/camera_view.ps1 -Dir <folder> [-Title <text>] [-WatchPid <pid>] [-LingerSeconds <n>]
# -WatchPid: when that process (the run) is gone the window says so and closes after -LingerSeconds
# (20), so the last images can still be looked at.
param([Parameter(Mandatory = $true)][string]$Dir,
      [string]$Title = 'Our cameras',
      [int]$WatchPid = 0,
      [int]$LingerSeconds = 20)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
# DPI aware, so a scaled display (150 %) draws it sharp; pixel sizes below are times $k.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ViewDpi {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
[void][ViewDpi]::SetProcessDPIAware()
$k = [ViewDpi]::GetDpiForSystem() / 96.0
# A viewer must not compete with the run for the CPU.
try { [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal' } catch { }
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "${Title}: $Dir"
$form.StartPosition = 'Manual'
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Size = New-Object System.Drawing.Size([int]($screen.Width * 0.72), [int]($screen.Height * 0.92))
$form.Location = New-Object System.Drawing.Point(($screen.Right - $form.Width - [int](10 * $k)), ($screen.Top + [int](10 * $k)))
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 24, 28)
$form.ForeColor = [System.Drawing.Color]::White

$status = New-Object System.Windows.Forms.Label
$status.AutoSize = $false
$status.Dock = 'Top'; $status.Height = [int](26 * $k); $status.TextAlign = 'MiddleLeft'
$legend = '  per camera: the image it produced (top), its depth, near bright (bottom left), its segmentation by body (bottom right)'
$status.Text = '  waiting for the first render ...'
$grid = New-Object System.Windows.Forms.TableLayoutPanel
$grid.Dock = 'Fill'; $grid.RowCount = 1; $grid.ColumnCount = 1
$form.Controls.Add($grid)
$form.Controls.Add($status)

# per camera: a column with a caption and the picture
$cams = [ordered]@{}      # name -> @{ Caption; Pic; Stamp }

function Add-Camera([string]$name) {
    $col = New-Object System.Windows.Forms.TableLayoutPanel
    $col.Dock = 'Fill'; $col.RowCount = 2; $col.ColumnCount = 1
    [void]$col.RowStyles.Add((New-Object System.Windows.Forms.RowStyle('Absolute', [int](46 * $script:k))))
    [void]$col.RowStyles.Add((New-Object System.Windows.Forms.RowStyle('Percent', 100)))
    $cap = New-Object System.Windows.Forms.Label
    $cap.AutoSize = $false
    $cap.Dock = 'Fill'; $cap.TextAlign = 'MiddleLeft'; $cap.Text = "  $name"
    $cap.Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
    $pic = New-Object System.Windows.Forms.PictureBox
    $pic.Dock = 'Fill'; $pic.SizeMode = 'Zoom'; $pic.BackColor = [System.Drawing.Color]::Black
    $col.Controls.Add($cap, 0, 0); $col.Controls.Add($pic, 0, 1)
    $n = $script:cams.Count
    if ($n -gt 0) { $script:grid.ColumnCount = $n + 1 }
    $script:grid.ColumnStyles.Clear()
    for ($i = 0; $i -le $n; $i++) {
        [void]$script:grid.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle('Percent', (100.0 / ($n + 1)))))
    }
    $script:grid.Controls.Add($col, $n, 0)
    $script:cams[$name] = @{ Caption = $cap; Pic = $pic; Stamp = [DateTime]::MinValue }
}

# Files are opened so that the writer (the run, in WSL) can replace them meanwhile:
# share Read, Write and Delete; the bytes are copied to memory at once.
function Read-Bytes([string]$path) {
    $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
                                 [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
    try {
        $ms = New-Object System.IO.MemoryStream
        $fs.CopyTo($ms)
        return , $ms.ToArray()
    } finally { $fs.Dispose() }
}

function Load-Image([string]$path) {
    try {
        $ms = New-Object System.IO.MemoryStream(, (Read-Bytes $path))
        return [System.Drawing.Image]::FromStream($ms)
    } catch { return $null }
}

# The run is watched through one Process object opened now: its handle pins the PID (a freed PID
# can go to another process within seconds, which would keep this window open for good) and
# HasExited says when the run is over.  A run that is gone already starts the countdown at once.
$script:runGone = $null     # when the watched process was first seen gone
$script:watch = $null
if ($WatchPid -gt 0) {
    try {
        $script:watch = [System.Diagnostics.Process]::GetProcessById($WatchPid)
        [void]$script:watch.HasExited
    } catch { $script:watch = $null; $script:runGone = Get-Date }
}
$script:visible = $false
$script:shows = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 200
$timer.Add_Tick({
    # run.ps1 starts this script with a hidden console (-WindowStyle Hidden), and Windows hands that
    # start-up state (hidden) to the first ShowWindow call of the process, which may be this form's
    # own: the form is then shown to .NET but not to Windows, and stays invisible.  While it is not
    # visible, one throwaway call (SW_SHOWDEFAULT) takes the start-up state if it is still unused
    # and the next (SW_SHOWNOACTIVATE) shows the form without taking the keyboard from the
    # terminal; tests/test_camera_view_script.py checks the calls, and with SB_WINDOW_TESTS=1 the
    # real window.  A check each tick, for 10 s, makes it hold whichever call came first.
    if (-not $script:visible -and $script:shows -lt 50) {
        $h = $script:form.Handle
        if ([ViewDpi]::IsWindowVisible($h)) { $script:visible = $true }
        else {
            $script:shows++
            [void][ViewDpi]::ShowWindow($h, 10)
            [void][ViewDpi]::ShowWindow($h, 4)
        }
    }
    if ($WatchPid -gt 0 -and ($null -ne $script:runGone -or $script:watch.HasExited)) {
        if ($null -eq $script:runGone) { $script:runGone = Get-Date }
        $left = $LingerSeconds - [int]((Get-Date) - $script:runGone).TotalSeconds
        if ($left -le 0) { $script:timer.Stop(); $script:form.Close(); return }
        $script:status.Text = "  the run has ended: its last images stay for $left s more"
    }
    $jsons = @(Get-ChildItem -LiteralPath $Dir -Filter '*.json' -File -ErrorAction SilentlyContinue)
    # eye first, then wrist, then any other
    $order = @($jsons | Sort-Object { switch ($_.BaseName) { 'eye' { 0 } 'wrist' { 1 } default { 2 } } }, Name)
    foreach ($j in $order) {
        $name = $j.BaseName
        if (-not $script:cams.Contains($name)) { Add-Camera $name }
        $c = $script:cams[$name]
        if ($j.LastWriteTimeUtc -le $c.Stamp) { continue }
        try { $meta = [System.Text.Encoding]::UTF8.GetString((Read-Bytes $j.FullName)) | ConvertFrom-Json } catch { continue }
        $img = Load-Image (Join-Path $Dir "$name.png")
        if ($null -eq $img) { continue }
        $old = $c.Pic.Image
        $c.Pic.Image = $img
        if ($old) { $old.Dispose() }
        $where = if ($meta.plan) { "plan $($meta.plan), step $($meta.step) ($($meta.action))" } else { 'outside a plan step (set-up, boxelization)' }
        $depth = if ($meta.depth_m) { "   depth $($meta.depth_m[0]) to $($meta.depth_m[1]) m" } else { '' }
        $c.Caption.Text = "  $name   render $($meta.n)   $($meta.clock)   $($meta.size)`n  $where$depth"
        $c.Stamp = $j.LastWriteTimeUtc
        if ($null -eq $script:runGone) { $script:status.Text = $legend }
    }
})
$timer.Start()
$form.Add_FormClosed({ $script:timer.Stop() })
[void]$form.ShowDialog()
