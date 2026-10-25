#!/usr/bin/env python3
"""
Build the two hero portraits so the eyes stay locked when they swap.

Pipeline
--------
1. scripts/lift_subject.swift  -> scripts/_lifted/aditN-cut.png   (bg removed)
2. scripts/face_points.swift   -> eye centres for each source photo
3. this script                 -> register + clean + export assets/aditN-cut.png

Both outputs are the same canvas size with the eye midpoint at the same
spot and the same inter-ocular distance, so only the expression + emoji
change on hover.  The shared eye anchor is printed at the end for the CSS.

Run:  /opt/anaconda3/bin/python3 scripts/build_portraits.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIFTED = ROOT / "scripts" / "_lifted"
ASSETS = ROOT / "assets"
SCRATCH = pathlib.Path(
    "/private/tmp/claude-501/-Users-balajivenkataraman-Documents-AditPortfolioSite"
    "/01cc523f-4417-402c-9baf-5fe6a16c0fb5/scratchpad"
)

# shared target frame — generous headroom so the hair crown never clips
CANVAS_W, CANVAS_H = 1024, 1320
EYE_X, EYE_Y = CANVAS_W / 2, 540.0
TARGET_IOD = 250.0
OUT_MAX_EDGE = 1000

# `trim` shrinks the head about the eye midpoint (eyes stay locked) so every
# pose reads at a similar overall size on swap — adit2 is shot closer.
#   adit1 = base    adit2 = topic hover    adit3 = look left    adit4 = look right
JOBS = [
    {"src": "adit1.jpeg", "lifted": "adit1-cut.png", "out": "adit1-cut.png", "trim": 1.0},
    {"src": "adit2.png", "lifted": "adit2-cut.png", "out": "adit2-cut.png", "trim": 0.92},
    {"src": "adit3.jpeg", "lifted": "adit3-cut.png", "out": "adit3-cut.png", "trim": 1.0},
    {"src": "adit4.jpeg", "lifted": "adit4-cut.png", "out": "adit4-cut.png", "trim": 1.0},
]


def eye_points(src: str) -> dict:
    out = subprocess.run(
        ["swift", str(ROOT / "scripts" / "face_points.swift"), str(ROOT / src)],
        capture_output=True, text=True, check=True,
    )
    line = [l for l in out.stdout.splitlines() if l.strip().startswith("{")][-1]
    return json.loads(line)


def clean_alpha(im: Image.Image) -> Image.Image:
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.MinFilter(3))          # bite off the 1px cream rim
    a = a.filter(ImageFilter.GaussianBlur(0.8))     # then feather
    return Image.merge("RGBA", (r, g, b, a))


def register(lifted_path: pathlib.Path, eyes: dict, trim: float = 1.0) -> Image.Image:
    im = clean_alpha(Image.open(lifted_path).convert("RGBA"))

    eL = np.array(eyes["eyeL"], dtype=float)
    eR = np.array(eyes["eyeR"], dtype=float)
    mid = (eL + eR) / 2.0
    d = eR - eL
    iod = float(np.hypot(*d))
    ang = np.arctan2(d[1], d[0])          # roll of the eye line
    s = TARGET_IOD / iod * trim

    # forward: translate(-mid) -> rotate(-ang)+scale(s) -> translate(+target)
    phi = -ang
    cos, sin = np.cos(phi), np.sin(phi)
    A = np.array([[s * cos, -s * sin, 0.0],
                  [s * sin,  s * cos, 0.0],
                  [0.0,      0.0,     1.0]])
    T_in = np.array([[1, 0, -mid[0]], [0, 1, -mid[1]], [0, 0, 1]], dtype=float)
    T_out = np.array([[1, 0, EYE_X], [0, 1, EYE_Y], [0, 0, 1]], dtype=float)
    M_fwd = T_out @ A @ T_in
    M_inv = np.linalg.inv(M_fwd)
    coeffs = (M_inv[0, 0], M_inv[0, 1], M_inv[0, 2],
              M_inv[1, 0], M_inv[1, 1], M_inv[1, 2])

    return im.transform((CANVAS_W, CANVAS_H), Image.AFFINE, coeffs,
                        resample=Image.BICUBIC)


def finish(im: Image.Image, out_name: str) -> None:
    if max(im.size) > OUT_MAX_EDGE:
        k = OUT_MAX_EDGE / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    ASSETS.mkdir(exist_ok=True)
    im.save(ASSETS / out_name, optimize=True)
    webp_name = out_name.rsplit(".", 1)[0] + ".webp"
    im.save(ASSETS / webp_name, quality=88, method=6)
    png_kb = (ASSETS / out_name).stat().st_size // 1024
    webp_kb = (ASSETS / webp_name).stat().st_size // 1024
    print(f"  {out_name}: {im.width}x{im.height}  (png {png_kb} KB / webp {webp_kb} KB)")

    stem = out_name.split("-")[0]
    for rgb, tag in [((210, 226, 234), "ice"), ((15, 20, 26), "dark")]:
        c = Image.new("RGBA", im.size, rgb + (255,))
        c.alpha_composite(im)
        c.convert("RGB").save(SCRATCH / f"qa_{stem}_{tag}.png")


if __name__ == "__main__":
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for job in JOBS:
        eyes = eye_points(job["src"])
        print(f"{job['src']}: eyes {eyes['eyeL']} {eyes['eyeR']}  trim={job['trim']}")
        finish(register(LIFTED / job["lifted"], eyes, job["trim"]), job["out"])

    scale = OUT_MAX_EDGE / max(CANVAS_W, CANVAS_H)
    print(
        "\nCSS anchor -> --eye-x: {:.1f}%;  --eye-y: {:.1f}%;  aspect-ratio: {} / {}".format(
            EYE_X / CANVAS_W * 100,
            EYE_Y / CANVAS_H * 100,
            round(CANVAS_W * scale),
            round(CANVAS_H * scale),
        )
    )
