"""Generate every Evergreen brand asset from one geometry definition.

The logo is defined once, on a 512 x 512 grid (centre seam x = 256). This script
derives from it:

  * docs/branding/*.svg            master logo, monochrome logo, app icon
  * docs/branding/png/*.png        raster exports (logo, icon, lockups, feature graphic)
  * lawnchair/res/drawable/*.xml   adaptive icon foreground, background and monochrome layers
  * legacy mipmap PNGs, the Play Store / F-Droid icon and the IDE project icon

Rasterising uses headless Chrome (or Edge). Run from the repository root:

    python docs/branding/generate.py

Set CHROME=<path to chrome.exe> if the browser is not found automatically.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs" / "branding"
PNG = BRAND / "png"
DRAWABLE = ROOT / "lawnchair" / "res" / "drawable"

# ---------------------------------------------------------------------------
# Geometry (512 grid)
# ---------------------------------------------------------------------------

SEAM = 256
# Tree polygon: every tier edge has slope 0.75, every notch is 40 px deep.
TREE = [(256, 52), (148, 196), (188, 196), (90, 326), (130, 326), (35, 452),
        (477, 452), (382, 326), (422, 326), (324, 196), (364, 196)]
CORNER = 8   # outer silhouette = TREE grown by 8 px with round convex corners
RIM = 4      # light rim = the outermost 4 px of the silhouette

# Bands: one curve family from the seam to each tier tip (control at 45% / 75%).
BANDS_LEFT = [  # drawn bottom-up, each covers everything above its curve
    ("l3", [("M", 256, 253), ("Q", 157, 402, 35, 452), ("L", 0, 452), ("L", 0, 0), ("L", 256, 0), ("Z",)]),
    ("l2", [("M", 256, 177), ("Q", 181, 289, 90, 326), ("L", 0, 326), ("L", 0, 0), ("L", 256, 0), ("Z",)]),
    ("l1", [("M", 256, 99), ("Q", 207, 172, 148, 196), ("L", 0, 196), ("L", 0, 0), ("L", 256, 0), ("Z",)]),
]


def mirror(cmds):
    out = []
    for c in cmds:
        if c[0] in ("M", "L"):
            out.append((c[0], 2 * SEAM - c[1], c[2]))
        elif c[0] == "Q":
            out.append(("Q", 2 * SEAM - c[1], c[2], 2 * SEAM - c[3], c[4]))
        else:
            out.append(c)
    return out


BANDS_RIGHT = [("r" + name[1], mirror(cmds)) for name, cmds in BANDS_LEFT]
HALF_LEFT = [("M", 0, 0), ("L", 256, 0), ("L", 256, 512), ("L", 0, 512), ("Z",)]
HALF_RIGHT = mirror(HALF_LEFT)


def _roof_y(x: float) -> float:
    return 253 + abs(x - SEAM) * (109 / 119)


# House outline as one polygon (roof + chimney + body), centred on the seam.
HOUSE = [("M", 256, 253), ("L", 306, _roof_y(306)), ("L", 306, 276), ("L", 336, 276),
         ("L", 336, _roof_y(336)), ("L", 375, 362), ("L", 337, 362), ("L", 337, 460),
         ("L", 175, 460), ("L", 175, 362), ("L", 137, 362), ("Z",)]
DOOR_LEFT = [("M", 229, 384), ("L", 256, 384), ("L", 256, 460), ("L", 229, 460), ("Z",)]
DOOR_RIGHT = [("M", 256, 384), ("L", 283, 384), ("L", 283, 460), ("L", 256, 460), ("Z",)]

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

GRADIENTS = {  # name: (y0, y1, top colour, bottom colour)
    "l1": (44, 196, "#BDEF9E", "#A3E588"),
    "l2": (100, 326, "#94E07C", "#78D274"),
    "l3": (180, 460, "#62C86E", "#46BA6C"),
    "l4": (300, 460, "#34B06B", "#27A265"),
    "r1": (44, 196, "#62BF8D", "#4FAB82"),
    "r2": (100, 326, "#43A07C", "#358870"),
    "r3": (180, 460, "#2F7C68", "#25685F"),
    "r4": (300, 460, "#1E5A5B", "#1A4D53"),
}
RIM_LEFT = ("#E6FFD6", 0.32)
RIM_RIGHT = ("#C8F5E0", 0.20)
HOUSE_COLOR = "#FFFFFF"
DOOR_LEFT_COLOR = "#3CB46C"
DOOR_RIGHT_COLOR = "#1A4D53"
BG_TOP = "#2E3A38"
BG_BOTTOM = "#1A2522"
INK_DARK = "#1F3D33"     # wordmark on light backgrounds
INK_LIGHT = "#E9F5EC"    # wordmark on dark backgrounds

# ---------------------------------------------------------------------------
# Outline offsetting (round convex corners, mitred concave corners)
# ---------------------------------------------------------------------------


def offset_outline(poly, r):
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    sign = 1 if area > 0 else -1

    def normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        return (sign * dy / length, -sign * dx / length), (dx / length, dy / length)

    cmds = []
    for i in range(n):
        prev, cur, nxt = poly[i - 1], poly[i], poly[(i + 1) % n]
        n0, d0 = normal(prev, cur)
        n1, d1 = normal(cur, nxt)
        cross = d0[0] * d1[1] - d0[1] * d1[0]
        if cross * sign > 0:  # convex: arc around the vertex
            p0 = (cur[0] + r * n0[0], cur[1] + r * n0[1])
            p1 = (cur[0] + r * n1[0], cur[1] + r * n1[1])
            cmds.append(("M" if not cmds else "L", *p0))
            cmds.append(("A", r, 1 if sign > 0 else 0, *p1))
        else:  # concave: intersect the two offset edges
            a = (cur[0] + r * n0[0], cur[1] + r * n0[1])
            b = (cur[0] + r * n1[0], cur[1] + r * n1[1])
            t = ((b[0] - a[0]) * d1[1] - (b[1] - a[1]) * d1[0]) / (d0[0] * d1[1] - d0[1] * d1[0])
            cmds.append(("M" if not cmds else "L", a[0] + t * d0[0], a[1] + t * d0[1]))
    cmds.append(("Z",))
    return cmds


SILHOUETTE = offset_outline(TREE, CORNER)
SILHOUETTE_INNER = offset_outline(TREE, CORNER - RIM)

# ---------------------------------------------------------------------------
# Path serialisation with an affine (scale + translate) transform
# ---------------------------------------------------------------------------


class Xf:
    def __init__(self, s=1.0, tx=0.0, ty=0.0):
        self.s, self.tx, self.ty = s, tx, ty

    def pt(self, x, y):
        return x * self.s + self.tx, y * self.s + self.ty

    def y(self, y):
        return y * self.s + self.ty


def fmt(v):
    v = round(v, 2)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0")


def path_d(cmds, xf):
    out = []
    for c in cmds:
        op = c[0]
        if op in ("M", "L"):
            x, y = xf.pt(c[1], c[2])
            out.append(f"{op}{fmt(x)},{fmt(y)}")
        elif op == "Q":
            cx, cy = xf.pt(c[1], c[2])
            x, y = xf.pt(c[3], c[4])
            out.append(f"Q{fmt(cx)},{fmt(cy)} {fmt(x)},{fmt(y)}")
        elif op == "A":
            r = c[1] * xf.s
            x, y = xf.pt(c[3], c[4])
            out.append(f"A{fmt(r)},{fmt(r)} 0 0,{c[2]} {fmt(x)},{fmt(y)}")
        else:
            out.append("Z")
    return " ".join(out)


def concat(*parts):
    return [c for p in parts for c in p]


# Adaptive icon placement: the logo's bounding box (x 27..485, y 44..460 on the
# 512 grid, centre (256, 252)) is centred on the 108 dp canvas. At this scale
# its rounded corners stay inside a 36 dp radius, so circular masks never clip
# them, and the logo fills about 70% of the 72 dp visible area.
ICON_S = 0.115
ICON_XF = Xf(ICON_S, 54 - SEAM * ICON_S, 54 - 252 * ICON_S)
IDENTITY = Xf()

# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def svg_logo_body(xf, uid="evg"):
    """SVG fragment drawing the full-colour logo, transformed by xf."""
    defs = []
    for name, (y0, y1, c0, c1) in GRADIENTS.items():
        defs.append(
            f'<linearGradient id="{uid}-{name}" gradientUnits="userSpaceOnUse" x1="0" y1="{fmt(xf.y(y0))}" '
            f'x2="0" y2="{fmt(xf.y(y1))}"><stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/>'
            f"</linearGradient>")
    defs.append(f'<clipPath id="{uid}-tree"><path d="{path_d(SILHOUETTE, xf)}"/></clipPath>')
    defs.append(f'<clipPath id="{uid}-left"><path d="{path_d(HALF_LEFT, xf)}"/></clipPath>')
    defs.append(f'<clipPath id="{uid}-right"><path d="{path_d(HALF_RIGHT, xf)}"/></clipPath>')

    body = [f'<g clip-path="url(#{uid}-tree)">',
            f'<path fill="url(#{uid}-l4)" d="{path_d(HALF_LEFT, xf)}"/>',
            f'<path fill="url(#{uid}-r4)" d="{path_d(HALF_RIGHT, xf)}"/>']
    for name, cmds in BANDS_LEFT + BANDS_RIGHT:
        body.append(f'<path fill="url(#{uid}-{name})" d="{path_d(cmds, xf)}"/>')
    body.append("</g>")
    rim = path_d(concat(SILHOUETTE, SILHOUETTE_INNER), xf)
    body.append(f'<path clip-path="url(#{uid}-left)" fill="{RIM_LEFT[0]}" fill-opacity="{RIM_LEFT[1]}" '
                f'fill-rule="evenodd" d="{rim}"/>')
    body.append(f'<path clip-path="url(#{uid}-right)" fill="{RIM_RIGHT[0]}" fill-opacity="{RIM_RIGHT[1]}" '
                f'fill-rule="evenodd" d="{rim}"/>')
    body.append(f'<path fill="{HOUSE_COLOR}" d="{path_d(HOUSE, xf)}"/>')
    body.append(f'<path fill="{DOOR_LEFT_COLOR}" d="{path_d(DOOR_LEFT, xf)}"/>')
    body.append(f'<path fill="{DOOR_RIGHT_COLOR}" d="{path_d(DOOR_RIGHT, xf)}"/>')
    return "<defs>" + "".join(defs) + "</defs>" + "".join(body)


def mono_path(xf, fill):
    # Even-odd: silhouette filled, house cut out, door filled again.
    door = [("M", 229, 384), ("L", 283, 384), ("L", 283, 460), ("L", 229, 460), ("Z",)]
    d = path_d(concat(SILHOUETTE, HOUSE, door), xf)
    return f'<path fill="{fill}" fill-rule="evenodd" d="{d}"/>'


def svg_doc(view, body, w=None, h=None, title="Evergreen"):
    size = f' width="{w}" height="{h}"' if w else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}"{size}>'
            f"<title>{title}</title>{body}</svg>\n")


def svg_background_108(uid="bg"):
    return (f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="0.6" y2="1">'
            f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/>'
            f'</linearGradient></defs><rect width="108" height="108" fill="url(#{uid})"/>')


def svg_icon(shape="square"):
    """The adaptive icon as a launcher shows it: the central 72 dp of the 108 dp canvas."""
    clip = ""
    if shape == "rounded":
        clip = '<clipPath id="shape"><rect x="18" y="18" width="72" height="72" rx="16"/></clipPath>'
    elif shape == "circle":
        clip = '<clipPath id="shape"><circle cx="54" cy="54" r="36"/></clipPath>'
    inner = svg_background_108() + svg_logo_body(ICON_XF)
    if clip:
        inner = f'<defs>{clip}</defs><g clip-path="url(#shape)">{inner}</g>'
    return svg_doc("18 18 72 72", inner, title="Evergreen Launcher")


# ---------------------------------------------------------------------------
# Android vector drawables
# ---------------------------------------------------------------------------

VD_HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n<!-- {comment}\n     Generated by docs/branding/generate.py; '
           'edit that script, not this file. -->\n'
           '<vector xmlns:android="http://schemas.android.com/apk/res/android"{ns}\n'
           '    android:width="108dp"\n    android:height="108dp"\n'
           '    android:viewportWidth="108"\n    android:viewportHeight="108">\n')
AAPT = '\n    xmlns:aapt="http://schemas.android.com/aapt"'


def vd_gradient_path(d, name, xf, indent):
    y0, y1, c0, c1 = GRADIENTS[name]
    p = " " * indent
    return (f'{p}<path android:pathData="{d}">\n'
            f'{p}    <aapt:attr name="android:fillColor">\n'
            f'{p}        <gradient android:type="linear" android:startX="54" android:startY="{fmt(xf.y(y0))}"\n'
            f'{p}            android:endX="54" android:endY="{fmt(xf.y(y1))}">\n'
            f'{p}            <item android:offset="0" android:color="{c0}" />\n'
            f'{p}            <item android:offset="1" android:color="{c1}" />\n'
            f'{p}        </gradient>\n{p}    </aapt:attr>\n{p}</path>\n')


def argb(hex_rgb, alpha):
    return f"#{round(alpha * 255):02X}{hex_rgb[1:]}"


def vd_foreground():
    xf = ICON_XF
    out = [VD_HEAD.format(comment="Evergreen adaptive icon foreground: two-tone fir tree with a house.", ns=AAPT)]
    out.append(f'    <group android:name="tree">\n        <clip-path android:pathData="{path_d(SILHOUETTE, xf)}" />\n')
    out.append(vd_gradient_path(path_d(HALF_LEFT, xf), "l4", xf, 8))
    out.append(vd_gradient_path(path_d(HALF_RIGHT, xf), "r4", xf, 8))
    for name, cmds in BANDS_LEFT + BANDS_RIGHT:
        out.append(vd_gradient_path(path_d(cmds, xf), name, xf, 8))
    out.append("    </group>\n")
    rim = path_d(concat(SILHOUETTE, SILHOUETTE_INNER), xf)
    for side, half, (color, alpha) in (("left", HALF_LEFT, RIM_LEFT), ("right", HALF_RIGHT, RIM_RIGHT)):
        out.append(f'    <group android:name="rim_{side}">\n'
                   f'        <clip-path android:pathData="{path_d(half, xf)}" />\n'
                   f'        <path android:fillColor="{argb(color, alpha)}" android:fillType="evenOdd"\n'
                   f'            android:pathData="{rim}" />\n    </group>\n')
    for cmds, color in ((HOUSE, HOUSE_COLOR), (DOOR_LEFT, DOOR_LEFT_COLOR), (DOOR_RIGHT, DOOR_RIGHT_COLOR)):
        out.append(f'    <path android:fillColor="{color}"\n        android:pathData="{path_d(cmds, xf)}" />\n')
    out.append("</vector>\n")
    return "".join(out)


def vd_background():
    return (VD_HEAD.format(comment="Evergreen adaptive icon background.", ns=AAPT)
            + '    <path android:pathData="M0,0h108v108h-108z">\n'
            '        <aapt:attr name="android:fillColor">\n'
            '            <gradient android:type="linear" android:startX="0" android:startY="0"\n'
            '                android:endX="64.8" android:endY="108">\n'
            f'                <item android:offset="0" android:color="{BG_TOP}" />\n'
            f'                <item android:offset="1" android:color="{BG_BOTTOM}" />\n'
            '            </gradient>\n        </aapt:attr>\n    </path>\n</vector>\n')


def vd_monochrome():
    door = [("M", 229, 384), ("L", 283, 384), ("L", 283, 460), ("L", 229, 460), ("Z",)]
    d = path_d(concat(SILHOUETTE, HOUSE, door), ICON_XF)
    return (VD_HEAD.format(comment="Evergreen monochrome (themed) icon: tree silhouette, house cut out.", ns="")
            + f'    <path android:fillColor="#FFFFFF" android:fillType="evenOdd"\n'
            f'        android:pathData="{d}" />\n</vector>\n')


# ---------------------------------------------------------------------------
# Rasterising
# ---------------------------------------------------------------------------

FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600&display=block" '
             'rel="stylesheet">')
FONT_STACK = "Outfit, Segoe UI, system-ui, sans-serif"  # no quotes: used inside style='...' 


def find_chrome():
    env = os.environ.get("CHROME")
    if env:
        return env
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("Chrome/Edge not found; set CHROME=<path>")


def render(html_body, w, h, out: Path, tmp: Path, chrome: str, bg="transparent"):
    page = tmp / (out.stem + ".html")
    page.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>{FONT_LINK}<style>"
        f"html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{bg}}}"
        f"svg{{display:block}}</style></head><body>{html_body}</body></html>", encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--default-background-color=00000000",
                    "--virtual-time-budget=4000", f"--window-size={w},{h}", f"--screenshot={out}",
                    page.as_uri()], check=True, capture_output=True)
    print("  ", out.relative_to(ROOT))


def sized(svg, w, h):
    return svg.replace("<svg ", f'<svg width="{w}" height="{h}" ', 1)


def lockup(ink, w=1200, h=400):
    logo = svg_doc("24 40 464 432", svg_logo_body(IDENTITY, "lk"), title="Evergreen")
    return (f"<div style='display:flex;align-items:center;gap:{h * 0.09}px;height:{h}px;padding:0 {h * 0.12}px'>"
            f"{sized(logo, int(h * 0.72 * 464 / 432), int(h * 0.72))}"
            f"<span style='font:600 {h * 0.34}px/1 {FONT_STACK};letter-spacing:-0.01em;color:{ink}'>"
            f"Evergreen</span></div>")


def feature_graphic():
    logo = svg_doc("24 40 464 432", svg_logo_body(IDENTITY, "fg"), title="Evergreen")
    return (f"<div style='width:1024px;height:500px;box-sizing:border-box;display:flex;align-items:center;"
            f"gap:56px;padding:0 88px;background:linear-gradient(160deg,{BG_TOP},{BG_BOTTOM})'>"
            f"{sized(logo, 300, 279)}<div>"
            f"<div style='font:600 92px/1 {FONT_STACK};letter-spacing:-0.015em;color:{INK_LIGHT}'>Evergreen</div>"
            f"<div style='margin-top:18px;font:500 34px/1.25 {FONT_STACK};color:#9FD9B0'>"
            f"A light, fast launcher<br>for older Android devices</div></div></div>")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("  ", path.relative_to(ROOT))


def main():
    print("Vector assets")
    logo_svg = svg_doc("0 0 512 512", svg_logo_body(IDENTITY), 512, 512)
    write(BRAND / "evergreen-logo.svg", logo_svg)
    write(BRAND / "evergreen-logo-mono.svg",
          svg_doc("0 0 512 512", mono_path(IDENTITY, "#1F3D33"), 512, 512, "Evergreen (monochrome)"))
    icon_rounded = svg_icon("rounded")
    write(BRAND / "evergreen-icon.svg", icon_rounded)
    write(DRAWABLE / "ic_evergreen_foreground.xml", vd_foreground())
    write(DRAWABLE / "ic_evergreen_background.xml", vd_background())
    write(DRAWABLE / "ic_launcher_home_monochrome.xml", vd_monochrome())

    print("Raster assets")
    chrome = find_chrome()
    icon_square = svg_icon("square")
    icon_circle = svg_icon("circle")
    layer_fg = svg_doc("0 0 108 108", svg_logo_body(ICON_XF))
    layer_bg = svg_doc("0 0 108 108", svg_background_108())
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        render(sized(logo_svg, 1024, 1024), 1024, 1024, PNG / "evergreen-logo-1024.png", tmp, chrome)
        render(sized(icon_square, 512, 512), 512, 512, PNG / "evergreen-icon-512.png", tmp, chrome)
        render(sized(icon_rounded, 512, 512), 512, 512, PNG / "evergreen-icon-rounded-512.png", tmp, chrome)
        render(lockup(INK_LIGHT), 1200, 400, PNG / "evergreen-lockup-on-dark.png", tmp, chrome)
        render(lockup(INK_DARK), 1200, 400, PNG / "evergreen-lockup-on-light.png", tmp, chrome)
        render(feature_graphic(), 1024, 500, PNG / "evergreen-feature-graphic.png", tmp, chrome)

        # Store / repository icons
        render(sized(icon_square, 512, 512), 512, 512, ROOT / "ic_launcher_home-playstore.png", tmp, chrome)
        images = ROOT / "fastlane" / "metadata" / "android" / "en-US" / "images"
        render(sized(icon_square, 512, 512), 512, 512, images / "icon.png", tmp, chrome)
        render(feature_graphic(), 1024, 500, images / "featureGraphic.png", tmp, chrome)
        render(sized(icon_rounded, 512, 512), 512, 512, ROOT / ".idea" / "icon.png", tmp, chrome)

        # Legacy mipmaps (pre-API 26 fallback, kept in sync with the adaptive icon)
        for dpi, scale in (("mdpi", 1), ("hdpi", 1.5), ("xhdpi", 2), ("xxhdpi", 3), ("xxxhdpi", 4)):
            d = ROOT / "res" / f"mipmap-{dpi}"
            px, layer = int(48 * scale), int(108 * scale)
            render(sized(icon_rounded, px, px), px, px, d / "ic_launcher_home.png", tmp, chrome)
            render(sized(icon_circle, px, px), px, px, d / "ic_launcher_home_round.png", tmp, chrome)
            render(sized(layer_fg, layer, layer), layer, layer, d / "ic_launcher_home_foreground.png", tmp, chrome)
            render(sized(layer_bg, layer, layer), layer, layer, d / "ic_launcher_home_background.png", tmp, chrome)


if __name__ == "__main__":
    main()
