import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import MAX_ROWS, build_query_body  # noqa: E402


def body(**overrides):
    args = dict(
        start_date="2026-10-01",
        end_date="2026-10-31",
        dimensions=["query"],
        row_limit=10,
        search_type="web",
        filters=None,
    )
    return build_query_body(**{**args, **overrides})


def test_basic_body_has_no_filter_group():
    assert body() == {
        "startDate": "2026-10-01",
        "endDate": "2026-10-31",
        "dimensions": ["query"],
        "rowLimit": 10,
        "type": "web",
    }


def test_filters_become_and_group():
    f = [{"dimension": "page", "operator": "contains", "expression": "/blog/"}]
    assert body(filters=f)["dimensionFilterGroups"] == [{"groupType": "and", "filters": f}]


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "2026-11-01"},
        {"start_date": "10/01/2026"},
        {"dimensions": ["keyword"]},
        {"row_limit": 0},
        {"row_limit": MAX_ROWS + 1},
    ],
)
def test_invalid_input_raises(overrides):
    with pytest.raises(ValueError):
        body(**overrides)


from server import build_report_request  # noqa: E402


def test_report_request_normalizes_property_and_builds_body():
    path, req = build_report_request(
        "properties/123", "28daysAgo", "yesterday", ["pagePath"], ["sessions"], 50
    )
    assert path == "properties/123"
    assert req == {
        "dateRanges": [{"startDate": "28daysAgo", "endDate": "yesterday"}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "sessions"}],
        "limit": 50,
    }


@pytest.mark.parametrize(
    "args",
    [
        ("abc", "today", "today", [], ["sessions"], 10),
        ("1", "last week", "today", [], ["sessions"], 10),
        ("1", "today", "today", [], [], 10),
        ("1", "today", "today", [], ["sessions"], 0),
    ],
)
def test_report_request_rejects_bad_input(args):
    with pytest.raises(ValueError):
        build_report_request(*args)


from server import DEFAULT_KEY, credentials_path  # noqa: E402


def test_credentials_path_uses_env_then_default(monkeypatch):
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", "")
    assert credentials_path() == DEFAULT_KEY
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", "/tmp/k.json")
    assert credentials_path() == Path("/tmp/k.json")


from datetime import date  # noqa: E402

import server  # noqa: E402
from server import merge_periods, period_windows, previous_period  # noqa: E402


def test_previous_period_is_same_length_and_adjacent():
    assert previous_period("2026-10-01", "2026-10-28") == ("2026-09-03", "2026-09-30")


def test_period_windows_end_three_days_before_today():
    assert period_windows(7, date(2026, 11, 3)) == (
        "2026-10-25",
        "2026-10-31",
        "2026-10-18",
        "2026-10-24",
    )


def _row(key, clicks):
    return {"keys": [key], "clicks": clicks, "impressions": clicks * 10, "position": 3.0}


def test_merge_periods_sorts_by_click_change_and_keeps_missing_side_null():
    merged = merge_periods([_row("a", 10), _row("b", 5)], [_row("a", 4), _row("c", 20)])
    assert [r["key"] for r in merged] == ["c", "a", "b"]
    assert merged[0]["clicks"] is None and merged[0]["clicks_delta"] == -20
    assert merged[1]["clicks_delta"] == 6 and merged[2]["prev_clicks"] is None


class _FakeSearchAnalytics:
    def __init__(self, available):
        self.available, self.calls = available, []

    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):  # noqa: N803 (mirrors the Google client signature)
        self.calls.append((body["startRow"], body["rowLimit"]))
        start, size = body["startRow"], body["rowLimit"]
        rows = [{"keys": [str(i)]} for i in range(start, min(start + size, self.available))]
        return type("Req", (), {"execute": lambda _self: {"rows": rows}})()


def test_query_rows_pages_until_data_runs_out(monkeypatch):
    fake = _FakeSearchAnalytics(available=27000)
    monkeypatch.setattr(server, "_service", lambda api, version: fake)
    rows = server._query_rows("sc-domain:x.com", {}, 60000)
    assert len(rows) == 27000
    assert fake.calls == [(0, 25000), (25000, 25000)]


def test_report_request_with_compare_filters_and_order():
    _, req = build_report_request(
        "1",
        "2026-10-01",
        "2026-10-28",
        ["pagePath"],
        ["sessions"],
        10,
        compare_start_date="2026-09-03",
        compare_end_date="2026-09-30",
        filters=[{"dimension": "pagePath", "value": "/blog/", "match": "BEGINS_WITH"}],
        order_by="-sessions",
    )
    assert len(req["dateRanges"]) == 2
    assert req["orderBys"] == [{"metric": {"metricName": "sessions"}, "desc": True}]
    flt = req["dimensionFilter"]["andGroup"]["expressions"][0]["filter"]
    assert flt == {"fieldName": "pagePath", "stringFilter": {"matchType": "BEGINS_WITH", "value": "/blog/"}}


@pytest.mark.parametrize(
    "extra",
    [
        {"compare_start_date": "2026-09-03"},
        {"order_by": "bounceRate"},
        {"filters": [{"dimension": "pagePath", "value": "x", "match": "LIKE"}]},
    ],
)
def test_report_request_rejects_bad_options(extra):
    with pytest.raises(ValueError):
        build_report_request("1", "today", "today", ["pagePath"], ["sessions"], 10, **extra)


class _FakeMetadata:
    def properties(self):
        return self

    def getMetadata(self, name):  # noqa: N802 (mirrors the Google client signature)
        meta = {
            "dimensions": [{"apiName": f"dim{i}"} for i in range(200)],
            "metrics": [{"apiName": f"met{i}", "uiName": "Key events" if i == 7 else ""} for i in range(200)],
        }
        return type("Req", (), {"execute": lambda _self: meta})()


def test_ga4_metadata_caps_each_type_and_filters(monkeypatch):
    monkeypatch.setattr(server, "_service", lambda api, version: _FakeMetadata())
    everything = server.ga4_metadata("1")
    assert sum(r["type"] == "dimension" for r in everything) == 150
    assert sum(r["type"] == "metric" for r in everything) == 150
    assert [r["apiName"] for r in server.ga4_metadata("1", "key events")] == ["met7"]
