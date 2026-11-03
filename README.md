# Infinite sport - daily table poster

Builds a league table picture + 3-4 line caption and posts it to your Facebook Page.
Europe (Premier League, La Liga, Serie A, Bundesliga) + Saudi Pro League publish at 03:30 Nepal time.
MLS publishes at 10:00 Nepal time. A league is skipped when it had no finished match in the last ~30 hours.

## One-time setup
1. Create a free GitHub account, make a new PRIVATE repository, upload everything in this folder
   (keep the `.github/workflows/post.yml` path).
2. Facebook token (do this on a computer):
   a. developers.facebook.com -> My Apps -> Create App -> type "Business". You are the admin, no app review needed.
   b. Tools -> Graph API Explorer. Pick your app, "Get Page Access Token", tick
      `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`
      and approve for the page "Infinite sport".
   c. Convert to a long-lived token (Access Token Debugger -> Extend), then in the Explorer call
      `me/accounts` with that long-lived USER token. The `access_token` shown for Infinite sport is a PAGE token
      that does not expire. The `id` next to it is your Page ID.
3. In the GitHub repo: Settings -> Secrets and variables -> Actions -> New secret:
   `FB_PAGE_ID` and `FB_PAGE_TOKEN`. Never paste these in chat or in code.
4. Actions tab -> "Post league tables" -> Run workflow, group `europe_saudi`, dry_run `true`.
   Download the `tables` artifact and check the pictures. Then run once with dry_run `false` to test a real post.
5. The two daily schedules start by themselves after that.

## Notes
- Data: ESPN's public standings feed (no key). It is unofficial and can change; if a league fails, the others still post
  and the failure shows in the Action log.
- Late MLS West Coast games can end after 10:00 Nepal time; those tables can miss that night's last game.
- GitHub may start scheduled jobs up to ~15 min late; the script builds first and waits until the exact publish time,
  or posts right away if the time has passed.
- Captions: the match is the most important one of the day (top teams, big margins). Goals and scorers come from ESPN. "Top scorer this season" is each club's own leading scorer according to ESPN. No assist data is used.
- Each run also saves raw match data (`*_matchdata.json`) in the downloadable `tables` files so wrong captions can be traced.
- Leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Saudi Pro League (03:50 Nepal start) and MLS Eastern (10:00 Nepal).
- Pictures: the STANDINGS picture is drawn by `stadium.py` at post time from the same live ESPN table that the caption uses, so the
  picture and the caption can never disagree. Club logos and the league logo are loaded from ESPN at run time; if one cannot be
  loaded that club shows its initials. Nothing needs to be uploaded or replaced by hand. (The old `posts/` pictures are no longer used.)
- A manual dry run (dry_run `true`) builds every league, ignores the "recent match" rule, posts nothing and puts the pictures on the
  `preview` branch so you can look at them.
- Caption: 3 lines from the table (leader, places 3-5, one rotating fact).
- Comments: the Page likes its own post, then writes two 2-line comments: English, then the local language of the league's
  country (Serie A Italian, La Liga Spanish, Bundesliga German, Ligue 1 French, Saudi Pro League Arabic).
  Premier League and MLS get the English comment only. There is no "Full table" comment any more.
- Facebook gives no official way for a program to like or comment from a personal profile, so that part stays manual.
- "Last 5" form dots are not included yet.
