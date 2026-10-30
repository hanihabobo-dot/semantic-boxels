"""The desktop icon of the launcher (run.ps1): a neon isometric boxel on a
dark rounded tile, the orange target glowing on its top face, the console's
colours (console_art: cyan for the robot, orange for the object).  Writes
tools/boxels.ico (256 to 16 px) and tools/boxels_icon.png (the 256 px
preview).  Pillow only:

    python tools/make_icon.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024                      # drawn at 4x, scaled down to 256
CX, CY, R = 512, 548, 300     # the cube's centre vertex and its radius
BG = (11, 18, 32, 255)
BG_LIGHT = (24, 34, 58, 255)
EDGE = (70, 228, 255, 255)
EDGE_CORE = (225, 252, 255, 255)
GLOW = (40, 200, 255, 150)
FACE_TOP = (36, 82, 120, 255)
FACE_RIGHT = (22, 50, 80, 255)
FACE_LEFT = (14, 32, 56, 255)
ORANGE = (255, 150, 30, 255)
ORANGE_GLOW = (255, 140, 20, 170)


def hexagon():
    c30, s30 = math.cos(math.radians(30)), 0.5
    top = (CX, CY - R)
    ur = (CX + R * c30, CY - R * s30)
    lr = (CX + R * c30, CY + R * s30)
    bottom = (CX, CY + R)
    ll = (CX - R * c30, CY + R * s30)
    ul = (CX - R * c30, CY - R * s30)
    return top, ur, lr, bottom, ll, ul


def tile():
    """The dark rounded tile with a soft lighter centre and a thin rim."""
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=190, fill=BG)
    light = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(light).ellipse((CX - 420, CY - 380, CX + 420, CY + 380), fill=BG_LIGHT)
    light = light.filter(ImageFilter.GaussianBlur(120))
    img.alpha_composite(light)
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((16, 16, S - 16, S - 16), radius=190, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=190, outline=(28, 74, 96, 255), width=8)
    return img


def floor_grid(img):
    """A faint isometric grid under the cube."""
    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c30, s30 = math.cos(math.radians(30)), 0.5
    for k in range(-7, 8):
        off = k * 110
        d.line((CX - 700 * c30 + off, CY + 260 + 700 * s30, CX + 700 * c30 + off, CY + 260 - 700 * s30),
               fill=(70, 200, 255, 26), width=3)
        d.line((CX - 700 * c30 + off, CY + 260 - 700 * s30, CX + 700 * c30 + off, CY + 260 + 700 * s30),
               fill=(70, 200, 255, 26), width=3)
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((16, CY + 60, S - 16, S - 16), radius=190, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(40))
    layer.putalpha(Image.eval(mask, lambda v: v * 1))
    img.alpha_composite(layer)


def cube(img):
    top, ur, lr, bottom, ll, ul = hexagon()
    c = (CX, CY)
    d = ImageDraw.Draw(img)
    d.polygon([top, ur, c, ul], fill=FACE_TOP)
    d.polygon([ul, c, bottom, ll], fill=FACE_LEFT)
    d.polygon([c, ur, lr, bottom], fill=FACE_RIGHT)
    edges = [(top, ur), (ur, lr), (lr, bottom), (bottom, ll), (ll, ul), (ul, top),
             (c, ur), (c, ul), (c, bottom)]
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for a, b in edges:
        g.line((a, b), fill=GLOW, width=44)
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    for a, b in edges:
        d.line((a, b), fill=EDGE, width=14)
    for a, b in edges:
        d.line((a, b), fill=EDGE_CORE, width=4)
    for p in (top, ur, lr, bottom, ll, ul, c):
        d.ellipse((p[0] - 9, p[1] - 9, p[0] + 9, p[1] + 9), fill=EDGE_CORE)


def target(img):
    """The orange target glowing on the top face."""
    x, y, r = CX, CY - R * 0.5, 40
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((x - r * 2.6, y - r * 2.6, x + r * 2.6, y + r * 2.6), fill=ORANGE_GLOW)
    glow = glow.filter(ImageFilter.GaussianBlur(34))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.ellipse((x - r, y - r, x + r, y + r), fill=ORANGE)
    d.ellipse((x - r * 0.45, y - r * 0.55, x + r * 0.1, y - r * 0.05), fill=(255, 230, 190, 255))


def main():
    img = tile()
    floor_grid(img)
    cube(img)
    target(img)
    icon = img.resize((256, 256), Image.LANCZOS)
    png = os.path.join(HERE, 'boxels_icon.png')
    ico = os.path.join(HERE, 'boxels.ico')
    icon.save(png)
    icon.save(ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print('wrote', png, 'and', ico)


if __name__ == '__main__':
    main()
