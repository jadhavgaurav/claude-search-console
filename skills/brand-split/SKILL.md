---
name: brand-split
description: Split Search Console performance into branded and non-branded queries and show the trend. Use for "branded vs non-branded", "brand traffic" or "is SEO growth real". Uses the search-console plugin tools (search_analytics), not other SEO connectors.
---

1. Pick the property from `list_sites`. Ask for the brand terms, including common misspellings. Do not guess them.
2. Build one regex from the terms in lowercase (queries are stored lowercase), for example `(cleanstart|clean start)`.
3. For the last 28 days and the 28 days before, call `search_analytics` twice with `dimensions: ["date"]`:
   - Branded: `filters: [{"dimension": "query", "operator": "includingRegex", "expression": "<regex>"}]`
   - Non-branded: the same with `"operator": "excludingRegex"`
4. Sum clicks and impressions per segment and period. Average position is impression-weighted.
5. Report a table: segment, clicks, share of clicks, impressions, position, change versus the previous period.
6. Interpret it: growth in non-branded clicks is the real SEO signal. Rising branded clicks usually mean awareness or ads, not rankings.
7. Note the limit: Google hides anonymized queries, and on some sites that is close to half of all clicks. Compare the two segments with the site total (a call with `dimensions: ["date"]` and no filter), report the hidden share, and do not call the segments the full picture.
