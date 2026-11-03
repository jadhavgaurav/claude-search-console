# search-console

Read-only Google Search Console and GA4 tools for Claude Code: `list_sites`, `search_analytics`, `inspect_url`, `list_sitemaps`, `ga4_list_properties`, `ga4_run_report`.

## Setup

1. In Google Cloud, create or pick a project and enable **Google Search Console API**, **Google Analytics Data API** and **Google Analytics Admin API**.
2. Create a **service account** and download a JSON key.
3. In Search Console, open Settings > Users and permissions and add the service account email (`...@<project>.iam.gserviceaccount.com`) to each property with **Restricted** access (read only).
4. In GA4, open Admin > Property access management and add the same service account email with the **Viewer** role.
5. Export the key path in your shell profile:

   ```bash
   export GSC_CREDENTIALS_FILE="$HOME/.config/gsc/service-account.json"
   ```

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
