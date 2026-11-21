#!/usr/bin/env python3
"""Rewrite the caption of today's already-published table posts in the new order
(results first, then the table). Never deletes or reposts anything.
  python edit_caption.py esp.1,ger.1 [--dry-run] [--hours 14]
Env: FB_PAGE_ID, FB_PAGE_TOKEN
"""
import argparse, datetime as dt, json, os, sys, urllib.request, urllib.parse
import standings_post as sp


def graph_get(path, **q):
    url = f"{sp.GRAPH}/{path}?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def graph_post(path, **f):
    body = urllib.parse.urlencode(f).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{sp.GRAPH}/{path}", data=body), timeout=60) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("leagues")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hours", type=int, default=14, help="results window for the caption")
    a = ap.parse_args()
    page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    now = dt.datetime.now(dt.timezone.utc)
    posts = graph_get(f"{page}/posts", fields="id,message,created_time", limit=25, access_token=token).get("data", [])
    recent = [p for p in posts if now - dt.datetime.strptime(p["created_time"], "%Y-%m-%dT%H:%M:%S%z") < dt.timedelta(hours=18)]
    for lg in a.leagues.split(","):
        js = sp.http_json(sp.ESPN.format(lg=lg))
        groups = sp.parse_standings(js)
        groups = [g for g in groups if lg != "usa.1" or any("Inter Miami" in r["team"] for r in g["rows"])] or groups
        old = sp.caption_table(lg, groups)
        if not old:
            print(f"[{lg}] no table data, skipped"); continue
        first = old.split("\n")[0]
        hits = [p for p in recent if (p.get("message") or "").startswith(first)]
        if not hits:
            print(f"[{lg}] no post from the last 18h starts with: {first!r} (already edited or not posted)"); continue
        results = sp.completed_results(lg, now, hours=a.hours)
        new = sp.caption_full(lg, groups, results)
        if not new or not results:
            print(f"[{lg}] no finished results found, caption left as it is"); continue
        for p in hits:
            print(f"[{lg}] post {p['id']} ({p['created_time']}) new caption:\n{new}\n")
            if not a.dry_run:
                print(f"[{lg}] edit result: {graph_post(p['id'], message=new, access_token=token)}")


if __name__ == "__main__":
    main()
