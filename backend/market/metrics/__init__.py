"""Metric registry. To add a metric: write a compute function and append a MetricDef."""

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from market.config import BENCHMARK, FRED_SERIES, MULTPL_SERIES, TARGETS
from market.metrics import calc
from market.store import DataStore

ComputeFn = Callable[[DataStore, str], pd.Series]


@dataclass(frozen=True)
class MetricDef:
    id: str
    name: str
    unit: str
    kind: str  # valuation | technical
    higher_is_expensive: bool
    description: str
    sources: dict[str, str]  # target -> human-readable data source
    compute: ComputeFn = field(repr=False)

    @property
    def targets(self) -> list[str]:
        return list(self.sources)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "unit": self.unit,
            "kind": self.kind,
            "higher_is_expensive": self.higher_is_expensive,
            "description": self.description,
            "sources": self.sources,
        }


def _index_close(store: DataStore, target: str) -> pd.Series:
    return store.close(TARGETS[target]["index"])


def _pe(store: DataStore, target: str) -> pd.Series:
    # S&P 500 has a long monthly history on multpl; others only have our daily ETF snapshots.
    if target == "SPX":
        return store.observations("multpl", MULTPL_SERIES["pe"])
    return store.observations("yahoo_etf_pe", TARGETS[target]["etf"])


def _cape(store: DataStore, target: str) -> pd.Series:
    return store.observations("multpl", MULTPL_SERIES["cape"])


def _buffett(store: DataStore, target: str) -> pd.Series:
    return calc.buffett_indicator(
        store.observations("fred", FRED_SERIES["EQUITY"]),
        store.observations("fred", FRED_SERIES["GDP"]),
        store.close("^W5000"),
    )


def _erp(store: DataStore, target: str) -> pd.Series:
    return calc.earnings_yield_spread(_pe(store, target), store.observations("fred", FRED_SERIES["DGS10"]))


def _ma200(store: DataStore, target: str) -> pd.Series:
    return calc.ma_deviation(_index_close(store, target), 200)


def _drawdown(store: DataStore, target: str) -> pd.Series:
    return calc.drawdown(_index_close(store, target))


def _rel(store: DataStore, target: str) -> pd.Series:
    return calc.relative_strength_deviation(_index_close(store, target), _index_close(store, BENCHMARK), 200)


_ALL = list(TARGETS)
_ETF_PE = {t: f"Yahoo {TARGETS[t]['etf']} trailing P/E（每日快照，自開始收集起累積）" for t in _ALL}

METRICS: list[MetricDef] = [
    MetricDef(
        id="pe_ttm",
        name="本益比 (TTM)",
        unit="x",
        kind="valuation",
        higher_is_expensive=True,
        description="價格 ÷ 過去 12 個月盈餘。最直觀的估值指標，但景氣循環底部時盈餘驟降會讓本益比看起來偏高。",
        sources={**_ETF_PE, "SPX": "multpl.com S&P 500 P/E（月資料，1871 起）"},
        compute=_pe,
    ),
    MetricDef(
        id="cape",
        name="席勒本益比 CAPE",
        unit="x",
        kind="valuation",
        higher_is_expensive=True,
        description="價格 ÷ 過去 10 年經通膨調整的平均盈餘，消除景氣循環影響。對未來 10 年報酬有一定解釋力，但不適合抓短期進出場時間點。",
        sources={"SPX": "multpl.com Shiller PE（月資料，1871 起）"},
        compute=_cape,
    ),
    MetricDef(
        id="buffett",
        name="巴菲特指標",
        unit="%",
        kind="valuation",
        higher_is_expensive=True,
        description="美國企業股權總市值 ÷ GDP。季資料，最新一季之後用 Wilshire 5000 的漲跌推估到今天。衡量的是整體美股，放在 S&P 500 欄位。",
        sources={"SPX": "FRED NCBEILQ027S ÷ GDP，以 ^W5000 推估至今"},
        compute=_buffett,
    ),
    MetricDef(
        id="erp",
        name="股權風險溢酬",
        unit="pp",
        kind="valuation",
        higher_is_expensive=False,
        description="盈餘殖利率 (1 ÷ 本益比) − 10 年期公債殖利率。越低代表股票相對債券越沒吸引力，也就是越貴。",
        sources={t: f"{src.split('（')[0]} − FRED DGS10" for t, src in {**_ETF_PE, "SPX": "multpl S&P 500 P/E"}.items()},
        compute=_erp,
    ),
    MetricDef(
        id="ma200_dev",
        name="偏離 200 日均線",
        unit="%",
        kind="technical",
        higher_is_expensive=True,
        description="指數高於 200 日均線多少 %。衡量中期過熱程度，不是估值。",
        sources={t: f"Yahoo {TARGETS[t]['index']}" for t in _ALL},
        compute=_ma200,
    ),
    MetricDef(
        id="drawdown",
        name="距歷史高點",
        unit="%",
        kind="technical",
        higher_is_expensive=True,
        description="目前價格比歷史最高收盤低多少 %。0 代表正在創新高。",
        sources={t: f"Yahoo {TARGETS[t]['index']}" for t in _ALL},
        compute=_drawdown,
    ),
    MetricDef(
        id="rel_strength",
        name="相對 S&P 500 強弱",
        unit="%",
        kind="technical",
        higher_is_expensive=True,
        description="指數 ÷ S&P 500 的比值，高於自己 200 日均線多少 %。用來看科技股或半導體相對大盤是否過熱。",
        sources={t: f"Yahoo {TARGETS[t]['index']} ÷ ^GSPC" for t in _ALL if t != BENCHMARK},
        compute=_rel,
    ),
]

METRICS_BY_ID = {m.id: m for m in METRICS}
