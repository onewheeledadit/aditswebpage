#!/usr/bin/env python3
"""
Synthesise the "looking up" pose (adit5) from the registered adit1 cut-out.

No photo of this pose exists, so it is built from adit1:
  1. the iris is painted out of each eye with the white either side of it
  2. each eye is opened wider with a smooth local stretch (mostly vertical),
     which also lifts the brow a touch — wide-eyed rather than sleepy
  3. a round iris is redrawn high in the enlarged opening, so the upper lid
     tucks over its top and white shows underneath, plus a catch-light

Because adit5 is derived from assets/adit1-cut.png it shares adit1's eye
registration, so swapping between them is seamless.

Run after build_portraits.py:
  /opt/anaconda3/bin/python3 scripts/make_lookup.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "adit1-cut.png"
OUT = ROOT / "assets" / "adit5-cut"

OPEN_Y = 2.05        # how much wider the eye opens vertically
OPEN_X = 1.20        # ...and horizontally
REACH_X = 0.85       # stretch falloff, × eye width
REACH_Y = 2.6        # stretch falloff, × eye height
IRIS_R = 0.22        # original iris radius, × eye width
IRIS_SCALE = 1.18    # redrawn iris size vs original
IRIS_BOTTOM = 0.70   # iris bottom sits this far down the new opening (0 top, 1 bottom)
WHITEN = 0.35        # how far to lift the whites toward a clean off-white
SS = 4               # supersampling for smooth masks


def landmarks() -> dict:
    out = subprocess.run(
        ["swift", str(ROOT / "scripts" / "eye_regions.swift"), str(SRC)],
        capture_output=True, text=True, check=True,
    )
    return json.loads([l for l in out.stdout.splitlines() if l.startswith("{")][-1])


def polygon_mask(shape, poly, grow=1.0, feather=0.8) -> np.ndarray:
    h, w = shape
    p = np.asarray(poly, float)
    c = p.mean(axis=0)
    p = c + (p - c) * grow
    img = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(img).polygon([tuple(q * SS) for q in p], fill=255)
    img = img.resize((w, h), Image.LANCZOS)
    if feather:
        img = img.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(img, float) / 255.0


def paint_out_iris(rgb, opening, px, r) -> np.ndarray:
    """Replace the iris with the colour either side of it, row by row."""
    h, w, _ = rgb.shape
    ys = np.where(opening.max(axis=1) > 0.05)[0]
    filled = rgb.copy()
    reach = r * 1.3
    for y in range(ys.min() - 3, ys.max() + 4):
        lx, rx = int(round(px - reach)), int(round(px + reach))
        lc = rgb[y, max(lx - 2, 0):lx + 1].mean(axis=0)
        rc = rgb[y, rx:rx + 3].mean(axis=0)
        span = np.arange(lx, rx + 1)
        t = (span - lx) / max(rx - lx, 1)
        filled[y, span] = lc[None, :] * (1 - t[:, None]) + rc[None, :] * t[:, None]
    xs = np.arange(w)
    band = np.clip((r * 1.25 - np.abs(xs - px)) / 2.0 + 0.5, 0, 1)[None, :]
    paint = (band * opening)[..., None]
    return rgb * (1 - paint) + filled * paint


def iris_profile(rgb, opening, px, py, r, bins=24) -> np.ndarray:
    """Mean colour of the visible iris as a function of distance from the pupil."""
    h, w, _ = rgb.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rho = np.hypot(xx - px, yy - py) / r
    sel = (opening > 0.6) & (rho < 1.0)
    idx = np.minimum((rho[sel] * bins).astype(int), bins - 1)
    prof = np.full((bins, 3), np.nan)
    for b in range(bins):
        m = idx == b
        if m.any():
            prof[b] = rgb[sel][m].mean(axis=0)
    good = ~np.isnan(prof[:, 0])
    for c in range(3):
        prof[:, c] = np.interp(np.arange(bins), np.where(good)[0], prof[good, c])
    return prof


def main() -> None:
    lm = landmarks()
    im = Image.open(SRC).convert("RGBA")
    arr = np.asarray(im).astype(float)
    h, w, _ = arr.shape
    rgb, alpha = arr[..., :3].copy(), arr[..., 3]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)

    eyes = []
    for side in ("left", "right"):
        poly = np.asarray(lm[f"{side}Eye"], float)
        px, py = lm[f"{side}Pupil"][0]
        eye_w = poly[:, 0].max() - poly[:, 0].min()
        eye_h = poly[:, 1].max() - poly[:, 1].min()
        r = IRIS_R * eye_w
        cx, cy = poly[:, 0].mean(), poly[:, 1].mean()
        opening = polygon_mask((h, w), poly, grow=0.95, feather=0.8)
        profile = iris_profile(rgb, opening, px, py, r)
        # 1. iris out
        rgb = paint_out_iris(rgb, polygon_mask((h, w), poly, grow=1.18, feather=1.2), px, r)
        # whites: lift toward a clean off-white so the bigger eye reads as awake
        white = np.array([228.0, 222.0, 218.0])
        lift = (polygon_mask((h, w), poly, grow=0.85, feather=1.5) * WHITEN)[..., None]
        rgb = rgb * (1 - lift) + white * lift
        eyes.append(dict(poly=poly, px=px, py=py, r=r, cx=cx, cy=cy,
                         rx=REACH_X * eye_w, ry=REACH_Y * eye_h, profile=profile))

    # 2. open the eyes: smooth local stretch (backward map), one region per eye
    src_x, src_y = xx.copy(), yy.copy()
    for e in eyes:
        dx, dy = xx - e["cx"], yy - e["cy"]
        rho2 = (dx / e["rx"]) ** 2 + (dy / e["ry"]) ** 2
        wgt = np.where(rho2 < 1, (1 - rho2) ** 2, 0.0)
        src_x = np.where(wgt > 0, e["cx"] + dx / (1 + (OPEN_X - 1) * wgt), src_x)
        src_y = np.where(wgt > 0, e["cy"] + dy / (1 + (OPEN_Y - 1) * wgt), src_y)

    def warp(channel):
        return ndimage.map_coordinates(channel, [src_y, src_x], order=3, mode="nearest")

    rgb = np.dstack([warp(rgb[..., c]) for c in range(3)])
    alpha = warp(alpha)

    # 3. redraw a round iris high in each enlarged opening
    for e in eyes:
        opening = polygon_mask((h, w), e["poly"], grow=0.93, feather=0.0)
        opening = ndimage.map_coordinates(opening, [src_y, src_x], order=1)
        opening = ndimage.gaussian_filter(opening, 0.8)
        rows = np.where(opening[:, int(e["px"])] > 0.5)[0]
        top, bot = rows.min(), rows.max()
        R = e["r"] * IRIS_SCALE
        icx = e["px"]
        icy = top + IRIS_BOTTOM * (bot - top) - R
        rho = np.hypot(xx - icx, yy - icy) / R
        prof = e["profile"]
        bins = len(prof)
        col = prof[np.minimum((rho * bins).astype(int), bins - 1)]
        # a little structure: warm brown iris ring, darker pupil and limbal rim
        ring = np.clip((rho - 0.38) / 0.08, 0, 1) * np.clip((0.92 - rho) / 0.08, 0, 1)
        col = col * (1 - 0.40 * ring[..., None]) + np.array([74.0, 48.0, 34.0]) * 0.40 * ring[..., None]
        pupil = np.clip((0.40 - rho) / 0.06, 0, 1)
        col = col * (1 - 0.55 * pupil[..., None]) + np.array([10.0, 9.0, 9.0]) * 0.55 * pupil[..., None]
        limbus = np.clip((rho - 0.86) / 0.1, 0, 1)
        col = col * (1 - 0.35 * limbus[..., None])
        disc = np.clip((1 - rho) * R / 1.1 + 0.5, 0, 1)
        # catch-light so the eye reads as alive
        hl = np.hypot(xx - (icx - 0.36 * R), yy - (icy + 0.05 * R)) / (0.15 * R)
        hl_a = np.clip(1.4 - hl, 0, 1) * 0.85
        col = col * (1 - hl_a[..., None]) + np.array([245.0, 243.0, 240.0]) * hl_a[..., None]
        m = (disc * opening)[..., None]
        rgb = rgb * (1 - m) + col * m

    out = Image.fromarray(np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8), "RGBA")
    out.save(OUT.with_suffix(".png"), optimize=True)
    out.save(OUT.with_suffix(".webp"), quality=88, method=6)
    print("wrote", OUT.with_suffix(".png").name, "+ .webp")


if __name__ == "__main__":
    main()
