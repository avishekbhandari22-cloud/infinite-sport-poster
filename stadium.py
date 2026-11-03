"""Draws the STANDINGS picture (stadium template) from live table rows.

render_standings(lg, rows, fetch) -> PIL RGB image 1080x1350.
rows: list of dicts with team/full, logo (url), mp, w, d, l, gd, pts (already sorted).
fetch(url, size) -> RGBA logo image or None (supplied by standings_post.py).
Nothing here is pre-made: the picture is drawn at post time, so it always matches the live table.
"""
import math, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
FD = os.path.join(HERE, "fonts") + os.sep
W, H = 1080, 1350
GOLD = (255, 214, 0); WHITE = (255, 255, 255)


def F(w, s): return ImageFont.truetype(FD + "BarlowCondensed-" + w + ".ttf", s)
def PF(s): return ImageFont.truetype(FD + "Poppins-Bold.ttf", s)


STYLE = {
    "eng.1": dict(lines=["Premier", "League"], zones=dict(ucl=4, uel=5, conf=0, po=None, rel=18), emblem=23),
    "esp.1": dict(lines=["La Liga"], zones=dict(ucl=4, uel=5, conf=6, po=None, rel=18), emblem=15),
    "ita.1": dict(lines=["Serie A"], zones=dict(ucl=4, uel=6, conf=0, po=None, rel=18), emblem=12),
    "ger.1": dict(lines=["Bundesliga"], zones=dict(ucl=4, uel=5, conf=6, po=16, rel=17), emblem=10),
    "fra.1": dict(lines=["Ligue 1"], zones=dict(ucl=4, uel=6, conf=0, po=16, rel=17), emblem=9),
    "ksa.1": dict(lines=["Saudi Pro", "League"], zones=dict(ucl=0, uel=0, conf=0, po=None, rel=16), emblem=2488),
    "usa.1": dict(lines=["MLS", "Eastern"], zones=dict(ucl=7, uel=9, conf=0, po=None, rel=None),
                  labels=dict(ucl="Playoffs", uel="Play-in"), emblem=19),
}
ALIAS = {"Internazionale": "Inter", "Inter Milan": "Inter", "AS Roma": "Roma", "Stade Rennais": "Rennes",
         "AS Monaco": "Monaco", "AJ Auxerre": "Auxerre", "Le Havre AC": "Le Havre", "Milan": "AC Milan"}
LEAGUE_LOGO = "https://a.espncdn.com/i/leaguelogos/soccer/500/{id}.png"


def grad(c1, c2, t): return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


_BG = None
def background():
    global _BG
    if _BG is not None:
        return _BG.copy()
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        c = grad((10, 8, 64), (64, 26, 160), min(1, k / 0.30)) if k < 0.30 else grad((64, 26, 160), (16, 8, 56), min(1, (k - 0.30) / 0.5))
        d.line([(0, y), (W, y)], fill=c)
    rays = Image.new("RGB", (W, H)); rd = ImageDraw.Draw(rays)
    for lx, ly in [(70, 30), (1010, 30)]:
        for ang in range(-8, 60, 9):
            a = math.radians(80 + ang * (1 if lx < 500 else -1) * 0.9)
            rd.polygon([(lx, ly),
                        (lx + math.cos(a - 0.05) * 1000 * (1 if lx < 500 else -1), ly + abs(math.sin(a - 0.05)) * 1000),
                        (lx + math.cos(a + 0.05) * 1000 * (1 if lx < 500 else -1), ly + abs(math.sin(a + 0.05)) * 1000)], fill=(34, 26, 80))
    im = ImageChops.add(im, rays.filter(ImageFilter.GaussianBlur(10)))
    pt = Image.new("RGB", (W, H)); pd = ImageDraw.Draw(pt)
    for y in range(1190, H):
        k = (y - 1190) / (H - 1190)
        for i in range(10):
            x0 = i * W / 10 - 30; x1 = (i + 1) * W / 10 + 30
            c = (14, 100, 40) if i % 2 == 0 else (10, 75, 32)
            pd.polygon([(x0, y), (x1, y), (x1, y + 2), (x0, y + 2)], fill=tuple(int(v * k) for v in c))
    im = ImageChops.add(im, pt.filter(ImageFilter.GaussianBlur(10)))
    gl = Image.new("RGB", (W, H)); ImageDraw.Draw(gl).ellipse([-100, 1200, W + 100, 1520], fill=(110, 40, 210))
    im = ImageChops.add(im, gl.filter(ImageFilter.GaussianBlur(60)))
    _BG = im
    return im.copy()


def infinity(d, cx, cy, r, col, w):
    pts = []
    for i in range(0, 361, 3):
        t = math.radians(i); s = 1 + math.sin(t) ** 2
        pts.append((cx + r * 1.6 * math.cos(t) / s, cy + r * 1.6 * math.sin(t) * math.cos(t) / s))
    d.line(pts, fill=col, width=w, joint="curve")


def ball(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 250, 255), outline=(40, 20, 90), width=4)
    d.ellipse([cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32], fill=(30, 20, 60))


def trim(e):
    """Crop transparent / plain-white margins so a logo sits centred in its circle."""
    e = e.convert("RGBA")
    a = e.getchannel("A")
    if a.getextrema()[0] > 240:  # opaque picture: treat near-white as background
        px = e.convert("RGB").point(lambda v: 255 if v < 238 else 0).convert("L")
        bb = px.getbbox()
    else:
        bb = a.point(lambda v: 255 if v > 12 else 0).getbbox()
    return e.crop(bb) if bb else e


def put_logo(im, cx, cy, r, logo, box, outline=2):
    d = ImageDraw.Draw(im)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=(170, 120, 255), width=outline)
    if logo is None:
        return False
    e = trim(logo)
    k = min(box / e.width, box / e.height)
    e = e.resize((max(1, int(e.width * k)), max(1, int(e.height * k))), Image.LANCZOS)
    im.alpha_composite(e, (int(cx - e.width / 2), int(cy - e.height / 2)))
    return True


def initials(d, cx, cy, name, size):
    t = "".join(w[0] for w in name.replace("-", " ").split()[:2]).upper() or "?"
    d.text((cx, cy), t, font=F("ExtraBold", int(size * 0.7)), fill=(40, 20, 90), anchor="mm")


def render_standings(lg, rows, fetch=None, stats=None):
    st = STYLE[lg]; z = st["zones"]; n = len(rows)
    names = []
    for r in rows:
        nm = r.get("full") or r["team"]
        names.append(ALIAS.get(nm, nm))
    im = background().convert("RGBA"); d = ImageDraw.Draw(im)
    # league emblem
    elogo = fetch(LEAGUE_LOGO.format(id=st["emblem"]), 300) if fetch else None
    if elogo is not None:
        put_logo(im, 240, 122, 56, elogo, 84, 3)
    else:
        d.ellipse([184, 66, 296, 178], fill=(255, 255, 255), outline=(170, 120, 255), width=3); ball(d, 240, 122, 40)
    d = ImageDraw.Draw(im)
    d.line([(326, 52), (326, 196)], fill=WHITE, width=4)
    lines = st["lines"]; sz = 88
    while max(d.textlength(l, font=PF(sz)) for l in lines) > 360: sz -= 2
    if len(lines) == 1:
        d.text((350, 126), lines[0], font=PF(sz), fill=WHITE, anchor="lm")
    else:
        d.text((350, 80), lines[0], font=PF(sz), fill=WHITE, anchor="lm"); d.text((350, 80 + int(sz * 0.84)), lines[1], font=PF(sz), fill=WHITE, anchor="lm")
    infinity(d, 872, 66, 20, GOLD, 6)
    d.text((910, 52), "INFINITE", font=F("ExtraBold", 30), fill=WHITE, anchor="lm"); d.text((910, 82), "SPORT", font=F("ExtraBold", 30), fill=GOLD, anchor="lm")
    by0, by1 = 208, 292
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).polygon([(230, by0 + 8), (870, by0 + 8), (910, by1 + 8), (190, by1 + 8)], fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8))); d = ImageDraw.Draw(im)
    for y in range(by0, by1):
        k = (y - by0) / (by1 - by0); c = grad((255, 236, 90), (240, 180, 0), k)
        d.line([(230 - 40 * k, y), (850 + 40 * k, y)], fill=c)
    d.text((W // 2, (by0 + by1) // 2 + 2), "STANDINGS", font=F("ExtraBold", 86), fill=(15, 10, 25), anchor="mm")
    # table
    TX0, TX1, TY0 = 36, W - 36, 376; HH = 52; avail = 1232 - TY0 - HH - 8; RH = avail // n; TY1 = TY0 + HH + RH * n + 8
    tb = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(tb)
    td.rounded_rectangle([TX0, TY0, TX1, TY1], 18, fill=(8, 10, 30, 225), outline=(120, 90, 220, 255), width=2)
    im.alpha_composite(tb); d = ImageDraw.Draw(im)
    d.rounded_rectangle([TX0, TY0, TX1, TY0 + HH], 18, fill=(70, 30, 150)); d.rectangle([TX0, TY0 + 20, TX1, TY0 + HH], fill=(70, 30, 150))
    P0 = 962
    d.rectangle([P0, TY0, TX1 - 2, TY0 + HH], fill=(50, 20, 100))
    nsz = max(30, min(40, RH - 2)); nf = F("Bold", nsz); sf = F("Bold", nsz)
    maxw = max(d.textlength(nm, font=nf) for nm in names)
    px = int(min(560, max(470, 222 + maxw + 60))); step = (920 - px) / 4
    cols = {"pos": 85, "P": px, "W": int(px + step), "D": int(px + 2 * step), "L": int(px + 3 * step), "GD": 920, "PTS": 1003}
    NAMEMAX = px - 45 - 222
    zb = Image.new("RGBA", (W, H), (0, 0, 0, 0)); zd = ImageDraw.Draw(zb)
    for i in range(1, n, 2):
        yy = TY0 + HH + 4 + i * RH; zd.rectangle([TX0 + 4, yy + 1, P0 - 3, yy + RH - 1], fill=(160, 150, 255, 16))
    im.alpha_composite(zb); d = ImageDraw.Draw(im)
    hf = F("ExtraBold", 34)
    for k, lbl in [("pos", "#"), ("P", "P"), ("W", "W"), ("D", "D"), ("L", "L"), ("GD", "GD"), ("PTS", "PTS")]:
        d.text((cols[k], TY0 + HH // 2), lbl, font=hf, fill=GOLD if k == "PTS" else WHITE, anchor="mm")
    d.text((222, TY0 + HH // 2), "TEAM", font=hf, fill=WHITE, anchor="lm")

    def zc(p):
        if p <= z["ucl"]: return ((60, 220, 60), (0, 130, 20))
        if p <= z["uel"]: return ((60, 160, 255), (0, 80, 200))
        if p <= z.get("conf", 0): return ((175, 115, 255), (105, 45, 205))
        if z["rel"] and p >= z["rel"]: return ((255, 70, 70), (170, 0, 10))
        if z["po"] and p == z["po"]: return ((255, 170, 40), (200, 100, 0))
        return ((190, 195, 225), (110, 115, 150))

    got = 0
    lr = min(24, round(RH * 0.52))
    for i, r in enumerate(rows):
        name = names[i]; Pp, Wn, Dn, Ln, GD, PT = r["mp"], r["w"], r["d"], r["l"], r["gd"], r["pts"]
        pos = i + 1; y = TY0 + HH + 4 + i * RH; cy = y + RH // 2
        bad = (z["rel"] and pos >= z["rel"]) or (z["po"] and pos == z["po"])
        if bad:
            tint = Image.new("RGBA", (W, H), (0, 0, 0, 0)); tdd = ImageDraw.Draw(tint)
            for x in range(TX0 + 4, P0):
                a = int(120 * (1 - (x - TX0) / (P0 - TX0))); tdd.line([(x, y + 1), (x, y + RH - 2)], fill=(200, 20, 40, a) if pos >= (z["rel"] or 99) else (220, 120, 0, a))
            im.alpha_composite(tint); d = ImageDraw.Draw(im)
        if i: d.line([(TX0 + 8, y), (P0 - 4, y)], fill=(60, 55, 110), width=1)
        top, bot = zc(pos)
        for yy in range(y + 3, y + RH - 3):
            k = (yy - y) / RH; d.line([(46, yy), (126, yy)], fill=grad(top, bot, k))
        d.rounded_rectangle([46, y + 3, 126, y + RH - 4], 8, outline=(255, 255, 255), width=1)
        d.text((86, cy), str(pos), font=F("ExtraBold", min(40, RH - 6)), fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        logo = fetch(r.get("logo"), 200) if (fetch and r.get("logo")) else None
        if put_logo(im, 178, cy, lr, logo, lr * 1.6):
            got += 1
        else:
            initials(d, 178, cy, name, lr * 1.6)
        d = ImageDraw.Draw(im)
        fsz = nf.size
        while d.textlength(name, font=F("Bold", fsz)) > NAMEMAX and fsz > 14: fsz -= 1
        d.text((222, cy), name, font=F("Bold", fsz), fill=WHITE, anchor="lm")
        for k, v in [("P", Pp), ("W", Wn), ("D", Dn), ("L", Ln)]: d.text((cols[k], cy), str(v), font=sf, fill=WHITE, anchor="mm")
        d.text((cols["GD"], cy), f"{GD:+d}" if GD else "0", font=sf, fill=(60, 230, 60) if GD > 0 else ((255, 60, 60) if GD < 0 else WHITE), anchor="mm")
        for yy in range(y + 3, y + RH - 3):
            k = (yy - y) / RH; d.line([(970, yy), (1036, yy)], fill=grad((255, 236, 60), (240, 190, 0), k))
        d.rounded_rectangle([970, y + 3, 1036, y + RH - 4], 8, outline=(255, 250, 200), width=1)
        d.text((1003, cy), str(PT), font=F("ExtraBold", min(40, RH - 4)), fill=(15, 10, 25), anchor="mm")
    if stats is not None:
        stats["logos"] = got; stats["rows"] = n
    # legend
    lb = st.get("labels", {}); items = []
    if z["ucl"] > 0: items.append(((60, 220, 60), lb.get("ucl", "Champions League")))
    if z["uel"] > z["ucl"]: items.append(((60, 160, 255), lb.get("uel", "Europa League")))
    if z.get("conf", 0) > z["uel"]: items.append(((175, 115, 255), "Conference League"))
    if z["po"]: items.append(((255, 170, 40), "Relegation play-off"))
    if z["rel"]: items.append(((255, 70, 70), "Relegation"))
    lsz = 30 if len(items) < 4 else 26; gap = 40 if len(items) < 4 else 26
    while True:
        lf = F("Bold", lsz); widths = [48 + d.textlength(t, font=lf) for _, t in items]
        tot = sum(widths) + gap * (len(items) - 1) + 60
        if tot <= W - 70 or lsz <= 18: break
        lsz -= 1; gap = max(14, gap - 2)
    lx0 = (W - tot) // 2; ly0 = TY1 + 12; ly1 = ly0 + 50
    d.rounded_rectangle([lx0, ly0, lx0 + tot, ly1], 25, fill=(20, 15, 50), outline=(110, 80, 200), width=2)
    x = lx0 + 30
    for (c, t), wd in zip(items, widths):
        d.ellipse([x, ly0 + 11, x + 28, ly0 + 39], fill=c); d.text((x + 40, (ly0 + ly1) // 2), t, font=lf, fill=WHITE, anchor="lm"); x += wd + gap
    fy = H - 30
    ft = "FOLLOW INFINITE SPORT FOR MORE UPDATES"; ff = F("BoldItalic", 38)
    tw = d.textlength(ft, font=ff) + 40
    d.text((W // 2, fy), ft, font=ff, fill=WHITE, anchor="mm")
    d.line([(30, fy), (W // 2 - tw / 2 - 10, fy)], fill=GOLD, width=4); d.line([(W // 2 + tw / 2 + 10, fy), (W - 30, fy)], fill=GOLD, width=4)
    return im.convert("RGB")
