"""Generates simple, on-brand SVG posters and artist images.

Used by seed.py for the demo data and by the admin panel when a concert
or artist is saved without an uploaded image.
"""
import os
import random
from xml.sax.saxutils import escape

BROWN, BLUE, CREAM = "#432F2E", "#C3DAE8", "#FEEFB6"
DEEP, MID, BLUE_D, CREAM_D = "#24191A", "#6E4F4C", "#8FB3CB", "#F2D77E"
FONT = "Manrope, 'Helvetica Neue', Arial, sans-serif"

SCHEMES = [
    {"bg1": BROWN, "bg2": DEEP, "a": BLUE, "b": CREAM, "text": CREAM, "sub": BLUE},
    {"bg1": BLUE, "bg2": BLUE_D, "a": BROWN, "b": CREAM, "text": BROWN, "sub": DEEP},
    {"bg1": CREAM, "bg2": CREAM_D, "a": BROWN, "b": BLUE_D, "text": BROWN, "sub": MID},
    {"bg1": DEEP, "bg2": MID, "a": CREAM, "b": BLUE, "text": CREAM, "sub": CREAM_D},
]


def _wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def _motif(style, s, rnd):
    parts = []
    if style == 0:  # concentric sound rings
        cx, cy = rnd.randint(300, 460), rnd.randint(220, 320)
        for i, r in enumerate(range(40, 520, 38)):
            col = s["a"] if i % 2 == 0 else s["b"]
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" '
                         f'stroke-width="{3 if i % 3 else 7}" opacity="{max(0.12, 0.85 - i * 0.06):.2f}"/>')
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="26" fill="{s["b"]}"/>')
    elif style == 1:  # waveform bars
        n, w = 34, 600 / 34
        for i in range(n):
            h = min(60 + abs(rnd.gauss(0, 1)) * 150, 380)
            col = s["a"] if i % 3 else s["b"]
            parts.append(f'<rect x="{i * w + 3:.1f}" y="{300 - h / 2:.1f}" width="{w - 6:.1f}" '
                         f'height="{h:.1f}" rx="{(w - 6) / 2:.1f}" fill="{col}" opacity="0.9"/>')
    elif style == 2:  # setting sun with stripes
        parts.append(f'<circle cx="300" cy="300" r="210" fill="{s["b"]}"/>')
        for i in range(7):
            y = 330 + i * 26
            parts.append(f'<rect x="60" y="{y}" width="480" height="{8 + i * 2}" fill="{s["bg1"]}"/>')
        parts.append(f'<circle cx="300" cy="300" r="210" fill="none" stroke="{s["a"]}" stroke-width="4"/>')
    else:  # dot grid
        for gx in range(12):
            for gy in range(11):
                r = rnd.choice([3, 4, 6, 9, 13])
                col = rnd.choice([s["a"], s["b"], s["b"]])
                parts.append(f'<circle cx="{40 + gx * 47}" cy="{60 + gy * 44}" r="{r}" fill="{col}" '
                             f'opacity="{rnd.uniform(0.35, 1):.2f}"/>')
    return "".join(parts)


def poster_svg(title, artist, date_text, venue, seed):
    rnd = random.Random(seed)
    s = SCHEMES[seed % len(SCHEMES)]
    style = (seed // len(SCHEMES) + seed) % 4
    name_lines = _wrap(artist.upper(), 14)
    size = 64 if max(len(l) for l in name_lines) <= 10 else 50
    y0 = 600
    name_svg = "".join(
        f'<text x="40" y="{y0 + i * (size + 4)}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="800" letter-spacing="-1" fill="{s["text"]}">{escape(l)}</text>'
        for i, l in enumerate(name_lines))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" width="600" height="800">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{s["bg1"]}"/><stop offset="1" stop-color="{s["bg2"]}"/></linearGradient>
<clipPath id="c"><rect width="600" height="520"/></clipPath></defs>
<rect width="600" height="800" fill="url(#g)"/>
<g clip-path="url(#c)">{_motif(style, s, rnd)}</g>
<text x="40" y="{y0 - size - 6}" font-family="{FONT}" font-size="20" font-weight="600" letter-spacing="4" fill="{s["sub"]}">{escape(title.upper()[:38])}</text>
{name_svg}
<line x1="40" y1="726" x2="560" y2="726" stroke="{s["sub"]}" stroke-width="1.5" opacity="0.6"/>
<text x="40" y="760" font-family="{FONT}" font-size="20" font-weight="700" fill="{s["text"]}">{escape(date_text)}</text>
<text x="560" y="760" text-anchor="end" font-family="{FONT}" font-size="18" fill="{s["sub"]}">{escape(venue[:30])}</text>
</svg>'''


def artist_svg(name, seed):
    rnd = random.Random(seed * 7 + 3)
    s = SCHEMES[(seed + 1) % len(SCHEMES)]
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    rings = "".join(
        f'<circle cx="{rnd.randint(260, 360)}" cy="{rnd.randint(40, 140)}" r="{r}" fill="none" '
        f'stroke="{s["a"] if i % 2 else s["b"]}" stroke-width="3" opacity="0.5"/>'
        for i, r in enumerate(range(40, 300, 34)))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{s["bg1"]}"/><stop offset="1" stop-color="{s["bg2"]}"/></linearGradient></defs>
<rect width="400" height="400" fill="url(#g)"/>{rings}
<text x="40" y="340" font-family="{FONT}" font-size="150" font-weight="800" letter-spacing="-6" fill="{s["text"]}">{escape(initials)}</text>
</svg>'''


def save_svg(static_dir, subfolder, filename, svg):
    folder = os.path.join(static_dir, "img", subfolder)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), "w", encoding="utf-8") as fh:
        fh.write(svg)
    return f"img/{subfolder}/{filename}"
