---
name: weekly-report
description: Weekly SEO and traffic report across all Search Console properties, with GA4 added where a property matches. Use for "weekly report", "how are my sites doing" or "what changed this week". Uses the search-console plugin tools (portfolio_summary, compare_periods, ga4_run_report), not other SEO connectors.
---

1. Call `portfolio_summary` with `days: 7` (use 28 if the user asks for a monthly view). The result already has the previous period.
2. Make a table, one row per site: clicks, change, impressions, change, position, change. Show any `error` rows as access problems to fix.
3. For the 2 sites with the largest click change, call `compare_periods` twice with the same windows: once with `dimension: "page"` and once with `dimension: "query"`. Windows: end = today minus 3 days, start = end minus (days - 1).
4. List the 3 biggest gains and the 3 biggest losses per site from those rows.
5. Call `ga4_list_properties`. Where a GA4 property clearly matches a site by name, run `ga4_run_report` with metrics `sessions` and `keyEvents`, dimension `sessionDefaultChannelGroup`, and `compare_start_date` and `compare_end_date` set to the previous window. If the match is not obvious, ask the user once and reuse the answer.
6. End with at most 5 actions in priority order, each tied to a number from the data.
7. Keep the whole report to one screen. To run it every week, the user can ask Claude Code to schedule this skill.
