# search-console

Read-only Google Search Console and GA4 tools for Claude Code: `list_sites`, `search_analytics`, `compare_periods`, `portfolio_summary`, `inspect_url`, `list_sitemaps`, `ga4_list_properties`, `ga4_metadata`, `ga4_run_report`.

Skills (they tell Claude which tools to call): `quick-wins`, `cannibalization`, `brand-split`, `weekly-report`. Ask for them by name, for example "run the weekly-report skill".

- `search_analytics` pages automatically, up to 100,000 rows per call.
- `compare_periods` compares a date range with the same-length range before it, per query, page, country or device.
- `portfolio_summary` shows every property for the last N days against the N before.
- `ga4_run_report` supports a comparison period, filters and ordering. `ga4_metadata` lists valid metric and dimension names.

## Setup

1. In Google Cloud, create or pick a project and enable **Google Search Console API**, **Google Analytics Data API** and **Google Analytics Admin API**.
2. Create a **service account** and download a JSON key.
3. In Search Console, open Settings > Users and permissions and add the service account email (`...@<project>.iam.gserviceaccount.com`) to each property with **Restricted** access (read only).
4. In GA4, open Admin > Property access management and add the same service account email with the **Viewer** role.
5. Save the key as `~/.config/gsc/service-account.json`. That path is the default. To use another path, set `GSC_CREDENTIALS_FILE` (desktop apps do not read your shell profile, so prefer the default).
6. Requires `uv`. Install from the marketplace repo on any device:

   ```bash
   claude plugin marketplace add jadhavgaurav/claude-search-console
   claude plugin install search-console@gsc-tools
   ```

   For local development use `claude --plugin-dir /path/to/search-console` instead.

Then ask, for example: "List my Search Console sites" or "Top 20 queries for sc-domain:example.com over the last 28 days".

## Tests

```bash
uv run --with pytest --with "mcp<2" --with google-api-python-client --with google-auth pytest
```
