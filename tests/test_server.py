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
