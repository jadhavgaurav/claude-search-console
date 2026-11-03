# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "google-api-python-client>=2.100", "google-auth>=2.20"]
# ///
"""Read-only Google Search Console and GA4 MCP server, authenticated with a service account."""

import os
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import FastMCP

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
PAGE_ROWS = 25000  # Search Console returns at most this many rows per request.
MAX_ROWS = 100000  # Total rows one tool call may page through.
MAX_REPORT_ROWS = 250000
MAX_METADATA_ROWS = 150  # per type (dimensions, metrics)
DATA_LAG_DAYS = 3
# GA4 accepts YYYY-MM-DD plus these relative forms.
GA_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2}|today|yesterday|\d+daysAgo)$")
GA_MATCH_TYPES = {"EXACT", "BEGINS_WITH", "ENDS_WITH", "CONTAINS", "FULL_REGEXP", "PARTIAL_REGEXP"}
# Desktop apps do not inherit shell profile variables, so a default path keeps the plugin working there.
DEFAULT_KEY = Path.home() / ".config" / "gsc" / "service-account.json"
DIMENSIONS = {"query", "page", "country", "device", "date", "searchAppearance"}

mcp = FastMCP("search-console")


def credentials_path() -> Path:
    """Key file from GSC_CREDENTIALS_FILE when set and non-empty, else DEFAULT_KEY."""
    return Path(os.environ.get("GSC_CREDENTIALS_FILE") or DEFAULT_KEY).expanduser()


@lru_cache(maxsize=None)
def _service(api: str, version: str) -> Any:
    path = credentials_path()
    if not path.is_file():
        raise RuntimeError(
            f"Service account key not found at {path}. "
            "Save the JSON key there or set GSC_CREDENTIALS_FILE."
        )
    creds = service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
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


def previous_period(start_date: str, end_date: str) -> tuple[str, str]:
    """The same-length window that ends the day before start_date."""
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - (end - start)
    return prev_start.isoformat(), prev_end.isoformat()


def period_windows(days: int, today: date) -> tuple[str, str, str, str]:
    """(start, end, prev_start, prev_end) for the last `days` days with data, plus the window before."""
    end = today - timedelta(days=DATA_LAG_DAYS)
    start = end - timedelta(days=days - 1)
    prev_start, prev_end = previous_period(start.isoformat(), end.isoformat())
    return start.isoformat(), end.isoformat(), prev_start, prev_end


def merge_periods(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join two single-dimension Search Console row lists by key, biggest click movers first."""
    cur = {r["keys"][0]: r for r in current}
    prev = {r["keys"][0]: r for r in previous}
    merged = []
    for key in cur.keys() | prev.keys():
        c, p = cur.get(key), prev.get(key)
        row: dict[str, Any] = {"key": key}
        for metric in ("clicks", "impressions", "position"):
            row[metric] = c[metric] if c else None
            row[f"prev_{metric}"] = p[metric] if p else None
        row["clicks_delta"] = (c["clicks"] if c else 0) - (p["clicks"] if p else 0)
        merged.append(row)
    return sorted(merged, key=lambda r: abs(r["clicks_delta"]), reverse=True)


def normalize_property(property_id: str) -> str:
    """Return the GA4 resource path 'properties/<id>' for a numeric id or an existing path."""
    pid = property_id.removeprefix("properties/")
    if not pid.isdigit():
        raise ValueError(f"property_id must be numeric (got {property_id!r})")
    return f"properties/{pid}"


def build_report_request(
    property_id: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    metrics: list[str],
    limit: int,
    compare_start_date: str | None = None,
    compare_end_date: str | None = None,
    filters: list[dict[str, str]] | None = None,
    order_by: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate tool input and build a GA4 runReport property path and body."""
    path = normalize_property(property_id)
    ranges = [(start_date, end_date)]
    if (compare_start_date is None) != (compare_end_date is None):
        raise ValueError("Give both compare_start_date and compare_end_date, or neither")
    if compare_start_date and compare_end_date:
        ranges.append((compare_start_date, compare_end_date))
    for value in (v for pair in ranges for v in pair):
        if not GA_DATE.fullmatch(value):
            raise ValueError(f"Bad date {value!r}; use YYYY-MM-DD, today, yesterday or NdaysAgo")
    if not metrics:
        raise ValueError("metrics must not be empty")
    if not 1 <= limit <= MAX_REPORT_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_REPORT_ROWS}")
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": s, "endDate": e} for s, e in ranges],
        "dimensions": [{"name": n} for n in dimensions],
        "metrics": [{"name": n} for n in metrics],
        "limit": limit,
    }
    if filters:
        for f in filters:
            if f.get("match", "EXACT") not in GA_MATCH_TYPES:
                raise ValueError(f"match must be one of {sorted(GA_MATCH_TYPES)}")
        body["dimensionFilter"] = {
            "andGroup": {
                "expressions": [
                    {
                        "filter": {
                            "fieldName": f["dimension"],
                            "stringFilter": {"matchType": f.get("match", "EXACT"), "value": f["value"]},
                        }
                    }
                    for f in filters
                ]
            }
        }
    if order_by:
        name = order_by.lstrip("-")
        if name in metrics:
            key = {"metric": {"metricName": name}}
        elif name in dimensions:
            key = {"dimension": {"dimensionName": name}}
        else:
            raise ValueError(f"order_by {name!r} must be one of the requested metrics or dimensions")
        body["orderBys"] = [{**key, "desc": order_by.startswith("-")}]
    return path, body


def _query_rows(site_url: str, body: dict[str, Any], total: int) -> list[dict[str, Any]]:
    """Run a searchanalytics query, paging with startRow until `total` rows or no more data."""
    api = _service("searchconsole", "v1").searchanalytics()
    rows: list[dict[str, Any]] = []
    while len(rows) < total:
        size = min(PAGE_ROWS, total - len(rows))
        page = {**body, "rowLimit": size, "startRow": len(rows)}
        got = api.query(siteUrl=site_url, body=page).execute().get("rows", [])
        rows += got
        if len(got) < size:
            break
    return rows


def _totals(site_url: str, start: str, end: str) -> dict[str, float]:
    body = {"startDate": start, "endDate": end}
    resp = _service("searchconsole", "v1").searchanalytics().query(siteUrl=site_url, body=body).execute()
    row = (resp.get("rows") or [{}])[0]
    return {k: row.get(k, 0) for k in ("clicks", "impressions", "position")}


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
    """Query clicks, impressions, ctr and position. Pages automatically up to row_limit (max 100000).

    site_url: property as listed by list_sites (e.g. https://example.com/ or sc-domain:example.com).
    start_date, end_date: YYYY-MM-DD. Data lags about 3 days.
    dimensions: any of query, page, country, device, date, searchAppearance. Defaults to ["query"].
    search_type: web, image, video, news, discover or googleNews.
    filters: list of {"dimension", "operator", "expression"}. Operators: equals, notEquals,
      contains, notContains, includingRegex, excludingRegex. Example:
      {"dimension": "page", "operator": "contains", "expression": "/blog/"}.
    """
    body = build_query_body(
        start_date, end_date, dimensions or ["query"], row_limit, search_type, filters
    )
    return _query_rows(site_url, body, row_limit)


@mcp.tool()
def compare_periods(
    site_url: str,
    start_date: str,
    end_date: str,
    dimension: str = "query",
    row_limit: int = 500,
    search_type: str = "web",
    filters: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Compare a period with the same-length period just before it, per query, page, country or device.

    Returns rows sorted by the biggest change in clicks, with clicks, impressions and position for
    both periods (prev_* is the earlier one; null means the key had no rows in that period).
    The top row_limit keys by clicks are fetched for each period, so a key outside that top list
    in one period shows null there even if it had a few clicks. Raise row_limit for long tails.
    filters: same format as search_analytics.
    """
    prev_start, prev_end = previous_period(start_date, end_date)
    periods = []
    for start, end in ((start_date, end_date), (prev_start, prev_end)):
        body = build_query_body(start, end, [dimension], row_limit, search_type, filters)
        periods.append(_query_rows(site_url, body, row_limit))
    return merge_periods(*periods)[:row_limit]


@mcp.tool()
def portfolio_summary(days: int = 28) -> list[dict[str, Any]]:
    """Clicks, impressions and average position for every Search Console property.

    Compares the last `days` days (ending 3 days ago, when data is complete) with the `days` before.
    A property that fails (for example a permissions problem) gets an "error" field instead of numbers.
    """
    if not 1 <= days <= 240:
        raise ValueError("days must be between 1 and 240 (Search Console keeps about 16 months)")
    start, end, prev_start, prev_end = period_windows(days, date.today())
    summary = []
    for site in list_sites():
        url = site["siteUrl"]
        try:
            cur, prev = _totals(url, start, end), _totals(url, prev_start, prev_end)
        except HttpError as exc:
            summary.append({"site": url, "error": str(exc)})
            continue
        summary.append(
            {"site": url, "period": f"{start} to {end}"}
            | {k: cur[k] for k in cur}
            | {f"prev_{k}": prev[k] for k in prev}
        )
    return summary


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
def ga4_metadata(property_id: str, search: str = "") -> list[dict[str, Any]]:
    """List the dimensions and metrics a GA4 property supports, including its custom ones.

    search: case-insensitive text matched against name and description (e.g. "conversion", "revenue").
    Returns at most 150 dimensions and 150 metrics, so pass a search term. custom=true marks
    property-specific definitions. GA4 now calls conversions "key events" (metric keyEvents).
    """
    path = normalize_property(property_id)
    meta = _service("analyticsdata", "v1beta").properties().getMetadata(name=f"{path}/metadata").execute()
    needle = search.lower()
    found: list[dict[str, Any]] = []
    for kind, key in (("dimension", "dimensions"), ("metric", "metrics")):
        matches = [
            {
                "type": kind,
                "apiName": item["apiName"],
                "uiName": item.get("uiName", ""),
                "custom": item.get("customDefinition", False),
            }
            for item in meta.get(key, [])
            if needle in f"{item['apiName']} {item.get('uiName', '')} {item.get('description', '')}".lower()
        ]
        found += matches[:MAX_METADATA_ROWS]
    return found


@mcp.tool()
def ga4_run_report(
    property_id: str,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    limit: int = 100,
    compare_start_date: str | None = None,
    compare_end_date: str | None = None,
    filters: list[dict[str, str]] | None = None,
    order_by: str | None = None,
) -> dict[str, Any]:
    """Run a GA4 report and return flat rows.

    property_id: numeric GA4 property id from ga4_list_properties (e.g. 123456789).
    start_date, end_date: YYYY-MM-DD, today, yesterday or NdaysAgo (e.g. 28daysAgo).
    metrics: API names such as sessions, activeUsers, screenPageViews, keyEvents, totalRevenue.
      Use ga4_metadata to find valid names.
    dimensions: API names such as date, pagePath, sessionDefaultChannelGroup, country, deviceCategory.
    compare_start_date, compare_end_date: optional second period. Rows then carry a dateRange field
      (date_range_0 is the main period, date_range_1 the comparison). A period with no data has no rows.
    filters: list of {"dimension", "value", "match"}, all must match. match defaults to EXACT; also
      BEGINS_WITH, ENDS_WITH, CONTAINS, FULL_REGEXP, PARTIAL_REGEXP.
      Example: {"dimension": "pagePath", "value": "/blog/", "match": "BEGINS_WITH"}.
    order_by: a requested metric or dimension; prefix with - for descending (e.g. "-sessions").
    If rowCount is larger than the rows returned, raise limit or narrow the query. With a comparison
    period, limit counts rows across both periods, so use about twice the rows you want per period.
    """
    path, body = build_report_request(
        property_id,
        start_date,
        end_date,
        dimensions or [],
        metrics,
        limit,
        compare_start_date,
        compare_end_date,
        filters,
        order_by,
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
