from src.symbols import denormalize_symbol, normalize_symbol


def test_symbol_normalize_denormalize_cn() -> None:
    assert normalize_symbol("000001", "CN", "akshare") == "000001.SZ"
    assert normalize_symbol("600000", "CN", "akshare") == "600000.SH"
    assert denormalize_symbol("000001.SZ", "CN", "akshare") == "000001"


def test_symbol_normalize_denormalize_hk_us() -> None:
    assert normalize_symbol("00700", "HK", "akshare") == "0700.HK"
    assert denormalize_symbol("0700.HK", "HK", "yfinance") == "0700.HK"
    assert normalize_symbol("spy", "US", "yfinance") == "SPY"
