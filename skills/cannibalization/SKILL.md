---
name: cannibalization
description: Detect keyword cannibalization in Search Console, where several pages on one site compete for the same query. Use for "cannibalization", "competing pages" or "duplicate targeting". Uses the search-console plugin tools (search_analytics), not other SEO connectors.
---

1. Pick the property from `list_sites`.
2. Call `search_analytics` for the last 90 days ending 3 days ago, `dimensions: ["query", "page"]`, `row_limit: 20000`.
3. Group rows by query. Keep queries with 2 or more pages that each have at least 10 impressions, and at least 100 impressions combined.
4. For each kept query list its pages with clicks, impressions and average position. The winner is the page with the most clicks. Flag the query as a real conflict when the winner has under 70% of the clicks.
5. Report the top 15 conflicts by combined impressions. Recommend one action per conflict:
   - Pages serve the same intent: merge them and 301 the weaker one.
   - Pages serve different intents: change titles and headings, and link the weaker page to the winner with distinct anchor text.
   - Both are fine: leave them, one page holding positions 1 to 3 is not a problem.
8. Note the limit: Search Console positions are averages and can differ by country and device, so check a flagged query by hand before merging pages.
