# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "google-api-python-client>=2.100", "google-auth>=2.20"]
# ///
"""Read-only Google Search Console and GA4 MCP server, authenticated with a service account."""

import os
import re
from datetime import date
from functools import lru_cache
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
MAX_ROWS = 25000
MAX_REPORT_ROWS = 250000
# GA4 accepts YYYY-MM-DD plus these relative forms.
GA_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2}|today|yesterday|\d+daysAgo)$")
DIMENSIONS = {"query", "page", "country", "device", "date", "searchAppearance"}

mcp = FastMCP("search-console")


@lru_cache(maxsize=None)
def _service(api: str, version: str) -> Any:
    path = os.environ.get("GSC_CREDENTIALS_FILE")
    if not path:
        raise RuntimeError(
            "GSC_CREDENTIALS_FILE is not set. Point it at a service account JSON key file."
        )
    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return build(api, version, credentials=creds, cache_discovery=False)


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


def build_report_request(
    property_id: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    metrics: list[str],
    limit: int,
) -> tuple[str, dict[str, Any]]:
    """Validate tool input and build a GA4 runReport property path and body."""
    pid = property_id.removeprefix("properties/")
    if not pid.isdigit():
        raise ValueError(f"property_id must be numeric (got {property_id!r})")
    for value in (start_date, end_date):
        if not GA_DATE.fullmatch(value):
            raise ValueError(f"Bad date {value!r}; use YYYY-MM-DD, today, yesterday or NdaysAgo")
    if not metrics:
        raise ValueError("metrics must not be empty")
    if not 1 <= limit <= MAX_REPORT_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_REPORT_ROWS}")
    body = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensions": [{"name": n} for n in dimensions],
        "metrics": [{"name": n} for n in metrics],
        "limit": limit,
    }
    return f"properties/{pid}", body


@mcp.tool()
def list_sites() -> list[dict[str, str]]:
    """List the Search Console properties the service account can access."""
    return _service("searchconsole", "v1").sites().list().execute().get("siteEntry", [])


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
    response = _service("searchconsole", "v1").searchanalytics().query(siteUrl=site_url, body=body).execute()
    return response.get("rows", [])


@mcp.tool()
def inspect_url(site_url: str, url: str) -> dict[str, Any]:
    """Run a URL Inspection (index status, canonical, crawl, mobile usability, rich results)."""
    body = {"inspectionUrl": url, "siteUrl": site_url}
    return _service("searchconsole", "v1").urlInspection().index().inspect(body=body).execute()


@mcp.tool()
def list_sitemaps(site_url: str) -> list[dict[str, Any]]:
    """List the sitemaps submitted for a property, with their error and warning counts."""
    return _service("searchconsole", "v1").sitemaps().list(siteUrl=site_url).execute().get("sitemap", [])


@mcp.tool()
def ga4_list_properties() -> list[dict[str, Any]]:
    """List the GA4 accounts and properties the service account can access."""
    service = _service("analyticsadmin", "v1beta")
    return service.accountSummaries().list(pageSize=200).execute().get("accountSummaries", [])


@mcp.tool()
def ga4_run_report(
    property_id: str,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Run a GA4 report and return flat rows.

    property_id: numeric GA4 property id from ga4_list_properties (e.g. 123456789).
    start_date, end_date: YYYY-MM-DD, today, yesterday or NdaysAgo (e.g. 28daysAgo).
    metrics: API names such as sessions, activeUsers, screenPageViews, conversions, totalRevenue.
    dimensions: API names such as date, pagePath, sessionDefaultChannelGroup, country, deviceCategory.
    If rowCount is larger than the rows returned, raise limit or narrow the query.
    """
    path, body = build_report_request(
        property_id, start_date, end_date, dimensions or [], metrics, limit
    )
    resp = _service("analyticsdata", "v1beta").properties().runReport(property=path, body=body).execute()
    dim_names = [h["name"] for h in resp.get("dimensionHeaders", [])]
    metric_names = [h["name"] for h in resp.get("metricHeaders", [])]
    rows = [
        dict(zip(dim_names, (v["value"] for v in r.get("dimensionValues", []))))
        | dict(zip(metric_names, (v["value"] for v in r.get("metricValues", []))))
        for r in resp.get("rows", [])
    ]
    return {"rowCount": resp.get("rowCount", 0), "rows": rows}


if __name__ == "__main__":
    mcp.run()
