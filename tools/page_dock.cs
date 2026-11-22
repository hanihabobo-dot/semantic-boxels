// The holder of the page beside our own window: tools/page_dock.ps1 compiles this file and
// calls PageDock.Run.  What it does and why is in that script's head; this file is the how.
//
//   Place        the arithmetic, and nothing else: where the page's window goes and which part
//                of it stays visible, from the simulator's rectangle, the screen's work area and
//                the page window's own margins.  tests/test_page_dock.py reads it.
//   Choose       which of the simulator windows open now is this run's, and nothing else.
//   Run          waits for the two windows, then keeps them together until one of them or the
//                run is gone: Sync (place and cut), Raise and RaiseSim (the two come to the
//                front together), OnEvent (the windows' own moves, as Windows reports them) and
//                Tick (four times a second: are both still there; a sync in case an event was
//                missed).  Its log says which windows it took and how Windows describes them.
//   Describe,    read only, and TryRaise, TryRaiseSim: for the trial on a desktop that is not
//   ContentOf... shown (tracks/dbgcams/checks/dock_trial.ps1).
//
// Reports of Windows can arrive inside Sync while it waits in SetWindowPos on the other
// program's window; the Sync that runs then and the outer one may each place once more, and the
// look four times a second settles it.
//
// It touches two windows that are not its own, and only so: the page's browser window is moved,
// sized, cut to its page (a window region), shown, minimised and moved in the stacking order;
// the simulator's window is only read, and moved in the stacking order when the page is clicked.
// Nothing is sent to either window (no message, no key, no click), and nothing here reaches the run.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public static class PageDock
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int L, T, R, B;
        public int W { get { return R - L; } }
        public int H { get { return B - T; } }
        public override string ToString() { return L + "," + T + "," + R + "," + B; }
    }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)]
    struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam; public IntPtr lParam; public uint time; public POINT pt; }
    [StructLayout(LayoutKind.Sequential)]
    struct MONITORINFO { public int cbSize; public RECT rcMonitor; public RECT rcWork; public uint dwFlags; }
    [StructLayout(LayoutKind.Sequential)]
    struct WINDOWPLACEMENT { public int length; public int flags; public int showCmd; public POINT ptMin; public POINT ptMax; public RECT rcNormal; }

    delegate bool EnumProc(IntPtr h, IntPtr l);
    delegate void WinEventProc(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time);

    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern int SetWindowRgn(IntPtr h, IntPtr rgn, bool redraw);
    [DllImport("user32.dll")] static extern int GetWindowRgnBox(IntPtr h, out RECT r);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr h, int index);
    [DllImport("gdi32.dll")] static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr o);
    [DllImport("user32.dll")] static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);
    [DllImport("user32.dll")] static extern bool SetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);
    [DllImport("user32.dll")] static extern IntPtr MonitorFromWindow(IntPtr h, uint flags);
    [DllImport("user32.dll")] static extern bool GetMonitorInfo(IntPtr m, ref MONITORINFO i);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr c);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
    [DllImport("user32.dll")] static extern IntPtr SetWinEventHook(uint min, uint max, IntPtr mod, WinEventProc proc, uint pid, uint thread, uint flags);
    [DllImport("user32.dll")] static extern bool UnhookWinEvent(IntPtr hook);
    [DllImport("user32.dll")] static extern int GetMessage(out MSG m, IntPtr h, uint min, uint max);
    [DllImport("user32.dll")] static extern bool TranslateMessage(ref MSG m);
    [DllImport("user32.dll")] static extern IntPtr DispatchMessage(ref MSG m);
    [DllImport("user32.dll")] static extern UIntPtr SetTimer(IntPtr h, UIntPtr id, uint ms, IntPtr proc);
    [DllImport("user32.dll")] static extern bool KillTimer(IntPtr h, UIntPtr id);
    [DllImport("user32.dll")] static extern void PostQuitMessage(int code);

    // ----- the arithmetic -------------------------------------------------------------------

    public const int Right = 1, Left = 2, OverRight = 3, OverLeft = 4;

    public struct Plan
    {
        public RECT Window;     // the page's whole window, on the screen
        public RECT Region;     // the part of it that stays visible, from the window's own corner
        public int Side;        // Right, Left, OverRight or OverLeft
        public int Width;       // the visible part's width
    }

    /// Where the page goes.  `sim` is the simulator's window as seen and `work` the screen
    /// without the taskbar.  `dl` and `dt` are how far the page lies inside its browser window
    /// from the left and from the top (the browser's invisible border and its title bar), `dr`
    /// and `db` how much of the window is kept beyond the page on the right and below.  The
    /// visible part gets the simulator's top and height.  Where at least `min` pixels are free
    /// beside the simulator it lies flush against it, `want` wide or as wide as the room: on
    /// the right (Right), else on the left (Left).  Where neither side has that room it is
    /// `min` wide at the screen's edge and lies over the simulator's edge by what is missing
    /// (OverRight, OverLeft: the side with more room).  `sideNow` (0: none yet) keeps the page
    /// on its side while that side still serves, so that it does not jump while the simulator
    /// is dragged.
    public static Plan Place(RECT sim, RECT work, int dl, int dt, int dr, int db, int want, int min, int sideNow)
    {
        int roomR = work.R - sim.R, roomL = sim.L - work.L;
        int side;
        if (sideNow == Right && roomR >= min) side = Right;
        else if (sideNow == Left && roomL >= min) side = Left;
        else if (roomR >= min) side = Right;
        else if (roomL >= min) side = Left;
        else if (sideNow == Right || sideNow == OverRight) side = OverRight;
        else if (sideNow == Left || sideNow == OverLeft) side = OverLeft;
        else side = roomR >= roomL ? OverRight : OverLeft;
        int width = side == Right ? Math.Min(want, roomR) : side == Left ? Math.Min(want, roomL) : min;
        RECT c = new RECT();
        c.T = sim.T; c.B = sim.B;
        if (side == Right) { c.L = sim.R; c.R = c.L + width; }
        else if (side == Left) { c.R = sim.L; c.L = c.R - width; }
        else if (side == OverRight) { c.R = work.R; c.L = c.R - width; }
        else { c.L = work.L; c.R = c.L + width; }
        Plan p = new Plan();
        p.Side = side; p.Width = width;
        p.Window.L = c.L - dl; p.Window.T = c.T - dt; p.Window.R = c.R + dr; p.Window.B = c.B + db;
        p.Region.L = dl; p.Region.T = dt; p.Region.R = dl + width; p.Region.B = dt + c.H;
        return p;
    }

    /// Which of the simulator windows open now (`open`, the topmost first) is this run's.
    /// `before` are the ones that were open when the holder last looked without the run's page
    /// answering, so before the run opened its window.  One that opened since is the run's (the
    /// topmost of them).  When none has, the list may have been taken late: then the run is
    /// asked, and once it has drawn its window (`runWindowOpen`) a single open window is the
    /// run's.  Returns the window, 0 for none yet, -1 when the run's window is open and there
    /// is more than one to choose from (the holder then takes none).
    public static long Choose(IList<long> open, ICollection<long> before, bool runWindowOpen)
    {
        foreach (long h in open) if (!before.Contains(h)) return h;
        if (!runWindowOpen || open.Count == 0) return 0;
        return open.Count == 1 ? open[0] : -1;
    }

    // ----- reading windows ------------------------------------------------------------------

    static string Title(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
    static string Class(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    static string ProcName(IntPtr h)
    {
        uint pid; GetWindowThreadProcessId(h, out pid);
        try { using (Process p = Process.GetProcessById((int)pid)) return p.ProcessName; } catch { return ""; }
    }
    /// The run's process, opened once: asked four times a second whether it has ended, and a
    /// process number given to another program later is never taken for it.
    static Process watched;
    static bool RunAlive()
    {
        if (watch == 0) return true;
        try { return watched != null && !watched.HasExited; } catch { return false; }
    }

    /// The simulator's windows open now, the topmost first: visible, `title` in the title,
    /// and of a process named `process` ('' takes any).
    public static List<long> FindSim(string title, string process)
    {
        var found = new List<long>();
        EnumWindows((h, l) =>
        {
            if (IsWindowVisible(h) && Title(h).IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0
                    && (process.Length == 0 || String.Equals(ProcName(h), process, StringComparison.OrdinalIgnoreCase)))
                found.Add(h.ToInt64());
            return true;
        }, IntPtr.Zero);
        return found;
    }

    /// A page in a browser window of its own carries the page's title and nothing more; a
    /// browser window with tabs that shows the page adds the browser's name ("... - Microsoft
    /// Edge").  Set (page_dock.ps1 sets it once it knows the run's page), only a window whose
    /// title IS the page's title is taken, so a person's own browser window with the page in a
    /// tab is never cut or moved.  Not set (the trial's stand-in pages): the title's start.
    public static bool WholeTitle;

    /// The page's browser window: visible, its title starts with `titleStart` (or is it, see
    /// WholeTitle), its window class starts with `classStart` ('' takes any).
    public static long FindPage(string titleStart, string classStart)
    {
        long found = 0;
        EnumWindows((h, l) =>
        {
            if (!IsWindowVisible(h)) return true;
            string t = Title(h);
            if ((WholeTitle ? t == titleStart : t.StartsWith(titleStart, StringComparison.Ordinal))
                    && (classStart.Length == 0 || Class(h).StartsWith(classStart, StringComparison.Ordinal)))
            { found = h.ToInt64(); return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    /// A window as seen: without the invisible borders Windows puts around it.
    static RECT Frame(IntPtr h)
    {
        RECT r;
        if (DwmGetWindowAttribute(h, 9, out r, 16) != 0 || r.R <= r.L) GetWindowRect(h, out r);
        return r;
    }

    /// How far what is SEEN of the simulator's window lies inside the rectangle Windows gives
    /// for it, in real pixels from the left, the top, the right and the bottom (page_dock.ps1's
    /// -SimInset).  All zero: the rectangle is taken as what is seen.  The simulator's window
    /// is drawn by WSL's window host, which may send its shadow as part of the window; Windows
    /// has no call that tells, so this is a measured number.
    public static RECT Inset;
    public static void SetInset(int left, int top, int right, int bottom)
    {
        Inset.L = left; Inset.T = top; Inset.R = right; Inset.B = bottom;
    }
    static RECT Seen(IntPtr simulator)
    {
        RECT r = Frame(simulator);
        r.L += Inset.L; r.T += Inset.T; r.R -= Inset.R; r.B -= Inset.B;
        return r;
    }

    /// The page inside its browser window: the browser's child window of class `childClass`
    /// that holds the page (the largest visible one).  `found` is false without such a child;
    /// then the whole window counts as the page and nothing is cut.
    public static RECT ContentOf(long window, string childClass)
    {
        bool found;
        return Content(new IntPtr(window), childClass, out found);
    }
    static RECT Content(IntPtr page, string childClass, out bool found)
    {
        RECT best = new RECT(); long area = 0;
        if (childClass.Length > 0)
            EnumChildWindows(page, (h, l) =>
            {
                if (IsWindowVisible(h) && Class(h) == childClass)
                {
                    RECT r; GetWindowRect(h, out r);
                    long a = (long)(r.R - r.L) * (r.B - r.T);
                    if (a > area) { area = a; best = r; }
                }
                return true;
            }, IntPtr.Zero);
        found = area > 0;
        if (found) return best;
        RECT w; GetWindowRect(page, out w);
        return w;
    }

    static RECT Work(IntPtr h)
    {
        var info = new MONITORINFO(); info.cbSize = Marshal.SizeOf(typeof(MONITORINFO));
        GetMonitorInfo(MonitorFromWindow(h, 2), ref info);
        return info.rcWork;
    }

    /// One window in a line, for the trial: where it is, as seen, its region, its state.
    public static string Describe(long window)
    {
        IntPtr h = new IntPtr(window);
        if (!IsWindow(h)) return "gone";
        RECT r, box; GetWindowRect(h, out r);
        int kind = GetWindowRgnBox(h, out box);
        return "rect=" + r + " frame=" + Frame(h) + " region=" + kind + ":" + box
             + " visible=" + IsWindowVisible(h) + " iconic=" + IsIconic(h) + " zoomed=" + IsZoomed(h)
             + " class=" + Class(h) + " title=[" + Title(h) + "]";
    }

    /// For the trial: a window as seen, its whole rectangle, the box of its region (all zero
    /// without one) and the screen's work area under it.
    public static RECT FrameOf(long window) { return Frame(new IntPtr(window)); }
    public static RECT RectOf(long window) { RECT r; GetWindowRect(new IntPtr(window), out r); return r; }
    public static RECT RegionOf(long window)
    {
        RECT box;
        return GetWindowRgnBox(new IntPtr(window), out box) >= 2 ? box : new RECT();
    }
    public static RECT WorkOf(long window) { return Work(new IntPtr(window)); }

    /// The handles of all top-level windows, the topmost first (the trial reads the order).
    public static List<long> Stack()
    {
        var all = new List<long>();
        EnumWindows((h, l) => { all.Add(h.ToInt64()); return true; }, IntPtr.Zero);
        return all;
    }

    /// For the trial: whether a window is shown, and whether it is set to stay above all
    /// others (the holder must never leave the page so).
    public static bool VisibleOf(long window) { return IsWindowVisible(new IntPtr(window)); }
    public static bool TopmostOf(long window) { return (GetWindowLongPtr(new IntPtr(window), -20).ToInt64() & 0x8) != 0; }

    /// For the trial: Windows reports no "came to the front" on a desktop that is not shown,
    /// so the holder's two answers to that report are called here, on the two windows named.
    public static void TryRaise(long simWindow, long pageWindow)
    {
        sim = new IntPtr(simWindow); page = new IntPtr(pageWindow);
        Raise();
    }
    public static void TryRaiseSim(long simWindow, long pageWindow)
    {
        sim = new IntPtr(simWindow); page = new IntPtr(pageWindow);
        RaiseSim();
    }

    // ----- holding the two together ---------------------------------------------------------

    const int GiveUpMs = 30000;     // what is missing for the pair stays missing this long: the holder ends and says why
    const int Slack = 3;            // pixels of window kept beyond the page on the right and below (see Sync)
    static IntPtr sim, page;
    static string childClass;
    static int wantAt100, minAt100, side, watch, missing;
    static bool done, away, havePlacement, trace;
    static WINDOWPLACEMENT saved;
    static string lastLine = "", lastSim = "";
    static int unasked;             // placings in a row, close together, while the simulator stood still
    static long quietUntil, lastUnasked, hiddenSince = -1;
    static readonly Stopwatch life = Stopwatch.StartNew();
    static StreamWriter log;
    static WinEventProc proc;       // kept here: the hooks call it for as long as the holder lives

    static void Note(string text)
    {
        if (log == null) return;
        try { log.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " " + text); } catch { }
    }

    /// Place the page's window and cut it to its page.  Nothing moves when it is in place.
    ///
    /// The browser lays its page out in whole units of its own, so the page's right and bottom
    /// edges inside the window come out a pixel or two different after every resize.  A plan
    /// that followed those edges never came to rest (the trial of 2026-11-22: the window was
    /// placed again and again, a pixel apart).  So only the page's left and top inside the
    /// window are read (they do not change), the window is kept Slack pixels larger than the
    /// page needs on the right and below, and the cut, not the page's own edge, is the edge
    /// that is seen.
    static void Sync(string why)
    {
        if (!IsWindow(sim) || !IsWindow(page)) return;
        var took = Stopwatch.StartNew();
        if (!IsWindowVisible(sim) || IsIconic(sim))
        {
            // The simulator is minimised: the page goes down with it at once.  It is hidden:
            // only when it stays so, since a window that is closing is hidden for a moment
            // first, and the page is then given back whole (Finish), not put down.
            if (IsIconic(sim)) hiddenSince = -1;
            else
            {
                if (hiddenSince < 0) hiddenSince = life.ElapsedMilliseconds;
                if (life.ElapsedMilliseconds - hiddenSince < 700) return;
            }
            if (!IsIconic(page)) { ShowWindow(page, 7); Note(why + ": the simulator is down, the page too"); }
            away = true;
            return;
        }
        hiddenSince = -1;
        if (away || IsIconic(page) || IsZoomed(page)) ShowWindow(page, 4);     // back, not activated
        away = false;
        RECT s = Seen(sim);
        RECT work = Work(sim);
        double k = GetDpiForWindow(page) / 96.0;
        if (k < 0.5) k = 1.0;
        int want = (int)Math.Round(wantAt100 * k), min = (int)Math.Round(minAt100 * k);
        RECT w; GetWindowRect(page, out w);
        bool found;
        RECT c = Content(page, childClass, out found);
        int dl = 0, dt = 0, dr = 0, db = 0;
        if (found) { dl = Math.Max(0, c.L - w.L); dt = Math.Max(0, c.T - w.T); dr = dl + Slack; db = dl + Slack; }
        Plan p = Place(s, work, dl, dt, dr, db, want, min, side);
        side = p.Side;
        string simNow = s.ToString();
        if (simNow != lastSim) { lastSim = simNow; unasked = 0; }
        if (w.L != p.Window.L || w.T != p.Window.T || w.R != p.Window.R || w.B != p.Window.B)
        {
            // A window that leaves its place again and again while the simulator stands still
            // is put back a few times and then left alone for a while: the holder never fights
            // for it.  Placings more than five seconds apart are not such a fight.
            long now = life.ElapsedMilliseconds;
            if (now < quietUntil) return;
            if (now - lastUnasked > 5000) unasked = 0;
            lastUnasked = now;
            if (++unasked > 8)
            {
                quietUntil = now + 3000; unasked = 0;
                Note("the page's window does not stay where it is put; it is left alone for three seconds");
                return;
            }
            // no activation, the stacking order as it is
            SetWindowPos(page, IntPtr.Zero, p.Window.L, p.Window.T, p.Window.W, p.Window.H, 0x0004 | 0x0010);
            if (trace) Note("  placing took " + took.ElapsedMilliseconds + " ms (" + why + ")");
        }
        RECT box;
        int kind = GetWindowRgnBox(page, out box);
        bool cut = found
            ? kind >= 2 && box.L == p.Region.L && box.T == p.Region.T && box.R == p.Region.R && box.B == p.Region.B
            : kind == 0;
        if (!cut)
        {
            if (found)
            {
                IntPtr region = CreateRectRgn(p.Region.L, p.Region.T, p.Region.R, p.Region.B);
                if (SetWindowRgn(page, region, true) == 0) DeleteObject(region);    // taken by Windows unless it failed
            }
            else SetWindowRgn(page, IntPtr.Zero, true);     // no page found inside the window: nothing is cut
        }
        string line = "sim " + s + " page " + p.Window + " cut " + (found ? p.Region.ToString() : "none") + " side " + side;
        if (line != lastLine) { lastLine = line; Note(why + ": " + line + (trace ? " (" + took.ElapsedMilliseconds + " ms)" : "")); }
    }

    /// The simulator came to the front: the page comes with it, without taking the keyboard.
    /// A program in the background may not simply put a window on top; it may make it stay
    /// on top and then take that back, which leaves it above the other windows.
    static void Raise()
    {
        if (!IsWindow(page) || IsIconic(page)) return;
        SetWindowPos(page, new IntPtr(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
        SetWindowPos(page, new IntPtr(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
    }

    /// The page came to the front: the simulator comes right behind it.
    static void RaiseSim()
    {
        if (IsWindow(sim) && !IsIconic(sim)) SetWindowPos(sim, page, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
    }

    /// The page's window as a window of its own again: whole, and where it was before.
    static void Release()
    {
        if (!IsWindow(page)) return;
        SetWindowRgn(page, IntPtr.Zero, true);
        if (havePlacement)
        {
            saved.length = Marshal.SizeOf(typeof(WINDOWPLACEMENT));
            saved.showCmd = 4;
            SetWindowPlacement(page, ref saved);
        }
        Note("the page's window is its own again");
    }

    static void Finish(string why, bool release)
    {
        if (done) return;
        done = true;
        Note("ending: " + why);
        if (release) { try { Release(); } catch (Exception e) { Note("release: " + e.Message); } }
        PostQuitMessage(0);
    }

    static void Tick()
    {
        if (!IsWindow(page)) { Finish("the page's window is gone", false); return; }
        if (!IsWindow(sim)) { if (++missing >= 2) Finish("the simulator's window is gone", true); return; }
        missing = 0;
        if (!RunAlive()) { Finish("the run has ended", true); return; }
        Sync("tick");
    }

    static void OnEvent(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time)
    {
        if (idObject != 0 || done) return;      // the window itself, not a part of it
        if (trace && (hwnd == sim || hwnd == page)) Note("  event " + ev.ToString("X") + (hwnd == sim ? " simulator" : " page"));
        try
        {
            if (hwnd == sim)
            {
                if (ev == 0x800B) Sync("the simulator moved");
                else if (ev == 0x0003) { Sync("the simulator in front"); Raise(); }
                else if (ev == 0x0016 || ev == 0x0017 || ev == 0x8002 || ev == 0x8003) Sync("the simulator shown or put down");
                else if (ev == 0x8001) Tick();
            }
            else if (hwnd == page)
            {
                if (ev == 0x800B) Sync("the page moved");
                else if (ev == 0x0003) RaiseSim();
                else if (ev == 0x8001) Tick();
            }
        }
        catch (Exception e) { Note("event " + ev.ToString("X") + ": " + e.Message); }
    }

    static HashSet<long> before, looked;

    /// The simulator windows that are open now.  Keep makes that list the one of the windows
    /// "open before this run's".  page_dock.ps1 looks before every ask of the page servers and
    /// keeps the list when no page gave the run's word back: the run starts its page before it
    /// opens its window, so the run's window was not open at that look, and a window which
    /// opens after it counts as new.
    public static int Look(string simTitle, string simProcess)
    {
        looked = new HashSet<long>(FindSim(simTitle, simProcess));
        return looked.Count;
    }
    public static void Keep() { before = looked; }

    /// Asks the run's page whether the run has shown a render, which it does only once its
    /// window is open (page_dock.ps1 sets it).  Asked only while no simulator window has opened
    /// since the list was kept, see Choose.  Not set: such a window is never taken.
    public static Func<bool> RunWindowOpen;

    /// Wait for the page's window and this run's simulator window, hold them together, end
    /// when one of them or the run (`watchPid`, 0: none) is gone.  Widths are pixels at 100 %
    /// scaling.  `traceAll`: the log also gets every report of Windows about the two windows
    /// and how long each placing took.  Returns
    ///   0  after holding
    ///   2  the run ended before its windows came
    ///   3  no run is watched and the windows did not come within `waitSeconds`
    ///   5  the run's window is open, more than one simulator window is, and none opened
    ///      after the holder's list: it cannot tell which is the run's and takes none
    ///   6  the run's window is open and no window with the simulator's title is found
    ///   7  the simulator's window is there and no browser window of its own shows the page
    /// (5 to 7 after GiveUpMs of that state; the log says which and why).
    public static int Run(string simTitle, string simProcess, string pageTitle, string pageClass,
                          string pageChildClass, int width, int minWidth, int watchPid, int waitSeconds,
                          string logPath, bool traceAll)
    {
        SetThreadDpiAwarenessContext(new IntPtr(-4));       // real pixels on every screen
        if (!String.IsNullOrEmpty(logPath))
        {
            // a log that cannot be written never stops the holder
            try
            {
                log = new StreamWriter(new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false));
                log.AutoFlush = true;
            }
            catch { log = null; }
        }
        childClass = pageChildClass ?? ""; wantAt100 = width; minAt100 = minWidth; watch = watchPid;
        side = 0; missing = 0; done = false; away = false; lastLine = ""; lastSim = ""; unasked = 0; quietUntil = 0; lastUnasked = 0; hiddenSince = -1; trace = traceAll;
        var hooks = new List<IntPtr>();
        UIntPtr timer = UIntPtr.Zero;
        bool held = false;
        try
        {
            if (watchPid != 0) { try { watched = Process.GetProcessById(watchPid); } catch { watched = null; } }
            if (before == null) { Look(simTitle, simProcess); Keep(); }
            Note("waiting; simulator windows open before: " + before.Count);
            var clock = Stopwatch.StartNew();
            bool open = false;
            long asked = -1000, lacksSince = 0;
            string lacks = "";
            while (true)
            {
                if (!RunAlive()) { Note("the run ended before its windows came"); return 2; }
                if (watchPid == 0 && clock.ElapsedMilliseconds > waitSeconds * 1000L) { Note("the windows did not come"); return 3; }
                page = new IntPtr(FindPage(pageTitle, pageClass));
                List<long> sims = FindSim(simTitle, simProcess);
                long pick = Choose(sims, before, open);
                if (pick == 0 && !open && RunWindowOpen != null && clock.ElapsedMilliseconds - asked >= 1000)
                {
                    // none has opened since the list was kept: has the run drawn its window?
                    asked = clock.ElapsedMilliseconds;
                    try { open = RunWindowOpen(); } catch { open = false; }
                    if (open) { Note("the run has drawn its window; simulator windows open: " + sims.Count); pick = Choose(sims, before, true); }
                }
                if (pick > 0 && page != IntPtr.Zero) { sim = new IntPtr(pick); break; }
                // What is missing for the pair, said when it changes.  When it stays missing
                // the holder ends with a code of its own, so that the launcher can say that
                // the page is not held.
                string now = pick > 0 ? "no browser window of its own shows the page (a window named exactly '" + pageTitle + "')"
                           : pick < 0 ? "the run's window is open, " + sims.Count + " simulator windows are, and none of them opened after the holder's list was taken: it cannot tell which is this run's and takes none"
                           : open ? "the run has drawn its window, and no window with '" + simTitle + "' in its title is found" + (simProcess.Length > 0 ? " among the windows of " + simProcess : "")
                           : "";
                if (now != lacks) { lacks = now; lacksSince = clock.ElapsedMilliseconds; if (now.Length > 0) Note("waiting: " + now); }
                if (lacks.Length > 0 && clock.ElapsedMilliseconds - lacksSince > GiveUpMs)
                {
                    Note("given up after " + (GiveUpMs / 1000) + " s: " + lacks);
                    return pick > 0 ? 7 : pick < 0 ? 5 : 6;
                }
                System.Threading.Thread.Sleep(150);
            }
            uint pidSim, pidPage;
            GetWindowThreadProcessId(sim, out pidSim);
            GetWindowThreadProcessId(page, out pidPage);
            saved = new WINDOWPLACEMENT(); saved.length = Marshal.SizeOf(typeof(WINDOWPLACEMENT));
            havePlacement = GetWindowPlacement(page, ref saved);
            held = true;
            Note("holding: simulator " + sim.ToInt64().ToString("X") + " [" + Title(sim) + "], page "
                 + page.ToInt64().ToString("X") + " [" + Title(page) + "]");
            // What the two windows are to Windows, before anything is placed: the look of the
            // pair on a real screen is measured against these lines (see Inset).
            Note("  the simulator's window " + (before.Contains(sim.ToInt64())
                 ? "was open when the holder's list was taken; taken as the only one, the run having drawn its window"
                 : "opened after the holder's list was taken"));
            Note("  simulator: " + Describe(sim.ToInt64()) + " process=" + ProcName(sim) + " dpi=" + GetDpiForWindow(sim)
                 + " work=" + Work(sim) + " inset=" + Inset + " taken as seen=" + Seen(sim));
            bool inside;
            RECT content = Content(page, childClass, out inside);
            Note("  page: " + Describe(page.ToInt64()) + " dpi=" + GetDpiForWindow(page)
                 + " its page inside=" + (inside ? content.ToString() : "not found"));
            foreach (long h in FindSim(simTitle, simProcess))
                if (h != sim.ToInt64())
                    Note("  another simulator window, left alone (" + (before.Contains(h) ? "open before" : "opened since") + "): " + Describe(h));
            proc = OnEvent;
            // The reports the holder acts on, of these two programs only: a window came to the
            // front (0003), was minimised or restored (0016, 0017), was closed, shown or hidden
            // (8001 to 8003), moved or resized (800B).  Narrow ranges: a browser reports much else.
            uint[] ranges = { 0x0003, 0x0003, 0x0016, 0x0017, 0x8001, 0x8003, 0x800B, 0x800B };
            uint[] programs = pidPage != pidSim ? new uint[] { pidSim, pidPage } : new uint[] { pidSim };
            int refused = 0;
            foreach (uint program in programs)
                for (int i = 0; i < ranges.Length; i += 2)
                {
                    IntPtr hook = SetWinEventHook(ranges[i], ranges[i + 1], IntPtr.Zero, proc, program, 0, 0x0002);
                    if (hook == IntPtr.Zero) refused++; else hooks.Add(hook);
                }
            if (refused > 0)
                Note("Windows refused " + refused + " of the holder's " + (programs.Length * ranges.Length / 2)
                     + " report hooks: for those the look four times a second stands in");
            timer = SetTimer(IntPtr.Zero, UIntPtr.Zero, 250, IntPtr.Zero);
            Sync("first");
            Raise();
            MSG m;
            while (!done && GetMessage(out m, IntPtr.Zero, 0, 0) > 0)
            {
                if (m.message == 0x0113 && m.hwnd == IntPtr.Zero) { Tick(); continue; }
                TranslateMessage(ref m);
                DispatchMessage(ref m);
            }
            return 0;
        }
        finally
        {
            if (timer != UIntPtr.Zero) KillTimer(IntPtr.Zero, timer);
            foreach (IntPtr hook in hooks) UnhookWinEvent(hook);
            if (held && !done) { try { Release(); } catch { } }      // an error on the way: the page is not left cut
            if (log != null) { try { log.Dispose(); } catch { } log = null; }
            if (watched != null) { try { watched.Dispose(); } catch { } watched = null; }
            before = null; looked = null;
        }
    }
}
