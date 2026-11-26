#!/usr/bin/env python3
"""Champions League (top 18 of the 36-team league phase, one picture) and
AFC Champions League Elite (the region table with Al Nassr, plus a Ronaldo line).

  python cups.py --comp uefa.champions --dry-run
  python cups.py --comp afc.champions
Everything is read live from ESPN at post time; nothing is pre-made.
"""
import argparse, datetime as dt, io, json, os, sys, time, urllib.parse, urllib.request

import standings_post as sp
import stadium

NAME = {"uefa.champions": "Champions League", "afc.champions": "AFC Champions League Elite"}


# ----------------------------------------------------------------- data
def groups_with_notes(comp):
    js = sp.http_json(sp.ESPN.format(lg=comp))
    groups = sp.parse_standings(js)
    # keep ESPN's qualification notes (e.g. "Round of 16") per team, used for the zone colours
    notes = {}
    for ch in js.get("children", []):
        for e in ch.get("standings", {}).get("entries", []):
            n = e.get("note") or {}
            if n.get("description"):
                notes[str(e["team"].get("id", ""))] = n["description"]
    return groups, notes


def zones_from_notes(rows, notes, default):
    """Turn ESPN's notes into stadium zone limits: green = 1st note band, blue = 2nd band, red = 'eliminated'."""
    bands = []
    for r in rows:
        d = (notes.get(r["tid"]) or "").lower().split(" - ")[0].strip()  # "playoffs - seeded/unseeded" = one band
        if not d:
            continue
        if not bands or bands[-1][0] != d:
            bands.append([d, r["pos"], r["pos"]])
        else:
            bands[-1][2] = r["pos"]
    if not bands:
        return default, {}
    z, lab = dict(default), {}
    good = [b for b in bands if "elimin" not in b[0] and "relegat" not in b[0]]
    if good:
        z["ucl"] = good[0][2]; lab["ucl"] = good[0][0].title()
        z["uel"] = good[1][2] if len(good) > 1 else 0
        if len(good) > 1:
            lab["uel"] = good[1][0].title()
    bad = [b for b in bands if "elimin" in b[0]]
    if bad:
        z["rel"] = bad[0][1]; lab["rel"] = "Eliminated"
    return z, lab


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ----------------------------------------------------------------- captions
BIG = ["real madrid", "barcelona", "bayern", "liverpool", "arsenal", "manchester city", "man city", "paris", "psg",
       "inter", "chelsea", "juventus", "atl", "dortmund", "milan", "napoli", "tottenham", "manchester united", "man united",
       "nassr", "hilal", "ahli", "ittihad", "al ain", "sadd"]


def big(m):
    t = (m["home"] + " " + m["away"]).lower()
    return any(k in t for k in BIG)


def results_block(comp, rows, results, n=5):
    pos = {r["tid"]: r["pos"] for r in rows}
    ordered = sorted(results, key=lambda m: (not big(m), -sp._interest(pos, m)))
    lines = ["⚽ " + sp._result_line(pos, m) for m in ordered[:n]]
    if len(ordered) > n:
        lines.append(f"➕ {len(ordered) - n} more results in the table.")
    st = sp._standouts(ordered)
    if st:
        lines.append("⭐ " + st)
    return lines


def ronaldo_line(rows, results, region):
    r = next((x for x in rows if "nassr" in (x["team"] + x["full"]).lower()), None)
    if not r:
        return None
    m = next((m for m in results if "nassr" in (m["home"] + m["away"]).lower()), None)
    parts = []
    if m:
        home = "nassr" in m["home"].lower()
        us, them = (m["hs"], m["as_"]) if home else (m["as_"], m["hs"])
        opp = m["away"] if home else m["home"]
        verb = "beat" if us > them else "drew with" if us == them else "lost to"
        score = f"{max(us, them)}-{min(us, them)}" if us != them else f"{us}-{them}"
        rg = [g for g in m.get("goals", []) if "ronaldo" in (g.get("player") or "").lower() and not g.get("own")]
        ron = ""
        if len(rg) == 1:
            ron = " Ronaldo scored" + (" from the penalty spot" if rg[0].get("pen") else "") + (f" ({rg[0]['minute']})" if rg[0].get("minute") else "") + "."
        elif len(rg) >= 2:
            ron = f" Ronaldo scored {'twice' if len(rg) == 2 else str(len(rg)) + ' goals'}."
        parts.append(f"⭐ Cristiano Ronaldo's Al Nassr {verb} {opp} {score}.{ron}")
    where = f"in the {region}" if region else "in the table"
    lead = rows[0]
    if r["pos"] == 1:
        nxt = rows[1]
        gap = r["pts"] - nxt["pts"]
        parts.append(f"Al Nassr top the {region or 'table'} on {r['pts']} points" + (f", {gap} clear of {nxt['team']}." if gap else f", level with {nxt['team']}."))
    else:
        parts.append(f"Al Nassr are {ordinal(r['pos'])} {where} on {r['pts']} points, {lead['pts'] - r['pts']} behind leaders {lead['team']}.")
    return " ".join(parts)


def table_lines(comp, rows, z):
    r1, r2 = rows[0], rows[1]
    gap = r1["pts"] - r2["pts"]
    l1 = (f"{r1['team']} lead the {NAME[comp]} table on {r1['pts']} points, {gap} clear of {r2['team']}." if gap
          else f"{r1['team']} and {r2['team']} are level on {r1['pts']} points at the top.")
    out = [l1]
    k = z.get("ucl") or 0
    if k and len(rows) > k:
        a, b = rows[k - 1], rows[k]
        out.append(f"{a['team']} hold the last Round of 16 place ({ordinal(k)}) on {a['pts']} points; {b['team']} are {ordinal(k + 1)} on {b['pts']}.")
    return out


# ----------------------------------------------------------------- facebook: one post with several pictures
def fb_upload_unpublished(page, token, png):
    body, ct = sp.multipart({"published": "false", "access_token": token}, {"source": ("table.png", png, "image/png")})
    req = urllib.request.Request(f"{sp.GRAPH}/{page}/photos", data=body, headers={"Content-Type": ct})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)["id"]


def fb_post_album(page, token, pngs, message):
    ids = [fb_upload_unpublished(page, token, p) for p in pngs]
    fields = {"message": message, "access_token": token}
    for i, pid in enumerate(ids):
        fields[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    req = urllib.request.Request(f"{sp.GRAPH}/{page}/feed", data=urllib.parse.urlencode(fields).encode())
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fb_photo_comment(post_id, token, png, message=""):
    body, ct = sp.multipart({"message": message, "access_token": token}, {"source": ("table.png", png, "image/png")})
    req = urllib.request.Request(f"{sp.GRAPH}/{post_id}/comments", data=body, headers={"Content-Type": ct})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fb_pin_comment(comment_id, token):
    body = urllib.parse.urlencode({"is_pinned": "true", "access_token": token}).encode()
    req = urllib.request.Request(f"{sp.GRAPH}/{comment_id}", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def latest_post_with(page, token, words):
    url = f"{sp.GRAPH}/{page}/posts?fields=id,message,created_time&limit=15&access_token={urllib.parse.quote(token)}"
    for p in sp.http_json(url).get("data", []):
        if words.lower() in (p.get("message") or "").lower():
            return p["id"]
    return None


def comment_rest(page, token, post_id, png):
    """Second half of the table as a photo comment, then try to pin it (Facebook may refuse pinning via API)."""
    res = fb_photo_comment(post_id, token, png, "Places 19-36 \U0001F447")
    cid = res.get("id")
    print(f"rest-of-table comment {cid} on {post_id}")
    try:
        fb_pin_comment(cid, token)
        print("comment pinned")
    except Exception as e:
        print(f"PIN FAILED (pin it by hand): {e}", file=sys.stderr)
    return cid


# ----------------------------------------------------------------- build + post
def build(comp, now, hours):
    groups, notes = groups_with_notes(comp)
    results = sp.completed_results(comp, now, hours=hours)
    rest = None
    if comp == "afc.champions":
        g = next((g for g in groups if any("nassr" in (r["team"] + r["full"]).lower() for r in g["rows"])), groups[0])
        rows = g["rows"]
        region = (g["name"] or "").replace("AFC Champions League Elite", "").strip(" -") or "West"
        region = region if "region" in region.lower() else f"{region} region"
        ids = {r["tid"] for r in rows}
        res = [m for m in results if m["hid"] in ids or m["aid"] in ids]
        z, lab = zones_from_notes(rows, notes, stadium.STYLE[comp]["zones"])
        pics = [stadium.render_standings(comp, rows, sp.fetch_logo, title=f"ACL Elite • {region.split()[0]}", zones=z, labels=lab)]
        lines = []
        ron = ronaldo_line(rows, res, region)
        if ron:
            lines += [ron, ""]
        if res:
            lines += [f"AFC Champions League Elite results ({region.split()[0]}):"] + results_block(comp, rows, res, 4) + [""]
        lines += ["\U0001F4CA " + " ".join(table_lines(comp, rows, z))]
        cap = "\n".join(lines)
    else:
        rows = groups[0]["rows"]
        z, lab = zones_from_notes(rows, notes, stadium.STYLE[comp]["zones"])
        # one picture: the top 18 of the league phase (Amisha: "only 18, no need for the others")
        pics = [stadium.render_standings(comp, rows[:18], sp.fetch_logo, start=1, title="Champions League", zones=z, labels=lab)]
        # places 19-36 go in a pinned comment under the post
        rest = stadium.render_standings(comp, rows[18:], sp.fetch_logo, start=19, title="Champions League", zones=z, labels=lab) if len(rows) > 18 else None
        lines = []
        if results:
            lines += results_block(comp, rows, results, 5) + [""]
        lines += ["\U0001F4CA " + " ".join(table_lines(comp, rows, z))]
        cap = "\n".join(lines)
    item = dict(caption=cap, pngs=[sp.to_png(p) for p in pics], pics=pics, results=results)
    if comp == "uefa.champions" and rest is not None:
        item["rest"] = rest
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True, choices=list(NAME))
    ap.add_argument("--hours", type=int, default=30, help="results finished within this many hours")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rest-only", action="store_true", help="only add the 19-36 picture as a comment on the latest Champions League post")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    item = build(a.comp, now, a.hours)
    os.makedirs("out", exist_ok=True)
    for i, p in enumerate(item["pics"], 1):
        p.save(f"out/{a.comp}_{i}.png")
    open(f"out/{a.comp}_caption.txt", "w").write(item["caption"])
    if item.get("rest") is not None:
        item["rest"].save(f"out/{a.comp}_19-36.png")
    print(item["caption"])
    if a.dry_run:
        return
    page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    if a.rest_only:
        if item.get("rest") is None:
            return
        pid = latest_post_with(page, token, "Champions League table")
        if not pid:
            sys.exit("no recent Champions League post found")
        comment_rest(page, token, pid, sp.to_png(item["rest"]))
        return
    if len(item["pngs"]) == 1:
        res = sp.fb_post_photo(page, token, item["pngs"][0], item["caption"])
    else:
        res = fb_post_album(page, token, item["pngs"], item["caption"])
    post_id = res.get("post_id") or res.get("id")
    print(f"[{a.comp}] posted {post_id}")
    try:
        sp.fb_like(post_id, token)
    except Exception as e:
        print(f"like failed: {e}", file=sys.stderr)
    if item.get("rest") is not None:
        time.sleep(5)
        try:
            comment_rest(page, token, post_id, sp.to_png(item["rest"]))
        except Exception as e:
            print(f"rest-of-table comment failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
