"""Metric registry. To add a metric: write a compute function and append a MetricDef."""

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from market.config import BENCHMARK, FRED_SERIES, MULTPL_SERIES, STOCK_BENCHMARK, TARGETS
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
    # False = shown in the table for reference only, left out of the composite temperature
    # (e.g. extra moving-average windows would otherwise count the same signal several times).
    in_temperature: bool = True

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
            "in_temperature": self.in_temperature,
        }


def _index_close(store: DataStore, target: str) -> pd.Series:
    return store.close(TARGETS[target]["index"])


def _pe(store: DataStore, target: str) -> pd.Series:
    # S&P 500 has a long monthly history on multpl; TWSE stocks have daily history since 2005;
    # others only have our daily ETF snapshots.
    if target == "SPX":
        return store.observations("multpl", MULTPL_SERIES["pe"])
    if code := TARGETS[target].get("twse"):
        return store.observations("twse", f"{code}:pe")
    return store.observations("yahoo_etf_pe", TARGETS[target]["etf"])


def _twse(field: str) -> ComputeFn:
    return lambda store, target: store.observations("twse", f"{TARGETS[target]['twse']}:{field}")


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


def _ma_dev(window: int) -> ComputeFn:
    return lambda store, target: calc.ma_deviation(_index_close(store, target), window)


def _ma_dev_metric(window: int, note: str, in_temperature: bool) -> MetricDef:
    return MetricDef(
        id=f"ma{window}_dev",
        name=f"偏離 {window} 日均線",
        unit="%",
        kind="technical",
        higher_is_expensive=True,
        description=f"價格高於 {window} 日均線多少 %。{note}不是估值。"
        "（比特幣全年無休，以自然日計算。）",
        sources={t: f"Yahoo {TARGETS[t]['index']}" for t in _ALL},
        compute=_ma_dev(window),
        in_temperature=in_temperature,
    )


def _drawdown(store: DataStore, target: str) -> pd.Series:
    return calc.drawdown(_index_close(store, target))


def _rel(store: DataStore, target: str) -> pd.Series:
    return calc.relative_strength_deviation(_index_close(store, target), _index_close(store, BENCHMARK), 200)


def _rel_tw(store: DataStore, target: str) -> pd.Series:
    return calc.relative_strength_deviation(
        _index_close(store, target), _index_close(store, STOCK_BENCHMARK), 200
    )


_ALL = list(TARGETS)
_MARKET = [t for t in _ALL if TARGETS[t]["group"] == "market"]
_STOCKS = [t for t in _ALL if TARGETS[t]["group"] == "stock"]
_TWSE = {t: f"證交所 {TARGETS[t]['twse']}" for t in _ALL if TARGETS[t].get("twse")}
_US = [t for t in _ALL if TARGETS[t]["market"] == "US"]
# Only assets with an earnings proxy get P/E-based metrics.
_ETF_PE = {
    t: f"Yahoo {TARGETS[t]['etf']} trailing P/E（每日快照，自開始收集起累積）" for t in _ALL if TARGETS[t]["etf"]
}

METRICS: list[MetricDef] = [
    MetricDef(
        id="pe_ttm",
        name="本益比 (TTM)",
        unit="x",
        kind="valuation",
        higher_is_expensive=True,
        description="價格 ÷ 過去 12 個月盈餘。最直觀的估值指標，但景氣循環底部時盈餘驟降會讓本益比看起來偏高。",
        sources={
            **_ETF_PE,
            "SPX": "multpl.com S&P 500 P/E（月資料，1871 起）",
            **{t: f"{src} 本益比（每日，2005/09 起）" for t, src in _TWSE.items()},
        },
        compute=_pe,
    ),
    MetricDef(
        id="pb",
        name="股價淨值比",
        unit="x",
        kind="valuation",
        higher_is_expensive=True,
        description="股價 ÷ 每股淨值。盈餘波動大時比本益比穩定，適合看景氣循環股。",
        sources={t: f"{src} 股價淨值比（每日，2005/09 起）" for t, src in _TWSE.items()},
        compute=_twse("pb"),
    ),
    MetricDef(
        id="div_yield",
        name="殖利率",
        unit="%",
        kind="valuation",
        higher_is_expensive=False,
        description="最近年度現金股利 ÷ 股價。殖利率越低代表股價相對配息越貴。",
        sources={t: f"{src} 殖利率（每日，2005/09 起）" for t, src in _TWSE.items()},
        compute=_twse("yield"),
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
        # US only: comparing Taiwan earnings yield with the US 10Y yield is not meaningful.
        sources={
            t: f"{src.split('（')[0]} − FRED DGS10"
            for t, src in {**_ETF_PE, "SPX": "multpl S&P 500 P/E"}.items()
            if t in _US and t in _ETF_PE
        },
        compute=_erp,
    ),
    _ma_dev_metric(200, "衡量中期過熱程度，", in_temperature=True),
    # Reference only: same signal as the 200-day deviation, so not counted in the temperature again.
    _ma_dev_metric(240, "240 日即台股常說的「年線」。僅供參考，不計入市場溫度，", in_temperature=False),
    _ma_dev_metric(500, "約兩年的長期趨勢。僅供參考，不計入市場溫度，", in_temperature=False),
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
        description="價格 ÷ S&P 500 的比值，高於自己 200 日均線多少 %。用來看科技股、半導體、黃金或比特幣相對美股大盤是否過熱。",
        sources={t: f"Yahoo {TARGETS[t]['index']} ÷ ^GSPC" for t in _MARKET if t != BENCHMARK},
        compute=_rel,
    ),
    MetricDef(
        id="rel_twii",
        name="相對台灣加權強弱",
        unit="%",
        kind="technical",
        higher_is_expensive=True,
        description="個股 ÷ 台灣加權指數的比值，高於自己 200 日均線多少 %。看個股相對台股大盤是否過熱。",
        sources={t: f"Yahoo {TARGETS[t]['index']} ÷ ^TWII" for t in _STOCKS},
        compute=_rel_tw,
    ),
]

METRICS_BY_ID = {m.id: m for m in METRICS}
