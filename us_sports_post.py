#!/usr/bin/env python3
"""NBA / NFL standings poster for a Facebook Page ("NBA & NFL Updates").

Usage:
  python us_sports_post.py --sport nba --post-at-et 08:00 [--dry-run]
  python us_sports_post.py --sport nfl --post-at-et 08:00 [--dry-run]

NBA regular season: two posts (Eastern, Western), each a top-10 image + caption,
  full 15-team table added as the first comment.
NBA playoffs: two posts (East, West) showing every series with its status.
NFL regular season: two posts (AFC, NFC), top 10 + playoff line after seed 7,
  full 16-team table as first comment. Posts on Tuesdays (ET) unless --force.
--post-at-et is US Eastern wall-clock time (DST handled). Everything is built
first, then the script waits until that time. Env (not --dry-run):
  FB_PAGE_ID_NBA, FB_PAGE_TOKEN_NBA
"""
import argparse, datetime as dt, io, json, os, re, sys, time, urllib.request, urllib.parse, uuid
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

ET = ZoneInfo("America/New_York")
GRAPH = "https://graph.facebook.com/v21.0"
SB = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d}"
ST = "https://site.api.espn.com/apis/v2/sports/{path}/standings?season={y}&seasontype=2"
SPORTS = {
    "nba": dict(path="basketball/nba", name="NBA", accent=(200, 16, 46), logo="nba", conf=("Eastern", "Western"), top=10),
    "nfl": dict(path="football/nfl", name="NFL", accent=(1, 51, 105), logo="nfl", conf=("AFC", "NFC"), top=10),
}
TAGS = {
    "nba": "#NBA #Basketball #NBAStandings #NBATwitter #{conf}Conference",
    "nfl": "#NFL #Football #NFLStandings #NFLTwitter #{conf}",
}
FOOT = "\U0001F447"


# ----------------------------------------------------------------- data
def http_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def stat(entry, name, default=0, display=False):
    for s in entry.get("stats", []):
        if s.get("name") == name or s.get("type") == name:
            if display:
                return s.get("displayValue", default)
            v = s.get("value")
            return default if v is None else v
    return default


def parse_standings(js):
    groups = []
    for ch in js.get("children", []):
        rows = []
        for e in ch.get("standings", {}).get("entries", []):
            t = e["team"]
            logos = t.get("logos") or []
            w, l, tie = int(stat(e, "wins")), int(stat(e, "losses")), int(stat(e, "ties"))
            gp = w + l + tie
            pct = stat(e, "winPercent", None)
            if pct is None:
                pct = (w + 0.5 * tie) / gp if gp else 0.0
            rows.append(dict(
                tid=str(t.get("id", "")), abbr=t.get("abbreviation", ""),
                team=t.get("shortDisplayName") or t.get("displayName") or t.get("name"),
                logo=(logos[0].get("href") if logos else None),
                w=w, l=l, t=tie, gp=gp, pct=float(pct),
                gb=stat(e, "gamesBehind", "-", display=True), strk=stat(e, "streak", "", display=True),
                pf=int(stat(e, "pointsFor")), pa=int(stat(e, "pointsAgainst")),
                diff=stat(e, "differential", "", display=True) or stat(e, "pointDifferential", "", display=True),
                seed=int(stat(e, "playoffSeed", 0)), l10=stat(e, "record", "", display=True)))
        rows.sort(key=lambda r: (r["seed"] if r["seed"] else 99, -r["pct"], -(r["pf"] - r["pa"])))
        if not any(r["seed"] for r in rows):
            rows.sort(key=lambda r: (-r["pct"], -(r["pf"] - r["pa"])))
        for i, r in enumerate(rows, 1):
            r["pos"] = i
        groups.append(dict(name=ch.get("name", ""), rows=rows))
    return groups


def pick_group(groups, key):
    alias = {"afc": "american", "nfc": "national"}.get(key.lower(), key.lower())
    for g in groups:
        n = g["name"].lower()
        if key.lower() in n or alias in n:
            return g
    return None


def season_info(sport, now):
    """-> (year, type, week) from the scoreboard; None if unavailable."""
    js = http_json(SB.format(path=SPORTS[sport]["path"], d=now.astimezone(ET).strftime("%Y%m%d")), tries=2)
    s = js.get("season", {}) or {}
    wk = (js.get("week") or {}).get("number")
    return s.get("year"), s.get("type"), wk, js


def recent_games(sport, now, hours=30):
    out, seen = [], set()
    for back in (0, 1, 2):
        d = (now.astimezone(ET) - dt.timedelta(days=back)).strftime("%Y%m%d")
        try:
            js = http_json(SB.format(path=SPORTS[sport]["path"], d=d), tries=2)
        except Exception:
            continue
        for ev in js.get("events", []):
            if ev["id"] in seen:
                continue
            comp = ev["competitions"][0]
            if not comp["status"]["type"].get("completed"):
                continue
            when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            if now - when > dt.timedelta(hours=hours):
                continue
            seen.add(ev["id"])
            h = next(c for c in comp["competitors"] if c["homeAway"] == "home")
            a = next(c for c in comp["competitors"] if c["homeAway"] == "away")

            def star(c):
                best = None
                for l in c.get("leaders", []) or []:
                    if l.get("name") in ("points", "passingYards", "rushingYards", "receivingYards") and l.get("leaders"):
                        x = l["leaders"][0]
                        best = (x.get("athlete", {}).get("displayName", ""), x.get("displayValue", ""), l.get("name"))
                        break
                return best
            ser = comp.get("series") or {}
            out.append(dict(ev=ev["id"], home=h["team"]["shortDisplayName"], away=a["team"]["shortDisplayName"],
                            hid=str(h["team"]["id"]), aid=str(a["team"]["id"]),
                            hs=int(float(h.get("score") or 0)), as_=int(float(a.get("score") or 0)),
                            hstar=star(h), astar=star(a), series=ser.get("summary", ""),
                            headline=(comp.get("notes") or [{}])[0].get("headline", "")))
    return out


# ----------------------------------------------------------------- captions
def last_name(n):
    p = (n or "").split()
    return p[-1] if p else "?"


def star_txt(m, win_side=None):
    s = m["hstar"] if win_side == "h" else m["astar"] if win_side == "a" else (m["hstar"] or m["astar"])
    if not s or not s[0]:
        return ""
    unit = {"points": "points", "passingYards": "passing yards", "rushingYards": "rushing yards", "receivingYards": "receiving yards"}.get(s[2], "")
    return f"{s[0]} led the way with {s[1]} {unit}.".replace("  ", " ")


def feature(rows, games):
    pos = {r["tid"]: r["pos"] for r in rows}
    def sc(m):
        return sum(6 if pos.get(t, 99) == 1 else 4 if pos.get(t, 99) <= 3 else 2 if pos.get(t, 99) <= 6 else 0 for t in (m["hid"], m["aid"])) + abs(m["hs"] - m["as_"]) * 0.2
    return max(games, key=sc)


def game_line(m):
    h, a, hs, as_ = m["home"], m["away"], m["hs"], m["as_"]
    w, l, ws, ls, side = (h, a, hs, as_, "h") if hs > as_ else (a, h, as_, hs, "a")
    d = ws - ls
    verb = "rolled past" if d >= 20 else "beat" if d >= 6 else "edged"
    return f"{w} {verb} {l} {ws}-{ls}. {star_txt(m, side)}".strip(), side


def games_lines(rows, games, n=3):
    """Top results of the day (games involving the best-placed teams first): winner, loser, score, and each side's top performer."""
    pos = {r["tid"]: r["pos"] for r in rows}
    def sc(m):
        return sum(6 if pos.get(t, 99) == 1 else 4 if pos.get(t, 99) <= 3 else 2 if pos.get(t, 99) <= 6 else 0 for t in (m["hid"], m["aid"])) + abs(m["hs"] - m["as_"]) * 0.2
    out = []
    for m in sorted(games, key=lambda x: -sc(x))[:n]:
        line, side = game_line(m)
        lose = star_txt(m, "a" if side == "h" else "h")
        if lose:
            line += " " + lose.replace("led the way with", "had")
        out.append("\u25AA " + line)
    return out


def caption_regular(sport, conf, grp, games, week=None):
    meta = SPORTS[sport]
    rows = grp["rows"]
    if not rows or rows[0]["gp"] == 0:
        return None
    top, sec = rows[0], rows[1]
    name = f"{conf} Conference" if sport == "nba" else conf
    today = dt.datetime.now(ET).strftime("%B %d")
    rec = lambda r: f"{r['w']}-{r['l']}" + (f"-{r['t']}" if r["t"] else "")
    if sport == "nba":
        head = f"\U0001F3C0 NBA {name} standings — {today}"
        gl = games_lines(rows, games)
        lead = f"{top['team']} lead the {conf} at {rec(top)}" + (f", {sec['gb']} {'game' if str(sec['gb']) == '1' else 'games'} clear of {sec['team']}." if str(sec["gb"]) not in ("-", "0", "") else f", level with {sec['team']}.")
        cut = rows[5] if len(rows) > 5 else None
        po = rows[9] if len(rows) > 9 else None
        extra = f"Top 6 qualify directly for the playoffs; seeds 7-10 go to the Play-In Tournament. {rows[5]['team']} hold the last automatic spot ({rec(rows[5])}), {rows[9]['team']} sit 10th ({rec(rows[9])})." if cut and po else ""
        lines = [head, *gl, lead, extra, f"Who's your {conf} champion pick? Tell us below. \U0001F4AC", f"Full 15-team table in the comments. {FOOT}"]
    else:
        head = f"\U0001F3C8 NFL {name} standings — Week {week}" if week else f"\U0001F3C8 NFL {name} standings"
        gl = games_lines(rows, games)
        lead = f"{top['team']} hold the No. 1 seed at {rec(top)}, ahead of {sec['team']} ({rec(sec)})."
        extra = f"The top 7 in each conference make the playoffs, and only No. 1 gets a first-round bye. {rows[6]['team']} currently hold the final spot ({rec(rows[6])})." if len(rows) > 6 else ""
        lines = [head, *gl, lead, extra, f"Is your team in the {conf} playoff picture? Tell us below. \U0001F4AC", f"Full table in the comments. {FOOT}"]
    lines.append(TAGS[sport].format(conf=conf))
    return "\n\n".join(l for l in lines if l)


def series_pairs(sport, now, groups):
    """Playoff mode: latest state of each series from recent scoreboard (fields guarded)."""
    seen, out = {}, []
    team_conf = {r["tid"]: g["name"] for g in groups for r in g["rows"]}
    for back in range(0, 3):
        d = (now.astimezone(ET) - dt.timedelta(days=back)).strftime("%Y%m%d")
        try:
            js = http_json(SB.format(path=SPORTS[sport]["path"], d=d), tries=2)
        except Exception:
            continue
        for ev in js.get("events", []):
            comp = ev["competitions"][0]
            ser = comp.get("series") or {}
            if ser.get("type") != "playoff":
                continue
            ts = [c["team"] for c in comp["competitors"]]
            key = tuple(sorted(str(t["id"]) for t in ts))
            if key in seen:
                continue
            wins = {str(c["id"]): c.get("wins", 0) for c in ser.get("competitors", [])}
            conf = team_conf.get(str(ts[0]["id"]), "")
            head = (comp.get("notes") or [{}])[0].get("headline", "") or ser.get("title", "")
            seen[key] = 1
            out.append(dict(conf=conf, round=head, summary=ser.get("summary", ""),
                            teams=[(t["shortDisplayName"], t.get("logo", ""), wins.get(str(t["id"]), 0)) for t in ts]))
    return out


def caption_playoffs(conf, pairs):
    today = dt.datetime.now(ET).strftime("%B %d")
    lines = [f"\U0001F3C6 NBA Playoffs — {conf} Conference series update ({today})"]
    for p in pairs[:8]:
        lines.append(f"• {p['summary'] or ' vs '.join(t[0] for t in p['teams'])}")
    lines += ["Which series are you watching tonight? \U0001F4AC", f"Full series scoreboard in the picture above. {FOOT}", TAGS["nba"].format(conf=conf) + " #NBAPlayoffs"]
    return "\n\n".join(lines[:1] + ["\n".join(lines[1:-3])] + lines[-3:])


# ----------------------------------------------------------------- image
def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
    for base in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/", ""):
        for n in names:
            try:
                return ImageFont.truetype(base + n, size)
            except OSError:
                pass
    return ImageFont.load_default()


_LOGO = {}


def fetch_logo(url, size):
    if not url:
        return None
    if url not in _LOGO:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                _LOGO[url] = Image.open(io.BytesIO(r.read())).convert("RGBA")
        except Exception:
            _LOGO[url] = None
    s = _LOGO[url]
    if s is None:
        return None
    im = s.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def initials_logo(name, size, color):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=color)
    t = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    f = font(int(size * 0.42), True)
    d.text(((size - d.textlength(t, font=f)) / 2, size * 0.26), t, font=f, fill="white")
    return im


def team_logo(url, name, size, i):
    pal = [(66, 99, 160), (160, 66, 66), (66, 140, 99), (140, 99, 160), (180, 130, 50)]
    return fetch_logo(url, size) or initials_logo(name, size, pal[i % len(pal)])


def render_table(sport, conf, rows, n=None, use_logos=True, week=None):
    meta = SPORTS[sport]
    rows = rows[:n] if n else rows
    if sport == "nba":
        cols = [("W", 590), ("L", 665), ("PCT", 780), ("GB", 880), ("STRK", 1040)]
        title = f"{conf} Conference"
        cut_after = {6: (46, 160, 90), 10: (240, 140, 20)}
    else:
        cols = [("W", 560), ("L", 625), ("T", 685), ("PCT", 790), ("PF", 880), ("PA", 960), ("STRK", 1050)]
        title = f"{conf}"
        cut_after = {7: (46, 160, 90)}
    W, PAD, HEAD, TABH, ROWH = 1080, 36, 150, 70, 72
    H = HEAD + TABH + ROWH * len(rows) + 100
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, HEAD), fill=meta["accent"])
    d.text((PAD, 30), f"{meta['name']} {title}", font=font(52, True), fill="white")
    sub = "Standings" + (f" · Week {week}" if week else "") + " · " + dt.datetime.now(ET).strftime("%b %d, %Y")
    d.text((PAD, 100), sub, font=font(28), fill=(235, 235, 240))
    y0 = HEAD + 14
    d.text((PAD, y0 + 18), "Team", font=font(26), fill=(110, 110, 120))
    for lab, x in cols:
        d.text((x - d.textlength(lab, font=font(26)), y0 + 18), lab, font=font(26, lab == "PCT"), fill=(110, 110, 120))
    y = HEAD + TABH
    for i, r in enumerate(rows):
        if i % 2 == 0:
            d.rectangle((0, y, W, y + ROWH), fill=(246, 247, 250))
        zc = next((c for p, c in sorted(cut_after.items()) if r["pos"] <= p), None)
        if zc:
            d.rectangle((0, y + 8, 7, y + ROWH - 8), fill=zc)
        d.text((PAD, y + 20), str(r["pos"]), font=font(30), fill=(60, 60, 70))
        lg = team_logo(r["logo"], r["team"], 54, i) if use_logos else initials_logo(r["team"], 54, (66, 99, 160))
        img.paste(lg, (PAD + 52, y + (ROWH - lg.height) // 2), lg)
        nm, f = r["team"], font(32)
        while d.textlength(nm, font=f) > 330 and len(nm) > 3:
            nm = nm[:-2].rstrip() + "."
        d.text((PAD + 112, y + 18), nm, font=f, fill=(15, 15, 25))
        vals = {"W": r["w"], "L": r["l"], "T": r["t"], "PCT": f"{r['pct']:.3f}".lstrip("0") if r["pct"] < 1 else "1.000",
                "GB": r["gb"], "PF": r["pf"], "PA": r["pa"], "STRK": r["strk"]}
        for lab, x in cols:
            t = str(vals[lab])
            fn = font(31, lab in ("W", "PCT"))
            d.text((x - d.textlength(t, font=fn), y + 19), t, font=fn, fill=(15, 15, 25) if lab in ("W", "PCT") else (60, 60, 70))
        y += ROWH
    d.line((0, y, W, y), fill=(220, 222, 230), width=2)
    x = PAD
    keys = ([("Playoffs", (46, 160, 90)), ("Play-In", (240, 140, 20))] if sport == "nba" else [("Playoff spot (top 7)", (46, 160, 90))])
    for txt, c in keys:
        d.rectangle((x, y + 36, x + 8, y + 60), fill=c)
        d.text((x + 18, y + 34), txt, font=font(24), fill=(90, 90, 100))
        x += 40 + int(d.textlength(txt, font=font(24))) + 30
    t = "Data: ESPN"
    d.text((W - PAD - d.textlength(t, font=font(24)), y + 34), t, font=font(24), fill=(90, 90, 100))
    return img


def render_series(conf, pairs):
    W, PAD, HEAD, ROWH = 1080, 36, 150, 120
    H = HEAD + ROWH * max(len(pairs), 1) + 80
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, HEAD), fill=SPORTS["nba"]["accent"])
    d.text((PAD, 30), f"NBA Playoffs · {conf}", font=font(50, True), fill="white")
    d.text((PAD, 100), "Series status · " + dt.datetime.now(ET).strftime("%b %d, %Y"), font=font(28), fill=(235, 235, 240))
    y = HEAD
    for i, p in enumerate(pairs):
        if i % 2 == 0:
            d.rectangle((0, y, W, y + ROWH), fill=(246, 247, 250))
        (a, al, aw), (b, bl, bw) = (p["teams"] + [("?", "", 0)] * 2)[:2]
        for k, (nm, lo, w) in enumerate(((a, al, aw), (b, bl, bw))):
            ox = PAD if k == 0 else W // 2 + 40
            lg = team_logo(lo, nm, 60, i + k)
            img.paste(lg, (ox, y + 12), lg)
            d.text((ox + 72, y + 14), nm, font=font(30, w >= bw and k == 0 or w >= aw and k == 1), fill=(15, 15, 25))
            d.text((ox + 72, y + 56), f"{w} win{'s' if w != 1 else ''}", font=font(24), fill=(90, 90, 100))
        d.text((W // 2 - 16, y + 34), "vs", font=font(26), fill=(120, 120, 130))
        y += ROWH
    return img


# ----------------------------------------------------------------- facebook
def multipart(fields, files):
    b = uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, data, ct) in files.items():
        body.write(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{b}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={b}"


def fb_post_photo(page, token, png, message):
    body, ct = multipart({"message": message, "access_token": token, "published": "true"}, {"source": ("table.png", png, "image/png")})
    with urllib.request.urlopen(urllib.request.Request(f"{GRAPH}/{page}/photos", data=body, headers={"Content-Type": ct}), timeout=90) as r:
        return json.load(r)


def fb_comment_photo(post_id, token, png, message):
    body, ct = multipart({"message": message, "access_token": token}, {"source": ("full_table.png", png, "image/png")})
    with urllib.request.urlopen(urllib.request.Request(f"{GRAPH}/{post_id}/comments", data=body, headers={"Content-Type": ct}), timeout=90) as r:
        return json.load(r)


def fb_like(post_id, token):
    body = urllib.parse.urlencode({"access_token": token}).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{GRAPH}/{post_id}/likes", data=body), timeout=60) as r:
        return json.load(r)


def to_png(img):
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


# ----------------------------------------------------------------- main
def build(sport, now, force=False):
    year, stype, week, _ = season_info(sport, now)
    if not year:
        print("no season info; skipping")
        return []
    if sport == "nfl" and not force and now.astimezone(ET).weekday() != 1:
        print("NFL posts on Tuesdays (ET); use --force to override")
        return []
    if stype not in (2, 3):
        print(f"season type {stype} (off-season/preseason); nothing to post")
        return []
    games = recent_games(sport, now, hours=30 if sport == "nba" else 48 + 24)
    st_js = http_json(ST.format(path=SPORTS[sport]["path"], y=year))
    groups = parse_standings(st_js)
    posts = []
    for conf in SPORTS[sport]["conf"]:
        g = pick_group(groups, conf)
        if not g:
            continue
        if stype == 3:
            if sport != "nba":
                continue
            pairs = [p for p in series_pairs(sport, now, groups) if conf.lower() in (p["conf"] or "").lower()]
            if not pairs:
                continue
            posts.append(dict(tag=f"{sport}_{conf}_po", caption=caption_playoffs(conf, pairs), main=render_series(conf, pairs), fulls=[]))
            continue
        if sport == "nfl" and week and g["rows"] and max(r["gp"] for r in g["rows"]) < int(week) - 3:
            print(f"[nfl {conf}] ESPN standings look stale (max games played {max(r['gp'] for r in g['rows'])} in week {week}); skipping")
            continue
        ids = {r["tid"] for r in g["rows"]}
        cg = [m for m in games if m["hid"] in ids or m["aid"] in ids]
        if not cg:
            print(f"[{sport} {conf}] no recent games; skipping")
            continue
        cap = caption_regular(sport, conf, g, cg, week)
        if not cap:
            print(f"[{sport} {conf}] no standings data yet; skipping")
            continue
        posts.append(dict(tag=f"{sport}_{conf}", caption=cap,
                          main=render_table(sport, conf, g["rows"], n=SPORTS[sport]["top"], week=week if sport == "nfl" else None),
                          fulls=[render_table(sport, conf, g["rows"], week=week if sport == "nfl" else None)]))
    return posts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=SPORTS)
    ap.add_argument("--post-at-et", help="US Eastern HH:MM to publish at (e.g. 08:00)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore NFL Tuesday rule")
    ap.add_argument("--only", help="e.g. Eastern or AFC (testing)")
    ap.add_argument("--out", default="out_us")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    os.makedirs(a.out, exist_ok=True)
    posts = [p for p in build(a.sport, now, a.force) if not a.only or a.only.lower() in p["tag"].lower()]
    for p in posts:
        p["main"].save(f"{a.out}/{p['tag']}_main.png")
        for i, im in enumerate(p["fulls"]):
            im.save(f"{a.out}/{p['tag']}_full{i}.png")
        open(f"{a.out}/{p['tag']}_caption.txt", "w").write(p["caption"])
        print(f"[{p['tag']}] built:\n{p['caption']}\n")
    if a.dry_run or not posts:
        return
    if a.post_at_et:
        hh, mm = map(int, a.post_at_et.split(":"))
        target = now.astimezone(ET).replace(hour=hh, minute=mm, second=0, microsecond=0)
        wait = (target - dt.datetime.now(ET)).total_seconds()
        if 0 < wait < 3 * 3600:
            print(f"waiting {wait:.0f}s until {target.isoformat()}")
            time.sleep(wait)
    page, token = os.environ["FB_PAGE_ID_NBA"], os.environ["FB_PAGE_TOKEN_NBA"]
    for p in posts:
        try:
            res = fb_post_photo(page, token, to_png(p["main"]), p["caption"])
            pid = res.get("post_id") or res.get("id")
            print(f"[{p['tag']}] posted {pid}")
            try:
                fb_like(pid, token)
            except Exception as e:
                print(f"[{p['tag']}] like failed: {e}", file=sys.stderr)
            for im in p["fulls"]:
                fb_comment_photo(pid, token, to_png(im), "Full table " + FOOT)
        except Exception as e:
            print(f"[{p['tag']}] ERROR posting: {e}", file=sys.stderr)
        time.sleep(20)


if __name__ == "__main__":
    main()
