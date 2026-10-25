# Aditya Venkataraman — personal site

A single interactive hero, inspired by [trevornoah.com](https://www.trevornoah.com/):
the name, the set `{ Glaciers, Climbing, Puzzles, Professional }`, and a cut-out
portrait that reacts.

**Four poses, all registered to the same eye position so swaps don't jump:**

| pose | when | extra |
|------|------|-------|
| `adit1` | resting (cursor over the figure, or touch) | — |
| `adit2` | a topic word is hovered / focused / tapped | emoji pair drops over the eyes, themed glow |
| `adit4` | cursor is anywhere left of the figure | he glances left, toward the cursor |
| `adit3` | cursor is anywhere right of the figure | he glances right, toward the cursor |

A topic always wins over the gaze. The gaze only runs for a fine pointer with
motion allowed. Which pose maps to which side is set by the `src` on
`.portrait__img--left` / `--right` in `index.html` — swap those to flip it.

**Topic emoji (one over each eye):**

| word | emoji ×2 |
|------|----------|
| Glaciers | 🧊 🧊 |
| Climbing | 🪨 🪨 |
| Puzzles | 🧩 🧩 |
| Professional | 📝 📝 |

## What to deploy

Static — no build step, no dependencies. Publish these to any host
(GitHub Pages, Netlify, Cloudflare Pages, …):

```
index.html
styles.css
script.js
assets/            # adit{1,2,3,4}-cut.{webp,png}
```

Everything else (`scripts/`, `adit*.jpeg`, `adit2.png`, `reference/`) is
build-time only.

Local preview:

```bash
python3 -m http.server 4599   # then open http://localhost:4599
```

## Regenerating the portraits

The four source selfies are shot against a cream wall with different framing.
The pipeline removes the background and registers every pose to a shared eye
anchor so the **eyes stay locked** when the face swaps.

Needs macOS 14+ (Vision framework) and the Anaconda Python (`Pillow`, `numpy`,
`scipy`):

```bash
# 1. background removal  ->  scripts/_lifted/
swift scripts/lift_subject.swift adit1.jpeg scripts/_lifted/adit1-cut.png
swift scripts/lift_subject.swift adit2.png  scripts/_lifted/adit2-cut.png
swift scripts/lift_subject.swift adit3.jpeg scripts/_lifted/adit3-cut.png
swift scripts/lift_subject.swift adit4.jpeg scripts/_lifted/adit4-cut.png

# 2. detect eyes, register, clean, export  ->  assets/  (png + webp)
/opt/anaconda3/bin/python3 scripts/build_portraits.py
```

Poses and per-pose `trim` (head-size match) are listed in `JOBS` at the top of
`scripts/build_portraits.py`.

`build_portraits.py` prints the shared eye anchor (`--eye-x` / `--eye-y`) and the
portrait `aspect-ratio`; if you change the canvas constants, update the matching
values in `styles.css` (`:root`).

To use different photos: drop in new `aditN` source files, re-run both steps,
then re-check these knobs in `styles.css :root`:

- `--eye-y` — vertical line the emoji pair sits on (% of portrait height)
- `--eye-gap` — half the eye spacing (% of portrait width); should match adit2
- `--emoji-size` — glyph size (× portrait width); per-theme overrides live in
  `.portrait[data-theme="…"] .portrait__emoji` along with `--emoji-dy`

## Notes

- Palette: alpine ice (cold luminous field, charcoal type, one amber accent).
- Type: Bricolage Grotesque (display) + Space Grotesk (UI), via Google Fonts.
- Accessible: the four words are real buttons — keyboard focus triggers the same
  preview as hover, `aria-pressed` reflects the pinned state, emoji are
  `aria-hidden`, and `prefers-reduced-motion` drops the spring/parallax.
- Touch: no hover, so a tap pins a state and a second tap (or tapping elsewhere,
  or Esc) releases it. The look-left / look-right gaze is pointer-only.
- Gaze boundary is the portrait element's box; tune it in `script.js`
  (`x < pRect.left` / `x > pRect.right`).
