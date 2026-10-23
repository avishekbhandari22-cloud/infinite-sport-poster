#!/usr/bin/env python3
"""Wrapper: ESPN removed the top-level 'season' from the scoreboard JSON; read it from leagues[0].season instead."""
import us_sports_post as m

def season_info(sport, now):
    js = m.http_json(m.SB.format(path=m.SPORTS[sport]["path"], d=now.astimezone(m.ET).strftime("%Y%m%d")), tries=2)
    s = js.get("season") or {}
    lg = ((js.get("leagues") or [{}])[0].get("season")) or {}
    year = s.get("year") or lg.get("year")
    t = s.get("type") or lg.get("type")
    if isinstance(t, dict):
        t = t.get("type")
    wk = (js.get("week") or {}).get("number")
    return year, t, wk, js

m.season_info = season_info

if __name__ == "__main__":
    m.main()
