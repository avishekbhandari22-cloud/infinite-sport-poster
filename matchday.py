#!/usr/bin/env python3
"""Post each league's table as soon as THAT league's matches for the day are all finished.

Europe + Saudi: checked every 30 min from 00:00 to 04:00 Nepal time.
MLS: one run at 10:00 Nepal time that posts if any MLS match finished overnight (the old rule).
  python matchday.py --check                 -> prints which leagues are ready (stdlib only, fast)
  python matchday.py --post esp.1,eng.1      -> builds and posts those leagues, records them in state/posted.json

A league is "ready" for a match day (the league's own local calendar day, e.g. Sunday in Spain) when:
  * at least one match that day has finished,
  * no match that day is still to start or still being played,
  * the last match kicked off at least 2h05m ago (so ESPN's table has caught up),
  * and that league + day has not been posted before (state/posted.json).
So La Liga posts after Sunday's last La Liga game, the Premier League after its own last game, and so on.
"""
import argparse, datetime as dt, json, os, sys, time, urllib.request
from zoneinfo import ZoneInfo

SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d}"
LEAGUE_TZ = {
    "eng.1": "Europe/London", "esp.1": "Europe/Madrid", "ita.1": "Europe/Rome", "ger.1": "Europe/Berlin",
    "fra.1": "Europe/Paris", "ksa.1": "Asia/Riyadh", "tur.1": "Europe/Istanbul", "usa.1": "America/New_York",
}
ORDER = list(LEAGUE_TZ)
STATE = "state/posted.json"
SETTLE = dt.timedelta(hours=2, minutes=5)    # last kickoff -> table safe to read
TOO_OLD = dt.timedelta(hours=20)            # never post a day that finished long ago
STALE_PRE = dt.timedelta(hours=4)           # a "not started" match this far past kickoff = postponed


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


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    for k in st:
        st[k] = sorted(set(st[k]))[-60:]
    json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)


def fetch_events(lg, now):
    evs = {}
    for shift in (-1, 0, 1, 2):  # tomorrow .. two days ago (UTC dates), deduplicated by id
        d = (now - dt.timedelta(days=shift)).strftime("%Y%m%d")
        try:
            js = http_json(SB.format(lg=lg, d=d), tries=2)
        except Exception as e:
            print(f"[{lg}] scoreboard {d} failed: {e}", file=sys.stderr)
            continue
        for ev in js.get("events", []):
            evs[ev["id"]] = ev
    return list(evs.values())


def ready_days(lg, events, now, posted, log=print):
    """Local match days of `lg` that are complete and not yet posted (oldest first)."""
    tz = ZoneInfo(LEAGUE_TZ[lg])
    days = {}
    for ev in events:
        ko = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        st = ev["competitions"][0]["status"]["type"]
        days.setdefault(ko.astimezone(tz).date().isoformat(), []).append(
            (ko, st.get("state", ""), bool(st.get("completed"))))
    out = []
    for day, ms in sorted(days.items()):
        if day in posted:
            continue
        waiting = [ko for ko, s, _ in ms if s == "in" or (s == "pre" and now - ko < STALE_PRE)]
        done = [ko for ko, _, c in ms if c]
        if not done:
            continue
        if waiting:
            log(f"[{lg}] {day}: {len(done)} finished, {len(waiting)} still to finish")
            continue
        last = max(done)
        if now - last < SETTLE:
            log(f"[{lg}] {day}: all {len(done)} finished, waiting for the table to update")
            continue
        if now - last > TOO_OLD:
            continue
        out.append(day)
    return out


def check(leagues, now, force=False):
    st = load_state()
    ready = {}
    for lg in leagues:
        if force:
            ready[lg] = "forced"  # manual repost: never mark a match day as posted
            continue
        days = ready_days(lg, fetch_events(lg, now), now, set(st.get(lg, [])))
        if days:
            ready[lg] = ",".join(days)
            print(f"[{lg}] READY: match day {days[-1]} finished")
    return ready


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def ronaldo_line(rows):
    """One caption line about Ronaldo's club, written only from the live table."""
    r = next((x for x in rows if "nassr" in (x.get("team") or "").lower() or "nassr" in (x.get("full") or "").lower()), None)
    if not r:
        return None
    if r["pos"] == 1:
        nxt = rows[1]
        gap = r["pts"] - nxt["pts"]
        tail = f"{gap} clear of {nxt['team']}" if gap > 0 else f"level with {nxt['team']}"
        return f"\u2b50 Cristiano Ronaldo's Al Nassr top the table on {r['pts']} points, {tail}."
    lead = rows[0]
    return (f"\u2b50 Cristiano Ronaldo's Al Nassr are {_ord(r['pos'])} on {r['pts']} points, "
            f"{lead['pts'] - r['pts']} behind leaders {lead['team']}.")


def post(ready, dry_run, out="out", gap=20, ronaldo=False, style="table"):
    import standings_post as sp  # needs Pillow; only loaded when something is ready
    now = dt.datetime.now(dt.timezone.utc)
    os.makedirs(out, exist_ok=True)
    st = load_state()
    page = token = None
    if not dry_run:
        page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    for i, (lg, days) in enumerate(ready.items()):
        if i and not dry_run:
            print(f"waiting {gap}s before {lg}")
            time.sleep(gap)  # wait BEFORE building so the table is fresh at posting time
        now = dt.datetime.now(dt.timezone.utc)
        try:
            # MLS keeps its old daily 10:00 rule: post if any MLS match finished in the last ~14 h
            item = sp.build_one(lg, now, force=(lg != "usa.1"))
        except Exception as e:
            print(f"[{lg}] ERROR building: {e}", file=sys.stderr)
            continue
        if not item:
            print(f"[{lg}] nothing to post (no table data)")
            continue
        if ronaldo and lg == "ksa.1":
            line = ronaldo_line(sp.parse_standings(sp.http_json(sp.ESPN.format(lg=lg)))[0]["rows"])
            if line:
                item["caption"] = item["caption"] + "\n" + line
        if style == "titlerace":  # "Who will win <league>?" poster, top 3 from the same live table
            try:
                import titlerace
                js = sp.http_json(sp.ESPN.format(lg=lg))
                groups = sp.parse_standings(js)
                groups = [g for g in groups if lg != "usa.1" or any("Inter Miami" in r["team"] for r in g["rows"])] or groups
                item["main"] = titlerace.render_title_race(lg, groups[0]["rows"], sp.fetch_logo)
                item["png"] = sp.to_png(item["main"])
            except Exception as e:
                print(f"[{lg}] title-race picture failed ({e}); keeping the table picture", file=sys.stderr)
        item["main"].save(f"{out}/{lg}_main.png")
        open(f"{out}/{lg}_caption.txt", "w").write(item["caption"])
        open(f"{out}/{lg}_comments.txt", "w").write("\n\n".join(f"[{l}]\n{t}" for l, t in item["comments"]))
        json.dump(item["results"], open(f"{out}/{lg}_matchdata.json", "w"), indent=1, default=str)
        print(f"[{lg}] built:\n{item['caption']}\n")
        if dry_run:
            continue
        try:
            res = sp.fb_post_photo(page, token, item["png"], item["caption"])
        except Exception as e:
            print(f"[{lg}] ERROR posting: {e}", file=sys.stderr)
            continue
        post_id = res.get("post_id") or res.get("id")
        print(f"[{lg}] posted {post_id}")
        if days != "forced":  # a manual forced repost must not block that night's automatic post
            st.setdefault(lg, []).extend(days.split(","))  # record at once so it is never posted twice
            save_state(st)
        try:
            sp.fb_like(post_id, token)
        except Exception as e:
            print(f"[{lg}] like failed: {e}", file=sys.stderr)
        for lang, text in item["comments"]:
            try:
                sp.fb_comment_text(post_id, token, text)
                print(f"[{lg}] comment [{lang}] posted")
            except Exception as e:
                print(f"[{lg}] comment [{lang}] failed: {e}", file=sys.stderr)
            time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--post", help="league codes from --check, e.g. esp.1,eng.1")
    ap.add_argument("--only", help="limit to these league codes (testing)")
    ap.add_argument("--force", action="store_true", help="treat leagues as finished (testing)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gap", type=int, default=20, help="seconds between posts")
    ap.add_argument("--ronaldo", action="store_true", help="add the Ronaldo / Al Nassr line to the Saudi caption")
    ap.add_argument("--style", default="table", choices=["table", "titlerace"], help="picture style")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    leagues = [x for x in a.only.split(",") if x in LEAGUE_TZ] if a.only else ORDER  # keeps the given order
    if a.check:
        ready = check(leagues, now, a.force)
        os.makedirs("out", exist_ok=True)
        json.dump(ready, open("out/ready.json", "w"))
        line = ",".join(ready)
        print(f"ready leagues: {line or 'none'}")
        if os.environ.get("GITHUB_OUTPUT"):
            open(os.environ["GITHUB_OUTPUT"], "a").write(f"ready={line}\n")
    elif a.post:
        try:
            ready = json.load(open("out/ready.json"))
        except Exception:
            ready = {}
        ready = {lg: ready.get(lg) or dt.datetime.now(ZoneInfo(LEAGUE_TZ[lg])).date().isoformat()
                 for lg in a.post.split(",") if lg in LEAGUE_TZ}
        post(ready, a.dry_run, gap=a.gap, ronaldo=a.ronaldo, style=a.style)


if __name__ == "__main__":
    main()
