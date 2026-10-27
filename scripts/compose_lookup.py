#!/usr/bin/env python3
"""
Build the "looking up" pose (assets/adit5-cut) from the adit5 photo.

The adit5 photo is a close crop in a hoodie; every other pose wears the grey
t-shirt. So the head from adit5 is placed on the neck + t-shirt of adit3 (also
a looking-up pose, so the neck angle matches). Both are already registered to
the shared eye anchor by build_portraits.py, and their chins land within a few
pixels of each other, so the seam can follow adit5's jawline.

  head  = adit5 above its jawline, minus any hoodie fabric
  body  = adit3 (neck + t-shirt), with the neck skin nudged toward adit5's tone

Run after build_portraits.py:
  /opt/anaconda3/bin/python3 scripts/compose_lookup.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = ROOT / "scripts" / "_lifted" / "adit5-head.png"
BODY = ROOT / "assets" / "adit3-cut.png"
OUT = ROOT / "assets" / "adit5-cut"

JAW_DROP = 4        # px below the detected jawline that still counts as head
LOBE_FRAC = 0.42    # ear-lobe level, as a fraction of the eye->chin height above the chin
JAW_MARGIN = 8      # px below adit3's detected jawline still treated as its face (stubble edge)
JAW_SMOOTH = 7      # px of smoothing on the detected jawlines
NECK_SPAN = 60      # px of adit3's neck that get stretched up to meet adit5's jaw
SEAM_FEATHER = 1.6  # px of blur on the head mask edge
TONE_BLEND = 0.9    # how far to warm the head toward the body photo's skin tone


def landmarks(path: pathlib.Path) -> dict:
    out = subprocess.run(
        ["swift", str(ROOT / "scripts" / "eye_regions.swift"), str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads([l for l in out.stdout.splitlines() if l.startswith("{")][-1])


def jaw_curve(contour: np.ndarray, w: int) -> tuple[np.ndarray, int, int]:
    """y of the jawline for each x inside the face contour (NaN outside)."""
    c = contour[np.argsort(contour[:, 0])]
    x0, x1 = int(np.ceil(c[0, 0])), int(np.floor(c[-1, 0]))
    jaw = np.full(w, np.nan)
    xs = np.arange(x0, x1 + 1)
    # the contour runs ear -> chin -> ear, so for each x take its lowest point
    lower = {}
    for x, y in contour:
        k = int(round(x))
        lower[k] = max(lower.get(k, -1), y)
    kx = np.array(sorted(lower)); ky = np.array([lower[k] for k in kx])
    # the contour is only 17 points; smooth the straight segments into a curve
    jaw[xs] = ndimage.gaussian_filter1d(np.interp(xs, kx, ky), JAW_SMOOTH, mode="nearest")
    return jaw, x0, x1


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > g + 8) & (g > b - 6) & (r > 60) & (r < 245)


def main() -> None:
    head = np.asarray(Image.open(HEAD).convert("RGBA")).astype(float)
    body = np.asarray(Image.open(BODY).convert("RGBA")).astype(float)
    h, w, _ = head.shape
    yy, xx = np.mgrid[0:h, 0:w]

    lm = landmarks(HEAD)
    contour = np.asarray(lm["faceContour"], float)
    jaw, jx0, jx1 = jaw_curve(contour, w)
    ear_y = contour[[0, -1], 1].mean()

    # --- head mask -------------------------------------------------------
    h_rgb, h_a = head[..., :3], head[..., 3] / 255.0
    below_jaw = np.zeros((h, w), bool)
    # only cut along the lower jaw / chin; up by the cheeks the contour sits
    # inside the real silhouette and a geometric cut would slice the face
    eye_y = np.mean([p[1] for p in lm["leftEye"] + lm["rightEye"]])
    chin = np.nanmax(jaw)
    lobe_y = chin - LOBE_FRAC * (chin - eye_y)            # roughly ear-lobe level
    # cut line: follows the jaw around the chin, flattens out at ear-lobe level
    # beside the face (below that it is all hood / neck, which adit3 supplies)
    cut_y = np.fmax(jaw + JAW_DROP, lobe_y - 10)          # NaN outside the face -> lobe level
    below_jaw = yy > cut_y[None, :]

    # hoodie: grey, low-chroma fabric below ear level that runs off the
    # bottom of the original photo (the photo is cropped right at the chin)
    chroma = h_rgb.max(axis=2) - h_rgb.min(axis=2)
    lum = h_rgb.mean(axis=2)
    crop_bottom = np.where((h_a > 0.5).any(axis=1))[0].max()
    fabric = (h_a > 0.5) & (chroma < 28) & (lum > 55) & (lum < 215) & (yy > ear_y + 30)
    lbl, n = ndimage.label(fabric)
    hood = np.zeros_like(fabric)
    for i, sl in enumerate(ndimage.find_objects(lbl), 1):
        if sl is not None and sl[0].stop >= crop_bottom - 4 and (lbl[sl] == i).sum() > 150:
            hood |= lbl == i
    hood = ndimage.binary_dilation(hood, iterations=3)
    # beside the jaw, below the lobes, anything that is not skin is hood too
    hood |= (yy > lobe_y) & ((xx < jx0) | (xx > jx1)) & (h_a > 0.5) & ~skin_mask(h_rgb)

    # solid head pixels first; then allow only the soft matte edge that borders
    # them — the hoodie's own faint outline edge would otherwise survive as a
    # thin line floating beside the jaw
    solid = (h_a > 0.5) & ~below_jaw & ~hood
    solid = ndimage.binary_opening(solid, iterations=1)
    lbl, n = ndimage.label(solid)
    if n > 1:
        sizes = ndimage.sum(solid, lbl, index=np.arange(1, n + 1))
        solid = lbl == (int(np.argmax(sizes)) + 1)
    keep = ndimage.binary_dilation(solid, iterations=2) & (h_a > 0.02) & ~below_jaw & ~hood
    m = ndimage.gaussian_filter(keep.astype(float), SEAM_FEATHER) * h_a

    # --- head: match its skin tone to the body photo's lighting ------------
    # adit5 was shot in cooler, dimmer light; a per-channel gain measured on
    # cheek/forehead skin warms it to match the other poses (dark hair stays dark)
    b_rgb, b_a = body[..., :3], body[..., 3] / 255.0
    b_contour = np.asarray(landmarks(BODY)["faceContour"], float)
    b_jaw, bx0, bx1 = jaw_curve(b_contour, w)

    def face_skin(rgb, a, jaw_line, x0, x1, top):
        inside = np.zeros((h, w), bool)
        c = np.arange(x0 + 25, x1 - 25)
        inside[:, c] = (yy[:, c] < jaw_line[c][None, :] - 25) & (yy[:, c] > top)
        return inside & skin_mask(rgb) & (a > 0.9)

    eye_top = lm["leftEye"][0][1] - 60
    src = face_skin(h_rgb, h_a, jaw, jx0, jx1, eye_top) & keep
    dst = face_skin(b_rgb, b_a, b_jaw, bx0, bx1, eye_top)
    gain = b_rgb[dst].mean(axis=0) / h_rgb[src].mean(axis=0)
    gain = 1 + (gain - 1) * TONE_BLEND
    h_rgb = (h_rgb * gain[None, None, :]).clip(0, 255)
    print("head tone gain", np.round(gain, 3), f"(skin px: head {src.sum()}, body {dst.sum()})")

    # --- body: drop adit3's ears ------------------------------------------
    # adit3's ears sit lower than adit5's and would peek out underneath as a
    # second ear; its jaw and neck stay as filler under adit5's head
    b_chin = np.nanmax(b_jaw)
    b_ear_top = b_contour[[0, -1], 1].mean()
    b_lobe = b_chin - LOBE_FRAC * (b_chin - eye_y)
    ears = (yy > b_ear_top - 30) & (yy < b_lobe + 12) & ((xx < bx0 + 16) | (xx > bx1 - 16))
    b_a = b_a * (1 - ndimage.gaussian_filter(ears.astype(float), 1.5))

    # adit5's jawline sits a little higher than adit3's. Rather than show
    # adit3's jaw underneath (it pokes out past adit5's), stretch adit3's neck
    # up in each column so it meets adit5's jaw — with the head tilted back you
    # would see more neck anyway. adit3's own jaw is then hidden.
    rows = np.arange(h, dtype=float)
    in_head = m > 0.5
    head_bottom_col = np.where(in_head.any(axis=0), h - 1 - np.argmax(in_head[::-1], axis=0), -1)
    face_line = np.where(np.isnan(b_jaw), -1.0, b_jaw + JAW_MARGIN)  # adit3 face is above this
    b_rgb, b_a = b_rgb.copy(), b_a.copy()
    src_rgb, src_a = b_rgb.copy(), b_a.copy()

    # neck columns: where adit3 is solid on a row just under its chin
    neck_row = int(b_chin) + 25
    cand = (src_a[neck_row] > 0.9) & (head_bottom_col >= 0) & (face_line >= 0)
    # every other column beside the face: nothing of adit3 above its chin
    # level (the detected jawline sits inside the real jaw edge near the ears,
    # so "below the jawline" there is still jaw; the t-shirt starts lower)
    for x in range(max(bx0 - 25, 0), min(bx1 + 25, w - 1) + 1):
        if not cand[x]:
            face_line[x] = b_chin
    lbl, n = ndimage.label(cand)
    stretched = 0
    if n:
        run = max(range(1, n + 1), key=lambda i: (lbl == i).sum())
        cols = np.where(lbl == run)[0]
        # smooth the per-column targets so neighbouring columns stretch alike
        hb_s = ndimage.gaussian_filter1d(head_bottom_col[cols].astype(float), 4, mode="nearest")
        nx_s = ndimage.gaussian_filter1d(face_line[cols], 4, mode="nearest")
        for x, hb, nx in zip(cols, hb_s, nx_s):
            y0 = int(round(hb)) - 3
            if y0 >= nx:
                continue
            y1 = int(min(nx + NECK_SPAN, h - 1))
            ys = np.arange(y0, y1)
            src = nx + (ys - y0) * (y1 - nx) / (y1 - y0)
            for c in range(3):
                b_rgb[ys, x, c] = np.interp(src, rows, src_rgb[:, x, c])
            b_a[ys, x] = np.interp(src, rows, src_a[:, x])
            face_line[x] = y0 - 1
            stretched += 1
    print(f"neck stretched up in {stretched} columns")

    # hide adit3's face wherever it would show outside adit5's head silhouette
    inside_outline = ndimage.binary_dilation(ndimage.binary_fill_holes(in_head), iterations=1)
    adit3_face = yy <= face_line[None, :]
    body_keep = ~adit3_face | inside_outline
    b_a = b_a * ndimage.gaussian_filter(body_keep.astype(float), 1.0)

    # --- composite: head over body -----------------------------------------
    out_a = m + b_a * (1 - m)
    out_rgb = (h_rgb * m[..., None] + b_rgb * (b_a * (1 - m))[..., None]) / np.maximum(out_a, 1e-6)[..., None]
    out = np.dstack([out_rgb, out_a * 255]).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    im.save(OUT.with_suffix(".png"), optimize=True)
    im.save(OUT.with_suffix(".webp"), quality=88, method=6)
    print("wrote", OUT.with_suffix(".png").name, "+ .webp")


if __name__ == "__main__":
    main()
