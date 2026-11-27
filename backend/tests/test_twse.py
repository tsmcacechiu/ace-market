import math

import pandas as pd
import pytest

from market.collectors import twse

OLD_FORMAT = {  # 2005-2019: 日期, 本益比, 殖利率, 股價淨值比
    "stat": "OK",
    "fields": ["日期", "本益比", "殖利率(%)", "股價淨值比"],
    "data": [["094年09月02日", "15.25", "4.73", "3.38"], ["094年09月05日", "-", "4.70", "3.40"]],
}
NEW_FORMAT = {  # 2020-: 日期, 殖利率, 股利年度, 本益比, 股價淨值比, 財報年/季
    "stat": "OK",
    "fields": ["日期", "殖利率(%)", "股利年度", "本益比", "股價淨值比", "財報年/季"],
    "data": [["115年11月26日", "1.03", 114, "21.83", "7.95", "115/3"]],
}


def test_parse_old_format_by_field_name():
    df = twse.parse_bwibbu(OLD_FORMAT)
    assert list(df.columns) == ["pe", "yield", "pb"]
    assert df.index[0] == pd.Timestamp("2005-09-02")  # ROC 94 = 2005
    assert df.loc["2005-09-02"].tolist() == [15.25, 4.73, 3.38]
    assert math.isnan(df.loc["2005-09-05", "pe"])  # "-" (e.g. losses) -> missing, not 0


def test_parse_new_format_by_field_name():
    df = twse.parse_bwibbu(NEW_FORMAT)
    assert df.index[0] == pd.Timestamp("2026-11-26")  # ROC 115 = 2026
    assert df.loc["2026-11-26"].tolist() == [21.83, 1.03, 7.95]


def test_parse_no_data_month_is_empty():
    assert twse.parse_bwibbu({"stat": "很抱歉，沒有符合條件的資料!"}).empty


def test_parse_unexpected_error_raises():
    with pytest.raises(RuntimeError):
        twse.parse_bwibbu({"stat": "查詢日期小於94年09月，請重新查詢!"})


def test_months_between():
    assert twse.months_between(pd.Timestamp("2025-11-15"), pd.Timestamp("2026-02-03")) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)
    ]


def test_get_json_retries_transient_failures(monkeypatch):
    calls = []

    def flaky(url):
        calls.append(url)
        if len(calls) < 3:
            raise TimeoutError("stalled")
        return '{"stat": "OK"}'

    monkeypatch.setattr(twse, "get_text", flaky)
    monkeypatch.setattr(twse, "RETRY_WAITS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(twse, "MIN_INTERVAL", 0.0)
    assert twse._get_json("u") == {"stat": "OK"}
    assert len(calls) == 3


def test_get_json_gives_up_after_the_last_retry(monkeypatch):
    monkeypatch.setattr(twse, "get_text", lambda url: (_ for _ in ()).throw(TimeoutError("stalled")))
    monkeypatch.setattr(twse, "RETRY_WAITS", (0.0,))
    monkeypatch.setattr(twse, "MIN_INTERVAL", 0.0)
    with pytest.raises(TimeoutError):
        twse._get_json("u")
