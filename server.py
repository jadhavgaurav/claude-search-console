# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "google-api-python-client>=2.100", "google-auth>=2.20"]
# ///
"""Read-only Google Search Console MCP server, authenticated with a service account."""

import os
from datetime import date
from functools import lru_cache
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
MAX_ROWS = 25000
DIMENSIONS = {"query", "page", "country", "device", "date", "searchAppearance"}

mcp = FastMCP("search-console")


@lru_cache(maxsize=1)
def _service() -> Any:
    path = os.environ.get("GSC_CREDENTIALS_FILE")
    if not path:
        raise RuntimeError(
            "GSC_CREDENTIALS_FILE is not set. Point it at a service account JSON key file."
        )
    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def build_query_body(
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int,
    search_type: str,
    filters: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Validate tool input and build a searchanalytics.query request body."""
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    unknown = set(dimensions) - DIMENSIONS
    if unknown:
        raise ValueError(f"Unknown dimensions {sorted(unknown)}; use {sorted(DIMENSIONS)}")
    if not 1 <= row_limit <= MAX_ROWS:
        raise ValueError(f"row_limit must be between 1 and {MAX_ROWS}")
    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "type": search_type,
    }
    if filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
    return body


@mcp.tool()
def list_sites() -> list[dict[str, str]]:
    """List the Search Console properties the service account can access."""
    return _service().sites().list().execute().get("siteEntry", [])


@mcp.tool()
def search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int = 100,
    search_type: str = "web",
    filters: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Query clicks, impressions, ctr and position.

    site_url: property as listed by list_sites (e.g. https://example.com/ or sc-domain:example.com).
    start_date, end_date: YYYY-MM-DD. Data lags about 2 days.
    dimensions: any of query, page, country, device, date, searchAppearance. Defaults to ["query"].
    search_type: web, image, video, news, discover or googleNews.
    filters: list of {"dimension", "operator", "expression"}, e.g.
      {"dimension": "page", "operator": "contains", "expression": "/blog/"}.
    """
    body = build_query_body(
        start_date, end_date, dimensions or ["query"], row_limit, search_type, filters
    )
    response = _service().searchanalytics().query(siteUrl=site_url, body=body).execute()
    return response.get("rows", [])


@mcp.tool()
def inspect_url(site_url: str, url: str) -> dict[str, Any]:
    """Run a URL Inspection (index status, canonical, crawl, mobile usability, rich results)."""
    body = {"inspectionUrl": url, "siteUrl": site_url}
    return _service().urlInspection().index().inspect(body=body).execute()


@mcp.tool()
def list_sitemaps(site_url: str) -> list[dict[str, Any]]:
    """List the sitemaps submitted for a property, with their error and warning counts."""
    return _service().sitemaps().list(siteUrl=site_url).execute().get("sitemap", [])


if __name__ == "__main__":
    mcp.run()
