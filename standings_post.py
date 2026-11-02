#!/usr/bin/env python3
"""Daily football standings poster for a Facebook Page.

Usage:
  python standings_post.py --group europe_saudi --post-at 21:45 [--dry-run]
  python standings_post.py --group mls          --post-at 04:15 [--dry-run]

--post-at is a UTC time (HH:MM). The script builds everything first, then waits
until that time and posts. If that time has already passed it posts immediately.
Environment (only when not --dry-run): FB_PAGE_ID, FB_PAGE_TOKEN
"""
import argparse, datetime as dt, io, json, os, sys, time, urllib.request, urllib.parse, uuid
from PIL import Image, ImageDraw, ImageFont

ESPN = "https://site.api.espn.com/apis/v2/sports/soccer/{lg}/standings"
ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}"
GRAPH = "https://graph.facebook.com/v21.0"

LEAGUES = {
    "eng.1": dict(name="Premier League", short="Premier League", accent=(56, 0, 60), zones=[(4, "ucl"), (5, "uel")], rel=3),
    "esp.1": dict(name="La Liga", short="La Liga", accent=(190, 30, 45), zones=[(4, "ucl"), (5, "uel")], rel=3),
    "ita.1": dict(name="Serie A", short="Serie A", accent=(0, 70, 150), zones=[(4, "ucl"), (5, "uel")], rel=3),
    "ger.1": dict(name="Bundesliga", short="Bundesliga", accent=(200, 20, 20), zones=[(4, "ucl"), (5, "uel")], rel=3),
    "fra.1": dict(name="Ligue 1", short="Ligue 1", accent=(10, 40, 90), zones=[(3, "ucl"), (4, "uel")], rel=2),
    "ksa.1": dict(name="Saudi Pro League", short="Saudi Pro League", accent=(0, 100, 60), zones=[(3, "acl")], rel=3),
    "usa.1": dict(name="MLS", short="MLS", accent=(15, 15, 20), zones=[], rel=0),
}
GROUPS = {
    "europe_saudi": ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ksa.1"],
    "mls": ["usa.1"],
}
TOP_N = 11  # rows shown on the main picture, like the page's current style


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


def stat(entry, name, default=0):
    for s in entry.get("stats", []):
        if s.get("name") == name:
            v = s.get("value")
            return default if v is None else v
    return default


def parse_standings(js):
    """-> list of groups: [{'name': str, 'rows': [row,...]}], rows sorted by rank."""
    groups = []
    for ch in js.get("children", []):
        entries = ch.get("standings", {}).get("entries", [])
        rows = []
        for e in entries:
            t = e["team"]
            logos = t.get("logos") or []
            rows.append(dict(
                tid=str(t.get("id", "")),
                team=t.get("shortDisplayName") or t.get("displayName") or t.get("name"),
                logo=(logos[0].get("href") if logos else None),
                mp=int(stat(e, "gamesPlayed")), w=int(stat(e, "wins")), d=int(stat(e, "ties")),
                l=int(stat(e, "losses")), gf=int(stat(e, "pointsFor")), ga=int(stat(e, "pointsAgainst")),
                gd=int(stat(e, "pointDifferential")), pts=int(stat(e, "points")), rank=int(stat(e, "rank", 999))))
        rows.sort(key=lambda r: (r["rank"], -r["pts"], -r["gd"], -r["gf"]))
        # rank may be missing/duplicated: re-number sequentially after sorting
        for i, r in enumerate(rows, 1):
            r["pos"] = i
        groups.append(dict(name=ch.get("name", ""), rows=rows))
    return groups


ESPN_SUM = "https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/summary?event={ev}"
import re


def last_name(n):
    parts = (n or "").replace("\u00a0", " ").split()
    if not parts:
        return "?"
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in {"de", "da", "di", "dos", "del", "van", "von", "der", "den", "le", "la", "al", "el", "ter", "ten", "mac", "mc"}:
        i -= 1
    return " ".join(parts[i:])


def completed_results(lg, now_utc, hours=14):
    """Matches completed within the last `hours` hours, with goals and each team's season leaders."""
    out, seen = [], set()
    for back in (0, 1, 2):
        d = (now_utc - dt.timedelta(days=back)).strftime("%Y%m%d")
        try:
            js = http_json(ESPN_SB.format(lg=lg, d=d), tries=2)
        except Exception:
            continue
        for ev in js.get("events", []):
            if ev["id"] in seen:
                continue
            comp = ev["competitions"][0]
            if not comp["status"]["type"].get("completed"):
                continue
            when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            if now_utc - when > dt.timedelta(hours=hours):
                continue
            seen.add(ev["id"])
            h = next(c for c in comp["competitors"] if c["homeAway"] == "home")
            a = next(c for c in comp["competitors"] if c["homeAway"] == "away")
            goals = []
            for det in comp.get("details", []) or []:
                if not det.get("scoringPlay"):
                    continue
                ath = (det.get("athletesInvolved") or [{}])[0]
                goals.append(dict(tid=str(det.get("team", {}).get("id", "")), player=ath.get("displayName", ""),
                                  own=bool(det.get("ownGoal")), pen=bool(det.get("penaltyKick")),
                                  minute=(det.get("clock") or {}).get("displayValue", "")))
            leaders = {}
            for c in (h, a):
                for l in c.get("leaders", []) or []:
                    if l.get("name") in ("goals", "goalsLeaders") and l.get("leaders"):
                        x = l["leaders"][0]
                        leaders.setdefault(str(c["team"]["id"]), {})["goals"] = (x.get("athlete", {}).get("displayName", ""), x.get("displayValue", ""))
                    if l.get("name") in ("assists", "assistsLeaders") and l.get("leaders"):
                        x = l["leaders"][0]
                        leaders.setdefault(str(c["team"]["id"]), {})["assists"] = (x.get("athlete", {}).get("displayName", ""), x.get("displayValue", ""))
            out.append(dict(ev=ev["id"], home=h["team"]["shortDisplayName"], away=a["team"]["shortDisplayName"],
                            hid=str(h["team"]["id"]), aid=str(a["team"]["id"]), hs=int(h["score"]), as_=int(a["score"]),
                            goals=goals, leaders=leaders))
    return out


def add_assists(lg, m):
    """Fill m['assists'] = [names] using the match summary 'Assisted by' text. Never raises."""
    m["assists"] = []
    try:
        js = http_json(ESPN_SUM.format(lg=lg, ev=m["ev"]), tries=2)
    except Exception:
        return
    for ke in js.get("keyEvents", []) or []:
        txt = ke.get("text", "") or ""
        if not (ke.get("scoringPlay") or txt.lower().startswith("goal")):
            continue
        mt = re.search(r"Assisted by ([^.]+?)(?: with | following | after | from |\.|$)", txt)
        if mt:
            m["assists"].append(mt.group(1).strip())


def points_before(rows, results):
    """Points of every team before the recent results (to tell 'stay top' from 'go top')."""
    pts = {r["tid"]: r["pts"] for r in rows}
    for m in results:
        if m["hs"] > m["as_"]:
            pts[m["hid"]] = pts.get(m["hid"], 0) - 3
        elif m["hs"] < m["as_"]:
            pts[m["aid"]] = pts.get(m["aid"], 0) - 3
        else:
            pts[m["hid"]] = pts.get(m["hid"], 0) - 1
            pts[m["aid"]] = pts.get(m["aid"], 0) - 1
    return pts


def pick_featured(rows, results):
    pos = {r["tid"]: r["pos"] for r in rows}
    def score(m):
        sc = 0
        for t in (m["hid"], m["aid"]):
            p = pos.get(t, 99)
            sc += 30 if p <= 3 else 14 if p <= 6 else 0
        sc += abs(m["hs"] - m["as_"]) * 1.5 + (m["hs"] + m["as_"]) * 0.5
        return sc
    return max(results, key=score)


def match_sentence(m):
    h, a, hs, as_ = m["home"], m["away"], m["hs"], m["as_"]
    if hs == as_:
        return f"{h} and {a} share the spoils in a {hs}-{as_} draw."
    w, l, ws, ls = (h, a, hs, as_) if hs > as_ else (a, h, as_, hs)
    d = ws - ls
    verb = "smash" if d >= 3 else "beat" if d == 2 else "edge past"
    return f"{w} {verb} {l} {ws}-{ls}."


def goals_sentence(m):
    cnt, order = {}, []
    for g in m["goals"]:
        if not g["player"]:
            continue
        key = last_name(g["player"]) + (" (og)" if g["own"] else "")
        if key not in cnt:
            order.append((key, g["pen"]))
        cnt[key] = cnt.get(key, 0) + 1
    scored = ", ".join(f"{k} ({cnt[k]})" if cnt[k] > 1 else (f"{k} (pen)" if pen else k) for k, pen in order)
    return f"Goals: {scored}." if scored else ""


def star_sentence(m):
    """Mention a team's season top scorer / top assist-maker if they scored or assisted in this match."""
    scorers = {g["player"] for g in m["goals"] if g["player"] and not g["own"]}
    assisters = set(m.get("assists", []))
    tname = {m["hid"]: m["home"], m["aid"]: m["away"]}
    out = []
    for tid, lead in m["leaders"].items():
        gl = lead.get("goals", ("", ""))[0]
        al = lead.get("assists", ("", ""))[0]
        if gl and gl in scorers:
            out.append(f"{last_name(gl)}, {tname.get(tid, '')}'s top scorer this season, got on the scoresheet.")
    return " ".join(out[:2])


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _interest(pos, m):
    sc = 0
    for t in (m["hid"], m["aid"]):
        p = pos.get(t, 99)
        sc += 30 if p <= 3 else 14 if p <= 6 else 0
    sc += abs(m["hs"] - m["as_"]) * 1.5 + (m["hs"] + m["as_"]) * 0.5
    return sc


def _result_line(pos, m):
    line = match_sentence(m).rstrip(".")
    tags = []
    for tid, name in ((m["hid"], m["home"]), (m["aid"], m["away"])):
        p = pos.get(tid, 99)
        if p == 1:
            tags.append(f"{name} lead the table")
        elif p <= 4:
            tags.append(f"{name} are {_ord(p)}")
    if tags:
        line += " (" + "; ".join(tags[:2]) + ")"
    line += "."
    g = goals_sentence(m)
    return (line + " " + g).strip()


def _standouts(ms):
    cnt = {}
    for m in ms:
        for g in m.get("goals", []):
            if g.get("player") and not g.get("own"):
                k = last_name(g["player"])
                cnt[k] = cnt.get(k, 0) + 1
    best = sorted([(c, k) for k, c in cnt.items() if c >= 2], reverse=True)[:3]
    if not best:
        return ""
    words = {2: "a brace", 3: "a hat-trick"}
    parts = [f"{k} with {words.get(c, str(c) + ' goals')}" for c, k in best]
    return "Standout performers: " + ", ".join(parts) + "."


def caption(lg, groups, results):
    meta = LEAGUES[lg]
    rows = groups[0]["rows"]
    if not rows or rows[0]["mp"] == 0 or not results:
        return None
    pos = {r["tid"]: r["pos"] for r in rows}
    top, second = rows[0], rows[1]
    gap = top["pts"] - second["pts"]
    pb = points_before(rows, results)
    prev_leader = max(rows, key=lambda r: (pb.get(r["tid"], r["pts"]), -r["pos"]))
    ranked = sorted(results, key=lambda x: _interest(pos, x), reverse=True)
    shown = ranked[:3]
    feat = shown[0]
    scope = "the " + (groups[0]["name"] or "MLS table") if lg == "usa.1" else ("" if meta["short"] == "La Liga" else "the ") + meta["short"]
    # hook: choose among the angles that fit today's data, rotate by day
    hooks = []
    if prev_leader["tid"] != top["tid"]:
        hooks.append(f"New leaders: {top['team']} go top of {scope}!")
    big = max([x for x in results if min(pos.get(x["hid"], 99), pos.get(x["aid"], 99)) <= 6] or results, key=lambda x: abs(x["hs"] - x["as_"]))
    bd = abs(big["hs"] - big["as_"])
    if bd >= 3:
        w = big["home"] if big["hs"] > big["as_"] else big["away"]
        l = big["away"] if big["hs"] > big["as_"] else big["home"]
        hooks.append(f"{w} run riot against {l}, {max(big['hs'], big['as_'])}-{min(big['hs'], big['as_'])}.")
    tot = sum(x["hs"] + x["as_"] for x in results)
    if tot >= 3 * len(results) and len(results) >= 2:
        hooks.append(f"{tot} goals in {len(results)} matches in {scope}.")
    draws = [x for x in results if x["hs"] == x["as_"]]
    if draws and any(pos.get(t, 99) <= 3 for d in draws for t in (d["hid"], d["aid"])):
        hooks.append("Points dropped at the top of the table.")
    hooks.append(f"Latest {meta['short']} results and what they mean for the table.")
    hook = hooks[dt.datetime.utcnow().timetuple().tm_yday % len(hooks)]
    lines = [hook, ""]
    for m in shown:
        lines.append("⚽ " + _result_line(pos, m))
    st = _standouts(shown)
    if st:
        lines.append("")
        lines.append("⭐ " + st)
    star = star_sentence(feat)
    if star:
        lines.append("⭐ " + star)
    tail = f"{top['team']} {'stay top of' if prev_leader['tid'] == top['tid'] else 'go top of'} {scope} with {top['pts']} points" + (f", {gap} clear of {second['team']}." if gap > 0 else f", level with {second['team']}.")
    lines += ["", "\U0001F4CA " + tail, "Full table in the comments. \U0001F447"]
    return "\n".join(lines)


TOP_CLUBS = {
    "eng.1": ["arsenal", "man city", "manchester city", "liverpool", "chelsea", "man united", "manchester united"],
    "esp.1": ["real madrid", "barcelona", "atlético", "atletico"],
    "ita.1": ["napoli", "milan", "atalanta", "juventus", "como"],
    "ger.1": ["bayern", "dortmund"],
    "fra.1": ["paris saint", "psg", "marseille", "monaco", "lyon", "lille"],
    "ksa.1": ["nassr", "hilal", "qad", "ittihad"],
}


def _is_top(lg, name):
    n = (name or "").lower()
    return any(k in n for k in TOP_CLUBS.get(lg, []))


def _involves_top(lg, m):
    return _is_top(lg, m["home"]) or _is_top(lg, m["away"])


def caption(lg, groups, results):
    meta = LEAGUES[lg]
    rows = groups[0]["rows"]
    if not rows or rows[0]["mp"] == 0 or not results:
        return None
    pos = {r["tid"]: r["pos"] for r in rows}
    top, second = rows[0], rows[1]
    gap = top["pts"] - second["pts"]
    pb = points_before(rows, results)
    prev_leader = max(rows, key=lambda r: (pb.get(r["tid"], r["pts"]), -r["pos"]))
    scope = "the " + (groups[0]["name"] or "MLS table") if lg == "usa.1" else ("" if meta["short"] == "La Liga" else "the ") + meta["short"]
    tops = [m for m in results if _involves_top(lg, m)]
    feat = max(tops or results, key=lambda x: _interest(pos, x))
    rest = sorted([m for m in results if m is not feat],
                  key=lambda x: (not _involves_top(lg, x), -_interest(pos, x)))
    shown = rest[:4]
    lines = [_result_line(pos, feat), ""]
    if rest:
        goals_rest = sum(x["hs"] + x["as_"] for x in rest)
        lines.append(f"{len(rest)} more {meta['short']} results are in, with {goals_rest} goals between them:")
        for m in shown:
            lines.append("⚽ " + _result_line(pos, m))
    st = _standouts([feat] + shown)
    if st:
        lines.append("")
        lines.append("⭐ " + st)
    tail = f"{top['team']} {'stay top of' if prev_leader['tid'] == top['tid'] else 'go top of'} {scope} with {top['pts']} points" + (f", {gap} clear of {second['team']}." if gap > 0 else f", level with {second['team']}.")
    lines += ["", "\U0001F4CA " + tail, "Full table in the comments. \U0001F447"]
    return "\n".join(lines)


# ----------------------------------------------------------------- new style: table caption + two comments
IMG_NAME = {"eng.1": "premier_league", "esp.1": "la_liga", "ita.1": "serie_a", "ger.1": "bundesliga",
            "fra.1": "ligue_1", "ksa.1": "saudi_pro_league", "usa.1": "mls_eastern"}
COUNTRY = {"eng.1": "England", "esp.1": "Spain", "ita.1": "Italy", "ger.1": "Germany",
           "fra.1": "France", "ksa.1": "Saudi Arabia", "usa.1": "United States"}
# language of the 2nd comment. Premier League and MLS: English only (one comment).
LOCAL_LANG = {"ita.1": "it", "esp.1": "es", "ger.1": "de", "fra.1": "fr", "ksa.1": "ar"}
SCOPE_EN = {"eng.1": "the Premier League", "esp.1": "La Liga", "ita.1": "Serie A", "ger.1": "the Bundesliga",
            "fra.1": "Ligue 1", "ksa.1": "the Saudi Pro League", "usa.1": "the Eastern Conference"}
TITLE_EN = {"eng.1": "the Premier League", "esp.1": "La Liga", "ita.1": "the Scudetto", "ger.1": "the Bundesliga",
            "fra.1": "Ligue 1", "ksa.1": "the Saudi Pro League", "usa.1": "the MLS Cup"}
LG_LOCAL = {"it": "Serie A", "es": "La Liga", "de": "Bundesliga", "fr": "Ligue 1", "ar": "دوري روشن السعودي"}


def _unbeaten(rows):
    return [r for r in rows if r["l"] == 0 and r["mp"] >= 3]


def caption_table(lg, groups):
    """3-line caption written from the table: leader, places 3-5, then one rotating fact."""
    rows = groups[0]["rows"]
    if len(rows) < 6 or rows[0]["mp"] == 0:
        return None
    sc = SCOPE_EN[lg]
    r1, r2, r3, r4, r5 = rows[:5]
    gap = r1["pts"] - r2["pts"]
    day = dt.datetime.utcnow().timetuple().tm_yday
    if gap > 0:
        l1 = f"{r1['team']} lead {sc} with {r1['pts']} points, {gap} clear of {r2['team']}. \U0001F51D"
    else:
        l1 = f"{r1['team']} and {r2['team']} are level on {r1['pts']} points at the top of {sc}. \U0001F51D"
    l2 = f"{r3['team']} are third on {r3['pts']}, {r4['team']} fourth on {r4['pts']} and {r5['team']} fifth on {r5['pts']}."
    facts = []
    unb = _unbeaten(rows)
    if len(unb) == 1:
        facts.append(f"{unb[0]['team']} are the only unbeaten team after {unb[0]['mp']} games.")
    elif len(unb) == 2:
        facts.append(f"{unb[0]['team']} and {unb[1]['team']} are the only unbeaten teams after {max(u['mp'] for u in unb)} games.")
    last = rows[-1]
    if lg != "usa.1" and len(rows) > 6:
        safe = rows[-4]["pts"] - last["pts"]
        if safe > 0:
            facts.append(f"{last['team']} are bottom on {last['pts']} points, {safe} from safety.")
    best = max(rows, key=lambda r: r["gd"])
    if best["gd"] >= 5:
        facts.append(f"{best['team']} have the best goal difference in {sc}: +{best['gd']}.")
    facts.append(f"Only {r1['pts'] - r4['pts']} points separate the top four." if r1["pts"] - r4["pts"] >= 2 else f"{r4['team']} sit fourth with {r4['pts']} points.")
    return "\n".join([l1, l2, facts[day % len(facts)]])


def _pts(lang, n):
    if lang == "ar":
        return "نقطة واحدة" if n == 1 else "نقطتين" if n == 2 else f"{n} نقاط" if 3 <= n <= 10 else f"{n} نقطة"
    one = {"en": "point", "it": "punto", "es": "punto", "de": "Punkt", "fr": "point"}[lang]
    many = {"en": "points", "it": "punti", "es": "puntos", "de": "Punkte", "fr": "points"}[lang]
    return f"{n} {one if n == 1 else many}"


# each language: unb1/unb2 = unbeaten fact (1 or 2 teams), gap/level = leader sentence,
# title_q = question about the title, spread/top4_q = top-four spread + question
PH = {
    "en": dict(unb1="{a} are the only unbeaten side in {lg}. \U0001F525", unb2="{a} and {b} are the only unbeaten sides in {lg}. \U0001F525",
               gap="{a} lead {b} by {n}.", level="{a} and {b} are level on {n}.",
               title_q="Who wins {title}? \U0001F447", spread="Only {n} separate the top four in {lg}. \U0001F525",
               top4_q="Who finishes in the top four? \U0001F447"),
    "it": dict(unb1="{a} è l'unica squadra imbattuta in {lg}. \U0001F525", unb2="{a} e {b} sono le uniche squadre imbattute in {lg}. \U0001F525",
               gap="{a} è in testa con {n} di vantaggio su {b}.", level="{a} e {b} sono appaiate in vetta con {n}.",
               title_q="Chi vincerà lo scudetto? \U0001F447", spread="Solo {n} separano le prime quattro in {lg}. \U0001F525",
               top4_q="Chi chiuderà in zona Champions? \U0001F447"),
    "es": dict(unb1="{a} es el único equipo invicto en {lg}. \U0001F525", unb2="{a} y {b} son los únicos equipos invictos en {lg}. \U0001F525",
               gap="{a} lidera con {n} de ventaja sobre {b}.", level="{a} y {b} empatan en lo más alto con {n}.",
               title_q="¿Quién ganará La Liga? \U0001F447", spread="Solo {n} separan a los cuatro primeros de {lg}. \U0001F525",
               top4_q="¿Quién terminará en puestos de Champions? \U0001F447"),
    "de": dict(unb1="{a} ist das einzige ungeschlagene Team der {lg}. \U0001F525", unb2="{a} und {b} sind die einzigen ungeschlagenen Teams der {lg}. \U0001F525",
               gap="{a} liegt {n} vor {b}.", level="{a} und {b} sind punktgleich an der Spitze.",
               title_q="Wer wird Deutscher Meister? \U0001F447", spread="Nur {n} trennen die ersten vier der {lg}. \U0001F525",
               top4_q="Wer landet in den Champions-League-Rängen? \U0001F447"),
    "fr": dict(unb1="{a} est la seule équipe invaincue en {lg}. \U0001F525", unb2="{a} et {b} sont les seules équipes invaincues en {lg}. \U0001F525",
               gap="{a} est leader avec {n} d'avance sur {b}.", level="{a} et {b} sont à égalité en tête avec {n}.",
               title_q="Qui sera champion de France ? \U0001F447", spread="Seulement {n} séparent les quatre premiers en {lg}. \U0001F525",
               top4_q="Qui finira dans le top 4 ? \U0001F447"),
    "ar": dict(unb1="{a} هو الفريق الوحيد الذي لم يخسر في {lg}. \U0001F525", unb2="{a} و {b} هما الفريقان الوحيدان اللذان لم يخسرا في {lg}. \U0001F525",
               gap="{a} يتصدر بفارق {n} عن {b}.", level="{a} و {b} متعادلان في الصدارة برصيد {n}.",
               title_q="من سيفوز بلقب الدوري؟ \U0001F447", spread="فارق {n} فقط بين الفرق الأربعة الأولى في {lg}. \U0001F525",
               top4_q="من سيحسم المراكز الأربعة الأولى؟ \U0001F447"),
}


def _comment(lg, rows, lang):
    """Two lines in `lang`. Rotates between three angles by day so the same comment does not repeat."""
    ph = PH[lang]
    lgn = SCOPE_EN[lg] if lang == "en" else LG_LOCAL[lang]
    title = TITLE_EN[lg]
    r1, r2, r4 = rows[0], rows[1], rows[3]
    gap = r1["pts"] - r2["pts"]
    gap_s = (ph["gap"] if gap > 0 else ph["level"]).format(a=r1["team"], b=r2["team"], n=_pts(lang, gap if gap > 0 else r1["pts"]))
    title_q = ph["title_q"].format(title=title)
    unb = _unbeaten(rows)
    opts = []
    if len(unb) in (1, 2):
        first = (ph["unb1"] if len(unb) == 1 else ph["unb2"]).format(a=unb[0]["team"], b=unb[-1]["team"], lg=lgn)
        opts.append((first, gap_s + " " + title_q))
    opts.append((gap_s, title_q))
    spread = r1["pts"] - r4["pts"]
    if spread >= 2:
        opts.append((ph["spread"].format(n=_pts(lang, spread), lg=lgn), ph["top4_q"]))
    day = dt.datetime.utcnow().timetuple().tm_yday
    a, b = opts[day % len(opts)]
    return a + "\n" + b


def make_comments(lg, groups):
    """[(lang, text)] - English first, then the local language of the league's country (if any)."""
    rows = groups[0]["rows"]
    out = [("en", _comment(lg, rows, "en"))]
    if lg in LOCAL_LANG:
        out.append((LOCAL_LANG[lg], _comment(lg, rows, LOCAL_LANG[lg])))
    return out


def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"])
    for base in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/", ""):
        for n in names:
            try:
                return ImageFont.truetype(base + n, size)
            except OSError:
                pass
    return ImageFont.load_default()


_LOGO_CACHE = {}


def fetch_logo(url, size):
    """Download a club logo once (500px PNG), return it resized with smooth edges; None if unavailable."""
    if not url:
        return None
    if url not in _LOGO_CACHE:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                _LOGO_CACHE[url] = Image.open(io.BytesIO(r.read())).convert("RGBA")
        except Exception:
            _LOGO_CACHE[url] = None
    src = _LOGO_CACHE[url]
    if src is None:
        return None
    im = src.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def initials_logo(name, size, color):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=color)
    t = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    f = font(int(size * 0.42), True)
    w = d.textlength(t, font=f)
    d.text(((size - w) / 2, size * 0.26), t, font=f, fill="white")
    return im


def render_table(lg, subtitle, rows, season_txt="", n=None, use_logos=True):
    meta = LEAGUES[lg]
    rows = rows[:n] if n else rows
    W, PAD = 1080, 36
    HEAD, TABH, ROWH = 150, 70, 72
    H = HEAD + TABH + ROWH * len(rows) + 90
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, HEAD), fill=meta["accent"])
    d.text((PAD, 34), meta["name"], font=font(54, True), fill="white")
    sub = " · ".join(x for x in (season_txt, subtitle) if x)
    d.text((PAD, 104), sub, font=font(28), fill=(225, 225, 235))
    # column layout
    cols = [("MP", 560), ("W", 630), ("D", 695), ("L", 760), ("GF", 835), ("GA", 910), ("GD", 985), ("PTS", 1050)]
    y0 = HEAD + 14
    d.text((PAD, y0 + 18), "Team", font=font(26), fill=(110, 110, 120))
    for label, x in cols:
        w = d.textlength(label, font=font(26, label == "PTS"))
        d.text((x - w, y0 + 18), label, font=font(26, label == "PTS"), fill=(30, 30, 40) if label == "PTS" else (110, 110, 120))
    y = HEAD + TABH
    palette = [(66, 99, 160), (160, 66, 66), (66, 140, 99), (140, 99, 160), (180, 130, 50)]
    for i, r in enumerate(rows):
        if i % 2 == 0:
            d.rectangle((0, y, W, y + ROWH), fill=(246, 247, 250))
        # zone marker
        zone = next((z for pos, z in meta["zones"] if r["pos"] <= pos), None)
        zc = {"ucl": (30, 110, 220), "uel": (240, 140, 20), "acl": (30, 110, 220)}.get(zone)
        if meta["rel"] and r["pos"] > len(rows) + 0 and False:
            zc = None
        if zc:
            d.rectangle((0, y + 8, 7, y + ROWH - 8), fill=zc)
        d.text((PAD, y + 20), str(r["pos"]), font=font(30), fill=(60, 60, 70))
        logo = fetch_logo(r["logo"], 54) if use_logos else None
        if logo is None:
            logo = initials_logo(r["team"], 54, palette[i % len(palette)])
        img.paste(logo, (PAD + 52, y + (ROWH - logo.height) // 2), logo)
        name = r["team"]
        f = font(32)
        while d.textlength(name, font=f) > 400 and len(name) > 3:
            name = name[:-2].rstrip() + "."
        d.text((PAD + 112, y + 18), name, font=f, fill=(15, 15, 25))
        vals = [r["mp"], r["w"], r["d"], r["l"], r["gf"], r["ga"], r["gd"], r["pts"]]
        for (label, x), v in zip(cols, vals):
            txt = str(v)
            fnt = font(32, True) if label == "PTS" else font(30)
            w = d.textlength(txt, font=fnt)
            d.text((x - w, y + 19), txt, font=fnt, fill=(15, 15, 25) if label == "PTS" else (60, 60, 70))
        y += ROWH
    d.line((0, y, W, y), fill=(220, 222, 230), width=2)
    # relegation / qualification key (small footer)
    key = []
    if any(z == "ucl" for _, z in meta["zones"]):
        key.append(("Champions League", (30, 110, 220)))
    if any(z == "uel" for _, z in meta["zones"]):
        key.append(("Europa League", (240, 140, 20)))
    if any(z == "acl" for _, z in meta["zones"]):
        key.append(("AFC Champions League", (30, 110, 220)))
    x = PAD
    for txt, c in key:
        d.rectangle((x, y + 32, x + 8, y + 56), fill=c)
        d.text((x + 18, y + 30), txt, font=font(24), fill=(90, 90, 100))
        x += 40 + int(d.textlength(txt, font=font(24))) + 30
    stamp = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=5, minutes=45)))
    t = stamp.strftime("%d %b %Y")
    w = d.textlength(t, font=font(24))
    d.text((W - PAD - w, y + 30), t, font=font(24), fill=(90, 90, 100))
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


def fb_post_photo(page_id, token, png, message, place=None):
    fields = {"message": message, "access_token": token, "published": "true"}
    if place:
        fields["place"] = place  # Facebook place id -> the post shows "at <country>"
    body, ct = multipart(fields, {"source": ("table.png", png, "image/png")})
    req = urllib.request.Request(f"{GRAPH}/{page_id}/photos", data=body, headers={"Content-Type": ct})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fb_comment_text(post_id, token, message):
    """Text comment written by the Page itself."""
    body = urllib.parse.urlencode({"message": message, "access_token": token}).encode()
    req = urllib.request.Request(f"{GRAPH}/{post_id}/comments", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


_PLACE_CACHE = {}


def place_for(lg, token):
    """Facebook place id of the league's country. FB_PLACE_IDS (json {"ita.1": "123"}) overrides the search.
    Returns None when nothing safe is found - the post then goes out without a location."""
    if lg in _PLACE_CACHE:
        return _PLACE_CACHE[lg]
    pid = None
    try:
        pid = json.loads(os.environ.get("FB_PLACE_IDS", "{}")).get(lg)
        if not pid:
            q = urllib.parse.urlencode({"type": "place", "q": COUNTRY[lg], "fields": "id,name,location", "limit": 15, "access_token": token})
            for p in http_json(f"{GRAPH}/search?{q}", tries=2).get("data", []):
                loc = p.get("location") or {}
                if (p.get("name") or "").strip().lower() == COUNTRY[lg].lower() and not loc.get("street"):
                    pid = p["id"]
                    break
    except Exception as e:  # noqa
        print(f"[{lg}] place lookup failed: {e}", file=sys.stderr)
    print(f"[{lg}] location: {COUNTRY[lg]} -> {pid or 'not found, posting without location'}")
    _PLACE_CACHE[lg] = pid
    return pid


def fb_like(post_id, token):
    """Like the post as the Page (a Page token acts as the Page)."""
    body = urllib.parse.urlencode({"access_token": token}).encode()
    req = urllib.request.Request(f"{GRAPH}/{post_id}/likes", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def to_png(img):
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


# ----------------------------------------------------------------- main
def build_one(lg, now, imgdir="posts"):
    js = http_json(ESPN.format(lg=lg))
    groups = parse_standings(js); groups = [g for g in groups if lg != "usa.1" or any("Inter Miami" in r["team"] for r in g["rows"])] or groups
    season = js.get("season", {}).get("displayName", "") if isinstance(js.get("season"), dict) else ""
    results = completed_results(lg, now)
    if not results:
        return None  # no matches finished recently -> skip
    cap = caption_table(lg, groups)
    if not cap:
        return None
    comments = make_comments(lg, groups)
    # the picture: the finished STANDINGS picture from the Crest Placer (posts/<league>.png), else the old plain table
    imgfile = f"{imgdir}/{IMG_NAME[lg]}.png"
    png, used = None, None
    if os.path.exists(imgfile):
        png = open(imgfile, "rb").read()
        main = Image.open(io.BytesIO(png)).convert("RGB")
        used = imgfile
    else:
        print(f"[{lg}] WARNING: {imgfile} not found - using the old plain table picture", file=sys.stderr)
        main = render_table(lg, groups[0]["name"] if len(groups) > 1 else "Standings", groups[0]["rows"], season, n=TOP_N)
    return dict(lg=lg, caption=cap, comments=comments, main=main, png=png, used=used, results=results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, choices=GROUPS)
    ap.add_argument("--post-at", help="UTC HH:MM to publish at")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="out"); ap.add_argument("--only", help="comma-separated ESPN league codes (testing)")
    ap.add_argument("--images", default="posts", help="folder with the finished STANDINGS pictures (<league>.png)")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    os.makedirs(a.out, exist_ok=True)
    built = []
    for lg in [x for x in GROUPS[a.group] if not a.only or x in a.only.split(",")]:
        try:
            item = build_one(lg, now, a.images)
        except Exception as e:  # one bad league must not stop the others
            print(f"[{lg}] ERROR building: {e}", file=sys.stderr)
            continue
        if not item:
            print(f"[{lg}] skipped (no recently completed matches or no data)")
            continue
        item["main"].save(f"{a.out}/{lg}_main.png")
        open(f"{a.out}/{lg}_caption.txt", "w").write(item["caption"])
        open(f"{a.out}/{lg}_comments.txt", "w").write("\n\n".join(f"[{l}]\n{t}" for l, t in item["comments"]))
        json.dump(item["results"], open(f"{a.out}/{lg}_matchdata.json", "w"), indent=1, default=str)  # raw data, for debugging captions
        print(f"[{lg}] built:\n{item['caption']}\n" + "\n".join(f"  comment [{l}]: {t!r}" for l, t in item["comments"]) + "\n")
        built.append(item)
    if a.dry_run or not built:
        return
    if a.post_at:
        hh, mm = map(int, a.post_at.split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target < now - dt.timedelta(hours=12):
            target += dt.timedelta(days=1)
        wait = (target - dt.datetime.now(dt.timezone.utc)).total_seconds()
        if 0 < wait < 3 * 3600:
            print(f"waiting {wait:.0f}s until {target.isoformat()}")
            time.sleep(wait)
    page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    used = []
    for item in built:
        try:
            res = fb_post_photo(page, token, item["png"] or to_png(item["main"]), item["caption"], place_for(item["lg"], token))
            post_id = res.get("post_id") or res.get("id")
            print(f"[{item['lg']}] posted {post_id}")
            if item["used"]:
                used.append(item["used"])
            try:
                fb_like(post_id, token)  # the Page likes its own post first
            except Exception as e:
                print(f"[{item['lg']}] like failed: {e}", file=sys.stderr)
            for lang, text in item["comments"]:  # English first, then the local language
                try:
                    fb_comment_text(post_id, token, text)
                    print(f"[{item['lg']}] comment [{lang}] posted")
                except Exception as e:
                    print(f"[{item['lg']}] comment [{lang}] failed: {e}", file=sys.stderr)
                time.sleep(3)
        except Exception as e:
            print(f"[{item['lg']}] ERROR posting: {e}", file=sys.stderr)
        time.sleep(20)  # small gap between posts
    open(f"{a.out}/used_images.txt", "w").write("\n".join(used))  # the workflow deletes these so a picture is never posted twice


if __name__ == "__main__":
    main()
