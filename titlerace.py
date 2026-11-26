"""'Who will win <league>?' title-race graphic (1080x1350), drawn from the live ESPN table.

render_title_race(lg, rows, fetch_logo, matchweek=None) -> PIL.Image
rows: parsed standings rows (team, full, logo, mp, w, d, l, gd, pts, pos), sorted by position.
fetch_logo(url, size) -> RGBA image or None (club crest; initials are drawn when missing).
"""
import math, os, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

W, H = 1080, 1350
HERE = os.path.dirname(os.path.abspath(__file__))
NAVY = (8, 16, 44)
GOLD = (255, 205, 30)
GOLD2 = (255, 160, 0)
WHITE = (255, 255, 255)
RED = (200, 20, 40)

LEAGUE_TITLE = {"eng.1": "PREMIER LEAGUE", "esp.1": "LA LIGA", "ita.1": "SERIE A", "ger.1": "BUNDESLIGA",
                "fra.1": "LIGUE 1", "ksa.1": "SAUDI PRO LEAGUE", "tur.1": "SÜPER LIG", "usa.1": "THE EAST"}
SHORT = {  # nicknames for the 'pick your champion' line
    "barcelona": "BARÇA", "real madrid": "REAL", "atlético": "ATLETI", "atletico": "ATLETI",
    "manchester city": "CITY", "man city": "CITY", "manchester united": "UNITED", "man united": "UNITED",
    "tottenham": "SPURS", "inter": "INTER", "milan": "MILAN", "juventus": "JUVE", "napoli": "NAPOLI",
    "bayern": "BAYERN", "dortmund": "BVB", "leverkusen": "LEVERKUSEN", "rb leipzig": "LEIPZIG",
    "paris saint": "PSG", "psg": "PSG", "marseille": "OM", "hilal": "HILAL", "nassr": "NASSR",
    "ittihad": "ITTIHAD", "qadsiah": "QADSIAH", "qadisiyah": "QADSIAH", "ahli": "AL AHLI", "inter miami": "MIAMI",
}


def _font(size, black=True, italic=True):
    names = []
    if black:
        names += [os.path.join(HERE, "fonts", "InterDisplay-BlackItalic.otf" if italic else "InterDisplay-Black.otf"),
                  "/usr/share/fonts/opentype/inter/InterDisplay-BlackItalic.otf" if italic else
                  "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"]
    names += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if italic else
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _text_img(text, size, fill, squeeze=0.86, italic=True, stroke=0, stroke_fill=(0, 0, 0)):
    """Text rendered on its own layer, then squeezed horizontally for a condensed sports look."""
    f = _font(size, italic=italic)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im.resize((max(1, int(im.width * squeeze)), im.height), Image.LANCZOS)


def _gradient_text(text, size, top, bottom, squeeze=0.86, max_w=None):
    mask = _text_img(text, size, (255, 255, 255, 255), squeeze)
    if max_w and mask.width > max_w:
        mask = mask.resize((max_w, int(mask.height * max_w / mask.width)), Image.LANCZOS)
    grad = Image.new("RGBA", mask.size)
    gd = ImageDraw.Draw(grad)
    for y in range(mask.height):
        k = y / max(1, mask.height - 1)
        gd.line((0, y, mask.width, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)) + (255,))
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask.split()[3])
    return out


def _shadowed(img, offset=(6, 8), blur=6, alpha=170):
    a = Image.new("L", (img.width + 40, img.height + 40), 0)
    a.paste(img.split()[3].point(lambda v: v * alpha // 255), (20 + offset[0], 20 + offset[1]))
    sh = Image.new("RGBA", a.size, (0, 0, 0, 0))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(blur)))
    sh.alpha_composite(img, (20, 20))
    return sh


def _background(seed):
    rnd = random.Random(seed)
    bg = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(bg)
    for y in range(H):  # vertical navy gradient, brighter in the middle (pitch lights)
        k = max(0.0, 1 - abs(y - H * 0.38) / (H * 0.55)) ** 1.6
        c = (int(4 + 18 * k), int(9 + 34 * k), int(28 + 80 * k))
        d.line((0, y, W, y), fill=c)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    for x0 in (60, 300, 780, 1020):  # floodlight banks
        for i in range(22):
            x = x0 + rnd.randint(-70, 70)
            y = 300 + rnd.randint(-40, 40)
            r = rnd.randint(2, 5)
            g.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 240))
    for _ in range(2600):  # crowd specks
        x, y = rnd.randint(0, W), rnd.randint(330, 900)
        c = rnd.choice([(40, 60, 120), (70, 90, 160), (25, 35, 80), (120, 130, 190)])
        g.point((x, y), fill=c)
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    halo = Image.new("RGB", (W, H), (0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse((-100, 200, W + 100, 640), fill=(30, 60, 140))
    for sx in (90, W - 90):  # light beams from the floodlights
        hd.polygon([(sx - 30, 300), (sx + 30, 300), (W // 2 + (sx - W // 2) // 3 + 160, 900), (W // 2 + (sx - W // 2) // 3 - 160, 900)], fill=(25, 45, 100))
    halo = halo.filter(ImageFilter.GaussianBlur(90))
    bg = ImageChops.add(bg, halo)
    bg = ImageChops.add(bg, glow)
    # red corner slashes
    d = ImageDraw.Draw(bg)
    d.polygon([(0, 0), (120, 0), (0, 95)], fill=RED)
    d.polygon([(W, H), (W - 150, H), (W, H - 110)], fill=RED)
    d.polygon([(0, H - 60), (110, H - 150), (130, H - 140), (20, H - 40)], fill=RED)
    d.polygon([(W, 60), (W - 90, 140), (W - 110, 130), (W - 20, 40)], fill=RED)
    return bg.convert("RGBA")


def _dominant(im):
    if im is None:
        return (60, 90, 170)
    small = im.convert("RGBA").resize((32, 32))
    best, score = (60, 90, 170), -1
    counts = {}
    for r, g, b, a in small.getdata():
        if a < 200:
            continue
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn < 40 or mx < 70:  # skip greys / near black / white
            continue
        key = (r // 32 * 32 + 16, g // 32 * 32 + 16, b // 32 * 32 + 16)
        counts[key] = counts.get(key, 0) + 1
    for k, v in counts.items():
        if v > score:
            best, score = k, v
    return best


def _initials(name, size, color):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,), outline=WHITE, width=max(2, size // 30))
    t = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    f = _font(int(size * 0.4), italic=False)
    l, tp, r, b = d.textbbox((0, 0), t, font=f)
    d.text(((size - (r - l)) / 2 - l, (size - (b - tp)) / 2 - tp), t, font=f, fill=WHITE)
    return im


def _crest(row, size, fetch_logo):
    im = fetch_logo(row.get("logo"), size) if fetch_logo else None
    if im is None:
        return _initials(row["team"], size, (60, 90, 170)), (60, 90, 170)
    return im, _dominant(im)


def _medallion(row, size, fetch_logo, place):
    crest, col = _crest(row, int(size * 0.62), fetch_logo)
    m = Image.new("RGBA", (size + 80, size + 80), (0, 0, 0, 0))
    ga = Image.new("L", m.size, 0)
    ImageDraw.Draw(ga).ellipse((22, 22, size + 58, size + 58), fill=190)
    glow = Image.new("RGBA", m.size, col + (0,))
    glow.putalpha(ga.filter(ImageFilter.GaussianBlur(20)))
    m = Image.alpha_composite(m, glow)
    d = ImageDraw.Draw(m)
    c = 40
    d.ellipse((c, c, c + size, c + size), fill=(10, 20, 55, 255), outline=GOLD if place == 1 else WHITE,
              width=8 if place == 1 else 5)
    inner = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(inner).ellipse((10, 10, size - 10, size - 10), fill=tuple(int(v * 0.45) for v in col) + (255,))
    m.alpha_composite(inner, (c, c))
    m.alpha_composite(crest, (c + (size - crest.width) // 2, c + (size - crest.height) // 2))
    return m


def _nick(team):
    n = team.lower()
    for k, v in SHORT.items():
        if k in n:
            return v
    return team.upper()


def render_title_race(lg, rows, fetch_logo=None, matchweek=None, season="2026/27", n=3, brand="INFINITE SPORT"):
    rows = rows[:n]
    img = _background(lg)
    d = ImageDraw.Draw(img)
    mw = matchweek or max(r["mp"] for r in rows)

    # ribbon
    rib = f"{season} TITLE RACE  •  MATCHWEEK {mw}"
    t = _text_img(rib, 40, WHITE, 0.92)
    rw = t.width + 70
    rx = (W - rw) // 2
    d.polygon([(rx + 14, 22), (rx + rw, 22), (rx + rw - 14, 82), (rx, 82)], fill=(150, 10, 25))
    img.alpha_composite(t, (rx + 35, 52 - t.height // 2))

    # headline
    h1 = _shadowed(_text_img("WHO WILL WIN", 118, WHITE, 0.84))
    img.alpha_composite(h1, ((W - h1.width) // 2, 92))
    title = LEAGUE_TITLE.get(lg, lg.upper()) + "?"
    size = 190 if len(title) <= 9 else 150 if len(title) <= 12 else 118
    h2 = _shadowed(_gradient_text(title, size, (255, 236, 90), GOLD2, 0.84, max_w=W - 120), offset=(7, 10))
    img.alpha_composite(h2, ((W - h2.width) // 2, 228))

    # podium of crests: 2nd left, leader centre (bigger, higher), 3rd right
    top_y = 228 + h2.height - 10
    spots = [(0, W // 2, 270, top_y), (1, 225, 210, top_y + 60), (2, W - 225, 210, top_y + 60)] if len(rows) >= 3 else []
    order = sorted(spots, key=lambda s: s[2])  # draw small ones first
    for idx, cx, sz, y in order:
        med = _medallion(rows[idx], sz, fetch_logo, idx + 1)
        img.alpha_composite(med, (cx - med.width // 2, y))
        lab = _shadowed(_text_img(f"{idx + 1}{['ST', 'ND', 'RD'][idx]}", 44, GOLD if idx == 0 else WHITE, 0.9), blur=4)
        img.alpha_composite(lab, (cx - lab.width // 2, y + med.height - 62))

    # table
    ty = 792
    rh = 86
    hh = 64
    x0, x1 = 30, W - 30
    pts_x = W - 190
    panel = Image.new("RGBA", (x1 - x0, hh + rh * len(rows)), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), 14, fill=(12, 22, 60, 235), outline=(255, 200, 40), width=3)
    pd.rounded_rectangle((pts_x - x0, 0, panel.width - 1, panel.height - 1), 14, fill=GOLD)
    pd.rectangle((pts_x - x0, 0, pts_x - x0 + 20, panel.height - 1), fill=GOLD)
    for i in range(1, len(rows) + 1):
        y = hh + rh * i
        if i < len(rows):
            pd.line((8, y, panel.width - 8, y), fill=(60, 80, 140), width=2)
    pd.line((8, hh, panel.width - 8, hh), fill=(60, 80, 140), width=2)
    img.alpha_composite(_shadowed(panel, blur=10), (x0 - 20, ty - 20))
    cols = {"MP": 528, "W": 607, "D": 680, "L": 752, "GD": 840}
    hf = 34
    head = [("#", 70, WHITE), ("TEAM", 220, WHITE)] + [(k, v, WHITE) for k, v in cols.items()] + [("PTS", (pts_x + x1) // 2, NAVY)]
    for txt, cx, col in head:
        ti = _text_img(txt, hf, col, 0.9)
        x = cx - ti.width // 2 if txt not in ("TEAM",) else cx - 50
        img.alpha_composite(ti, (x, ty + (hh - ti.height) // 2))
    for i, r in enumerate(rows):
        cy = ty + hh + rh * i + rh // 2
        p = _text_img(str(r["pos"]), 64, GOLD, 0.9)
        img.alpha_composite(p, (70 - p.width // 2, cy - p.height // 2))
        cr, _ = _crest(r, 64, fetch_logo)
        img.alpha_composite(cr, (175 - cr.width // 2, cy - cr.height // 2))
        name = (r.get("full") or r["team"]).upper()
        nm = _text_img(name, 42, WHITE, 0.8, italic=False)
        if nm.width > 262:
            nm = nm.resize((262, nm.height), Image.LANCZOS)
        img.alpha_composite(nm, (225, cy - nm.height // 2))
        gd = f"+{r['gd']}" if r["gd"] > 0 else str(r["gd"])
        for k, v in zip(cols, (r["mp"], r["w"], r["d"], r["l"], gd)):
            ti = _text_img(str(v), 42, WHITE, 0.86, italic=False)
            img.alpha_composite(ti, (cols[k] - ti.width // 2, cy - ti.height // 2))
        pt = _text_img(str(r["pts"]), 72, NAVY, 0.9, italic=False)
        img.alpha_composite(pt, ((pts_x + x1) // 2 - pt.width // 2, cy - pt.height // 2))

    # yellow brush banner
    by = ty + hh + rh * len(rows) + 14
    brush = Image.new("RGBA", (W, 118), (0, 0, 0, 0))
    bd = ImageDraw.Draw(brush)
    rnd = random.Random(lg + "b")
    bd.polygon([(70, 16), (W - 40, 6), (W - 70, 102), (40, 112)], fill=GOLD + (255,))
    for _ in range(40):  # ragged brush edges
        x = rnd.randint(30, W - 30)
        yy = rnd.choice([rnd.randint(4, 16), rnd.randint(102, 114)])
        bd.ellipse((x - 18, yy - 6, x + 18, yy + 6), fill=GOLD + (255,))
    img.alpha_composite(brush, (0, by))
    q = _text_img("WHO LIFTS THE TROPHY?", 76, NAVY, 0.84)
    img.alpha_composite(q, ((W - q.width) // 2, by + 58 - q.height // 2))

    picks = "  •  ".join(_nick(r["team"]) for r in rows)
    l1 = _shadowed(_text_img(picks + "  —", 40, WHITE, 0.88), blur=4)
    l2 = _shadowed(_text_img("PICK YOUR CHAMPION", 40, GOLD, 0.88), blur=4)
    line = Image.new("RGBA", (l1.width + l2.width - 30, max(l1.height, l2.height)), (0, 0, 0, 0))
    line.alpha_composite(l1, (0, 0))
    line.alpha_composite(l2, (l1.width - 30, 0))
    if line.width > W - 50:
        line = line.resize((W - 50, int(line.height * (W - 50) / line.width)), Image.LANCZOS)
    img.alpha_composite(line, ((W - line.width) // 2, by + 104 + (l1.height - line.height) // 2))

    # brand mark
    bm = _text_img(brand, 24, (255, 255, 255, 210), 0.95, italic=False)
    img.alpha_composite(bm, ((W - bm.width) // 2, H - bm.height - 10))
    return img.convert("RGB")


if __name__ == "__main__":  # preview with sample data, no network
    sample = [dict(team="Barcelona", full="FC Barcelona", logo=None, mp=12, w=11, d=0, l=1, gd=35, pts=33, pos=1),
              dict(team="Real Madrid", full="Real Madrid", logo=None, mp=12, w=10, d=0, l=2, gd=21, pts=30, pos=2),
              dict(team="Atlético", full="Atlético Madrid", logo=None, mp=12, w=9, d=1, l=2, gd=13, pts=28, pos=3)]
    render_title_race("esp.1", sample).save("/tmp/titlerace_esp.png")
    s2 = [dict(team="Al Hilal", full="Al Hilal", logo=None, mp=11, w=9, d=3, l=0, gd=23, pts=30, pos=1),
          dict(team="Al Qadsiah", full="Al Qadsiah", logo=None, mp=11, w=9, d=1, l=1, gd=15, pts=28, pos=2),
          dict(team="Al Nassr", full="Al Nassr", logo=None, mp=11, w=9, d=1, l=1, gd=17, pts=28, pos=3)]
    render_title_race("ksa.1", s2).save("/tmp/titlerace_ksa.png")
    print("ok")
