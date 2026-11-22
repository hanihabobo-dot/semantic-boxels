// The holder of the page beside our own window: tools/page_dock.ps1 compiles this file and
// calls PageDock.Run.  What it does and why is in that script's head; this file is the how.
//
//   Place        the arithmetic, and nothing else: where the page's window goes and which part
//                of it stays visible, from the simulator's rectangle, the screen's work area and
//                the page window's own margins.  tests/test_page_dock.py reads it.
//   Run          waits for the two windows, then keeps them together until one of them or the
//                run is gone: Sync (place and cut), Raise and RaiseSim (the two come to the
//                front together), OnEvent (the windows' own moves, as Windows reports them) and
//                Tick (four times a second: are both still there; a sync in case an event was
//                missed).
//   Describe,    read only, for the trial on a hidden desktop
//   ContentOf    (tracks/dbgcams/checks/dock_trial.ps1).
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

    // ----- reading windows ------------------------------------------------------------------

    static string Title(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
    static string Class(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    static string ProcName(IntPtr h)
    {
        uint pid; GetWindowThreadProcessId(h, out pid);
        try { return Process.GetProcessById((int)pid).ProcessName; } catch { return ""; }
    }
    static bool Alive(int pid)
    {
        try { return !Process.GetProcessById(pid).HasExited; } catch { return false; }
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

    // ----- holding the two together ---------------------------------------------------------

    const int OldAfterMs = 20000;   // a simulator window that was open before this run is taken only after this long
    const int Slack = 3;            // pixels of window kept beyond the page on the right and below (see Sync)
    static IntPtr sim, page;
    static string childClass;
    static int wantAt100, minAt100, side, watch, missing;
    static bool done, away, havePlacement, trace;
    static WINDOWPLACEMENT saved;
    static string lastLine = "", lastSim = "";
    static int unasked;             // placings in a row while the simulator stood still
    static long quietUntil, hiddenSince = -1;
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
        RECT s = Frame(sim);
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
            // A window that leaves its place while the simulator stands still is put back a few
            // times and then left alone for a while: the holder never fights for it.
            long now = life.ElapsedMilliseconds;
            if (now < quietUntil) return;
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
        if (watch != 0 && !Alive(watch)) { Finish("the run has ended", true); return; }
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

    static HashSet<long> before;

    /// The simulator windows that are open now, kept as "open before this run's": for a
    /// caller that has something to wait for before Run (page_dock.ps1 waits for the run's
    /// page to answer), so that a window which opens during that wait still counts as new.
    public static int Snapshot(string simTitle, string simProcess)
    {
        before = new HashSet<long>(FindSim(simTitle, simProcess));
        return before.Count;
    }

    /// Wait for the page's window and this run's simulator window, hold them together, end
    /// when one of them or the run (`watchPid`, 0: none) is gone.  Widths are pixels at 100 %
    /// scaling.  Returns 0 after holding, 2 when the run ended before its windows came, 3 when
    /// no run is watched and they did not come within `waitSeconds`.  `traceAll`: the log also
    /// gets every report of Windows about the two windows and how long each placing took.
    public static int Run(string simTitle, string simProcess, string pageTitle, string pageClass,
                          string pageChildClass, int width, int minWidth, int watchPid, int waitSeconds,
                          string logPath, bool traceAll)
    {
        SetThreadDpiAwarenessContext(new IntPtr(-4));       // real pixels on every screen
        if (!String.IsNullOrEmpty(logPath)) { log = new StreamWriter(logPath, true, new UTF8Encoding(false)); log.AutoFlush = true; }
        childClass = pageChildClass ?? ""; wantAt100 = width; minAt100 = minWidth; watch = watchPid;
        side = 0; missing = 0; done = false; away = false; lastLine = ""; lastSim = ""; unasked = 0; quietUntil = 0; hiddenSince = -1; trace = traceAll;
        IntPtr h1 = IntPtr.Zero, h2 = IntPtr.Zero;
        UIntPtr timer = UIntPtr.Zero;
        try
        {
            // This run's simulator window is one that opens while the holder waits.  One that
            // was open before (another program's, or a window left behind) is taken only when
            // no new one has come for a while after the page.  The list of those is taken
            // here, or earlier by Snapshot when the caller waits for something first.
            if (before == null) Snapshot(simTitle, simProcess);
            Note("waiting; simulator windows open before: " + before.Count);
            var clock = Stopwatch.StartNew();
            long pageSince = -1;
            while (true)
            {
                if (watchPid != 0 && !Alive(watchPid)) { Note("the run ended before its windows came"); return 2; }
                if (watchPid == 0 && clock.ElapsedMilliseconds > waitSeconds * 1000L) { Note("the windows did not come"); return 3; }
                page = new IntPtr(FindPage(pageTitle, pageClass));
                if (page != IntPtr.Zero)
                {
                    if (pageSince < 0) pageSince = clock.ElapsedMilliseconds;
                    List<long> sims = FindSim(simTitle, simProcess);
                    sim = IntPtr.Zero;
                    foreach (long h in sims) if (!before.Contains(h)) { sim = new IntPtr(h); break; }
                    if (sim == IntPtr.Zero && sims.Count > 0 && clock.ElapsedMilliseconds - pageSince > OldAfterMs)
                        sim = new IntPtr(sims[0]);
                    if (sim != IntPtr.Zero) break;
                }
                else pageSince = -1;
                System.Threading.Thread.Sleep(150);
            }
            uint pidSim, pidPage;
            GetWindowThreadProcessId(sim, out pidSim);
            GetWindowThreadProcessId(page, out pidPage);
            saved = new WINDOWPLACEMENT(); saved.length = Marshal.SizeOf(typeof(WINDOWPLACEMENT));
            havePlacement = GetWindowPlacement(page, ref saved);
            Note("holding: simulator " + sim.ToInt64().ToString("X") + " [" + Title(sim) + "], page "
                 + page.ToInt64().ToString("X") + " [" + Title(page) + "]");
            proc = OnEvent;
            // from 'a window came to the front' to 'a window moved', of these two programs only
            h1 = SetWinEventHook(0x0003, 0x800B, IntPtr.Zero, proc, pidSim, 0, 0x0002);
            if (pidPage != pidSim) h2 = SetWinEventHook(0x0003, 0x800B, IntPtr.Zero, proc, pidPage, 0, 0x0002);
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
            if (h1 != IntPtr.Zero) UnhookWinEvent(h1);
            if (h2 != IntPtr.Zero) UnhookWinEvent(h2);
            if (!done) { try { Release(); } catch { } }      // an error on the way: the page is not left cut
            if (log != null) { try { log.Dispose(); } catch { } log = null; }
            before = null;
        }
    }
}
