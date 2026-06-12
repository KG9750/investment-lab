from __future__ import annotations

import sys
import types

import pandas as pd

from src.data_sources.baostock_source import BaoStockSource
from src.data_sources.base import PriceRequest
from src.data_sources.efinance_source import EFinanceSource


def test_baostock_source_standardizes_price_frame(monkeypatch, capsys) -> None:
    class LoginResult:
        error_code = "0"
        error_msg = ""

    class QueryResult:
        error_code = "0"
        error_msg = ""
        fields = ["date", "open", "high", "low", "close", "volume", "amount"]

        def __init__(self) -> None:
            self.rows = [["2024-01-02", "1", "2", "1", "2", "100", "200"]]
            self.index = -1

        def next(self) -> bool:
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self) -> list[str]:
            return self.rows[self.index]

    def fake_login():
        print("login success!")
        return LoginResult()

    def fake_logout():
        print("logout success!")

    fake = types.SimpleNamespace(
        login=fake_login,
        logout=fake_logout,
        query_history_k_data_plus=lambda *args, **kwargs: QueryResult(),
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)

    out = BaoStockSource().get_price(
        PriceRequest("600000.SH", "CN", "2024-01-01", snapshot_id="s1")
    )

    assert out.iloc[0]["symbol"] == "600000.SH"
    assert out.iloc[0]["provider_symbol"] == "sh.600000"
    assert out.iloc[0]["provider"] == "baostock"
    assert out.iloc[0]["adjust"] == "forward_adjusted"
    assert capsys.readouterr().out == ""


def test_efinance_source_standardizes_price_frame(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "日期": "2024-01-02",
                "开盘": 1,
                "最高": 2,
                "最低": 1,
                "收盘": 2,
                "成交量": 100,
                "成交额": 200,
            }
        ]
    )
    def fake_history(**kwargs):
        assert kwargs["stock_codes"] == "000001"
        return frame

    fake_stock = types.SimpleNamespace(get_quote_history=fake_history)
    fake_market = types.SimpleNamespace(A_stock="A", Hongkong="HK", US_stock="US")
    fake_common = types.SimpleNamespace(config=types.SimpleNamespace(MarketType=fake_market))
    fake = types.SimpleNamespace(stock=fake_stock, common=fake_common)
    monkeypatch.setitem(sys.modules, "efinance", fake)

    out = EFinanceSource().get_price(
        PriceRequest("000001.SZ", "CN", "2024-01-01", snapshot_id="s1")
    )

    assert out.iloc[0]["symbol"] == "000001.SZ"
    assert out.iloc[0]["provider_symbol"] == "000001"
    assert out.iloc[0]["provider"] == "efinance"
