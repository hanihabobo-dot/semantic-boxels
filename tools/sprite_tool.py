#!/usr/bin/env python3
"""The sprite tool for the Semantic Boxels console art (console_art.py, the
animated pictograms console_ui draws beside its status line).

  python tools/sprite_tool.py check tools/sprites/pick.txt          validate one sprite, print its sheet
  python tools/sprite_tool.py check tools/sprites/pick.txt --color  the sheet with ANSI colours (256)
  python tools/sprite_tool.py assemble tools/sprites console/console_art.py
        every <key>.reviewed.txt (else <key>.txt) in the directory becomes one
        entry of SPRITES in the generated module (PALETTE and ASCII_MAP included)

The sprite file format (plain text, UTF-8, no quoting):

  key: pick
  width: 10
  period_ms: 200
  pingpong: no
  notes: one line on what it shows
  frame 1
  <glyph row 1>      exactly 5 glyph rows, each at most `width` characters
  <glyph row 2>      (shorter rows are padded with spaces on the right)
  <glyph row 3>
  <glyph row 4>
  <glyph row 5>
  <colour row 1>     exactly 5 colour rows, one PALETTE key per character of
  <colour row 2>     the glyph row above it (space = the terminal's default)
  <colour row 3>
  <colour row 4>
  <colour row 5>
  frame 2
  ...

Exactly 10 lines follow every `frame` line (a glyph row may be all spaces,
so blank lines inside a frame count).  Blank lines are allowed between frames.
"""
import json
import os
import re
import sys
import unicodedata

HEIGHT = 5
MIN_W, MAX_W = 6, 12
MIN_FRAMES, MAX_FRAMES = 2, 10
MIN_PERIOD, MAX_PERIOD = 80, 400

# colour key: (name, 256-colour SGR, 16-colour fallback SGR)
PALETTE = {
    ' ': ('default', None, None),
    'k': ('grey', '38;5;245', '2'),
    'K': ('dark grey', '38;5;240', '2'),
    'w': ('white', '38;5;252', '37'),
    'W': ('bright white', '1;38;5;231', '1;97'),
    'r': ('red', '38;5;160', '31'),
    'R': ('bright red', '1;38;5;196', '1;91'),
    'g': ('green', '38;5;34', '32'),
    'G': ('bright green', '1;38;5;82', '1;92'),
    'y': ('yellow', '38;5;178', '33'),
    'Y': ('bright yellow', '1;38;5;226', '1;93'),
    'b': ('blue', '38;5;33', '34'),
    'B': ('bright blue', '1;38;5;75', '1;94'),
    'm': ('magenta', '38;5;127', '35'),
    'M': ('bright magenta', '1;38;5;201', '1;95'),
    'c': ('cyan', '38;5;37', '36'),
    'C': ('bright cyan', '1;38;5;51', '1;96'),
    'o': ('orange', '38;5;208', '33'),
    'O': ('bright orange', '1;38;5;214', '1;93'),
    'p': ('pink', '38;5;213', '95'),
    'n': ('brown', '38;5;130', '33'),
    'l': ('lime', '38;5;118', '92'),
    'v': ('violet', '38;5;135', '95'),
    't': ('teal', '38;5;30', '36'),
    's': ('steel blue', '38;5;67', '34'),
    'd': ('gold', '1;38;5;220', '1;93'),
}

# Glyphs a monospace terminal font renders one cell wide (checked per
# character below, together with the East Asian width and the category).
ALLOWED_RANGES = (
    (0x20, 0x7E),      # ASCII
    (0xA1, 0xFF),      # Latin-1 symbols (° ± · ¬ ¯ ×)
    (0x2010, 0x2027),  # dashes, bullets, ellipsis
    (0x2190, 0x21FF),  # arrows
    (0x2200, 0x22FF),  # mathematical operators (≈ ∞ ∴ ∿)
    (0x2300, 0x23FF),  # miscellaneous technical (⌂ ⌁ ⏏)
    (0x2500, 0x257F),  # box drawing
    (0x2580, 0x259F),  # block elements
    (0x25A0, 0x25FF),  # geometric shapes
    (0x2600, 0x26FF),  # miscellaneous symbols (☀ ★ ☆ ♦)
    (0x2700, 0x27BF),  # dingbats (✓ ✔ ✦ ✧ ✶ ✻ ❖)
    (0x2B00, 0x2B2F),  # miscellaneous symbols and arrows (narrow part)
)

# The ASCII fallback for a terminal without UTF-8 (console_art.ASCII_MAP).
ASCII_MAP = {
    '─': '-', '━': '=', '│': '|', '┃': '|', '┄': '-', '┆': '|', '┈': '-', '┊': '|',
    '╭': '+', '╮': '+', '╰': '+', '╯': '+', '┌': '+', '┐': '+', '└': '+', '┘': '+',
    '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+', '═': '=', '║': '|',
    '╔': '+', '╗': '+', '╚': '+', '╝': '+', '╦': '+', '╩': '+', '╠': '+', '╣': '+', '╬': '+',
    '╒': '+', '╕': '+', '╘': '+', '╛': '+', '╤': '+', '╧': '+', '╞': '+', '╡': '+', '╪': '+',
    '╷': '|', '╵': '|', '╶': '-', '╴': '-', '╱': '/', '╲': '\\', '╳': 'X',
    '█': '#', '▓': '#', '▒': '%', '░': '.', '▀': '^', '▄': '_', '▌': '|', '▐': '|',
    '▔': '-', '▁': '_', '▏': '|', '▕': '|', '▖': '.', '▗': '.', '▘': "'", '▝': "'",
    '■': '#', '□': '#', '▪': '*', '▫': '.', '▬': '=', '▭': '=', '▮': '#', '▯': '#',
    '●': 'o', '○': 'o', '◆': '*', '◇': '*', '◉': '@', '◎': 'O', '◌': 'o', '◍': 'o',
    '◐': 'o', '◑': 'o', '◒': 'o', '◓': 'o', '◔': 'o', '◕': 'o', '◯': 'O',
    '▲': '^', '△': '^', '▼': 'v', '▽': 'v', '◀': '<', '◁': '<', '▶': '>', '▷': '>',
    '▴': '^', '▾': 'v', '◂': '<', '▸': '>', '◢': '/', '◣': '\\', '◤': '/', '◥': '\\',
    '←': '<', '→': '>', '↑': '^', '↓': 'v', '↔': '-', '↕': '|', '⇠': '<', '⇢': '>',
    '⇡': '^', '⇣': 'v', '⇐': '<', '⇒': '>', '↺': 'o', '↻': 'o', '⤴': '^', '⤵': 'v',
    '✦': '*', '✧': '+', '✶': '*', '✷': '*', '✸': '*', '✹': '*', '✺': '*', '✻': '*',
    '✼': '*', '✽': '*', '✾': '*', '✿': '*', '❀': '*', '❖': '*', '✢': '+', '✣': '+',
    '✤': '+', '✥': '+', '✓': 'v', '✔': 'V', '✕': 'x', '✖': 'X', '✗': 'x', '✘': 'X',
    '★': '*', '☆': '*', '☀': '*', '♦': '*', '♢': '*', '·': '.', '•': 'o', '‥': '.',
    '…': '.', '⌂': '^', '⌁': '~', '≈': '~', '∿': '~', '∞': '8', '°': 'o', '×': 'x',
    '±': '+', '¬': '-', '¯': '-', '∴': ':', '∵': ':', '⏏': '^', '⚡': '!', '✚': '+',
}


class SpriteError(Exception):
    pass


def _glyph_ok(ch):
    cp = ord(ch)
    if cp > 0xFFFF:
        return False
    if not any(lo <= cp <= hi for lo, hi in ALLOWED_RANGES):
        return False
    if unicodedata.category(ch)[0] in ('M', 'C'):
        return False
    if unicodedata.east_asian_width(ch) in ('W', 'F'):
        return False
    return True


def parse(path):
    with open(path, encoding='utf-8-sig') as f:
        lines = f.read().split('\n')
    lines = [ln.rstrip('\r') for ln in lines]
    meta = {'period_ms': 200, 'pingpong': False, 'notes': ''}
    frames = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        m = re.match(r'^frame(?:\s+\d+)?\s*$', ln.strip())
        if m:
            block = lines[i + 1:i + 1 + 2 * HEIGHT]
            if len(block) < 2 * HEIGHT:
                raise SpriteError(f'line {i + 1}: a frame needs {2 * HEIGHT} lines after it')
            frames.append((block[:HEIGHT], block[HEIGHT:]))
            i += 1 + 2 * HEIGHT
            continue
        m = re.match(r'^(key|width|period_ms|pingpong|notes)\s*:\s*(.*)$', ln)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k == 'width' or k == 'period_ms':
                try:
                    v = int(v)
                except ValueError:
                    raise SpriteError(f'line {i + 1}: {k} must be an integer')
            elif k == 'pingpong':
                v = v.lower() in ('yes', 'true', '1', 'on')
            meta[k] = v
            i += 1
            continue
        if ln.strip() == '':
            i += 1
            continue
        raise SpriteError(f'line {i + 1}: unexpected text outside a frame: {ln!r}')
    meta['frames'] = frames
    return meta


def validate(meta):
    errors = []
    key = meta.get('key')
    if not key or not re.fullmatch(r'[a-z][a-z_]*', str(key)):
        errors.append('key: a lowercase identifier is required')
    width = meta.get('width')
    if not isinstance(width, int) or not MIN_W <= width <= MAX_W:
        errors.append(f'width: an integer between {MIN_W} and {MAX_W} is required')
        width = MAX_W
    period = meta.get('period_ms', 200)
    if not isinstance(period, int) or not MIN_PERIOD <= period <= MAX_PERIOD:
        errors.append(f'period_ms: between {MIN_PERIOD} and {MAX_PERIOD}')
    frames = meta.get('frames', [])
    if not MIN_FRAMES <= len(frames) <= MAX_FRAMES:
        errors.append(f'frames: between {MIN_FRAMES} and {MAX_FRAMES}, found {len(frames)}')
    clean = []
    for fi, (rows, masks) in enumerate(frames, 1):
        crows, cmasks = [], []
        for ri in range(HEIGHT):
            row, mask = rows[ri], masks[ri]
            if len(row) > width:
                errors.append(f'frame {fi} row {ri + 1}: {len(row)} characters, width is {width}')
                row = row[:width]
            if len(mask) > width:
                errors.append(f'frame {fi} colour row {ri + 1}: {len(mask)} characters, width is {width}')
                mask = mask[:width]
            for ci, ch in enumerate(row):
                if not _glyph_ok(ch):
                    errors.append(f'frame {fi} row {ri + 1} col {ci + 1}: glyph {ch!r} (U+{ord(ch):04X}) '
                                  f'is not in the allowed single-width set')
            for ci, ch in enumerate(mask):
                if ch not in PALETTE:
                    errors.append(f'frame {fi} colour row {ri + 1} col {ci + 1}: unknown colour key {ch!r}')
            row = row.ljust(width)
            mask = mask.ljust(width)
            for ci, (g, k) in enumerate(zip(row, mask)):
                if g == ' ' and k != ' ':
                    pass        # colouring a space is harmless
            crows.append(row)
            cmasks.append(mask)
        if all(r.strip() == '' for r in crows):
            errors.append(f'frame {fi}: empty')
        clean.append((tuple(crows), tuple(cmasks)))
    if frames and len({len(f[0]) for f in clean}) > 1:
        errors.append('frames differ in height')
    for a, b in zip(clean, clean[1:]):
        if a == b:
            errors.append('two consecutive frames are identical (a held frame is fine, but say so in notes)')
            break
    meta = dict(meta)
    meta['frames'] = clean
    meta['width'] = width
    return meta, errors


def _sgr(code):
    return f'\033[{code}m' if code else ''


def render_row(row, mask, color):
    if not color:
        return row
    out, cur, buf = [], None, ''
    for g, k in zip(row, mask):
        if k != cur:
            if buf:
                out.append(_sgr(PALETTE[cur][1]) + buf + ('\033[0m' if PALETTE[cur][1] else ''))
            cur, buf = k, ''
        buf += g
    if buf:
        out.append(_sgr(PALETTE[cur][1]) + buf + ('\033[0m' if PALETTE[cur][1] else ''))
    return ''.join(out)


def sheet(meta, color=False, cols=100):
    width = meta['width']
    frames = meta['frames']
    per_line = max(1, (cols + 3) // (width + 3))
    out = []
    for start in range(0, len(frames), per_line):
        chunk = frames[start:start + per_line]
        out.append('  '.join(f'frame {start + i + 1}'.ljust(width + 1) for i in range(len(chunk))))
        for ri in range(HEIGHT):
            out.append(' │ '.join(render_row(f[0][ri], f[1][ri], color) for f in chunk))
        out.append('  '.join('colours'.ljust(width + 1) for _ in chunk))
        for ri in range(HEIGHT):
            out.append(' │ '.join(f[1][ri] for f in chunk))
        out.append('')
    return '\n'.join(out)


def check(path, color=False):
    try:
        meta = parse(path)
    except SpriteError as e:
        print(f'FAIL {path}: {e}')
        return 1
    meta, errors = validate(meta)
    print(sheet(meta, color=color))
    if errors:
        print(f'FAIL {path}:')
        for e in errors:
            print(f'  - {e}')
        return 1
    print(f"OK {path}: key {meta['key']}, {meta['width']}x{HEIGHT}, {len(meta['frames'])} frames, "
          f"{meta['period_ms']} ms per frame, pingpong {'yes' if meta.get('pingpong') else 'no'}")
    return 0


HEADER = '''"""The console's text-art sprites (console_ui's live block): one short
animation per activity, GIF style, in colour, an emoji-like pictogram of
what the robot is doing beside its status line (Hani, 2026-10-30; one
artist and one reviewer per sprite).  Data only: nothing here feeds a
decision, and nothing here is read by the pipeline.

A sprite is a list of frames; a frame is HEIGHT glyph rows and HEIGHT
colour rows of the same width, one PALETTE key per character (a space is
the terminal's default colour).  console_ui plays the frames at period_ms,
looping (or back and forth with pingpong), clips them to the terminal and
translates the glyphs through ASCII_MAP when the locale is not UTF-8.

Generated by tools/sprite_tool.py from tools/sprites/<key>.txt (one file
per sprite, the format in the tool's docstring):

    python tools/sprite_tool.py assemble tools/sprites console_art.py

Edit the data here by hand only to touch up a frame; redraw a sprite in its
source file and assemble again.
"""

HEIGHT = {height}

# colour key: (256-colour SGR, 16-colour fallback SGR); None is the default
PALETTE = {{
{palette}
}}

# the ASCII stand-in of every glyph the sprites use (a terminal without UTF-8)
ASCII_MAP = {{
{ascii_map}
}}

SPRITES = {{
{sprites}
}}
'''


def assemble(src_dir, out_path):
    keys = {}
    for name in sorted(os.listdir(src_dir)):
        m = re.fullmatch(r'([a-z][a-z_]*)(\.reviewed)?\.txt', name)
        if not m:
            continue
        key, reviewed = m.group(1), bool(m.group(2))
        if reviewed or key not in keys:
            keys[key] = os.path.join(src_dir, name)
    entries, bad = [], 0
    used = set()
    for key, path in sorted(keys.items()):
        try:
            meta = parse(path)
        except SpriteError as e:
            print(f'SKIP {key}: {e}')
            bad += 1
            continue
        meta, errors = validate(meta)
        if errors or meta['key'] != key:
            print(f'SKIP {key} ({os.path.basename(path)}):')
            for e in errors or [f"key inside the file is {meta['key']!r}"]:
                print(f'  - {e}')
            bad += 1
            continue
        for rows, _ in meta['frames']:
            used.update(ch for r in rows for ch in r)
        frames = []
        for rows, masks in meta['frames']:
            frames.append('            (' + repr(tuple(rows)) + ',\n'
                          '             ' + repr(tuple(masks)) + '),')
        entries.append(
            f"    {key!r}: {{\n"
            f"        'width': {meta['width']}, 'period_ms': {meta['period_ms']}, "
            f"'pingpong': {bool(meta.get('pingpong'))},\n"
            f"        'frames': (\n" + '\n'.join(frames) + "\n        ),\n"
            f"    }},")
        print(f"OK {key}: {os.path.basename(path)}, {len(meta['frames'])} frames, "
              f"{meta['width']}x{HEIGHT}")
    missing = sorted(ch for ch in used if ord(ch) > 0x7E and ch not in ASCII_MAP)
    if missing:
        print('glyphs without an ASCII stand-in (they fall back to "*"): ' + ' '.join(missing))
    palette = '\n'.join(f'    {k!r}: ({v[1]!r}, {v[2]!r}),' for k, v in PALETTE.items())
    ascii_map = '\n'.join(f'    {k!r}: {v!r},' for k, v in ASCII_MAP.items())
    text = HEADER.format(height=HEIGHT, palette=palette, ascii_map=ascii_map,
                         sprites='\n'.join(entries))
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f'wrote {out_path}: {len(entries)} sprites, {bad} skipped')
    return 1 if bad else 0


def main(argv):
    if len(argv) >= 2 and argv[0] == 'check':
        return check(argv[1], color='--color' in argv[2:])
    if len(argv) == 3 and argv[0] == 'assemble':
        return assemble(argv[1], argv[2])
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
