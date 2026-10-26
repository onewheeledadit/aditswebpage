#!/usr/bin/env python3
"""
Synthesise the "looking up" pose (adit5) from the registered adit1 cut-out.

No photo of this pose exists, so the irises are moved up inside each eye:
  1. eye opening = Vision eye contour (scripts/eye_regions.swift)
  2. the iris is painted out, row by row, with the sclera colour either side
  3. a round iris is redrawn higher up and clipped to the eye opening, so the
     upper lid hides its top and white shows underneath

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

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "adit1-cut.png"
OUT = ROOT / "assets" / "adit5-cut"

LIFT = 0.80      # how far the iris moves up, as a fraction of the iris radius
IRIS_R = 0.22    # iris radius as a fraction of the eye width
SS = 4           # supersampling for smooth masks


def landmarks() -> dict:
    out = subprocess.run(
        ["swift", str(ROOT / "scripts" / "eye_regions.swift"), str(SRC)],
        capture_output=True, text=True, check=True,
    )
    return json.loads([l for l in out.stdout.splitlines() if l.startswith("{")][-1])


def polygon_mask(shape, poly, grow=1.0, feather=0.8) -> np.ndarray:
    """Soft mask (0..1) of a polygon scaled by `grow` about its centroid."""
    h, w = shape
    p = np.asarray(poly, float)
    c = p.mean(axis=0)
    p = c + (p - c) * grow
    img = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(img).polygon([tuple(q * SS) for q in p], fill=255)
    img = img.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(img, float) / 255.0


def disc_mask(shape, cx, cy, r, soft=1.2) -> np.ndarray:
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    return np.clip((r - d) / soft + 0.5, 0, 1)


def lift_eye(rgb: np.ndarray, contour, pupil) -> np.ndarray:
    h, w, _ = rgb.shape
    poly = np.asarray(contour, float)
    px, py = pupil
    eye_w = poly[:, 0].max() - poly[:, 0].min()
    r = IRIS_R * eye_w
    d = LIFT * r

    m_fill = polygon_mask((h, w), contour, grow=1.18, feather=1.2)   # area we may repaint
    m_clip = polygon_mask((h, w), contour, grow=0.93, feather=0.8)  # visible opening
    x0, x1 = int(poly[:, 0].min()) - 3, int(poly[:, 0].max()) + 4
    y0, y1 = int(poly[:, 1].min()) - 3, int(poly[:, 1].max()) + 4
    xs = np.arange(w)

    # 1. paint the iris out with the colour either side of it, row by row
    filled = rgb.copy()
    reach = r * 1.3
    for y in range(y0, y1):
        lx, rx = int(round(px - reach)), int(round(px + reach))
        lc = rgb[y, max(lx - 2, 0):lx + 1].mean(axis=0)
        rc = rgb[y, rx:rx + 3].mean(axis=0)
        span = np.arange(lx, rx + 1)
        t = (span - lx) / max(rx - lx, 1)
        filled[y, span] = lc[None, :] * (1 - t[:, None]) + rc[None, :] * t[:, None]
    band = np.clip((r * 1.25 - np.abs(xs - px)) / 2.0 + 0.5, 0, 1)[None, :]
    paint = (band * m_fill)[..., None]
    clean = rgb * (1 - paint) + filled * paint

    # 2. redraw a round iris higher up, sampling the original visible band
    open_rows = m_clip > 0.5
    moved = clean.copy()
    for x in range(x0, x1):
        rows = np.where(open_rows[:, x])[0]
        if rows.size < 3:
            continue
        top, bot = rows.min() + 1, rows.max() - 1
        for y in range(y0 - int(d) - 2, y1):
            moved[y, x] = rgb[int(round(np.clip(y + d, top, bot))), x]

    iris = (disc_mask((h, w), px, py - d, r) * m_clip)[..., None]
    return clean * (1 - iris) + moved * iris


def main() -> None:
    lm = landmarks()
    im = Image.open(SRC).convert("RGBA")
    arr = np.asarray(im).astype(float)
    rgb, alpha = arr[..., :3], arr[..., 3:]

    for side in ("left", "right"):
        rgb = lift_eye(rgb, lm[f"{side}Eye"], lm[f"{side}Pupil"][0])

    out = Image.fromarray(np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8), "RGBA")
    out.save(OUT.with_suffix(".png"), optimize=True)
    out.save(OUT.with_suffix(".webp"), quality=88, method=6)
    print("wrote", OUT.with_suffix(".png").name, "+ .webp")


if __name__ == "__main__":
    main()
