"""The console's sound (console_ui, 2026-10-30): retro sci-fi synth music
that follows what the robot is doing, quiet and slow.  One tune loops while
it acts (a pulsing bass, slow detuned pads, a sparse low melody with echo, a
faint airflow) and a calmer variant while it plans (the pads, a soft sine
sequence, a tick on the beat); a few soft effects mark the moments that
matter: power-on, the target found, a warning, a failed step, the mission
done, the mission failed.  Everything is synthesized here from sine,
triangle and noise waves into small WAV files (logs/console_sounds, ignored
by git) and played by Windows: the pipeline runs in WSL and WSL's interop
runs tools/console_speaker.ps1 in Windows PowerShell, one process that loops
the music and one that plays the effects, so nothing has to be installed.

Opt-in through the environment, set by run.ps1's -Music and -Sfx:
  SB_AUDIO=on      music and effects       SB_AUDIO=music   the loops only
  SB_AUDIO=sfx     the effects only        SB_VOICE=on      Windows' voice reads the
                                                            narration as well (off by default)
Best effort, and never into the console: a missing interop, a failed process
or a closed pipe only means silence.  Hani's brief (18:30): one or two tunes
of low melody and rhythm, less video game, more sci-fi retro, less of it.
"""
import math
import os
import queue
import random
import re
import shutil
import struct
import subprocess
import threading
import wave

REPO = os.path.dirname(os.path.abspath(__file__))
SPEAKER = os.path.join(REPO, 'tools', 'console_speaker.ps1')
VERSION = 2                     # bump when a piece changes: the files are regenerated
SOUND_DIR = os.path.join(REPO, 'logs', 'console_sounds', f'v{VERSION}')
POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
RATE = 22050
QUEUE_MAX = 3                   # pending sentences before the unimportant ones are dropped


def wanted():
    """(music, sfx, speech) from SB_AUDIO and SB_VOICE, or None when all off."""
    a = os.environ.get('SB_AUDIO', '').strip().lower()
    v = os.environ.get('SB_VOICE', '').strip().lower()
    music = a in ('on', '1', 'yes', 'true', 'music')
    sfx = a in ('on', '1', 'yes', 'true', 'sfx')
    speech = v in ('on', '1', 'yes', 'true', 'speech')
    if not (music or sfx or speech):
        return None
    return music, sfx, speech


# ---------------------------------------------------------------------------
# the synthesizer
# ---------------------------------------------------------------------------

_NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def midi(name):
    """'C5', 'G#4', 'Bb3' as a MIDI number."""
    m = re.fullmatch(r'([A-G])([#b]?)(-?\d)', name)
    n = _NOTE[m.group(1)] + (1 if m.group(2) == '#' else -1 if m.group(2) == 'b' else 0)
    return 12 * (int(m.group(3)) + 1) + n


def freq(name):
    return 440.0 * 2.0 ** ((midi(name) - 69) / 12.0)


class Mix:
    """A float sample buffer the voices add into."""

    def __init__(self, seconds):
        self.n = int(RATE * seconds)
        self.buf = [0.0] * self.n

    def tone(self, start, dur, hz, kind='sine', vol=0.2, attack=0.01, release=0.05,
             sweep=None, decay=None, detune=0.0):
        """One note: `kind` sine, triangle, square or noise; `attack` and
        `release` in seconds; `sweep` the frequency at the note's end;
        `decay` an exponential fade per second; `detune` a second
        oscillator that far above (a slow chorus)."""
        i0 = int(start * RATE)
        n = int(dur * RATE)
        a_n = max(1, int(attack * RATE))
        r_n = max(1, int(release * RATE))
        rng = random.Random(int(hz * 100) + i0)
        phase, phase2 = 0.0, 0.25
        for k in range(n):
            i = i0 + k
            if i >= self.n:
                break
            f = hz if sweep is None else hz + (sweep - hz) * (k / max(1, n))
            phase += f / RATE
            if kind == 'sine':
                s = math.sin(2 * math.pi * phase)
            elif kind == 'triangle':
                s = 4.0 * abs((phase % 1.0) - 0.5) - 1.0
            elif kind == 'square':
                s = 1.0 if (phase % 1.0) < 0.5 else -1.0
            else:
                s = rng.uniform(-1.0, 1.0)
            if detune and kind != 'noise':
                phase2 += f * (1.0 + detune) / RATE
                s2 = (math.sin(2 * math.pi * phase2) if kind == 'sine'
                      else 4.0 * abs((phase2 % 1.0) - 0.5) - 1.0)
                s = 0.5 * (s + s2)
            env = min(1.0, k / a_n) * min(1.0, (n - k) / r_n)
            if decay:
                env *= math.exp(-decay * k / RATE)
            self.buf[i] += vol * env * s

    def noise_bed(self, vol, window=60, lfo_hz=0.07):
        """A faint low-passed noise over the whole buffer, breathing slowly:
        the airflow of a ship."""
        rng = random.Random(7)
        white = [rng.uniform(-1.0, 1.0) for _ in range(self.n + window)]
        acc = sum(white[:window])
        for i in range(self.n):
            acc += white[i + window] - white[i]
            lfo = 0.6 + 0.4 * math.sin(2 * math.pi * lfo_hz * i / RATE)
            self.buf[i] += vol * lfo * acc / window * 3.0

    def echo(self, delay, feedback, taps=3, wrap=True):
        """Delayed, fading copies of the signal; wrapping ones cross the
        loop's end into its start, so a loop stays seamless."""
        d = int(delay * RATE)
        dry = list(self.buf)
        for k in range(1, taps + 1):
            gain = feedback ** k
            off = k * d
            for i in range(self.n):
                j = i + off
                if j < self.n:
                    self.buf[j] += gain * dry[i]
                elif wrap:
                    self.buf[j % self.n] += gain * dry[i]

    def add(self, other, gain=1.0):
        for i in range(min(self.n, other.n)):
            self.buf[i] += gain * other.buf[i]

    def normalize(self, peak):
        top = max(1e-9, max(abs(s) for s in self.buf))
        g = peak / top
        self.buf = [s * g for s in self.buf]

    def write(self, path):
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b''.join(struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767))
                                   for s in self.buf))


def _pad(mix, chords, bpm, beats_each, vol, attack=0.6, release=0.6, kind='triangle', detune=0.004):
    beat = 60.0 / bpm
    for c, names in enumerate(chords):
        for name in names:
            mix.tone(c * beats_each * beat, beats_each * beat, freq(name), kind, vol=vol,
                     attack=attack, release=release, detune=detune)


def _pulse(mix, roots, bpm, beats_each, step, vol, gate=0.55, kind='triangle', accents=(1.0, 0.7)):
    beat = 60.0 / bpm
    for c, name in enumerate(roots):
        t0 = c * beats_each * beat
        k = 0
        t = 0.0
        while t < beats_each * beat - 1e-9:
            mix.tone(t0 + t, step * beat * gate, freq(name), kind, vol=vol * accents[k % len(accents)],
                     attack=0.012, release=0.05)
            t += step * beat
            k += 1


def _phrase(mix, notes, bpm, vol, kind='sine', attack=0.12, release=0.25, detune=0.0):
    """notes: (beat, beats, name)."""
    beat = 60.0 / bpm
    for b, d, name in notes:
        mix.tone(b * beat, d * beat, freq(name), kind, vol=vol, attack=attack, release=release,
                 detune=detune)


BPM = 76        # both loops, so a switch between them keeps the pulse


def _cruise_loop():
    """While the robot acts: D minor, eight bars; a pulsing bass, detuned
    pads, a sparse low sine melody with echo, the airflow."""
    bars = 8
    beat = 60.0 / BPM
    mix = Mix(bars * 4 * beat)
    chords = (('D3', 'F3', 'A3'), ('Bb2', 'D3', 'F3'), ('F3', 'A3', 'C4'), ('C3', 'E3', 'G3'))
    _pad(mix, chords, BPM, 8, vol=0.06, attack=0.7, release=0.7)
    _pulse(mix, ('D2', 'Bb1', 'F2', 'C2'), BPM, 8, step=0.5, vol=0.17)
    lead = Mix(bars * 4 * beat)
    _phrase(lead, [(0, 2, 'A3'), (3, 1, 'D4'), (8, 3, 'F4'), (14, 2, 'E4'), (16, 2, 'C4'),
                   (19, 1, 'F4'), (24, 3, 'G4'), (28, 2, 'E4'), (30, 2, 'D4')],
            BPM, vol=0.12, attack=0.15, release=0.3)
    lead.echo(beat * 0.75, 0.33)
    mix.add(lead)
    mix.noise_bed(0.028)
    mix.normalize(0.38)
    return mix


def _drift_loop():
    """While the robot plans: the pads on a darker turn, a soft sine
    sequence with echo, a tick on the beat, the airflow; no pulse."""
    bars = 8
    beat = 60.0 / BPM
    mix = Mix(bars * 4 * beat)
    chords = (('D3', 'F3', 'A3'), ('G3', 'Bb3', 'D4'), ('Bb2', 'D3', 'F3'), ('A2', 'C#3', 'E3'))
    _pad(mix, chords, BPM, 8, vol=0.06, attack=0.9, release=0.9)
    seq = Mix(bars * 4 * beat)
    arps = (('D4', 'F4', 'A4', 'C5'), ('G3', 'Bb3', 'D4', 'F4'),
            ('Bb3', 'D4', 'F4', 'A4'), ('A3', 'C#4', 'E4', 'G4'))
    pattern = (0, 1, 2, 3, 2, 1, 0, 1)
    t = 0.0
    for chord in arps:
        for _ in range(4):                 # four times the pattern = 8 beats
            for p in pattern:
                seq.tone(t, 0.25 * beat * 0.5, freq(chord[p]), 'sine', vol=0.07,
                         attack=0.006, release=0.04)
                t += 0.25 * beat
    seq.echo(beat * 0.75, 0.35)
    mix.add(seq)
    for b in range(bars * 4):
        mix.tone(b * beat, 0.012, 1.0, 'noise', vol=0.05, attack=0.001, release=0.004, decay=150.0)
    mix.noise_bed(0.024)
    mix.normalize(0.34)
    return mix


def _startup():
    mix = Mix(1.9)
    mix.tone(0.0, 1.3, 110.0, 'sine', vol=0.2, attack=0.25, release=0.5, sweep=440.0)
    for name in ('D3', 'F3', 'A3'):
        mix.tone(0.2, 1.6, freq(name), 'triangle', vol=0.05, attack=0.5, release=0.6, detune=0.004)
    mix.normalize(0.4)
    return mix


def _found():
    mix = Mix(1.3)
    mix.tone(0.0, 0.18, freq('A4'), 'sine', vol=0.18, attack=0.01, release=0.08)
    mix.tone(0.18, 0.5, freq('D5'), 'sine', vol=0.18, attack=0.01, release=0.3)
    mix.echo(0.24, 0.35, wrap=False)
    mix.normalize(0.4)
    return mix


def _warn():
    mix = Mix(0.7)
    mix.tone(0.0, 0.14, freq('E4'), 'sine', vol=0.15, attack=0.01, release=0.08)
    mix.echo(0.18, 0.3, wrap=False)
    mix.normalize(0.3)
    return mix


def _fail():
    mix = Mix(0.6)
    mix.tone(0.0, 0.35, 72.0, 'sine', vol=0.3, attack=0.005, release=0.1, sweep=44.0, decay=5.0)
    mix.tone(0.0, 0.08, 1.0, 'noise', vol=0.07, attack=0.001, release=0.02, decay=40.0)
    mix.normalize(0.42)
    return mix


def _success():
    mix = Mix(3.0)
    for name in ('D3', 'F#3', 'A3', 'D4'):
        mix.tone(0.0, 2.7, freq(name), 'triangle', vol=0.06, attack=0.3, release=0.9, detune=0.004)
    lead = Mix(3.0)
    lead.tone(0.25, 0.35, freq('A4'), 'sine', vol=0.16, attack=0.04, release=0.15)
    lead.tone(0.6, 1.5, freq('D5'), 'sine', vol=0.16, attack=0.04, release=0.7)
    lead.echo(0.3, 0.3, wrap=False)
    mix.add(lead)
    mix.normalize(0.42)
    return mix


def _failure():
    mix = Mix(3.3)
    mix.tone(0.0, 3.0, freq('D2'), 'triangle', vol=0.12, attack=0.2, release=0.9, detune=0.003)
    for b, d, name in ((0.0, 0.6, 'D4'), (0.6, 0.6, 'C4'), (1.2, 0.6, 'Bb3'), (1.8, 1.2, 'A3')):
        mix.tone(b, d, freq(name), 'sine', vol=0.14, attack=0.05, release=0.3)
    mix.normalize(0.38)
    return mix


def _death():
    """The Wumpus world (2026-11-06): a pit or the wumpus ends the run.  One
    soft falling glide and a low thud at its end, in the style of `fail`."""
    mix = Mix(1.7)
    mix.tone(0.0, 0.9, 330.0, 'sine', vol=0.18, attack=0.01, release=0.2, sweep=58.0)
    mix.tone(0.85, 0.55, 55.0, 'sine', vol=0.32, attack=0.005, release=0.15, sweep=38.0, decay=6.0)
    mix.tone(0.85, 0.1, 1.0, 'noise', vol=0.07, attack=0.001, release=0.03, decay=40.0)
    mix.echo(0.3, 0.25, wrap=False)
    mix.normalize(0.42)
    return mix


def _gold():
    """The Wumpus world: the gold bar is held.  Three soft rising sine notes
    over a faint triangle shimmer, a little brighter than `found`."""
    mix = Mix(1.9)
    for i, name in enumerate(('D5', 'A5', 'D6')):
        mix.tone(0.09 * i, 0.5, freq(name), 'sine', vol=0.13, attack=0.005, release=0.35)
    mix.tone(0.3, 1.0, freq('F#5'), 'triangle', vol=0.05, attack=0.1, release=0.6, detune=0.004)
    mix.echo(0.27, 0.35, wrap=False)
    mix.normalize(0.4)
    return mix


PIECES = {
    'act': _cruise_loop, 'think': _drift_loop,                       # the loops
    'startup': _startup, 'found': _found, 'warn': _warn, 'fail': _fail,
    'success': _success, 'failure': _failure,                        # the effects
    'death': _death, 'gold': _gold,        # the Wumpus world; no VERSION bump, only the new files are rendered
}
LOOPS = ('act', 'think')


def ensure_sounds():
    """The pieces as WAV files, synthesized once per VERSION; {name: path}."""
    os.makedirs(SOUND_DIR, exist_ok=True)
    paths = {}
    for name, make in PIECES.items():
        p = os.path.join(SOUND_DIR, name + '.wav')
        if not os.path.exists(p):
            make().write(p)
        paths[name] = p
    return paths


# ---------------------------------------------------------------------------
# playback through Windows
# ---------------------------------------------------------------------------

def speakable(text):
    """A console line as a voice should say it: no markup, no glyphs, no
    timings, the units in words."""
    t = str(text).replace('`', '')
    t = re.sub(r'\s*\((?:[\d.]+ s|[\d]+ px|[^()]*\brad\b[^()]*)\)', '', t)
    for g in '●✻✔✘⚠⎿▣━─':
        t = t.replace(g, ' ')
    t = t.replace('…', '.').replace('·', ',').replace('_', ' ')
    t = re.sub(r'(\d) mm\b', r'\1 millimetres', t)
    t = re.sub(r'(\d) px\b', r'\1 pixels', t)
    return re.sub(r'\s+', ' ', t).strip()


def _powershell():
    return shutil.which('powershell.exe') or (POWERSHELL if os.path.exists(POWERSHELL) else None)


def _winpath(path):
    """A Linux path as Windows sees it (wslpath), or None."""
    try:
        out = subprocess.run(['wslpath', '-w', path], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


class _Child:
    """One console_speaker.ps1 process: command lines in, 'ok' lines out."""

    def __init__(self, ps, script, mode, voice_name='', rate=0):
        args = [ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', script, '-Mode', mode, '-Rate', str(rate)]
        if voice_name:
            args += ['-VoiceName', voice_name]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                     errors='replace', bufsize=1)
        self.ok = self._read() == 'ready'

    def _read(self):
        try:
            return self.proc.stdout.readline().strip()
        except Exception:
            return ''

    def send(self, line):
        """One command, then its 'ok' (speech: when the sentence is over)."""
        try:
            self.proc.stdin.write(line.replace('\n', ' ') + '\n')
            self.proc.stdin.flush()
        except Exception:
            self.ok = False
            return False
        if self._read() != 'ok':
            self.ok = False
            return False
        return True

    def close(self):
        try:
            self.proc.stdin.write('quit\n')
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except Exception:
            pass


class Audio:
    def __init__(self, music=True, sfx=True, speech=False):
        self.want_music, self.want_sfx, self.want_speech = music, sfx, speech
        self.voice_name = os.environ.get('SB_VOICE_NAME', '').strip()
        try:
            self.rate = int(os.environ.get('SB_VOICE_RATE', '1'))
        except ValueError:
            self.rate = 1
        self._q = queue.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self._stop = False
        self._music_child = self._sfx_child = self._say_child = None
        self._paths = {}
        self._loop = None
        self._thread = threading.Thread(target=self._run, name='console-audio', daemon=True)
        self._thread.start()

    # ----- the console's side -----------------------------------------------

    def music(self, name):
        """Switch the loop (None stops it); the same loop again is nothing."""
        if self.want_music and not self._stop:
            self._idle.clear()
            self._q.put(('music', name, True))

    def sfx(self, name):
        """An effect by name; names without a piece (the console marks more
        moments than this quiet set plays) are nothing."""
        if self.want_sfx and not self._stop and name in PIECES and name not in LOOPS:
            self._idle.clear()
            self._q.put(('sfx', name, True))

    def say(self, text, important=False):
        if self.want_speech and not self._stop:
            t = speakable(text)
            if t:
                self._idle.clear()
                self._q.put(('say', t, important))

    def drain(self, timeout=2.0):
        """Wait until everything queued has been handed over."""
        self._idle.wait(timeout)

    def close(self):
        self._stop = True
        self._q.put(('quit', '', True))

    # ----- the worker ------------------------------------------------------------

    def _start(self):
        ps = _powershell()
        script = _winpath(SPEAKER) if ps else None
        if not ps or not script or not os.path.exists(SPEAKER):
            return False
        if self.want_music or self.want_sfx:
            win_dir = _winpath(SOUND_DIR)
            if win_dir:
                for name, path in ensure_sounds().items():
                    self._paths[name] = win_dir.rstrip('\\') + '\\' + os.path.basename(path)
        if self.want_music and self._paths:
            self._music_child = _Child(ps, script, 'play')
            if not self._music_child.ok:
                self._music_child = None
        if self.want_sfx and self._paths:
            self._sfx_child = _Child(ps, script, 'play')
            if not self._sfx_child.ok:
                self._sfx_child = None
        if self.want_speech:
            self._say_child = _Child(ps, script, 'say', self.voice_name, self.rate)
            if not self._say_child.ok:
                self._say_child = None
        return any(c is not None for c in (self._music_child, self._sfx_child, self._say_child))

    def _run(self):
        try:
            if not self._start():
                self._stop = True
        except Exception:
            self._stop = True
        while True:
            try:
                kind, arg, important = self._q.get(timeout=0.5)
            except queue.Empty:
                self._idle.set()
                continue
            try:
                if kind == 'quit':
                    break
                if self._stop:
                    continue
                if kind == 'music' and self._music_child is not None:
                    if arg != self._loop:
                        self._loop = arg
                        path = self._paths.get(arg) if arg else None
                        self._music_child.send(('loop ' + path) if path else 'stop')
                elif kind == 'sfx' and self._sfx_child is not None:
                    path = self._paths.get(arg)
                    if path:
                        self._sfx_child.send('play ' + path)
                elif kind == 'say' and self._say_child is not None:
                    if important or self._q.qsize() <= QUEUE_MAX:
                        self._say_child.send('say ' + arg)
            except Exception:
                pass
            finally:
                if self._q.empty():
                    self._idle.set()
        for child in (self._music_child, self._sfx_child, self._say_child):
            if child is not None:
                child.close()
        self._idle.set()


if __name__ == '__main__':
    # Render every piece and print where they are (a listen: play them in
    # Windows, or run.ps1 -Music).
    for name, path in ensure_sounds().items():
        print(name, path)
