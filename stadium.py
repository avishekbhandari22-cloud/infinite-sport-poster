"""Draws the STANDINGS picture (stadium template) from live table rows.

render_standings(lg, rows, fetch) -> PIL RGB image 1080x1350.
rows: list of dicts with team/full, logo (url), mp, w, d, l, gd, pts (already sorted).
fetch(url, size) -> RGBA logo image or None (supplied by standings_post.py).
Nothing here is pre-made: the picture is drawn at post time, so it always matches the live table.

Layout (Nov 2026): compact one-line header (emblem far left, league name on one line),
STANDINGS ribbon right under it, table fills everything down to a 40 px bottom strip
(small legend left, follow line right). Row height grows when a league has fewer teams.
"""
import math, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
FD = os.path.join(HERE, "fonts") + os.sep
W, H = 1080, 1350
GOLD = (255, 214, 0); WHITE = (255, 255, 255)
STRIP = 40  # bottom strip height


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
    # ---- header: emblem far left, league name on ONE line, brand mark right
    ecx, ecy, er = 86, 62, 46
    elogo = fetch(LEAGUE_LOGO.format(id=st["emblem"]), 300) if fetch else None
    if elogo is not None:
        put_logo(im, ecx, ecy, er, elogo, 70, 3)
    else:
        d.ellipse([ecx - er, ecy - er, ecx + er, ecy + er], fill=(255, 255, 255), outline=(170, 120, 255), width=3); ball(d, ecx, ecy, 32)
    d = ImageDraw.Draw(im)
    d.line([(150, 22), (150, 102)], fill=WHITE, width=4)
    title = " ".join(st["lines"]); sz = 66
    while d.textlength(title, font=PF(sz)) > 660 and sz > 30: sz -= 2
    d.text((172, 66), title, font=PF(sz), fill=WHITE, anchor="lm")
    infinity(d, 872, 60, 20, GOLD, 6)
    d.text((910, 46), "INFINITE", font=F("ExtraBold", 30), fill=WHITE, anchor="lm"); d.text((910, 76), "SPORT", font=F("ExtraBold", 30), fill=GOLD, anchor="lm")
    # ---- STANDINGS ribbon directly under the title
    by0, by1 = 116, 168
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sh).polygon([(230, by0 + 6), (850, by0 + 6), (885, by1 + 6), (195, by1 + 6)], fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6))); d = ImageDraw.Draw(im)
    for y in range(by0, by1):
        k = (y - by0) / (by1 - by0); c = grad((255, 236, 90), (240, 180, 0), k)
        d.line([(230 - 35 * k, y), (850 + 35 * k, y)], fill=c)
    d.text((W // 2, (by0 + by1) // 2 + 2), "STANDINGS", font=F("ExtraBold", 54), fill=(15, 10, 25), anchor="mm")
    # ---- table: fills everything down to the bottom strip
    TX0, TX1, TY0 = 30, W - 30, 178; HH = 46
    avail = (H - STRIP - 6) - TY0 - HH - 8; RH = avail // n; TY1 = TY0 + HH + RH * n + 8
    tb = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(tb)
    td.rounded_rectangle([TX0, TY0, TX1, TY1], 18, fill=(8, 10, 30, 225), outline=(120, 90, 220, 255), width=2)
    im.alpha_composite(tb); d = ImageDraw.Draw(im)
    d.rounded_rectangle([TX0, TY0, TX1, TY0 + HH], 18, fill=(70, 30, 150)); d.rectangle([TX0, TY0 + 20, TX1, TY0 + HH], fill=(70, 30, 150))
    P0 = 962
    d.rectangle([P0, TY0, TX1 - 2, TY0 + HH], fill=(50, 20, 100))
    nsz = max(30, min(50, int(RH * 0.80))); nf = F("Bold", nsz); sf = F("Bold", nsz)
    maxw = max(d.textlength(nm, font=nf) for nm in names)
    px = int(min(640, max(480, 232 + maxw + 50))); step = (920 - px) / 4
    cols = {"pos": 82, "P": px, "W": int(px + step), "D": int(px + 2 * step), "L": int(px + 3 * step), "GD": 920, "PTS": 1003}
    NAMEMAX = px - 40 - 232
    zb = Image.new("RGBA", (W, H), (0, 0, 0, 0)); zd = ImageDraw.Draw(zb)
    for i in range(1, n, 2):
        yy = TY0 + HH + 4 + i * RH; zd.rectangle([TX0 + 4, yy + 1, P0 - 3, yy + RH - 1], fill=(160, 150, 255, 16))
    im.alpha_composite(zb); d = ImageDraw.Draw(im)
    hf = F("ExtraBold", 34)
    for k, lbl in [("pos", "#"), ("P", "P"), ("W", "W"), ("D", "D"), ("L", "L"), ("GD", "GD"), ("PTS", "PTS")]:
        d.text((cols[k], TY0 + HH // 2), lbl, font=hf, fill=GOLD if k == "PTS" else WHITE, anchor="mm")
    d.text((232, TY0 + HH // 2), "TEAM", font=hf, fill=WHITE, anchor="lm")

    def zc(p):
        if p <= z["ucl"]: return ((60, 220, 60), (0, 130, 20))
        if p <= z["uel"]: return ((60, 160, 255), (0, 80, 200))
        if p <= z.get("conf", 0): return ((175, 115, 255), (105, 45, 205))
        if z["rel"] and p >= z["rel"]: return ((255, 70, 70), (170, 0, 10))
        if z["po"] and p == z["po"]: return ((255, 170, 40), (200, 100, 0))
        return ((190, 195, 225), (110, 115, 150))

    got = 0
    lr = min(32, round(RH * 0.46))
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
        for yy in range(y + 4, y + RH - 4):
            k = (yy - y) / RH; d.line([(42, yy), (122, yy)], fill=grad(top, bot, k))
        d.rounded_rectangle([42, y + 4, 122, y + RH - 5], 8, outline=(255, 255, 255), width=1)
        d.text((82, cy), str(pos), font=F("ExtraBold", min(48, RH - 10)), fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        logo = fetch(r.get("logo"), 200) if (fetch and r.get("logo")) else None
        if put_logo(im, 180, cy, lr, logo, lr * 1.6):
            got += 1
        else:
            initials(d, 180, cy, name, lr * 1.6)
        d = ImageDraw.Draw(im)
        fsz = nf.size
        while d.textlength(name, font=F("Bold", fsz)) > NAMEMAX and fsz > 14: fsz -= 1
        d.text((232, cy), name, font=F("Bold", fsz), fill=WHITE, anchor="lm")
        for k, v in [("P", Pp), ("W", Wn), ("D", Dn), ("L", Ln)]: d.text((cols[k], cy), str(v), font=sf, fill=WHITE, anchor="mm")
        d.text((cols["GD"], cy), f"{GD:+d}" if GD else "0", font=sf, fill=(60, 230, 60) if GD > 0 else ((255, 60, 60) if GD < 0 else WHITE), anchor="mm")
        for yy in range(y + 4, y + RH - 4):
            k = (yy - y) / RH; d.line([(970, yy), (1038, yy)], fill=grad((255, 236, 60), (240, 190, 0), k))
        d.rounded_rectangle([970, y + 4, 1038, y + RH - 5], 8, outline=(255, 250, 200), width=1)
        d.text((1004, cy), str(PT), font=F("ExtraBold", min(48, RH - 8)), fill=(15, 10, 25), anchor="mm")
    if stats is not None:
        stats["logos"] = got; stats["rows"] = n
    # ---- bottom strip (40 px): small legend left, follow line right
    lb = st.get("labels", {}); items = []
    if z["ucl"] > 0: items.append(((60, 220, 60), lb.get("ucl", "Champions League")))
    if z["uel"] > z["ucl"]: items.append(((60, 160, 255), lb.get("uel", "Europa League")))
    if z.get("conf", 0) > z["uel"]: items.append(((175, 115, 255), "Conference League"))
    if z["po"]: items.append(((255, 170, 40), "Relegation play-off"))
    if z["rel"]: items.append(((255, 70, 70), "Relegation"))
    fy0 = H - STRIP; fcy = fy0 + STRIP // 2
    d.rectangle([0, fy0, W, H], fill=(90, 30, 200))
    ft = "FOLLOW INFINITE SPORT FOR MORE UPDATES"
    lsz = 22
    while True:
        lf = F("Bold", lsz)
        tot = sum(22 + d.textlength(t, font=lf) for _, t in items) + 16 * max(0, len(items) - 1)
        if tot + d.textlength(ft, font=lf) + 80 <= W or lsz <= 15: break
        lsz -= 1
    x = 28
    for c, t in items:
        d.ellipse([x, fcy - 7, x + 14, fcy + 7], fill=c); d.text((x + 20, fcy), t, font=lf, fill=WHITE, anchor="lm")
        x += 22 + d.textlength(t, font=lf) + 16
    d.text((W - 28, fcy), ft, font=lf, fill=WHITE, anchor="rm")
    return im.convert("RGB")
