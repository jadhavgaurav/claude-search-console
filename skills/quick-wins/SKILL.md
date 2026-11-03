---
name: quick-wins
description: Find Search Console ranking quick wins, meaning queries sitting on page 1 to 2 with high impressions and weak CTR. Use for "quick wins", "low hanging fruit" or "what should I optimize" on a site. Uses the search-console plugin tools (search_analytics), not other SEO connectors.
---

1. Pick the property from `list_sites` (ask if more than one could match).
2. Call `search_analytics` for the last 28 days ending 3 days ago, `dimensions: ["query", "page"]`, `row_limit: 5000`.
3. From those rows keep position 4 to 20. Of those keep the top quarter by impressions.
4. Compare each row's CTR with the median CTR at the same rounded position across the full dataset. Flag rows below it.
5. Estimate the gain as impressions x (median CTR for positions 1 to 3 in this dataset - current CTR). Say it is an estimate.
6. Report the top 15 as a table: query, page, position, impressions, CTR, estimated extra clicks, action.
   - Position 4 to 10 with low CTR: rewrite title and meta description, check the snippet against the top results.
   - Position 11 to 20: strengthen the content for the query, add internal links to the page.
7. Close with the totals and which 3 pages to fix first.
